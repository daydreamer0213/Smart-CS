"""Document approval, publication, and lifecycle deletion tests."""

from datetime import date, timedelta

import pytest

from app.models.document import Document, DocumentChunk, DocumentFamily


def _governed_snapshot(
    db,
    tenant_id,
    *,
    family=None,
    status="ready",
    quality="passed",
    review_status="pending_review",
    effective_date=None,
    expiry_date=None,
    storage_key="tenant/shared-policy.txt",
):
    if family is None:
        family = DocumentFamily(tenant_id=tenant_id, name="Leave policy")
        db.add(family)
        db.flush()
    version = db.query(Document).filter(Document.family_id == family.id).count() + 1
    document = Document(
        tenant_id=tenant_id,
        family_id=family.id,
        filename="leave-policy.txt",
        file_type="txt",
        file_hash=f"hash-{version}-{status}-{quality}",
        status=status,
        parse_quality_status=quality,
        review_status=review_status,
        effective_date=effective_date,
        expiry_date=expiry_date,
        storage_key=storage_key,
        version=version,
    )
    db.add(document)
    db.flush()
    return family, document


def test_approval_switches_family_pointer_and_records_reviewer(db, test_tenant):
    from app.core.auth.security import hash_password
    from app.models.user import User
    from app.services.document_service import review_document

    reviewer = User(
        tenant_id=test_tenant.id,
        email="service-reviewer@example.com",
        password_hash=hash_password("not-used-in-test"),
        display_name="Service Reviewer",
        role="admin",
        is_active=True,
    )
    db.add(reviewer)
    db.flush()

    family, old = _governed_snapshot(
        db, test_tenant.id, review_status="approved"
    )
    family.current_document_id = old.id
    _, pending = _governed_snapshot(db, test_tenant.id, family=family)

    reviewed = review_document(
        db,
        tenant_id=test_tenant.id,
        document_id=pending.id,
        decision="approved",
        reviewer_user_id=reviewer.id,
    )

    assert reviewed.review_status == "approved"
    assert reviewed.reviewed_by_user_id == reviewer.id
    assert reviewed.reviewed_at is not None
    assert family.current_document_id == pending.id


def test_rejection_never_changes_current_pointer(db, test_tenant):
    from app.services.document_service import review_document

    family, current = _governed_snapshot(
        db, test_tenant.id, review_status="approved"
    )
    family.current_document_id = current.id
    _, pending = _governed_snapshot(
        db,
        test_tenant.id,
        family=family,
        status="review_required",
        quality="review_required",
    )

    reviewed = review_document(
        db,
        tenant_id=test_tenant.id,
        document_id=pending.id,
        decision="rejected",
        reviewer_user_id=None,
    )

    assert reviewed.review_status == "rejected"
    assert reviewed.reviewed_at is not None
    assert family.current_document_id == current.id


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "failed"}, "ready"),
        ({"quality": "review_required"}, "quality"),
        ({"effective_date": date.today() + timedelta(days=1)}, "effective"),
        ({"expiry_date": date.today() - timedelta(days=1)}, "expired"),
    ],
)
def test_invalid_snapshot_cannot_be_approved(
    db, test_tenant, overrides, message,
):
    from app.services.document_service import DocumentLifecycleError, review_document

    _, document = _governed_snapshot(db, test_tenant.id, **overrides)

    with pytest.raises(DocumentLifecycleError, match=message):
        review_document(
            db,
            tenant_id=test_tenant.id,
            document_id=document.id,
            decision="approved",
            reviewer_user_id=None,
        )


def test_cross_tenant_document_cannot_be_reviewed(db, test_tenant):
    from app.models.tenant import Tenant
    from app.services.document_service import DocumentLifecycleError, review_document

    other = Tenant(
        slug="governance-other-tenant",
        name="Governance Other Tenant",
        config_json={},
        is_active=True,
    )
    db.add(other)
    db.flush()
    family, document = _governed_snapshot(db, other.id)

    with pytest.raises(DocumentLifecycleError, match="not found"):
        review_document(
            db,
            tenant_id=test_tenant.id,
            document_id=document.id,
            decision="approved",
            reviewer_user_id=None,
        )

    db.delete(document)
    db.delete(family)
    db.delete(other)
    db.commit()


def test_current_published_snapshot_cannot_be_deleted(db, test_tenant, monkeypatch):
    from app.services.document_service import DocumentLifecycleError, delete_document

    family, current = _governed_snapshot(
        db, test_tenant.id, review_status="approved"
    )
    family.current_document_id = current.id
    db.commit()

    with pytest.raises(DocumentLifecycleError, match="current"):
        delete_document(db, test_tenant.id, test_tenant.slug, current.id)


def test_non_current_delete_removes_only_unshared_original(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import delete_document

    family, current = _governed_snapshot(
        db, test_tenant.id, review_status="approved"
    )
    family.current_document_id = current.id
    _, obsolete = _governed_snapshot(
        db,
        test_tenant.id,
        family=family,
        review_status="rejected",
        storage_key="tenant/obsolete.txt",
    )
    db.commit()

    deleted = []
    monkeypatch.setattr(
        "app.services.document_service.delete_original", deleted.append,
        raising=False,
    )

    delete_document(db, test_tenant.id, test_tenant.slug, obsolete.id)

    assert db.get(Document, obsolete.id) is None
    assert deleted == ["tenant/obsolete.txt"]


def test_non_current_delete_keeps_shared_original(db, test_tenant, monkeypatch):
    from app.services.document_service import delete_document

    family, current = _governed_snapshot(
        db, test_tenant.id, review_status="approved"
    )
    family.current_document_id = current.id
    _, obsolete = _governed_snapshot(
        db,
        test_tenant.id,
        family=family,
        review_status="rejected",
    )
    db.commit()

    deleted = []
    monkeypatch.setattr(
        "app.services.document_service.delete_original", deleted.append,
        raising=False,
    )

    delete_document(db, test_tenant.id, test_tenant.slug, obsolete.id)

    assert db.get(Document, obsolete.id) is None
    assert deleted == []


def test_delete_service_is_tenant_scoped(db, test_tenant):
    from app.services.document_service import delete_document

    _, document = _governed_snapshot(
        db, test_tenant.id, review_status="rejected"
    )
    db.commit()

    delete_document(db, "wrong-tenant", test_tenant.slug, document.id)

    assert db.get(Document, document.id) is not None


def test_external_cleanup_failure_does_not_keep_sql_visible_snapshot(
    db, test_tenant, monkeypatch,
):
    from app.services.document_service import delete_document

    _, document = _governed_snapshot(
        db,
        test_tenant.id,
        review_status="rejected",
        storage_key=None,
    )
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="obsolete",
        status="active",
    )
    db.add(chunk)
    db.commit()

    class FailingVector:
        def delete(self, *_args):
            raise RuntimeError("vector unavailable")

    class FailingBm25:
        def remove(self, *_args):
            raise RuntimeError("bm25 unavailable")

    monkeypatch.setattr(
        "app.services.document_service.get_vector_store", lambda: FailingVector()
    )
    monkeypatch.setattr(
        "app.services.document_service.get_bm25_manager", lambda: FailingBm25()
    )

    delete_document(db, test_tenant.id, test_tenant.slug, document.id)

    assert db.get(Document, document.id) is None
