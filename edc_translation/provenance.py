"""Model provenance validation helpers for EDC_TRANSLATION."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROVENANCE_FILE_NAME = "provenance.json"

REQUIRED_BASE_FIELDS = (
    "weights_sha256",
    "license",
    "runtime_version",
)
REQUIRED_SUPPLY_CHAIN_FIELDS = (
    "slsa_provenance_uri",
    "intoto_attestation_sha256",
    "sbom_sha256",
)

_SHA256_HEX_LENGTH = 64
_UNLOADED_WEIGHT_SENTINELS = {"not_loaded", "n/a", "unknown"}
_UNVERIFIED_SENTINEL = "unverified"


class ProvenanceError(RuntimeError):
    """Base class for model provenance validation errors."""


class ProvenanceMissingError(ProvenanceError):
    """Raised when required provenance fields are absent or malformed."""


class ProvenanceCorruptError(ProvenanceError):
    """Raised when a provenance file cannot be parsed as a JSON object."""


@dataclasses.dataclass(frozen=True)
class ModelProvenance:
    """Validated model provenance record."""

    slsa_provenance_uri: str
    intoto_attestation_sha256: str
    sbom_sha256: str
    weights_sha256: str
    license: str
    runtime_version: str

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def load_model_provenance_from_dir(
    model_dir: str | Path,
    *,
    enforce_supply_chain: bool = True,
    allow_unloaded_weights: bool = False,
) -> dict[str, Any]:
    """Load and validate ``provenance.json`` from a model directory."""

    path = Path(model_dir) / PROVENANCE_FILE_NAME
    if not path.is_file():
        raise FileNotFoundError(f"model provenance file missing at {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceCorruptError(
            f"model provenance file at {path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProvenanceCorruptError(
            f"model provenance file at {path} must contain a JSON object"
        )

    return normalize_model_provenance(
        payload,
        enforce_supply_chain=enforce_supply_chain,
        allow_unloaded_weights=allow_unloaded_weights,
    )


def normalize_model_provenance(
    provenance: Mapping[str, Any],
    *,
    enforce_supply_chain: bool = True,
    allow_unloaded_weights: bool = True,
) -> dict[str, Any]:
    """Return a validated provenance payload while preserving extra fields."""

    record = validate_model_provenance(
        provenance,
        enforce_supply_chain=enforce_supply_chain,
        allow_unloaded_weights=allow_unloaded_weights,
    )
    normalized = dict(provenance)
    normalized.update(record.to_dict())
    return normalized


def validate_model_provenance(
    provenance: Mapping[str, Any],
    *,
    enforce_supply_chain: bool = True,
    allow_unloaded_weights: bool = True,
) -> ModelProvenance:
    """Validate model provenance and return normalized core fields."""

    if not isinstance(provenance, Mapping):
        raise ProvenanceMissingError(
            f"model provenance must be a mapping, got {type(provenance).__name__}"
        )

    weights_sha256 = _required_string("weights_sha256", provenance)
    license_ = _required_string("license", provenance)
    runtime_version = _required_string("runtime_version", provenance)
    weights_sha256 = _normalize_weights_sha256(
        weights_sha256,
        allow_unloaded_weights=allow_unloaded_weights,
    )

    slsa_uri = provenance.get("slsa_provenance_uri")
    intoto_sha = provenance.get("intoto_attestation_sha256")
    sbom_sha = provenance.get("sbom_sha256")

    missing = [
        field
        for field, value in (
            ("slsa_provenance_uri", slsa_uri),
            ("intoto_attestation_sha256", intoto_sha),
            ("sbom_sha256", sbom_sha),
        )
        if not isinstance(value, str) or not value.strip()
    ]
    if missing and enforce_supply_chain:
        raise ProvenanceMissingError(
            "model provenance missing required supply-chain fields: "
            f"{', '.join(missing)}"
        )
    if missing:
        slsa_uri = _coalesce_unverified(slsa_uri)
        intoto_sha = _coalesce_unverified(intoto_sha)
        sbom_sha = _coalesce_unverified(sbom_sha)

    slsa_uri = _required_string_value("slsa_provenance_uri", slsa_uri)
    intoto_sha = _normalize_optional_sha256(
        "intoto_attestation_sha256",
        intoto_sha,
    )
    sbom_sha = _normalize_optional_sha256("sbom_sha256", sbom_sha)

    return ModelProvenance(
        slsa_provenance_uri=slsa_uri,
        intoto_attestation_sha256=intoto_sha,
        sbom_sha256=sbom_sha,
        weights_sha256=weights_sha256,
        license=license_,
        runtime_version=runtime_version,
    )


def _required_string(field: str, provenance: Mapping[str, Any]) -> str:
    return _required_string_value(field, provenance.get(field))


def _required_string_value(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceMissingError(
            f"model provenance field {field!r} must be a non-empty string"
        )
    return value.strip()


def _normalize_weights_sha256(
    value: str,
    *,
    allow_unloaded_weights: bool,
) -> str:
    normalized = value.strip().lower()
    if normalized in _UNLOADED_WEIGHT_SENTINELS:
        if allow_unloaded_weights:
            return normalized
        raise ProvenanceMissingError(
            "weights_sha256 must be a real SHA-256 digest for loaded model "
            "provenance"
        )
    return _normalize_sha256("weights_sha256", normalized)


def _normalize_optional_sha256(field: str, value: Any) -> str:
    normalized = _required_string_value(field, value).lower()
    if normalized == _UNVERIFIED_SENTINEL:
        return normalized
    return _normalize_sha256(field, normalized)


def _normalize_sha256(field: str, value: str) -> str:
    if len(value) != _SHA256_HEX_LENGTH:
        raise ProvenanceMissingError(
            f"{field} must be a 64-character SHA-256 hex digest"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProvenanceMissingError(
            f"{field} must be a 64-character SHA-256 hex digest"
        ) from exc
    return value


def _coalesce_unverified(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return _UNVERIFIED_SENTINEL
    return value
