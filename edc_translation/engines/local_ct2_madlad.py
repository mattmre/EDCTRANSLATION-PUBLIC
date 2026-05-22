"""Optional CTranslate2-backed MADLAD-400 engine adapter."""

from __future__ import annotations

from edc_translation.engines import register_engine
from edc_translation.engines.ct2_sentencepiece import CT2SentencePieceEngine
from edc_translation.models import EngineCapability

MODEL_DIR_ENV = "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR"


@register_engine
class LocalCT2MADLADEngine(CT2SentencePieceEngine):
    """MADLAD-400 adapter scaffold backed by optional CTranslate2 runtime."""

    capability = EngineCapability(
        id="local_ct2_madlad",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="standard",
        latency_class="standard",
        license="Apache-2.0",
        provider_retention_class="local_only",
        deployment_envs=["local", "air_gapped", "kubernetes"],
        cost_per_1m_chars_usd=0.0,
        cost_per_1m_tokens_usd=0.0,
        handles_handwriting_natively=False,
    )
    provider_family = "ct2_nmt"
    model_dir_env = MODEL_DIR_ENV
