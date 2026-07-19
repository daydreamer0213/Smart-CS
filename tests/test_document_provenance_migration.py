from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "e4f5a6b7c8d9"


def _config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_provenance_upgrade_and_downgrade_preserve_legacy_rows(tmp_path):
    database_path = tmp_path / "provenance.db"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO tenants (id, slug, name, config_json, is_active) "
            "VALUES ('tenant-1', 'tenant-one', 'Tenant One', '{}', 1)"
        ))
        connection.execute(sa.text(
            "INSERT INTO documents "
            "(id, tenant_id, filename, file_type, file_hash, status) "
            "VALUES ('document-1', 'tenant-1', 'legacy.txt', 'txt', 'legacy-hash', 'ready')"
        ))
        connection.execute(sa.text(
            "INSERT INTO document_chunks (id, document_id, chunk_index, content, status) "
            "VALUES ('chunk-1', 'document-1', 1, 'legacy content', 'active')"
        ))

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    document_columns = {
        column["name"]: column for column in inspector.get_columns("documents")
    }
    chunk_columns = {
        column["name"]: column
        for column in inspector.get_columns("document_chunks")
    }
    assert {
        "parser_name",
        "parser_version",
        "page_count",
        "parse_quality_status",
        "parse_quality_details",
    } <= set(document_columns)
    assert {
        "page_start",
        "page_end",
        "section_path",
        "element_types",
        "source_element_indexes",
    } <= set(chunk_columns)
    assert all(
        document_columns[name]["nullable"]
        for name in (
            "parser_name",
            "parser_version",
            "page_count",
            "parse_quality_status",
            "parse_quality_details",
        )
    )
    assert all(
        chunk_columns[name]["nullable"]
        for name in (
            "page_start",
            "page_end",
            "section_path",
            "element_types",
            "source_element_indexes",
        )
    )

    with engine.connect() as connection:
        document = connection.execute(sa.text(
            "SELECT filename, parse_quality_status FROM documents "
            "WHERE id = 'document-1'"
        )).one()
        chunk = connection.execute(sa.text(
            "SELECT content, page_start FROM document_chunks WHERE id = 'chunk-1'"
        )).one()
    assert document.filename == "legacy.txt"
    assert document.parse_quality_status is None
    assert chunk.content == "legacy content"
    assert chunk.page_start is None

    command.downgrade(config, PREVIOUS_REVISION)

    inspector = sa.inspect(engine)
    assert "parser_name" not in {
        column["name"] for column in inspector.get_columns("documents")
    }
    assert "page_start" not in {
        column["name"] for column in inspector.get_columns("document_chunks")
    }
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            "SELECT filename FROM documents WHERE id = 'document-1'"
        )).scalar_one() == "legacy.txt"
        assert connection.execute(sa.text(
            "SELECT content FROM document_chunks WHERE id = 'chunk-1'"
        )).scalar_one() == "legacy content"


def test_provenance_migration_tolerates_missing_document_tables(tmp_path):
    database_path = tmp_path / "missing-tables.db"
    config = _config(database_path)

    command.stamp(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
