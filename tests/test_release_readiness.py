from __future__ import annotations

import json
from pathlib import Path

from edc_translation.release_readiness import (
    PRODUCTION_EVIDENCE_REQUIREMENTS,
    release_readiness_rubric_status,
    local_evidence_artifact_status,
    live_smoke_artifact_status,
    production_evidence_status,
)
from edc_translation.cli import main as cli_main


def _write_production_artifact(
    path: Path,
    *,
    requirement: str,
    controls: list[str],
    auth_mode: str = "jwt_ldap",
) -> Path:
    payload = {
        "artifact_type": "edc_translation_production_evidence",
        "requirement": requirement,
        "status": "passed",
        "environment": "approved_staging",
        "reviewed_by": "security-reviewer",
        "timestamp": "2026-05-16T12:00:00Z",
        "controls": controls,
    }
    if requirement == "auth-provider":
        payload["auth_mode"] = auth_mode
    payload["controls"] = [
        {
            "id": control,
            "passed": True,
            "evidence_ref": f"evidence://{requirement}/{control}",
            "command": f"validate-{control}",
        }
        for control in controls
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_local_artifact(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_local_evidence",
                "status": "passed",
                "reviewed_by": "local-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "commands": [
                    "pytest",
                    "ruff",
                    "helm_template_default",
                    "helm_template_production",
                    "readiness_run_nonclaimable",
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _valid_production_env(tmp_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for requirement, spec in PRODUCTION_EVIDENCE_REQUIREMENTS.items():
        env_name = spec["env"]
        artifact = _write_production_artifact(
            tmp_path / f"{requirement}.json",
            requirement=requirement,
            controls=list(spec["controls"]),
        )
        env[env_name] = str(artifact)
    return env


def test_release_readiness_rubric_blocks_100_without_live_and_production_evidence():
    status = release_readiness_rubric_status(env={})

    assert status["lanes"]["local"]["score"] == 0
    assert status["lanes"]["product_e2e"]["score"] == 0
    assert status["lanes"]["production_live"]["score"] == 0
    assert status["claimable_100"] is False
    assert status["total_score"] < 100
    assert "manual reviewed score artifact" in " ".join(status["blockers"])


def test_release_readiness_rubric_live_smoke_does_not_unblock_production():
    status = release_readiness_rubric_status(
        env={},
        live_smoke_results=[{"provider_id": "local_openai_compat", "success": True}],
    )

    assert status["lanes"]["product_e2e"]["score"] == 50
    assert status["lanes"]["production_live"]["score"] == 0
    assert status["claimable_100"] is False


def test_release_readiness_rubric_accepts_recorded_live_smoke_artifact(tmp_path: Path):
    artifact = tmp_path / "live-smoke.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_live_smoke",
                "status": "passed",
                "reviewed_by": "runtime-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "smoke": {
                    "provider_id": "local_openai_compat",
                    "success": True,
                    "model_id": "approved-local-runtime",
                    "latency_ms": 12,
                },
                "runtime": {
                    "runtime_kind": "local_openai_compatible_gpu",
                    "approved_runtime": True,
                    "mock_runtime": False,
                    "model_provenance_ref": "evidence://model/approved-local-runtime",
                    "gpu_readiness": {
                        "available": True,
                        "gpu_count": 1,
                        "gpus": [{"name": "NVIDIA GeForce RTX 3090"}],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    status = release_readiness_rubric_status(env={}, live_smoke_artifact=str(artifact))

    assert status["lanes"]["product_e2e"]["score"] == 50
    assert status["lanes"]["product_e2e"]["live_smoke_passed"] is True
    assert status["lanes"]["product_e2e"]["live_smoke_artifact"]["valid"] is True
    assert status["claimable_100"] is False


def test_release_readiness_rubric_rejects_mock_local_live_smoke_artifact(tmp_path: Path):
    artifact = tmp_path / "mock-live-smoke.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_live_smoke",
                "status": "passed",
                "reviewed_by": "runtime-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "smoke": {
                    "provider_id": "local_openai_compat",
                    "success": True,
                    "model_id": "mock-translation-smoke",
                    "latency_ms": 12,
                },
            }
        ),
        encoding="utf-8",
    )

    artifact_status = live_smoke_artifact_status(str(artifact))
    status = release_readiness_rubric_status(env={}, live_smoke_artifact=str(artifact))

    assert artifact_status["valid"] is False
    assert "mock local smoke model" in artifact_status["reason"]
    assert status["lanes"]["product_e2e"]["score"] == 0
    assert status["claimable_100"] is False


