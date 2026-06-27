"""Provider orchestration for sequential provider execution.

The orchestrator is intentionally simple: it accepts a provider factory and a
list of provider configurations, then tries each provider in order until one
returns a successful response. Fallback policy and retry behavior are out of
scope for this initial implementation.
"""

from collections.abc import Sequence

from app.core.exceptions import ProviderError
from app.providers.base import AbstractLLMProvider
from app.providers.factory import ProviderFactory
from app.providers.models import ProviderRequest, ProviderResponse


class ProviderOrchestrator:
    """Coordinate sequential provider selection and execution."""

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
        last_error: ProviderError | None = None

        for provider_config in provider_configs:
            model = provider_config.get("model")
            if not isinstance(model, str) or not model:
                raise ValueError("Each provider configuration must include a non-empty model")

            provider: AbstractLLMProvider = self._provider_factory.get_provider(model)

            try:
                return await provider.complete(request.model_copy(update={"model": model}))
            except ProviderError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        raise ProviderError("No providers were configured for orchestration")
