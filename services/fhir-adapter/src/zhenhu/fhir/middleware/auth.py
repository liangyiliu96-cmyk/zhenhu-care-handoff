"""Authentication and identity establishment for the FHIR adapter service.

``header`` is a development-only compatibility mode. Production deployments
must use OIDC tokens verified against the configured JWKS endpoint.
"""

from __future__ import annotations

import os
from urllib.parse import unquote
from collections.abc import Iterable
from typing import Any

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient

_PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}
_jwks_clients: dict[str, PyJWKClient] = {}


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
                options={"verify_aud": False, "require": ["exp", "sub", "iss"]},
            )
        else:
            raise AuthenticationError("unsupported authentication mode")
    except ExpiredSignatureError as exc:
        raise AuthenticationError("access token expired") from exc
    except InvalidTokenError as exc:
        raise AuthenticationError("invalid access token") from exc
    except Exception as exc:
        raise AuthenticationError("access token verification failed") from exc

    if mode == "oidc":
        # Keycloak public client token 无 aud: 存在 aud 时兜底校验, 无 aud 时依赖 iss 校验
        token_aud = claims.get("aud")
        if token_aud and audience and audience not in (token_aud if isinstance(token_aud, list) else [token_aud]):
            raise AuthenticationError("audience mismatch")

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("access token is missing subject")
    roles = _roles_from_claims(claims)
    return {
        "actor_id": subject,
        "name": str(claims.get("name") or subject).strip(),
        "role": "doctor" if "doctor" in roles else "nurse" if "nurse" in roles else "",
        "roles": roles,
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
        mapped = {"doctor": "doctor", "physician": "doctor", "clinician": "doctor",
                  "nurse": "nurse", "nursing": "nurse"}.get(item.lower())
        if mapped:
            normalized.add(mapped)
    return normalized


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
    return {
        "actor_id": request.headers.get("x-user-id", "").strip() or None,
        "name": unquote(request.headers.get("x-user-name", "")).strip() or None,
        "role": role,
        "roles": {role} if role else set(),
        "auth_mode": "header",
        "claims": {},
    }


def _bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def role_middleware(request: Request, call_next):
    """Establish request identity and require a verified token for protected routes."""
    path = request.url.path
    mode = _auth_mode()

    if mode == "header":
        request.state.user_info = _header_user(request)
        return await call_next(request)

    if path in _PUBLIC_PATHS:
        return await call_next(request)

    token = _bearer_token(request)
    if not token:
        return JSONResponse(status_code=401, content={"error": "unauthorized", "message": "缺少 Bearer access token"})
    try:
        user = authenticate_bearer_token(token)
    except AuthenticationError as exc:
        return JSONResponse(status_code=401, content={"error": "unauthorized", "message": str(exc)})

    request.state.user_info = user
    return await call_next(request)
