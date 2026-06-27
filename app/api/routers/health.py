"""Health check router."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_di_container
from app.core.config import get_settings
from app.schemas.responses import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(container=Depends(get_di_container)) -> HealthResponse:
    """Liveness probe — returns app version and loaded policies."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        policies_loaded=container.policy_service.policy_ids(),
    )
