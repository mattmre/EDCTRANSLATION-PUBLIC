"""Engine abstraction for standalone EDC_TRANSLATION providers."""

from __future__ import annotations

import importlib.metadata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from edc_translation.models import EngineCapability, SpanTranslation


@dataclass(frozen=True)
class EngineTranslation:
    """Result of translating one text span."""

    translated_text: str
    confidence: float = 1.0
    quality_score: float | None = None


class TranslationEngine(ABC):
    """Abstract base for all EDC_TRANSLATION engines."""

    capability: ClassVar[EngineCapability]
    provider_family: ClassVar[str] = "unknown"

    @abstractmethod
    def translate_text(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> EngineTranslation:
        """Translate one text span."""

    def translate_spans(
        self,
        spans: list[dict[str, Any]],
        src: str,
        tgt: str,
        glossary: Any | None = None,
        seed: int = 42,
        beam_size: int = 4,
    ) -> list[SpanTranslation]:
        """OCR-compatible span adapter over ``translate_text``."""

        from edc_translation.engines.span_adapter import translate_spans

        return translate_spans(
            self,
            spans,
            src,
            tgt,
            glossary=glossary,
            seed=seed,
            beam_size=beam_size,
        )

    def model_provenance(self) -> dict[str, str]:
        """Return minimal model provenance metadata."""

        return {
            "weights_sha256": "n/a",
            "license": self.capability.license,
            "runtime": "edc_translation",
            "runtime_version": self.runtime_info()["version"],
        }

    def runtime_info(self) -> dict[str, str]:
        """Return runtime identity for this engine."""

        try:
            version = importlib.metadata.version("edc-translation")
        except importlib.metadata.PackageNotFoundError:
            version = "0.1.0"
        return {"runtime": "edc_translation", "version": version}
