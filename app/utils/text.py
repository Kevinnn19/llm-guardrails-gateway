"""Text utility helpers used across guardrails."""

import re
import unicodedata


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace.

    Normalisation prevents trivial bypasses like "Ign0re" or "IGNORE  ALL".
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_chars: int = 500) -> str:
    """Return a safe preview for logging — never log full prompts."""
    return text[:max_chars] + "…" if len(text) > max_chars else text


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT-3/4 rule of thumb).

    Accurate enough for limit checks without requiring a tokeniser dependency.
    Use a real tokeniser (tiktoken) if sub-5% accuracy is needed.
    """
    return max(1, len(text) // 4)
