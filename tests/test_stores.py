from __future__ import annotations

from edc_translation.auth import (
    AuditOutcome,
    Principal,
    audit_event,
    issue_api_token,
)
from edc_translation.model_registry import ModelBundleStatus
from edc_translation.stores import (
    InMemoryAuditStore,
    InMemoryEvidenceStore,
    InMemoryModelRegistryStore,
    InMemoryResultStore,
    InMemoryTokenStore,
    ResultRecord,
)
from edc_translation.auth import JsonTokenAuditStore  # for protocol compliance test


def test_result_store_saves_result_pointer_and_bundle():
    store = InMemoryResultStore()
    record = ResultRecord(
        job_id="trjob_1",
        document_id="doc-1",
        status="succeeded",
        result_ref="s3://bucket/result.json",
        translation_bundle={"schema_version": "translation-bundle-v1"},
    )

    store.save(record)

    assert store.get("trjob_1") == record
    assert store.list() == [record]
    assert store.get("trjob_1").result_ref == "s3://bucket/result.json"


def test_audit_store_filters_by_tenant_and_type():
    store = InMemoryAuditStore()
    principal = Principal(subject="alice", tenant_id="tenant-a")
    event = audit_event(
        event_type="job.submitted",
        outcome=AuditOutcome.SUCCESS,
        principal=principal,
        resource="trjob_1",
        now=100,
    )

    store.record(event)

    assert store.list_events(tenant_id="tenant-a") == [event]
    assert store.list_events(event_type="job.submitted") == [event]
    assert store.list_events(tenant_id="tenant-b") == []


def test_token_store_lists_by_tenant_without_plaintext():
    store = InMemoryTokenStore()
    issued = issue_api_token(
        tenant_id="tenant-a",
        scopes={"translation:submit"},
        created_by="alice",
        now=100,
    )

    store.save(issued.record)

    assert store.get(issued.record.token_id) == issued.record
    assert store.list(tenant_id="tenant-a") == [issued.record]
    assert store.list(tenant_id="tenant-b") == []
    assert issued.plaintext_token not in store.get(issued.record.token_id).token_hash


def test_model_registry_store_saves_approval_state():
    store = InMemoryModelRegistryStore()
    status = ModelBundleStatus(
        model_id="opus-en-fr",
        path="/models/opus-en-fr",
        valid=True,
        approved=True,
        errors=[],
        provenance={"license": "CC-BY-4.0"},
    )

    store.save(status)

    assert store.get("opus-en-fr") == status
    assert store.list() == [status]


def test_model_registry_store_round_trips_cache_metadata():
    store = InMemoryModelRegistryStore()
    status = ModelBundleStatus(
        model_id="opus-en-fr",
        path="/models/opus-en-fr",
        valid=True,
        approved=True,
        errors=[],
        provenance={"license": "CC-BY-4.0", "weights_sha256": "a" * 64},
        engine_family="ctranslate2",
        license="CC-BY-4.0",
        vram_profile="gpu-8gb",
        cache_location="s3://edc-model-cache/opus-en-fr",
        quality_evidence_ref="s3://edc-evidence/models/opus-en-fr.json",
        updated_at="2026-05-16T00:00:00+00:00",
    )

    saved = store.save(status)
    status.provenance["license"] = "mutated"
    fetched = store.get("opus-en-fr")

    assert saved == fetched
    assert fetched.to_dict() == {
        "model_id": "opus-en-fr",
        "path": "/models/opus-en-fr",
        "valid": True,
        "approved": True,
        "errors": [],
        "provenance": {"license": "CC-BY-4.0", "weights_sha256": "a" * 64},
        "engine_family": "ctranslate2",
        "license": "CC-BY-4.0",
        "vram_profile": "gpu-8gb",
        "cache_location": "s3://edc-model-cache/opus-en-fr",
        "quality_evidence_ref": "s3://edc-evidence/models/opus-en-fr.json",
        "updated_at": "2026-05-16T00:00:00+00:00",
    }
    assert store.list() == [fetched]


def test_evidence_store_saves_bundle_by_job_id():
    store = InMemoryEvidenceStore()
    evidence = {
        "schema_version": "translation-evidence-bundle-v1",
        "job_id": "trjob_1",
    }

    store.save("trjob_1", evidence)

    assert store.get("trjob_1") == evidence


def test_json_token_audit_store_implements_token_and_audit_store_protocols(tmp_path):
    """Focused test for Auth tranche: Json now satisfies the stores protocols used by DEFAULT_* wiring."""
    path = tmp_path / "tokens-audit.json"
    store = JsonTokenAuditStore(path)

    # TokenStore protocol surface
    issued = issue_api_token(
        tenant_id="tenant-proto",
        scopes={"translation:read", "models:read"},
        created_by="tester",
        now=1778880000,
    )
    saved = store.save(issued.record)
    assert saved.token_id == issued.record.token_id
    fetched = store.get(issued.record.token_id)
    assert fetched.tenant_id == "tenant-proto"
    listed = store.list(tenant_id="tenant-proto")
    assert len(listed) == 1

    # AuditStore protocol surface
    principal = Principal(subject="tester", tenant_id="tenant-proto")
    ev = audit_event(
        event_type="auth.test",
        outcome=AuditOutcome.SUCCESS,
        principal=principal,
        resource="tok_123",
        now=1778880001,
    )
    stored_ev = store.record(ev)
    assert stored_ev.event_type == "auth.test"
    evs = store.list_events(tenant_id="tenant-proto")
    assert len(evs) == 1
    assert evs[0].resource == "tok_123"
