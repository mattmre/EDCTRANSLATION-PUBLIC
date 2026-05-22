from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edc_translation.release_readiness import (
    PRODUCTION_EVIDENCE_REQUIREMENTS,
    release_readiness_lane_status,
    production_evidence_status,
)
from edc_translation.engines import get_engine
from edc_translation.llm_live import (
    GEMINI_BASE_URL,
    LIVE_SMOKE_ENV,
    LOCAL_BASE_URL_ENV,
    LOCAL_MODEL_IDS_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL_IDS_ENV,
    discover_env_variable_names,
    discover_gemini_text_models,
    discover_openrouter_free_models,
    gpu_readiness_probe,
    gpu_profile_readiness,
    local_runtime_readiness,
    rank_local_models,
    smoke_provider,
    translate_with_gemini,
    translate_with_openai_compatible_chat,
)
from edc_translation.service import list_engine_providers, submit_text_job


class FakeJsonClient:
    def __init__(
        self,
        *,
        get_payloads: list[dict[str, Any]] | None = None,
        post_payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        self.get_payloads = list(get_payloads or [])
        self.post_payloads = list(post_payloads or [])
        self.get_requests: list[dict[str, Any]] = []
        self.post_requests: list[dict[str, Any]] = []

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.get_requests.append({"url": url, "headers": headers or {}})
        return self.get_payloads.pop(0)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.post_requests.append(
            {"url": url, "payload": payload, "headers": headers or {}}
        )
        return self.post_payloads.pop(0)


class FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _gpu_runner(stdout: str):
    def _run(command: list[str], timeout_seconds: int) -> FakeCompletedProcess:
        assert command[0] == "nvidia-smi"
        assert timeout_seconds == 5
        return FakeCompletedProcess(stdout)

    return _run


def _chat_response(text: str = "Bonjour.") -> dict[str, Any]:
    return {"choices": [{"message": {"content": text}}]}


def _gemini_response(text: str = "Bonjour.") -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_openai_compatible_translation_uses_chat_completion_contract():
    client = FakeJsonClient(post_payloads=[_chat_response("Bonjour.")])

    translated = translate_with_openai_compatible_chat(
        base_url="http://127.0.0.1:1234",
        model_id="local-model",
        text="Hello.",
        source_language="en",
        target_language="fr",
        api_key="local-key",
        max_tokens=12,
        client=client,
    )

    request = client.post_requests[0]
    assert translated == "Bonjour."
    assert request["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer local-key"
    assert request["payload"]["model"] == "local-model"
    assert request["payload"]["max_tokens"] == 12
    assert request["payload"]["temperature"] == 0


def test_live_smoke_is_opt_in_and_does_not_call_provider_when_disabled():
    client = FakeJsonClient(post_payloads=[_chat_response()])

    result = smoke_provider(
        "local_openai_compat",
        client=client,
        env={
            LOCAL_BASE_URL_ENV: "http://127.0.0.1:1234",
            LOCAL_MODEL_IDS_ENV: "local-model",
        },
    )

    assert result["configured"] is True
    assert result["live_enabled"] is False
    assert result["attempted"] is False
    assert result["success"] is False
    assert client.post_requests == []


def test_local_smoke_caps_tokens_and_uses_one_translation_request():
    client = FakeJsonClient(post_payloads=[_chat_response("Bonjour.")])

    result = smoke_provider(
        "local_openai_compat",
        source_language="en",
        target_language="fr",
        text="Hello.",
        max_tokens=4096,
        client=client,
        env={
            LIVE_SMOKE_ENV: "1",
            LOCAL_BASE_URL_ENV: "http://127.0.0.1:1234",
            LOCAL_MODEL_IDS_ENV: "local-model",
        },
    )

    assert result["success"] is True
    assert result["attempted"] is True
    assert result["model_id"] == "local-model"
    assert len(client.post_requests) == 1
    assert client.post_requests[0]["payload"]["max_tokens"] == 64


def test_rank_local_models_discovers_models_and_sorts_successful_probes():
    client = FakeJsonClient(
        get_payloads=[{"data": [{"id": "slow"}, {"id": "fast"}]}],
        post_payloads=[_chat_response("Bonjour lent."), _chat_response("Bonjour.")],
    )

    results = rank_local_models(
        source_language="en",
        target_language="fr",
        text="Hello.",
        max_models=2,
        client=client,
        env={
            LIVE_SMOKE_ENV: "1",
            LOCAL_BASE_URL_ENV: "http://127.0.0.1:1234",
        },
    )

    assert {item["model_id"] for item in results} == {"slow", "fast"}
    assert all(item["success"] for item in results)
    assert len(client.get_requests) == 1
    assert len(client.post_requests) == 2


def test_gpu_readiness_probe_parses_nvidia_smi_query_output():
    result = gpu_readiness_probe(
        runner=_gpu_runner(
            "0, NVIDIA GeForce RTX 3090, 24576, 2027, 22549, 591.86\n"
        )
    )

    assert result["available"] is True
    assert result["gpu_count"] == 1
    gpu = result["gpus"][0]
    assert gpu["name"] == "NVIDIA GeForce RTX 3090"
    assert gpu["memory_total_mib"] == 24576
    assert gpu["memory_used_mib"] == 2027
    assert gpu["driver_version"] == "591.86"


def test_local_runtime_readiness_rejects_mock_endpoint_as_evidence():
    result = local_runtime_readiness(
        env={
            LIVE_SMOKE_ENV: "1",
            LOCAL_BASE_URL_ENV: "http://mock-llm:8082",
            LOCAL_MODEL_IDS_ENV: "mock-translation-smoke",
        },
        runner=_gpu_runner(
            "0, NVIDIA GeForce RTX 3090, 24576, 2027, 22549, 591.86\n"
        ),
    )

    assert result["configured"] is True
    assert result["gpu_readiness"]["available"] is True
    assert result["mock_runtime"] is True
    assert result["ready"] is False
    assert "mock local" in result["reason"]


def test_local_runtime_readiness_accepts_configured_non_mock_gpu_runtime():
    result = local_runtime_readiness(
        env={
            LIVE_SMOKE_ENV: "1",
            LOCAL_BASE_URL_ENV: "http://127.0.0.1:8000",
            LOCAL_MODEL_IDS_ENV: "approved-local-runtime",
        },
        runner=_gpu_runner(
            "0, NVIDIA GeForce RTX 3090, 24576, 2027, 22549, 591.86\n"
        ),
    )

    assert result["ready"] is True
    assert result["runtime_kind"] == "local_openai_compatible_gpu"
    assert result["model_ids"] == ["approved-local-runtime"]
    assert result["gpu_profiles"]["single_card"]["single-gpu-16gb"]["status"] == "validated"
    assert result["gpu_profiles"]["single_card"]["single-gpu-24gb"]["status"] == "validated"
    assert (
        result["gpu_profiles"]["operator_handoff"]["gpu-4x"]["status"]
        == "requires_cluster_operator_evidence"
    )


def test_gpu_profile_readiness_blocks_24gb_on_16gb_card():
    readiness = gpu_readiness_probe(
        runner=_gpu_runner(
            "0, NVIDIA RTX 4000 Ada, 16384, 1024, 15360, 591.86\n"
        )
    )

    profiles = gpu_profile_readiness(readiness)

    assert profiles["single_card"]["single-gpu-16gb"]["status"] == "validated"
    assert profiles["single_card"]["single-gpu-24gb"]["status"] == "blocked"
    assert profiles["operator_handoff"]["gpu-2x"]["observed_local_gpu_count"] == 1


def test_runtime_readiness_reports_model_evidence_env_refs():
    result = local_runtime_readiness(
        env={
            LIVE_SMOKE_ENV: "1",
            LOCAL_BASE_URL_ENV: "http://127.0.0.1:8000",
            LOCAL_MODEL_IDS_ENV: "approved-local-runtime",
            "TRANSLATION_CT2_MODEL_DIR": "/opt/edc/models/opus",
            "TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE": "/opt/edc/evidence/gpu.json",
        },
        runner=_gpu_runner(
            "0, NVIDIA GeForce RTX 3090, 24576, 2027, 22549, 591.86\n"
        ),
    )

    assert result["evidence_refs"]["ct2_model_dir_configured"] is True
    assert result["evidence_refs"]["gpu_model_provenance_configured"] is True


def test_openrouter_free_model_discovery_filters_paid_models_and_uses_auth_header():
    client = FakeJsonClient(
        get_payloads=[
            {
                "data": [
                    {"id": "paid", "pricing": {"prompt": "0.1", "completion": "0.1"}},
                    {"id": "free-by-id:free", "pricing": {}},
                    {
                        "id": "free-by-price",
                        "pricing": {"prompt": "0", "completion": "0.000000"},
                    },
                ]
            }
        ]
    )

    models = discover_openrouter_free_models(
        client=client,
        api_key="router-key",
    )

    assert models == ["free-by-id:free", "free-by-price"]
    assert client.get_requests[0]["url"] == f"{OPENROUTER_BASE_URL}/models"
    assert client.get_requests[0]["headers"]["Authorization"] == "Bearer router-key"


def test_openrouter_smoke_uses_configured_model_without_model_discovery():
    client = FakeJsonClient(post_payloads=[_chat_response("Bonjour.")])

    result = smoke_provider(
        "openrouter_llm",
        text="Hello.",
        client=client,
        env={
            LIVE_SMOKE_ENV: "1",
            OPENROUTER_API_KEY_ENV: "router-key",
            OPENROUTER_MODEL_IDS_ENV: "provider/free:free",
        },
    )

    assert result["success"] is True
    assert result["model_id"] == "provider/free:free"
    assert client.get_requests == []
    assert client.post_requests[0]["url"] == f"{OPENROUTER_BASE_URL}/chat/completions"
    assert client.post_requests[0]["headers"]["Authorization"] == "Bearer router-key"


def test_openrouter_smoke_reports_empty_free_model_discovery_cleanly():
    client = FakeJsonClient(get_payloads=[{"data": []}])

    result = smoke_provider(
        "openrouter_llm",
        text="Hello.",
        client=client,
        env={
            LIVE_SMOKE_ENV: "1",
            OPENROUTER_API_KEY_ENV: "router-key",
        },
    )

    assert result["success"] is False
    assert result["attempted"] is True
    assert result["error"] == "no free OpenRouter model discovered"


def test_gemini_model_discovery_prefers_flash_style_text_models():
    client = FakeJsonClient(
        get_payloads=[
            {
                "models": [
                    {
                        "name": "models/gemini-pro",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-2.0-flash-lite",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding-model",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }
        ]
    )

    models = discover_gemini_text_models(client=client, api_key="google-key")

    assert models == ["gemini-2.0-flash-lite", "gemini-pro"]
    assert client.get_requests[0]["url"] == f"{GEMINI_BASE_URL}/models?key=google-key"


def test_gemini_translation_parses_generate_content_response():
    client = FakeJsonClient(post_payloads=[_gemini_response("Bonjour.")])

    translated = translate_with_gemini(
        model_id="models/gemini-2.0-flash",
        text="Hello.",
        source_language="en",
        target_language="fr",
        api_key="google-key",
        max_tokens=16,
        client=client,
    )

    request = client.post_requests[0]
    assert translated == "Bonjour."
    assert request["url"].startswith(
        f"{GEMINI_BASE_URL}/models/gemini-2.0-flash:generateContent"
    )
    assert request["payload"]["generationConfig"]["maxOutputTokens"] == 16
    assert "Return only the translated text" in request["payload"]["contents"][0]["parts"][0]["text"]


def test_env_discovery_reports_names_without_secret_values(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=secret-router\nUNRELATED=value\n",
        encoding="utf-8",
    )
    child = tmp_path / "OTHER_REPO"
    child.mkdir()
    (child / ".env.local").write_text(
        "GOOGLE_API_KEY=secret-google\nEDC_TRANSLATION_GOOGLE_MODEL_ID=gemini\n",
        encoding="utf-8",
    )

    discovered = discover_env_variable_names(root=tmp_path)
    rendered = json.dumps(discovered)

    assert len(discovered) == 2
    assert "OPENROUTER_API_KEY" in discovered[0]["variables"]
    assert "GOOGLE_API_KEY" in discovered[1]["variables"]
    assert "EDC_TRANSLATION_GOOGLE_MODEL_ID" in discovered[1]["variables"]
    assert "secret-router" not in rendered
    assert "secret-google" not in rendered


def test_release_readiness_checker_separates_smoke_success_from_production_evidence(tmp_path: Path):
    missing = release_readiness_lane_status(env={}, live_smoke_results=[{"success": True}])

    assert missing["product_e2e"]["status"] == "live_provider_smoke_passed"
    assert missing["production_live"]["status"] == "blocked"
    assert "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE" in missing["production_live"]["missing"]

    env = {}
    for requirement, spec in PRODUCTION_EVIDENCE_REQUIREMENTS.items():
        artifact = tmp_path / f"{requirement}.json"
        payload = {
            "artifact_type": "edc_translation_production_evidence",
            "requirement": requirement,
            "status": "passed",
            "environment": "approved_staging",
            "reviewed_by": "security-reviewer",
            "timestamp": "2026-05-16T12:00:00Z",
            "controls": [
                {
                    "id": control,
                    "passed": True,
                    "evidence_ref": f"evidence://{requirement}/{control}",
                    "command": f"validate-{requirement}-{control}",
                }
                for control in spec["controls"]
            ],
        }
        if requirement == "auth-provider":
            payload["auth_mode"] = "jwt_ldap"
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        env[spec["env"]] = str(artifact)

    evidence = production_evidence_status(env)
    ready = release_readiness_lane_status(env=env)

    assert all(item["valid"] for item in evidence)
    assert ready["production_live"]["status"] == "ready_for_review"
    assert ready["production_live"]["missing"] == []


def test_live_provider_engines_are_registered_and_show_configuration(monkeypatch):
    monkeypatch.delenv(LOCAL_BASE_URL_ENV, raising=False)
    ids = {engine["id"]: engine for engine in list_engine_providers()}

    assert get_engine("local_openai_compat")
    assert get_engine("openrouter_llm")
    assert get_engine("google_gemini")
    assert ids["local_openai_compat"]["family"] == "llm_local"
    assert ids["openrouter_llm"]["family"] == "llm_cloud"
    assert ids["google_gemini"]["configuration"]["configured"] is False


def test_cloud_provider_translation_is_blocked_by_default_tenant_policy():
    job = submit_text_job(
        "Hello.",
        source_language="en",
        target_language="fr",
        provider_id="openrouter_llm",
    )

    assert job["status"] == "failed"
    assert "provider family blocked by tenant policy: llm_cloud" in job["error"]["message"]
