"""Loguru-based structured logging configuration."""

import sys
from contextvars import ContextVar

import loguru
from loguru import logger

from app.core.config import get_settings

# Per-request context propagated through the call stack
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def _formatter(record: dict) -> str:
    record["extra"].setdefault("request_id", get_request_id())
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
        "req={extra[request_id]} | "
        "<level>{message}</level>\n{exception}"
    )


def setup_logging() -> None:
    """Configure Loguru for structured console output."""
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        format=_formatter,
        level=settings.log_level.upper(),
        colorize=True,
        backtrace=settings.debug,
        diagnose=settings.debug,
        enqueue=True,  # thread-safe async logging
    )


__all__ = ["get_request_id", "logger", "set_request_id", "setup_logging"]
