from __future__ import annotations

import json
from pathlib import Path

from edc_translation.contracts import canonical_json_sha256, validate_payload
from edc_translation.jobs import InMemoryTranslationJobRepository
from edc_translation.service import (
    get_translation_job_bundle,
    get_translation_job_status,
    list_translation_jobs,
    list_engine_providers,
    submit_document_bundle_job,
    translate_document_bundle,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "edc_contracts"


def _document_bundle() -> dict:
    return json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )


def test_list_engine_providers_contains_initial_providers():
    providers = list_engine_providers()
    ids = {provider["id"] for provider in providers}
    passthrough = next(
        provider for provider in providers if provider["id"] == "passthrough"
    )

    assert {"passthrough", "stub", "deterministic_ci"}.issubset(ids)
    assert passthrough["family"] == "passthrough"
    assert passthrough["latency_class"] == "realtime"
    assert "local" in passthrough["deployment_envs"]
    assert passthrough["runtime"] == "edc_translation"
    assert passthrough["runtime_version"]


def test_list_engine_providers_can_include_auto_routing_diagnostics(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)
    providers = list_engine_providers(
        include_routing_diagnostics=True,
        source_language="en",
        target_language="fr",
    )
    opus = next(
        provider for provider in providers if provider["id"] == "local_ct2_opus"
    )
    passthrough = next(
        provider for provider in providers if provider["id"] == "passthrough"
    )

    assert opus["auto_routing"]["eligible"] is False
    assert (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR"
        in opus["auto_routing"]["reason"]
    )
    assert passthrough["auto_routing"]["reason"] == "not an auto-routing candidate"


def test_translate_document_bundle_validates_output():
    document = _document_bundle()
    translated = translate_document_bundle(
        document,
        target_language="fr",
        provider_id="deterministic_ci",
    )

    validate_payload(translated, "translation-bundle-v1")
    assert translated["document_id"] == document["document_id"]
    assert translated["source_bundle_sha256"] == canonical_json_sha256(document)
    assert translated["target_language"] == "fr"
    assert translated["engine_provider"]["id"] == "deterministic_ci"
    assert translated["translated_spans"][0]["translated_text"].endswith("[en->fr]")


def test_passthrough_provider_preserves_text():
    translated = translate_document_bundle(
        _document_bundle(),
        target_language="en",
        provider_id="passthrough",
    )
    first_span = translated["translated_spans"][0]
    assert first_span["translated_text"] == first_span["source_text"]
    assert translated["certified"] is False


def test_auto_provider_routes_same_language_to_passthrough():
    translated = translate_document_bundle(
        _document_bundle(),
        target_language="en",
        provider_id="auto",
    )

    assert translated["engine_provider"]["id"] == "passthrough"
    assert translated["translated_spans"][0]["translated_text"] == "Hello world."


def test_translate_document_bundle_uses_span_adapter_shape():
    document = _document_bundle()
    document["spans"][0]["language"] = "fr"

    translated = translate_document_bundle(
        document,
        target_language="de",
        provider_id="deterministic_ci",
    )

    first_span = translated["translated_spans"][0]
    assert first_span["span_id"] == document["spans"][0]["span_id"]
    assert first_span["page_number"] == document["spans"][0]["page_number"]
    assert first_span["source_bbox"] == document["spans"][0]["bbox"]
    assert first_span["source_bboxes"] == document["spans"][0]["bboxes"]
    assert first_span["source_language"] == "fr"
    assert first_span["translated_text"].endswith("[fr->de]")
    assert translated["model_provenance"]["license"] == "Apache-2.0"


def test_submit_document_bundle_job_persists_status_and_bundle():
    repository = InMemoryTranslationJobRepository()
    document = _document_bundle()

    job = submit_document_bundle_job(
        document,
        target_language="fr",
        provider_id="deterministic_ci",
        repository=repository,
    )

    assert job["status"] == "succeeded"
    assert job["document_id"] == document["document_id"]
    assert job["translation_bundle_available"] is True
    assert job["metadata"]["persistence"] == "process_local_in_memory"

    status = get_translation_job_status(job["job_id"], repository=repository)
    bundle = get_translation_job_bundle(job["job_id"], repository=repository)

    assert status["status"] == "succeeded"
    assert bundle["schema_version"] == "translation-bundle-v1"
    assert bundle["engine_provider"]["id"] == "deterministic_ci"

    jobs = list_translation_jobs(repository=repository)
    assert [listed["job_id"] for listed in jobs] == [job["job_id"]]
    assert jobs[0]["translation_bundle_available"] is True
    assert jobs[0]["metadata"] == job["metadata"]


def test_submit_document_bundle_job_records_auto_route_failure(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)
    repository = InMemoryTranslationJobRepository()

    job = submit_document_bundle_job(
        _document_bundle(),
        target_language="fr",
        provider_id="auto",
        repository=repository,
    )

    assert job["status"] == "failed"
    assert job["translation_bundle_available"] is False
    assert job["error"]["code"] == "auto_route_unavailable"
