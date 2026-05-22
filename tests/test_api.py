from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from edc_translation.api import app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "edc_contracts"


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_healthz_and_readyz_aliases_are_public(monkeypatch):
    monkeypatch.setenv("EDC_AUTH_MODE", "jwt_ldap")
    client = TestClient(app)

    health_response = client.get("/healthz")
    ready_response = client.get("/readyz")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "healthy"
    assert ready_response.status_code == 200
    assert ready_response.json()["readiness"] == "ready"


def test_engine_list_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/translation/engines")
    assert response.status_code == 200
    ids = {engine["id"] for engine in response.json()["engines"]}
    assert "deterministic_ci" in ids


def test_language_catalog_endpoint_exposes_broad_provider_capabilities():
    client = TestClient(app)
    response = client.get("/api/v1/translation/languages")

    assert response.status_code == 200
    payload = response.json()
    codes = {language["code"] for language in payload["languages"]}
    assert {"auto", "en", "fr", "eng_Latn", "fra_Latn", "zho_Hans"}.issubset(
        codes
    )
    assert {"ace_Arab", "wol_Latn", "yor_Latn", "zul_Latn"}.issubset(codes)
    assert payload["language_count"] >= 300
    assert payload["free_form_supported"] is True
    assert payload["catalogs"]["flores_200"]["language_count"] >= 200
    assert payload["provider_capabilities"]["fasttext_lid"]["language_count"] == 176
    assert payload["provider_capabilities"]["nllb_200"]["language_count"] == 200
    assert payload["provider_capabilities"]["madlad_400"]["language_count"] == 419
    matrices = payload["provider_language_matrices"]
    assert matrices["passthrough"]["target_strategy"] == "same_as_source"
    assert "est_Latn" in matrices["local_ct2_nllb"]["source_codes"]
    assert "eng_Latn" in matrices["local_ct2_nllb"]["target_codes"]
    assert matrices["local_ct2_opus"]["matrix_type"] == "configured_model_specific"
    assert "est_Latn" in payload["equivalent_codes"]["et"]


