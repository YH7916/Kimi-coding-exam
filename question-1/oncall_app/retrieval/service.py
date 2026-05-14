"""High-level retrieval service."""

# pylint: disable=too-many-instance-attributes

from dataclasses import dataclass

from oncall_app.llm.embedding_client import EmbeddingClient
from oncall_app.models import Document, SearchResult
from oncall_app.retrieval.bm25 import BM25Index
from oncall_app.retrieval.chunking import DocumentChunk, build_chunks
from oncall_app.retrieval.embeddings import EmbeddingCache
from oncall_app.retrieval.tokenize import tokenize
from oncall_app.retrieval.vector_store import VectorHit, VectorStore

SNIPPET_RADIUS = 56
VECTOR_HIT_MULTIPLIER = 8
DOCUMENT_COUNT_BOOST = 0.01


@dataclass
class _DocumentVectorScore:
    """Aggregated vector score for one document."""

    document: Document
    best_chunk: DocumentChunk
    max_score: float
    lexical_bonus: float
    hit_count: int = 0

    @property
    def score(self) -> float:
        """Return a stable document score."""
        return (
            self.max_score
            + min(self.hit_count, 10) * DOCUMENT_COUNT_BOOST
            + self.lexical_bonus
        )


class RetrievalService:
    """Search over parsed SOP documents."""

    def __init__(
        self,
        documents: list[Document],
        embedding_client: EmbeddingClient | None = None,
        embedding_cache: EmbeddingCache | None = None,
    ):
        self.documents = documents
        self._documents_by_id = {document.doc_id: document for document in documents}
        self._tokens = [tokenize(f"{document.title} {document.text}") for document in documents]
        self._bm25 = BM25Index(self._tokens)
        self._embedding_client = embedding_client
        self._embedding_cache = embedding_cache
        self._chunks = build_chunks(documents)
        self._vector_store = (
            VectorStore.from_chunks(self._chunks, embedding_client, embedding_cache)
            if embedding_client is not None
            else None
        )

    @classmethod
    def from_documents(
        cls,
        documents: list[Document],
        embedding_client: EmbeddingClient | None = None,
        embedding_cache: EmbeddingCache | None = None,
    ) -> "RetrievalService":
        """Build a retrieval service from parsed documents."""
        return cls(
            documents,
            embedding_client=embedding_client,
            embedding_cache=embedding_cache,
        )

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

    def semantic_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Return embedding-based semantic search results."""
        normalized_query = query.strip()
        if not normalized_query:
            return []
        if self._embedding_client is None or self._vector_store is None:
            return self.keyword_search(normalized_query, limit=limit)

        query_vector = _embed_query(
            normalized_query,
            self._embedding_client,
            self._embedding_cache,
        )
        hit_limit = max(limit * VECTOR_HIT_MULTIPLIER, limit)
        hits = self._vector_store.rank(query_vector, limit=hit_limit)
        return self._results_from_vector_hits(hits, normalized_query, limit)

    def _results_from_vector_hits(
        self,
        hits: list[VectorHit],
        query: str,
        limit: int,
    ) -> list[SearchResult]:
        """Aggregate chunk hits into document-level search results."""
        query_terms = _query_terms(query)
        scores: dict[str, _DocumentVectorScore] = {}
        for hit in hits:
            document = self._documents_by_id[hit.chunk.doc_id]
            current = scores.get(hit.chunk.doc_id)
            if current is None:
                scores[hit.chunk.doc_id] = _DocumentVectorScore(
                    document=document,
                    best_chunk=hit.chunk,
                    max_score=hit.score,
                    lexical_bonus=_lexical_bonus(document, query_terms),
                    hit_count=1,
                )
                continue
            current.hit_count += 1
            if hit.score > current.max_score:
                current.max_score = hit.score
                current.best_chunk = hit.chunk

        ranked = sorted(scores.values(), key=lambda item: (-item.score, item.document.doc_id))
        return [
            SearchResult(
                doc_id=item.document.doc_id,
                title=item.document.title,
                snippet=_chunk_snippet(item.best_chunk),
                score=round(item.score, 4),
            )
            for item in ranked[:limit]
        ]


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


def _chunk_snippet(chunk: DocumentChunk) -> str:
    """Build a snippet from the best vector chunk."""
    snippet = chunk.text.replace("\n", " ")
    return snippet[: SNIPPET_RADIUS * 2]


def _query_terms(query: str) -> set[str]:
    """Return meaningful lexical terms for vector tie-breaking."""
    return {
        term.casefold()
        for term in [query, *tokenize(query)]
        if len(term.strip()) >= 2 or term == "&"
    }


def _lexical_bonus(document: Document, query_terms: set[str]) -> float:
    """Return a small overlap bonus used only to break vector near-ties."""
    folded_text = f"{document.title} {document.text}".casefold()
    occurrences = sum(
        min(folded_text.count(term), 3)
        for term in query_terms
        if term and term in folded_text
    )
    return min(occurrences, 20) * 0.001


def _embed_query(
    query: str,
    embedding_client: EmbeddingClient,
    cache: EmbeddingCache | None,
) -> list[float]:
    """Embed a query with optional cache lookup."""
    if cache is None:
        return embedding_client.embed(query)
    return cache.get_or_create(query, embedding_client.embed)
