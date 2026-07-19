"""add document governance lifecycle

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOCUMENT_COLUMNS = (
    sa.Column(
        "family_id",
        sa.String(length=36),
        sa.ForeignKey(
            "document_families.id",
            name="fk_documents_family_id_document_families",
        ),
        nullable=True,
    ),
    sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    sa.Column("index_generation", sa.Integer(), server_default="1", nullable=False),
    sa.Column(
        "review_status",
        sa.String(length=20),
        server_default="approved",
        nullable=False,
    ),
    sa.Column("effective_date", sa.Date(), nullable=True),
    sa.Column("expiry_date", sa.Date(), nullable=True),
    sa.Column(
        "source_type",
        sa.String(length=30),
        server_default="upload",
        nullable=False,
    ),
    sa.Column("source_ref", sa.String(length=500), nullable=True),
    sa.Column("storage_key", sa.String(length=1000), nullable=True),
    sa.Column(
        "owner_user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", name="fk_documents_owner_user_id_users"),
        nullable=True,
    ),
    sa.Column(
        "reviewed_by_user_id",
        sa.String(length=36),
        sa.ForeignKey("users.id", name="fk_documents_reviewed_by_user_id_users"),
        nullable=True,
    ),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("chunker_version", sa.String(length=100), nullable=True),
    sa.Column("embedding_provider", sa.String(length=100), nullable=True),
    sa.Column("embedding_model", sa.String(length=200), nullable=True),
)
CHUNK_COLUMNS = (
    sa.Column("index_generation", sa.Integer(), server_default="1", nullable=False),
    sa.Column("chunker_version", sa.String(length=100), nullable=True),
    sa.Column("embedding_model", sa.String(length=200), nullable=True),
)


def _create_family_table() -> None:
    op.create_table(
        "document_families",
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
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("current_document_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_families_tenant_id",
        "document_families",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_families_current_document_id",
        "document_families",
        ["current_document_id"],
    )


def _add_missing_columns(
    table_name: str,
    columns: tuple[sa.Column, ...],
    *,
    batch: bool = False,
) -> None:
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    missing = [column for column in columns if column.name not in existing]
    if batch and missing:
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            for column in missing:
                batch_op.add_column(column)
        return
    for column in missing:
        op.add_column(table_name, column)


def _without_foreign_keys(column: sa.Column) -> sa.Column:
    kwargs = {"nullable": column.nullable}
    if column.server_default is not None:
        kwargs["server_default"] = column.server_default.arg
    return sa.Column(column.name, column.type, **kwargs)


def _create_document_indexes() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes("documents")}
    if "ix_documents_family_id" not in existing:
        op.create_index("ix_documents_family_id", "documents", ["family_id"])
    if "uq_documents_family_version_generation" not in existing:
        op.create_index(
            "uq_documents_family_version_generation",
            "documents",
            ["family_id", "version", "index_generation"],
            unique=True,
        )


def _backfill_legacy_documents() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, tenant_id, filename, status FROM documents "
        "WHERE family_id IS NULL ORDER BY id"
    )).mappings()
    for row in rows:
        current_document_id = row["id"] if row["status"] == "ready" else None
        connection.execute(
            sa.text(
                "INSERT INTO document_families "
                "(id, tenant_id, name, current_document_id) "
                "VALUES (:id, :tenant_id, :name, :current_document_id)"
            ),
            {
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "name": row["filename"],
                "current_document_id": current_document_id,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE documents SET family_id=:family_id, version=1, "
                "index_generation=1, review_status=:review_status "
                "WHERE id=:document_id"
            ),
            {
                "family_id": row["id"],
                "review_status": (
                    "approved" if row["status"] == "ready" else "pending_review"
                ),
                "document_id": row["id"],
            },
        )


def upgrade() -> None:
    if context.is_offline_mode():
        _create_family_table()
        for column in DOCUMENT_COLUMNS:
            op.add_column("documents", _without_foreign_keys(column))
        for column in CHUNK_COLUMNS:
            op.add_column("document_chunks", column)
        op.create_index("ix_documents_family_id", "documents", ["family_id"])
        op.create_index(
            "uq_documents_family_version_generation",
            "documents",
            ["family_id", "version", "index_generation"],
            unique=True,
        )
        return

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("document_families"):
        _create_family_table()
    if inspector.has_table("documents"):
        _add_missing_columns("documents", DOCUMENT_COLUMNS, batch=True)
        _backfill_legacy_documents()
        _create_document_indexes()
    if inspector.has_table("document_chunks"):
        _add_missing_columns("document_chunks", CHUNK_COLUMNS)


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_index(
            "uq_documents_family_version_generation", table_name="documents"
        )
        op.drop_index("ix_documents_family_id", table_name="documents")
        for column in reversed(CHUNK_COLUMNS):
            op.drop_column("document_chunks", column.name)
        for column in reversed(DOCUMENT_COLUMNS):
            op.drop_column("documents", column.name)
        op.drop_table("document_families")
        return

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("documents"):
        indexes = {index["name"] for index in inspector.get_indexes("documents")}
        for name in (
            "uq_documents_family_version_generation",
            "ix_documents_family_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="documents")
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
        removable = [
            column for column in reversed(DOCUMENT_COLUMNS) if column.name in existing
        ]
        if removable:
            with op.batch_alter_table("documents", recreate="always") as batch_op:
                for column in removable:
                    batch_op.drop_column(column.name)
    if inspector.has_table("document_families"):
        op.drop_table("document_families")
