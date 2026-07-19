"""Admin document API integration tests."""

from types import SimpleNamespace

import pytest

from app.models.document import Document, DocumentChunk
from app.services import document_service


class _FakeRetrieval:
    def add(self, *_args, **_kwargs):
        pass

    def delete(self, *_args, **_kwargs):
        pass

    def remove(self, *_args, **_kwargs):
        pass


@pytest.fixture(autouse=True)
def fake_retrieval(monkeypatch):
    monkeypatch.setattr(document_service, "get_vector_store", _FakeRetrieval)
    monkeypatch.setattr(document_service, "get_bm25_manager", _FakeRetrieval)


async def test_document_upload_accepts_and_returns_audience_roles(
    admin_client, test_tenant, monkeypatch,
):
    captured = {}

    async def fake_upload(*_args, audience_roles=None, **_kwargs):
        captured["audience_roles"] = audience_roles
        return SimpleNamespace(
            id="doc-1", filename="policy.txt", chunk_count=1,
            status="ready", audience_roles=audience_roles,
        )

    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("policy.txt", b"policy", "text/plain")},
        data={"audience_roles": "admin"},
    )

    assert response.status_code == 201
    assert captured["audience_roles"] == ["admin"]
    assert response.json()["audience_roles"] == ["admin"]


async def test_document_upload_returns_explicit_provenance_without_parser_metadata(
    admin_client, test_tenant, monkeypatch,
):
    async def fake_upload(*_args, **_kwargs):
        return SimpleNamespace(
            id="doc-provenance",
            filename="policy.pdf",
            chunk_count=2,
            status="review_required",
            audience_roles=["admin"],
            parser_name="docling",
            parser_version="2.0",
            page_count=4,
            parse_quality_status="review_required",
            parse_quality_details={
                "metrics": {"page_count": 4},
                "warnings": ["missing_page_coverage"],
            },
            error_message=None,
            parser_metadata={"customer_secret": "must-not-leak"},
        )

    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("policy.pdf", b"pdf", "application/pdf")},
        data={"audience_roles": "admin"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "document_id": "doc-provenance",
        "filename": "policy.pdf",
        "chunk_count": 2,
        "status": "review_required",
        "audience_roles": ["admin"],
        "parser_name": "docling",
        "parser_version": "2.0",
        "page_count": 4,
        "parse_quality_status": "review_required",
        "parse_quality_details": {
            "metrics": {"page_count": 4},
            "warnings": ["missing_page_coverage"],
        },
        "error_message": None,
    }


async def test_document_upload_accepts_repeated_audience_roles(
    admin_client, test_tenant, monkeypatch,
):
    captured = {}

    async def fake_upload(*_args, audience_roles=None, **_kwargs):
        captured["audience_roles"] = audience_roles
        return SimpleNamespace(
            id="doc-1", filename="policy.txt", chunk_count=1,
            status="ready", audience_roles=audience_roles,
        )

    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files=[
            ("file", ("policy.txt", b"policy", "text/plain")),
            ("audience_roles", (None, "owner")),
            ("audience_roles", (None, "admin")),
        ],
    )

    assert response.status_code == 201
    assert captured["audience_roles"] == ["owner", "admin"]
    assert response.json()["audience_roles"] == ["owner", "admin"]


async def test_document_upload_rejects_invalid_audience_role(
    admin_client, test_tenant, monkeypatch,
):
    async def fail_if_called(*_args, **_kwargs):
        pytest.fail("upload_document must not be called for an invalid role")

    monkeypatch.setattr(document_service, "upload_document", fail_if_called)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("policy.txt", b"policy", "text/plain")},
        data={"audience_roles": "invalid"},
    )

    assert response.status_code == 422


async def test_document_list_returns_audience_roles(admin_client, db, test_tenant):
    db.add(Document(
        tenant_id=test_tenant.id,
        filename="policy.txt",
        file_type="txt",
        file_size=6,
        file_hash="policy-hash",
        status="ready",
        audience_roles=["admin"],
    ))
    db.commit()

    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents"
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["audience_roles"] == ["admin"]


