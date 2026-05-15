"""Chat Completions client interface."""

# pylint: disable=too-few-public-methods

from typing import Protocol

from oncall_app.llm.config import ProviderConfig, chat_config_from_env
from oncall_app.llm.openai_compat import JsonObject, OpenAICompatClient


class ChatClient(Protocol):
    """Protocol used by the Agent layer."""

    def create_chat_completion(
        self,
        messages: list[JsonObject],
        tools: list[JsonObject],
    ) -> JsonObject:
        """Create a Chat Completions response."""


def create_chat_client(config: ProviderConfig | None = None) -> OpenAICompatClient:
    """Create the default chat client."""
    return OpenAICompatClient(config or chat_config_from_env())
