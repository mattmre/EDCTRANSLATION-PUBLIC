"""Visible stub engine for manual skeleton checks."""

from __future__ import annotations

from edc_translation.engines import register_engine
from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.models import EngineCapability


@register_engine
class StubEngine(TranslationEngine):
    capability = EngineCapability(
        id="stub",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="draft",
        latency_class="realtime",
        license="Apache-2.0",
        provider_retention_class="local_only",
        deployment_envs=["local", "air_gapped", "kubernetes"],
    )
    provider_family = "passthrough"

    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        return EngineTranslation(
            translated_text=f"[stub:{target_language}] {text}",
            confidence=0.9,
        )
