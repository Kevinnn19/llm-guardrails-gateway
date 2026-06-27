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

from app.core.exceptions import MaxRetriesExceededError
from app.core.logging import logger
from app.guardrails.result import Violation
from app.providers.factory import ProviderFactory
from app.providers.models import Message, ProviderRequest, ProviderResponse
from app.providers.provider_orchestrator import ProviderOrchestrator
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


def _build_provider_metadata(
    provider_configs: list[dict[str, str | float | None]],
    provider_name: str,
) -> tuple[bool, int, list[str]]:
    provider_chain: list[str] = []
    for provider_config in provider_configs:
        model = provider_config.get("model")
        if isinstance(model, str) and model:
            provider_chain.append(model.split("/")[0] if "/" in model else model)

    if not provider_chain:
        return False, 0, []

    for index, attempted_provider in enumerate(provider_chain):
        if attempted_provider == provider_name:
            return index > 0, index + 1, provider_chain

    return len(provider_chain) > 1, len(provider_chain), provider_chain


class GatewayService:
    """Orchestrates input validation → LLM call → output validation → retry."""

    def __init__(
        self,
        policy_service: PolicyService,
        provider_factory: ProviderFactory | None = None,
        input_validator: ValidationService | None = None,
        output_validator: OutputValidationService | None = None,
        provider_orchestrator: ProviderOrchestrator | None = None,
    ) -> None:
        if input_validator is None or output_validator is None:
            raise ValueError("input_validator and output_validator are required")

        if provider_orchestrator is None:
            if provider_factory is None:
                raise ValueError("provider_factory or provider_orchestrator is required")
            provider_orchestrator = ProviderOrchestrator(provider_factory)

        self._policy_service = policy_service
        self._provider_factory = provider_factory
        self._provider_orchestrator = provider_orchestrator
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
            policy = policy.model_copy(
                update={
                    "provider": {
                        "primary": {
                            "name": request.provider or policy.provider.name,
                            "model": request.model,
                            "timeout_seconds": policy.provider.timeout_seconds,
                        },
                        "fallbacks": [
                            {"name": fallback.name, "model": fallback.model, "timeout_seconds": fallback.timeout_seconds}
                            for fallback in policy.provider.fallbacks
                        ],
                    }
                }
            )

        # 3. Input validation
        input_result = self._input_validator.validate_with_policy(
            request.prompt, policy
        )
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
                    fallback_used=False,
                    attempts=0,
                    provider_chain=[],
                    latency_ms=latency_ms,
                    input_valid=False,
                    output_valid=False,
                )
            # action == "warn" or "log" — continue with original prompt

        # 4. Build conversation messages
        history: list[Message] = [
            Message(role=m.role, content=m.content)
            for m in (request.context or [])
        ]

        # 5. First LLM call
        primary_model = policy.litellm_model()
        provider_configs = [{"model": primary_model}]
        for fallback in policy.provider.fallbacks:
            fallback_model = (
                fallback.model
                if "/" in fallback.model
                else f"{fallback.name}/{fallback.model}"
            )
            provider_configs.append({"model": fallback_model})

        provider_request = ProviderRequest(
            model=primary_model,
            messages=history + [Message(role="user", content=request.prompt)],
            timeout_seconds=policy.provider.timeout_seconds,
        )
        logger.info("Provider request = {}", provider_request.model_dump())
        provider = None
        llm_response: ProviderResponse = await self._provider_orchestrator.execute(
            provider_request,
            provider_configs,
        )
        fallback_used, attempts, provider_chain = _build_provider_metadata(
            list(provider_configs),
            llm_response.provider,
        )

        # 6. Output validation
        output_result = self._output_validator.validate_with_policy(
            llm_response.content, policy, prompt=request.prompt
        )
        all_violations.extend(output_result.violations)
        retries_used = 0

        # 7. Retry if output failed
        if not output_result.passed and policy.retry.max_attempts > 0:
            if provider is None and self._provider_factory is not None:
                provider = self._provider_factory.get_provider(primary_model)

            ctx = RetryContext(
                prompt=request.prompt,
                policy=policy,
                conversation_history=history,
            )
            try:
                (
                    llm_response,
                    output_result,
                    retries_used,
                ) = await self._retry_engine.run(ctx, provider)
                all_violations = list(input_result.violations) + list(
                    output_result.violations
                )
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
                    risk_score=min(
                        1.0, max((v.score for v in all_violations), default=0.0)
                    ),
                    violations=_to_violation_details(all_violations),
                    retries=policy.retry.max_attempts,
                    fallback_used=fallback_used,
                    attempts=attempts,
                    provider_chain=provider_chain,
                    latency_ms=latency_ms,
                    input_valid=input_result.passed,
                    output_valid=False,
                )

        latency_ms = (time.perf_counter() - start) * 1000
        risk_score = (
            max((v.score for v in all_violations), default=0.0)
            if all_violations
            else 0.0
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
            fallback_used=fallback_used,
            attempts=attempts,
            provider_chain=provider_chain,
            latency_ms=latency_ms,
            input_valid=input_result.passed,
            output_valid=output_result.passed,
        )
