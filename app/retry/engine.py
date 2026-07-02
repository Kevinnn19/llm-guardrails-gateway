"""RetryEngine — orchestrates the correct-and-retry loop.

Responsibilities:
  1. Accept a failed ValidationResult from GatewayService.
  2. Build a corrected prompt via PromptCorrector.
  3. Call the LLM provider again.
  4. Re-validate the new response.
  5. Repeat up to max_attempts.
  6. If all attempts fail, return the fallback message from the policy.

The RetryEngine is intentionally stateless — all context is passed in on
each call. This makes it trivially testable and safe to use as a singleton.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import MaxRetriesExceededError
from app.core.logging import logger
from app.guardrails.result import ValidationResult
from app.policies.models import Policy
from app.providers.base import AbstractLLMProvider
from app.providers.models import Message, ProviderRequest, ProviderResponse
from app.retry.prompt_corrector import PromptCorrector
from app.services.output_validation import OutputValidationService
from app.services.validation import ValidationService


@dataclass
class RetryContext:
    """Carries the state of a single retry session."""

    prompt: str
    policy: Policy
    conversation_history: list[Message] = field(default_factory=list)
    attempts: int = 0
    last_response: ProviderResponse | None = None
    all_violations: list[Any] = field(default_factory=list)


class RetryEngine:
    """Orchestrates the correct-and-retry loop for failed validations."""

    def __init__(
        self,
        corrector: PromptCorrector,
        input_validator: ValidationService,
        output_validator: OutputValidationService,
    ) -> None:
        self._corrector = corrector
        self._input_validator = input_validator
        self._output_validator = output_validator

    async def run(
        self,
        ctx: RetryContext,
        provider: AbstractLLMProvider,
    ) -> tuple[ProviderResponse, ValidationResult, int]:
        """Run the retry loop until success or max_attempts is exhausted.

        Args:
            ctx:      RetryContext with prompt, policy, and history.
            provider: LLM provider to call.

        Returns:
            (final_response, final_output_result, attempts_used)

        Raises:
            MaxRetriesExceededError: if all attempts fail and strategy is
                                     not static_fallback (fallback is handled
                                     by GatewayService).
        """
        policy = ctx.policy
        max_attempts: int = policy.retry.max_attempts
        current_prompt = ctx.prompt

        for attempt in range(1, max_attempts + 1):
            ctx.attempts = attempt
            logger.info("retry_attempt attempt={} max={}", attempt, max_attempts)

            # Build messages
            messages = [*ctx.conversation_history, Message(role="user", content=current_prompt)]

            # Call provider
            request = ProviderRequest(
                model=policy.litellm_model(),
                messages=messages,
                timeout_seconds=policy.provider.timeout_seconds,
            )
            response = await provider.complete(request=request)
            ctx.last_response = response

            # Validate output
            output_result = self._output_validator.validate_with_policy(
                response.content, policy, prompt=ctx.prompt
            )

            if output_result.passed:
                logger.info("retry_succeeded attempt={}", attempt)
                return response, output_result, attempt

            ctx.all_violations.extend(output_result.violations)
            logger.warning(
                "retry_output_failed attempt={} violations={}",
                attempt,
                [v.code for v in output_result.violations],
            )

            if attempt < max_attempts:
                current_prompt = self._corrector.build_correction(
                    ctx.prompt, output_result.violations, attempt=attempt + 1
                )

        # All attempts exhausted
        raise MaxRetriesExceededError(
            f"Output validation failed after {max_attempts} attempt(s)"
        )
