"""Validation endpoints for standalone input/output guardrail checks."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_di_container, get_request_id_header
from app.guardrails.base import GuardrailContext
from app.schemas.requests import ValidateInputRequest, ValidateOutputRequest
from app.schemas.responses import ValidationResponse, ViolationDetail

router = APIRouter(prefix="/validate", tags=["validation"])


def _to_response(result) -> ValidationResponse:  # type: ignore[no-untyped-def]
    return ValidationResponse(
        valid=result.passed,
        violations=[
            ViolationDetail(
                guardrail=v.guardrail,
                code=v.code,
                message=v.message,
                severity=v.severity,
                score=v.score,
            )
            for v in result.violations
        ],
        risk_score=result.risk_score,
    )


@router.post("/input", response_model=ValidationResponse)
async def validate_input(
    request: ValidateInputRequest,
    request_id: str = Depends(get_request_id_header),
    container=Depends(get_di_container),
) -> ValidationResponse:
    """Run input guardrails against a prompt without calling an LLM."""
    svc = container.input_validation_service
    if request.policy_id:
        policy = container.policy_service.get(request.policy_id)
        result = svc.validate_with_policy(request.prompt, policy)
    else:
        result = svc.validate(request.prompt, GuardrailContext())
    return _to_response(result)


@router.post("/output", response_model=ValidationResponse)
async def validate_output(
    request: ValidateOutputRequest,
    request_id: str = Depends(get_request_id_header),
    container=Depends(get_di_container),
) -> ValidationResponse:
    """Run output guardrails against an LLM response."""
    svc = container.output_validation_service
    prompt = request.prompt or ""

    if request.policy_id:
        policy = container.policy_service.get(request.policy_id)
        result = svc.validate_with_policy(request.response, policy, prompt=prompt)
    else:
        ctx = GuardrailContext()
        if request.expected_schema:
            ctx["schema"] = request.expected_schema
        result = svc.validate(request.response, prompt=prompt, context=ctx)

    return _to_response(result)
