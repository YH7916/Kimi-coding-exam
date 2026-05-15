"""Structured document ingestion tests."""

import unittest
from pathlib import Path

from oncall_app.documents.repository import DocumentRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class StructuredDocumentTest(unittest.TestCase):
    """SOP documents are parsed into clean sections."""

    def test_script_and_style_are_not_visible_text(self):
        """Script and style content is excluded from searchable text."""
        repository = DocumentRepository(DATA_DIR)
        document = repository.get("sop-002")

        self.assertIn("主从复制状态", document.text)
        self.assertNotIn("replicationLag", document.text)
        self.assertNotIn("font-family", document.text)

    def test_sections_preserve_headings(self):
        """Heading structure is preserved for retrieval and citation."""
        repository = DocumentRepository(DATA_DIR)
        document = repository.get("sop-001")
        headings = [section.heading for section in document.sections]

        self.assertIn("三、常见故障处理", headings)
        self.assertIn("场景二：单服务OOM崩溃", headings)

if __name__ == "__main__":
    unittest.main()
