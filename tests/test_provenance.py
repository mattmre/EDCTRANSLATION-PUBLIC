from __future__ import annotations

import json

import pytest

from edc_translation.provenance import (
    PROVENANCE_FILE_NAME,
    REQUIRED_BASE_FIELDS,
    REQUIRED_SUPPLY_CHAIN_FIELDS,
    ModelProvenance,
    ProvenanceCorruptError,
    ProvenanceMissingError,
    load_model_provenance_from_dir,
    normalize_model_provenance,
    validate_model_provenance,
)


def _payload(**overrides):
    payload = {
        "slsa_provenance_uri": "https://models.example/opus/slsa.intoto.jsonl",
        "intoto_attestation_sha256": "a" * 64,
        "sbom_sha256": "b" * 64,
        "weights_sha256": "c" * 64,
        "license": "CC-BY-4.0",
        "runtime_version": "4.6.1",
    }
    payload.update(overrides)
    return payload


def test_required_field_constants_match_contract_names():
    assert REQUIRED_BASE_FIELDS == (
        "weights_sha256",
        "license",
        "runtime_version",
    )
    assert REQUIRED_SUPPLY_CHAIN_FIELDS == (
        "slsa_provenance_uri",
        "intoto_attestation_sha256",
        "sbom_sha256",
    )


def test_validate_model_provenance_accepts_complete_record():
    record = validate_model_provenance(_payload())

    assert isinstance(record, ModelProvenance)
    assert record.weights_sha256 == "c" * 64
    assert record.license == "CC-BY-4.0"
    assert record.runtime_version == "4.6.1"


@pytest.mark.parametrize("field", REQUIRED_SUPPLY_CHAIN_FIELDS)
def test_validate_model_provenance_rejects_missing_supply_chain_field(field):
    payload = _payload()
    payload.pop(field)

    with pytest.raises(ProvenanceMissingError, match=field):
        validate_model_provenance(payload, enforce_supply_chain=True)


@pytest.mark.parametrize("field", REQUIRED_BASE_FIELDS)
def test_validate_model_provenance_rejects_missing_base_field(field):
    payload = _payload()
    payload.pop(field)

    with pytest.raises(ProvenanceMissingError, match=field):
        validate_model_provenance(payload, enforce_supply_chain=False)


def test_validate_model_provenance_enforce_false_fills_unverified():
    payload = _payload()
    for field in REQUIRED_SUPPLY_CHAIN_FIELDS:
        payload.pop(field)

    record = validate_model_provenance(payload, enforce_supply_chain=False)

    assert record.slsa_provenance_uri == "unverified"
    assert record.intoto_attestation_sha256 == "unverified"
    assert record.sbom_sha256 == "unverified"


def test_validate_model_provenance_rejects_unloaded_weight_for_loaded_model():
    with pytest.raises(ProvenanceMissingError, match="weights_sha256"):
        validate_model_provenance(
            _payload(weights_sha256="not_loaded"),
            allow_unloaded_weights=False,
        )


def test_validate_model_provenance_lowercases_sha256_fields():
    record = validate_model_provenance(
        _payload(
            intoto_attestation_sha256="A" * 64,
            sbom_sha256="B" * 64,
            weights_sha256="C" * 64,
        )
    )

    assert record.intoto_attestation_sha256 == "a" * 64
    assert record.sbom_sha256 == "b" * 64
    assert record.weights_sha256 == "c" * 64


def test_normalize_model_provenance_preserves_extra_fields():
    normalized = normalize_model_provenance(
        _payload(engine_id="local_ct2_opus"),
    )

    assert normalized["engine_id"] == "local_ct2_opus"
    assert normalized["weights_sha256"] == "c" * 64


def test_load_model_provenance_from_dir_validates_file(tmp_path):
    payload = _payload()
    (tmp_path / PROVENANCE_FILE_NAME).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    assert load_model_provenance_from_dir(tmp_path)["weights_sha256"] == "c" * 64


def test_load_model_provenance_from_dir_rejects_malformed_json(tmp_path):
    (tmp_path / PROVENANCE_FILE_NAME).write_text("{not json", encoding="utf-8")

    with pytest.raises(ProvenanceCorruptError):
        load_model_provenance_from_dir(tmp_path)


def test_load_model_provenance_from_dir_rejects_non_object(tmp_path):
    (tmp_path / PROVENANCE_FILE_NAME).write_text("[]", encoding="utf-8")

    with pytest.raises(ProvenanceCorruptError):
        load_model_provenance_from_dir(tmp_path)
