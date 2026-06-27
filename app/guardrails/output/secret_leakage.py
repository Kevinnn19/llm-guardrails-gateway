"""Secret leakage detector for LLM responses.

Reuses the same SECRETS pattern registry used by the input SecretDetector.
Even if no secrets entered via the prompt, a model might hallucinate or
reproduce credentials it saw during training.
"""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import SECRETS


class SecretLeakageDetector(AbstractGuardrail):
    """Detects API keys, tokens, and credentials leaked in LLM responses."""

    @property
    def name(self) -> str:
        return "SecretLeakageDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        violations: list[Violation] = []

        for secret_type, pattern in SECRETS.items():
            if pattern.search(content):
                violations.append(
                    Violation(
                        guardrail=self.name,
                        code="secret_leakage_detected",
                        message=f"Potential secret in response: {secret_type}",
                        severity="critical",
                        score=0.95,
                    )
                )

        if not violations:
            return ValidationResult.ok()

        return ValidationResult.fail(violations=violations, risk_score=1.0)
