"""Secret / API key detector."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import SECRETS


class SecretDetector(AbstractGuardrail):
    """Detects API keys, tokens, and credentials in prompts."""

    @property
    def name(self) -> str:
        return "SecretDetector"

    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        violations: list[Violation] = []

        for secret_type, pattern in SECRETS.items():
            if pattern.search(content):
                violations.append(
                    Violation(
                        guardrail=self.name,
                        code="secret_detected",
                        message=f"Potential secret detected: {secret_type}",
                        severity="critical",
                        score=0.95,
                    )
                )

        if not violations:
            return ValidationResult.ok()

        return ValidationResult.fail(violations=violations, risk_score=1.0)
