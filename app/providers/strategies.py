"""Provider selection strategies for orchestration.

The strategy layer is intentionally small and isolated so future provider
selection policies can be added with minimal changes to the orchestrator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class ProviderSelectionStrategy(ABC):
    """Selects the order in which providers should be attempted."""

    name: str

    @abstractmethod
    def select(
        self,
        provider_configs: Sequence[dict[str, str | float | None]],
    ) -> list[dict[str, str | float | None]]:
        """Return the provider configurations in execution order."""


class SequentialProviderSelectionStrategy(ProviderSelectionStrategy):
    """Try providers in the order supplied by policy."""

    name = "sequential"

    def select(
        self,
        provider_configs: Sequence[dict[str, str | float | None]],
    ) -> list[dict[str, str | float | None]]:
        return list(provider_configs)


class ProviderSelectionStrategyFactory:
    """Builds provider selection strategies from policy configuration."""

    def build(self, strategy_name: str | None) -> ProviderSelectionStrategy:
        normalized_name = (strategy_name or "sequential").strip().lower()

        if normalized_name == "sequential":
            return SequentialProviderSelectionStrategy()

        raise NotImplementedError(
            f"Provider strategy '{strategy_name}' is not implemented yet"
        )
