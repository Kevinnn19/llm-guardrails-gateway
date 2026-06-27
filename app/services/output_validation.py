"""OutputValidationService — runs the output guardrail chain."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.policies.models import OutputGuardrailsConfig, Policy

_OUTPUT_GUARDRAIL_CONFIG_KEY: dict[str, str] = {
    "JSONSchemaValidator":    "json_schema",
    "OutputToxicityDetector": "toxicity",
    "PromptLeakageDetector":  "prompt_leakage",
    "SecretLeakageDetector":  "secret_leakage",
    "OffTopicDetector":       "off_topic",
    "HallucinationGuard":     "hallucination",
}


class OutputValidationService:
    """Runs an ordered output guardrail chain."""

    def __init__(self, guardrails: list[AbstractGuardrail]) -> None:
        self._guardrails = guardrails

    def validate(
        self,
        response: str,
        prompt: str = "",
        context: GuardrailContext | None = None,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """Run all guardrails against the LLM response.

        Args:
            response:  The LLM-generated text to validate.
            prompt:    Original prompt — forwarded to leakage/off-topic guardrails.
            context:   Additional policy config merged into the per-guardrail context.
            fail_fast: Stop at the first failure.
        """
        base_ctx = GuardrailContext(context or {})
        base_ctx["prompt"] = prompt  # inject for leakage + off-topic guardrails

        all_violations: list[Violation] = []
        for guardrail in self._guardrails:
            result = guardrail.validate(response, base_ctx)
            if not result.passed:
                all_violations.extend(result.violations)
                if fail_fast:
                    return ValidationResult.fail(
                        violations=all_violations,
                        risk_score=result.risk_score,
                    )

        if not all_violations:
            return ValidationResult.ok()

        return ValidationResult.fail(
            violations=all_violations,
            risk_score=max(v.score for v in all_violations),
        )

    def validate_with_policy(
        self,
        response: str,
        policy: Policy,
        prompt: str = "",
        fail_fast: bool = False,
    ) -> ValidationResult:
        """Run only policy-enabled output guardrails with per-guardrail config."""
        og = policy.output_guardrails
        all_violations: list[Violation] = []

        for guardrail in self._guardrails:
            cfg_key = _OUTPUT_GUARDRAIL_CONFIG_KEY.get(guardrail.name)
            if cfg_key is None:
                continue
            cfg = getattr(og, cfg_key, None)
            if cfg is None or not cfg.enabled:
                continue

            ctx = GuardrailContext(cfg.model_dump())
            ctx["prompt"] = prompt
            result = guardrail.validate(response, ctx)
            if not result.passed:
                all_violations.extend(result.violations)
                if fail_fast:
                    return ValidationResult.fail(
                        violations=all_violations,
                        risk_score=result.risk_score,
                    )

        if not all_violations:
            return ValidationResult.ok()

        return ValidationResult.fail(
            violations=all_violations,
            risk_score=max(v.score for v in all_violations),
        )

    @property
    def guardrail_names(self) -> list[str]:
        return [g.name for g in self._guardrails]
