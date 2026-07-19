"""Admin document API integration tests."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.models.document import Document, DocumentChunk, DocumentFamily
from app.services import document_service


def _governed_document(**overrides):
    values = {
        "id": "doc-governed",
        "filename": "policy.txt",
        "chunk_count": 1,
        "status": "ready",
        "audience_roles": ["employee"],
        "family_id": "family-1",
        "family": SimpleNamespace(
            name="Annual leave policy",
            current_document_id=None,
        ),
        "version": 2,
        "index_generation": 1,
        "review_status": "pending_review",
        "effective_date": None,
        "expiry_date": None,
        "owner_user_id": None,
        "reviewed_by_user_id": None,
        "reviewed_at": None,
        "source_type": "upload",
        "source_ref": "policy.txt",
        "storage_key": "tenant/private/source.txt",
        "chunker_version": "structured-v1",
        "embedding_provider": "openai",
        "embedding_model": "test-embedding",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
    monkeypatch.setattr(
        document_service,
        "store_original",
        lambda tenant_id, file_hash, suffix, _data: (
            f"{tenant_id}/{file_hash}{suffix}"
        ),
    )


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
    secret = r"C:\customer\private.pdf token=upload-secret"

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
                "metrics": {
                    "page_count": 4,
                    "elapsed_ms": 12.5,
                    "private_path": secret,
                    "heading_count": {"metadata": secret},
                },
                "warnings": ["missing_page_coverage", secret],
                "metadata": {"secret": secret},
                "arbitrary": secret,
            },
            error_message=secret,
            parser_metadata={"customer_secret": secret},
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
            "metrics": {"page_count": 4, "elapsed_ms": 12.5},
            "warnings": ["missing_page_coverage"],
        },
        "error_message": "Document processing failed.",
    }
    assert secret not in response.text


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


async def test_document_upload_accepts_governance_fields_without_exposing_storage_key(
    admin_client, test_tenant, monkeypatch,
):
    captured = {}

    async def fake_upload(*_args, **kwargs):
        captured.update(kwargs)
        return _governed_document()

    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        files={"file": ("policy.txt", b"policy", "text/plain")},
        data={
            "audience_roles": "employee",
            "family_id": "family-1",
            "family_name": "Annual leave policy",
            "effective_date": "2026-01-01",
            "expiry_date": "2026-12-31",
        },
    )

    assert response.status_code == 201
    assert captured["family_id"] == "family-1"
    assert captured["family_name"] == "Annual leave policy"
    assert captured["effective_date"].isoformat() == "2026-01-01"
    assert captured["expiry_date"].isoformat() == "2026-12-31"
    assert captured["owner_user_id"] is None
    payload = response.json()
    assert payload["family_id"] == "family-1"
    assert payload["family_name"] == "Annual leave policy"
    assert payload["version"] == 2
    assert payload["index_generation"] == 1
    assert payload["review_status"] == "pending_review"
    assert payload["original_file_available"] is True
    assert "storage_key" not in payload
    assert "private" not in response.text


async def test_document_upload_uses_jwt_admin_as_owner(
    client, db, test_tenant, monkeypatch,
):
    from app.core.auth.security import hash_password
    from app.core.auth.token import create_access_token
    from app.models.user import User

    owner = User(
        tenant_id=test_tenant.id,
        email="document-owner@example.com",
        password_hash=hash_password("not-used-in-test"),
        display_name="Document Owner",
        role="owner",
        is_active=True,
    )
    db.add(owner)
    db.commit()
    captured = {}

    async def fake_upload(*_args, **kwargs):
        captured.update(kwargs)
        return _governed_document(owner_user_id=owner.id)

    monkeypatch.setattr(document_service, "upload_document", fake_upload)
    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/upload",
        headers={"Authorization": f"Bearer {create_access_token(owner)}"},
        files={"file": ("policy.txt", b"policy", "text/plain")},
    )

    assert response.status_code == 201
    assert captured["owner_user_id"] == owner.id
    assert response.json()["owner_user_id"] == owner.id


async def test_document_review_approves_and_publishes_snapshot(
    admin_client, db, test_tenant,
):
    family = DocumentFamily(tenant_id=test_tenant.id, name="Review policy")
    db.add(family)
    db.flush()
    document = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename="review-policy.txt",
        file_type="txt",
        file_hash="review-policy-hash",
        status="ready",
        parse_quality_status="passed",
        review_status="pending_review",
    )
    db.add(document)
    db.commit()

    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/{document.id}/review",
        json={"decision": "approved"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document.id
    assert payload["review_status"] == "approved"
    assert payload["is_current"] is True
    assert payload["reviewed_by_user_id"] is None
    db.refresh(family)
    assert family.current_document_id == document.id


async def test_document_review_records_jwt_reviewer(
    client, db, test_tenant,
):
    from app.core.auth.security import hash_password
    from app.core.auth.token import create_access_token
    from app.models.user import User

    reviewer = User(
        tenant_id=test_tenant.id,
        email="reviewer@example.com",
        password_hash=hash_password("not-used-in-test"),
        display_name="Reviewer",
        role="admin",
        is_active=True,
    )
    family = DocumentFamily(tenant_id=test_tenant.id, name="JWT review policy")
    db.add_all([reviewer, family])
    db.flush()
    document = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename="jwt-review.txt",
        file_type="txt",
        file_hash="jwt-review-hash",
        status="ready",
        parse_quality_status="passed",
        review_status="pending_review",
    )
    db.add(document)
    db.commit()

    response = await client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/{document.id}/review",
        headers={"Authorization": f"Bearer {create_access_token(reviewer)}"},
        json={"decision": "approved"},
    )

    assert response.status_code == 200
    assert response.json()["reviewed_by_user_id"] == reviewer.id


async def test_document_review_rejects_unpublishable_snapshot(
    admin_client, db, test_tenant,
):
    family = DocumentFamily(tenant_id=test_tenant.id, name="Failed policy")
    db.add(family)
    db.flush()
    document = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename="failed-policy.txt",
        file_type="txt",
        file_hash="failed-review-hash",
        status="failed",
        parse_quality_status="failed",
        review_status="pending_review",
    )
    db.add(document)
    db.commit()

    response = await admin_client.post(
        f"/api/v1/admin/{test_tenant.slug}/documents/{document.id}/review",
        json={"decision": "approved"},
    )

    assert response.status_code == 409
    assert "ready" in response.text


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


async def test_document_list_returns_governance_without_storage_key(
    admin_client, db, test_tenant,
):
    family = DocumentFamily(
        tenant_id=test_tenant.id,
        name="Annual leave policy",
    )
    db.add(family)
    db.flush()
    document = Document(
        tenant_id=test_tenant.id,
        family_id=family.id,
        filename="annual-leave.pdf",
        file_type="pdf",
        file_size=10,
        file_hash="governed-list-hash",
        status="ready",
        version=2,
        index_generation=3,
        review_status="approved",
        effective_date=date(2026, 1, 1),
        source_type="upload",
        source_ref="annual-leave.pdf",
        storage_key="tenant/private/original.pdf",
        chunker_version="structured-v1",
        embedding_provider="openai",
        embedding_model="test-embedding",
    )
    db.add(document)
    db.flush()
    family.current_document_id = document.id
    db.commit()

    response = await admin_client.get(
        f"/api/v1/admin/{test_tenant.slug}/documents"
    )

    assert response.status_code == 200
    item = next(
        item for item in response.json()["items"]
        if item["filename"] == "annual-leave.pdf"
    )
    assert item["family_id"] == family.id
    assert item["family_name"] == "Annual leave policy"
    assert item["version"] == 2
    assert item["index_generation"] == 3
    assert item["review_status"] == "approved"
    assert item["effective_date"] == "2026-01-01"
    assert item["is_current"] is True
    assert item["original_file_available"] is True
    assert "storage_key" not in item
    assert "private" not in response.text


async def test_document_list_returns_explicit_provenance_and_legacy_nulls(
    admin_client, db, test_tenant,
):
    secret = r"C:\customer\private.pdf token=list-secret"
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
                "metrics": {
                    "page_count": 2,
                    "ocr_confidence": 0.9,
                    "private_path": secret,
                },
                "warnings": ["missing_page_coverage", secret],
                "metadata": {"secret": secret},
            },
            error_message=secret,
        ),
        Document(
            tenant_id=test_tenant.id,
            filename="legacy.txt",
            file_type="txt",
            file_size=6,
            file_hash="legacy-api-provenance-hash",
            status="ready",
            error_message="Document indexing failed.",
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
    assert items["structured.pdf"]["parse_quality_details"] == {
        "metrics": {"page_count": 2, "ocr_confidence": 0.9},
        "warnings": ["missing_page_coverage"],
    }
    assert items["structured.pdf"]["error_message"] == "Document processing failed."
    assert items["legacy.txt"]["parser_name"] is None
    assert items["legacy.txt"]["parser_version"] is None
    assert items["legacy.txt"]["page_count"] is None
    assert items["legacy.txt"]["parse_quality_status"] is None
    assert items["legacy.txt"]["parse_quality_details"] is None
    assert items["legacy.txt"]["error_message"] == "Document indexing failed."
    assert secret not in response.text


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
        index_generation=2,
        chunker_version="structured-v1",
        embedding_model="test-embedding",
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
    assert chunk["index_generation"] == 2
    assert chunk["chunker_version"] == "structured-v1"
    assert chunk["embedding_model"] == "test-embedding"


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
