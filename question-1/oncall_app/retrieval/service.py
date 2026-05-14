"""High-level retrieval service."""

from oncall_app.models import Document, SearchResult
from oncall_app.retrieval.bm25 import BM25Index
from oncall_app.retrieval.tokenize import tokenize

SNIPPET_RADIUS = 56


class RetrievalService:
    """Search over parsed SOP documents."""

    def __init__(self, documents: list[Document]):
        self.documents = documents
        self._tokens = [tokenize(f"{document.title} {document.text}") for document in documents]
        self._bm25 = BM25Index(self._tokens)

    @classmethod
    def from_documents(cls, documents: list[Document]) -> "RetrievalService":
        """Build a retrieval service from parsed documents."""
        return cls(documents)

    def keyword_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Return BM25 keyword search results."""
        query_tokens = tokenize(query.strip())
        if not query_tokens:
            return []
        results = []
        for doc_index, score in self._bm25.rank(query_tokens, limit=limit):
            document = self.documents[doc_index]
            results.append(
                SearchResult(
                    doc_id=document.doc_id,
                    title=document.title,
                    snippet=_make_snippet(document, query, query_tokens),
                    score=round(score, 4),
                )
            )
        return results


def _make_snippet(document: Document, query: str, query_tokens: list[str]) -> str:
    """Build a snippet around the query or first matching token."""
    sources = (document.text, document.title)
    candidates = [query, *query_tokens]
    for candidate in candidates:
        if not candidate:
            continue
        folded_candidate = candidate.casefold()
        for source in sources:
            index = source.casefold().find(folded_candidate)
            if index >= 0:
                start = max(0, index - SNIPPET_RADIUS)
                end = min(len(source), index + len(candidate) + SNIPPET_RADIUS)
                prefix = "..." if start else ""
                suffix = "..." if end < len(source) else ""
                return f"{prefix}{source[start:end]}{suffix}"
    return document.text[: SNIPPET_RADIUS * 2]
