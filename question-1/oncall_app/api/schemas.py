"""Pydantic schemas for HTTP APIs."""

from pydantic import BaseModel, Field

from oncall_app.agent.evidence import EvidenceItem
from oncall_app.models import AgentResponse, SearchResult, ToolCall


class SearchResultItem(BaseModel):
    """One search result returned by the README APIs."""

    id: str
    title: str
    snippet: str
    score: float


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


class ChatRequest(BaseModel):
    """Request body for v3 chat."""

    message: str = Field(min_length=1)


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
            )
            for result in results
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
                section=item.section_heading,
                text=item.text,
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
