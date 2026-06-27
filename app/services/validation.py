"""ValidationService — runs a chain of guardrails and aggregates results."""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.policies.models import InputGuardrailsConfig, Policy

# Maps guardrail class name → the InputGuardrailsConfig attribute that controls it
_INPUT_GUARDRAIL_CONFIG_KEY: dict[str, str] = {
    "PromptInjectionDetector": "prompt_injection",
    "JailbreakDetector": "jailbreak",
    "PIIDetector": "pii",
    "SecretDetector": "secrets",
    "TokenLengthValidator": "token_length",
    "LanguageValidator": "language",
    "ToxicityDetector": "toxicity",
}


def build_input_context(ig: InputGuardrailsConfig) -> GuardrailContext:
    """Flatten InputGuardrailsConfig into a single GuardrailContext dict.

    Each guardrail reads its own keys from this flat dict, so we merge all
    configs together. Key collisions (e.g. two guardrails both have
    'threshold') are prevented by using guardrail-name-prefixed keys in
    practice — but since each guardrail only reads the keys it expects, the
    flat merge is safe and keeps GuardrailContext simple.
    """
    return GuardrailContext(
        # PromptInjection / Jailbreak / Toxicity
        threshold=ig.prompt_injection.threshold,  # each guardrail overrides locally
        # PII
        entities=ig.pii.entities,
        # TokenLength
        max_tokens=ig.token_length.max_tokens,
        # Language
        allowed=ig.language.allowed,
    )


class ValidationService:
    """Runs an ordered guardrail chain and produces an aggregated result."""

    def __init__(self, guardrails: list[AbstractGuardrail]) -> None:
        self._guardrails = guardrails

    def validate(
        self,
        content: str,
        context: GuardrailContext | None = None,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """Run all active guardrails against content."""
        all_violations: list[Violation] = []

        for guardrail in self._guardrails:
            result = guardrail.validate(content, context)
            if not result.passed:
                all_violations.extend(result.violations)
                if fail_fast:
                    return ValidationResult.fail(
                        violations=all_violations,
                        risk_score=result.risk_score,
                    )

        if not all_violations:
            return ValidationResult.ok()

        risk_score = max(v.score for v in all_violations)
        return ValidationResult.fail(violations=all_violations, risk_score=risk_score)

    def validate_with_policy(
        self,
        content: str,
        policy: Policy,
        fail_fast: bool = False,
    ) -> ValidationResult:
        """Run only policy-enabled guardrails, with policy-derived thresholds.

        Guardrails disabled in the policy (enabled=False) are skipped entirely.
        Per-guardrail thresholds and config are applied via the context.
        """
        ig = policy.input_guardrails
        active_guardrails = [
            g
            for g in self._guardrails
            if getattr(ig, _INPUT_GUARDRAIL_CONFIG_KEY.get(g.name, ""), None)
            is not None
            and getattr(ig, _INPUT_GUARDRAIL_CONFIG_KEY[g.name]).enabled
        ]

        # Build per-guardrail contexts so each gets its own threshold/config
        all_violations: list[Violation] = []
        for guardrail in active_guardrails:
            cfg_key = _INPUT_GUARDRAIL_CONFIG_KEY[guardrail.name]
            cfg = getattr(ig, cfg_key)
            ctx = GuardrailContext(cfg.model_dump())
            result = guardrail.validate(content, ctx)
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
