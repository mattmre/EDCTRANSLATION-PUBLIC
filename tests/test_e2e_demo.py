from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from edc_translation.api import app
from edc_translation.release_readiness import release_readiness_rubric_status
from edc_translation.cli import main as cli_main
from edc_translation.client import TranslationClient
from edc_translation.mcp import call_tool

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "e2e-demo" / "edc-translation-cc0-smoke.json"


def _demo() -> dict:
    return json.loads(DEMO.read_text(encoding="utf-8"))


def test_free_demo_data_end_to_end_surfaces(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("EDC_AUTH_MODE", "disabled")
    demo = _demo()
    pair = demo["pairs"][0]
    client = TestClient(app)

    api_response = client.post(
        "/api/v1/translation/jobs/text",
        json={
            "text": pair["source_text"],
            "source_language": pair["source_language"],
            "target_language": pair["target_language"],
            "provider_id": "deterministic_ci",
            "tenant_id": "e2e-demo",
        },
    )
    assert api_response.status_code == 202
    api_job = api_response.json()["job"]
    api_bundle = client.get(
        f"/api/v1/translation/jobs/{api_job['job_id']}/bundle"
    ).json()["translation_bundle"]
    assert api_bundle["translated_spans"][0]["translated_text"].endswith("[en->fr]")

    assert (
        cli_main(
            [
                "submit-text",
                pair["source_text"],
                "--source",
                pair["source_language"],
                "--target",
                pair["target_language"],
                "--provider",
                "deterministic_ci",
            ]
        )
        == 0
    )
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["job"]["status"] == "succeeded"

    mcp_payload = call_tool(
        "translation_submit_text",
        {
            "text": pair["source_text"],
            "source_language": pair["source_language"],
            "target_language": pair["target_language"],
            "provider_id": "deterministic_ci",
            "tenant_id": "e2e-demo",
        },
    )
    assert mcp_payload["job"]["status"] == "succeeded"

    py_client = TranslationClient()
    py_job = py_client.submit_text(
        demo["pairs"][1]["source_text"],
        source_language=demo["pairs"][1]["source_language"],
        target_language=demo["pairs"][1]["target_language"],
        provider_id="deterministic_ci",
        tenant_id="e2e-demo",
    )
    py_bundle = py_client.get_bundle(py_job["job_id"])
    assert py_client.validate_custody(py_bundle)["valid"] is True
    assert py_client.get_evidence_bundle(py_job["job_id"])["job_id"] == py_job["job_id"]

    artifact = tmp_path / "product-e2e-artifact.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_product_e2e",
                "status": "passed",
                "reviewed_by": "qa-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "dataset": demo["dataset"],
                "surfaces": [
                    "api",
                    "cli",
                    "mcp",
                    "python_client",
                    "custody_evidence",
                    "readiness_product_e2e",
                ],
                "jobs": [
                    api_job["job_id"],
                    cli_payload["job"]["job_id"],
                    mcp_payload["job"]["job_id"],
                    py_job["job_id"],
                ],
                "commands": ["python -m pytest tests/test_e2e_demo.py"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    readiness = release_readiness_rubric_status(env={}, product_e2e_artifact=str(artifact))
    assert readiness["lanes"]["product_e2e"]["score"] == 50
    assert readiness["lanes"]["product_e2e"]["artifact"]["valid"] is True
    assert readiness["lanes"]["product_e2e"]["live_smoke_passed"] is False
    assert readiness["lanes"]["production_live"]["score"] == 0
    assert readiness["claimable_100"] is False


def test_demo_fixture_declares_public_license():
    demo = _demo()

    assert demo["dataset"]["license"] == "CC0-1.0"
    assert demo["dataset"]["source"] == "Project-authored deterministic E2E smoke fixture"
