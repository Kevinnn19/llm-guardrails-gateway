"""LiteLLM-backed provider implementation.

A single class covers all LiteLLM-supported providers (OpenAI, Anthropic,
Gemini, Ollama, etc.). The `model` field on ProviderRequest uses LiteLLM's
routing syntax: "openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022",
"gemini/gemini-1.5-pro", "ollama/llama3".

Adding a new provider requires zero changes here — just a new model string.
"""

import time
from typing import Any

import litellm

from app.core.exceptions import ProviderError
from app.core.logging import logger
from app.providers.base import AbstractLLMProvider
from app.providers.models import ProviderRequest, ProviderResponse, TokenUsage

# Suppress LiteLLM's default verbose logging; our logger handles it
litellm.suppress_debug_info = True


def _extract_provider(model: str) -> str:
    """Derive a short provider name from a LiteLLM model string."""
    return model.split("/")[0] if "/" in model else "unknown"


def _build_usage(raw_usage: Any) -> TokenUsage | None:
    if raw_usage is None:
        return None
    return TokenUsage(
        prompt_tokens=getattr(raw_usage, "prompt_tokens", 0),
        completion_tokens=getattr(raw_usage, "completion_tokens", 0),
        total_tokens=getattr(raw_usage, "total_tokens", 0),
    )


class LiteLLMProvider(AbstractLLMProvider):
    """Routes completion requests through LiteLLM's unified API."""

    @property
    def provider_name(self) -> str:
        return "litellm"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages = [m.model_dump() for m in request.messages]
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "timeout": request.timeout_seconds,
            **request.extra,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        logger.debug(
            "provider_request model={} messages={}", request.model, len(messages)
        )
        start = time.perf_counter()

        try:
            response = await litellm.acompletion(**kwargs)
        except litellm.AuthenticationError as exc:
            raise ProviderError(
                f"Authentication failed for {request.model}: {exc}"
            ) from exc
        except litellm.RateLimitError as exc:
            raise ProviderError(
                f"Rate limit exceeded for {request.model}: {exc}"
            ) from exc
        except litellm.BadRequestError as exc:
            raise ProviderError(f"Bad request to {request.model}: {exc}") from exc
        except Exception as exc:
            raise ProviderError(
                f"Provider call failed for {request.model}: {exc}"
            ) from exc

        latency_ms = (time.perf_counter() - start) * 1000
        content: str = response.choices[0].message.content or ""
        served_model: str = getattr(response, "model", request.model)

        logger.debug(
            "provider_response model={} latency_ms={:.1f} tokens={}",
            served_model,
            latency_ms,
            getattr(response, "usage", None),
        )

        return ProviderResponse(
            content=content,
            model=served_model,
            provider=_extract_provider(request.model),
            usage=_build_usage(getattr(response, "usage", None)),
            latency_ms=latency_ms,
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )
