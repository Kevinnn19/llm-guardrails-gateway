"""Guardrail domain models: Violation and ValidationResult."""

from pydantic import BaseModel, Field


class Violation(BaseModel):
    """A single rule breach detected by a guardrail."""

    guardrail: str        # guardrail class name, e.g. "PromptInjectionDetector"
    code: str             # machine-readable code, e.g. "prompt_injection_detected"
    message: str          # human-readable description
    severity: str         # "low" | "medium" | "high" | "critical"
    score: float = Field(ge=0.0, le=1.0)  # confidence / severity score


class ValidationResult(BaseModel):
    """Aggregated output of one or more guardrail checks."""

    passed: bool
    violations: list[Violation] = []
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(passed=True)

    @classmethod
    def fail(cls, violations: list[Violation], risk_score: float = 1.0) -> "ValidationResult":
        return cls(passed=False, violations=violations, risk_score=risk_score)
