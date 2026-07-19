"""add document parse provenance

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOCUMENT_COLUMNS = (
    sa.Column("parser_name", sa.String(length=100), nullable=True),
    sa.Column("parser_version", sa.String(length=100), nullable=True),
    sa.Column("page_count", sa.Integer(), nullable=True),
    sa.Column("parse_quality_status", sa.String(length=20), nullable=True),
    sa.Column("parse_quality_details", sa.JSON(), nullable=True),
)
CHUNK_COLUMNS = (
    sa.Column("page_start", sa.Integer(), nullable=True),
    sa.Column("page_end", sa.Integer(), nullable=True),
    sa.Column("section_path", sa.JSON(), nullable=True),
    sa.Column("element_types", sa.JSON(), nullable=True),
    sa.Column("source_element_indexes", sa.JSON(), nullable=True),
)


def _add_missing_columns(table_name: str, columns: tuple[sa.Column, ...]) -> None:
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def upgrade() -> None:
    if context.is_offline_mode():
        for column in DOCUMENT_COLUMNS:
            op.add_column("documents", column)
        for column in CHUNK_COLUMNS:
            op.add_column("document_chunks", column)
        return

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("documents"):
        _add_missing_columns("documents", DOCUMENT_COLUMNS)
    if inspector.has_table("document_chunks"):
        _add_missing_columns("document_chunks", CHUNK_COLUMNS)


def downgrade() -> None:
    if context.is_offline_mode():
        for column in reversed(CHUNK_COLUMNS):
            op.drop_column("document_chunks", column.name)
        for column in reversed(DOCUMENT_COLUMNS):
            op.drop_column("documents", column.name)
        return

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("document_chunks"):
        existing = {
            column["name"] for column in inspector.get_columns("document_chunks")
        }
        for column in reversed(CHUNK_COLUMNS):
            if column.name in existing:
                op.drop_column("document_chunks", column.name)
    if inspector.has_table("documents"):
        existing = {
            column["name"] for column in inspector.get_columns("documents")
        }
        for column in reversed(DOCUMENT_COLUMNS):
            if column.name in existing:
                op.drop_column("documents", column.name)
