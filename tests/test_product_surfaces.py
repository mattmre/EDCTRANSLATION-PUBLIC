from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from edc_translation.api import app
from edc_translation.cli import main as cli_main
from edc_translation.client import TranslationClient
from edc_translation.contracts import validate_payload
from edc_translation.jobs import FileTranslationJobRepository
from edc_translation.mcp import call_tool, list_tools
from edc_translation.service import (
    get_translation_job_bundle,
    raw_text_to_document_bundle,
    score_pair,
    submit_text_job,
    upsert_glossary,
    validate_custody_payload,
    validate_model_bundle,
)


def test_raw_text_to_document_bundle_preserves_contract():
    bundle = raw_text_to_document_bundle(
        "Hello world.",
        source_language="en",
        source_name="note.txt",
    )

    validate_payload(bundle, "document-bundle-v1")
    assert bundle["document_id"].startswith("raw-text-")
    assert bundle["spans"][0]["text"] == "Hello world."
    assert bundle["ocr_engine_metadata"]["engine_id"] == "raw_text_normalizer"


def test_submit_text_job_emits_translation_bundle():
    job = submit_text_job(
        "Hello world.",
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
    )

    assert job["status"] == "succeeded"
    assert job["translation_bundle_available"] is True
    assert job["metadata"]["input_contract"] == "document-bundle-v1"


def test_submit_text_job_auto_detects_source_language():
    job = submit_text_job(
        "Bonjour le monde.",
        source_language="auto",
        target_language="en",
        provider_id="deterministic_ci",
    )
    bundle = get_translation_job_bundle(job["job_id"])

    assert job["status"] == "succeeded"
    assert bundle["translated_spans"][0]["source_language"] == "fr"


def test_file_job_repository_persists_completed_bundle(tmp_path: Path):
    repository = FileTranslationJobRepository(tmp_path / "jobs")
    job = submit_text_job(
        "Hello world.",
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
        repository=repository,
    )
    reloaded = FileTranslationJobRepository(tmp_path / "jobs")

    status = reloaded.get(job["job_id"]).status_payload()
    bundle = get_translation_job_bundle(job["job_id"], repository=reloaded)

    assert status["status"] == "succeeded"
    assert bundle["schema_version"] == "translation-bundle-v1"


def test_glossary_hits_are_written_to_translation_bundle():
    upsert_glossary(
        {
            "glossary_id": "legal-fr",
            "name": "Legal FR",
            "source_language": "en",
            "target_language": "fr",
            "entries": {"contract": "contrat"},
            "approved": True,
        }
    )

    job = submit_text_job(
        "The contract is signed.",
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
        glossary_ids=["legal-fr"],
    )

    from edc_translation.service import get_translation_job_bundle

    bundle = get_translation_job_bundle(job["job_id"])
    assert bundle["glossary_hits"] == ["legal-fr:contract"]
    assert bundle["translated_spans"][0]["glossary_hits"] == ["legal-fr:contract"]


def test_score_pair_and_custody_validation():
    quality = score_pair(
        "Hello world.",
        "Hello world. [en->fr]",
        source_language="en",
        target_language="fr",
    )

    assert 0 <= quality["score"] <= 1
    assert quality["provider_id"] == "deterministic_local_qe"

    job = submit_text_job(
        "Hello world.",
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
    )
    from edc_translation.service import get_translation_job_bundle

    bundle = get_translation_job_bundle(job["job_id"])
    custody = validate_custody_payload(bundle)
    assert custody["valid"] is True
    assert custody["missing"] == []


def test_validate_model_bundle_reports_missing_artifacts(tmp_path: Path):
    result = validate_model_bundle(tmp_path, enforce_supply_chain=True)

    assert result["valid"] is False
    assert result["approved"] is False
    assert any("source.spm" in error for error in result["errors"])
    assert any("provenance" in error for error in result["errors"])


