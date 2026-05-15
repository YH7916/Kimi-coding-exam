"""HTTP route declarations."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response, status

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.evidence import EvidenceExtractor, EvidenceItem
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentCreate,
    DocumentCreated,
    DocumentDetail,
    SearchResponse,
    chat_response,
    document_detail,
    search_response,
)
from oncall_app.api.static_files import read_frontend_shell
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient, create_chat_client
from oncall_app.llm.config import chat_config_from_env, embedding_config_from_env
from oncall_app.llm.embedding_client import EmbeddingClient, create_embedding_client
from oncall_app.models import ConversationTurn, ToolCall
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDING_CACHE_PATH = PROJECT_ROOT / ".cache" / "embeddings.sqlite3"
AGENT_CANDIDATE_LIMIT = 5
RETRIEVAL_HISTORY_TURNS = 4
MAX_RETRIEVAL_QUERY_CHARS = 800

router = APIRouter()


class SearchRuntime:
    """Holds mutable document and retrieval state for the API process."""

    def __init__(
        self,
        data_dir: Path,
        test_mode: bool = False,
        embedding_client: EmbeddingClient | None = None,
        embedding_cache_path: Path | None = EMBEDDING_CACHE_PATH,
    ):
        self.data_dir = data_dir
        self.test_mode = test_mode
        self._embedding_client_override = embedding_client
        self.embedding_cache_path = embedding_cache_path
        self.repository = DocumentRepository(data_dir)
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def reset(self, test_mode: bool = False) -> None:
        """Reset repository and retrieval state from disk."""
        self.test_mode = test_mode
        self.repository = DocumentRepository(self.data_dir)
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Rebuild retrieval indexes from repository documents."""
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def chat(self, message: str, history: list[ConversationTurn] | None = None):
        """Answer with v2 hybrid retrieval candidates feeding the v3 Agent."""
        turns = history or []
        retrieval_query = _conversation_query(message, turns)
        candidates = self.service.semantic_search(retrieval_query, limit=AGENT_CANDIDATE_LIMIT)
        return self.assistant.chat(
            message,
            retrieval_candidates=candidates,
            history=turns,
        )

    def _build_retrieval_service(self) -> RetrievalService:
        """Build v1/v2 retrieval with optional real embedding support."""
        embedding_client, embedding_cache = self._embedding_components()
        return RetrievalService.from_documents(
            self.repository.all_documents(),
            embedding_client=embedding_client,
            embedding_cache=embedding_cache,
        )

    def _embedding_components(self) -> tuple[EmbeddingClient | None, EmbeddingCache | None]:
        """Return embedding client/cache for production v2 search."""
        if self._embedding_client_override is not None:
            return self._embedding_client_override, None
        if self.test_mode:
            return None, None

        config = embedding_config_from_env()
        if not (config.base_url and config.api_key and config.model):
            return None, None
        cache = (
            EmbeddingCache(self.embedding_cache_path, config.model)
            if self.embedding_cache_path is not None
            else None
        )
        return create_embedding_client(config), cache

    def _build_assistant(self) -> OnCallAssistant:
        """Build the v3 assistant."""
        return OnCallAssistant(
            repository=self.repository,
            chat_client=_chat_client(self.test_mode),
        )


@router.get("/health")
def health() -> dict[str, str]:
    """Return process health."""
    return {"status": "ok"}


@router.get("/v1", response_class=Response)
@router.get("/v2", response_class=Response)
@router.get("/v3", response_class=Response)
def frontend_page() -> Response:
    """Serve the frontend shell for each README page route."""
    return Response(read_frontend_shell(), media_type="text/html")


@router.get("/v1/search")
def v1_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with BM25 lexical retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.keyword_search(query))


@router.post("/v1/documents", status_code=status.HTTP_201_CREATED)
def v1_documents(payload: DocumentCreate) -> DocumentCreated:
    """Add an SOP document to the in-memory repository and index."""
    document = runtime.repository.add_document(
        payload.id,
        payload.html,
        file_name=f"{payload.id}.html",
    )
    runtime.rebuild_index()
    return DocumentCreated(id=document.doc_id, title=document.title)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str) -> DocumentDetail:
    """Return one parsed SOP document for frontend source preview."""
    normalized_id = doc_id.removesuffix(".html")
    try:
        return document_detail(runtime.repository.get(normalized_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc


@router.get("/v2/search")
def v2_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with semantic retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.service.semantic_search(query))


@router.post("/v3/chat")
def v3_chat(payload: ChatRequest) -> ChatResponse:
    """Answer an On-Call question with a traceable tool-using Agent."""
    history = [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]
    retrieval_query = _conversation_query(payload.message, history)
    response = runtime.chat(payload.message, history=history)
    evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
    return chat_response(response, evidence)


def _normalize_query(q: str) -> str:
    """Normalize README query behavior."""
    return "&" if q == "" else q


def _chat_client(test_mode: bool) -> ChatClient:
    """Return the real chat client when configured, otherwise a local fallback."""
    if test_mode:
        return LocalChatClient()
    config = chat_config_from_env()
    if config.base_url and config.api_key and config.model:
        return create_chat_client(config)
    return LocalChatClient()


def _evidence_for_tool_calls(message: str, tool_calls: list[ToolCall]) -> list[EvidenceItem]:
    """Extract evidence for HTML files read by the agent."""
    documents = []
    for call in tool_calls:
        if not call.fname.endswith(".html"):
            continue
        try:
            documents.append(runtime.repository.get(Path(call.fname).stem))
        except KeyError:
            continue
    return EvidenceExtractor().extract(message, documents)


def _conversation_query(message: str, history: list[ConversationTurn]) -> str:
    """Build a compact retrieval query from recent user-visible context."""
    recent_user_turns = [
        turn.content.strip()
        for turn in history[-RETRIEVAL_HISTORY_TURNS:]
        if turn.role == "user" and turn.content.strip()
    ]
    combined = " ".join([*recent_user_turns, message.strip()]).strip()
    if len(combined) <= MAX_RETRIEVAL_QUERY_CHARS:
        return combined
    return combined[-MAX_RETRIEVAL_QUERY_CHARS:]


runtime = SearchRuntime(DATA_DIR, test_mode=True)


def reset_runtime(test_mode: bool = False) -> None:
    """Reset API runtime state."""
    runtime.reset(test_mode=test_mode)
