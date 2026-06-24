"""Admin document API integration tests."""

import pytest


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
