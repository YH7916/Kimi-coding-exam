"""HTTP route declarations."""

import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from oncall_app.agent.evidence import EvidenceItem
from oncall_app.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentCreate,
    DocumentCreated,
    DocumentDetail,
    MemoryRecordListResponse,
    MemorySearchResponse,
    ProviderStatusResponse,
    SearchResponse,
    chat_response,
    document_detail,
    memory_record_list,
    memory_search_response,
    search_response,
)
from oncall_app.api.static_files import read_frontend_shell
from oncall_app.memory.models import MemorySearchHit
from oncall_app.models import (
    AgentResponse,
    AgentStreamEvent,
    ConversationTurn,
    SearchResult,
)
from oncall_app.runtime import runtime

router = APIRouter()


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
    return search_response(query, runtime.keyword_search(query))


@router.post("/v1/documents", status_code=status.HTTP_201_CREATED)
def v1_documents(payload: DocumentCreate) -> DocumentCreated:
    """Add an SOP document to the in-memory repository and index."""
    document = runtime.add_document(payload.id, payload.html)
    return DocumentCreated(id=document.doc_id, title=document.title)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str) -> DocumentDetail:
    """Return one parsed SOP document for frontend source preview."""
    normalized_id = doc_id.removesuffix(".html")
    try:
        return document_detail(runtime.get_document(normalized_id))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc


@router.get("/v2/search")
def v2_search(q: str = Query(default="")) -> SearchResponse:
    """Search SOPs with semantic retrieval."""
    query = _normalize_query(q)
    return search_response(query, runtime.semantic_search(query))


@router.post("/v3/chat")
def v3_chat(payload: ChatRequest) -> ChatResponse:
    """Answer an On-Call question with a traceable tool-using Agent."""
    history = _conversation_turns(payload)
    retrieval_query = runtime.retrieval_query(payload.message, history)
    response = runtime.chat(payload.message, history=history)
    evidence = runtime.evidence_for_tool_calls(retrieval_query, response.tool_calls)
    runtime.record_interaction(payload.message, response, evidence)
    return chat_response(response, evidence)


@router.post("/v3/chat/stream")
def v3_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Stream v3 Agent progress as Server-Sent Events."""
    history = _conversation_turns(payload)
    retrieval_query = runtime.retrieval_query(payload.message, history)
    return StreamingResponse(
        _chat_event_stream(payload.message, history, retrieval_query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/v3/memory")
def v3_memory(layer: str | None = Query(default=None)) -> MemoryRecordListResponse:
    """List stored memories for inspection."""
    return memory_record_list(runtime.list_memories(layer=layer))


@router.get("/v3/memory/search")
def v3_memory_search(
    q: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=20),
) -> MemorySearchResponse:
    """Search stored L1/L2 memories."""
    return memory_search_response(runtime.search_memories(q, limit=limit))


@router.delete("/v3/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def v3_memory_delete(memory_id: str) -> Response:
    """Soft-delete one memory."""
    try:
        runtime.delete_memory(memory_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _conversation_turns(payload: ChatRequest) -> list[ConversationTurn]:
    """Convert validated API history into domain turns."""
    return [
        ConversationTurn(role=item.role, content=item.content)
        for item in payload.history
    ]


def _normalize_query(q: str) -> str:
    """Normalize README query behavior."""
    return "&" if q == "" else q


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
        evidence = runtime.evidence_for_tool_calls(retrieval_query, response.tool_calls)
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
        evidence = runtime.evidence_for_tool_calls(retrieval_query, response.tool_calls)
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

