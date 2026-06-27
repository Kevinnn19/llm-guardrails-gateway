"""Token length validator."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.text import estimate_tokens

_DEFAULT_MAX_TOKENS = 4096


class TokenLengthValidator(AbstractGuardrail):
    """Rejects prompts that exceed the configured token limit."""

    @property
    def name(self) -> str:
        return "TokenLengthValidator"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        ctx: GuardrailContext = context or GuardrailContext()
        max_tokens: int = int(ctx.get("max_tokens", _DEFAULT_MAX_TOKENS))
        estimated = estimate_tokens(content)

        if estimated <= max_tokens:
            return ValidationResult.ok()

        score = min(1.0, estimated / max_tokens - 1.0 + 0.5)
        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="token_limit_exceeded",
                    message=f"Estimated token count {estimated} exceeds limit {max_tokens}",
                    severity="medium",
                    score=score,
                )
            ],
            risk_score=score,
        )
