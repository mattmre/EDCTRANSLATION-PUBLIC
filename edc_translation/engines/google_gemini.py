"""Google Gemini API translation adapter."""

from __future__ import annotations

import os
from typing import Any

from edc_translation.engines import register_engine
from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.llm_live import (
    DEFAULT_MAX_TOKENS,
    GOOGLE_MODEL_ID_ENV,
    LIVE_SMOKE_ENV,
    gemini_provider_config_status,
    live_smoke_enabled,
    translate_with_gemini,
)
from edc_translation.models import EngineCapability


@register_engine
class GoogleGeminiEngine(TranslationEngine):
    provider_family = "llm_cloud"
    capability = EngineCapability(
        id="google_gemini",
        is_local=False,
        is_cloud=True,
        supports_pairs="any",
        quality_class="standard",
        latency_class="standard",
        license="provider-dependent",
        provider_retention_class="unknown",
        deployment_envs=["single-server", "kubernetes", "federated"],
        cost_per_1m_tokens_usd=None,
    )

    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        if not live_smoke_enabled():
            raise RuntimeError(f"{LIVE_SMOKE_ENV}=1 is required for cloud calls")
        api_key = _google_api_key()
        model_id = os.environ.get(GOOGLE_MODEL_ID_ENV, "").strip()
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY is unset")
        if not model_id:
            raise RuntimeError(f"{GOOGLE_MODEL_ID_ENV} is unset")
        translated = translate_with_gemini(
            model_id=model_id,
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        return EngineTranslation(translated_text=translated, confidence=0.75)

    def model_provenance(self) -> dict[str, str]:
        return {
            "weights_sha256": "provider-managed",
            "license": self.capability.license,
            "runtime": "google_gemini",
            "runtime_version": "v1beta",
            "model_id": os.environ.get(GOOGLE_MODEL_ID_ENV, "unconfigured"),
        }

    def configuration_status(self) -> dict[str, Any]:
        return gemini_provider_config_status()


def _google_api_key() -> str:
    return os.environ.get("GOOGLE_API_KEY", "").strip() or os.environ.get(
        "GEMINI_API_KEY",
        "",
    ).strip()
