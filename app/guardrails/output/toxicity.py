"""Toxicity detector for LLM output responses.

Reuses the same TOXICITY patterns from utils/patterns.py used by the input
toxicity detector. Output toxicity may warrant a different default threshold
since model outputs are generally cleaner than raw user prompts.
"""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import TOXICITY
from app.utils.text import normalise

_DEFAULT_THRESHOLD = 0.85


class OutputToxicityDetector(AbstractGuardrail):
    """Detects toxic content in LLM responses."""

    @property
    def name(self) -> str:
        return "OutputToxicityDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        ctx = context or {}
        threshold: float = float(ctx.get("threshold", _DEFAULT_THRESHOLD))

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
                    code="toxic_output_detected",
                    message=f"Toxic content in response ({len(matches)} match(es))",
                    severity="high",
                    score=score,
                )
            ],
            risk_score=score,
        )
