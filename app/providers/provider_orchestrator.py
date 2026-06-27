"""Provider orchestration with automatic failover for recoverable errors.

The orchestrator accepts a provider factory and an ordered list of provider
configurations. It tries each provider sequentially, returning on the first
successful response. Recoverable provider failures (timeouts, rate limits,
quota exhaustion, and transient network issues) trigger a move to the next
configured provider. Non-recoverable failures stop the orchestration
immediately.
"""

from collections.abc import Sequence

from app.core.exceptions import ProviderError
from app.core.logging import logger
from app.providers.base import AbstractLLMProvider
from app.providers.factory import ProviderFactory
from app.providers.models import ProviderRequest, ProviderResponse


class ProviderOrchestrator:
    """Coordinate sequential provider selection and execution."""

    _RECOVERABLE_FAILURE_MARKERS = (
        "timeout",
        "rate limit",
        "quota",
        "temporar",
        "network",
        "connection",
    )

    def __init__(self, provider_factory: ProviderFactory) -> None:
        """Create an orchestrator bound to a provider factory.

        Args:
            provider_factory: Factory that resolves model strings to provider
                implementations.
        """
        self._provider_factory = provider_factory

    async def execute(
        self,
        request: ProviderRequest,
        provider_configs: Sequence[dict[str, str | float | None]],
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
        failures: list[tuple[str, str]] = []

        for provider_config in provider_configs:
            model = provider_config.get("model")
            if not isinstance(model, str) or not model:
                raise ValueError(
                    "Each provider configuration must include a non-empty model"
                )

            provider: AbstractLLMProvider = self._provider_factory.get_provider(model)

            try:
                return await provider.complete(request.model_copy(update={"model": model}))
            except ProviderError as exc:
                reason = str(exc)
                failures.append((model, reason))
                if self._is_recoverable_failure(reason):
                    logger.warning(
                        "provider_failed_rolling_over model={} reason={}",
                        model,
                        reason,
                    )
                    continue

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
