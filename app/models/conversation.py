"""Conversation session and message models."""

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    visitor_id = Column(String(100), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    message_count = Column(Integer, default=0)

    tenant = relationship("Tenant")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    conversation_id = Column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    cache_hit = Column(String(10), nullable=True)
    sources_json = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    conversation = relationship("Conversation")
