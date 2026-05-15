"""Shared data models for the On-Call assistant."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Section:
    """A structured SOP section."""

    heading: str
    level: int
    text: str


@dataclass(frozen=True)
class Document:
    """A parsed SOP document."""

    doc_id: str
    title: str
    text: str
    html: str
    file_name: str = ""
    sections: list[Section] = field(default_factory=list)


@dataclass(frozen=True)
class ManifestEntry:
    """A file-level summary for Agent file selection."""

    file: str
    doc_id: str
    title: str
    topics: list[str]


@dataclass(frozen=True)
class SopManifest:
    """Index manifest stored in data/sop-index.json."""

    entries: list[ManifestEntry]


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
