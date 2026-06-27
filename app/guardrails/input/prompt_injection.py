"""Prompt injection detector."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import PROMPT_INJECTION
from app.utils.text import normalise


class PromptInjectionDetector(AbstractGuardrail):
    """Detects attempts to override system instructions via the user prompt."""

    @property
    def name(self) -> str:
        return "PromptInjectionDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        normalised = normalise(content)
        matches = [p.pattern for p in PROMPT_INJECTION if p.search(normalised)]
        if not matches:
            return ValidationResult.ok()

        score = min(1.0, 0.5 + 0.1 * len(matches))
        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="prompt_injection_detected",
                    message=f"Prompt injection pattern detected ({len(matches)} match(es))",
                    severity="critical",
                    score=score,
                )
            ],
            risk_score=score,
        )
