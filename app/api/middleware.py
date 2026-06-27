"""Request/response middleware: timing, request-id propagation, error normalisation."""

import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.exceptions import GatewayError
from app.core.logging import logger, set_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request_id and log every request with latency."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(request_id)
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "Unhandled exception path={} latency_ms={:.1f} error={}",
                request.url.path,
                latency_ms,
                exc,
            )
            raise

        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "method={} path={} status={} latency_ms={:.1f}",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Latency-Ms"] = f"{latency_ms:.1f}"
        return response


class GatewayErrorMiddleware(BaseHTTPMiddleware):
    """Convert GatewayError domain exceptions to structured JSON responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except GatewayError as exc:
            return JSONResponse(
                status_code=exc.http_status,
                content={
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request.headers.get("X-Request-ID", "-"),
                },
            )
        except NotImplementedError as exc:
            return JSONResponse(
                status_code=501,
                content={
                    "code": "not_implemented",
                    "message": str(exc),
                    "request_id": request.headers.get("X-Request-ID", "-"),
                },
            )
