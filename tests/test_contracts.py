from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from edc_translation.contracts import load_schema, validate_payload

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "edc_contracts"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_document_bundle_fixture_validates():
    payload = _load("document-bundle-v1.valid.json")
    validate_payload(payload, "document-bundle-v1")


def test_translation_bundle_fixture_validates():
    payload = _load("translation-bundle-v1.valid.json")
    validate_payload(payload, "translation-bundle-v1")


def test_schema_rejects_missing_source_bundle_sha():
    payload = _load("translation-bundle-v1.valid.json")
    payload.pop("source_bundle_sha256")
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_payload(payload, "translation-bundle-v1")


def test_schema_titles_are_stable():
    assert load_schema("document-bundle-v1")["title"] == "EDC DocumentBundle v1"
    assert load_schema("translation-bundle-v1")["title"] == "EDC TranslationBundle v1"
