"""Failure-safe immutable document reindex tests."""

import hashlib
import pytest

from app.core.parsing.contracts import (
    KnowledgeChunk,
    ParsedDocument,
    ParsedElement,
    ParseQuality,
)
from app.models.document import Document, DocumentChunk, DocumentFamily


def _parsed(status="passed"):
    return ParsedDocument(
        parser_name="reindex-parser",
        parser_version="3.0",
        page_count=2,
        elements=[
            ParsedElement(
                text="Annual leave policy",
                element_type="paragraph",
                page_start=1,
                page_end=2,
                section_path=["HR", "Leave"],
            )
        ],
        quality=ParseQuality(
            status=status,
            metrics={"character_count": 19},
            warnings=[] if status == "passed" else ["missing_page_coverage"],
        ),
    )


def _chunks():
    return [
        KnowledgeChunk(
            content="Annual leave policy",
            contextualized_content="HR > Leave\n\nAnnual leave policy",
            page_start=1,
            page_end=2,
            section_path=["HR", "Leave"],
            element_types=["paragraph"],
            source_element_indexes=[0],
            token_count=6,
        )
    ]


def _current_snapshot(db, tenant_id):
    family = DocumentFamily(tenant_id=tenant_id, name="Annual leave policy")
    db.add(family)
    db.flush()
    document = Document(
        tenant_id=tenant_id,
        family_id=family.id,
        filename="annual-leave.txt",
        file_type="txt",
        file_size=19,
        file_hash=hashlib.sha256(b"source").hexdigest(),
        status="ready",
        parse_quality_status="passed",
        review_status="approved",
        version=2,
        index_generation=1,
        storage_key="tenant/reindex-source.txt",
        audience_roles=["employee"],
        source_type="upload",
        source_ref="annual-leave.txt",
        chunker_version="structured-v1",
        embedding_provider="test-provider",
        embedding_model="test-embedding",
    )
    db.add(document)
    db.flush()
    old_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Old annual leave policy",
        status="active",
        embedding_id="old-embedding",
        index_generation=1,
    )
    db.add(old_chunk)
    db.flush()
    family.current_document_id = document.id
    db.commit()
    return family, document, old_chunk


class _Embedding:
    def __init__(self, fail=False):
        self.fail = fail

    async def embed(self, _texts):
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[0.1, 0.2]]


class _Vector:
    def __init__(self, fail=False):
        self.fail = fail
        self.added = []
        self.deleted = []

    def add(self, _tenant, chunk_id, _embedding, metadata):
        self.added.append((chunk_id, metadata))
        if self.fail:
            raise RuntimeError("vector unavailable")

    def delete(self, _tenant, chunk_id):
        self.deleted.append(chunk_id)


class _Bm25:
    def __init__(self, fail=False):
        self.fail = fail
        self.added = []
        self.removed = []

    def add(self, _tenant, chunk_id, _content):
        self.added.append(chunk_id)
        if self.fail:
            raise RuntimeError("bm25 unavailable")

    def remove(self, _tenant, chunk_id):
        self.removed.append(chunk_id)


def _configure_success(monkeypatch, *, stage=None, quality="passed"):
    embedding = _Embedding(fail=stage == "embedding")
    vector = _Vector(fail=stage == "vector")
    bm25 = _Bm25(fail=stage == "bm25")
    monkeypatch.setattr(
        "app.services.document_service.read_original", lambda _key: b"source"
    )
    monkeypatch.setattr(
        "app.services.document_service.parse_structured_file",
        lambda *_args: _parsed(quality),
    )
    monkeypatch.setattr(
        "app.services.document_service.chunk_document", lambda *_args: _chunks()
    )
    monkeypatch.setattr(
        "app.services.document_service.get_embedding_provider", lambda: embedding
    )
    monkeypatch.setattr(
        "app.services.document_service.get_vector_store", lambda: vector
    )
    monkeypatch.setattr(
        "app.services.document_service.get_bm25_manager", lambda: bm25
    )
    monkeypatch.setattr("app.services.document_service.asyncio.sleep", _no_sleep)
    return vector, bm25


async def _no_sleep(_seconds):
    return None


async def test_reindex_creates_new_generation_then_switches_pointer(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import reindex_document

    family, current, old_chunk = _current_snapshot(db, test_tenant.id)
    vector, bm25 = _configure_success(monkeypatch)

    rebuilt = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )

    db.refresh(family)
    db.refresh(old_chunk)
    assert rebuilt.id != current.id
    assert (rebuilt.version, rebuilt.index_generation) == (2, 2)
    assert rebuilt.review_status == "approved"
    assert rebuilt.status == "ready"
    assert rebuilt.storage_key == current.storage_key
    assert rebuilt.audience_roles == ["employee"]
    assert family.current_document_id == rebuilt.id
    assert old_chunk.status == "inactive"
    new_chunk = db.query(DocumentChunk).filter_by(document_id=rebuilt.id).one()
    assert new_chunk.status == "active"
    assert new_chunk.index_generation == 2
    assert vector.added[0][1]["index_generation"] == 2
    assert old_chunk.id in vector.deleted
    assert old_chunk.id in bm25.removed


