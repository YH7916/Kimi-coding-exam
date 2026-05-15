"""Provider configuration for OpenAI-compatible APIs."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 30.0
DEFAULT_CHAT_TIMEOUT_SECONDS = 60.0

load_dotenv()


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime settings for an OpenAI-compatible provider."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS


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
        timeout_seconds=_timeout_from_env(
            "ONCALL_CHAT_TIMEOUT_SECONDS",
            DEFAULT_CHAT_TIMEOUT_SECONDS,
        ),
    )


def _timeout_from_env(name: str, default: float) -> float:
    """Read a positive timeout value from the environment."""
    try:
        timeout = float(os.getenv(name, ""))
    except ValueError:
        return default
    if timeout <= 0:
        return default
    return timeout