def test_api_product_surfaces(tmp_path: Path):
    client = TestClient(app)

    policy = client.get("/api/v1/translation/tenant-policy/standalone")
    assert policy.status_code == 200
    assert policy.json()["tenant_policy"]["retention_policy"] == "process_local_only"

    glossary = client.post(
        "/api/v1/translation/glossaries",
        json={
            "glossary_id": "api-glossary",
            "source_language": "en",
            "target_language": "fr",
            "entries": {"hello": "bonjour"},
            "approved": True,
        },
    )
    assert glossary.status_code == 200
    assert glossary.json()["glossary"]["approved"] is True

    text_job = client.post(
        "/api/v1/translation/jobs/text",
        json={
            "text": "hello",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "glossary_ids": ["api-glossary"],
        },
    )
    assert text_job.status_code == 202
    job_id = text_job.json()["job"]["job_id"]

    bundle = client.get(f"/api/v1/translation/jobs/{job_id}/bundle")
    assert bundle.status_code == 200
    assert bundle.json()["translation_bundle"]["glossary_hits"] == [
        "api-glossary:hello"
    ]

    score = client.post(
        "/api/v1/translation/score-pair",
        json={"source_text": "hello", "translated_text": "bonjour"},
    )
    assert score.status_code == 200
    assert 0 <= score.json()["quality"]["score"] <= 1

    evidence = client.get(f"/api/v1/translation/jobs/{job_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["evidence_bundle"]["job_id"] == job_id

    review = client.post(
        f"/api/v1/translation/jobs/{job_id}/reviews",
        json={"decision": "certified", "reviewer": "qa"},
    )
    assert review.status_code == 200

    validate_model = client.post(
        "/api/v1/translation/models/validate",
        json={"model_dir": str(tmp_path), "enforce_supply_chain": True},
    )
    assert validate_model.status_code == 200
    assert validate_model.json()["model_status"]["valid"] is False


def test_cli_product_surfaces(tmp_path: Path, capsys):
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("hello", encoding="utf-8")
    target.write_text("bonjour", encoding="utf-8")

    assert cli_main(["score-pair", "--source", str(source), "--target", str(target)]) == 0
    score_payload = json.loads(capsys.readouterr().out)
    assert "score" in score_payload["quality"]

    assert (
        cli_main(
            [
                "submit-text",
                "hello",
                "--target",
                "fr",
                "--engine",
                "deterministic_ci",
            ]
        )
        == 0
    )
    job_id = json.loads(capsys.readouterr().out)["job"]["job_id"]

    assert cli_main(["evidence-bundle", job_id]) == 0
    assert json.loads(capsys.readouterr().out)["evidence_bundle"]["job_id"] == job_id

    assert cli_main(["review-job", job_id, "--decision", "certified", "--reviewer", "qa"]) == 0
    assert json.loads(capsys.readouterr().out)["review"]["decision"] == "certified"

    assert cli_main(["verify-model-bundle", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["model_status"]["valid"] is False


def test_mcp_product_tools_cover_backlog():
    names = {tool["name"] for tool in list_tools()["tools"]}
    assert {
        "translation_submit_text",
        "translation_score_pair",
        "translation_validate_model_bundle",
        "translation_get_evidence_bundle",
        "translation_validate_custody",
    }.issubset(names)

    text_result = call_tool(
        "translation_submit_text",
        {
            "text": "hello",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
        },
    )
    assert text_result["job"]["status"] == "succeeded"

    evidence = call_tool(
        "translation_get_evidence_bundle",
        {"job_id": text_result["job"]["job_id"]},
    )
    assert evidence["evidence_bundle"]["job_id"] == text_result["job"]["job_id"]

    custody = call_tool(
        "translation_validate_custody",
        {"translation_bundle": text_result["translation_bundle"]},
    )
    assert custody["custody"]["valid"] is True

    score = call_tool(
        "translation_score_pair",
        {"source_text": "hello", "translated_text": "bonjour"},
    )
    assert "score" in score["quality"]


def test_python_client_supports_required_workflows(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", raising=False)
    for name in (
        "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        "TRANSLATION_CT2_MODEL_DIR",
        "KUBECONFIG",
        "TRANSLATION_TSA_URL",
        "PLUGIN_SANDBOX_RUNTIME_PROOF",
    ):
        monkeypatch.delenv(name, raising=False)
    client = TranslationClient()
    job = client.submit_text(
        "Hello world.",
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
    )
    bundle = client.get_bundle(job["job_id"])

    assert client.get_job_status(job["job_id"])["status"] == "succeeded"
    assert bundle["schema_version"] == "translation-bundle-v1"
    assert client.validate_custody(bundle)["valid"] is True
    assert "score" in client.score_pair("hello", "bonjour")
    assert client.get_evidence_bundle(job["job_id"])["job_id"] == job["job_id"]
    assert client.validate_model_bundle(tmp_path)["valid"] is False
    assert any(engine["id"] == "deterministic_ci" for engine in client.list_engines())
    languages = client.list_languages()
    assert languages["language_count"] >= 300
    assert languages["provider_capabilities"]["nllb_200"]["language_count"] == 200
    assert client.rank_local_models() == []
    assert client.live_smoke("local_openai_compat")["success"] is False
    assert client.release_readiness_status()["production_live"]["status"] == "blocked"

    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=secret\n", encoding="utf-8")
    discovered = client.discover_env(root=tmp_path)
    assert discovered[0]["variables"] == ["OPENROUTER_API_KEY"]
    assert "secret" not in json.dumps(discovered)