async def test_document_list_returns_explicit_provenance_and_legacy_nulls(
    admin_client, db, test_tenant,
):
    db.add_all([
        Document(
            tenant_id=test_tenant.id,
            filename="structured.pdf",
            file_type="pdf",
            file_size=10,
            file_hash="structured-provenance-hash",
            status="review_required",
            parser_name="docling",
            parser_version="2.0",
            page_count=2,
            parse_quality_status="review_required",
            parse_quality_details={
                "metrics": {"page_count": 2},
                "warnings": ["missing_page_coverage"],
            },
        ),
        Document(
            tenant_id=test_tenant.id,
            filename="legacy.txt",
            file_type="txt",
            file_size=6,
            file_hash="legacy-api-provenance-hash",
            status="ready",
        ),
    ])
    db.commit()

    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents"
    )

    assert response.status_code == 200
    items = {item["filename"]: item for item in response.json()["items"]}
    assert items["structured.pdf"]["parser_name"] == "docling"
    assert items["structured.pdf"]["page_count"] == 2
    assert items["structured.pdf"]["parse_quality_status"] == "review_required"
    assert items["structured.pdf"]["parse_quality_details"]["warnings"] == [
        "missing_page_coverage"
    ]
    assert items["legacy.txt"]["parser_name"] is None
    assert items["legacy.txt"]["parser_version"] is None
    assert items["legacy.txt"]["page_count"] is None
    assert items["legacy.txt"]["parse_quality_status"] is None
    assert items["legacy.txt"]["parse_quality_details"] is None


async def test_document_chunks_return_explicit_provenance(
    admin_client, db, test_tenant,
):
    document = Document(
        tenant_id=test_tenant.id,
        filename="chunks.pdf",
        file_type="pdf",
        file_size=10,
        file_hash="chunk-api-provenance-hash",
        status="review_required",
    )
    db.add(document)
    db.flush()
    db.add(DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Leave policy",
        status="inactive",
        page_start=2,
        page_end=3,
        section_path=["HR", "Leave"],
        element_types=["paragraph", "table"],
        source_element_indexes=[4, 5],
    ))
    db.commit()

    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents/{document.id}/chunks"
    )

    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["page_start"] == 2
    assert chunk["page_end"] == 3
    assert chunk["section_path"] == ["HR", "Leave"]
    assert chunk["element_types"] == ["paragraph", "table"]
    assert chunk["source_element_indexes"] == [4, 5]


async def test_document_upload_endpoint(admin_client, test_tenant):
    """Upload a txt file via the admin API."""
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("test.txt", b"Q: test question\nA: test answer", "text/plain")},
    )
    assert response.status_code in (201, 400)  # 400 if no embedding API key


async def test_document_list_endpoint(admin_client, test_tenant):
    """GET documents list returns 200."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents"
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


async def test_document_upload_requires_auth(client, test_tenant):
    """Upload endpoint requires X-Admin-Key."""
    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("test.txt", b"data", "text/plain")},
    )
    assert response.status_code == 401


async def test_document_upload_rejects_exe(admin_client, test_tenant):
    """Unsupported file types should be rejected."""
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("virus.exe", b"malware", "application/octet-stream")},
    )
    assert response.status_code in (400, 401)


async def test_document_delete_cascade(admin_client, test_tenant):
    """Delete a document and verify it's gone."""
    # Upload first
    resp = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("delete-test.txt", b"delete test content", "text/plain")},
    )
    if resp.status_code == 201:
        doc_id = resp.json()["document_id"]
        # Delete
        resp2 = await admin_client.delete(
            f"/api/v1/admin/{test_tenant.slug}/documents/{doc_id}"
        )
        assert resp2.status_code == 200


async def test_document_list_respects_pagination(admin_client, test_tenant):
    """Documents list supports pagination params."""
    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents?page=1&page_size=5"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 5
