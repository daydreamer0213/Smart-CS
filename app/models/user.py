"""User model for JWT authentication."""

from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200), default="", nullable=False)
    role = Column(String(20), default="agent", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    tenant = relationship("Tenant")
