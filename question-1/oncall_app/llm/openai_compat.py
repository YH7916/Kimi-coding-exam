"""OpenAI-compatible HTTP client."""

# pylint: disable=too-few-public-methods

from typing import Any, Protocol, cast

import httpx

from oncall_app.llm.config import ProviderConfig

JsonObject = dict[str, Any]


class JsonTransport(Protocol):
    """Minimal JSON transport used by unit tests and real HTTP calls."""

    def post_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> JsonObject:
        """POST JSON to a provider path."""


class HttpxTransport:
    """HTTP transport backed by httpx."""

    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def post_json(
        self,
        path: str,
        payload: JsonObject,
        headers: dict[str, str],
    ) -> JsonObject:
        """POST JSON and return the provider response body."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("provider returned a non-object JSON response")
        return cast(JsonObject, data)


class OpenAICompatClient:
    """Small client for OpenAI-compatible embeddings and chat completions."""

    def __init__(
        self,
        config: ProviderConfig,
        transport: JsonTransport | None = None,
    ):
        self.config = config
        self._transport = transport or HttpxTransport(
            config.base_url,
            config.timeout_seconds,
        )

    def create_embedding(self, text: str) -> list[float]:
        """Create one embedding vector for text."""
        response = self._transport.post_json(
            "/embeddings",
            {"model": self.config.model, "input": text},
            self._headers(),
        )
        embedding = _extract_embedding(response)
        return [float(value) for value in embedding]

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Create a Chat Completions response."""
        return self._transport.post_json(
            "/chat/completions",
            {"model": self.config.model, "messages": messages, "tools": tools},
            self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        """Build provider request headers."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


def _extract_embedding(response: JsonObject) -> list[Any]:
    """Extract an embedding vector from an OpenAI-compatible response."""
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("embedding response missing data")
    first_item = data[0]
    if not isinstance(first_item, dict):
        raise ValueError("embedding response item is not an object")
    embedding = first_item.get("embedding")
    if not isinstance(embedding, list):
        raise ValueError("embedding response missing vector")
    return embedding
