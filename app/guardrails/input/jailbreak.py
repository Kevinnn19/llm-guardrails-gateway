"""Jailbreak detector."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import JAILBREAK
from app.utils.text import normalise


class JailbreakDetector(AbstractGuardrail):
    """Detects attempts to strip the model of its safety guidelines."""

    @property
    def name(self) -> str:
        return "JailbreakDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        normalised = normalise(content)
        matches = [p.pattern for p in JAILBREAK if p.search(normalised)]
        if not matches:
            return ValidationResult.ok()

        score = min(1.0, 0.5 + 0.1 * len(matches))
        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="jailbreak_detected",
                    message=f"Jailbreak pattern detected ({len(matches)} match(es))",
                    severity="critical",
                    score=score,
                )
            ],
            risk_score=score,
        )