def test_language_catalog_endpoint_can_expose_configured_opus_pairs(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv(
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        str(tmp_path / "opus-et-en"),
    )
    client = TestClient(app)
    response = client.get("/api/v1/translation/languages")

    assert response.status_code == 200
    matrix = response.json()["provider_language_matrices"]["local_ct2_opus"]
    assert matrix["known_matrix"] is True
    assert matrix["pairs"] == {"et": ["en"]}


def test_engine_list_endpoint_can_include_routing_diagnostics():
    client = TestClient(app)
    response = client.get(
        "/api/v1/translation/engines",
        params={
            "include_routing_diagnostics": "true",
            "source_language": "en",
            "target_language": "fr",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["routing_diagnostics"]["provider_id"] == "auto"
    assert "auto_routing" in payload["engines"][0]


def test_routing_diagnostics_endpoint():
    client = TestClient(app)
    response = client.get(
        "/api/v1/translation/routing/diagnostics",
        params={
            "source_language": "en",
            "target_language": "fr",
        },
    )

    assert response.status_code == 200
    diagnostics = response.json()["routing_diagnostics"]
    assert diagnostics["provider_id"] == "auto"
    assert diagnostics["source_language"] == "en"
    assert diagnostics["target_language"] == "fr"


def test_auto_route_readiness_endpoint_ready_for_same_language(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    client = TestClient(app)
    response = client.get(
        "/api/v1/translation/readiness/auto-route",
        params={
            "source_language": "en",
            "target_language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["routing_diagnostics"]["selected_provider_id"] == "passthrough"


def test_auto_route_readiness_endpoint_reports_unavailable(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    client = TestClient(app)
    response = client.get(
        "/api/v1/translation/readiness/auto-route",
        params={
            "source_language": "en",
            "target_language": "fr",
        },
    )

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error["code"] == "auto_route_unavailable"
    assert error["routing_diagnostics"]["selected_provider_id"] is None


def test_translate_bundle_endpoint():
    client = TestClient(app)
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    response = client.post(
        "/api/v1/translation/bundles",
        json={
            "document_bundle": document_bundle,
            "target_language": "fr",
            "provider_id": "stub",
        },
    )
    assert response.status_code == 200
    bundle = response.json()["translation_bundle"]
    assert bundle["schema_version"] == "translation-bundle-v1"
    assert bundle["engine_provider"]["id"] == "stub"


def test_translate_bundle_endpoint_accepts_auto_provider_for_same_language():
    client = TestClient(app)
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    response = client.post(
        "/api/v1/translation/bundles",
        json={
            "document_bundle": document_bundle,
            "target_language": "en",
            "provider_id": "auto",
        },
    )

    assert response.status_code == 200
    bundle = response.json()["translation_bundle"]
    assert bundle["engine_provider"]["id"] == "passthrough"


def test_translate_bundle_endpoint_reports_auto_route_failure(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    client = TestClient(app)
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    response = client.post(
        "/api/v1/translation/bundles",
        json={
            "document_bundle": document_bundle,
            "target_language": "fr",
            "provider_id": "auto",
        },
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    diagnostics = error["routing_diagnostics"]
    assert error["code"] == "auto_route_unavailable"
    assert "No auto-routeable translation engine" in error["message"]
    assert diagnostics["provider_id"] == "auto"
    assert diagnostics["source_language"] == "en"
    assert diagnostics["target_language"] == "fr"
    assert diagnostics["selected_provider_id"] is None
    assert any(
        candidate["reason"] == "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR is unset"
        for candidate in diagnostics["candidates"]
    )


def test_translation_job_submit_status_and_bundle_endpoints():
    client = TestClient(app)
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )

    submit = client.post(
        "/api/v1/translation/jobs",
        json={
            "document_bundle": document_bundle,
            "target_language": "fr",
            "provider_id": "deterministic_ci",
        },
    )

    assert submit.status_code == 202
    job = submit.json()["job"]
    assert job["status"] == "succeeded"
    assert job["translation_bundle_available"] is True

    status = client.get(f"/api/v1/translation/jobs/{job['job_id']}")
    assert status.status_code == 200
    assert status.json()["job"]["status"] == "succeeded"

    bundle_response = client.get(f"/api/v1/translation/jobs/{job['job_id']}/bundle")
    assert bundle_response.status_code == 200
    bundle = bundle_response.json()["translation_bundle"]
    assert bundle["schema_version"] == "translation-bundle-v1"
    assert bundle["engine_provider"]["id"] == "deterministic_ci"


def test_translation_job_endpoints_report_missing_job():
    client = TestClient(app)

    status = client.get("/api/v1/translation/jobs/trjob_missing")
    bundle = client.get("/api/v1/translation/jobs/trjob_missing/bundle")

    assert status.status_code == 404
    assert bundle.status_code == 404


def test_text_file_batch_api_returns_json_job_logs_and_outputs(tmp_path: Path):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "utf8.txt").write_text("Hello.", encoding="utf-8")
    (source / "utf16.txt").write_text("World.", encoding="utf-16")
    (source / "ansi.txt").write_bytes("Café.".encode("cp1252"))
    client = TestClient(app)

    submit = client.post(
        "/api/v1/translation/files/batch",
        json={
            "source_path": str(source),
            "output_dir": str(output),
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "input_encoding": "auto",
            "output_encoding": "utf-8",
            "file_extensions": [".txt"],
        },
    )
    assert submit.status_code == 202
    job_id = submit.json()["job"]["job_id"]

    status_payload = _wait_for_batch(client, job_id)
    logs = client.get(f"/api/v1/translation/files/batch/{job_id}/logs")
    log_text = client.get(f"/api/v1/translation/files/batch/{job_id}/logs/text")
    save_log = client.post(
        f"/api/v1/translation/files/batch/{job_id}/logs/save",
        json={"log_path": str(output / "saved.log")},
    )
    outputs = client.get(f"/api/v1/translation/files/batch/{job_id}/outputs")

    assert status_payload["status"] == "succeeded"
    assert status_payload["total_files"] == 3
    assert logs.status_code == 200
    assert any("Converted file" in entry["message"] for entry in logs.json()["logs"])
    assert log_text.status_code == 200
    assert "Converted file" in log_text.text
    assert save_log.status_code == 200
    assert Path(save_log.json()["log"]["log_path"]).is_file()
    assert outputs.status_code == 200
    assert len(outputs.json()["files"]) == 3
    assert (output / "utf8.txt").read_text(encoding="utf-8") == "Hello. [en->fr]"
    assert (output / "utf16.txt.translation-bundle.json").is_file()


def test_text_file_batch_api_reports_missing_job():
    client = TestClient(app)

    status = client.get("/api/v1/translation/files/batch/tfjob_missing")
    logs = client.get("/api/v1/translation/files/batch/tfjob_missing/logs")
    outputs = client.get("/api/v1/translation/files/batch/tfjob_missing/outputs")

    assert status.status_code == 404
    assert logs.status_code == 404
    assert outputs.status_code == 404


def test_live_smoke_endpoint_reports_disabled_gate(monkeypatch):
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS", "local-model")
    monkeypatch.delenv("EDC_TRANSLATION_LIVE_SMOKE", raising=False)

    client = TestClient(app)
    response = client.post(
        "/api/v1/translation/live-smoke",
        json={"provider_id": "local_openai_compat"},
    )

    assert response.status_code == 200
    smoke = response.json()["smoke"]
    assert smoke["configured"] is True
    assert smoke["attempted"] is False
    assert smoke["success"] is False


def test_local_model_ranking_endpoint_reports_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/translation/local-model-ranking")

    assert response.status_code == 200
    assert response.json()["models"] == []


def test_env_discovery_endpoint_reports_names_without_values(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=secret\nEDC_TRANSLATION_LIVE_SMOKE=1\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/translation/env-discovery",
        params={"root": str(tmp_path)},
    )
    rendered = response.text

    assert response.status_code == 200
    assert response.json()["env_files"][0]["variables"] == [
        "EDC_TRANSLATION_LIVE_SMOKE",
        "OPENROUTER_API_KEY",
    ]
    assert "secret" not in rendered


def test_release_readiness_status_endpoint_blocks_without_production_artifacts(monkeypatch):
    for name in (
        "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        "TRANSLATION_CT2_MODEL_DIR",
        "KUBECONFIG",
        "TRANSLATION_TSA_URL",
        "PLUGIN_SANDBOX_RUNTIME_PROOF",
    ):
        monkeypatch.delenv(name, raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/translation/readiness/evidence-status")

    assert response.status_code == 200
    payload = response.json()["readiness"]
    assert payload["production_live"]["status"] == "blocked"
    assert "TRANSLATION_TSA_URL" in payload["production_live"]["missing"]


def test_admin_page_loads():
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200

    versioned_response = client.get("/api/v1/translation/admin")
    assert versioned_response.status_code == 200
    assert versioned_response.text == response.text

    assert response.status_code == 200
    assert "EDC_TRANSLATION" in response.text
    assert "Batch Text Files" in response.text
    assert "/api/v1/translation/files/batch" in response.text
    assert "Full Log" in response.text
    assert 'name="source_language" data-language-role="source"' in response.text
    assert 'name="target_language" data-language-role="target"' in response.text
    assert 'data-default="en"' in response.text
    assert "targetLanguagesForProviderSource" in response.text
    assert "providerLanguageMatrices" in response.text
    assert "local_ct2_nllb" in response.text
    assert "/api/v1/translation/languages" in response.text
    assert (
        "True writes the translated text plus a per-file TranslationBundle v1 "
        "JSON sidecar"
        in response.text
    )
    assert "Source language for the input. Auto detects each file" in response.text
    assert "Encoding for translated text outputs" in response.text


def test_openapi_summary_lists_route_endpoints():
    client = TestClient(app)
    response = client.get("/api/v1/translation/openapi-summary")

    assert response.status_code == 200
    endpoints = set(response.json()["endpoints"])
    assert "/api/v1/translation/routing/diagnostics" in endpoints
    assert "/api/v1/translation/languages" in endpoints
    assert "/api/v1/translation/readiness/auto-route" in endpoints
    assert "/api/v1/translation/jobs" in endpoints
    assert "/api/v1/translation/files/batch" in endpoints
    assert "/api/v1/translation/files/batch/{job_id}/logs" in endpoints
    assert "/api/v1/translation/files/batch/{job_id}/logs/text" in endpoints
    assert "/api/v1/translation/files/batch/{job_id}/logs/save" in endpoints
    assert "/api/v1/translation/live-smoke" in endpoints
    assert "/api/v1/translation/readiness/evidence-status" in endpoints


def _wait_for_batch(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(50):
        response = client.get(f"/api/v1/translation/files/batch/{job_id}")
        assert response.status_code == 200
        job = response.json()["job"]
        if job["terminal"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Batch job did not finish: {job_id}")
