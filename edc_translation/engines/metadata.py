"""Engine metadata and provenance normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edc_translation.engines.base import TranslationEngine

VALID_PROVIDER_FAMILIES = {
    "ct2_nmt",
    "llm_local",
    "llm_cloud",
    "quality_estimation",
    "passthrough",
    "unknown",
}


def engine_provider_payload(engine: "TranslationEngine") -> dict[str, Any]:
    """Return the TranslationBundle ``engine_provider`` payload."""

    capability = engine.capability
    return {
        "id": capability.id,
        "family": provider_family(engine),
        "is_local": bool(capability.is_local),
        "is_cloud": bool(capability.is_cloud),
        "license": capability.license,
        "provider_retention_class": capability.provider_retention_class,
    }


def engine_model_provenance(engine: "TranslationEngine") -> dict[str, Any]:
    """Return normalized model provenance for bundle/service responses."""

    raw = engine.model_provenance()
    provenance = dict(raw) if isinstance(raw, Mapping) else {}
    runtime = engine.runtime_info()
    provenance.setdefault("weights_sha256", "unknown")
    provenance.setdefault("license", engine.capability.license)
    provenance.setdefault("runtime", runtime.get("runtime", "edc_translation"))
    provenance.setdefault("runtime_version", runtime.get("version", "unknown"))
    return provenance


def engine_list_entry(engine: "TranslationEngine") -> dict[str, Any]:
    """Return provider metadata for engine-list API and compatibility callers."""

    capability = engine.capability
    provenance = engine_model_provenance(engine)
    payload = engine_provider_payload(engine)
    payload.update(
        {
            "quality_class": capability.quality_class,
            "latency_class": capability.latency_class,
            "supports_pairs": capability.supports_pairs,
            "deployment_envs": list(capability.deployment_envs),
            "cost_per_1m_chars_usd": capability.cost_per_1m_chars_usd,
            "cost_per_1m_tokens_usd": capability.cost_per_1m_tokens_usd,
            "handles_handwriting_natively": capability.handles_handwriting_natively,
            "weights_sha256": provenance["weights_sha256"],
            "runtime": provenance["runtime"],
            "runtime_version": provenance["runtime_version"],
        }
    )
    configuration_status = getattr(engine, "configuration_status", None)
    if callable(configuration_status):
        payload["configuration"] = configuration_status()
    else:
        payload["configuration"] = {
            "configured": True,
            "reason": "no external configuration required",
        }
    return payload


def provider_family(engine: "TranslationEngine") -> str:
    explicit = str(getattr(engine, "provider_family", "") or "")
    if explicit in VALID_PROVIDER_FAMILIES:
        return explicit
    return infer_provider_family(engine.capability.id)


def infer_provider_family(engine_id: str) -> str:
    lowered = engine_id.lower()
    if engine_id == "passthrough":
        return "passthrough"
    if (
        "ct2" in lowered
        or "opus" in lowered
        or "nllb" in lowered
        or "madlad" in lowered
    ):
        return "ct2_nmt"
    if "cloud" in lowered or "vertex" in lowered or "gemini" in lowered:
        return "llm_cloud"
    if "llm" in lowered:
        return "llm_local"
    return "unknown"


def quality_scores_payload(
    translated_spans: list[dict[str, Any]],
    *,
    quality_class: str,
) -> dict[str, Any]:
    scores = [
        span["quality_score"]
        for span in translated_spans
        if span.get("quality_score") is not None
    ]
    return {
        "mean_score": sum(scores) / len(scores) if scores else None,
        "below_threshold_count": sum(1 for score in scores if score < 0.7),
        "quality_class": quality_class,
    }
