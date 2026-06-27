"""Toxicity detector for input prompts."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import TOXICITY
from app.utils.text import normalise


class ToxicityDetector(AbstractGuardrail):
    """Detects toxic, hateful, or threatening language in prompts."""

    @property
    def name(self) -> str:
        return "ToxicityDetector"

    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        ctx = context or {}
        threshold: float = float(ctx.get("threshold", 0.5))

        normalised = normalise(content)
        matches = [p.pattern for p in TOXICITY if p.search(normalised)]
        if not matches:
            return ValidationResult.ok()

        score = min(1.0, 0.4 + 0.15 * len(matches))
        if score < threshold:
            return ValidationResult.ok()

        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="toxic_content_detected",
                    message=f"Toxic content detected ({len(matches)} match(es))",
                    severity="high",
                    score=score,
                )
            ],
            risk_score=score,
        )
