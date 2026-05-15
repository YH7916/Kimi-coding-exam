"""SOP manifest generation for Agent file selection."""

import re
from collections import Counter

from oncall_app.models import Document, ManifestEntry, SopManifest

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}")
STOP_TOPICS = {
    "On",
    "Call",
    "SOP",
    "场景",
    "处理",
    "工具",
    "命令",
    "参考",
    "禁止",
    "操作",
    "流程",
}


def _topic_candidates(document: Document) -> list[str]:
    """Return topic candidates from title and section headings."""
    source = " ".join([document.title, *(section.heading for section in document.sections)])
    tokens = TOKEN_PATTERN.findall(source)
    counter = Counter(token for token in tokens if token not in STOP_TOPICS)
    return [token for token, _count in counter.most_common(12)]


def build_manifest(documents: list[Document]) -> SopManifest:
    """Build a file-level SOP manifest."""
    entries = [
        ManifestEntry(
            file=document.file_name or f"{document.doc_id}.html",
            doc_id=document.doc_id,
            title=document.title,
            topics=_topic_candidates(document),
        )
        for document in sorted(documents, key=lambda item: item.doc_id)
    ]
    return SopManifest(entries=entries)
