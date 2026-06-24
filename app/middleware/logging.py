"""Structlog configuration and request-level logging middleware."""

import os
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

import logging
import logging.handlers

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_structlog(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    # JSON file handler for persistent structured logs
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "smartcs.jsonl",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    # Console handler for docker logs / dev
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)

        logger = structlog.get_logger()
        start = time.monotonic()
        logger.info(
            "request_started", method=request.method, path=request.url.path
        )

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )

        response.headers["X-Request-ID"] = rid
        return response
