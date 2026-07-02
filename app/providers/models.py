"""Provider domain models — the gateway's internal representation of LLM I/O.

These are deliberately decoupled from LiteLLM and any specific provider SDK
so the rest of the codebase never imports provider-specific types.
"""

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single conversation turn."""

    role: str  # "system" | "user" | "assistant"
    content: str


class ProviderRequest(BaseModel):
    """Everything needed to make an LLM completion call."""

    model: str  # LiteLLM model string, e.g. "openai/gpt-4o", "ollama/llama3"
    messages: list[Message]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = None
    timeout_seconds: float = 30.0
    extra: dict[str, Any] = Field(default_factory=dict)  # pass-through params


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ProviderAttempt(BaseModel):
    provider: str
    status: str
    reason: str | None = None

class ProviderResponse(BaseModel):
    """Normalised LLM response returned to the rest of the gateway."""

    content: str
    model: str  # model that actually served the request (may differ from requested)
    provider: str  # e.g. "openai", "deepseek", "ollama"
    usage: TokenUsage | None = None
    latency_ms: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)  # original response
    attempt_history: list[ProviderAttempt] = Field(default_factory=list)