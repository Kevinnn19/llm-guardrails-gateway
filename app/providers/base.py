"""Abstract interface for LLM providers.

Any concrete provider must implement `complete`. The Strategy Pattern is used
here: the GatewayService depends only on this interface and never on a
concrete implementation, making providers swappable at runtime.
"""

from abc import ABC, abstractmethod

from app.providers.models import ProviderRequest, ProviderResponse


class AbstractLLMProvider(ABC):
    """Contract every LLM provider adapter must fulfil."""

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Send a completion request and return a normalised response.

        Raises:
            ProviderError: on any provider-side failure (network, auth, rate limit).
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifies this provider in logs and response metadata."""
