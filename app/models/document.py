"""Document and DocumentChunk models — uploaded files with chunk-level storage."""

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size = Column(Integer, default=0)
    file_hash = Column(String(64), nullable=False, index=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="processing", nullable=False)
    error_message = Column(String(500), nullable=True)
    audience_roles = Column(JSON, default=list, nullable=False)

    tenant = relationship("Tenant")
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base, TimestampMixin):
    __tablename__ = "document_chunks"

    document_id = Column(
        String(36), ForeignKey("documents.id"), nullable=False, index=True
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(200), nullable=True)
    token_count = Column(Integer, default=0)
    keywords = Column(Text, default="")
    status = Column(String(20), default="active", nullable=False)

    document = relationship("Document", back_populates="chunks")
