"""Knowledge base models — FAQ items and categories."""

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    sort_order = Column(Integer, default=0)

    tenant = relationship("Tenant")


class KnowledgeItem(Base, TimestampMixin):
    __tablename__ = "knowledge_items"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    keywords = Column(Text, default="")
    embedding_id = Column(String(200), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    audience_roles = Column(JSON, default=list, nullable=False)

    tenant = relationship("Tenant")
    category = relationship("Category")
