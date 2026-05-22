from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from edc_translation.contracts import validate_payload
from edc_translation.engines import ENGINE_REGISTRY, get_engine
from edc_translation.engines.local_ct2_opus import LocalCT2OpusEngine
from edc_translation.provenance import ProvenanceMissingError
from edc_translation.service import list_engine_providers, translate_document_bundle

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edc_contracts"


def test_local_ct2_opus_is_registered_with_local_metadata(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    assert ENGINE_REGISTRY["local_ct2_opus"] is LocalCT2OpusEngine

    entry = next(
        provider
        for provider in list_engine_providers()
        if provider["id"] == "local_ct2_opus"
    )

    assert entry["family"] == "ct2_nmt"
    assert entry["is_local"] is True
    assert entry["is_cloud"] is False
    assert entry["license"] == "CC-BY-4.0"
    assert entry["provider_retention_class"] == "local_only"
    assert entry["weights_sha256"] == "not_loaded"


def test_local_ct2_opus_fails_closed_without_model_dir(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)
    engine = get_engine("local_ct2_opus")()

    with pytest.raises(RuntimeError, match="model directory"):
        engine.translate_text(
            "hello",
            source_language="en",
            target_language="fr",
        )


def test_local_ct2_opus_fails_closed_without_optional_runtime(tmp_path):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    (model_dir / "source.spm").write_text("source", encoding="utf-8")
    (model_dir / "target.spm").write_text("target", encoding="utf-8")

    with mock.patch.dict(
        sys.modules,
        {"ctranslate2": None, "sentencepiece": None},
    ):
        engine = LocalCT2OpusEngine(model_dir=model_dir)
        with pytest.raises(RuntimeError, match="ctranslate2"):
            engine.translate_text(
                "hello",
                source_language="en",
                target_language="fr",
            )


def test_local_ct2_opus_model_provenance_reads_model_files(tmp_path):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    digest = "a" * 64
    (model_dir / "MODEL_SHA256").write_text(f"{digest}\n", encoding="utf-8")

    provenance = LocalCT2OpusEngine(model_dir=model_dir).model_provenance()

    assert provenance["weights_sha256"] == digest
    assert provenance["license"] == "CC-BY-4.0"
    assert provenance["runtime"] == "ctranslate2"
    assert provenance["runtime_version"] == "not_loaded"
    assert provenance["model_dir_configured"] is True


def test_local_ct2_opus_loads_valid_provenance_json(tmp_path):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    payload = {
        "slsa_provenance_uri": "https://models.example/opus/slsa.intoto.jsonl",
        "intoto_attestation_sha256": "A" * 64,
        "sbom_sha256": "B" * 64,
        "weights_sha256": "C" * 64,
        "license": "CC-BY-4.0",
        "runtime_version": "4.6.1",
        "extra": "preserved",
    }
    (model_dir / "provenance.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    provenance = LocalCT2OpusEngine(model_dir=model_dir).model_provenance()

    assert provenance["weights_sha256"] == "c" * 64
    assert provenance["intoto_attestation_sha256"] == "a" * 64
    assert provenance["sbom_sha256"] == "b" * 64
    assert provenance["runtime_version"] == "4.6.1"
    assert provenance["extra"] == "preserved"


def test_local_ct2_opus_rejects_incomplete_provenance_json(tmp_path):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    payload = {
        "weights_sha256": "c" * 64,
        "license": "CC-BY-4.0",
        "runtime_version": "4.6.1",
    }
    (model_dir / "provenance.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceMissingError, match="slsa_provenance_uri"):
        LocalCT2OpusEngine(model_dir=model_dir).model_provenance()


def test_local_ct2_opus_uses_fake_ct2_runtime(tmp_path, monkeypatch):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    (model_dir / "source.spm").write_text("source", encoding="utf-8")
    (model_dir / "target.spm").write_text("target", encoding="utf-8")

    class _Translator:
        def __init__(self, model_path: str, device: str) -> None:
            assert model_path == str(model_dir)
            assert device == "cpu"

        def translate_batch(self, batch, **kwargs):
            assert batch == [["Hello", "world"]]
            assert kwargs["beam_size"] == 4
            return [SimpleNamespace(hypotheses=[["Bonjour", "monde"]])]

    class _SentencePiece:
        def __init__(self, model_file: str) -> None:
            self.model_file = model_file

        def encode(self, text: str, out_type=str):
            assert text == "Hello world"
            assert out_type is str
            return ["Hello", "world"]

        def decode(self, pieces):
            assert pieces == ["Bonjour", "monde"]
            return "Bonjour monde"

    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(Translator=_Translator, __version__="4.5.0"),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentencepiece",
        SimpleNamespace(SentencePieceProcessor=_SentencePiece),
    )

    engine = LocalCT2OpusEngine(model_dir=model_dir)
    result = engine.translate_text(
        "Hello world",
        source_language="en",
        target_language="fr",
    )

    assert result.translated_text == "Bonjour monde"
    assert result.confidence == 0.85
    assert engine.runtime_info() == {"runtime": "ctranslate2", "version": "4.5.0"}


def test_local_ct2_opus_service_path_emits_valid_translation_bundle(
    tmp_path,
    monkeypatch,
):
    model_dir = tmp_path / "opus"
    model_dir.mkdir()
    (model_dir / "source.spm").write_text("source", encoding="utf-8")
    (model_dir / "target.spm").write_text("target", encoding="utf-8")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))

    class _Translator:
        def __init__(self, model_path: str, device: str) -> None:
            assert model_path == str(model_dir)
            assert device == "cpu"

        def translate_batch(self, batch, **kwargs):
            del kwargs
            return [
                SimpleNamespace(hypotheses=[["fr:"] + tokenized])
                for tokenized in batch
            ]

    class _SentencePiece:
        def __init__(self, model_file: str) -> None:
            self.model_file = model_file

        def encode(self, text: str, out_type=str):
            assert out_type is str
            return text.split()

        def decode(self, pieces):
            return " ".join(pieces)

    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(Translator=_Translator, __version__="4.5.0"),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentencepiece",
        SimpleNamespace(SentencePieceProcessor=_SentencePiece),
    )
    document = json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )

    bundle = translate_document_bundle(
        document,
        target_language="fr",
        provider_id="local_ct2_opus",
    )

    validate_payload(bundle, "translation-bundle-v1")
    assert bundle["engine_provider"]["id"] == "local_ct2_opus"
    assert bundle["engine_provider"]["family"] == "ct2_nmt"
    assert bundle["translated_spans"][0]["translated_text"].startswith("fr:")
