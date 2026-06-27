"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config for the gateway. All fields can be overridden via env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "LLM Guardrails Gateway"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Policy
    policy_dir: Path = Path("policies")
    default_policy_id: str = "default"

    # LLM Provider defaults (overridden per-request via policy)
    openai_api_key: str = Field(default="", repr=False)
    anthropic_api_key: str = Field(default="", repr=False)
    google_api_key: str = Field(default="", repr=False)
    ollama_base_url: str = "http://localhost:11434"

    # Retry
    max_retry_attempts: int = 3

    # Request limits
    max_request_body_bytes: int = 1_048_576  # 1 MB


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return _settings


_settings = Settings()
