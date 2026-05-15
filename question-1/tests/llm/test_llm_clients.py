"""OpenAI-compatible client tests."""

# pylint: disable=too-few-public-methods

import unittest
from typing import Any
from unittest.mock import patch

from oncall_app.llm.config import DEFAULT_CHAT_TIMEOUT_SECONDS, ProviderConfig, chat_config_from_env
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

    def stream_json(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ):
        """Record request data and return OpenAI-compatible stream chunks."""
        self.last_path = path
        self.last_payload = payload
        self.last_headers = headers
        yield {"choices": [{"delta": {"content": "hel"}}]}
        yield {"choices": [{"delta": {"content": "lo"}}]}


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

    def test_chat_stream_request_uses_streaming_endpoint(self):
        """Streaming chat calls use stream=true and yield provider deltas."""
        transport = FakeTransport()
        client = OpenAICompatClient(
            ProviderConfig(base_url="https://example.test/v1", api_key="key", model="chat"),
            transport=transport,
        )

        chunks = list(
            client.stream_chat_completion(
                [{"role": "user", "content": "hi"}],
                tools=[],
            )
        )

        self.assertEqual(transport.last_path, "/chat/completions")
        self.assertEqual(transport.last_payload["model"], "chat")
        self.assertTrue(transport.last_payload["stream"])
        self.assertEqual(chunks, ["hel", "lo"])

    def test_chat_config_uses_longer_default_timeout(self):
        """Chat synthesis has more time than short embedding requests."""
        with patch.dict("os.environ", {}, clear=True):
            config = chat_config_from_env()

        self.assertEqual(config.timeout_seconds, DEFAULT_CHAT_TIMEOUT_SECONDS)

    def test_chat_timeout_can_be_overridden(self):
        """Operators can tune slow proxy calls without code changes."""
        with patch.dict("os.environ", {"ONCALL_CHAT_TIMEOUT_SECONDS": "75"}, clear=True):
            config = chat_config_from_env()

        self.assertEqual(config.timeout_seconds, 75.0)


if __name__ == "__main__":
    unittest.main()
