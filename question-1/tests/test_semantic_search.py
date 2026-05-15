"""Tests for semantic SOP search."""

import unittest
from pathlib import Path

from oncall_app.repository import DocumentRepository
from oncall_app.search import semantic_search

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class SemanticSearchTest(unittest.TestCase):
    """Phase 2 semantic search behavior."""

    def setUp(self):
        """Load demo SOPs."""
        self.documents = DocumentRepository(DATA_DIR).all_documents()

    def test_server_down_ranks_backend_and_sre_first(self):
        """服务器挂了 should rank backend and SRE near the top."""
        results = semantic_search(self.documents, "服务器挂了")

        top_ids = [result.doc_id for result in results[:2]]

        self.assertEqual(set(top_ids), {"sop-001", "sop-004"})

    def test_compact_oom_question_ranks_backend_first(self):
        """OOM怎么办 should rank the backend SOP first."""
        results = semantic_search(self.documents, "OOM怎么办")

        self.assertEqual(results[0].doc_id, "sop-001")

    def test_hacker_attack_ranks_security_first(self):
        """黑客攻击 should rank the security SOP first."""
        results = semantic_search(self.documents, "黑客攻击")

        self.assertEqual(results[0].doc_id, "sop-005")

    def test_machine_learning_model_issue_ranks_ai_first(self):
        """机器学习模型出问题 should rank the AI SOP first."""
        results = semantic_search(self.documents, "机器学习模型出问题")

        self.assertEqual(results[0].doc_id, "sop-008")


if __name__ == "__main__":
    unittest.main()
