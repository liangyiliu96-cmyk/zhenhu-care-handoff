"""Authentication and role enforcement for the inpatient service.

``header`` is a development-only compatibility mode. Production deployments
must use OIDC tokens verified against the configured JWKS endpoint.
"""

from __future__ import annotations

import os
import re
from urllib.parse import unquote
from collections.abc import Iterable
from typing import Any

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient

_DOCTOR_ONLY = [
    "/review/", "/command/", "/discharge/", "/inpatient/review/",
    "/inpatient/command/", "/inpatient/discharge/",
    "/inpatient/fixtures/load/",
    "/v1/review/", "/v1/command/", "/v1/discharge/", "/v1/inpatient/review/",
    "/v1/inpatient/command/", "/v1/inpatient/discharge/",
]
_SHARED = [
    "/admissions/", "/monitoring/", "/ward/", "/reviews/", "/dashboard/",
    "/nurse/", "/patients/", "/inpatient/admissions/", "/inpatient/monitoring/",
    "/inpatient/dashboard/",
    "/v1/admissions/", "/v1/monitoring/", "/v1/ward/", "/v1/reviews/", "/v1/dashboard/",
    "/v1/nurse/", "/v1/patients/", "/v1/inpatient/admissions/", "/v1/inpatient/monitoring/",
    "/v1/inpatient/dashboard/",
]
_ALLOWED_ROLES = {"doctor", "nurse"}
_PUBLIC_PATHS = {
    "/health",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/assistant/public/quick-questions",
    "/assistant/public/chat/stream",
}
_JWT_LOGIN_PATHS = {
    "/inpatient/login",
    "/v1/inpatient/login",
    "/inpatient/login/dev-shortcut",
    "/v1/inpatient/login/dev-shortcut",
}
_ROLE_ALIASES = {
    "doctor": "doctor", "physician": "doctor", "clinician": "doctor",
    "nurse": "nurse", "nursing": "nurse",
}
_jwks_clients: dict[str, PyJWKClient] = {}
_PATIENT_PATH_PATTERNS = (
    re.compile(r"^/v1/inpatient/(?:admissions|monitoring|review|discharge)/(?P<patient_id>[^/]+)(?:/|$)"),
    re.compile(r"^/v1/(?:review|monitoring|discharge|dashboard)/(?P<patient_id>[^/]+)(?:/|$)"),
    re.compile(r"^/v1/inpatient/(?P<patient_id>(?!admissions$|monitoring$|review$|discharge$)[^/]+)(?:/|$)"),
    re.compile(r"^/inpatient/(?:admissions|monitoring|review|discharge)/(?P<patient_id>[^/]+)(?:/|$)"),
    re.compile(r"^/(?:review|monitoring|discharge|dashboard)/(?P<patient_id>[^/]+)(?:/|$)"),
    re.compile(r"^/inpatient/(?P<patient_id>(?!admissions$|monitoring$|review$|discharge$)[^/]+)(?:/|$)"),
)


class AuthenticationError(Exception):
    """Raised when a bearer token cannot establish an authenticated identity."""


def _environment() -> str:
    return os.environ.get("APP_ENV", "dev").strip().lower()


def _auth_mode() -> str:
    return os.environ.get("AUTH_MODE", "header").strip().lower()


def validate_auth_configuration() -> None:
    """Validate authentication configuration before accepting requests."""
    environment = _environment()
    mode = _auth_mode()
    if mode not in {"header", "jwt", "oidc"}:
        raise RuntimeError("AUTH_MODE must be one of: header, jwt, oidc")
    if environment == "production" and mode != "oidc":
        raise RuntimeError(
            "Production requires a verified authentication provider: AUTH_MODE=oidc; "
            "demo/header and shared-secret JWT auth are forbidden."
        )
    if mode == "header":
        return

    required = ("AUTH_ISSUER", "AUTH_AUDIENCE")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if mode == "oidc" and not os.environ.get("AUTH_JWKS_URL", "").strip():
        missing.append("AUTH_JWKS_URL")
    if mode == "jwt" and not os.environ.get("AUTH_JWT_SECRET", "").strip():
        missing.append("AUTH_JWT_SECRET")
    if missing:
        raise RuntimeError(f"{mode} authentication requires: {', '.join(missing)}")


