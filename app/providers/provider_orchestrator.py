"""Provider orchestration with automatic failover for recoverable errors.

The orchestrator accepts a provider factory and an ordered list of provider
configurations. It tries each provider sequentially, returning on the first
successful response. Recoverable provider failures (timeouts, rate limits,
quota exhaustion, and transient network issues) trigger a move to the next
configured provider. Non-recoverable failures stop the orchestration
immediately.
"""

import time
from collections.abc import Sequence

from app.core.exceptions import ProviderError
from app.core.logging import logger
from app.providers.base import AbstractLLMProvider
from app.providers.factory import ProviderFactory
from app.providers.models import (
    ProviderAttempt,
    ProviderRequest,
    ProviderResponse,
)
from app.providers.strategies import (
    ProviderSelectionStrategy,
    ProviderSelectionStrategyFactory,
)


class ProviderOrchestrator:
    """Coordinate sequential provider selection and execution."""

    _RECOVERABLE_FAILURE_MARKERS = (
        "timeout",
        "timed out",
        "rate limit",
        "quota",
        "temporar",
        "network",
        "connection",
    )

    def __init__(
        self,
        provider_factory: ProviderFactory,
        strategy: ProviderSelectionStrategy | None = None,
    ) -> None:
        """Create an orchestrator bound to a provider factory.

        Args:
            provider_factory: Factory that resolves model strings to provider
                implementations.
            strategy: Selection strategy used to order provider attempts.
        """
        self._provider_factory = provider_factory
        self._strategy = strategy or ProviderSelectionStrategyFactory().build(
            "sequential"
        )

    async def execute(
        self,
        request: ProviderRequest,
        provider_configs: Sequence[dict[str, str | float | None]],
        strategy_name: str | None = None,
    ) -> ProviderResponse:
        """Attempt each configured provider in order until one succeeds.

        The current implementation does not implement fallback policy, retrying,
        or any form of error aggregation. The first successful provider response
        is returned immediately.

        Args:
            request: The shared completion request to execute.
            provider_configs: Ordered provider configuration entries. Each entry
                must include at least a model identifier.

        Returns:
            The first successful provider response.

        Raises:
            ProviderError: If every configured provider fails.
        """
        strategy = self._strategy
        if strategy_name is not None:
            strategy = ProviderSelectionStrategyFactory().build(strategy_name)

        ordered_configs = strategy.select(provider_configs)
        failures: list[tuple[str, str]] = []
        attempted_providers: list[str] = []
        attempt_history: list[ProviderAttempt] = []
        total_configs = len(ordered_configs)

        for attempt, provider_config in enumerate(ordered_configs, start=1):
            model = provider_config.get("model")
            if not isinstance(model, str) or not model:
                raise ValueError(
                    "Each provider configuration must include a non-empty model"
                )

            provider: AbstractLLMProvider = self._provider_factory.get_provider(model)
            attempted_providers.append(model.split("/")[0])
            started_at = time.perf_counter()

            logger.info(
                "Provider {}/{} | {} | {} | Attempt started",
                attempt,
                total_configs,
                model.split("/")[0],
                model,
            )

            try:
                response = await provider.complete(
                    request.model_copy(update={"model": model})
                )
                latency_ms = (time.perf_counter() - started_at) * 1000
                logger.info(
                    "Provider {}/{} | {} | Success | {:.2f} ms",
                    attempt,
                    total_configs,
                    model.split("/")[0],
                    latency_ms,
                )
                logger.info(
                    "Provider {} selected. Returning response to Gateway.",
                    model.split("/")[0],
                )
                response.raw["provider_chain"] = attempted_providers
                response.raw["attempts"] = attempt
                response.raw["fallback_used"] = attempt > 1
                attempt_history.append(
                    ProviderAttempt(
                        provider=model.split("/")[0],
                        status="success",
                        latency_ms=latency_ms,
                    )
                )

                response.attempt_history = attempt_history
                return response
            except ProviderError as exc:
                latency_ms = (time.perf_counter() - started_at) * 1000
                reason = str(exc)
                attempt_history.append(
                    ProviderAttempt(
                        provider=model.split("/")[0],
                        status="failed",
                        latency_ms=latency_ms,
                        reason=reason,
                    )
                )
                failures.append((model, reason))

                if self._is_recoverable_failure(reason):
                    logger.warning(
                        "Provider {}/{} | {} | Recoverable Failure | {}",
                        attempt,
                        total_configs,
                        model.split("/")[0],
                        reason,
                    )

                    if attempt < total_configs:
                        logger.info(
                            "Switching to provider {}/{}",
                            attempt + 1,
                            total_configs,
                        )
                    continue

                logger.error(
                    "Provider {}/{} | {} | Non-Recoverable Failure | {}",
                    attempt,
                    total_configs,
                    model.split("/")[0],
                    reason,
                )
                raise ProviderError(
                    f"Provider '{model}' failed with non-recoverable error: {reason}"
                ) from exc

        if failures:
            details = "; ".join(f"{model}: {reason}" for model, reason in failures)
            raise ProviderError(f"All providers failed: {details}")

        raise ProviderError("No providers were configured for orchestration")

    @classmethod
    def _is_recoverable_failure(cls, reason: str) -> bool:
        lowered = reason.lower()
        return any(marker in lowered for marker in cls._RECOVERABLE_FAILURE_MARKERS)
