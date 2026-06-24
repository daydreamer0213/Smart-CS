"""Tenant middleware — extracts tenant_slug from URL path and injects request.state.tenant."""

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.db import SessionLocal
from app.middleware.logging import request_id_var
from app.models.tenant import Tenant

_CHAT_PATH_RE = re.compile(r"^/api/v\d+/([^/]+)/(?:chat(?:/stream)?|health)$")
_ADMIN_PATH_RE = re.compile(r"^/api/v\d+/admin/([^/]+)/")


def _extract_slug(path: str) -> str | None:
    match = _ADMIN_PATH_RE.match(path)
    if match:
        return match.group(1)
    match = _CHAT_PATH_RE.match(path)
    if match:
        return match.group(1)
    return None


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        slug = _extract_slug(request.url.path)

        if slug is None:
            request.state.tenant = None
            return await call_next(request)

        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
            if tenant is None:
                rid = request_id_var.get()
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "TENANT_NOT_FOUND",
                            "message": f"Tenant '{slug}' does not exist",
                        },
                        "request_id": rid,
                    },
                )

            request.state.tenant = tenant
            response = await call_next(request)
            return response
        finally:
            db.close()
