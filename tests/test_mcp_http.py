from __future__ import annotations

from fastapi.testclient import TestClient

from edc_translation.auth import hash_api_token
from edc_translation.mcp_http import app


def test_mcp_http_health_and_tool_call_in_disabled_mode(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "disabled")
    client = TestClient(app)

    assert client.get("/healthz").json() == {"status": "ok"}
    tools = client.get("/mcp/tools")
    assert tools.status_code == 200
    assert tools.json()["tools"]

    response = client.post(
        "/mcp/call",
        json={
            "name": "translation_submit_text",
            "arguments": {
                "text": "Hello",
                "source_language": "en",
                "target_language": "fr",
                "provider_id": "deterministic_ci",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "succeeded"


def test_mcp_http_protected_mode_requires_token(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.delenv("EDC_STATIC_API_TOKEN_HASH", raising=False)
    client = TestClient(app)

    response = client.get("/mcp/tools")

    assert response.status_code == 401


def test_mcp_http_uses_mcp_scope_mapping(monkeypatch):
    token = "edc_mcp_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "translation:submit")
    client = TestClient(app)

    response = client.post(
        "/mcp/call",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "translation_submit_text",
            "arguments": {
                "text": "Hello",
                "source_language": "en",
                "target_language": "fr",
                "provider_id": "deterministic_ci",
                "tenant_id": "tenant-a",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["job"]["metadata"]["tenant_id"] == "tenant-a"


def test_mcp_http_tool_listing_requires_models_scope(monkeypatch):
    token = "edc_mcp_limited_token"
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_HASH", hash_api_token(token))
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_TENANT", "tenant-a")
    monkeypatch.setenv("EDC_STATIC_API_TOKEN_SCOPES", "translation:submit")
    client = TestClient(app)

    response = client.get(
        "/mcp/tools",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "models:read" in response.json()["detail"]
