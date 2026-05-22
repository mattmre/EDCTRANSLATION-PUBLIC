"""Opt-in translation engine routing for EDC_TRANSLATION."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from edc_translation.errors import auto_route_unavailable_message
from edc_translation.engines import get_engine

if TYPE_CHECKING:
    from edc_translation.engines.base import TranslationEngine
    from edc_translation.models import EngineCapability, TranslationRequest

AUTO_PROVIDER_ID = "auto"

DEFAULT_AUTO_ENGINE_IDS = (
    "local_ct2_opus",
    "local_ct2_madlad",
    "local_ct2_nllb",
)


class RoutingError(RuntimeError):
    """Raised when opt-in auto routing cannot select an engine."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class EngineRoutingPolicy:
    """Small standalone routing policy for the split seam."""

    allow_nc_licensed: bool = False
    preferred_engine_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EngineAvailability:
    """Engine availability detail for auto-routing decisions."""

    available: bool
    reason: str


def resolve_provider_id(
    provider_id: str,
    request: "TranslationRequest",
    *,
    policy: EngineRoutingPolicy | None = None,
) -> str:
    """Resolve explicit provider ids or opt-in ``auto`` routing."""

    if provider_id != AUTO_PROVIDER_ID:
        return provider_id
    return select_auto_provider_id(request, policy=policy)


def select_auto_provider_id(
    request: "TranslationRequest",
    *,
    policy: EngineRoutingPolicy | None = None,
) -> str:
    """Select an available provider for an explicit auto-routed request."""

    diagnostics = diagnose_auto_route(request, policy=policy)
    selected = diagnostics["selected_provider_id"]
    if selected:
        return str(selected)

    raise RoutingError(
        auto_route_unavailable_message(
            request.src_lang,
            request.tgt_lang,
            diagnostics,
        ),
        diagnostics=diagnostics,
    )


def diagnose_auto_route(
    request: "TranslationRequest",
    *,
    policy: EngineRoutingPolicy | None = None,
) -> dict[str, object]:
    """Return a structured explanation for an opt-in auto-routing decision."""

    policy = policy or EngineRoutingPolicy()
    if request.src_lang == request.tgt_lang:
        return {
            "provider_id": AUTO_PROVIDER_ID,
            "source_language": request.src_lang,
            "target_language": request.tgt_lang,
            "allow_nc_licensed": policy.allow_nc_licensed,
            "selected_provider_id": "passthrough",
            "candidates": [
                {
                    "id": "passthrough",
                    "registered": True,
                    "eligible": True,
                    "selected": True,
                    "reason": "same-language passthrough",
                    "model_dir_env": None,
                    "model_dir_configured": False,
                }
            ],
        }

    selected_provider_id: str | None = None
    candidates: list[dict[str, object]] = []
    for engine_id in _ordered_auto_engine_ids(policy):
        try:
            engine_cls = get_engine(engine_id)
        except KeyError:
            candidates.append(
                {
                    "id": engine_id,
                    "registered": False,
                    "eligible": False,
                    "selected": False,
                    "reason": "not registered",
                    "model_dir_env": None,
                    "model_dir_configured": False,
                }
            )
            continue

        capability = engine_cls.capability
        candidate = _candidate_base(engine_id, engine_cls)
        if not _supports_pair(capability, request.src_lang, request.tgt_lang):
            candidate["reason"] = (
                f"does not support {request.src_lang}->{request.tgt_lang}"
            )
            candidates.append(candidate)
            continue
        if _is_nc_licensed(capability) and not policy.allow_nc_licensed:
            candidate["reason"] = "NC license blocked"
            candidates.append(candidate)
            continue

        availability = engine_availability(engine_cls)
        if not availability.available:
            candidate["reason"] = availability.reason
            candidates.append(candidate)
            continue

        candidate["eligible"] = True
        if selected_provider_id is None:
            selected_provider_id = engine_id
            candidate["selected"] = True
            candidate["reason"] = "selected"
        else:
            candidate["reason"] = "eligible but lower priority"
        candidates.append(candidate)

    return {
        "provider_id": AUTO_PROVIDER_ID,
        "source_language": request.src_lang,
        "target_language": request.tgt_lang,
        "allow_nc_licensed": policy.allow_nc_licensed,
        "selected_provider_id": selected_provider_id,
        "candidates": candidates,
    }


def engine_availability(
    engine_cls: type["TranslationEngine"],
) -> EngineAvailability:
    """Return whether an engine is configured enough for auto routing."""

    model_dir_env = str(getattr(engine_cls, "model_dir_env", "") or "")
    if not model_dir_env:
        return EngineAvailability(False, "engine has no model_dir_env")

    raw_model_dir = os.getenv(model_dir_env, "").strip()
    if not raw_model_dir:
        return EngineAvailability(False, f"{model_dir_env} is unset")

    model_dir = Path(raw_model_dir)
    if not model_dir.is_dir():
        return EngineAvailability(False, f"{model_dir_env} is not a directory")

    tokenizer_files = tuple(
        getattr(engine_cls, "tokenizer_files", ("source.spm", "target.spm"))
    )
    missing = [name for name in tokenizer_files if not (model_dir / name).is_file()]
    if missing:
        return EngineAvailability(
            False,
            f"{model_dir_env} missing {', '.join(missing)}",
        )

    return EngineAvailability(True, "configured")


def _ordered_auto_engine_ids(policy: EngineRoutingPolicy) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for engine_id in (*policy.preferred_engine_ids, *DEFAULT_AUTO_ENGINE_IDS):
        if engine_id in seen:
            continue
        seen.add(engine_id)
        ordered.append(engine_id)
    return tuple(ordered)


def _candidate_base(
    engine_id: str,
    engine_cls: type["TranslationEngine"],
) -> dict[str, object]:
    capability = engine_cls.capability
    model_dir_env = str(getattr(engine_cls, "model_dir_env", "") or "")
    return {
        "id": engine_id,
        "registered": True,
        "eligible": False,
        "selected": False,
        "reason": "not evaluated",
        "license": capability.license,
        "quality_class": capability.quality_class,
        "provider_retention_class": capability.provider_retention_class,
        "model_dir_env": model_dir_env or None,
        "model_dir_configured": bool(model_dir_env and os.getenv(model_dir_env, "")),
    }


def _supports_pair(
    capability: "EngineCapability",
    source_language: str,
    target_language: str,
) -> bool:
    if capability.supports_pairs == "any":
        return True
    pair = (source_language.lower(), target_language.lower())
    return pair in {
        (source.lower(), target.lower())
        for source, target in capability.supports_pairs
    }


def _is_nc_licensed(capability: "EngineCapability") -> bool:
    return "nc" in capability.license.lower()
