"""Unit tests for the provider layer.

Strategy:
- LiteLLMProvider.complete() is tested by mocking litellm.acompletion — we
  never make real network calls in unit tests.
- ProviderFactory is tested purely in-process (no mocking needed).
- Error mapping is tested by making the mock raise each LiteLLM exception type
  and asserting a ProviderError is raised with the right message.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ProviderError, ProviderNotFoundError
from app.providers.factory import ProviderFactory
from app.providers.litellm_provider import LiteLLMProvider, _extract_provider
from app.providers.models import Message, ProviderRequest, ProviderResponse
from app.providers.provider_orchestrator import ProviderOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(model: str = "openai/gpt-4o") -> ProviderRequest:
    return ProviderRequest(
        model=model,
        messages=[Message(role="user", content="Hello")],
    )


def _make_litellm_response(content: str = "Hi there") -> MagicMock:
    """Build a minimal object that looks like a litellm ModelResponse."""
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15

    choice = MagicMock()
    choice.message.content = content

    response = MagicMock()
    response.choices = [choice]
    response.model = "gpt-4o-2024-05-13"
    response.usage = usage
    response.model_dump.return_value = {"id": "chatcmpl-test"}
    return response


# ---------------------------------------------------------------------------
# _extract_provider
# ---------------------------------------------------------------------------


class TestExtractProvider:
    def test_extracts_prefix(self) -> None:
        assert _extract_provider("openai/gpt-4o") == "openai"

    def test_extracts_anthropic(self) -> None:
        assert _extract_provider("anthropic/claude-3-5-sonnet-20241022") == "anthropic"

    def test_no_slash_returns_unknown(self) -> None:
        assert _extract_provider("gpt-4o") == "unknown"


# ---------------------------------------------------------------------------
# LiteLLMProvider.complete — happy path
# ---------------------------------------------------------------------------


class TestLiteLLMProviderComplete:
    @pytest.mark.asyncio
    async def test_returns_provider_response(self) -> None:
        mock_response = _make_litellm_response("Hello!")
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ):
            provider = LiteLLMProvider()
            result = await provider.complete(_make_request())

        assert isinstance(result, ProviderResponse)
        assert result.content == "Hello!"
        assert result.provider == "openai"
        assert result.model == "gpt-4o-2024-05-13"

    @pytest.mark.asyncio
    async def test_usage_mapped_correctly(self) -> None:
        mock_response = _make_litellm_response()
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await LiteLLMProvider().complete(_make_request())

        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_latency_is_positive(self) -> None:
        mock_response = _make_litellm_response()
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await LiteLLMProvider().complete(_make_request())
        assert result.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_max_tokens_forwarded(self) -> None:
        mock_response = _make_litellm_response()
        request = ProviderRequest(
            model="openai/gpt-4o",
            messages=[Message(role="user", content="Hi")],
            max_tokens=256,
        )
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ) as mock_call:
            await LiteLLMProvider().complete(request)
        _, kwargs = mock_call.call_args
        assert (
            kwargs.get("max_tokens") == 256
            or mock_call.call_args[1].get("max_tokens") == 256
        )

    @pytest.mark.asyncio
    async def test_no_max_tokens_when_none(self) -> None:
        mock_response = _make_litellm_response()
        request = _make_request()  # max_tokens=None
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ) as mock_call:
            await LiteLLMProvider().complete(request)
        call_kwargs: dict[str, Any] = mock_call.call_args[1]
        assert "max_tokens" not in call_kwargs

    @pytest.mark.asyncio
    async def test_none_usage_handled(self) -> None:
        mock_response = _make_litellm_response()
        mock_response.usage = None
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await LiteLLMProvider().complete(_make_request())
        assert result.usage is None


# ---------------------------------------------------------------------------
# LiteLLMProvider.complete — error mapping
# ---------------------------------------------------------------------------


class TestLiteLLMProviderErrors:
    @pytest.mark.asyncio
    async def test_authentication_error_raises_provider_error(self) -> None:
        import litellm

        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(
                side_effect=litellm.AuthenticationError(
                    "bad key", llm_provider="openai", model="gpt-4o"
                )
            ),
        ):
            with pytest.raises(ProviderError, match="Authentication failed"):
                await LiteLLMProvider().complete(_make_request())

    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_provider_error(self) -> None:
        import litellm

        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(
                side_effect=litellm.RateLimitError(
                    "rate limit", llm_provider="openai", model="gpt-4o"
                )
            ),
        ):
            with pytest.raises(ProviderError, match="Rate limit exceeded"):
                await LiteLLMProvider().complete(_make_request())

    @pytest.mark.asyncio
    async def test_bad_request_error_raises_provider_error(self) -> None:
        import litellm

        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(
                side_effect=litellm.BadRequestError(
                    "bad request", llm_provider="openai", model="gpt-4o"
                )
            ),
        ):
            with pytest.raises(ProviderError, match="Bad request"):
                await LiteLLMProvider().complete(_make_request())

    @pytest.mark.asyncio
    async def test_generic_exception_raises_provider_error(self) -> None:
        with patch(
            "app.providers.litellm_provider.litellm.acompletion",
            new=AsyncMock(side_effect=RuntimeError("network timeout")),
        ):
            with pytest.raises(ProviderError, match="Provider call failed"):
                await LiteLLMProvider().complete(_make_request())


# ---------------------------------------------------------------------------
# LiteLLMProvider — provider_name
# ---------------------------------------------------------------------------


class TestLiteLLMProviderName:
    def test_provider_name(self) -> None:
        assert LiteLLMProvider().provider_name == "litellm"


# ---------------------------------------------------------------------------
# ProviderFactory
# ---------------------------------------------------------------------------


class TestProviderFactory:
    def test_openai_returns_litellm_provider(self) -> None:
        factory = ProviderFactory()
        provider = factory.get_provider("openai/gpt-4o")
        assert isinstance(provider, LiteLLMProvider)


class TestProviderOrchestrator:
    @pytest.mark.asyncio
    async def test_fails_over_for_recoverable_errors(self) -> None:
        factory = MagicMock()
        first_provider = AsyncMock()
        first_provider.complete.side_effect = ProviderError("Rate limit exceeded")
        second_provider = AsyncMock()
        second_provider.complete.return_value = ProviderResponse(
            content="fallback response",
            model="gemini/gemini-2.5-flash",
            provider="gemini",
        )
        factory.get_provider.side_effect = [first_provider, second_provider]

        orchestrator = ProviderOrchestrator(factory)
        result = await orchestrator.execute(
            _make_request(),
            [{"model": "openai/gpt-4o"}, {"model": "gemini/gemini-2.5-flash"}],
        )

        assert result.content == "fallback response"
        assert first_provider.complete.await_count == 1
        assert second_provider.complete.await_count == 1

    @pytest.mark.asyncio
    async def test_stops_immediately_for_non_recoverable_errors(self) -> None:
        factory = MagicMock()
        first_provider = AsyncMock()
        first_provider.complete.side_effect = ProviderError("Authentication failed")
        second_provider = AsyncMock()
        second_provider.complete.return_value = ProviderResponse(
            content="should not be used",
            model="gemini/gemini-2.5-flash",
            provider="gemini",
        )
        factory.get_provider.side_effect = [first_provider, second_provider]

        orchestrator = ProviderOrchestrator(factory)

        with pytest.raises(ProviderError, match="non-recoverable"):
            await orchestrator.execute(
                _make_request(),
                [{"model": "openai/gpt-4o"}, {"model": "gemini/gemini-2.5-flash"}],
            )

        assert first_provider.complete.await_count == 1
        assert second_provider.complete.await_count == 0

    @pytest.mark.asyncio
    async def test_raises_aggregated_error_when_all_fail(self) -> None:
        factory = MagicMock()
        first_provider = AsyncMock()
        first_provider.complete.side_effect = ProviderError("timeout exceeded")
        second_provider = AsyncMock()
        second_provider.complete.side_effect = ProviderError("temporary network error")
        factory.get_provider.side_effect = [first_provider, second_provider]

        orchestrator = ProviderOrchestrator(factory)

        with pytest.raises(ProviderError, match="All providers failed"):
            await orchestrator.execute(
                _make_request(),
                [{"model": "openai/gpt-4o"}, {"model": "gemini/gemini-2.5-flash"}],
            )

    def test_anthropic_returns_litellm_provider(self) -> None:
        provider = ProviderFactory().get_provider(
            "anthropic/claude-3-5-sonnet-20241022"
        )
        assert isinstance(provider, LiteLLMProvider)

    def test_gemini_returns_litellm_provider(self) -> None:
        provider = ProviderFactory().get_provider("gemini/gemini-1.5-pro")
        assert isinstance(provider, LiteLLMProvider)

    def test_ollama_returns_litellm_provider(self) -> None:
        provider = ProviderFactory().get_provider("ollama/llama3")
        assert isinstance(provider, LiteLLMProvider)

    def test_unknown_prefix_raises_provider_not_found(self) -> None:
        with pytest.raises(ProviderNotFoundError, match="No provider registered"):
            ProviderFactory().get_provider("unknownvendor/some-model")

    def test_singleton_same_instance_returned(self) -> None:
        factory = ProviderFactory()
        assert factory.get_provider("openai/gpt-4o") is factory.get_provider(
            "anthropic/claude-3-5-sonnet-20241022"
        )

    def test_model_without_prefix_routes_to_litellm(self) -> None:
        """Bare model names (no slash) default to openai prefix logic."""
        provider = ProviderFactory().get_provider("gpt-4o")
        assert isinstance(provider, LiteLLMProvider)
