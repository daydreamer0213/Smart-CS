"""Persistence and response-contract tests for HR support handoffs."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from pydantic import ValidationError

from app.models import HandoffDraft, SupportHandoff
from app.models.user import User
from app.schemas.hr_support import HandoffStatusUpdate, SourceCitation


def _employee(tenant_id: str) -> User:
    return User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        email=f"employee-{uuid.uuid4().hex}@example.test",
        password_hash="not-a-real-password",
        display_name="Test Employee",
        role="employee",
    )


def test_handoff_draft_persists_required_fields_and_pending_default(db, test_tenant):
    employee = _employee(test_tenant.id)
    draft = HandoffDraft(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant.id,
        requester_user_id=employee.id,
        question="How does cross-border employment affect annual leave?",
        reason="The published policy does not cover this exception.",
        sources_json=[{"source_type": "document", "source_id": "doc-1"}],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    db.add_all([employee, draft])
    db.commit()
    stored = db.get(HandoffDraft, draft.id)

    assert stored is not None
    assert stored.tenant_id == test_tenant.id
    assert stored.requester_user_id == employee.id
    assert stored.question == draft.question
    assert stored.reason == draft.reason
    assert stored.sources_json == draft.sources_json
    assert stored.status == "pending"
    assert stored.expires_at is not None


def test_support_handoff_persists_open_default_and_nullable_lifecycle_fields(db, test_tenant):
    employee = _employee(test_tenant.id)
    handoff = SupportHandoff(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant.id,
        requester_user_id=employee.id,
        question="Please help with a policy exception.",
        reason="No authorized answer is available.",
        sources_json=[],
    )

    db.add_all([employee, handoff])
    db.commit()
    stored = db.get(SupportHandoff, handoff.id)

    assert stored is not None
    assert stored.tenant_id == test_tenant.id
    assert stored.requester_user_id == employee.id
    assert stored.question == handoff.question
    assert stored.reason == handoff.reason
    assert stored.sources_json == []
    assert stored.status == "open"
    assert stored.assigned_user_id is None
    assert stored.resolved_by_user_id is None
    assert stored.resolution_note is None
    assert stored.resolved_at is None


def test_handoff_draft_defaults_sources_to_an_empty_list(db, test_tenant):
    employee = _employee(test_tenant.id)
    draft = HandoffDraft(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant.id,
        requester_user_id=employee.id,
        question="Where is the leave policy?",
        reason="The employee needs HR support.",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    db.add_all([employee, draft])
    db.commit()

    assert db.get(HandoffDraft, draft.id).sources_json == []


def test_source_citation_accepts_only_public_display_fields():
    citation = SourceCitation(
        source_type="document",
        source_id="doc-1",
        title="Annual leave policy",
        excerpt="Apply five business days in advance.",
        score=0.98,
    )

    assert citation.model_dump() == {
        "source_type": "document",
        "source_id": "doc-1",
        "title": "Annual leave policy",
        "excerpt": "Apply five business days in advance.",
        "score": 0.98,
    }
    with pytest.raises(ValidationError):
        SourceCitation(source_type="document", source_id="doc-1", raw_content="secret")


def test_resolved_handoff_status_requires_nonblank_resolution_note():
    with pytest.raises(ValidationError):
        HandoffStatusUpdate(status="resolved", resolution_note="   ")
