"""Local OpenAI-compatible chat translation adapter."""

from __future__ import annotations

import os
from typing import Any

from edc_translation.engines import register_engine
from edc_translation.engines.base import EngineTranslation, TranslationEngine
from edc_translation.llm_live import (
    DEFAULT_MAX_TOKENS,
    LOCAL_BASE_URL_ENV,
    LOCAL_LLM_API_KEY_ENV,
    LOCAL_MODEL_IDS_ENV,
    local_provider_config_status,
    split_model_ids,
    translate_with_openai_compatible_chat,
)
from edc_translation.models import EngineCapability


@register_engine
class LocalOpenAICompatEngine(TranslationEngine):
    provider_family = "llm_local"
    capability = EngineCapability(
        id="local_openai_compat",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="standard",
        latency_class="standard",
        license="operator-configured",
        provider_retention_class="local_only",
        deployment_envs=["local", "single-server"],
        cost_per_1m_tokens_usd=0.0,
    )

    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        base_url = os.environ.get(LOCAL_BASE_URL_ENV, "").strip()
        model_ids = split_model_ids(os.environ.get(LOCAL_MODEL_IDS_ENV))
        api_key = os.environ.get(LOCAL_LLM_API_KEY_ENV, "").strip() or None
        if not base_url:
            raise RuntimeError(f"{LOCAL_BASE_URL_ENV} is unset")
        if not model_ids:
            raise RuntimeError(f"{LOCAL_MODEL_IDS_ENV} is unset")
        translated = translate_with_openai_compatible_chat(
            base_url=base_url,
            model_id=model_ids[0],
            text=text,
            source_language=source_language,
            target_language=target_language,
            api_key=api_key,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        return EngineTranslation(translated_text=translated, confidence=0.8)

    def model_provenance(self) -> dict[str, str]:
        model_ids = split_model_ids(os.environ.get(LOCAL_MODEL_IDS_ENV))
        return {
            "weights_sha256": "operator-managed",
            "license": self.capability.license,
            "runtime": "openai_compatible_local",
            "runtime_version": "operator-managed",
            "model_id": model_ids[0] if model_ids else "unconfigured",
        }

    def configuration_status(self) -> dict[str, Any]:
        return local_provider_config_status()
