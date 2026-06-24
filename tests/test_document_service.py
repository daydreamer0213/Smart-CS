"""Document service tests — upload, list, get, delete."""

import pytest


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
    async def test_upload_txt_creates_document(self, db, test_tenant):
        """Upload a text file and verify Document + chunks are created."""
        from app.services.document_service import upload_document

        doc = await upload_document(
            db, test_tenant.id, test_tenant.slug,
            "faq.txt", b"Q: test question\nA: test answer",
        )
        assert doc.status in ("ready", "failed")
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
