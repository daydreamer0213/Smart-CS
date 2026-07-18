import io
import os
from pathlib import Path
import subprocess
import sys

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_REVISION = "d1e2f3a4b5c6"


def _alembic_config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_cli_upgrade_honors_database_url(tmp_path):
    target_db = tmp_path / "requested.db"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(PROJECT_ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite:///{target_db.as_posix()}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert target_db.exists()
    assert not (tmp_path / "smartcs.db").exists()


def _create_legacy_document_tables(
    engine: sa.Engine, include_document_chunks: bool = True
) -> None:
    metadata = sa.MetaData()
    sa.Table("tenants", metadata, autoload_with=engine)
    documents = sa.Table(
        "documents",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size", sa.Integer()),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("chunk_count", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(500)),
    )
    sa.Index("ix_documents_tenant_id", documents.c.tenant_id)
    sa.Index("ix_documents_file_hash", documents.c.file_hash)
    if include_document_chunks:
        document_chunks = sa.Table(
            "document_chunks",
            metadata,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("embedding_id", sa.String(200)),
            sa.Column("token_count", sa.Integer()),
            sa.Column("keywords", sa.Text()),
            sa.Column("status", sa.String(20), nullable=False),
        )
        sa.Index("ix_document_chunks_document_id", document_chunks.c.document_id)
    metadata.create_all(engine)


def test_upgrade_head_creates_document_tables_for_empty_database(tmp_path):
    database_path = tmp_path / "empty.db"

    command.upgrade(_alembic_config(database_path), "head")

    inspector = sa.inspect(sa.create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert {"documents", "document_chunks"} <= set(inspector.get_table_names())
    document_columns = {
        column["name"]: column for column in inspector.get_columns("documents")
    }
    chunk_columns = {
        column["name"]: column for column in inspector.get_columns("document_chunks")
    }
    assert {
        "id", "created_at", "updated_at", "tenant_id", "filename", "file_type",
        "file_size", "file_hash", "chunk_count", "status", "error_message",
        "audience_roles",
    } <= set(document_columns)
    assert {"id", "created_at", "updated_at", "document_id", "chunk_index", "content",
            "embedding_id", "token_count", "keywords", "status"} <= set(chunk_columns)
    assert document_columns["audience_roles"]["nullable"] is False
    assert document_columns["audience_roles"]["default"] == "'[]'"
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("documents")} == {"tenants"}
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("document_chunks")} == {"documents"}
    assert {index["name"] for index in inspector.get_indexes("documents")} >= {
        "ix_documents_tenant_id", "ix_documents_file_hash",
    }
    assert {index["name"] for index in inspector.get_indexes("document_chunks")} >= {
        "ix_document_chunks_document_id",
    }


def test_upgrade_head_preserves_legacy_document_rows(tmp_path):
    database_path = tmp_path / "legacy.db"
    config = _alembic_config(database_path)
    command.upgrade(config, LEGACY_REVISION)

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    _create_legacy_document_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO tenants (id, slug, name, config_json, is_active) "
                "VALUES (:id, :slug, :name, :config_json, :is_active)"
            ),
            {
                "id": "tenant-1",
                "slug": "tenant-one",
                "name": "Tenant One",
                "config_json": "{}",
                "is_active": True,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, tenant_id, filename, file_type, file_size, file_hash, chunk_count, status) "
                "VALUES (:id, :tenant_id, :filename, :file_type, :file_size, :file_hash, :chunk_count, :status)"
            ),
            {
                "id": "document-1",
                "tenant_id": "tenant-1",
                "filename": "policy.txt",
                "file_type": "txt",
                "file_size": 42,
                "file_hash": "legacy-document-hash",
                "chunk_count": 1,
                "status": "ready",
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO document_chunks (id, document_id, chunk_index, content, status) "
                "VALUES (:id, :document_id, :chunk_index, :content, :status)"
            ),
            {
                "id": "chunk-1",
                "document_id": "document-1",
                "chunk_index": 0,
                "content": "Legacy policy content",
                "status": "active",
            },
        )

    command.stamp(config, LEGACY_REVISION)
    command.upgrade(config, "head")

    metadata = sa.MetaData()
    documents = sa.Table("documents", metadata, autoload_with=engine)
    document_chunks = sa.Table("document_chunks", metadata, autoload_with=engine)
    with engine.connect() as connection:
        document = connection.execute(
            sa.select(documents).where(documents.c.id == "document-1")
        ).one()
        chunk = connection.execute(
            sa.select(document_chunks).where(document_chunks.c.id == "chunk-1")
        ).one()

    assert document._mapping["filename"] == "policy.txt"
    assert document._mapping["audience_roles"] == []
    assert chunk._mapping["content"] == "Legacy policy content"

    command.downgrade(config, LEGACY_REVISION)

    inspector = sa.inspect(engine)
    assert "audience_roles" not in {column["name"] for column in inspector.get_columns("documents")}
    with engine.connect() as connection:
        document = connection.execute(
            sa.text("SELECT filename FROM documents WHERE id = 'document-1'")
        ).one()
        chunk = connection.execute(
            sa.text("SELECT content FROM document_chunks WHERE id = 'chunk-1'")
        ).one()

    assert document.filename == "policy.txt"
    assert chunk.content == "Legacy policy content"


def test_upgrade_head_recovers_missing_document_chunks_from_partial_schema(tmp_path):
    database_path = tmp_path / "partial.db"
    config = _alembic_config(database_path)
    command.upgrade(config, LEGACY_REVISION)

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    _create_legacy_document_tables(engine, include_document_chunks=False)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO tenants (id, slug, name, config_json, is_active) "
                "VALUES ('tenant-2', 'tenant-two', 'Tenant Two', '{}', 1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, tenant_id, filename, file_type, file_hash, status) "
                "VALUES ('document-2', 'tenant-2', 'partial.txt', 'txt', 'partial-hash', 'ready')"
            )
        )

    command.stamp(config, LEGACY_REVISION)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert "document_chunks" in inspector.get_table_names()
    assert "audience_roles" in {
        column["name"] for column in inspector.get_columns("documents")
    }
    document = sa.Table("documents", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        audience_roles = connection.execute(
            sa.select(document.c.audience_roles).where(document.c.id == "document-2")
        ).scalar_one()

    assert audience_roles == []


def test_offline_upgrade_emits_legacy_document_add_column_sql(tmp_path):
    database_path = tmp_path / "offline.db"
    config = _alembic_config(database_path)
    output = io.StringIO()
    config.output_buffer = output

    command.upgrade(config, "head", sql=True)

    assert "ALTER TABLE documents ADD COLUMN audience_roles JSON DEFAULT '[]' NOT NULL" in output.getvalue()