def test_release_readiness_rubric_product_e2e_artifact_scores_product_lane(tmp_path: Path):
    artifact = tmp_path / "product-e2e.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_product_e2e",
                "status": "passed",
                "reviewed_by": "qa-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "dataset": {
                    "name": "EDC demo parallel phrases",
                    "license": "CC0-1.0",
                },
                "surfaces": [
                    "api",
                    "cli",
                    "mcp",
                    "python_client",
                    "custody_evidence",
                    "readiness_product_e2e",
                ],
                "commands": ["python -m pytest tests/test_e2e_demo.py"],
            }
        ),
        encoding="utf-8",
    )

    status = release_readiness_rubric_status(env={}, product_e2e_artifact=str(artifact))

    assert status["lanes"]["product_e2e"]["score"] == 50
    assert status["lanes"]["product_e2e"]["status"] == "demo_e2e_artifact_passed"
    assert status["lanes"]["production_live"]["score"] == 0
    assert status["claimable_100"] is False


def test_release_readiness_rubric_ready_production_still_requires_manual_review(tmp_path: Path):
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("reviewed", encoding="utf-8")
    env = _valid_production_env(tmp_path)
    local = _write_local_artifact(tmp_path / "local-evidence.json")
    product = tmp_path / "product-e2e.json"
    product.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_product_e2e",
                "status": "passed",
                "reviewed_by": "qa-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "dataset": {"name": "demo", "license": "CC0-1.0"},
                "surfaces": [
                    "api",
                    "cli",
                    "mcp",
                    "python_client",
                    "custody_evidence",
                    "readiness_product_e2e",
                ],
                "commands": ["python -m pytest tests/test_e2e_demo.py"],
            }
        ),
        encoding="utf-8",
    )

    without_review = release_readiness_rubric_status(
        env=env,
        live_smoke_results=[{"success": True}],
        local_evidence_artifact=str(local),
        product_e2e_artifact=str(product),
    )
    with_review = release_readiness_rubric_status(
        env=env,
        live_smoke_results=[{"success": True}],
        local_evidence_artifact=str(local),
        product_e2e_artifact=str(product),
        manual_review_artifact=str(evidence),
    )

    assert without_review["lanes"]["production_live"]["score"] == 100
    assert without_review["claimable_100"] is False
    assert with_review["claimable_100"] is True
    assert with_review["total_score"] == 100


def test_local_evidence_requires_recorded_validation_artifact(tmp_path: Path):
    missing = local_evidence_artifact_status(None)
    valid = local_evidence_artifact_status(str(_write_local_artifact(tmp_path / "local.json")))
    incomplete = tmp_path / "incomplete-local.json"
    incomplete.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_local_evidence",
                "status": "passed",
                "reviewed_by": "local-reviewer",
                "timestamp": "2026-05-16T12:00:00Z",
                "commands": ["pytest"],
            }
        ),
        encoding="utf-8",
    )

    assert missing["valid"] is False
    assert valid["valid"] is True
    assert local_evidence_artifact_status(str(incomplete))["valid"] is False


def test_production_evidence_rejects_malformed_typed_artifact(tmp_path: Path):
    env = _valid_production_env(tmp_path)
    bad = tmp_path / "bad-cloud.json"
    bad.write_text("{}", encoding="utf-8")
    env["TRANSLATION_CLOUD_RESIDENCY_EVIDENCE"] = str(bad)

    status = release_readiness_rubric_status(
        env=env,
        live_smoke_results=[{"success": True}],
        manual_review_artifact=env["KUBECONFIG"],
    )
    cloud = next(
        item
        for item in production_evidence_status(env)
        if item["requirement"] == "cloud-residency"
    )

    assert cloud["valid"] is False
    assert "artifact_type" in cloud["reason"]
    assert status["lanes"]["production_live"]["score"] == 0
    assert status["claimable_100"] is False


