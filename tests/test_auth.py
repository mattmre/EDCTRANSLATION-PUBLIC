from __future__ import annotations

import pytest

from edc_translation.auth import (
    AuditOutcome,
    AuthError,
    InMemoryAuditSink,
    JsonTokenAuditStore,
    LdapConfig,
    Principal,
    audit_event,
    create_session_jwt,
    disabled_auth_principal,
    hash_api_token,
    issue_api_token,
    is_production_auth_mode,
    principal_from_api_token,
    principal_from_session_jwt,
    require_production_auth_mode,
    require_mcp_tool_scope,
    require_scope,
    require_tenant,
    scopes_for_roles,
    verify_api_token,
)


def test_api_token_hash_does_not_store_plaintext_and_verifies():
    token = "edc_example_token"
    stored_hash = hash_api_token(token)

    assert token not in stored_hash
    assert verify_api_token(token, stored_hash) is True
    assert verify_api_token("wrong-token", stored_hash) is False


def test_issue_api_token_binds_tenant_scopes_and_expiry():
    issued = issue_api_token(
        tenant_id="tenant-a",
        scopes={"translation:submit"},
        created_by="alice",
        ttl_seconds=60,
        now=100,
    )

    principal = principal_from_api_token(
        issued.plaintext_token,
        [issued.record],
        now=120,
    )

    assert principal.subject == "alice"
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"translation:submit"})
    assert principal.token_id == issued.record.token_id

    with pytest.raises(AuthError, match="expired or revoked"):
        principal_from_api_token(issued.plaintext_token, [issued.record], now=161)


def test_json_token_audit_store_persists_hash_revocation_and_audit(tmp_path):
    store_path = tmp_path / "security-store.json"
    store = JsonTokenAuditStore(store_path)
    issued = issue_api_token(
        tenant_id="tenant-a",
        scopes={"translation:submit"},
        created_by="alice",
        ttl_seconds=300,
        now=100,
    )

    store.save_token(issued.record)
    principal = store.principal_from_token(issued.plaintext_token, now=120)
    raw = store_path.read_text(encoding="utf-8")

    assert issued.plaintext_token not in raw
    assert principal.tenant_id == "tenant-a"
    assert store.list_tokens()[0].last_used_at == 120
    assert store.list_audit_events(event_type="api_token.used")[0].resource == (
        issued.record.token_id
    )

    store.revoke_token(issued.record.token_id, principal=principal, now=130)

    with pytest.raises(AuthError, match="expired or revoked"):
        store.principal_from_token(issued.plaintext_token, now=140)
    assert store.list_tokens()[0].revoked_at == 130
    assert store.list_audit_events(event_type="api_token.revoked")
    assert store.list_audit_events(event_type="api_token.denied")


def test_jwt_session_round_trip_and_expiry():
    principal = Principal(
        subject="alice",
        tenant_id="tenant-a",
        roles=frozenset({"translator"}),
        scopes=scopes_for_roles(frozenset({"translator"})),
        auth_type="ldap",
    )

    token = create_session_jwt(
        principal,
        secret="test-secret",
        ttl_seconds=60,
        now=100,
    )
    parsed = principal_from_session_jwt(token, secret="test-secret", now=120)

    assert parsed.subject == "alice"
    assert parsed.tenant_id == "tenant-a"
    assert "translation:submit" in parsed.scopes

    with pytest.raises(AuthError, match="expired"):
        principal_from_session_jwt(token, secret="test-secret", now=161)

    with pytest.raises(AuthError, match="signature"):
        principal_from_session_jwt(token, secret="wrong-secret", now=120)


def test_scope_and_tenant_authorization_checks():
    principal = Principal(
        subject="alice",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:read"}),
    )

    require_scope(principal, "translation:read")
    require_tenant(principal, "tenant-a")

    with pytest.raises(AuthError, match="scope"):
        require_scope(principal, "translation:submit")
    with pytest.raises(AuthError, match="cannot access"):
        require_tenant(principal, "tenant-b")


def test_disabled_auth_principal_is_local_admin_shape():
    principal = disabled_auth_principal()

    assert principal.auth_type == "disabled"
    assert principal.tenant_id == "standalone"
    assert "translation:submit" in principal.scopes
    assert "tokens:write" in principal.scopes


def test_disabled_auth_is_rejected_for_production_mode():
    assert is_production_auth_mode("jwt_ldap") is True
    assert is_production_auth_mode("oidc") is False
    assert is_production_auth_mode("disabled") is False

    require_production_auth_mode("jwt_ldap")
    with pytest.raises(AuthError, match="dev-only"):
        require_production_auth_mode("disabled")
    with pytest.raises(AuthError, match="unsupported"):
        require_production_auth_mode("unknown")


def test_mcp_tools_require_mapped_scopes():
    submitter = Principal(
        subject="svc",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:submit"}),
    )
    viewer = Principal(
        subject="svc",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:read"}),
    )

    require_mcp_tool_scope(submitter, "translation_submit_text")

    with pytest.raises(AuthError, match="scope"):
        require_mcp_tool_scope(viewer, "translation_submit_text")
    with pytest.raises(AuthError, match="unknown MCP tool"):
        require_mcp_tool_scope(submitter, "missing_tool")


def test_audit_sink_records_and_filters_events():
    sink = InMemoryAuditSink()
    principal = Principal(subject="alice", tenant_id="tenant-a")
    event = audit_event(
        event_type="job.submitted",
        outcome=AuditOutcome.SUCCESS,
        principal=principal,
        resource="trjob_1",
        details={"provider_id": "deterministic_ci"},
        now=100,
    )

    sink.record(event)

    assert sink.list_events(tenant_id="tenant-a") == [event]
    assert sink.list_events(event_type="job.submitted") == [event]
    assert sink.list_events(tenant_id="tenant-b") == []
    assert event.to_dict()["outcome"] == "success"


def test_ldap_config_reports_missing_secret_env(monkeypatch):
    monkeypatch.delenv("EDC_LDAP_BIND_DN", raising=False)
    monkeypatch.setenv("EDC_LDAP_BIND_PASSWORD", "secret")
    config = LdapConfig(
        url="ldaps://ldap.example.test",
        user_search_base="ou=users,dc=example,dc=test",
        group_search_base="ou=groups,dc=example,dc=test",
    )

    assert config.missing_secret_env() == ["EDC_LDAP_BIND_DN"]
