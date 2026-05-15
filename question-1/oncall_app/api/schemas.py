"""Pydantic schemas for HTTP APIs."""

from typing import Literal

from pydantic import BaseModel, Field

from oncall_app.agent.evidence import EvidenceItem
from oncall_app.models import AgentResponse, Document, SearchResult, ToolCall

MAX_EVIDENCE_HEADING_CHARS = 80
MAX_EVIDENCE_TEXT_CHARS = 240


class SearchResultItem(BaseModel):
    """One search result returned by the README APIs."""

    id: str
    title: str
    snippet: str
    score: float
    section: str = ""


class SearchResponse(BaseModel):
    """Search response shape."""

    query: str
    results: list[SearchResultItem]


class DocumentCreate(BaseModel):
    """Request body for adding an SOP document."""

    id: str = Field(min_length=1)
    html: str = Field(min_length=1)


class DocumentCreated(BaseModel):
    """Response body for a stored SOP document."""

    id: str
    title: str


class DocumentSectionItem(BaseModel):
    """One structured section in a stored SOP document."""

    heading: str
    level: int
    text: str


class DocumentDetail(BaseModel):
    """Full SOP document returned for source preview."""

    id: str
    file: str
    title: str
    text: str
    sections: list[DocumentSectionItem]


class ProviderEndpointStatus(BaseModel):
    """Non-sensitive runtime status for one external provider."""

    mode: Literal["real", "fallback"]
    model: str | None = None
    base_url: str | None = None
    detail: str


class EmbeddingCacheStatus(BaseModel):
    """Embedding cache counters for the current process."""

    enabled: bool
    path: str | None = None
    entries: int = 0
    hits: int = 0
    misses: int = 0
    writes: int = 0


class ProviderStatusResponse(BaseModel):
    """Provider and cache status shown in the frontend."""

    embedding: ProviderEndpointStatus
    chat: ProviderEndpointStatus
    cache: EmbeddingCacheStatus


class ChatHistoryItem(BaseModel):
    """One previous visible chat turn supplied by the frontend."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Request body for v3 chat."""

    message: str = Field(min_length=1)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=12)


class ToolCallItem(BaseModel):
    """Visible tool call returned by v3 chat."""

    tool: str
    fname: str
    result_preview: str


class EvidenceResponseItem(BaseModel):
    """Evidence card returned by v3 chat."""

    file: str
    section: str
    text: str


class TraceResponseItem(BaseModel):
    """Trace event returned by v3 chat."""

    type: str
    message: str


class ChatResponse(BaseModel):
    """v3 chat response shape."""

    answer: str
    tool_calls: list[ToolCallItem]
    evidence: list[EvidenceResponseItem]
    trace: list[TraceResponseItem]


def search_response(query: str, results: list[SearchResult]) -> SearchResponse:
    """Convert domain search results into API schema."""
    return SearchResponse(
        query=query,
        results=[
            SearchResultItem(
                id=result.doc_id,
                title=result.title,
                snippet=result.snippet,
                score=result.score,
                section=_compact_text(result.section_heading, MAX_EVIDENCE_HEADING_CHARS),
            )
            for result in results
        ],
    )


def document_detail(document: Document) -> DocumentDetail:
    """Convert a parsed SOP document into a source preview response."""
    return DocumentDetail(
        id=document.doc_id,
        file=document.file_name or f"{document.doc_id}.html",
        title=document.title,
        text=document.text,
        sections=[
            DocumentSectionItem(
                heading=section.heading,
                level=section.level,
                text=section.text,
            )
            for section in document.sections
        ],
    )


def chat_response(response: AgentResponse, evidence: list[EvidenceItem]) -> ChatResponse:
    """Convert an agent response into API schema."""
    retrieval_trace = []
    if response.retrieval_candidates:
        files = ", ".join(f"{candidate.doc_id}.html" for candidate in response.retrieval_candidates)
        retrieval_trace.append(
            TraceResponseItem(
                type="retrieval",
                message=f"v2 hybrid retrieval candidates: {files}",
            )
        )
    return ChatResponse(
        answer=response.answer,
        tool_calls=[_tool_call_item(call) for call in response.tool_calls],
        evidence=[
            EvidenceResponseItem(
                file=item.file,
                section=_compact_text(item.section_heading, MAX_EVIDENCE_HEADING_CHARS),
                text=_compact_text(item.text, MAX_EVIDENCE_TEXT_CHARS),
            )
            for item in evidence
        ],
        trace=retrieval_trace
        + [
            TraceResponseItem(type="tool_call", message=f'readFile("{call.fname}")')
            for call in response.tool_calls
        ]
        + [TraceResponseItem(type="answer", message="final answer returned")],
    )


def _tool_call_item(call: ToolCall) -> ToolCallItem:
    """Convert a domain tool call into API schema."""
    return ToolCallItem(
        tool=call.tool,
        fname=call.fname,
        result_preview=call.result_preview,
    )


def _compact_text(value: str, limit: int) -> str:
    """Return a single-line preview bounded for the frontend."""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."
