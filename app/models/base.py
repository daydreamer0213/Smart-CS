"""SQLAlchemy declarative base and shared mixin."""

import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.orm import declarative_base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


Base = declarative_base()


class TimestampMixin:
    """Shared columns for all business models."""

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
