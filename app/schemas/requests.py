"""API request schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32_768)
    provider: str | None = None
    model: str | None = None
    policy_id: str | None = None
    context: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


class ValidateInputRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32_768)
    policy_id: str | None = None


class ValidateOutputRequest(BaseModel):
    response: str = Field(..., min_length=1)
    prompt: str | None = None  # original prompt for leakage / off-topic checks
    policy_id: str | None = None
    expected_schema: dict[str, Any] | None = None  # inline JSON schema override


class ReloadPolicyRequest(BaseModel):
    policy_id: str | None = None  # None = reload all
