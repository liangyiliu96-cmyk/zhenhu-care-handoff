"""Authentication configuration and JWT claim mapping tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


def _jwt(secret: str, **claims: object) -> str:
    payload = {
        "sub": "clinician-001",
        "iss": "https://idp.example.test/realms/zhenhu",
        "aud": "zhenhu-inpatient",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        **claims,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_signed_jwt_maps_only_verified_identity_claims(monkeypatch):
    """JWT identities come from signed claims rather than request headers."""
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret")
    monkeypatch.setenv("AUTH_ISSUER", "https://idp.example.test/realms/zhenhu")
    monkeypatch.setenv("AUTH_AUDIENCE", "zhenhu-inpatient")

    from zhenhu.inpatient.middleware.auth import authenticate_bearer_token

    user = authenticate_bearer_token(
        _jwt(
            "test-signing-secret",
            realm_access={"roles": ["clinician", "nurse"]},
            departments=["cardiology", "geriatrics"],
            actor_id="forgeable-request-value",
        )
    )

    assert user["actor_id"] == "clinician-001"
    assert user["roles"] == {"doctor", "nurse"}
    assert user["departments"] == {"cardiology", "geriatrics"}
    assert "actor_id" not in user["claims"]


def test_expired_jwt_is_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret")
    monkeypatch.setenv("AUTH_ISSUER", "https://idp.example.test/realms/zhenhu")
    monkeypatch.setenv("AUTH_AUDIENCE", "zhenhu-inpatient")

    from zhenhu.inpatient.middleware.auth import AuthenticationError, authenticate_bearer_token

    expired = jwt.encode(
        {
            "sub": "clinician-001",
            "iss": "https://idp.example.test/realms/zhenhu",
            "aud": "zhenhu-inpatient",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        "test-signing-secret",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="expired"):
        authenticate_bearer_token(expired)


def test_production_oidc_requires_complete_configuration(monkeypatch):
    from zhenhu.inpatient.middleware.auth import validate_auth_configuration

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_ISSUER", "https://idp.example.test/realms/zhenhu")
    monkeypatch.setenv("AUTH_AUDIENCE", "zhenhu-inpatient")
    monkeypatch.delenv("AUTH_JWKS_URL", raising=False)

    with pytest.raises(RuntimeError, match="AUTH_JWKS_URL"):
        validate_auth_configuration()


@pytest.mark.asyncio
async def test_nurse_cannot_invoke_admin_write_operations():
    from zhenhu.inpatient import main

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/inpatient/clear-expired", headers={"x-role": "nurse"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dev_shortcut_login_requires_explicit_jwt_development_switch(monkeypatch):
    from zhenhu.inpatient.routes import admin, state_store

    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret")
    monkeypatch.setenv("AUTH_ISSUER", "zhenhu")
    monkeypatch.setenv("AUTH_AUDIENCE", "zhenhu-inpatient")
    monkeypatch.setenv("ENABLE_DEV_SHORTCUT_LOGIN", "true")
    monkeypatch.setattr(state_store, "get_org_all", lambda: [{
        "name": "测试主任",
        "title": "科主任",
        "department": "心内科",
        "role": "doctor",
        "job_number": "D-XN-001",
        "is_manager": True,
    }])

    response = await admin.dev_shortcut_login("cardiology-director")

    assert response.data["name"] == "测试主任"
    assert response.data["token"]
    monkeypatch.setattr(state_store, "get_org_all", lambda: [{
        "name": "呼吸科护士长",
        "title": "护士长",
        "department": "呼吸科",
        "role": "nurse",
        "job_number": "N-HX-001",
        "is_manager": True,
    }])
    respiratory_response = await admin.dev_shortcut_login("respiratory-head-nurse")
    assert respiratory_response.data["department"] == "呼吸科"
    monkeypatch.setenv("ENABLE_DEV_SHORTCUT_LOGIN", "false")
    with pytest.raises(HTTPException) as exc_info:
        await admin.dev_shortcut_login("cardiology-director")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_jwt_login_and_whoami_ignore_forged_identity_headers(monkeypatch):
    from zhenhu.inpatient import main
    from zhenhu.inpatient.routes import state_store

    identity = {
        "name": "可信医生",
        "title": "主治医师",
        "department": "心内科",
        "role": "doctor",
        "job_number": "D-XN-002",
        "is_manager": False,
    }
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-signing-secret")
    monkeypatch.setenv("AUTH_ISSUER", "zhenhu")
    monkeypatch.setenv("AUTH_AUDIENCE", "zhenhu-inpatient")
    monkeypatch.setattr(state_store, "verify_staff_credentials", lambda *_: identity)

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        login = await client.post("/inpatient/login", json={"job_number": "D-XN-002", "password": "ignored"})
        assert login.status_code == 200
        token = login.json()["data"]["token"]
        whoami = await client.get("/inpatient/whoami", headers={
            "Authorization": f"Bearer {token}",
            "x-role": "nurse",
            "x-user-id": "forged-user",
            "x-department": "forged-department",
        })

    assert whoami.status_code == 200
    data = whoami.json()["data"]
    assert data["actor_id"] == "D-XN-002"
    assert data["role"] == "doctor"
    assert data["department"] == "心内科"
