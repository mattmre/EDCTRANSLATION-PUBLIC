from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from edc_translation.engines import ENGINE_REGISTRY
from edc_translation.engines.local_ct2_madlad import LocalCT2MADLADEngine
from edc_translation.engines.local_ct2_nllb import LocalCT2NLLBEngine
from edc_translation.engines.local_ct2_opus import LocalCT2OpusEngine
from edc_translation.service import list_engine_providers

ENGINE_CASES = (
    (LocalCT2OpusEngine, "local_ct2_opus", "CC-BY-4.0"),
    (LocalCT2NLLBEngine, "local_ct2_nllb", "CC-BY-NC-4.0"),
    (LocalCT2MADLADEngine, "local_ct2_madlad", "Apache-2.0"),
)


def _clear_model_envs(monkeypatch):
    for engine_cls, _engine_id, _license in ENGINE_CASES:
        monkeypatch.delenv(engine_cls.model_dir_env, raising=False)


@pytest.mark.parametrize(("engine_cls", "engine_id", "license"), ENGINE_CASES)
def test_ct2_adapter_metadata_is_registered(engine_cls, engine_id, license, monkeypatch):
    _clear_model_envs(monkeypatch)

    assert ENGINE_REGISTRY[engine_id] is engine_cls

    entry = next(
        provider for provider in list_engine_providers() if provider["id"] == engine_id
    )
    assert entry["family"] == "ct2_nmt"
    assert entry["is_local"] is True
    assert entry["is_cloud"] is False
    assert entry["license"] == license
    assert entry["provider_retention_class"] == "local_only"
    assert entry["weights_sha256"] == "not_loaded"


@pytest.mark.parametrize(("engine_cls", "engine_id", "_license"), ENGINE_CASES)
def test_ct2_adapters_fail_closed_without_model_dir(
    engine_cls,
    engine_id,
    _license,
    monkeypatch,
):
    _clear_model_envs(monkeypatch)

    with pytest.raises(RuntimeError, match=engine_id):
        engine_cls().translate_text(
            "hello",
            source_language="en",
            target_language="fr",
        )


@pytest.mark.parametrize(("engine_cls", "engine_id", "license"), ENGINE_CASES)
def test_ct2_adapters_read_model_sha256(engine_cls, engine_id, license, tmp_path):
    model_dir = tmp_path / engine_id
    model_dir.mkdir()
    digest = "d" * 64
    (model_dir / "MODEL_SHA256").write_text(f"{digest}\n", encoding="utf-8")

    provenance = engine_cls(model_dir=model_dir).model_provenance()

    assert provenance["weights_sha256"] == digest
    assert provenance["license"] == license
    assert provenance["runtime"] == "ctranslate2"
    assert provenance["runtime_version"] == "not_loaded"
    assert provenance["model_dir_env"] == engine_cls.model_dir_env


@pytest.mark.parametrize(("engine_cls", "engine_id", "_license"), ENGINE_CASES)
def test_ct2_adapters_use_fake_runtime(engine_cls, engine_id, _license, tmp_path, monkeypatch):
    model_dir = tmp_path / engine_id
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
            return [SimpleNamespace(hypotheses=[[engine_id, "Bonjour", "monde"]])]

    class _SentencePiece:
        def __init__(self, model_file: str) -> None:
            self.model_file = model_file

        def encode(self, text: str, out_type=str):
            assert text == "Hello world"
            assert out_type is str
            return ["Hello", "world"]

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

    result = engine_cls(model_dir=model_dir).translate_text(
        "Hello world",
        source_language="en",
        target_language="fr",
    )

    assert result.translated_text == f"{engine_id} Bonjour monde"
    assert result.confidence == 0.85
