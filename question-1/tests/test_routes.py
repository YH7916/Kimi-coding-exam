"""Tests for HTTP route orchestration."""

import json
from pathlib import Path
import unittest

from oncall_app.repository import DocumentRepository
from oncall_app.routes import Router


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


class RouteTest(unittest.TestCase):
    """Route layer behavior."""

    def setUp(self):
        """Create a fresh router for each test."""
        self.router = Router(DocumentRepository(DATA_DIR))

    def test_v1_page_renders_search_form(self):
        """GET /v1 returns a simple HTML search page."""
        response = self.router.handle("GET", "/v1", b"")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertIn("<form", response.body)
        self.assertIn("/v1/search", response.body)

    def test_v1_search_returns_json_results(self):
        """GET /v1/search returns the keyword search JSON shape."""
        response = self.router.handle("GET", "/v1/search?q=OOM", b"")

        payload = json.loads(response.body)

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["query"], "OOM")
        self.assertEqual(payload["results"][0]["id"], "sop-001")
        self.assertIn("score", payload["results"][0])

    def test_v1_search_treats_blank_query_as_ampersand(self):
        """The README's q=& validation searches for literal ampersands."""
        response = self.router.handle("GET", "/v1/search?q=&", b"")

        payload = json.loads(response.body)
        result_ids = [result["id"] for result in payload["results"]]

        self.assertEqual(payload["query"], "&")
        self.assertIn("sop-003", result_ids)
        self.assertIn("sop-010", result_ids)

    def test_v1_documents_adds_document(self):
        """POST /v1/documents parses and stores an HTML document."""
        body = json.dumps(
            {
                "id": "sop-test",
                "html": "<html><head><title>测试 SOP</title></head><body>OOM 测试</body></html>",
            }
        ).encode("utf-8")

        response = self.router.handle("POST", "/v1/documents", body)
        search_response = self.router.handle("GET", "/v1/search?q=OOM", b"")
        post_payload = json.loads(response.body)
        search_payload = json.loads(search_response.body)

        self.assertEqual(response.status, 201)
        self.assertEqual(post_payload, {"id": "sop-test", "title": "测试 SOP"})
        self.assertIn("sop-test", [result["id"] for result in search_payload["results"]])

    def test_v2_search_uses_semantic_results(self):
        """GET /v2/search returns semantic search results."""
        response = self.router.handle("GET", "/v2/search?q=黑客攻击", b"")

        payload = json.loads(response.body)

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["query"], "黑客攻击")
        self.assertEqual(payload["results"][0]["id"], "sop-005")

    def test_unknown_route_returns_404(self):
        """Unknown paths return a JSON 404."""
        response = self.router.handle("GET", "/missing", b"")

        payload = json.loads(response.body)

        self.assertEqual(response.status, 404)
        self.assertEqual(payload["error"], "not found")


if __name__ == "__main__":
    unittest.main()
