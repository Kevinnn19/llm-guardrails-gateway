"""Abstract guardrail interface.

Every input and output guardrail implements this contract.
The Strategy Pattern: validators are interchangeable and composable.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.guardrails.result import ValidationResult


class GuardrailContext(dict[str, Any]):
    """Typed dict passed alongside content to provide policy config."""


class AbstractGuardrail(ABC):
    """Base class for all input and output guardrails."""

    @abstractmethod
    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        """Validate content and return a result.

        Args:
            content: The text to validate (prompt or LLM response).
            context: Optional policy-driven config (thresholds, allowed values, etc.).

        Returns:
            ValidationResult with passed=True or passed=False + violations.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in logs and violation records."""
