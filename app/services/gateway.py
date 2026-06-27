"""GatewayService — orchestrates the full /chat request lifecycle.

Flow:
  1. Resolve policy (from request or default).
  2. Run input guardrails with policy config.
  3. If input fails and action==block: return fallback or raise.
  4. Call LLM provider.
  5. Run output guardrails with policy config.
  6. If output fails: hand off to RetryEngine.
  7. If RetryEngine exhausts attempts: return fallback response.
  8. Return final ChatResponse with risk score, violations, latency, retries.
"""

import time
from dataclasses import dataclass

from app.core.exceptions import MaxRetriesExceededError
from app.core.logging import logger
from app.guardrails.result import Violation
from app.policies.models import Policy
from app.providers.base import AbstractLLMProvider
from app.providers.factory import ProviderFactory
from app.providers.models import Message, ProviderRequest, ProviderResponse
from app.retry.engine import RetryContext, RetryEngine
from app.retry.prompt_corrector import PromptCorrector
from app.schemas.requests import ChatRequest
from app.schemas.responses import ChatResponse, ViolationDetail
from app.services.output_validation import OutputValidationService
from app.services.policy import PolicyService
from app.services.validation import ValidationService


def _to_violation_details(violations: list[Violation]) -> list[ViolationDetail]:
    return [
        ViolationDetail(
            guardrail=v.guardrail,
            code=v.code,
            message=v.message,
            severity=v.severity,
            score=v.score,
        )
        for v in violations
    ]


class GatewayService:
    """Orchestrates input validation → LLM call → output validation → retry."""

    def __init__(
        self,
        policy_service: PolicyService,
        provider_factory: ProviderFactory,
        input_validator: ValidationService,
        output_validator: OutputValidationService,
    ) -> None:
        self._policy_service = policy_service
        self._provider_factory = provider_factory
        self._input_validator = input_validator
        self._output_validator = output_validator
        self._corrector = PromptCorrector()
        self._retry_engine = RetryEngine(
            corrector=self._corrector,
            input_validator=input_validator,
            output_validator=output_validator,
        )

    async def chat(self, request: ChatRequest, request_id: str) -> ChatResponse:
        """Process a /chat request end-to-end."""
        start = time.perf_counter()

        # 1. Resolve policy
        policy = self._policy_service.get(request.policy_id)

        # 2. Override model/provider from request if provided
        if request.model:
            # Shallow copy with model override — avoid mutating the cached policy
            from copy import deepcopy
            from app.policies.models import ProviderConfig
            policy = policy.model_copy(
                update={"provider": ProviderConfig(
                    name=request.provider or policy.provider.name,
                    model=request.model,
                    timeout_seconds=policy.provider.timeout_seconds,
                )}
            )

        # 3. Input validation
        input_result = self._input_validator.validate_with_policy(request.prompt, policy)
        all_violations: list[Violation] = list(input_result.violations)

        if not input_result.passed:
            action = policy.input_guardrails.prompt_injection.action  # representative
            logger.warning(
                "input_validation_failed request_id={} violations={}",
                request_id,
                [v.code for v in input_result.violations],
            )
            if action == "block":
                latency_ms = (time.perf_counter() - start) * 1000
                return ChatResponse(
                    request_id=request_id,
                    response=policy.retry.fallback_message,
                    provider=policy.provider.name,
                    model=policy.litellm_model(),
                    risk_score=input_result.risk_score,
                    violations=_to_violation_details(all_violations),
                    retries=0,
                    latency_ms=latency_ms,
                    input_valid=False,
                    output_valid=False,
                )
            # action == "warn" or "log" — continue with original prompt

        # 4. Build conversation messages
        history: list[Message] = [
            Message(role=m["role"], content=m["content"])
            for m in (request.context or [])
        ]

        # 5. First LLM call
        provider: AbstractLLMProvider = self._provider_factory.get_provider(
            policy.litellm_model()
        )
        provider_request = ProviderRequest(
            model=policy.litellm_model(),
            messages=history + [Message(role="user", content=request.prompt)],
            timeout_seconds=policy.provider.timeout_seconds,
        )
        logger.info("Provider request = {}", provider_request.model_dump())
        llm_response: ProviderResponse = await provider.complete(provider_request)

        # 6. Output validation
        output_result = self._output_validator.validate_with_policy(
            llm_response.content, policy, prompt=request.prompt
        )
        all_violations.extend(output_result.violations)
        retries_used = 0

        # 7. Retry if output failed
        if not output_result.passed and policy.retry.max_attempts > 0:
            ctx = RetryContext(
                prompt=request.prompt,
                policy=policy,
                conversation_history=history,
            )
            try:
                llm_response, output_result, retries_used = await self._retry_engine.run(
                    ctx, provider
                )
                all_violations = list(input_result.violations) + list(output_result.violations)
            except MaxRetriesExceededError:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "max_retries_exceeded request_id={} attempts={}",
                    request_id,
                    policy.retry.max_attempts,
                )
                return ChatResponse(
                    request_id=request_id,
                    response=policy.retry.fallback_message,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    risk_score=min(1.0, max((v.score for v in all_violations), default=0.0)),
                    violations=_to_violation_details(all_violations),
                    retries=policy.retry.max_attempts,
                    latency_ms=latency_ms,
                    input_valid=input_result.passed,
                    output_valid=False,
                )

        latency_ms = (time.perf_counter() - start) * 1000
        risk_score = (
            max((v.score for v in all_violations), default=0.0)
            if all_violations else 0.0
        )

        logger.info(
            "chat_complete request_id={} provider={} retries={} latency_ms={:.1f} risk={:.2f}",
            request_id,
            llm_response.provider,
            retries_used,
            latency_ms,
            risk_score,
        )

        return ChatResponse(
            request_id=request_id,
            response=llm_response.content,
            provider=llm_response.provider,
            model=llm_response.model,
            risk_score=risk_score,
            violations=_to_violation_details(all_violations),
            retries=retries_used,
            latency_ms=latency_ms,
            input_valid=input_result.passed,
            output_valid=output_result.passed,
        )
