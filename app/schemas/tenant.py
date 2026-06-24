"""Tenant schemas — request/response models for tenant management.

Covers tenant creation/update payloads, admin API key management,
tenant configuration (intent keywords, model settings, branding),
and status/health response models.
"""

from pydantic import BaseModel


class TenantPlaceholder(BaseModel):
    """Placeholder — remove once real tenant schemas are defined."""
    pass
