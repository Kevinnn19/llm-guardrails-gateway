"""Language validator — ensures the prompt is in an allowed language.

Detection strategy: character-set heuristics + common word frequency.
This avoids a heavy ML dependency (langdetect / fasttext) while being
reliable enough for the most common use-case (enforce English-only).
For production use with many languages, swap _detect_language() for
langdetect or lingua with a conditional import.
"""

import re

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation

_DEFAULT_ALLOWED = ["en"]

# High-frequency English function words — present in almost every English sentence
_EN_MARKERS: re.Pattern[str] = re.compile(
    r"\b(the|is|are|was|were|and|or|but|not|this|that|with|for|you|have|it|"
    r"they|be|at|by|from|on|an|a|in|to|of|do|does|did|will|would|can|could)\b",
    re.IGNORECASE,
)

# CJK unified ideographs (Chinese/Japanese/Korean)
_CJK: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
# Arabic / Hebrew
_ARABIC_HEBREW: re.Pattern[str] = re.compile(r"[\u0600-\u06ff\u0590-\u05ff]")
# Cyrillic (Russian, etc.)
_CYRILLIC: re.Pattern[str] = re.compile(r"[\u0400-\u04ff]")
# Devanagari (Hindi, etc.)
_DEVANAGARI: re.Pattern[str] = re.compile(r"[\u0900-\u097f]")


def _detect_language(text: str) -> str:
    """Heuristic language detection. Returns ISO 639-1 code or 'unknown'."""
    if len(text.strip()) < 4:
        return "en"  # too short to judge; pass through

    # Non-Latin scripts: check raw text FIRST, before word-count guards.
    # CJK text has no spaces, so word-count is always low.
    if _CJK.search(text):
        return "zh"
    if _ARABIC_HEBREW.search(text):
        return "ar"
    if _CYRILLIC.search(text):
        return "ru"
    if _DEVANAGARI.search(text):
        return "hi"

    words = len(text.split())
    if words < 3:
        return "en"

    en_hits = len(_EN_MARKERS.findall(text))
    ratio = en_hits / max(words, 1)
    return "en" if ratio >= 0.15 else "unknown"


class LanguageValidator(AbstractGuardrail):
    """Rejects prompts not written in an allowed language."""

    @property
    def name(self) -> str:
        return "LanguageValidator"

    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        ctx = context or {}
        allowed: list[str] = list(ctx.get("allowed", _DEFAULT_ALLOWED))
        detected = _detect_language(content)

        if detected in allowed or detected == "unknown":
            return ValidationResult.ok()

        return ValidationResult.fail(
            violations=[
                Violation(
                    guardrail=self.name,
                    code="language_not_allowed",
                    message=f"Detected language '{detected}' is not in allowed list {allowed}",
                    severity="medium",
                    score=0.8,
                )
            ],
            risk_score=0.8,
        )
