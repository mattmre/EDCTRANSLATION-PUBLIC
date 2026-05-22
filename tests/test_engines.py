from __future__ import annotations

import pytest

from edc_translation.engines import ENGINE_REGISTRY, get_engine, iter_engines
from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.models import EngineCapability
from edc_translation.providers import get_provider, list_providers


def test_builtin_engines_are_registered():
    assert {
        "passthrough",
        "stub",
        "deterministic_ci",
        "local_ct2_opus",
        "local_ct2_nllb",
        "local_ct2_madlad",
        "local_openai_compat",
        "openrouter_llm",
        "google_gemini",
    }.issubset(ENGINE_REGISTRY)


def test_registered_engines_have_capabilities():
    for engine_id, engine_cls in iter_engines():
        assert issubclass(engine_cls, TranslationEngine)
        assert isinstance(engine_cls.capability, EngineCapability)
        assert engine_cls.capability.id == engine_id


def test_get_engine_unknown_raises():
    with pytest.raises(KeyError):
        get_engine("missing-engine")


def test_passthrough_engine_preserves_text():
    engine = get_engine("passthrough")()
    result = engine.translate_text(
        "hello",
        source_language="en",
        target_language="fr",
    )
    assert isinstance(result, EngineTranslation)
    assert result.translated_text == "hello"


def test_deterministic_ci_engine_marks_language_pair():
    engine = get_engine("deterministic_ci")()
    result = engine.translate_text(
        "hello",
        source_language="en",
        target_language="fr",
    )
    assert result.translated_text == "hello [en->fr]"
    assert result.quality_score == 1.0


def test_engine_model_provenance_includes_license():
    engine = get_engine("passthrough")()
    provenance = engine.model_provenance()
    assert provenance["weights_sha256"] == "n/a"
    assert provenance["license"] == engine.capability.license


def test_provider_compatibility_uses_engine_registry():
    provider = get_provider("stub")
    assert provider.metadata.id == "stub"
    assert provider.translate(
        "hello",
        source_language="en",
        target_language="fr",
    ).translated_text == "[stub:fr] hello"
    ids = {metadata.id for metadata in list_providers()}
    assert "deterministic_ci" in ids
