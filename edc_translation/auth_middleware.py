"""FastAPI auth middleware with explicit disabled-local default."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from edc_translation.auth import (
    ApiTokenRecord,
    AuditOutcome,
    AuthError,
    AuthMode,
    JsonTokenAuditStore,
    Principal,
    audit_event,
    disabled_auth_principal,
    principal_from_api_token,
    principal_from_session_jwt,
    require_tenant,
    require_scope,
    verify_api_token,
)
from .service import DEFAULT_AUDIT_STORE  # enables audit on tenant binding for durable auth paths (Auth tranche)


PUBLIC_PATHS = {
    "/health",
    "/healthz",
    "/readyz",
    "/docs",
    "/openapi.json",
}


class PrincipalAuthMiddleware(BaseHTTPMiddleware):
    """Attach a principal in local mode and enforce bearer auth when enabled."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        mode = os.getenv("EDC_AUTH_MODE", AuthMode.DISABLED.value).strip().lower()
        if mode == AuthMode.DISABLED.value:
            deployment_env = os.getenv("EDC_DEPLOYMENT_ENV", "local").strip().lower()
            if deployment_env in {"production", "prod", "approved_staging", "staging"}:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "disabled auth is rejected outside local/dev"},
                )
            request.state.principal = disabled_auth_principal(
                tenant_id=request.headers.get("X-EDC-Tenant-ID", "standalone")
            )
            return await call_next(request)

        if mode == AuthMode.OIDC.value:
            return JSONResponse(
                status_code=501,
                content={"detail": "EDC_AUTH_MODE=oidc requires OIDC/JWKS validation before use"},
            )
        if mode != AuthMode.JWT_LDAP.value:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Unsupported EDC_AUTH_MODE: {mode}"},
            )

        try:
            principal = _principal_from_authorization(request)
        except AuthError as exc:
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
            )
        if principal is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        tenant_id = request.headers.get("X-EDC-Tenant-ID")
        if tenant_id:
            try:
                require_tenant(principal, tenant_id)
            except AuthError as exc:
                return JSONResponse(status_code=403, content={"detail": str(exc)})

        request.state.principal = principal
        return await call_next(request)


def _principal_from_authorization(request: Request) -> Principal | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None

    # Durable postgres-backed token + audit path (wired for Auth tranche)
    auth_backend = os.getenv("EDC_TRANSLATION_AUTH_STORE_BACKEND", "").strip().lower()
    if auth_backend == "postgres":
        try:
            from .postgres_backend import make_postgres_audit_store, make_postgres_token_store

            ts = make_postgres_token_store()
            records = ts.list()
            p = principal_from_api_token(token, records)
            # Mirror JsonTokenAuditStore side-effects: update last_used + durable audit record
            if p and p.token_id:
                now = int(time.time())
                try:
                    rec = ts.get(p.token_id)
                    updated = ApiTokenRecord(
                        token_id=rec.token_id,
                        token_hash=rec.token_hash,
                        tenant_id=rec.tenant_id,
                        scopes=rec.scopes,
                        created_by=rec.created_by,
                        created_at=rec.created_at,
                        expires_at=rec.expires_at,
                        revoked_at=rec.revoked_at,
                        last_used_at=now,
                    )
                    ts.save(updated)
                except Exception:
                    pass
                try:
                    audit = make_postgres_audit_store()
                    ev = audit_event(
                        event_type="api_token.used",
                        outcome=AuditOutcome.SUCCESS,
                        principal=Principal(
                            subject=p.subject,
                            tenant_id=p.tenant_id,
                            scopes=p.scopes,
                            auth_type=p.auth_type,
                            token_id=p.token_id,
                        ),
                        resource=p.token_id or "unknown",
                        now=now,
                    )
                    audit.record(ev)
                except Exception:
                    pass
            return p
        except AuthError:
            return None
        except Exception:
            # A configured durable auth backend must fail closed. Falling back
            # to static or JWT-only auth would hide broken production evidence.
            raise AuthError("configured postgres auth store is unavailable")

    store_path = os.getenv("EDC_TOKEN_AUDIT_STORE_PATH", "").strip()
    if store_path:
        try:
            return JsonTokenAuditStore(store_path).principal_from_token(token)
        except AuthError:
            pass

    static_hash = os.getenv("EDC_STATIC_API_TOKEN_HASH", "").strip()
    if static_hash and verify_api_token(token, static_hash):
        scopes = frozenset(
            scope.strip()
            for scope in os.getenv("EDC_STATIC_API_TOKEN_SCOPES", "").split(",")
            if scope.strip()
        )
        return Principal(
            subject=os.getenv("EDC_STATIC_API_TOKEN_SUBJECT", "static-api-token"),
            tenant_id=os.getenv("EDC_STATIC_API_TOKEN_TENANT", "standalone"),
            scopes=scopes,
            auth_type="api_token",
            token_id="static",
        )

    jwt_secret = os.getenv("EDC_JWT_SECRET", "").strip()
    if jwt_secret:
        try:
            return principal_from_session_jwt(token, secret=jwt_secret)
        except AuthError:
            return None
    return None


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, Principal):
        return principal
    mode = os.getenv("EDC_AUTH_MODE", AuthMode.DISABLED.value).strip().lower()
    if mode != AuthMode.DISABLED.value:
        raise HTTPException(status_code=401, detail="Authentication required")
    return disabled_auth_principal()


def require_route_scope(principal: Principal, scope: str) -> None:
    try:
        require_scope(principal, scope)
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def bind_request_tenant(principal: Principal, requested_tenant: str | None) -> str:
    """Resolve tenant for the request.

    Contract per Auth tranche: tenant always comes from the authenticated
    Principal for non-disabled modes (never arbitrary caller-supplied value).
    In disabled (local-dev) mode, caller-supplied tenant_id is permitted for
    multi-tenant simulation. Admin paths (e.g. tenant-policy) follow the same
    binding; cross-tenant access for admins is future extension with explicit
    audit + super-admin role.
    """
    effective = requested_tenant or principal.tenant_id
    if principal.auth_type == AuthMode.DISABLED.value:
        # local dev flexibility; still audit the choice for evidence
        try:
            DEFAULT_AUDIT_STORE.record(
                audit_event(
                    event_type="tenant.resolved",
                    outcome=AuditOutcome.SUCCESS,
                    principal=principal,
                    resource=effective,
                    details={"requested": requested_tenant, "source": "disabled-override"},
                )
            )
        except Exception:
            pass
        return effective
    if requested_tenant and requested_tenant != principal.tenant_id:
        # record denied cross-tenant attempt (audit durable when postgres backend)
        try:
            DEFAULT_AUDIT_STORE.record(
                audit_event(
                    event_type="tenant.denied",
                    outcome=AuditOutcome.DENIED,
                    principal=principal,
                    resource=requested_tenant,
                    details={"principal_tenant": principal.tenant_id},
                )
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=403,
            detail=(
                f"principal tenant {principal.tenant_id!r} cannot access "
                f"{requested_tenant!r}"
            ),
        )
    # normal case: from principal, audit for durable trail
    try:
        DEFAULT_AUDIT_STORE.record(
            audit_event(
                event_type="tenant.resolved",
                outcome=AuditOutcome.SUCCESS,
                principal=principal,
                resource=principal.tenant_id,
                details={"requested": requested_tenant, "source": "principal"},
            )
        )
    except Exception:
        pass
    return principal.tenant_id
