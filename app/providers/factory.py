"""ProviderFactory — resolves a model string to an AbstractLLMProvider.

Design: all currently-supported providers are backed by LiteLLM. The factory
exists as a seam: if a future provider needs a bespoke client (e.g. a private
deployment with a custom SDK), register it here without touching call sites.

Supported model prefixes:
    openai/...        → OpenAI via LiteLLM
    deepseek/...      → DeepSeek via LiteLLM
    gemini/...        → Google Gemini via LiteLLM
    ollama/...        → Ollama via LiteLLM
    <no prefix>       → passed to LiteLLM as-is (default OpenAI behaviour)
"""

from app.core.exceptions import ProviderNotFoundError
from app.providers.base import AbstractLLMProvider
from app.providers.litellm_provider import LiteLLMProvider

# Providers that route through LiteLLM — extend this set to add new ones
_LITELLM_PREFIXES: frozenset[str] = frozenset(
    {"openai", "deepseek", "gemini", "ollama", "azure", "cohere", "huggingface"}
)

# Module-level singleton — LiteLLMProvider is stateless so one instance suffices
_litellm_provider = LiteLLMProvider()


class ProviderFactory:
    """Maps model strings to the appropriate AbstractLLMProvider implementation."""

    def get_provider(self, model: str) -> AbstractLLMProvider:
        """Return the provider for the given LiteLLM model string.

        Args:
            model: LiteLLM routing string, e.g. "openai/gpt-4o".

        Raises:
            ProviderNotFoundError: if the prefix is explicitly unsupported.
        """
        prefix = model.split("/")[0] if "/" in model else "openai"

        if prefix in _LITELLM_PREFIXES:
            return _litellm_provider

        raise ProviderNotFoundError(
            f"No provider registered for prefix '{prefix}'. "
            f"Supported prefixes: {sorted(_LITELLM_PREFIXES)}"
        )
