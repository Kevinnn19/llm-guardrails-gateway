"""Hallucination guard — rule-based heuristics.

Detects signals that indicate a model may be hallucinating:
  1. Confident factual claims with no hedging language.
  2. Self-contradictory statements within the response.
  3. References to fabricated citations (e.g. "Smith et al., 2019" pattern
     without any URL or DOI to back them up — configurable).
  4. Extreme certainty phrases that are a hallucination red flag.

This is intentionally rule-based and conservative. A high false-negative
rate is acceptable — the guard only fires on clear signals. For production,
augment with a grounding step (RAG + factual consistency scoring).
"""

import re

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation

# Phrases that signal overconfident, unhedged factual claims
_OVERCONFIDENT: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(it is a fact that|the fact is|definitively|indisputably|undeniably)\b",
        r"\b(100\s*%\s*(certain|sure|accurate|correct|guaranteed))\b",
        r"\b(there is no doubt|without any doubt|absolutely certain)\b",
        r"\b(everyone knows|it is well known that|as all experts agree)\b",
    ]
]

# Citation-like patterns with no URL/DOI — possible fabricated reference
_FAKE_CITATION: re.Pattern[str] = re.compile(
    r"\b[A-Z][a-z]+(?: et al\.)?,?\s*\d{4}\b(?!.*https?://|.*doi\.org)",
)

# Self-contradiction signals
_CONTRADICTION: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        (
            r"\b(however|but|on the other hand|conversely)\b"
            r".{0,80}\b(earlier|above|previously)\b"
        ),
        r"\bcontradicts?\b",
    ]
]


class HallucinationGuard(AbstractGuardrail):
    """Rule-based hallucination signal detector."""

    @property
    def name(self) -> str:
        return "HallucinationGuard"

    def validate(
        self, content: str, context: GuardrailContext | None = None
    ) -> ValidationResult:
        ctx: GuardrailContext = context or GuardrailContext()
        check_citations: bool = bool(ctx.get("check_citations", False))

        violations: list[Violation] = []

        # Check overconfident language
        overconfident_hits = [p.pattern for p in _OVERCONFIDENT if p.search(content)]
        if overconfident_hits:
            violations.append(
                Violation(
                    guardrail=self.name,
                    code="hallucination_signal",
                    message=(
                        f"Overconfident language detected "
                        f"({len(overconfident_hits)} pattern(s))"
                    ),
                    severity="medium",
                    score=0.6,
                )
            )

        # Check fabricated citations (opt-in)
        if check_citations:
            citation_matches = _FAKE_CITATION.findall(content)
            if citation_matches:
                violations.append(
                    Violation(
                        guardrail=self.name,
                        code="possible_fabricated_citation",
                        message=(
                            f"Possible fabricated citation(s): "
                            f"{citation_matches[:3]}"
                        ),
                        severity="medium",
                        score=0.65,
                    )
                )

        # Check self-contradiction signals
        contradiction_hits = [p.pattern for p in _CONTRADICTION if p.search(content)]
        if contradiction_hits:
            violations.append(
                Violation(
                    guardrail=self.name,
                    code="contradiction_signal",
                    message="Possible self-contradiction detected in response",
                    severity="low",
                    score=0.45,
                )
            )

        if not violations:
            return ValidationResult.ok()

        risk = max(v.score for v in violations)
        return ValidationResult.fail(violations=violations, risk_score=risk)
