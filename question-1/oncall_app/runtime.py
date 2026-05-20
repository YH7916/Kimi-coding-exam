"""Application runtime orchestration for retrieval, memory, and agent workflows."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

from oncall_app.agent.assistant import OnCallAssistant
from oncall_app.agent.evidence import EvidenceExtractor, EvidenceItem
from oncall_app.agent.local_chat import LocalChatClient
from oncall_app.api.schemas import (
    EmbeddingCacheStatus,
    ProviderEndpointStatus,
    ProviderStatusResponse,
)
from oncall_app.documents.repository import DocumentRepository
from oncall_app.llm.chat_client import ChatClient, create_chat_client
from oncall_app.llm.config import chat_config_from_env, embedding_config_from_env
from oncall_app.llm.embedding_client import EmbeddingClient, create_embedding_client
from oncall_app.memory.context import format_memory_context
from oncall_app.memory.extractor import DeterministicMemoryExtractor
from oncall_app.memory.models import MemoryRecord, MemorySearchHit, RawMemoryEvent
from oncall_app.memory.retrieval import MemoryRetriever
from oncall_app.memory.store import MemoryStore
from oncall_app.models import (
    AgentResponse,
    AgentStreamEvent,
    ConversationTurn,
    Document,
    SearchResult,
    ToolCall,
)
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDING_CACHE_PATH = PROJECT_ROOT / ".cache" / "embeddings.sqlite3"
MEMORY_STORE_PATH = PROJECT_ROOT / ".cache" / "memory.sqlite3"
AGENT_CANDIDATE_LIMIT = 5
RETRIEVAL_HISTORY_TURNS = 4
MAX_RETRIEVAL_QUERY_CHARS = 800


class SearchRuntime:
    """Owns mutable document, retrieval, memory, and agent state."""

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
        self._build_memory_components()
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def reset(self, test_mode: bool = False) -> None:
        """Reset repository, retrieval, memory, and assistant state."""
        self.test_mode = test_mode
        self.repository = DocumentRepository(self.data_dir)
        self._build_memory_components()
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Rebuild retrieval indexes from repository documents."""
        self.service = self._build_retrieval_service()
        self.assistant = self._build_assistant()

    def keyword_search(self, query: str) -> list[SearchResult]:
        """Search SOPs with lexical retrieval."""
        return self.service.keyword_search(query)

    def semantic_search(self, query: str) -> list[SearchResult]:
        """Search SOPs with the v2 semantic retrieval chain."""
        return self.service.semantic_search(query)

    def add_document(self, doc_id: str, html: str) -> Document:
        """Add a document and refresh retrieval indexes."""
        document = self.repository.add_document(
            doc_id,
            html,
            file_name=f"{doc_id}.html",
        )
        self.rebuild_index()
        return document

    def get_document(self, doc_id: str) -> Document:
        """Return one parsed SOP document by id."""
        return self.repository.get(doc_id)

    def chat(
        self,
        message: str,
        history: list[ConversationTurn] | None = None,
    ) -> AgentResponse:
        """Answer with v2 hybrid retrieval candidates feeding the v3 Agent."""
        turns = history or []
        retrieval_query = self.retrieval_query(message, turns)
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
        """Yield retrieval, memory, and Agent events for SSE streaming."""
        turns = history or []
        retrieval_query = self.retrieval_query(message, turns)
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

    def retrieval_query(self, message: str, history: list[ConversationTurn]) -> str:
        """Build the retrieval query used by chat and evidence extraction."""
        return _conversation_query(message, history)

    def evidence_for_tool_calls(
        self,
        message: str,
        tool_calls: list[ToolCall],
    ) -> list[EvidenceItem]:
        """Extract evidence for HTML files read by the agent."""
        documents = []
        for call in tool_calls:
            if not call.fname.endswith(".html"):
                continue
            try:
                documents.append(self.repository.get(Path(call.fname).stem))
            except KeyError:
                continue
        return EvidenceExtractor().extract(message, documents)

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

    def list_memories(self, layer: str | None = None) -> list[MemoryRecord]:
        """List stored memories for inspection."""
        return self.memory_store.list_memories(layer=layer)

    def search_memories(self, query: str, limit: int) -> list[MemorySearchHit]:
        """Search stored L1/L2 memories."""
        return self.memory_retriever.search(query, limit=limit)

    def delete_memory(self, memory_id: str) -> None:
        """Soft-delete one memory."""
        self.memory_store.delete_memory(memory_id)

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

    def _build_memory_components(self) -> None:
        """Build memory store and recall helpers."""
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
