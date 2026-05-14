"""Shared data models for the On-Call assistant."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """A parsed SOP document."""

    doc_id: str
    title: str
    text: str
    html: str


@dataclass(frozen=True)
class SearchResult:
    """A ranked search result returned by the search services."""

    doc_id: str
    title: str
    snippet: str
    score: float


@dataclass(frozen=True)
class ToolCall:
    """A visible agent tool invocation."""

    tool: str
    fname: str
    result_preview: str


@dataclass(frozen=True)
class AgentResponse:
    """The final agent response and the tool calls used to produce it."""

    answer: str
    tool_calls: list[ToolCall]
