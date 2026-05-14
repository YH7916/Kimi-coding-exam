"""HTML parsing utilities for SOP documents."""

import re
from html import unescape
from html.parser import HTMLParser

from oncall_app.models import Document

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
    "td",
    "th",
    "tr",
    "ul",
}


class _VisibleTextParser(HTMLParser):
    """Extract title and visible text from HTML while skipping scripts/styles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):  # pylint: disable=unused-argument
        """Track title and hidden blocks."""
        lowered = tag.lower()
        if lowered in {"script", "style"}:
            self._skip_depth += 1
            return
        if lowered == "title":
            self._in_title = True
            return
        if lowered in BLOCK_TAGS and not self._skip_depth and not self._in_title:
            self.text_parts.append(" ")

    def handle_endtag(self, tag):
        """Track title and hidden block endings."""
        lowered = tag.lower()
        if lowered in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if lowered == "title":
            self._in_title = False
            return
        if lowered in BLOCK_TAGS and not self._skip_depth and not self._in_title:
            self.text_parts.append(" ")

    def handle_data(self, data):
        """Collect visible data."""
        if self._skip_depth:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)


def _normalize_text(value: str) -> str:
    """Decode HTML entities and collapse whitespace."""
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_html_document(doc_id: str, html: str) -> Document:
    """Parse a raw SOP HTML document into a searchable document."""
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    title = _normalize_text(" ".join(parser.title_parts)) or doc_id
    text = _normalize_text(" ".join(parser.text_parts))
    return Document(doc_id=doc_id, title=title, text=text, html=html)
