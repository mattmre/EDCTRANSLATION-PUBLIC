"""OCR-style span adapter for standalone EDC_TRANSLATION engines."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from edc_translation.models import SpanTranslation

if TYPE_CHECKING:
    from edc_translation.engines.base import TranslationEngine


def translate_spans(
    engine: "TranslationEngine",
    spans: list[Mapping[str, Any]],
    src: str,
    tgt: str,
    glossary: Any | None = None,
    seed: int = 42,
    beam_size: int = 4,
) -> list[SpanTranslation]:
    """Translate OCR-shaped span dicts using an EDC text engine.

    The signature intentionally mirrors the current OCR engine contract so the
    first engine ports can be tested in ``EDC_TRANSLATION`` before OCR's in-repo
    engines are moved or renamed.
    """

    _ = glossary, seed, beam_size
    results: list[SpanTranslation] = []
    for index, span in enumerate(spans):
        text = str(span["text"])
        source_language = str(span.get("language", src))
        bbox = _normalize_bbox(span.get("bbox", [0.0, 0.0, 100.0, 12.0]))
        source_bboxes = _normalize_bboxes(
            span.get("bboxes", span.get("source_bboxes")),
            default=bbox,
        )
        translated = engine.translate_text(
            text,
            source_language=source_language,
            target_language=tgt,
        )
        results.append(
            SpanTranslation(
                span_id=str(span.get("span_id", f"s{index}")),
                source_text=text,
                target_text=translated.translated_text,
                source_bbox=bbox,
                source_bboxes=source_bboxes,
                source_language=source_language,
                target_language=tgt,
                confidence=translated.confidence,
                quality_score=translated.quality_score,
                engine_id=engine.capability.id,
                glossary_hits=list(span.get("glossary_hits", [])),
            )
        )
    return results


def _normalize_bbox(value: Any) -> list[float]:
    return [float(part) for part in value]


def _normalize_bboxes(value: Any, *, default: list[float]) -> list[list[float]]:
    if value is None:
        return [list(default)]
    return [_normalize_bbox(item) for item in value]
