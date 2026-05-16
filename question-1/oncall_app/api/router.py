"""HTTP route declarations."""

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.evidence import EvidenceExtractor, EvidenceItem
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentCreate,
    DocumentCreated,
    DocumentDetail,
    EmbeddingCacheStatus,
    MemoryRecordListResponse,
    MemorySearchResponse,
    ProviderEndpointStatus,
    ProviderStatusResponse,
    SearchResponse,
    chat_response,
    document_detail,
    memory_record_list,
    memory_search_response,
    search_response,
)
from oncall_app.api.static_files import read_frontend_shell
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient, create_chat_client
from oncall_app.llm.config import chat_config_from_env, embedding_config_from_env
from oncall_app.llm.embedding_client import EmbeddingClient, create_embedding_client
from oncall_app.memory.context import format_memory_context
from oncall_app.memory.extractor import DeterministicMemoryExtractor
from oncall_app.memory.models import MemorySearchHit, RawMemoryEvent
from oncall_app.memory.retrieval import MemoryRetriever
from oncall_app.memory.store import MemoryStore
from oncall_app.models import (
    AgentResponse,
    AgentStreamEvent,
    ConversationTurn,
    SearchResult,
    ToolCall,
)
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDING_CACHE_PATH = PROJECT_ROOT / ".cache" / "embeddings.sqlite3"
MEMORY_STORE_PATH = PROJECT_ROOT / ".cache" / "memory.sqlite3"
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
        memory_store_path: Path | None = MEMORY_STORE_PATH,
    ):
        self.data_dir = data_dir
        self.test_mode = test_mode
        self._embedding_client_override = embedding_client
        self.embedding_cache_path = embedding_cache_path
        self.memory_store_path = memory_store_path
        self.repository = DocumentRepository(data_dir)
        self._build_memory_components(reset_store=test_mode)
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def reset(self, test_mode: bool = False) -> None:
        """Reset repository and retrieval state from disk."""
        self.test_mode = test_mode
        self.repository = DocumentRepository(self.data_dir)
        self._build_memory_components(reset_store=test_mode)
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
        memory_hits = self._memory_hits(retrieval_query)
        return self.assistant.chat(
            message,
            retrieval_candidates=candidates,
            history=turns,
            memory_context=format_memory_context(memory_hits),
            memory_hits=memory_hits,
        )

    def chat_events(
        self,
        message: str,
        history: list[ConversationTurn] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        """Yield retrieval and Agent events for SSE streaming."""
        turns = history or []
        retrieval_query = _conversation_query(message, turns)
        candidates = self.service.semantic_search(retrieval_query, limit=AGENT_CANDIDATE_LIMIT)
        memory_hits = self._memory_hits(retrieval_query)
        yield AgentStreamEvent(
            type="retrieval",
            payload={
                "query": retrieval_query,
                "candidates": candidates,
            },
        )
        if memory_hits:
            yield AgentStreamEvent(
                type="memory",
                payload={"memory_hits": memory_hits},
            )
        yield from self.assistant.stream_chat(
            message,
            retrieval_candidates=candidates,
            history=turns,
            memory_context=format_memory_context(memory_hits),
            memory_hits=memory_hits,
        )

    def record_interaction(
        self,
        message: str,
        response: AgentResponse,
        evidence: list[EvidenceItem],
    ) -> None:
        """Persist one completed chat turn and extract durable memories."""
        event = self.memory_store.add_event(
            RawMemoryEvent(
                session_id="default",
                user_message=message,
                assistant_answer=response.answer,
                tool_calls=[
                    {
                        "tool": call.tool,
                        "fname": call.fname,
                        "result_preview": call.result_preview,
                    }
                    for call in response.tool_calls
                ],
                evidence=[
                    {
                        "file": item.file,
                        "section": item.section_heading,
                        "text": item.text,
                    }
                    for item in evidence
                ],
                trace=[
                    {
                        "type": "memory",
                        "message": f"used {len(response.memory_hits)} recalled memories",
                    }
                ],
            )
        )
        for memory in self.memory_extractor.extract(event):
            self.memory_store.upsert_memory(memory)

    def provider_status(self) -> ProviderStatusResponse:
        """Return non-sensitive provider and cache status."""
        embedding_config = embedding_config_from_env()
        chat_config = chat_config_from_env()
        embedding_configured = bool(
            embedding_config.base_url
            and embedding_config.api_key
            and embedding_config.model
        )
        chat_configured = bool(
            chat_config.base_url
            and chat_config.api_key
            and chat_config.model
        )
        embedding_is_real = (
            not self.test_mode
            and self.service.has_vector_index
            and embedding_configured
        )
        chat_is_real = not self.test_mode and chat_configured
        cache_stats = self.service.embedding_cache_stats
        return ProviderStatusResponse(
            embedding=_endpoint_status(
                is_real=embedding_is_real,
                model=embedding_config.model,
                base_url=embedding_config.base_url,
                real_detail="SiliconFlow embeddings active",
                fallback_detail="deterministic semantic fallback active",
            ),
            chat=_endpoint_status(
                is_real=chat_is_real,
                model=chat_config.model,
                base_url=chat_config.base_url,
                real_detail="OpenAI-compatible Chat Completions active",
                fallback_detail="local deterministic chat fallback active",
            ),
            cache=_cache_status(cache_stats),
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

    def _build_memory_components(self, reset_store: bool = False) -> None:
        """Build memory store and recall helpers."""
        del reset_store
        path = (
            PROJECT_ROOT / ".cache" / f"test-memory-{uuid4().hex}.sqlite3"
            if self.test_mode
            else self.memory_store_path
        )
        if path is None:
            path = MEMORY_STORE_PATH
        self.memory_store = MemoryStore(path)
        self.memory_retriever = MemoryRetriever(self.memory_store)
        self.memory_extractor = DeterministicMemoryExtractor()

    def _memory_hits(self, query: str) -> list[MemorySearchHit]:
        """Return profile plus query-specific memory hits."""
        return _dedupe_memory_hits(
            [
                *self.memory_retriever.load_profile(limit=3),
                *self.memory_retriever.search(query, limit=5),
            ]
        )


@router.get("/health")
def health() -> dict[str, str]:
    """Return process health."""
    return {"status": "ok"}


@router.get("/provider-status")
def get_provider_status() -> ProviderStatusResponse:
    """Return non-sensitive LLM provider and embedding cache status."""
    return runtime.provider_status()


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
    runtime.record_interaction(payload.message, response, evidence)
    return chat_response(response, evidence)


@router.post("/v3/chat/stream")
def v3_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Stream v3 Agent progress as Server-Sent Events."""
    history = [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]
    retrieval_query = _conversation_query(payload.message, history)
    return StreamingResponse(
        _chat_event_stream(payload.message, history, retrieval_query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/v3/memory")
def v3_memory(layer: str | None = Query(default=None)) -> MemoryRecordListResponse:
    """List stored memories for inspection."""
    return memory_record_list(runtime.memory_store.list_memories(layer=layer))


@router.get("/v3/memory/search")
def v3_memory_search(
    q: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
) -> MemorySearchResponse:
    """Search stored L1/L2 memories."""
    return memory_search_response(runtime.memory_retriever.search(q, limit=limit))


@router.delete("/v3/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def v3_memory_delete(memory_id: str) -> Response:
    """Soft-delete one memory."""
    try:
        runtime.memory_store.delete_memory(memory_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


def _endpoint_status(
    is_real: bool,
    model: str,
    base_url: str,
    real_detail: str,
    fallback_detail: str,
) -> ProviderEndpointStatus:
    """Build one provider status without exposing credentials."""
    return ProviderEndpointStatus(
        mode="real" if is_real else "fallback",
        model=model or None,
        base_url=base_url or None,
        detail=real_detail if is_real else fallback_detail,
    )


def _cache_status(cache_stats: dict[str, int | str] | None) -> EmbeddingCacheStatus:
    """Build embedding cache status."""
    if cache_stats is None:
        return EmbeddingCacheStatus(enabled=False)
    return EmbeddingCacheStatus(
        enabled=True,
        path=str(cache_stats.get("path") or ""),
        entries=int(cache_stats.get("entries") or 0),
        hits=int(cache_stats.get("hits") or 0),
        misses=int(cache_stats.get("misses") or 0),
        writes=int(cache_stats.get("writes") or 0),
    )


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


def _chat_event_stream(
    message: str,
    history: list[ConversationTurn],
    retrieval_query: str,
) -> Iterator[str]:
    """Serialize Agent stream events into SSE frames."""
    try:
        for event in runtime.chat_events(message, history=history):
            if event.type == "done":
                warning = _record_streamed_interaction(message, retrieval_query, event)
                if warning:
                    yield _sse("warning", {"message": warning})
            yield _sse(event.type, _stream_payload(event, retrieval_query))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        yield _sse("error", {"message": str(exc)})


def _record_streamed_interaction(
    message: str,
    retrieval_query: str,
    event: AgentStreamEvent,
) -> str | None:
    """Persist a completed streaming chat turn once the final response exists."""
    response = event.payload.get("response")
    if not isinstance(response, AgentResponse):
        return None
    try:
        evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
        runtime.record_interaction(message, response, evidence)
    except Exception:  # pylint: disable=broad-exception-caught
        return "memory write failed; answer still returned"
    return None


def _stream_payload(event: AgentStreamEvent, retrieval_query: str) -> dict[str, object]:
    """Convert an AgentStreamEvent payload into JSON-safe data."""
    if event.type == "retrieval":
        candidates = event.payload.get("candidates", [])
        return {
            "query": str(event.payload.get("query") or ""),
            "candidates": _candidate_items(candidates),
        }
    if event.type == "evidence":
        evidence = event.payload.get("evidence", [])
        return {"items": _evidence_items(evidence)}
    if event.type == "memory":
        memory_hits = event.payload.get("memory_hits", [])
        return {"items": _memory_hit_items(memory_hits)}
    if event.type == "done":
        response = event.payload.get("response")
        if not isinstance(response, AgentResponse):
            return {"answer": ""}
        evidence = _evidence_for_tool_calls(retrieval_query, response.tool_calls)
        return chat_response(response, evidence).model_dump()
    return event.payload


def _candidate_items(candidates: object) -> list[dict[str, object]]:
    """Return JSON-safe retrieval candidate summaries."""
    if not isinstance(candidates, list):
        return []
    items = []
    for candidate in candidates:
        if not isinstance(candidate, SearchResult):
            continue
        items.append(
            {
                "id": candidate.doc_id,
                "file": f"{candidate.doc_id}.html",
                "title": candidate.title,
                "snippet": candidate.snippet,
                "score": candidate.score,
            }
        )
    return items


def _evidence_items(evidence: object) -> list[dict[str, str]]:
    """Return JSON-safe evidence summaries."""
    if not isinstance(evidence, list):
        return []
    items = []
    for item in evidence:
        if not isinstance(item, EvidenceItem):
            continue
        items.append(
            {
                "file": item.file,
                "section": item.section_heading,
                "text": item.text,
            }
        )
    return items


def _memory_hit_items(memory_hits: object) -> list[dict[str, object]]:
    """Return JSON-safe recalled memory summaries."""
    if not isinstance(memory_hits, list):
        return []
    items = []
    for hit in memory_hits:
        if not isinstance(hit, MemorySearchHit):
            continue
        items.append(
            {
                "id": hit.record.id,
                "layer": hit.record.layer,
                "kind": hit.record.kind,
                "summary": hit.record.summary or hit.record.content,
                "score": hit.score,
                "reason": hit.reason,
            }
        )
    return items


def _sse(event: str, data: dict[str, object]) -> str:
    """Return one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


def _dedupe_memory_hits(hits: list[MemorySearchHit]) -> list[MemorySearchHit]:
    """Keep first hit per memory id while preserving score order by source list."""
    seen: set[str] = set()
    deduped = []
    for hit in hits:
        if hit.record.id in seen:
            continue
        seen.add(hit.record.id)
        deduped.append(hit)
    return deduped


runtime = SearchRuntime(DATA_DIR, test_mode=True)


def reset_runtime(test_mode: bool = False) -> None:
    """Reset API runtime state."""
    runtime.reset(test_mode=test_mode)
