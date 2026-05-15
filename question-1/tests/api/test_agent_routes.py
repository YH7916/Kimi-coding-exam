"""Agent API route tests."""

import unittest

from fastapi.testclient import TestClient

from oncall_app.api.app_factory import create_app


class AgentRouteTest(unittest.TestCase):
    """v3 chat API returns answer, tool calls, evidence, and trace."""

    def test_v3_chat_oom(self):
        """OOM chat returns an answer with visible tool trace."""
        client = TestClient(create_app(test_mode=True))

        response = client.post("/v3/chat", json={"message": "服务 OOM 了怎么办？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", payload)
        self.assertGreaterEqual(len(payload["tool_calls"]), 1)
        self.assertEqual(payload["tool_calls"][0]["tool"], "readFile")
        self.assertIn("sop-001.html", [call["fname"] for call in payload["tool_calls"]])
        self.assertIn("trace", payload)
        self.assertTrue(any(item["type"] == "retrieval" for item in payload["trace"]))
        self.assertIn("sop-001.html", payload["trace"][0]["message"])
        self.assertTrue(any(item["type"] == "tool_call" for item in payload["trace"]))
        self.assertTrue(any("OOM" in item["section"] for item in payload["evidence"]))

    def test_v3_evidence_is_frontend_sized(self):
        """Evidence cards return compact citations instead of whole SOP sections."""
        client = TestClient(create_app(test_mode=True))

        response = client.post("/v3/chat", json={"message": "P0 故障的响应流程是什么？"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["evidence"])
        self.assertTrue(all(len(item["section"]) <= 80 for item in payload["evidence"]))
        self.assertTrue(all(len(item["text"]) <= 240 for item in payload["evidence"]))


if __name__ == "__main__":
    unittest.main()
