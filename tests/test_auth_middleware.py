from __future__ import annotations

import time

from fastapi.testclient import TestClient
from starlette.requests import Request

from edc_translation.api import app
from edc_translation.auth import (
    JsonTokenAuditStore,
    Principal,
    create_session_jwt,
    hash_api_token,
    issue_api_token,
    scopes_for_roles,
)
from edc_translation.auth_middleware import current_principal


def test_auth_middleware_disabled_mode_preserves_local_api(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "disabled")
    client = TestClient(app)

    response = client.get("/api/v1/translation/engines")

    assert response.status_code == 200


def test_auth_middleware_protected_mode_requires_bearer(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.delenv("EDC_STATIC_API_TOKEN_HASH", raising=False)
    monkeypatch.delenv("EDC_JWT_SECRET", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/translation/engines")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_disabled_auth_rejected_in_production_deployment(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "disabled")
    monkeypatch.setenv("EDC_DEPLOYMENT_ENV", "production")
    client = TestClient(app)

    response = client.get("/api/v1/translation/engines")

    assert response.status_code == 500
    assert "disabled auth is rejected" in response.json()["detail"]


def test_auth_middleware_accepts_static_hashed_api_token(monkeypatch):
    token = "edc_test_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "models:read")
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EDC-Tenant-ID": "tenant-a",
        },
    )

    assert response.status_code == 200


def test_auth_middleware_accepts_persisted_hashed_api_token(monkeypatch, tmp_path):
    issued = issue_api_token(
        tenant_id="tenant-a",
        scopes={"models:read"},
        created_by="svc-mcp",
        now=100,
    )
    store_path = tmp_path / "security-store.json"
    JsonTokenAuditStore(store_path).save_token(issued.record)
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_TOKEN_AUDIT_STORE_PATH", str(store_path))
    monkeypatch.delenv("EDC_STATIC_API_TOKEN_HASH", raising=False)
    monkeypatch.delenv("EDC_JWT_SECRET", raising=False)
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={"Authorization": f"Bearer {issued.plaintext_token}"},
    )

    events = JsonTokenAuditStore(store_path).list_audit_events(
        event_type="api_token.used"
    )
    assert response.status_code == 200
    assert events[0].subject == "svc-mcp"


def test_postgres_auth_backend_failure_does_not_fallback_to_static_token(monkeypatch):
    import edc_translation.postgres_backend as postgres_backend

    token = "edc_test_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_TRANSLATION_AUTH_STORE_BACKEND", "postgres")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "models:read")

    def fail_connect(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(postgres_backend, "make_postgres_token_store", fail_connect)
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "configured postgres auth store is unavailable"


def test_auth_route_scope_rejects_missing_scope(monkeypatch):
    token = "edc_test_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "translation:read")
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "models:read" in response.json()["detail"]


def test_auth_submit_text_binds_authenticated_tenant(monkeypatch):
    token = "edc_submit_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "translation:submit")
    client = TestClient(app)

    response = client.post(
        "/api/v1/translation/jobs/text",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "tenant_id": "tenant-a",
        },
    )

    assert response.status_code == 202
    assert response.json()["job"]["metadata"]["tenant_id"] == "tenant-a"


def test_auth_submit_text_rejects_cross_tenant_body(monkeypatch):
    token = "edc_submit_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "translation:submit")
    client = TestClient(app)

    response = client.post(
        "/api/v1/translation/jobs/text",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Hello",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "tenant_id": "tenant-b",
        },
    )

    assert response.status_code == 403


def test_auth_tenant_policy_rejects_cross_tenant_path(monkeypatch):
    token = "edc_policy_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "tenant:policy:read")
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/tenant-policy/tenant-b",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "tenant-a" in response.json()["detail"]
    assert "tenant-b" in response.json()["detail"]


def test_auth_model_validation_rejects_missing_scope(monkeypatch):
    token = "edc_model_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "models:read")
    client = TestClient(app)

    response = client.post(
        "/api/v1/translation/models/validate",
        headers={"Authorization": f"Bearer {token}"},
        json={"model_dir": "does-not-need-to-exist"},
    )

    assert response.status_code == 403
    assert "models:write" in response.json()["detail"]


def test_auth_middleware_rejects_cross_tenant_static_token(monkeypatch):
    token = "edc_test_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EDC-Tenant-ID": "tenant-b",
        },
    )

    assert response.status_code == 403


def test_auth_middleware_accepts_hmac_jwt(monkeypatch):
    secret = "test-secret"
    now = int(time.time())
    principal = Principal(
        subject="alice",
        tenant_id="tenant-a",
        roles=frozenset({"translator"}),
        scopes=scopes_for_roles(frozenset({"translator"})),
    )
    token = create_session_jwt(principal, secret=secret, now=now)
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_JWT_SECRET", secret)
    monkeypatch.delenv("EDC_STATIC_API_TOKEN_HASH", raising=False)
    client = TestClient(app)

    response = client.get(
        "/api/v1/translation/engines",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EDC-Tenant-ID": "tenant-a",
        },
    )

    assert response.status_code == 200


def test_current_principal_fails_closed_without_middleware_state(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    request = Request({"type": "http", "headers": []})

    try:
        current_principal(request)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("current_principal should fail closed in protected mode")


def test_oidc_mode_is_rejected_until_jwks_validation_exists(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "oidc")
    client = TestClient(app)

    response = client.get("/api/v1/translation/engines")

    assert response.status_code == 501
    assert "OIDC" in response.json()["detail"] or "oidc" in response.json()["detail"]