async def test_parse_failure_keeps_previous_generation_published(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import reindex_document

    family, current, old_chunk = _current_snapshot(db, test_tenant.id)
    monkeypatch.setattr(
        "app.services.document_service.read_original", lambda _key: b"source"
    )
    monkeypatch.setattr(
        "app.services.document_service.parse_structured_file",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("parser failed")),
    )

    rebuilt = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )

    db.refresh(family)
    db.refresh(old_chunk)
    assert rebuilt.status == "failed"
    assert rebuilt.index_generation == 2
    assert family.current_document_id == current.id
    assert old_chunk.status == "active"

    _configure_success(monkeypatch)
    retried = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )
    assert retried.index_generation == 3
    assert retried.status == "ready"


async def test_only_current_snapshot_can_be_reindexed(db, test_tenant):
    from app.services.document_service import (
        DocumentLifecycleError,
        reindex_document,
    )

    family, current, _ = _current_snapshot(db, test_tenant.id)
    old = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename=current.filename,
        file_type=current.file_type,
        file_hash=current.file_hash,
        status="ready",
        parse_quality_status="passed",
        review_status="approved",
        version=1,
        index_generation=1,
        storage_key=current.storage_key,
    )
    db.add(old)
    db.commit()

    with pytest.raises(DocumentLifecycleError, match="current"):
        await reindex_document(
            db,
            tenant_id=test_tenant.id,
            tenant_slug=test_tenant.slug,
            document_id=old.id,
            actor_user_id=None,
        )


async def test_original_integrity_failure_creates_no_generation(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import (
        DocumentLifecycleError,
        reindex_document,
    )

    _, current, _ = _current_snapshot(db, test_tenant.id)
    monkeypatch.setattr(
        "app.services.document_service.read_original", lambda _key: b"tampered"
    )
    before = db.query(Document).count()

    with pytest.raises(DocumentLifecycleError, match="integrity"):
        await reindex_document(
            db,
            tenant_id=test_tenant.id,
            tenant_slug=test_tenant.slug,
            document_id=current.id,
            actor_user_id=None,
        )

    assert db.query(Document).count() == before


async def test_concurrent_publication_prevents_late_reindex_overwrite(
    db, test_tenant, monkeypatch,
):
    from sqlalchemy.orm import Session
    from app.services.document_service import reindex_document

    family, current, old_chunk = _current_snapshot(db, test_tenant.id)
    competitor = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename=current.filename,
        file_type=current.file_type,
        file_hash=current.file_hash,
        status="ready",
        parse_quality_status="passed",
        review_status="approved",
        version=3,
        index_generation=1,
        storage_key=current.storage_key,
    )
    db.add(competitor)
    db.commit()
    vector = _Vector()

    class ConcurrentBm25(_Bm25):
        def add(self, tenant_slug, chunk_id, content):
            with Session(bind=db.get_bind()) as other:
                persisted_family = other.get(DocumentFamily, family.id)
                persisted_family.current_document_id = competitor.id
                other.commit()
            super().add(tenant_slug, chunk_id, content)

    bm25 = ConcurrentBm25()
    monkeypatch.setattr(
        "app.services.document_service.read_original", lambda _key: b"source"
    )
    monkeypatch.setattr(
        "app.services.document_service.parse_structured_file", lambda *_: _parsed()
    )
    monkeypatch.setattr(
        "app.services.document_service.chunk_document", lambda *_: _chunks()
    )
    monkeypatch.setattr(
        "app.services.document_service.get_embedding_provider", lambda: _Embedding()
    )
    monkeypatch.setattr(
        "app.services.document_service.get_vector_store", lambda: vector
    )
    monkeypatch.setattr(
        "app.services.document_service.get_bm25_manager", lambda: bm25
    )

    rebuilt = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )

    db.refresh(family)
    db.refresh(old_chunk)
    assert rebuilt.status == "failed"
    assert family.current_document_id == competitor.id
    assert old_chunk.status == "active"


async def test_review_required_reindex_keeps_previous_generation_published(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import reindex_document

    family, current, old_chunk = _current_snapshot(db, test_tenant.id)
    _configure_success(monkeypatch, quality="review_required")

    rebuilt = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )

    db.refresh(family)
    db.refresh(old_chunk)
    assert rebuilt.status == "review_required"
    assert family.current_document_id == current.id
    assert old_chunk.status == "active"


@pytest.mark.parametrize("stage", ["embedding", "vector", "bm25"])
async def test_index_failure_cleans_new_entries_and_keeps_old_pointer(
    db, test_tenant, monkeypatch, stage,
):
    from app.services.document_service import reindex_document

    family, current, old_chunk = _current_snapshot(db, test_tenant.id)
    vector, bm25 = _configure_success(monkeypatch, stage=stage)

    rebuilt = await reindex_document(
        db,
        tenant_id=test_tenant.id,
        tenant_slug=test_tenant.slug,
        document_id=current.id,
        actor_user_id=None,
    )

    db.refresh(family)
    db.refresh(old_chunk)
    new_chunk = db.query(DocumentChunk).filter_by(document_id=rebuilt.id).one()
    assert rebuilt.status == "failed"
    assert new_chunk.status == "inactive"
    assert family.current_document_id == current.id
    assert old_chunk.status == "active"
    if stage in {"vector", "bm25"}:
        assert new_chunk.id in vector.deleted
    if stage == "bm25":
        assert new_chunk.id in bm25.removed