def test_production_evidence_rejects_missing_required_controls(tmp_path: Path):
    env = _valid_production_env(tmp_path)
    artifact = _write_production_artifact(
        tmp_path / "network-rbac-incomplete.json",
        requirement="network-rbac",
        controls=["default_deny_network_policy"],
    )
    env["TRANSLATION_NETWORK_RBAC_EVIDENCE"] = str(artifact)

    evidence = production_evidence_status(env)
    network = next(item for item in evidence if item["requirement"] == "network-rbac")

    assert network["valid"] is False
    assert "least_privilege_service_account" in network["reason"]


def test_production_evidence_rejects_local_staging_candidate_artifact(tmp_path: Path):
    env = _valid_production_env(tmp_path)
    spec = PRODUCTION_EVIDENCE_REQUIREMENTS["kubeconfig"]
    artifact = _write_production_artifact(
        tmp_path / "local-staging-candidate.json",
        requirement="kubeconfig",
        controls=list(spec["controls"]),
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["environment"] = "local-staging-candidate"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    env["KUBECONFIG"] = str(artifact)

    kubeconfig = next(
        item
        for item in production_evidence_status(env)
        if item["requirement"] == "kubeconfig"
    )

    assert kubeconfig["valid"] is False
    assert "production or approved_staging" in kubeconfig["reason"]


def test_product_e2e_artifact_requires_review_metadata_and_command(tmp_path: Path):
    artifact = tmp_path / "unreviewed-product-e2e.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "edc_translation_product_e2e",
                "status": "passed",
                "dataset": {"name": "demo", "license": "CC0-1.0"},
                "surfaces": [
                    "api",
                    "cli",
                    "mcp",
                    "python_client",
                    "custody_evidence",
                    "readiness_product_e2e",
                ],
            }
        ),
        encoding="utf-8",
    )

    status = release_readiness_rubric_status(env={}, product_e2e_artifact=str(artifact))

    assert status["lanes"]["product_e2e"]["artifact"]["valid"] is False
    assert status["lanes"]["product_e2e"]["score"] == 0
    assert status["claimable_100"] is False


def test_auth_provider_evidence_rejects_disabled_auth(tmp_path: Path):
    env = _valid_production_env(tmp_path)
    spec = PRODUCTION_EVIDENCE_REQUIREMENTS["auth-provider"]
    artifact = _write_production_artifact(
        tmp_path / "auth-disabled.json",
        requirement="auth-provider",
        controls=list(spec["controls"]),
        auth_mode="disabled",
    )
    env["TRANSLATION_AUTH_PROVIDER_EVIDENCE"] = str(artifact)

    auth_provider = next(
        item
        for item in production_evidence_status(env)
        if item["requirement"] == "auth-provider"
    )

    assert auth_provider["valid"] is False
    assert "disabled auth" in auth_provider["reason"]


def test_cli_readiness_run_reports_nonclaimable_status(capsys):
    assert cli_main(["readiness-run"]) == 1

    payload = capsys.readouterr().out
    assert '"claimable_100": false' in payload


def test_cli_readiness_run_out_writes_bounded_manifest_without_env_values(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    secret_values = {
        spec["env"]: f"secret-{name}"
        for name, spec in PRODUCTION_EVIDENCE_REQUIREMENTS.items()
    }
    for env_name, value in secret_values.items():
        monkeypatch.setenv(env_name, value)

    out = tmp_path / "readiness-manifest.json"

    assert cli_main(["readiness-run", "--out", str(out)]) == 1

    capsys.readouterr()
    raw_manifest = out.read_text(encoding="utf-8")
    manifest = json.loads(raw_manifest)

    assert manifest["timestamp"]
    assert manifest["env_var_names"] == list(secret_values)
    assert len(manifest["production_requirements"]) == len(secret_values)
    assert manifest["claimable_100"] is False
    assert manifest["blockers"]
    for secret_value in secret_values.values():
        assert secret_value not in raw_manifest
