"""Hybrid retrieval tests."""

# pylint: disable=too-few-public-methods

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository
from oncall_app.retrieval.hybrid import rrf_fuse
from oncall_app.retrieval.service import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class FakeEmbeddingClient:
    """Embedding client that separates service-infra text from other text."""

    def embed(self, text: str) -> list[float]:
        """Return a tiny deterministic topic vector."""
        if "服务" in text or "K8s" in text or "服务器" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


class HybridRetrievalTest(unittest.TestCase):
    """Hybrid retrieval keeps lexical precision and semantic recall."""

    def test_rrf_promotes_documents_seen_by_multiple_rankers(self):
        """RRF should promote a document that both rankers retrieve."""
        fused = rrf_fuse(
            [
                ["sop-003", "sop-010"],
                ["sop-010", "sop-004"],
            ]
        )

        self.assertEqual(fused[0].doc_id, "sop-010")

    def test_server_down_returns_backend_and_sre_top_two(self):
        """Server-down queries should keep backend and SRE in the top two."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("服务器挂了")
        top_two = {result.doc_id for result in results[:2]}

        self.assertEqual(top_two, {"sop-001", "sop-004"})

    def test_cdn_keeps_exact_lexical_matches(self):
        """Exact CDN hits should survive even when vector recall is broad."""
        repository = DocumentRepository(DATA_DIR)
        service = RetrievalService.from_documents(
            repository.all_documents(),
            embedding_client=FakeEmbeddingClient(),
        )

        results = service.semantic_search("CDN")
        ids = [result.doc_id for result in results]

        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)


if __name__ == "__main__":
    unittest.main()