def authenticate_bearer_token(token: str) -> dict[str, Any]:
    """Verify a bearer token and map trusted claims to the request identity."""
    mode = _auth_mode()
    if mode == "header":
        raise AuthenticationError("bearer authentication is not enabled")

    issuer = os.environ.get("AUTH_ISSUER", "").strip()
    audience = os.environ.get("AUTH_AUDIENCE", "").strip()
    try:
        if mode == "jwt":
            claims = jwt.decode(
                token,
                os.environ.get("AUTH_JWT_SECRET", ""),
                algorithms=["HS256"],
                issuer=issuer,
                audience=audience,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        elif mode == "oidc":
            jwks_url = os.environ.get("AUTH_JWKS_URL", "").strip()
            client = _jwks_clients.setdefault(jwks_url, PyJWKClient(jwks_url))
            signing_key = client.get_signing_key_from_jwt(token).key
            algorithms = [item.strip() for item in os.environ.get("AUTH_JWT_ALGORITHMS", "RS256,ES256").split(",") if item.strip()]
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=algorithms,
                issuer=issuer,
                audience=audience,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        else:
            raise AuthenticationError("unsupported authentication mode")
    except ExpiredSignatureError as exc:
        raise AuthenticationError("access token expired") from exc
    except InvalidTokenError as exc:
        raise AuthenticationError("invalid access token") from exc
    except Exception as exc:
        raise AuthenticationError("access token verification failed") from exc

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("access token is missing subject")
    roles = _roles_from_claims(claims)
    departments = _departments_from_claims(claims)
    return {
        "actor_id": subject,
        "name": str(claims.get("name") or subject).strip(),
        "role": "doctor" if "doctor" in roles else "nurse" if "nurse" in roles else "",
        "roles": roles,
        "title": str(claims.get("title") or "").strip(),
        "department": next(iter(departments), None),
        "departments": departments,
        "auth_mode": mode,
        "claims": {key: value for key, value in claims.items() if key not in {"actor_id", "user_id", "id"}},
    }


def _roles_from_claims(claims: dict[str, Any]) -> set[str]:
    values: list[Any] = [claims.get("roles"), claims.get("role")]
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        values.append(realm_access.get("roles"))
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        for resource in resource_access.values():
            if isinstance(resource, dict):
                values.append(resource.get("roles"))
    normalized = set()
    for item in _flatten_strings(values):
        mapped = _ROLE_ALIASES.get(item.lower())
        if mapped:
            normalized.add(mapped)
    return normalized


def _departments_from_claims(claims: dict[str, Any]) -> set[str]:
    return {item.lower() for item in _flatten_strings([claims.get("departments"), claims.get("department")])}


def _flatten_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.extend(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple, set)):
            result.extend(str(item).strip() for item in value if str(item).strip())
    return result


def _header_user(request: Request) -> dict[str, Any]:
    role = unquote(request.headers.get("x-role", "")).strip().lower()
    if not role and _environment() == "dev":
        role = "doctor"
    department_values = _flatten_strings([unquote(request.headers.get("x-department", ""))])
    departments = {item.lower() for item in department_values}
    return {
        "actor_id": request.headers.get("x-user-id", "").strip() or None,
        "name": unquote(request.headers.get("x-user-name", "")).strip() or None,
        "role": role,
        "roles": {role} if role else set(),
        "title": unquote(request.headers.get("x-title", "")).strip() or {"doctor": "医生", "nurse": "护士"}.get(role, ""),
        "department": next(iter(departments), None),
        "departments": departments,
        "auth_mode": "header",
        "claims": {},
    }


def _is_role_protected(path: str, method: str = "GET") -> tuple[bool, bool]:
    normalized_path = path.removeprefix("/v1")
    is_patient_command = normalized_path.startswith("/inpatient/") and normalized_path.endswith("/command")
    is_patient_care_action = normalized_path.startswith("/inpatient/") and "/care/" in normalized_path
    is_assistant_action_draft = normalized_path.startswith("/inpatient/") and "/assistant-action-drafts" in normalized_path
    is_patient_alert_path = normalized_path.startswith("/inpatient/") and "/alerts" in normalized_path
    is_patient_alert_action = is_patient_alert_path and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    doctor_only = is_patient_command or is_patient_care_action or is_assistant_action_draft or is_patient_alert_action or any(
        path.startswith(prefix) or path == prefix.rstrip("/") for prefix in _DOCTOR_ONLY
    )
    shared = is_patient_alert_path or any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in _SHARED)
    return doctor_only, shared


def _bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _patient_id_from_path(path: str) -> str | None:
    for pattern in _PATIENT_PATH_PATTERNS:
        match = pattern.match(path)
        if match:
            return match.group("patient_id")
    return None


async def role_middleware(request: Request, call_next):
    """Establish request identity and enforce endpoint role requirements."""
    path = request.url.path
    mode = _auth_mode()
    doctor_only, shared = _is_role_protected(path, request.method)

    if mode == "header":
        user = _header_user(request)
        if (doctor_only or shared) and not user["role"]:
            return JSONResponse(status_code=401, content={"error": "unauthorized", "message": "缺少认证身份"})
    elif path in _PUBLIC_PATHS or (mode == "jwt" and any(path == login_path or path.startswith(f"{login_path}/") for login_path in _JWT_LOGIN_PATHS)):
        return await call_next(request)
    else:
        token = _bearer_token(request)
        if not token:
            return JSONResponse(status_code=401, content={"error": "unauthorized", "message": "缺少 Bearer access token"})
        try:
            user = authenticate_bearer_token(token)
        except AuthenticationError as exc:
            return JSONResponse(status_code=401, content={"error": "unauthorized", "message": str(exc)})

    request.state.user_info = user
    roles = user["roles"]
    if doctor_only and "doctor" not in roles:
        return JSONResponse(status_code=403, content={"error": "forbidden", "message": "该操作需要 doctor 角色"})
    if shared and not roles.intersection(_ALLOWED_ROLES):
        return JSONResponse(status_code=403, content={"error": "forbidden", "message": "该操作需要临床角色"})
    patient_id = _patient_id_from_path(path)
    if patient_id:
        from ..services.patient_access import PatientAccessDeniedError, require_patient_access

        try:
            require_patient_access(patient_id, user)
        except PatientAccessDeniedError:
            return JSONResponse(status_code=403, content={"error": "forbidden", "message": "无权访问该患者记录"})
    return await call_next(request)
