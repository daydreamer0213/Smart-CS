"""Local CRM models used by the business-agent demo.

These tables intentionally model only the sales workflow demonstrated by the
application.  They are not a generic CRM or an integration layer.
"""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "normalized_name", name="uq_customer_tenant_name"),)

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), nullable=False)
    industry = Column(String(100), default="", nullable=False)
    level = Column(String(20), default="normal", nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(20), default="active", nullable=False)

    contacts = relationship("Contact", back_populates="customer", cascade="all, delete-orphan")
    opportunities = relationship("Opportunity", back_populates="customer")
    tasks = relationship("FollowUpTask", back_populates="customer")


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("customer_id", "email", name="uq_contact_customer_email"),)

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    title = Column(String(100), default="", nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), default="", nullable=False)

    customer = relationship("Customer", back_populates="contacts")


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_company", "contact_email", name="uq_lead_tenant_company_email"),
    )

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    company = Column(String(200), nullable=False)
    normalized_company = Column(String(200), nullable=False)
    contact_name = Column(String(100), nullable=False)
    contact_email = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    stage = Column(String(30), default="new", nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    amount_cents = Column(Integer, default=0, nullable=False)
    stage = Column(String(30), default="qualification", nullable=False)
    expected_close_date = Column(Date, nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    customer = relationship("Customer", back_populates="opportunities")


class FollowUpTask(Base, TimestampMixin):
    __tablename__ = "follow_up_tasks"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=True, index=True)
    opportunity_id = Column(String(36), ForeignKey("opportunities.id"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    due_date = Column(Date, nullable=False)
    assignee_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), default="open", nullable=False)

    customer = relationship("Customer", back_populates="tasks")


class ActionDraft(Base, TimestampMixin):
    __tablename__ = "action_drafts"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    params_json = Column(JSON, nullable=False)
    summary = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_audit_tenant_idempotency"),)

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=True, index=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False)
    error_code = Column(String(50), nullable=True)
    request_id = Column(String(100), nullable=True)
    idempotency_key = Column(String(100), nullable=True)
