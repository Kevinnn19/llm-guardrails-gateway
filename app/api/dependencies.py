"""FastAPI dependency providers injected into route handlers via Depends()."""

import uuid

from fastapi import Request

from app.core.container import Container, get_container
from app.core.logging import set_request_id


def get_request_id_header(request: Request) -> str:
    """Extract or generate a request ID and bind it to the logging context."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)
    return request_id


def get_di_container() -> Container:
    """Provide the DI container to route handlers."""
    return get_container()
