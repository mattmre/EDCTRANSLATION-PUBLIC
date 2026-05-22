from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from edc_translation.contracts import validate_payload
from edc_translation.engines.local_ct2_opus import LocalCT2OpusEngine
from edc_translation.models import TranslationRequest
from edc_translation.routing import (
    AUTO_PROVIDER_ID,
    EngineRoutingPolicy,
    RoutingError,
    diagnose_auto_route,
    engine_availability,
    resolve_provider_id,
    select_auto_provider_id,
)
from edc_translation.service import translate_document_bundle

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edc_contracts"


def _request(src: str = "en", tgt: str = "fr") -> TranslationRequest:
    return TranslationRequest(src_lang=src, tgt_lang=tgt, tenant_id="test")


def _document_bundle() -> dict:
    return json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )


def _model_dir(tmp_path: Path, name: str) -> Path:
    model_dir = tmp_path / name
    model_dir.mkdir()
    (model_dir / "source.spm").write_text("source", encoding="utf-8")
    (model_dir / "target.spm").write_text("target", encoding="utf-8")
    return model_dir


def _install_fake_ct2(monkeypatch, model_dir: Path, marker: str = "auto") -> None:
    class _Translator:
        def __init__(self, model_path: str, device: str) -> None:
            assert model_path == str(model_dir)
            assert device == "cpu"

        def translate_batch(self, batch, **kwargs):
            del kwargs
            return [
                SimpleNamespace(hypotheses=[[marker] + tokenized])
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


def test_explicit_provider_id_bypasses_auto_routing(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    assert resolve_provider_id("stub", _request()) == "stub"


def test_auto_routes_same_language_to_passthrough(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    assert select_auto_provider_id(_request(src="en", tgt="en")) == "passthrough"


def test_diagnose_auto_route_explains_same_language_passthrough(monkeypatch):
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)

    diagnostics = diagnose_auto_route(_request(src="en", tgt="en"))

    assert diagnostics["selected_provider_id"] == "passthrough"
    assert diagnostics["candidates"][0]["id"] == "passthrough"
    assert diagnostics["candidates"][0]["reason"] == "same-language passthrough"


def test_auto_rejects_cross_language_when_no_model_dirs_configured(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    with pytest.raises(RoutingError, match="No auto-routeable"):
        select_auto_provider_id(_request())


def test_auto_routing_error_carries_diagnostics(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    with pytest.raises(RoutingError) as exc_info:
        select_auto_provider_id(_request())

    diagnostics = exc_info.value.diagnostics
    assert diagnostics["provider_id"] == "auto"
    assert diagnostics["source_language"] == "en"
    assert diagnostics["target_language"] == "fr"
    assert diagnostics["selected_provider_id"] is None
    assert any(
        candidate["id"] == "local_ct2_opus"
        and candidate["reason"] == "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR is unset"
        for candidate in diagnostics["candidates"]
    )


def test_diagnose_auto_route_reports_unconfigured_candidates(monkeypatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    diagnostics = diagnose_auto_route(_request())
    reasons = {
        candidate["id"]: candidate["reason"]
        for candidate in diagnostics["candidates"]
    }

    assert diagnostics["selected_provider_id"] is None
    assert (
        reasons["local_ct2_opus"]
        == "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR is unset"
    )
    assert reasons["local_ct2_nllb"] == "NC license blocked"


def test_engine_availability_requires_tokenizer_files(tmp_path, monkeypatch):
    model_dir = tmp_path / "missing-tokenizers"
    model_dir.mkdir()
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))

    availability = engine_availability(LocalCT2OpusEngine)

    assert availability.available is False
    assert "source.spm" in availability.reason
    assert "target.spm" in availability.reason


def test_auto_routes_to_configured_opus_model_dir(tmp_path, monkeypatch):
    model_dir = _model_dir(tmp_path, "opus")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", raising=False)
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)

    selected = select_auto_provider_id(_request())

    assert selected == "local_ct2_opus"


def test_diagnose_auto_route_marks_selected_engine(tmp_path, monkeypatch):
    model_dir = _model_dir(tmp_path, "opus")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", raising=False)
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)

    diagnostics = diagnose_auto_route(_request())
    selected = next(
        candidate
        for candidate in diagnostics["candidates"]
        if candidate["id"] == "local_ct2_opus"
    )

    assert diagnostics["selected_provider_id"] == "local_ct2_opus"
    assert selected["eligible"] is True
    assert selected["selected"] is True
    assert selected["reason"] == "selected"


def test_auto_blocks_nc_licensed_nllb_by_default(tmp_path, monkeypatch):
    model_dir = _model_dir(tmp_path, "nllb")
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)

    with pytest.raises(RoutingError, match="NC license blocked"):
        select_auto_provider_id(
            _request(),
            policy=EngineRoutingPolicy(preferred_engine_ids=("local_ct2_nllb",)),
        )


def test_auto_can_allow_nc_licensed_nllb(tmp_path, monkeypatch):
    model_dir = _model_dir(tmp_path, "nllb")
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", raising=False)
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)

    selected = select_auto_provider_id(
        _request(),
        policy=EngineRoutingPolicy(
            allow_nc_licensed=True,
            preferred_engine_ids=("local_ct2_nllb",),
        ),
    )

    assert selected == "local_ct2_nllb"


def test_translate_document_bundle_auto_uses_routed_engine(tmp_path, monkeypatch):
    model_dir = _model_dir(tmp_path, "opus")
    monkeypatch.setenv("EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR", raising=False)
    monkeypatch.delenv("EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR", raising=False)
    _install_fake_ct2(monkeypatch, model_dir)

    bundle = translate_document_bundle(
        _document_bundle(),
        target_language="fr",
        provider_id=AUTO_PROVIDER_ID,
    )

    validate_payload(bundle, "translation-bundle-v1")
    assert bundle["engine_provider"]["id"] == "local_ct2_opus"
    assert bundle["translated_spans"][0]["translated_text"].startswith("auto")
