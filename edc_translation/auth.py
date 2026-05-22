"""Dependency-light auth and security primitives for EDC_TRANSLATION.

This module provides locally testable auth primitives while keeping isolated
local use unauthenticated until enforcement is explicitly configured.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any


class AuthMode(StrEnum):
    DISABLED = "disabled"
    JWT_LDAP = "jwt_ldap"
    OIDC = "oidc"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class AuthError(ValueError):
    """Raised when credentials or authorization data are invalid."""


PRODUCTION_AUTH_MODES = frozenset({AuthMode.JWT_LDAP.value})


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    auth_type: str = "disabled"
    token_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["roles"] = sorted(self.roles)
        payload["scopes"] = sorted(self.scopes)
        return payload


@dataclass(frozen=True)
class ApiTokenRecord:
    token_id: str
    token_hash: str
    tenant_id: str
    scopes: frozenset[str]
    created_by: str
    created_at: int
    expires_at: int | None = None
    revoked_at: int | None = None
    last_used_at: int | None = None

    def is_active(self, now: int | None = None) -> bool:
        current = int(time.time()) if now is None else now
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > current

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scopes"] = sorted(self.scopes)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ApiTokenRecord:
        return cls(
            token_id=str(payload["token_id"]),
            token_hash=str(payload["token_hash"]),
            tenant_id=str(payload["tenant_id"]),
            scopes=frozenset(str(scope) for scope in payload.get("scopes", [])),
            created_by=str(payload["created_by"]),
            created_at=int(payload["created_at"]),
            expires_at=_optional_int(payload.get("expires_at")),
            revoked_at=_optional_int(payload.get("revoked_at")),
            last_used_at=_optional_int(payload.get("last_used_at")),
        )


@dataclass(frozen=True)
class IssuedApiToken:
    plaintext_token: str
    record: ApiTokenRecord


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    outcome: AuditOutcome
    tenant_id: str
    subject: str
    resource: str
    timestamp: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuditEvent:
        return cls(
            event_type=str(payload["event_type"]),
            outcome=AuditOutcome(str(payload["outcome"])),
            tenant_id=str(payload["tenant_id"]),
            subject=str(payload["subject"]),
            resource=str(payload["resource"]),
            timestamp=int(payload["timestamp"]),
            details=dict(payload.get("details", {})),
        )


@dataclass(frozen=True)
class LdapConfig:
    url: str
    user_search_base: str
    group_search_base: str
    bind_dn_env: str = "EDC_LDAP_BIND_DN"
    bind_password_env: str = "EDC_LDAP_BIND_PASSWORD"

    def missing_secret_env(self) -> list[str]:
        return [
            name
            for name in (self.bind_dn_env, self.bind_password_env)
            if not os.getenv(name)
        ]


ROLE_SCOPES: dict[str, frozenset[str]] = {
    "viewer": frozenset(
        {
            "translation:read",
            "evidence:read",
            "models:read",
        }
    ),
    "translator": frozenset(
        {
            "translation:read",
            "translation:submit",
            "evidence:read",
            "models:read",
        }
    ),
    "reviewer": frozenset(
        {
            "translation:read",
            "reviews:write",
            "evidence:read",
            "models:read",
        }
    ),
    "tenant_admin": frozenset(
        {
            "translation:read",
            "translation:submit",
            "reviews:write",
            "tenant:policy:read",
            "tenant:policy:write",
            "tokens:write",
            "audit:read",
            "evidence:read",
            "models:read",
        }
    ),
    "model_admin": frozenset(
        {
            "models:read",
            "models:write",
            "audit:read",
        }
    ),
}

MCP_TOOL_SCOPES: dict[str, str] = {
    "translation_list_engines": "models:read",
    "translation_submit_bundle": "translation:submit",
    "translation_submit_text": "translation:submit",
    "translation_get_job_status": "translation:read",
    "translation_get_bundle": "translation:read",
    "translation_score_pair": "translation:read",
    "translation_validate_model_bundle": "models:write",
    "translation_get_evidence_bundle": "evidence:read",
    "translation_validate_custody": "evidence:read",
    "translation_live_smoke": "models:read",
    "translation_rank_local_models": "models:read",
    "translation_discover_env": "audit:read",
    "translation_release_readiness_status": "audit:read",
}


def disabled_auth_principal(tenant_id: str = "standalone") -> Principal:
    scopes = frozenset().union(*ROLE_SCOPES.values())
    return Principal(
        subject="local-dev-disabled-auth",
        tenant_id=tenant_id,
        roles=frozenset({"tenant_admin", "model_admin"}),
        scopes=scopes,
        auth_type=AuthMode.DISABLED.value,
    )


def is_production_auth_mode(mode: str) -> bool:
    return mode.strip().lower() in PRODUCTION_AUTH_MODES


def require_production_auth_mode(mode: str) -> None:
    normalized = mode.strip().lower()
    if normalized == AuthMode.DISABLED.value:
        raise AuthError("disabled auth is dev-only and cannot satisfy production evidence")
    if normalized not in PRODUCTION_AUTH_MODES:
        raise AuthError(f"unsupported production auth mode: {mode}")


def scopes_for_roles(roles: set[str] | frozenset[str]) -> frozenset[str]:
    scopes: set[str] = set()
    for role in roles:
        scopes.update(ROLE_SCOPES.get(role, frozenset()))
    return frozenset(scopes)


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise AuthError(f"principal lacks required scope: {scope}")


def require_tenant(principal: Principal, tenant_id: str) -> None:
    if principal.tenant_id != tenant_id:
        raise AuthError(
            f"principal tenant {principal.tenant_id!r} cannot access {tenant_id!r}"
        )


def require_mcp_tool_scope(principal: Principal, tool_name: str) -> None:
    scope = MCP_TOOL_SCOPES.get(tool_name)
    if scope is None:
        raise AuthError(f"unknown MCP tool for auth mapping: {tool_name}")
    require_scope(principal, scope)


def hash_api_token(token: str, salt: bytes | None = None) -> str:
    token_salt = secrets.token_bytes(16) if salt is None else salt
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        token_salt,
        210_000,
    )
    return (
        "pbkdf2_sha256$210000$"
        f"{base64.urlsafe_b64encode(token_salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def verify_api_token(token: str, stored_hash: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256" or rounds != "210000":
        return False
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    expected = hash_api_token(token, salt=salt)
    return hmac.compare_digest(expected, stored_hash)


def issue_api_token(
    *,
    tenant_id: str,
    scopes: set[str] | frozenset[str],
    created_by: str,
    ttl_seconds: int | None = None,
    now: int | None = None,
) -> IssuedApiToken:
    current = int(time.time()) if now is None else now
    token_id = f"tok_{secrets.token_urlsafe(12)}"
    plaintext = f"edc_{secrets.token_urlsafe(32)}"
    record = ApiTokenRecord(
        token_id=token_id,
        token_hash=hash_api_token(plaintext),
        tenant_id=tenant_id,
        scopes=frozenset(scopes),
        created_by=created_by,
        created_at=current,
        expires_at=None if ttl_seconds is None else current + ttl_seconds,
    )
    return IssuedApiToken(plaintext_token=plaintext, record=record)


def principal_from_api_token(
    token: str,
    records: list[ApiTokenRecord],
    *,
    now: int | None = None,
) -> Principal:
    for record in records:
        if verify_api_token(token, record.token_hash):
            if not record.is_active(now=now):
                raise AuthError("API token is expired or revoked")
            return Principal(
                subject=record.created_by,
                tenant_id=record.tenant_id,
                scopes=record.scopes,
                auth_type="api_token",
                token_id=record.token_id,
            )
    raise AuthError("API token was not found")


class JsonTokenAuditStore:
    """Small repo-local durable token/audit store for tests and security evidence."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def save_token(self, record: ApiTokenRecord) -> ApiTokenRecord:
        with self._lock:
            payload = self._load()
            tokens = [
                token
                for token in payload["tokens"]
                if str(token.get("token_id")) != record.token_id
            ]
            tokens.append(record.to_dict())
            payload["tokens"] = tokens
            self._save(payload)
        return record

    def list_tokens(self, *, tenant_id: str | None = None) -> list[ApiTokenRecord]:
        with self._lock:
            payload = self._load()
        records = [ApiTokenRecord.from_dict(token) for token in payload["tokens"]]
        if tenant_id is None:
            return records
        return [record for record in records if record.tenant_id == tenant_id]

    def record_audit_event(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            payload = self._load()
            payload["audit_events"].append(event.to_dict())
            self._save(payload)
        return event

    def list_audit_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]:
        with self._lock:
            payload = self._load()
        events = [AuditEvent.from_dict(event) for event in payload["audit_events"]]
        if tenant_id is not None:
            events = [event for event in events if event.tenant_id == tenant_id]
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        return events

    def revoke_token(
        self,
        token_id: str,
        *,
        principal: Principal,
        now: int | None = None,
    ) -> ApiTokenRecord:
        current = int(time.time()) if now is None else now
        with self._lock:
            payload = self._load()
            records = [ApiTokenRecord.from_dict(token) for token in payload["tokens"]]
            replacement: ApiTokenRecord | None = None
            updated: list[dict[str, Any]] = []
            for record in records:
                if record.token_id == token_id:
                    replacement = ApiTokenRecord(
                        token_id=record.token_id,
                        token_hash=record.token_hash,
                        tenant_id=record.tenant_id,
                        scopes=record.scopes,
                        created_by=record.created_by,
                        created_at=record.created_at,
                        expires_at=record.expires_at,
                        revoked_at=current,
                        last_used_at=record.last_used_at,
                    )
                    updated.append(replacement.to_dict())
                else:
                    updated.append(record.to_dict())
            if replacement is None:
                raise AuthError(f"API token not found for revocation: {token_id}")
            payload["tokens"] = updated
            payload["audit_events"].append(
                audit_event(
                    event_type="api_token.revoked",
                    outcome=AuditOutcome.SUCCESS,
                    principal=principal,
                    resource=token_id,
                    now=current,
                ).to_dict()
            )
            self._save(payload)
        return replacement

    def principal_from_token(
        self,
        token: str,
        *,
        now: int | None = None,
    ) -> Principal:
        current = int(time.time()) if now is None else now
        with self._lock:
            payload = self._load()
            records = [ApiTokenRecord.from_dict(item) for item in payload["tokens"]]
            for record in records:
                if not verify_api_token(token, record.token_hash):
                    continue
                if not record.is_active(now=current):
                    principal = Principal(
                        subject=record.created_by,
                        tenant_id=record.tenant_id,
                        scopes=record.scopes,
                        auth_type="api_token",
                        token_id=record.token_id,
                    )
                    payload["audit_events"].append(
                        audit_event(
                            event_type="api_token.denied",
                            outcome=AuditOutcome.DENIED,
                            principal=principal,
                            resource=record.token_id,
                            details={"reason": "expired_or_revoked"},
                            now=current,
                        ).to_dict()
                    )
                    self._save(payload)
                    raise AuthError("API token is expired or revoked")
                updated = ApiTokenRecord(
                    token_id=record.token_id,
                    token_hash=record.token_hash,
                    tenant_id=record.tenant_id,
                    scopes=record.scopes,
                    created_by=record.created_by,
                    created_at=record.created_at,
                    expires_at=record.expires_at,
                    revoked_at=record.revoked_at,
                    last_used_at=current,
                )
                payload["tokens"] = [
                    updated.to_dict() if item.token_id == record.token_id else item.to_dict()
                    for item in records
                ]
                principal = Principal(
                    subject=record.created_by,
                    tenant_id=record.tenant_id,
                    scopes=record.scopes,
                    auth_type="api_token",
                    token_id=record.token_id,
                )
                payload["audit_events"].append(
                    audit_event(
                        event_type="api_token.used",
                        outcome=AuditOutcome.SUCCESS,
                        principal=principal,
                        resource=record.token_id,
                        now=current,
                    ).to_dict()
                )
                self._save(payload)
                return principal
        raise AuthError("API token was not found")

    # Protocol compliance for stores.TokenStore and stores.AuditStore
    # (structural; enables DEFAULT_TOKEN_STORE / DEFAULT_AUDIT_STORE wiring
    #  and uniform use of JsonTokenAuditStore as a durable backend impl)
    def save(self, record: ApiTokenRecord) -> ApiTokenRecord:
        return self.save_token(record)

    def list(self, *, tenant_id: str | None = None) -> list[ApiTokenRecord]:
        return self.list_tokens(tenant_id=tenant_id)

    def get(self, token_id: str) -> ApiTokenRecord:
        for r in self.list_tokens():
            if r.token_id == token_id:
                return r
        raise KeyError(f"API token not found: {token_id}")

    def record(self, event: AuditEvent) -> AuditEvent:
        return self.record_audit_event(event)

    def list_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]:
        return self.list_audit_events(tenant_id=tenant_id, event_type=event_type)

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.is_file():
            return {"tokens": [], "audit_events": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "tokens": list(payload.get("tokens", [])),
            "audit_events": list(payload.get("audit_events", [])),
        }

    def _save(self, payload: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)


