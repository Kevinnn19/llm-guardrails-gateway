"""API response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ViolationDetail(BaseModel):
    guardrail: str
    code: str
    message: str
    severity: str  # "low" | "medium" | "high" | "critical"
    score: float = Field(ge=0.0, le=1.0)


class ValidationResponse(BaseModel):
    valid: bool
    violations: list[ViolationDetail] = []
    risk_score: float = Field(ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    request_id: str
    response: str
    provider: str
    model: str
    risk_score: float = Field(ge=0.0, le=1.0)
    violations: list[ViolationDetail] = []
    retries: int = 0
    latency_ms: float
    input_valid: bool
    output_valid: bool


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    policies_loaded: list[str]


class PolicySummary(BaseModel):
    id: str
    version: str
    provider: str
    input_guardrails_enabled: list[str]
    output_guardrails_enabled: list[str]


class PoliciesResponse(BaseModel):
    policies: list[PolicySummary]


class ReloadPolicyResponse(BaseModel):
    reloaded: list[str]
    errors: dict[str, str] = {}


class ErrorResponse(BaseModel):
    request_id: str
    code: str
    message: str
    details: Any = None
