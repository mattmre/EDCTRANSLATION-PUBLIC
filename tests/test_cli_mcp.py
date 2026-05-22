from __future__ import annotations

import json
from pathlib import Path

from edc_translation.auth import Principal
from edc_translation.cli import main as cli_main
from edc_translation.mcp import call_tool, list_tools

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "edc_contracts"


def test_cli_list_engines(capsys):
    assert cli_main(["list-engines"]) == 0
    payload = json.loads(capsys.readouterr().out)
    ids = {engine["id"] for engine in payload["engines"]}
    assert "passthrough" in ids


def test_cli_list_engines_can_include_routing_diagnostics(capsys):
    assert (
        cli_main(
            [
                "list-engines",
                "--include-routing-diagnostics",
                "--source",
                "en",
                "--target",
                "fr",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["routing_diagnostics"]["provider_id"] == "auto"
    assert payload["routing_diagnostics"]["source_language"] == "en"
    assert "auto_routing" in payload["engines"][0]


def test_cli_smoke_auto_route_fails_when_no_engine_selected(capsys, monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    assert cli_main(["smoke-auto-route", "--source", "en", "--target", "fr"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["routing_diagnostics"]["selected_provider_id"] is None
    assert "No auto-routeable translation engine selected" in captured.err
    assert "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR is unset" in captured.err


def test_cli_smoke_auto_route_passes_for_same_language(capsys, monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    assert cli_main(["smoke-auto-route", "--source", "en", "--target", "en"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["routing_diagnostics"]["selected_provider_id"] == "passthrough"
    assert captured.err == ""


def test_cli_smoke_auto_route_passes_for_configured_opus(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    (model_dir / "source.spm").write_text("source", encoding="utf-8")
    (model_dir / "target.spm").write_text("target", encoding="utf-8")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", raising=False)
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)

    assert cli_main(["smoke-auto-route", "--source", "en", "--target", "fr"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["routing_diagnostics"]["selected_provider_id"] == "local_ct2_opus"
    assert captured.err == ""


def test_cli_translate_writes_bundle(tmp_path: Path):
    out = tmp_path / "translation-bundle.json"
    assert (
        cli_main(
            [
                "translate",
                str(FIXTURES / "document-bundle-v1.valid.json"),
                "--target",
                "fr",
                "--provider",
                "deterministic_ci",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "translation-bundle-v1"
    assert payload["engine_provider"]["id"] == "deterministic_ci"


def test_cli_translate_accepts_auto_provider_for_same_language(tmp_path: Path):
    out = tmp_path / "translation-bundle.json"
    assert (
        cli_main(
            [
                "translate",
                str(FIXTURES / "document-bundle-v1.valid.json"),
                "--target",
                "en",
                "--provider",
                "auto",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["engine_provider"]["id"] == "passthrough"


def test_cli_translate_reports_auto_route_failure(capsys, monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    assert (
        cli_main(
            [
                "translate",
                str(FIXTURES / "document-bundle-v1.valid.json"),
                "--target",
                "fr",
                "--provider",
                "auto",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert captured.out == ""
    assert payload["error"]["code"] == "auto_route_unavailable"
    assert payload["error"]["routing_diagnostics"]["selected_provider_id"] is None
    assert "No auto-routeable translation engine" in payload["error"]["message"]


def test_cli_submit_bundle_job_status_and_get_bundle(tmp_path: Path, capsys):
    assert (
        cli_main(
            [
                "submit-bundle",
                str(FIXTURES / "document-bundle-v1.valid.json"),
                "--target",
                "fr",
                "--provider",
                "deterministic_ci",
            ]
        )
        == 0
    )
    submit_payload = json.loads(capsys.readouterr().out)
    job_id = submit_payload["job"]["job_id"]
    assert submit_payload["job"]["status"] == "succeeded"

    assert cli_main(["job-status", job_id]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["job"]["translation_bundle_available"] is True

    out = tmp_path / "from-job.json"
    assert cli_main(["get-bundle", job_id, "--out", str(out)]) == 0
    assert capsys.readouterr().out == ""
    bundle = json.loads(out.read_text(encoding="utf-8"))
    assert bundle["schema_version"] == "translation-bundle-v1"
    assert bundle["engine_provider"]["id"] == "deterministic_ci"


def test_cli_live_smoke_is_clear_when_live_gate_is_disabled(capsys, monkeypatch):
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS", "local-model")
    monkeypatch.delenv("EDC_TRANSLATION_LIVE_SMOKE", raising=False)

    assert cli_main(["live-smoke", "--provider", "local_openai_compat"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["smoke"]["configured"] is True
    assert payload["smoke"]["attempted"] is False
    assert "EDC_TRANSLATION_LIVE_SMOKE=1" in payload["smoke"]["error"]


def test_cli_rank_local_models_reports_no_models_when_local_endpoint_unset(
    capsys,
    monkeypatch,
):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", raising=False)

    assert cli_main(["rank-local-models"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["models"] == []


def test_cli_discover_env_reports_variable_names_without_values(
    tmp_path: Path,
    capsys,
):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=secret\nEDC_TRANSLATION_LIVE_SMOKE=1\n",
        encoding="utf-8",
    )

    assert cli_main(["discover-env", "--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["env_files"][0]["variables"] == [
        "EDC_TRANSLATION_LIVE_SMOKE",
        "OPENROUTER_API_KEY",
    ]
    assert "secret" not in output


def test_cli_readiness_check_reports_missing_production_evidence(capsys, monkeypatch):
    for name in (
        "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        "TRANSLATION_CT2_MODEL_DIR",
        "KUBECONFIG",
        "TRANSLATION_TSA_URL",
        "PLUGIN_SANDBOX_RUNTIME_PROOF",
    ):
        monkeypatch.delenv(name, raising=False)

    assert cli_main(["readiness-check"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["readiness"]["production_live"]["status"] == "blocked"
    assert "TRANSLATION_CT2_MODEL_DIR" in payload["readiness"]["production_live"]["missing"]


def test_mcp_tool_list_contains_expected_tools():
    names = {tool["name"] for tool in list_tools()["tools"]}
    assert {
        "translation_list_engines",
        "translation_submit_bundle",
        "translation_get_job_status",
        "translation_get_bundle",
        "translation_live_smoke",
        "translation_release_readiness_status",
    }.issubset(names)


def test_mcp_list_engines_can_include_routing_diagnostics():
    payload = call_tool(
        "translation_list_engines",
        {
            "include_routing_diagnostics": True,
            "source_language": "en",
            "target_language": "fr",
        },
    )

    assert payload["routing_diagnostics"]["provider_id"] == "auto"
    assert "auto_routing" in payload["engines"][0]


def test_mcp_submit_bundle_call():
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    result = call_tool(
        "translation_submit_bundle",
        {
            "document_bundle": document_bundle,
            "target_language": "fr",
            "provider_id": "passthrough",
        },
    )
    assert result["job"]["status"] == "succeeded"
    assert result["translation_bundle"]["schema_version"] == "translation-bundle-v1"

    status = call_tool("translation_get_job_status", {"job_id": result["job"]["job_id"]})
    bundle = call_tool("translation_get_bundle", {"job_id": result["job"]["job_id"]})

    assert status["job"]["translation_bundle_available"] is True
    assert bundle["translation_bundle"]["schema_version"] == "translation-bundle-v1"


def test_mcp_submit_bundle_accepts_auto_provider():
    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    result = call_tool(
        "translation_submit_bundle",
        {
            "document_bundle": document_bundle,
            "target_language": "en",
            "provider_id": "auto",
        },
    )
    assert result["translation_bundle"]["engine_provider"]["id"] == "passthrough"


def test_mcp_submit_bundle_reports_auto_route_failure(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    document_bundle = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )
    result = call_tool(
        "translation_submit_bundle",
        {
            "document_bundle": document_bundle,
            "target_language": "fr",
            "provider_id": "auto",
        },
    )

    assert result["is_error"] is True
    assert result["error"]["code"] == "auto_route_unavailable"
    assert result["job"]["status"] == "failed"
    assert result["error"]["routing_diagnostics"]["provider_id"] == "auto"
    assert result["error"]["routing_diagnostics"]["selected_provider_id"] is None


def test_mcp_job_lookup_reports_missing_job():
    result = call_tool("translation_get_job_status", {"job_id": "trjob_missing"})

    assert result["is_error"] is True
    assert result["error"]["code"] == "translation_job_not_found"


def test_mcp_live_smoke_and_readiness_tools_report_status(monkeypatch):
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS", "local-model")
    monkeypatch.delenv("EDC_TRANSLATION_LIVE_SMOKE", raising=False)
    for name in (
        "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        "TRANSLATION_CT2_MODEL_DIR",
        "KUBECONFIG",
        "TRANSLATION_TSA_URL",
        "PLUGIN_SANDBOX_RUNTIME_PROOF",
    ):
        monkeypatch.delenv(name, raising=False)

    smoke = call_tool("translation_live_smoke", {"provider_id": "local_openai_compat"})
    readiness = call_tool("translation_release_readiness_status", {})

    assert smoke["smoke"]["attempted"] is False
    assert smoke["smoke"]["configured"] is True
    assert readiness["readiness"]["production_live"]["status"] == "blocked"


def test_mcp_discover_env_reports_names_without_values(tmp_path: Path):
    (tmp_path / ".env.local").write_text(
        "GEMINI_API_KEY=secret\nEDC_TRANSLATION_GOOGLE_MODEL_ID=gemini\n",
        encoding="utf-8",
    )

    result = call_tool("translation_discover_env", {"root": str(tmp_path)})
    rendered = json.dumps(result)

    assert result["env_files"][0]["variables"] == [
        "EDC_TRANSLATION_GOOGLE_MODEL_ID",
        "GEMINI_API_KEY",
    ]
    assert "secret" not in rendered


def test_mcp_call_tool_rejects_missing_scope():
    principal = Principal(
        subject="viewer",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:read"}),
        auth_type="api_token",
    )

    result = call_tool("translation_list_engines", principal=principal)

    assert result["is_error"] is True
    assert result["error"]["code"] == "mcp_authorization_failed"
    assert "models:read" in result["error"]["message"]


def test_mcp_submit_text_binds_authenticated_tenant():
    principal = Principal(
        subject="translator",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:submit"}),
        auth_type="api_token",
    )

    result = call_tool(
        "translation_submit_text",
        {
            "text": "Hello",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "tenant_id": "tenant-a",
        },
        principal=principal,
    )

    assert result["job"]["metadata"]["tenant_id"] == "tenant-a"


def test_mcp_submit_text_rejects_cross_tenant_principal():
    principal = Principal(
        subject="translator",
        tenant_id="tenant-a",
        scopes=frozenset({"translation:submit"}),
        auth_type="api_token",
    )

    result = call_tool(
        "translation_submit_text",
        {
            "text": "Hello",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "deterministic_ci",
            "tenant_id": "tenant-b",
        },
        principal=principal,
    )

    assert result["is_error"] is True
    assert result["error"]["code"] == "mcp_authorization_failed"
