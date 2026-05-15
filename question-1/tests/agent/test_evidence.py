"""Evidence extraction tests."""

import unittest
from pathlib import Path

from oncall_app.agent.evidence import EvidenceExtractor
from oncall_app.documents.repository import DocumentRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class EvidenceExtractorTest(unittest.TestCase):
    """Relevant SOP sections are extracted for answers."""

    def test_oom_extracts_oom_section_and_escalation(self):
        """OOM evidence should include the OOM scenario and escalation section."""
        repository = DocumentRepository(DATA_DIR)
        document = repository.get("sop-001")

        evidence = EvidenceExtractor().extract("服务 OOM 了怎么办？", [document])
        headings = [item.section_heading for item in evidence]

        self.assertIn("场景二：单服务OOM崩溃", headings)
        self.assertTrue(any("升级流程" in heading for heading in headings))

    def test_p0_extracts_multiple_documents(self):
        """P0 workflow evidence should span multiple SOP documents."""
        repository = DocumentRepository(DATA_DIR)
        documents = [
            repository.get("sop-001"),
            repository.get("sop-002"),
            repository.get("sop-005"),
        ]

        evidence = EvidenceExtractor().extract("P0 故障的响应流程是什么？", documents)
        files = {item.file for item in evidence}

        self.assertGreaterEqual(len(files), 2)


if __name__ == "__main__":
    unittest.main()
