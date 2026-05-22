"""Local model bundle validation and registry status."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from edc_translation.provenance import (
    ProvenanceError,
    load_model_provenance_from_dir,
)


@dataclass
class ModelBundleStatus:
    model_id: str
    path: str
    valid: bool
    approved: bool
    errors: list[str]
    provenance: dict[str, Any] | None = None
    engine_family: str | None = None
    license: str | None = None
    vram_profile: str | None = None
    cache_location: str | None = None
    quality_evidence_ref: str | None = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelBundleStatus":
        return cls(
            model_id=str(payload["model_id"]),
            path=str(payload["path"]),
            valid=bool(payload["valid"]),
            approved=bool(payload["approved"]),
            errors=list(payload.get("errors") or []),
            provenance=(
                dict(payload["provenance"])
                if isinstance(payload.get("provenance"), dict)
                else None
            ),
            engine_family=_optional_str(payload.get("engine_family")),
            license=_optional_str(payload.get("license")),
            vram_profile=_optional_str(payload.get("vram_profile")),
            cache_location=_optional_str(payload.get("cache_location")),
            quality_evidence_ref=_optional_str(payload.get("quality_evidence_ref")),
            updated_at=str(
                payload.get("updated_at") or datetime.now(timezone.utc).isoformat()
            ),
        )


class ModelRegistry:
    def __init__(self) -> None:
        self._statuses: dict[str, ModelBundleStatus] = {}
        self._lock = Lock()

    def validate_bundle(
        self,
        model_dir: str | Path,
        *,
        model_id: str | None = None,
        enforce_supply_chain: bool = True,
        engine_family: str | None = None,
        vram_profile: str | None = None,
        cache_location: str | None = None,
        quality_evidence_ref: str | None = None,
    ) -> ModelBundleStatus:
        path = Path(model_dir)
        resolved_model_id = model_id or path.name or "model"
        errors: list[str] = []
        provenance: dict[str, Any] | None = None
        if not path.is_dir():
            errors.append(f"model directory does not exist: {path}")
        else:
            for filename in ("source.spm", "target.spm"):
                if not (path / filename).is_file():
                    errors.append(f"missing required file: {filename}")
            try:
                provenance = load_model_provenance_from_dir(
                    path,
                    enforce_supply_chain=enforce_supply_chain,
                    allow_unloaded_weights=False,
                )
            except (FileNotFoundError, ProvenanceError) as exc:
                errors.append(str(exc))

        status = ModelBundleStatus(
            model_id=resolved_model_id,
            path=str(path),
            valid=not errors,
            approved=not errors and enforce_supply_chain,
            errors=errors,
            provenance=provenance,
            engine_family=engine_family,
            license=(
                str(provenance["license"])
                if isinstance(provenance, dict) and provenance.get("license") is not None
                else None
            ),
            vram_profile=vram_profile,
            cache_location=cache_location,
            quality_evidence_ref=quality_evidence_ref,
        )
        with self._lock:
            self._statuses[resolved_model_id] = status
        return status

    def list(self) -> list[ModelBundleStatus]:
        with self._lock:
            return list(self._statuses.values())

    def get(self, model_id: str) -> ModelBundleStatus:
        with self._lock:
            return self._statuses[model_id]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
