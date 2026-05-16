"""Deterministic extraction from raw events into atomic memories."""

import re

from oncall_app.memory.models import MemoryRecord, RawMemoryEvent

EXPLICIT_PREFIXES = ("记住：", "记住:", "请记住：", "请记住:")
DURABLE_MARKERS = ("记住：", "记住:", "请记住", "以后", "我们团队", "负责人是", "升级群是", "偏好")


class DeterministicMemoryExtractor:
    """Extract high-confidence L1 memories without an LLM dependency."""

    def extract(self, event: RawMemoryEvent) -> list[MemoryRecord]:
        """Return durable memories from a completed turn."""
        text = event.user_message.strip()
        if not text or not _looks_durable(text):
            return []

        content = _strip_prefix(text)
        if not content:
            return []

        return [
            MemoryRecord(
                layer="L1",
                kind=_kind_for(text),
                content=content,
                summary=_summary_for(content),
                tags=_tags_for(content),
                source_event_ids=[event.id],
                confidence=_confidence_for(text),
                importance=_importance_for(text),
            )
        ]


def _looks_durable(text: str) -> bool:
    return any(marker in text for marker in DURABLE_MARKERS)


def _strip_prefix(text: str) -> str:
    content = text.strip()
    for prefix in EXPLICIT_PREFIXES:
        if content.startswith(prefix):
            content = content[len(prefix) :].strip()
            break
    return content


def _kind_for(text: str) -> str:
    if text.startswith(EXPLICIT_PREFIXES) or "请记住" in text:
        return "explicit_fact"
    if "偏好" in text:
        return "preference"
    if "负责人" in text or "升级群" in text:
        return "service_context"
    return "fact"


def _confidence_for(text: str) -> float:
    if text.startswith(EXPLICIT_PREFIXES) or "请记住" in text:
        return 0.9
    return 0.7


def _importance_for(text: str) -> float:
    if "负责人" in text or "升级群" in text:
        return 0.8
    return 0.6


def _summary_for(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:80]


def _tags_for(content: str) -> list[str]:
    tags: list[str] = []
    for match in re.finditer(r"([\w\u4e00-\u9fff]{2,20}服务)", content):
        tags.append(match.group(1))
    if "负责人" in content:
        tags.append("负责人")
    if "升级群" in content:
        tags.append("升级群")
    if "偏好" in content:
        tags.append("偏好")
    return list(dict.fromkeys(tags))
