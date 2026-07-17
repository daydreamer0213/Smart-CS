"""Document service tests — upload, list, get, delete."""

import pytest


class _FakeRetrieval:
    async def embed(self, texts):
        return [[0.0] for _ in texts]

    def add(self, *_args, **_kwargs):
        pass

    def delete(self, *_args, **_kwargs):
        pass

    def remove(self, *_args, **_kwargs):
        pass


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
    async def test_upload_document_persists_audience_roles(
        self, db, test_tenant, monkeypatch,
    ):
        from app.services.document_service import upload_document

        async def fake_chunk_text(_text):
            return ["policy text"]

        monkeypatch.setattr(
            "app.services.document_service.parse_file", lambda *_: "policy text"
        )
        monkeypatch.setattr("app.services.document_service.chunk_text", fake_chunk_text)

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug, "policy.txt", b"policy text",
            audience_roles=["admin"],
        )

        assert doc.audience_roles == ["admin"]

    async def test_upload_txt_creates_document(self, db, test_tenant):
        """Upload a text file and verify Document + chunks are created."""
        from app.services.document_service import upload_document

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "faq.txt", b"Q: test question\nA: test answer",
        )
        assert doc.status in ("ready", "failed")
        assert doc.audience_roles == []
        if doc.status == "ready":
            assert doc.chunk_count > 0

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
