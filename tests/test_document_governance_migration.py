from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "f6a7b8c9d0e1"


def _config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _seed_legacy_documents(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO tenants (id, slug, name, config_json, is_active) "
            "VALUES ('tenant-1', 'tenant-one', 'Tenant One', '{}', 1)"
        ))
        connection.execute(sa.text(
            "INSERT INTO documents "
            "(id, tenant_id, filename, file_type, file_hash, status) VALUES "
            "('ready-doc', 'tenant-1', 'leave-policy.pdf', 'pdf', 'ready-hash', 'ready'), "
            "('failed-doc', 'tenant-1', 'broken-policy.pdf', 'pdf', 'failed-hash', 'failed')"
        ))
        connection.execute(sa.text(
            "INSERT INTO document_chunks "
            "(id, document_id, chunk_index, content, status) VALUES "
            "('ready-chunk', 'ready-doc', 1, 'leave policy', 'active')"
        ))


def test_governance_upgrade_backfills_legacy_lifecycle_and_lineage(tmp_path):
    database_path = tmp_path / "governance.db"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    _seed_legacy_documents(engine)

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert "document_families" in inspector.get_table_names()
    document_columns = {
        column["name"] for column in inspector.get_columns("documents")
    }
    assert {
        "family_id",
        "version",
        "index_generation",
        "review_status",
        "effective_date",
        "expiry_date",
        "source_type",
        "source_ref",
        "storage_key",
        "owner_user_id",
        "reviewed_by_user_id",
        "reviewed_at",
        "chunker_version",
        "embedding_provider",
        "embedding_model",
    } <= document_columns
    chunk_columns = {
        column["name"] for column in inspector.get_columns("document_chunks")
    }
    assert {"index_generation", "chunker_version", "embedding_model"} <= chunk_columns

    with engine.connect() as connection:
        documents = connection.execute(sa.text(
            "SELECT id, family_id, version, index_generation, review_status "
            "FROM documents ORDER BY id"
        )).mappings().all()
        families = connection.execute(sa.text(
            "SELECT id, name, current_document_id FROM document_families ORDER BY id"
        )).mappings().all()
        chunk = connection.execute(sa.text(
            "SELECT index_generation, chunker_version, embedding_model "
            "FROM document_chunks WHERE id='ready-chunk'"
        )).mappings().one()

    assert documents == [
        {
            "id": "failed-doc",
            "family_id": "failed-doc",
            "version": 1,
            "index_generation": 1,
            "review_status": "pending_review",
        },
        {
            "id": "ready-doc",
            "family_id": "ready-doc",
            "version": 1,
            "index_generation": 1,
            "review_status": "approved",
        },
    ]
    assert families == [
        {
            "id": "failed-doc",
            "name": "broken-policy.pdf",
            "current_document_id": None,
        },
        {
            "id": "ready-doc",
            "name": "leave-policy.pdf",
            "current_document_id": "ready-doc",
        },
    ]
    assert chunk == {
        "index_generation": 1,
        "chunker_version": None,
        "embedding_model": None,
    }


def test_governance_downgrade_preserves_legacy_documents(tmp_path):
    database_path = tmp_path / "governance-downgrade.db"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    _seed_legacy_documents(engine)
    command.upgrade(config, "head")

    command.downgrade(config, PREVIOUS_REVISION)

    inspector = sa.inspect(engine)
    assert "document_families" not in inspector.get_table_names()
    assert "family_id" not in {
        column["name"] for column in inspector.get_columns("documents")
    }
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            "SELECT filename FROM documents WHERE id='ready-doc'"
        )).scalar_one() == "leave-policy.pdf"
        assert connection.execute(sa.text(
            "SELECT content FROM document_chunks WHERE id='ready-chunk'"
        )).scalar_one() == "leave policy"


def test_governance_migration_tolerates_missing_document_tables(tmp_path):
    database_path = tmp_path / "missing-tables.db"
    config = _config(database_path)
    command.stamp(config, PREVIOUS_REVISION)

    command.upgrade(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
