"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import GatewayErrorMiddleware, RequestContextMiddleware
from app.api.routers import chat, health, policies, validation
from app.core.config import get_settings
from app.core.container import init_container
from app.core.logging import logger, setup_logging


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    setup_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        container = init_container()
        logger.info("Gateway started version={}", settings.app_version)
        yield
        container.shutdown()
        logger.info("Gateway shutting down")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware — order matters: outermost runs first on request, last on response
    app.add_middleware(GatewayErrorMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(validation.router)
    app.include_router(policies.router)

    return app


app = create_app()