def create_session_jwt(
    principal: Principal,
    *,
    secret: str,
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> str:
    current = int(time.time()) if now is None else now
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": principal.subject,
        "tenant_id": principal.tenant_id,
        "roles": sorted(principal.roles),
        "scopes": sorted(principal.scopes),
        "iat": current,
        "exp": current + ttl_seconds,
    }
    signing_input = ".".join((_b64_json(header), _b64_json(payload)))
    signature = _b64_bytes(
        hmac.new(
            secret.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    return f"{signing_input}.{signature}"


def principal_from_session_jwt(
    token: str,
    *,
    secret: str,
    now: int | None = None,
) -> Principal:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
    except ValueError as exc:
        raise AuthError("JWT must have three segments") from exc
    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _b64_bytes(
        hmac.new(
            secret.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(expected_signature, encoded_signature):
        raise AuthError("JWT signature verification failed")
    header = _json_from_b64(encoded_header)
    if header.get("alg") != "HS256":
        raise AuthError("JWT algorithm is not supported")
    payload = _json_from_b64(encoded_payload)
    current = int(time.time()) if now is None else now
    if int(payload["exp"]) <= current:
        raise AuthError("JWT is expired")
    return Principal(
        subject=str(payload["sub"]),
        tenant_id=str(payload["tenant_id"]),
        roles=frozenset(str(role) for role in payload.get("roles", [])),
        scopes=frozenset(str(scope) for scope in payload.get("scopes", [])),
        auth_type="jwt",
    )


class InMemoryAuditSink:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

    def list_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]:
        events = self._events
        if tenant_id is not None:
            events = [event for event in events if event.tenant_id == tenant_id]
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        return list(events)


def audit_event(
    *,
    event_type: str,
    outcome: AuditOutcome,
    principal: Principal,
    resource: str,
    details: dict[str, Any] | None = None,
    now: int | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        outcome=outcome,
        tenant_id=principal.tenant_id,
        subject=principal.subject,
        resource=resource,
        timestamp=int(time.time()) if now is None else now,
        details=details or {},
    )


def _b64_json(payload: dict[str, Any]) -> str:
    return _b64_bytes(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _b64_bytes(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _json_from_b64(payload: str) -> dict[str, Any]:
    padding = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
