"""Optional live LLM provider discovery and smoke helpers."""

from __future__ import annotations

import csv
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urljoin

from edc_translation.http_json import JsonHttpClient, JsonHttpError
from edc_translation.quality import score_translation_pair

LIVE_SMOKE_ENV = "EDC_TRANSLATION_LIVE_SMOKE"
DEFAULT_SMOKE_TEXT = "Translate this sentence."
DEFAULT_MAX_TOKENS = 64
NVIDIA_SMI_TIMEOUT_SECONDS = 5

LOCAL_BASE_URL_ENV = "EDC_TRANSLATION_LOCAL_LLM_BASE_URL"
LOCAL_MODEL_IDS_ENV = "EDC_TRANSLATION_LOCAL_LLM_MODEL_IDS"
LOCAL_LLM_API_KEY_ENV = "EDC_TRANSLATION_LOCAL_LLM_API_KEY"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_IDS_ENV = "EDC_TRANSLATION_OPENROUTER_MODEL_IDS"
GOOGLE_API_KEY_ENVS = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
GOOGLE_MODEL_ID_ENV = "EDC_TRANSLATION_GOOGLE_MODEL_ID"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MOCK_LOCAL_MODEL_IDS = {"mock-translation-smoke"}
TRANSLATION_CT2_MODEL_DIR_ENV = "TRANSLATION_CT2_MODEL_DIR"
TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE_ENV = "TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE"

SINGLE_GPU_VRAM_PROFILES = {
    "single-gpu-16gb": 16 * 1024,
    "single-gpu-24gb": 24 * 1024,
}
OPERATOR_GPU_PROFILES = {
    "gpu-2x": 2,
    "gpu-4x": 4,
    "gpu-8x": 8,
    "dgx": 8,
}


@dataclass
class ProviderSmokeResult:
    provider_id: str
    configured: bool
    live_enabled: bool
    attempted: bool
    success: bool
    model_id: str | None = None
    latency_ms: int | None = None
    quality_score: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def live_smoke_enabled(env: dict[str, str] | None = None) -> bool:
    if env is None:
        env = os.environ
    return env.get(LIVE_SMOKE_ENV) == "1"


