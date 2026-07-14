"""JWT auth and admin boundary tests."""

import uuid

from app.models.tenant import Tenant
from app.models.user import User


def _email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


async def _register(client, headers: dict | None = None, **overrides):
    payload = {
        "email": _email("user"),
        "password": "password123",
        "display_name": "Test User",
        "role": "agent",
    }
    payload.update(overrides)
    return await client.post("/api/v1/auth/register", json=payload, headers=headers)


async def test_owner_register_creates_tenant_and_user(client, db):
    slug = f"owner-{uuid.uuid4().hex[:8]}"
    response = await _register(
        client,
        email=_email("owner"),
        role="owner",
        tenant_slug=slug,
        tenant_name="Owner Tenant",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "owner"
    assert data["user"]["tenant_slug"] == slug
    assert data["access_token"]
    assert data["refresh_token"]
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    assert tenant is not None
    assert db.query(User).filter(User.tenant_id == tenant.id).count() == 1


async def test_admin_register_binds_existing_tenant(admin_client, test_tenant):
    response = await _register(
        admin_client,
        email=_email("admin"),
        role="admin",
        tenant_slug=test_tenant.slug,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "admin"
    assert data["user"]["tenant_id"] == test_tenant.id


async def test_agent_register_binds_existing_tenant(admin_client, test_tenant):
    response = await _register(
        admin_client,
        email=_email("agent"),
        role="agent",
        tenant_slug=test_tenant.slug,
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "agent"


async def test_employee_register_binds_existing_tenant(admin_client, test_tenant):
    response = await _register(
        admin_client,
        email=_email("employee"),
        role="employee",
        tenant_slug=test_tenant.slug,
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "employee"


async def test_existing_tenant_role_registration_requires_tenant_admin(client, test_tenant):
    response = await _register(
        client,
        email=_email("rogue-admin"),
        role="admin",
        tenant_slug=test_tenant.slug,
    )

    assert response.status_code == 401


async def test_owner_jwt_can_register_agent_for_own_tenant(client):
    slug = f"owner-agent-{uuid.uuid4().hex[:8]}"
    owner = await _register(
        client,
        email=_email("owner-agent"),
        role="owner",
        tenant_slug=slug,
        tenant_name="Owner Agent Tenant",
    )

    response = await _register(
        client,
        headers={"Authorization": f"Bearer {owner.json()['access_token']}"},
        email=_email("owner-created-agent"),
        role="agent",
        tenant_slug=slug,
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "agent"


async def test_register_rejects_weak_password_and_missing_role_fields(client):
    weak_password = await _register(
        client,
        password="password",
        role="owner",
        tenant_slug=f"weak-{uuid.uuid4().hex[:6]}",
        tenant_name="Weak Tenant",
    )
    assert weak_password.status_code == 422

    missing_owner_name = await _register(
        client,
        role="owner",
        tenant_slug=f"missing-{uuid.uuid4().hex[:6]}",
    )
    assert missing_owner_name.status_code == 422

    missing_tenant = await _register(client, role="admin")
    assert missing_tenant.status_code == 422


async def test_login_refresh_and_me(client, admin_client, test_tenant):
    email = _email("login")
    password = "password123"
    register_response = await _register(
        admin_client,
        email=email,
        password=password,
        role="admin",
        tenant_slug=test_tenant.slug,
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": test_tenant.slug, "email": email, "password": password},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email


async def test_admin_jwt_can_access_admin_api(client, admin_client, test_tenant):
    response = await _register(
        admin_client,
        email=_email("admin-route"),
        role="admin",
        tenant_slug=test_tenant.slug,
    )
    token = response.json()["access_token"]

    admin_response = await client.get(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert admin_response.status_code == 200


async def test_admin_api_key_still_works(admin_client, test_tenant):
    response = await admin_client.get(f"/api/v1/admin/{test_tenant.slug}/knowledge")
    assert response.status_code == 200


async def test_agent_forbidden_from_admin_api(client, admin_client, test_tenant):
    response = await _register(
        admin_client,
        email=_email("agent-route"),
        role="agent",
        tenant_slug=test_tenant.slug,
    )
    token = response.json()["access_token"]

    admin_response = await client.get(
        f"/api/v1/admin/{test_tenant.slug}/knowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert admin_response.status_code == 403


async def test_cross_tenant_jwt_forbidden(client, db):
    slug_a = f"tenant-a-{uuid.uuid4().hex[:6]}"
    slug_b = f"tenant-b-{uuid.uuid4().hex[:6]}"
    reg = await _register(
        client,
        email=_email("owner-a"),
        role="owner",
        tenant_slug=slug_a,
        tenant_name="Tenant A",
    )
    tenant_b = Tenant(
        id=str(uuid.uuid4()),
        slug=slug_b,
        name="Tenant B",
        config_json={},
        is_active=True,
    )
    db.add(tenant_b)
    db.commit()

    response = await client.get(
        f"/api/v1/admin/{slug_b}/knowledge",
        headers={"Authorization": f"Bearer {reg.json()['access_token']}"},
    )
    assert response.status_code == 403


async def test_cross_tenant_api_key_forbidden(admin_client, db):
    other = Tenant(
        id=str(uuid.uuid4()),
        slug=f"other-{uuid.uuid4().hex[:6]}",
        name="Other",
        config_json={},
        is_active=True,
    )
    db.add(other)
    db.commit()

    response = await admin_client.get(f"/api/v1/admin/{other.slug}/knowledge")
    assert response.status_code == 403
