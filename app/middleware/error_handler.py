"""Global exception handler — converts all unhandled exceptions to JSON error format."""

import structlog

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware.logging import request_id_var

logger = structlog.get_logger()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": "HTTP_ERROR", "message": exc.detail},
                "request_id": request_id_var.get(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = request_id_var.get()
        logger.error(
            "unhandled_exception",
            request_id=rid,
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
                "request_id": rid,
            },
        )
