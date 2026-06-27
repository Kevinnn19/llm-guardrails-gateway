"""PII detector — finds personally identifiable information in prompts."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.patterns import PII

# Default entities to check when no context config is supplied
_DEFAULT_ENTITIES: frozenset[str] = frozenset({"EMAIL", "PHONE", "SSN", "CREDIT_CARD"})


class PIIDetector(AbstractGuardrail):
    """Detects PII entities in the prompt using regex patterns."""

    @property
    def name(self) -> str:
        return "PIIDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        ctx = context or {}
        entities: frozenset[str] = frozenset(ctx.get("entities", _DEFAULT_ENTITIES))

        violations: list[Violation] = []
        for entity, pattern in PII.items():
            if entity not in entities:
                continue
            if pattern.search(content):
                violations.append(
                    Violation(
                        guardrail=self.name,
                        code="pii_detected",
                        message=f"PII detected: {entity}",
                        severity="high",
                        score=0.9,
                    )
                )

        if not violations:
            return ValidationResult.ok()

        risk = min(1.0, 0.5 + 0.1 * len(violations))
        return ValidationResult.fail(violations=violations, risk_score=risk)
