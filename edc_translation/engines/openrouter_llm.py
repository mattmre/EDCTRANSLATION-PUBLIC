"""OpenRouter cloud LLM translation adapter."""

from __future__ import annotations

import os
from typing import Any

from edc_translation.engines import register_engine
from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.llm_live import (
    DEFAULT_MAX_TOKENS,
    LIVE_SMOKE_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL_IDS_ENV,
    live_smoke_enabled,
    openrouter_provider_config_status,
    split_model_ids,
    translate_with_openai_compatible_chat,
)
from edc_translation.models import EngineCapability


@register_engine
class OpenRouterLLMEngine(TranslationEngine):
    provider_family = "llm_cloud"
    capability = EngineCapability(
        id="openrouter_llm",
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
        api_key = os.environ.get(OPENROUTER_API_KEY_ENV, "").strip()
        model_ids = split_model_ids(os.environ.get(OPENROUTER_MODEL_IDS_ENV))
        if not api_key:
            raise RuntimeError(f"{OPENROUTER_API_KEY_ENV} is unset")
        if not model_ids:
            raise RuntimeError(f"{OPENROUTER_MODEL_IDS_ENV} is unset")
        translated = translate_with_openai_compatible_chat(
            base_url=OPENROUTER_BASE_URL,
            model_id=model_ids[0],
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        return EngineTranslation(translated_text=translated, confidence=0.75)

    def model_provenance(self) -> dict[str, str]:
        model_ids = split_model_ids(os.environ.get(OPENROUTER_MODEL_IDS_ENV))
        return {
            "weights_sha256": "provider-managed",
            "license": self.capability.license,
            "runtime": "openrouter",
            "runtime_version": "api",
            "model_id": model_ids[0] if model_ids else "unconfigured",
        }

    def configuration_status(self) -> dict[str, Any]:
        return openrouter_provider_config_status()
