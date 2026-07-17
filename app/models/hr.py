"""Tenant-scoped HR support handoff persistence models."""

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text

from app.models.base import Base, TimestampMixin


class HandoffDraft(Base, TimestampMixin):
    __tablename__ = "hr_handoff_drafts"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    requester_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    sources_json = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class SupportHandoff(Base, TimestampMixin):
    __tablename__ = "hr_support_handoffs"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    requester_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    assigned_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    question = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    sources_json = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="open", index=True)
    resolution_note = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
