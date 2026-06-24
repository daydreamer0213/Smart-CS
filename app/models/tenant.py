"""Tenant and admin API key models."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    config_json = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)


class AdminApiKey(Base, TimestampMixin):
    __tablename__ = "admin_api_keys"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    key_hash = Column(String(128), unique=True, nullable=False)
    label = Column(String(200), default="")
    last_used_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant")
