"""Contract schema helpers for EDC_TRANSLATION."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
PACKAGE_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

DOCUMENT_BUNDLE_SCHEMA = "document-bundle-v1"
TRANSLATION_BUNDLE_SCHEMA = "translation-bundle-v1"

KNOWN_SCHEMAS = frozenset(
    {
        DOCUMENT_BUNDLE_SCHEMA,
        TRANSLATION_BUNDLE_SCHEMA,
    }
)


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in KNOWN_SCHEMAS:
        raise ValueError(f"Unknown contract schema: {schema_name!r}")
    schema_path = _schema_path(schema_name)
    with schema_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_payload(payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
    import jsonschema

    schema = load_schema(schema_name)
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(payload, schema)
    return payload


def _schema_path(schema_name: str) -> Path:
    file_name = f"{schema_name}.schema.json"
    for candidate in (
        PACKAGE_SCHEMA_DIR / file_name,
        SCHEMA_DIR / file_name,
        Path.cwd() / "schemas" / file_name,
    ):
        if candidate.is_file():
            return candidate
    return SCHEMA_DIR / file_name
