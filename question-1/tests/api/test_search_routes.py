"""Search route tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class SearchRouteTest(unittest.TestCase):
    """README search API behavior."""

    def setUp(self):
        """Create a test client."""
        self.client = TestClient(create_app())

    def test_v1_oom(self):
        """V1 BM25 search should return the backend SOP for OOM."""
        response = self.client.get("/v1/search", params={"q": "OOM"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], "sop-001")

    def test_v1_replication_is_empty(self):
        """Script-only terms should not be searchable."""
        response = self.client.get("/v1/search", params={"q": "replication"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_v1_blank_query_is_literal_ampersand(self):
        """README q=& behavior searches for a literal ampersand."""
        response = self.client.get("/v1/search?q=&")
        ids = [result["id"] for result in response.json()["results"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["query"], "&")
        self.assertIn("sop-003", ids)
        self.assertIn("sop-010", ids)

    def test_v2_security_query(self):
        """V2 semantic search should retrieve the security SOP."""
        response = self.client.get("/v2/search", params={"q": "黑客攻击"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], "sop-005")

    def test_post_document_updates_v1_index(self):
        """Posting a document should update the in-memory search index."""
        response = self.client.post(
            "/v1/documents",
            json={"id": "sop-test", "html": "<html><title>测试</title><body>OOM 测试</body></html>"},
        )
        search = self.client.get("/v1/search", params={"q": "OOM"}).json()

        self.assertEqual(response.status_code, 201)
        self.assertIn("sop-test", [item["id"] for item in search["results"]])


if __name__ == "__main__":
    unittest.main()
