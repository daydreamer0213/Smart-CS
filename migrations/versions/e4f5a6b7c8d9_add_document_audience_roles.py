"""add document audience roles

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_audience_roles() -> None:
    op.add_column(
        "documents",
        sa.Column("audience_roles", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def _create_documents() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "audience_roles",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])


def _create_document_chunks() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_id", sa.String(length=200), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def upgrade() -> None:
    if context.is_offline_mode():
        # Offline SQL targets the normal legacy database with document tables already present.
        _add_audience_roles()
        return

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("documents"):
        if "audience_roles" not in {
            column["name"] for column in inspector.get_columns("documents")
        }:
            _add_audience_roles()
    else:
        _create_documents()

    if not inspector.has_table("document_chunks"):
        _create_document_chunks()


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_column("documents", "audience_roles")
        return

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("documents") and "audience_roles" in {
        column["name"] for column in inspector.get_columns("documents")
    }:
        op.drop_column("documents", "audience_roles")
    # Retain document tables: this revision repairs their missing legacy baseline.
