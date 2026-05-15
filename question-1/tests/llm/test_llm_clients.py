"""OpenAI-compatible client tests."""

# pylint: disable=too-few-public-methods

import unittest
from typing import Any

from oncall_app.llm.config import ProviderConfig
from oncall_app.llm.openai_compat import OpenAICompatClient


class FakeTransport:
    """Fake transport recording request payloads."""

    def __init__(self):
        self.last_path = ""
        self.last_payload: dict[str, Any] = {}
        self.last_headers: dict[str, str] = {}

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Record request data and return an OpenAI-compatible response."""
        self.last_path = path
        self.last_payload = payload
        self.last_headers = headers
        if path == "/embeddings":
            return {"data": [{"embedding": [1.0, 0.0, 0.0]}]}
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


class OpenAICompatClientTest(unittest.TestCase):
    """Client builds correct OpenAI-compatible requests."""

    def test_embedding_request_uses_embeddings_endpoint(self):
        """Embedding calls use the configured model and embeddings endpoint."""
        transport = FakeTransport()
        client = OpenAICompatClient(
            ProviderConfig(base_url="https://example.test/v1", api_key="key", model="embed"),
            transport=transport,
        )

        result = client.create_embedding("hello")

        self.assertEqual(transport.last_path, "/embeddings")
        self.assertEqual(transport.last_payload["model"], "embed")
        self.assertEqual(transport.last_payload["input"], "hello")
        self.assertEqual(transport.last_headers["Authorization"], "Bearer key")
        self.assertEqual(result, [1.0, 0.0, 0.0])

    def test_chat_request_uses_chat_completions_endpoint(self):
        """Chat calls use OpenAI Chat Completions request shape."""
        transport = FakeTransport()
        client = OpenAICompatClient(
            ProviderConfig(base_url="https://example.test/v1", api_key="key", model="chat"),
            transport=transport,
        )

        result = client.create_chat_completion(
            [{"role": "user", "content": "hi"}],
            tools=[],
        )

        self.assertEqual(transport.last_path, "/chat/completions")
        self.assertEqual(transport.last_payload["model"], "chat")
        self.assertEqual(transport.last_payload["messages"][0]["content"], "hi")
        self.assertEqual(transport.last_payload["tools"], [])
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")


if __name__ == "__main__":
    unittest.main()
