"""Document service tests — upload, list, get, delete."""

import pytest

from app.core.parsing.contracts import (
    KnowledgeChunk,
    ParsedDocument,
    ParsedElement,
    ParseQuality,
)


class _FakeRetrieval:
    async def embed(self, texts):
        return [[0.0] for _ in texts]

    def add(self, *_args, **_kwargs):
        pass

    def delete(self, *_args, **_kwargs):
        pass

    def remove(self, *_args, **_kwargs):
        pass


def _parsed_document(status="passed", metadata=None):
    return ParsedDocument(
        parser_name="fixture-parser",
        parser_version="2.1",
        page_count=3,
        elements=[
            ParsedElement(
                text="Leave policy",
                element_type="paragraph",
                page_start=1,
                page_end=3,
                section_path=["HR", "Leave"],
            )
        ],
        quality=ParseQuality(
            status=status,
            metrics={"character_count": 12},
            warnings={
                "passed": [],
                "review_required": ["missing_page_coverage"],
                "failed": ["parser_exception"],
            }[status],
        ),
        metadata=metadata or {},
    )


def _knowledge_chunk(content="Leave policy"):
    return KnowledgeChunk(
        content=content,
        contextualized_content=f"Policy\nHR > Leave\n\n{content}",
        page_start=2,
        page_end=3,
        section_path=["HR", "Leave"],
        element_types=["paragraph"],
        source_element_indexes=[0],
        token_count=7,
        metadata={"untrusted": "do-not-publish"},
    )


@pytest.fixture(autouse=True)
def fake_retrieval(monkeypatch):
    monkeypatch.setattr(
        "app.services.document_service.get_embedding_provider", _FakeRetrieval
    )
    monkeypatch.setattr(
        "app.services.document_service.get_vector_store", _FakeRetrieval
    )
    monkeypatch.setattr(
        "app.services.document_service.get_bm25_manager", _FakeRetrieval
    )


class TestParseFile:
    def test_parse_txt(self):
        from app.core.parsing.parser import parse_file

        text = parse_file("test.txt", b"hello world")
        assert text == "hello world"

    def test_parse_md(self):
        from app.core.parsing.parser import parse_file

        text = parse_file("readme.md", b"# Title\n\nbody text")
        assert "Title" in text
        assert "body text" in text

    def test_parse_unsupported(self):
        from app.core.parsing.parser import parse_file

        with pytest.raises(ValueError, match="Unsupported"):
            parse_file("test.exe", b"data")


class TestChunker:
    async def test_fixed_chunk_basic(self):
        from app.core.parsing.chunker import _fixed_chunk

        text = "Hello world. " * 500  # ~6500 chars
        chunks = _fixed_chunk(text)
        assert len(chunks) > 1
        assert all(len(c) <= 1000 for c in chunks)

    async def test_struct_chunk_headings(self):
        from app.core.parsing.chunker import _struct_chunk

        text = "## Section 1\ncontent one\n\n## Section 2\ncontent two"
        chunks = _struct_chunk(text)
        assert len(chunks) == 2
        assert "Section 1" in chunks[0]

    async def test_chunk_text_short(self):
        from app.core.parsing.chunker import chunk_text

        chunks = await chunk_text("short text")
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    async def test_chunk_text_empty(self):
        from app.core.parsing.chunker import chunk_text

        chunks = await chunk_text("")
        assert chunks == []


