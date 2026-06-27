"""Chat router — primary LLM request endpoint."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_di_container, get_request_id_header
from app.schemas.requests import ChatRequest
from app.schemas.responses import ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    request_id: str = Depends(get_request_id_header),
    container=Depends(get_di_container),
) -> ChatResponse:
    """Process a prompt through input guardrails → LLM → output guardrails."""
    return await container.gateway_service.chat(request, request_id)
