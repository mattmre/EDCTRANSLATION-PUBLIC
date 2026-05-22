from __future__ import annotations

from dataclasses import dataclass

import pytest

from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.engines.metadata import (
    engine_list_entry,
    engine_model_provenance,
    engine_provider_payload,
    infer_provider_family,
    quality_scores_payload,
)
from edc_translation.models import EngineCapability


@dataclass
class _FakeEngine(TranslationEngine):
    capability = EngineCapability(
        id="opus_mt",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="standard",
        latency_class="bulk",
        license="CC-BY-4.0",
        provider_retention_class="local_only",
        deployment_envs=["local"],
        cost_per_1m_chars_usd=0.0,
    )
    provider_family = "not-a-schema-family"

    provenance: object = None

    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        return EngineTranslation(translated_text=text)

    def model_provenance(self) -> object:
        return self.provenance if self.provenance is not None else {}

    def runtime_info(self) -> dict[str, str]:
        return {"runtime": "fake-runtime", "version": "9.9.9"}


@pytest.mark.parametrize(
    ("engine_id", "family"),
    [
        ("passthrough", "passthrough"),
        ("opus_mt", "ct2_nmt"),
        ("nllb_200", "ct2_nmt"),
        ("madlad_400", "ct2_nmt"),
        ("vertex_translate", "llm_cloud"),
        ("local_llm_runtime", "llm_local"),
        ("custom", "unknown"),
    ],
)
def test_infer_provider_family_matches_ocr_bundle_adapter(engine_id, family):
    assert infer_provider_family(engine_id) == family


def test_engine_provider_payload_infers_schema_family_when_explicit_invalid():
    engine = _FakeEngine()

    payload = engine_provider_payload(engine)

    assert payload == {
        "id": "opus_mt",
        "family": "ct2_nmt",
        "is_local": True,
        "is_cloud": False,
        "license": "CC-BY-4.0",
        "provider_retention_class": "local_only",
    }


def test_engine_model_provenance_defaults_missing_fields():
    provenance = engine_model_provenance(_FakeEngine({"weights_sha256": "not_loaded"}))

    assert provenance["weights_sha256"] == "not_loaded"
    assert provenance["license"] == "CC-BY-4.0"
    assert provenance["runtime"] == "fake-runtime"
    assert provenance["runtime_version"] == "9.9.9"


def test_engine_model_provenance_tolerates_non_mapping_output():
    provenance = engine_model_provenance(_FakeEngine(["bad"]))

    assert provenance["weights_sha256"] == "unknown"
    assert provenance["license"] == "CC-BY-4.0"


def test_engine_list_entry_includes_capability_and_runtime_metadata():
    entry = engine_list_entry(_FakeEngine({"weights_sha256": "not_loaded"}))

    assert entry["id"] == "opus_mt"
    assert entry["family"] == "ct2_nmt"
    assert entry["quality_class"] == "standard"
    assert entry["latency_class"] == "bulk"
    assert entry["deployment_envs"] == ["local"]
    assert entry["cost_per_1m_chars_usd"] == 0.0
    assert entry["runtime_version"] == "9.9.9"


def test_quality_scores_payload_matches_bundle_contract_shape():
    payload = quality_scores_payload(
        [
            {"quality_score": 0.6},
            {"quality_score": 0.8},
            {"quality_score": None},
        ],
        quality_class="draft",
    )

    assert payload == {
        "mean_score": 0.7,
        "below_threshold_count": 1,
        "quality_class": "draft",
    }
