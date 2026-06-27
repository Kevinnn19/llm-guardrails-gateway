"""Off-topic detector.

Checks whether the LLM response is relevant to the original prompt using
keyword overlap heuristics. A low overlap ratio between prompt and response
vocabulary suggests the model drifted off-topic.

This is intentionally lightweight. For production use with strict topic
enforcement, replace keyword overlap with a sentence-transformer similarity
score (cosine similarity >= threshold).

Requires context['prompt'] to compare against.
"""

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation
from app.utils.text import normalise

_DEFAULT_MIN_OVERLAP = 0.05  # minimum keyword overlap ratio to be considered on-topic
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "and",
        "or",
        "but",
        "not",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "it",
        "this",
        "that",
        "be",
        "have",
        "do",
        "what",
        "how",
        "why",
        "when",
        "where",
        "which",
        "i",
        "you",
        "we",
        "they",
        "he",
        "she",
    }
)


def _keywords(text: str) -> set[str]:
    return {w for w in normalise(text).split() if w not in _STOP_WORDS and len(w) > 2}


class OffTopicDetector(AbstractGuardrail):
    """Flags responses that appear unrelated to the original prompt."""

    @property
    def name(self) -> str:
        return "OffTopicDetector"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        ctx: GuardrailContext = context or GuardrailContext()
        prompt: str = ctx.get("prompt", "")
        min_overlap: float = float(ctx.get("min_overlap", _DEFAULT_MIN_OVERLAP))

        if not prompt.strip():
            return ValidationResult.ok()  # can't judge without a prompt

        prompt_kw = _keywords(prompt)
        response_kw = _keywords(content)

        if not prompt_kw or not response_kw:
            return ValidationResult.ok()

        overlap = len(prompt_kw & response_kw) / len(prompt_kw)

        if overlap >= min_overlap:
            return ValidationResult.ok()

        score = min(1.0, 0.5 + (min_overlap - overlap) * 5)
        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="off_topic_response",
                    message=f"Response keyword overlap with prompt is {overlap:.0%} (min {min_overlap:.0%})",
                    severity="medium",
                    score=score,
                )
            ],
            risk_score=score,
        )
