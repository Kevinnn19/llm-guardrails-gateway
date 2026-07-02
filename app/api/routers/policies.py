"""Policy management endpoints."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_di_container, get_request_id_header
from app.core.container import Container
from app.schemas.requests import ReloadPolicyRequest
from app.schemas.responses import PoliciesResponse, PolicySummary, ReloadPolicyResponse

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=PoliciesResponse)
async def list_policies(
    request_id: str = Depends(get_request_id_header),
    container: Container = Depends(get_di_container),
) -> PoliciesResponse:
    """List all loaded policies and their active guardrail configuration."""
    policies = container.policy_service.list_all()
    return PoliciesResponse(
        policies=[
            PolicySummary(
                id=p.id,
                version=p.version,
                provider=p.litellm_model(),
                input_guardrails_enabled=p.enabled_input_guardrails(),
                output_guardrails_enabled=p.enabled_output_guardrails(),
            )
            for p in policies
        ]
    )


@router.post("/reload", response_model=ReloadPolicyResponse)
async def reload_policy(
    request: ReloadPolicyRequest,
    request_id: str = Depends(get_request_id_header),
    container: Container = Depends(get_di_container),
) -> ReloadPolicyResponse:
    """Trigger hot-reload of one or all policy files from disk."""
    svc = container.policy_service
    if request.policy_id:
        svc.reload_one(request.policy_id)
        return ReloadPolicyResponse(reloaded=[request.policy_id])
    loaded, errors = svc.reload_all()
    return ReloadPolicyResponse(reloaded=loaded, errors=errors)
