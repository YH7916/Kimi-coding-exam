"""Search services for SOP documents."""

from oncall_app.models import Document, SearchResult
from oncall_app.retrieval.service import RetrievalService

DEFAULT_LIMIT = 10


def keyword_search(
    documents: list[Document],
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    """Search documents by BM25 lexical retrieval."""
    return RetrievalService.from_documents(documents).keyword_search(query, limit=limit)


def semantic_search(
    documents: list[Document],
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    """Search documents by the shared v2 semantic retrieval service."""
    return RetrievalService.from_documents(documents).semantic_search(query, limit=limit)
