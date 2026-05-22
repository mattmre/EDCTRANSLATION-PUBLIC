"""Optional CTranslate2-backed NLLB-200 engine adapter."""

from __future__ import annotations

from edc_translation.engines import register_engine
from edc_translation.engines.ct2_sentencepiece import CT2SentencePieceEngine
from edc_translation.models import EngineCapability

MODEL_DIR_ENV = "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR"


@register_engine
class LocalCT2NLLBEngine(CT2SentencePieceEngine):
    """NLLB-200 adapter scaffold backed by optional CTranslate2 runtime."""

    capability = EngineCapability(
        id="local_ct2_nllb",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="standard",
        latency_class="standard",
        license="CC-BY-NC-4.0",
        provider_retention_class="local_only",
        deployment_envs=["local", "air_gapped", "kubernetes"],
        cost_per_1m_chars_usd=0.0,
        cost_per_1m_tokens_usd=0.0,
        handles_handwriting_natively=False,
    )
    provider_family = "ct2_nmt"
    model_dir_env = MODEL_DIR_ENV
