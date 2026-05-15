"""Provider configuration for OpenAI-compatible APIs."""

import os
from dataclasses import dataclass

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime settings for an OpenAI-compatible provider."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0


def embedding_config_from_env() -> ProviderConfig:
    """Load SiliconFlow embedding settings from environment variables."""
    return ProviderConfig(
        base_url=os.getenv("ONCALL_EMBEDDING_BASE_URL", SILICONFLOW_BASE_URL),
        api_key=os.getenv("ONCALL_EMBEDDING_API_KEY", ""),
        model=os.getenv("ONCALL_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
    )


def chat_config_from_env() -> ProviderConfig:
    """Load Chat Completions settings from environment variables."""
    return ProviderConfig(
        base_url=os.getenv("ONCALL_CHAT_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        api_key=os.getenv("ONCALL_CHAT_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        model=os.getenv("ONCALL_CHAT_MODEL", os.getenv("OPENAI_MODEL", "")),
    )
