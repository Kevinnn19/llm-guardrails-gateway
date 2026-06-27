"""Prompt leakage detector.

Checks whether the LLM response accidentally echoes back content from the
system prompt or the original user prompt. This matters when the system
prompt contains confidential instructions, business logic, or security rules.

Detection strategy:
  1. Exact substring match of long prompt fragments in the response.
  2. N-gram overlap above a configurable threshold.

The original prompt is passed via context['prompt'].
"""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.text import normalise

_DEFAULT_OVERLAP_THRESHOLD = 0.35   # fraction of prompt 5-grams found in response
_MIN_PROMPT_LEN = 20                # ignore very short prompts


def _word_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = text.split()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


class PromptLeakageDetector(AbstractGuardrail):
    """Detects when the model leaks back content from the original prompt."""

    @property
    def name(self) -> str:
        return "PromptLeakageDetector"

    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        ctx = context or {}
        prompt: str = ctx.get("prompt", "")
        threshold: float = float(ctx.get("overlap_threshold", _DEFAULT_OVERLAP_THRESHOLD))

        if len(prompt) < _MIN_PROMPT_LEN:
            return ValidationResult.ok()

        norm_prompt = normalise(prompt)
        norm_response = normalise(content)

        # Exact long-fragment check (>30 chars)
        words = norm_prompt.split()
        if len(words) >= 6:
            chunk = " ".join(words[:6])
            if chunk in norm_response:
                return ValidationResult.fail(
                    violations=[Violation(
                        guardrail=self.name,
                        code="prompt_leakage_detected",
                        message="Response contains verbatim fragment of the original prompt",
                        severity="high",
                        score=0.9,
                    )],
                    risk_score=0.9,
                )

        # N-gram overlap check
        prompt_ngrams = _word_ngrams(norm_prompt, 5)
        if not prompt_ngrams:
            return ValidationResult.ok()

        response_ngrams = _word_ngrams(norm_response, 5)
        overlap = len(prompt_ngrams & response_ngrams) / len(prompt_ngrams)

        if overlap >= threshold:
            score = min(1.0, 0.5 + overlap)
            return ValidationResult.fail(
                violations=[Violation(
                    guardrail=self.name,
                    code="prompt_leakage_detected",
                    message=f"Response overlaps with prompt at {overlap:.0%}",
                    severity="high",
                    score=score,
                )],
                risk_score=score,
            )

        return ValidationResult.ok()
