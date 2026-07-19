"""Document and DocumentChunk models — uploaded files with chunk-level storage."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class DocumentFamily(Base, TimestampMixin):
    """Stable identity for all versions and index generations of one policy."""

    __tablename__ = "document_families"

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    current_document_id = Column(String(36), nullable=True, index=True)

    tenant = relationship("Tenant")
    documents = relationship("Document", back_populates="family")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "family_id",
            "version",
            "index_generation",
            name="uq_documents_family_version_generation",
        ),
    )

    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    family_id = Column(
        String(36), ForeignKey("document_families.id"), nullable=True, index=True
    )
    filename = Column(String(500), nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size = Column(Integer, default=0)
    file_hash = Column(String(64), nullable=False, index=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="processing", nullable=False)
    error_message = Column(String(500), nullable=True)
    audience_roles = Column(JSON, default=list, nullable=False)
    parser_name = Column(String(100), nullable=True)
    parser_version = Column(String(100), nullable=True)
    page_count = Column(Integer, nullable=True)
    parse_quality_status = Column(String(20), nullable=True)
    parse_quality_details = Column(JSON, nullable=True)
    version = Column(Integer, default=1, server_default="1", nullable=False)
    index_generation = Column(Integer, default=1, server_default="1", nullable=False)
    review_status = Column(
        String(20), default="approved", server_default="approved", nullable=False
    )
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    source_type = Column(
        String(30), default="upload", server_default="upload", nullable=False
    )
    source_ref = Column(String(500), nullable=True)
    storage_key = Column(String(1000), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    chunker_version = Column(String(100), nullable=True)
    embedding_provider = Column(String(100), nullable=True)
    embedding_model = Column(String(200), nullable=True)

    tenant = relationship("Tenant")
    family = relationship("DocumentFamily", back_populates="documents")
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
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section_path = Column(JSON, nullable=True)
    element_types = Column(JSON, nullable=True)
    source_element_indexes = Column(JSON, nullable=True)
    index_generation = Column(Integer, default=1, server_default="1", nullable=False)
    chunker_version = Column(String(100), nullable=True)
    embedding_model = Column(String(200), nullable=True)

    document = relationship("Document", back_populates="chunks")