def split_model_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def gpu_readiness_probe(
    *,
    runner: Callable[[list[str], int], Any] | None = None,
    timeout_seconds: int = NVIDIA_SMI_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return a bounded local NVIDIA readiness probe without loading models."""

    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ]
    run = runner or _run_nvidia_smi
    try:
        completed = run(command, timeout_seconds)
    except FileNotFoundError:
        return _gpu_probe_unavailable("nvidia-smi was not found", command)
    except subprocess.TimeoutExpired:
        return _gpu_probe_unavailable("nvidia-smi timed out", command)
    except OSError as exc:
        return _gpu_probe_unavailable(str(exc), command)

    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    returncode = int(getattr(completed, "returncode", 1))
    if returncode != 0:
        error = (stderr or stdout or f"nvidia-smi exited {returncode}").strip()
        return _gpu_probe_unavailable(error, command)

    gpus = _parse_nvidia_smi_query(stdout)
    return {
        "probe": "nvidia-smi",
        "command": " ".join(command),
        "available": bool(gpus),
        "gpu_count": len(gpus),
        "gpus": gpus,
        "error": None if gpus else "nvidia-smi returned no GPUs",
    }


def local_runtime_readiness(
    *,
    provider_id: str = "local_openai_compat",
    env: dict[str, str] | None = None,
    runner: Callable[[list[str], int], Any] | None = None,
) -> dict[str, Any]:
    """Report whether a local provider can support approved GPU smoke evidence."""

    if env is None:
        env = os.environ
    status = _provider_config_status(provider_id, env)
    gpu = gpu_readiness_probe(runner=runner)
    profiles = gpu_profile_readiness(gpu)
    evidence_refs = _runtime_evidence_refs(env)
    if provider_id != "local_openai_compat":
        return {
            "provider_id": provider_id,
            "runtime_kind": "unsupported",
            "configured": bool(status["configured"]),
            "live_smoke_gate": live_smoke_enabled(env),
            "ready": False,
            "reason": "runtime readiness currently supports local_openai_compat only",
            "mock_runtime": False,
            "model_count": int(status.get("model_count", 0) or 0),
            "model_ids": [],
            "gpu_readiness": gpu,
            "gpu_profiles": profiles,
            "evidence_refs": evidence_refs,
        }

    base_url = env.get(LOCAL_BASE_URL_ENV, "").strip()
    model_ids = split_model_ids(env.get(LOCAL_MODEL_IDS_ENV))
    mock_runtime = _is_mock_local_runtime(base_url, model_ids)
    blockers: list[str] = []
    if not status["configured"]:
        blockers.append(str(status["reason"]))
    if not gpu["available"] or int(gpu["gpu_count"]) < 1:
        blockers.append("no NVIDIA GPU detected by nvidia-smi")
    if mock_runtime:
        blockers.append("mock local OpenAI-compatible endpoint is not approved runtime smoke evidence")

    return {
        "provider_id": provider_id,
        "runtime_kind": "local_openai_compatible_gpu",
        "configured": bool(status["configured"]),
        "live_smoke_gate": live_smoke_enabled(env),
        "ready": not blockers,
        "reason": "ready" if not blockers else "; ".join(blockers),
        "mock_runtime": mock_runtime,
        "model_count": len(model_ids),
        "model_ids": model_ids,
        "base_url_configured": bool(base_url),
        "gpu_readiness": gpu,
        "gpu_profiles": profiles,
        "evidence_refs": evidence_refs,
    }


def gpu_profile_readiness(gpu_readiness: dict[str, Any]) -> dict[str, Any]:
    """Map probed GPU facts to single-card readiness and operator guidance profiles."""

    gpus = [
        gpu
        for gpu in gpu_readiness.get("gpus", [])
        if isinstance(gpu, dict)
    ]
    memory_totals = [
        int(gpu["memory_total_mib"])
        for gpu in gpus
        if isinstance(gpu.get("memory_total_mib"), int)
    ]
    largest_gpu_mib = max(memory_totals, default=0)
    available_count = int(gpu_readiness.get("gpu_count") or 0)
    single_card = {
        profile: {
            "status": "validated" if largest_gpu_mib >= required_mib else "blocked",
            "required_memory_mib": required_mib,
            "observed_largest_gpu_memory_mib": largest_gpu_mib,
            "command": gpu_readiness.get("command", ""),
        }
        for profile, required_mib in SINGLE_GPU_VRAM_PROFILES.items()
    }
    operator_handoff = {
        profile: {
            "status": "requires_cluster_operator_evidence",
            "required_gpu_count": required_count,
            "observed_local_gpu_count": available_count,
            "evidence_owner": "Platform / Kubernetes / GitOps",
            "expected_evidence": "Helm GPU profile, KEDA scaling, GPU operator, and scheduled worker pod evidence",
        }
        for profile, required_count in OPERATOR_GPU_PROFILES.items()
    }
    return {
        "single_card": single_card,
        "operator_handoff": operator_handoff,
    }


def local_provider_config_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    if env is None:
        env = os.environ
    base_url = env.get(LOCAL_BASE_URL_ENV, "").strip()
    models = split_model_ids(env.get(LOCAL_MODEL_IDS_ENV))
    if not base_url:
        return {"configured": False, "reason": f"{LOCAL_BASE_URL_ENV} is unset"}
    if not models:
        return {"configured": False, "reason": f"{LOCAL_MODEL_IDS_ENV} is unset"}
    api_key_set = bool(env.get(LOCAL_LLM_API_KEY_ENV, "").strip())
    return {
        "configured": True,
        "reason": "configured",
        "model_count": len(models),
        "api_key_configured": api_key_set,
    }


def openrouter_provider_config_status(
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if env is None:
        env = os.environ
    if not env.get(OPENROUTER_API_KEY_ENV, "").strip():
        return {"configured": False, "reason": f"{OPENROUTER_API_KEY_ENV} is unset"}
    models = split_model_ids(env.get(OPENROUTER_MODEL_IDS_ENV))
    return {
        "configured": True,
        "reason": "configured" if models else "configured; model discovery required",
        "model_count": len(models),
    }


def gemini_provider_config_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    if env is None:
        env = os.environ
    if not _google_api_key(env):
        return {
            "configured": False,
            "reason": f"{' or '.join(GOOGLE_API_KEY_ENVS)} is unset",
        }
    configured_model = env.get(GOOGLE_MODEL_ID_ENV, "").strip()
    return {
        "configured": True,
        "reason": "configured"
        if configured_model
        else "configured; model discovery required",
        "model_count": 1 if configured_model else 0,
    }


def discover_local_openai_models(
    base_url: str,
    *,
    client: Any | None = None,
    api_key: str | None = None,
) -> list[str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = (client or JsonHttpClient()).get_json(
        _join_url(base_url, "/v1/models"), headers=headers
    )
    models = payload.get("data", [])
    if not isinstance(models, list):
        return []
    out: list[str] = []
    for model in models:
        if isinstance(model, dict) and isinstance(model.get("id"), str):
            out.append(model["id"])
    return out


def discover_openrouter_free_models(
    *,
    client: Any | None = None,
    api_key: str | None = None,
    max_models: int = 8,
) -> list[str]:
    headers = _openrouter_headers(api_key or "")
    payload = (client or JsonHttpClient()).get_json(
        f"{OPENROUTER_BASE_URL}/models",
        headers=headers,
    )
    models = payload.get("data", [])
    if not isinstance(models, list):
        return []
    free_models: list[str] = []
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        pricing = model.get("pricing", {})
        prompt_price = str(pricing.get("prompt", "")) if isinstance(pricing, dict) else ""
        completion_price = (
            str(pricing.get("completion", "")) if isinstance(pricing, dict) else ""
        )
        is_free = model["id"].endswith(":free") or (
            prompt_price in {"0", "0.0", "0.000000"}
            and completion_price in {"0", "0.0", "0.000000"}
        )
        if is_free:
            free_models.append(model["id"])
    return free_models[:max_models]


def discover_gemini_text_models(
    *,
    client: Any | None = None,
    api_key: str,
) -> list[str]:
    payload = (client or JsonHttpClient()).get_json(
        f"{GEMINI_BASE_URL}/models?key={quote(api_key)}"
    )
    models = payload.get("models", [])
    if not isinstance(models, list):
        return []
    out: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        actions = model.get("supportedGenerationMethods", [])
        name = model.get("name")
        if isinstance(name, str) and "generateContent" in actions:
            out.append(name.removeprefix("models/"))
    return sorted(out, key=_gemini_preference_key)


def translate_with_openai_compatible_chat(
    *,
    base_url: str,
    model_id: str,
    text: str,
    source_language: str,
    target_language: str,
    api_key: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
) -> str:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_id,
        "messages": _translation_messages(text, source_language, target_language),
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    response = (client or JsonHttpClient()).post_json(
        _chat_completions_url(base_url),
        payload,
        headers=headers,
    )
    return _extract_openai_chat_text(response)


def translate_with_gemini(
    *,
    model_id: str,
    text: str,
    source_language: str,
    target_language: str,
    api_key: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
) -> str:
    normalized_model_id = model_id.removeprefix("models/")
    prompt = (
        f"Translate from {source_language} to {target_language}. "
        "Return only the translated text.\n\n"
        f"{text}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
    }
    response = (client or JsonHttpClient()).post_json(
        f"{GEMINI_BASE_URL}/models/{quote(normalized_model_id, safe='')}:generateContent?key={quote(api_key, safe='')}",
        payload,
    )
    return _extract_gemini_text(response)


def smoke_provider(
    provider_id: str,
    *,
    source_language: str = "en",
    target_language: str = "fr",
    text: str = DEFAULT_SMOKE_TEXT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if env is None:
        env = os.environ
    enabled = live_smoke_enabled(env)
    token_cap = min(max(1, int(max_tokens)), DEFAULT_MAX_TOKENS)
    status = _provider_config_status(provider_id, env)
    if not status["configured"]:
        return ProviderSmokeResult(
            provider_id=provider_id,
            configured=False,
            live_enabled=enabled,
            attempted=False,
            success=False,
            error=status["reason"],
        ).to_dict()
    if not enabled:
        return ProviderSmokeResult(
            provider_id=provider_id,
            configured=True,
            live_enabled=False,
            attempted=False,
            success=False,
            error=f"{LIVE_SMOKE_ENV}=1 is required for live smoke",
        ).to_dict()

    try:
        start = time.perf_counter()
        model_id, translated = _translate_for_provider(
            provider_id,
            source_language=source_language,
            target_language=target_language,
            text=text,
            max_tokens=token_cap,
            client=client,
            env=env,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        quality = score_translation_pair(
            text,
            translated,
            source_language=source_language,
            target_language=target_language,
        )
        return ProviderSmokeResult(
            provider_id=provider_id,
            configured=True,
            live_enabled=True,
            attempted=True,
            success=True,
            model_id=model_id,
            latency_ms=latency_ms,
            quality_score=float(quality["score"]),
        ).to_dict()
    except (JsonHttpError, RuntimeError, KeyError, ValueError) as exc:
        return ProviderSmokeResult(
            provider_id=provider_id,
            configured=True,
            live_enabled=True,
            attempted=True,
            success=False,
            error=str(exc),
        ).to_dict()


def rank_local_models(
    *,
    source_language: str = "en",
    target_language: str = "fr",
    text: str = DEFAULT_SMOKE_TEXT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_models: int = 4,
    client: Any | None = None,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if env is None:
        env = os.environ
    base_url = env.get(LOCAL_BASE_URL_ENV, "").strip()
    configured_models = split_model_ids(env.get(LOCAL_MODEL_IDS_ENV))
    if not base_url:
        return []
    model_ids = configured_models or discover_local_openai_models(
        base_url,
        client=client,
    )
    results: list[dict[str, Any]] = []
    for model_id in model_ids[:max_models]:
        smoke_env = dict(env)
        smoke_env[LOCAL_MODEL_IDS_ENV] = model_id
        result = smoke_provider(
            "local_openai_compat",
            source_language=source_language,
            target_language=target_language,
            text=text,
            max_tokens=max_tokens,
            client=client,
            env=smoke_env,
        )
        results.append(result)
    return sorted(
        results,
        key=lambda item: (
            not bool(item.get("success")),
            -(float(item.get("quality_score") or 0)),
            int(item.get("latency_ms") or 999999),
        ),
    )


def discover_env_variable_names(
    *,
    root: str | Path = ".",
) -> list[dict[str, Any]]:
    target_names = {
        LIVE_SMOKE_ENV,
        LOCAL_BASE_URL_ENV,
        LOCAL_MODEL_IDS_ENV,
        OPENROUTER_API_KEY_ENV,
        OPENROUTER_MODEL_IDS_ENV,
        *GOOGLE_API_KEY_ENVS,
        GOOGLE_MODEL_ID_ENV,
        "GOOGLE_APPLICATION_CREDENTIALS",
        "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        TRANSLATION_CT2_MODEL_DIR_ENV,
        "TRANSLATION_TSA_URL",
        "KUBECONFIG",
        "PLUGIN_SANDBOX_RUNTIME_PROOF",
        TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE_ENV,
    }
    root_path = Path(root)
    candidates = list(root_path.glob(".env*")) + list(root_path.glob("*/.env*"))
    out: list[dict[str, Any]] = []
    for path in sorted(candidates):
        if not path.is_file():
            continue
        names: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name = stripped.split("=", 1)[0].strip()
            if name in target_names:
                names.add(name)
        if names:
            out.append({"path": str(path), "variables": sorted(names)})
    return out


def _provider_config_status(provider_id: str, env: dict[str, str]) -> dict[str, Any]:
    if provider_id == "local_openai_compat":
        return local_provider_config_status(env)
    if provider_id == "openrouter_llm":
        return openrouter_provider_config_status(env)
    if provider_id == "google_gemini":
        return gemini_provider_config_status(env)
    return {"configured": False, "reason": f"unknown live provider: {provider_id}"}


def _runtime_evidence_refs(env: dict[str, str]) -> dict[str, Any]:
    ct2_model_dir = env.get(TRANSLATION_CT2_MODEL_DIR_ENV, "").strip()
    gpu_model_provenance = env.get(
        TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE_ENV,
        "",
    ).strip()
    return {
        "ct2_model_dir_env": TRANSLATION_CT2_MODEL_DIR_ENV,
        "ct2_model_dir_configured": bool(ct2_model_dir),
        "gpu_model_provenance_env": TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE_ENV,
        "gpu_model_provenance_configured": bool(gpu_model_provenance),
    }


def _translate_for_provider(
    provider_id: str,
    *,
    source_language: str,
    target_language: str,
    text: str,
    max_tokens: int,
    client: Any | None,
    env: dict[str, str],
) -> tuple[str, str]:
    if provider_id == "local_openai_compat":
        base_url = env[LOCAL_BASE_URL_ENV].strip()
        models = split_model_ids(env.get(LOCAL_MODEL_IDS_ENV))
        api_key = env.get(LOCAL_LLM_API_KEY_ENV, "").strip() or None
        if not models:
            models = discover_local_openai_models(base_url, client=client, api_key=api_key)
        if not models:
            raise RuntimeError("no local OpenAI-compatible model discovered")
        model_id = models[0]
        return model_id, translate_with_openai_compatible_chat(
            base_url=base_url,
            model_id=model_id,
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=max_tokens,
            client=client,
        )
    if provider_id == "openrouter_llm":
        api_key = env[OPENROUTER_API_KEY_ENV].strip()
        models = split_model_ids(env.get(OPENROUTER_MODEL_IDS_ENV))
        if not models:
            models = discover_openrouter_free_models(
                client=client,
                api_key=api_key,
                max_models=1,
            )
        if not models:
            raise RuntimeError("no free OpenRouter model discovered")
        model_id = models[0]
        return model_id, translate_with_openai_compatible_chat(
            base_url=OPENROUTER_BASE_URL,
            model_id=model_id,
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=max_tokens,
            client=client,
        )
    if provider_id == "google_gemini":
        api_key = _google_api_key(env)
        if not api_key:
            raise RuntimeError(f"{' or '.join(GOOGLE_API_KEY_ENVS)} is unset")
        model_id = env.get(GOOGLE_MODEL_ID_ENV, "").strip()
        if not model_id:
            models = discover_gemini_text_models(client=client, api_key=api_key)
            if not models:
                raise RuntimeError("no Gemini text-generation model discovered")
            model_id = models[0]
        return model_id, translate_with_gemini(
            model_id=model_id,
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=max_tokens,
            client=client,
        )
    raise RuntimeError(f"unknown live provider: {provider_id}")


def _translation_messages(
    text: str,
    source_language: str,
    target_language: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Translate faithfully. Return only translated text. "
                "Do not add explanations."
            ),
        },
        {
            "role": "user",
            "content": f"Translate from {source_language} to {target_language}: {text}",
        },
    ]


def _extract_openai_chat_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise JsonHttpError("provider response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise JsonHttpError("provider response missing message content")
    return content.strip()


def _extract_gemini_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise JsonHttpError("Gemini response missing candidates")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise JsonHttpError("Gemini response missing content parts")
    text = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()
    if not text:
        raise JsonHttpError("Gemini response missing text")
    return text


def _openrouter_headers(api_key: str) -> dict[str, str]:
    headers = {
        "HTTP-Referer": "https://localhost/edc-translation",
        "X-Title": "EDC_TRANSLATION",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _google_api_key(env: dict[str, str]) -> str:
    for name in GOOGLE_API_KEY_ENVS:
        value = env.get(name, "").strip()
        if value:
            return value
    return ""


def _gemini_preference_key(model_id: str) -> tuple[int, str]:
    lowered = model_id.lower()
    if "flash" in lowered and ("8b" in lowered or "lite" in lowered):
        return (0, model_id)
    if "flash" in lowered:
        return (1, model_id)
    return (2, model_id)


def _run_nvidia_smi(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _gpu_probe_unavailable(error: str, command: list[str]) -> dict[str, Any]:
    return {
        "probe": "nvidia-smi",
        "command": " ".join(command),
        "available": False,
        "gpu_count": 0,
        "gpus": [],
        "error": error,
    }


def _parse_nvidia_smi_query(stdout: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in csv.reader(stdout.splitlines()):
        if len(row) < 6:
            continue
        out.append(
            {
                "index": _optional_int(row[0]),
                "name": row[1].strip(),
                "memory_total_mib": _optional_int(row[2]),
                "memory_used_mib": _optional_int(row[3]),
                "memory_free_mib": _optional_int(row[4]),
                "driver_version": row[5].strip(),
            }
        )
    return out


def _optional_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _is_mock_local_runtime(base_url: str, model_ids: list[str]) -> bool:
    lowered_url = base_url.lower()
    lowered_mock_ids = {model_id.casefold() for model_id in MOCK_LOCAL_MODEL_IDS}
    return (
        "mock" in lowered_url
        or any(model_id.casefold() in lowered_mock_ids for model_id in model_ids)
    )


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return _join_url(base_url, "/v1/chat/completions")