class TestDocumentUpload:
    def test_legacy_document_provenance_is_unknown(self, db, test_tenant):
        from app.models.document import Document, DocumentChunk

        doc = Document(
            tenant_id=test_tenant.id,
            filename="legacy.txt",
            file_type="txt",
            file_size=6,
            file_hash="legacy-provenance-hash",
            status="ready",
        )
        db.add(doc)
        db.flush()
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=1,
            content="legacy",
        )
        db.add(chunk)
        db.flush()

        assert doc.parser_name is None
        assert doc.parser_version is None
        assert doc.page_count is None
        assert doc.parse_quality_status is None
        assert doc.parse_quality_details is None
        assert chunk.page_start is None
        assert chunk.page_end is None
        assert chunk.section_path is None
        assert chunk.element_types is None
        assert chunk.source_element_indexes is None

    async def test_upload_document_persists_audience_roles(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import upload_document

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document(),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "policy.txt", b"policy text",
            audience_roles=["admin"],
        )

        assert doc.audience_roles == ["admin"]

    async def test_upload_flushes_processing_document_before_parsing(
        self, db, test_tenant, monkeypatch,
    ):
        from app.models.document import Document
        from app.services.document_service import upload_document

        def parse_after_flush(filename, _data):
            persisted = db.query(Document).filter_by(filename=filename).one()
            assert persisted.status == "processing"
            return _parsed_document()

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file", parse_after_flush
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "flush.txt", b"flush me"
        )

        assert doc.status == "ready"

    async def test_processing_document_is_visible_to_independent_session_before_parsing(
        self, tmp_path, monkeypatch,
    ):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models import Base
        from app.models.document import Document
        from app.models.tenant import Tenant
        from app.services.document_service import upload_document

        engine = create_engine(f"sqlite:///{(tmp_path / 'processing.db').as_posix()}")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        upload_db = session_factory()
        observer_db = session_factory()
        tenant = Tenant(
            slug="independent-observer",
            name="Independent Observer",
            config_json={},
            is_active=True,
        )
        upload_db.add(tenant)
        upload_db.commit()
        observed_statuses = []

        def observe_processing_document(filename, _data):
            observer_db.expire_all()
            document = observer_db.query(Document).filter_by(filename=filename).first()
            observed_statuses.append(document.status if document else None)
            return _parsed_document()

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            observe_processing_document,
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
        )

        try:
            doc = await upload_document(
                upload_db,
                tenant.id,
                tenant.slug,
                "visible.txt",
                b"visible processing document",
            )
        finally:
            observer_db.close()
            upload_db.close()
            engine.dispose()

        assert observed_statuses == ["processing"]
        assert doc.status == "ready"

    async def test_ready_commit_failure_rolls_back_and_persists_failed_checkpoint(
        self, db, test_tenant, monkeypatch,
    ):
        from app.models.document import Document
        from app.services.document_service import list_chunks, upload_document

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document(),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
        )

        real_commit = db.commit
        real_rollback = db.rollback
        state = {"failed_once": False, "poisoned": False, "rollbacks": 0}

        def fail_ready_commit_once():
            ready = any(
                isinstance(item, Document) and item.status == "ready"
                for item in db.identity_map.values()
            )
            if ready and not state["failed_once"]:
                db.flush()
                state["failed_once"] = True
                state["poisoned"] = True
                raise RuntimeError("ready commit failed at C:\\secret token=abc")
            if state["poisoned"]:
                raise AssertionError("rollback required before another commit")
            return real_commit()

        def tracked_rollback():
            state["rollbacks"] += 1
            state["poisoned"] = False
            return real_rollback()

        monkeypatch.setattr(db, "commit", fail_ready_commit_once)
        monkeypatch.setattr(db, "rollback", tracked_rollback)

        upload_error = None
        doc = None
        try:
            doc = await upload_document(
                db,
                test_tenant.id,
                test_tenant.slug,
                "ready-commit.txt",
                b"ready commit failure",
            )
        except Exception as error:
            upload_error = error
        finally:
            if state["poisoned"]:
                state["poisoned"] = False
                real_rollback()
            monkeypatch.setattr(db, "commit", real_commit)
            monkeypatch.setattr(db, "rollback", real_rollback)

        assert upload_error is None
        assert doc is not None
        chunks = list_chunks(db, doc.id)

        assert state == {"failed_once": True, "poisoned": False, "rollbacks": 1}
        assert doc.status == "failed"
        assert doc.error_message == "Document indexing failed."
        assert len(chunks) == 1
        assert chunks[0].status == "inactive"
        assert chunks[0].embedding_id is None

    async def test_passed_upload_persists_provenance_and_indexes_controlled_data(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import list_chunks, upload_document

        class Embedding:
            def __init__(self):
                self.texts = []

            async def embed(self, texts):
                self.texts.extend(texts)
                return [[0.1, 0.2]]

        class Index:
            def __init__(self):
                self.added = []

            def add(self, *args, **kwargs):
                self.added.append((args, kwargs))

            def delete(self, *_args):
                pass

            def remove(self, *_args):
                pass

        embedding = Embedding()
        vector = Index()
        bm25 = Index()
        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document(metadata={"secret": "parser-internal"}),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
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

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "policy.txt", b"policy"
        )
        chunk = list_chunks(db, doc.id)[0]

        assert doc.status == "ready"
        assert doc.parser_name == "fixture-parser"
        assert doc.parser_version == "2.1"
        assert doc.page_count == 3
        assert doc.parse_quality_status == "passed"
        metrics = doc.parse_quality_details["metrics"]
        assert metrics["page_count"] == 3
        assert metrics["usable_text_pages"] == 3
        assert metrics["empty_pages"] == 0
        assert metrics["character_count"] == 12
        assert metrics["table_count"] == 0
        assert metrics["heading_count"] == 0
        assert metrics["ocr_pages"] == 0
        assert metrics["elapsed_ms"] >= 0
        assert doc.parse_quality_details["warnings"] == []
        assert chunk.chunk_index == 1
        assert chunk.content == "Leave policy"
        assert chunk.token_count == 7
        assert chunk.status == "active"
        assert chunk.page_start == 2
        assert chunk.page_end == 3
        assert chunk.section_path == ["HR", "Leave"]
        assert chunk.element_types == ["paragraph"]
        assert chunk.source_element_indexes == [0]
        assert chunk.embedding_id == chunk.id
        assert embedding.texts == ["Policy\nHR > Leave\n\nLeave policy"]
        assert vector.added == [(
            (
                test_tenant.slug,
                chunk.id,
                [0.1, 0.2],
            ),
            {"metadata": {
                "source": "document",
                "document_id": doc.id,
                "chunk_index": 1,
            }},
        )]
        assert bm25.added == [((test_tenant.slug, chunk.id, chunk.content), {})]

    async def test_review_required_persists_inactive_inspection_chunks_without_indexing(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import list_chunks, upload_document

        def retrieval_must_not_load():
            pytest.fail("review-required documents must not load retrieval backends")

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document("review_required"),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk()],
        )
        monkeypatch.setattr(
            "app.services.document_service.get_embedding_provider",
            retrieval_must_not_load,
        )
        monkeypatch.setattr(
            "app.services.document_service.get_vector_store", retrieval_must_not_load
        )
        monkeypatch.setattr(
            "app.services.document_service.get_bm25_manager", retrieval_must_not_load
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "review.txt", b"review"
        )
        chunks = list_chunks(db, doc.id)

        assert doc.status == "review_required"
        assert doc.parse_quality_status == "review_required"
        assert doc.chunk_count == 1
        assert doc.error_message is None
        assert len(chunks) == 1
        assert chunks[0].status == "inactive"
        assert chunks[0].embedding_id is None

    async def test_failed_quality_never_creates_chunks_or_indexes(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import list_chunks, upload_document

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document("failed"),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: pytest.fail("failed parse quality must not be chunked"),
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "failed.txt", b"failed"
        )

        assert doc.status == "failed"
        assert doc.parse_quality_status == "failed"
        assert doc.error_message == "Document parsing failed."
        assert list_chunks(db, doc.id) == []

    async def test_parser_exception_is_persisted_with_safe_error(self, db, test_tenant, monkeypatch):
        from app.services.document_service import get_document, upload_document

        def unsafe_parser(*_args):
            raise RuntimeError(r"C:\\secret\\customer.pdf token=abc")

        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file", unsafe_parser
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "unsafe.txt", b"unsafe"
        )
        persisted = get_document(db, test_tenant.id, doc.id)

        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.parse_quality_status == "failed"
        assert persisted.parse_quality_details == {
            "metrics": {},
            "warnings": ["parser_exception"],
        }
        assert persisted.error_message == "Document parsing failed."
        assert "secret" not in persisted.error_message

    async def test_partial_index_failure_cleans_vectors_and_bm25_before_failed_commit(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import list_chunks, upload_document

        class Embedding:
            async def embed(self, _texts):
                return [[0.1]]

        class Vector:
            def __init__(self):
                self.added = []
                self.deleted = []

            def add(self, _tenant_slug, chunk_id, *_args, **_kwargs):
                self.added.append(chunk_id)

            def delete(self, _tenant_slug, chunk_id):
                self.deleted.append(chunk_id)

        class Bm25:
            def __init__(self):
                self.added = []
                self.removed = []

            def add(self, _tenant_slug, chunk_id, _content):
                self.added.append(chunk_id)
                if len(self.added) == 2:
                    raise RuntimeError("customer secret from index")

            def remove(self, _tenant_slug, chunk_id):
                self.removed.append(chunk_id)

        vector = Vector()
        bm25 = Bm25()
        monkeypatch.setattr(
            "app.services.document_service.parse_structured_file",
            lambda *_: _parsed_document(),
        )
        monkeypatch.setattr(
            "app.services.document_service.chunk_document",
            lambda *_: [_knowledge_chunk("one"), _knowledge_chunk("two")],
        )
        monkeypatch.setattr(
            "app.services.document_service.get_embedding_provider", lambda: Embedding()
        )
        monkeypatch.setattr(
            "app.services.document_service.get_vector_store", lambda: vector
        )
        monkeypatch.setattr(
            "app.services.document_service.get_bm25_manager", lambda: bm25
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "partial.txt", b"partial"
        )
        chunks = list_chunks(db, doc.id)
        chunk_ids = [chunk.id for chunk in chunks]

        assert doc.status == "failed"
        assert doc.error_message == "Document indexing failed."
        assert doc.chunk_count == 2
        assert vector.added == chunk_ids
        assert vector.deleted == chunk_ids
        assert bm25.added == chunk_ids
        assert bm25.removed == chunk_ids
        assert all(chunk.status == "inactive" for chunk in chunks)
        assert all(chunk.embedding_id is None for chunk in chunks)

    async def test_native_txt_upload_evaluates_quality_and_indexes(self, db, test_tenant):
        from app.services.document_service import list_chunks, upload_document

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "native-policy.txt", b"Policy title\n\nPolicy body",
        )

        chunks = list_chunks(db, doc.id)
        metrics = doc.parse_quality_details["metrics"]
        assert doc.status == "ready"
        assert doc.parser_name == "native-text"
        assert doc.parse_quality_status == "passed"
        assert metrics["page_count"] == 0
        assert metrics["character_count"] == 23
        assert metrics["table_count"] == 0
        assert metrics["heading_count"] == 0
        assert metrics["elapsed_ms"] >= 0
        assert doc.parse_quality_details["warnings"] == []
        assert doc.chunk_count == 1
        assert doc.audience_roles == []
        assert len(chunks) == 1
        assert chunks[0].status == "active"
        assert chunks[0].embedding_id == chunks[0].id

    async def test_upload_empty_file_raises(self, db, test_tenant):
        from app.services.document_service import upload_document

        with pytest.raises(ValueError, match="Empty"):
            await upload_document(
                db, test_tenant.id, test_tenant.slug,
                "empty.txt", b"",
            )

    async def test_upload_duplicate_detected(self, db, test_tenant):
        from app.services.document_service import upload_document

        data = b"unique doc content for dedup test"
        await upload_document(db, test_tenant.id, test_tenant.slug, "a.txt", data)
        with pytest.raises(ValueError, match="already imported"):
            await upload_document(db, test_tenant.id, test_tenant.slug, "b.txt", data)

    async def test_list_documents(self, db, test_tenant):
        from app.services.document_service import list_documents, upload_document

        await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "list-test.txt", b"list test content",
        )
        items, total = list_documents(db, test_tenant.id)
        assert total >= 1

    async def test_delete_cascade(self, db, test_tenant):
        from app.services.document_service import (
            delete_document,
            get_document,
            list_chunks,
            upload_document,
        )

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "delete-me.txt", b"content to delete",
        )
        if doc.status == "ready":
            chunks_before = list_chunks(db, doc.id)
            assert len(chunks_before) > 0

        delete_document(db, test_tenant.slug, doc.id)
        assert get_document(db, test_tenant.id, doc.id) is None

    async def test_cross_tenant_dedup_allowed(self, db, test_tenant):
        """Same file hash, different tenant — allowed, not rejected."""
        from app.services.document_service import upload_document
        data = b"cross-tenant content for dedup"
        # Upload to first tenant
        doc1 = await upload_document(db, test_tenant.id, test_tenant.slug, "x.txt", data)
        assert doc1.status in ("ready", "failed")

        # Upload same content to a second tenant (simulated with a new tenant)
        from app.models.tenant import Tenant
        import uuid
        tenant2 = Tenant(
            id=str(uuid.uuid4()), slug="tenant-b", name="Tenant B",
            config_json={"handoff_enabled": True}, is_active=True,
        )
        db.add(tenant2)
        db.commit()
        # Should NOT raise "already imported"
        doc2 = await upload_document(db, tenant2.id, tenant2.slug, "x.txt", data)
        assert doc2.status in ("ready", "failed")


class TestRetrievalCoverage:
    """Verify that imported document chunks are retrievable."""

    async def test_chunk_searchable_after_import(self, db, test_tenant):
        """After importing a document, chunks are persisted in DB."""
        from app.services.document_service import upload_document, list_chunks

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "retrieval-test.txt", b"return policy: 7-day return, 15-day quality exchange",
        )
        if doc.status != "ready":
            return  # skip if no embedding API available

        chunks = list_chunks(db, doc.id)
        assert len(chunks) >= 1
        assert len(chunks[0].content) > 0
        assert chunks[0].embedding_id is not None
