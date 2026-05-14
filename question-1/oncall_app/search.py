"""Search services for SOP documents."""

from oncall_app.models import Document, SearchResult


DEFAULT_LIMIT = 10
SNIPPET_RADIUS = 48


def _casefold(value: str) -> str:
    """Return a case-insensitive comparison form."""
    return value.casefold()


def _count_occurrences(value: str, query: str) -> int:
    """Count non-overlapping case-insensitive query occurrences."""
    if not query:
        return 0
    return _casefold(value).count(_casefold(query))


def _make_snippet(document: Document, query: str) -> str:
    """Build a compact snippet around the first query match."""
    for source in (document.text, document.title):
        index = _casefold(source).find(_casefold(query))
        if index >= 0:
            start = max(0, index - SNIPPET_RADIUS)
            end = min(len(source), index + len(query) + SNIPPET_RADIUS)
            prefix = "..." if start else ""
            suffix = "..." if end < len(source) else ""
            return f"{prefix}{source[start:end]}{suffix}"
    return document.text[: SNIPPET_RADIUS * 2]


def keyword_search(
    documents: list[Document],
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    """Search documents by exact keyword matching with simple ranking."""
    normalized_query = query.strip()
    if not normalized_query:
        return []

    results: list[SearchResult] = []
    for document in documents:
        title_matches = _count_occurrences(document.title, normalized_query)
        text_matches = _count_occurrences(document.text, normalized_query)
        if not title_matches and not text_matches:
            continue
        score = float(title_matches * 5 + text_matches)
        results.append(
            SearchResult(
                doc_id=document.doc_id,
                title=document.title,
                snippet=_make_snippet(document, normalized_query),
                score=score,
            )
        )

    return sorted(results, key=lambda result: (-result.score, result.doc_id))[:limit]
