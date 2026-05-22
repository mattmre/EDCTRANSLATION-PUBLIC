"""Compatibility provider registry.

The Phase 3 engine abstraction lives in ``edc_translation.engines``.  This
module remains as a thin compatibility layer for Phase 2 callers that used
provider terminology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from edc_translation.engines import get_engine, iter_engines
from edc_translation.engines.metadata import engine_list_entry


@dataclass(frozen=True)
class ProviderMetadata:
    id: str
    family: str
    is_local: bool
    is_cloud: bool
    license: str
    provider_retention_class: str
    quality_class: str
    weights_sha256: str = "n/a"
    runtime: str = "edc_translation"
    runtime_version: str = "0.1.0"


@dataclass(frozen=True)
class TranslationResult:
    translated_text: str
    confidence: float = 1.0
    quality_score: float | None = None


class TranslationProvider(Protocol):
    metadata: ProviderMetadata

    def translate(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        ...


class _EngineProviderAdapter:
    def __init__(self, engine_id: str) -> None:
        self._engine = get_engine(engine_id)()
        entry = engine_list_entry(self._engine)
        self.metadata = ProviderMetadata(
            id=entry["id"],
            family=entry["family"],
            is_local=entry["is_local"],
            is_cloud=entry["is_cloud"],
            license=entry["license"],
            provider_retention_class=entry["provider_retention_class"],
            quality_class=entry["quality_class"],
            weights_sha256=entry["weights_sha256"],
            runtime=entry["runtime"],
            runtime_version=entry["runtime_version"],
        )

    def translate(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        result = self._engine.translate_text(
            text,
            source_language=source_language,
            target_language=target_language,
        )
        return TranslationResult(
            translated_text=result.translated_text,
            confidence=result.confidence,
            quality_score=result.quality_score,
        )


def list_providers() -> list[ProviderMetadata]:
    return [
        _EngineProviderAdapter(engine_id).metadata
        for engine_id, _engine_cls in iter_engines()
    ]


def get_provider(provider_id: str) -> TranslationProvider:
    try:
        return _EngineProviderAdapter(provider_id)
    except KeyError as exc:
        raise ValueError(
            f"Unknown translation provider: {provider_id!r}. "
            f"Valid: {sorted(engine_id for engine_id, _cls in iter_engines())}"
        ) from exc
