from __future__ import annotations

from edc_translation.engines import get_engine
from edc_translation.models import SpanTranslation


def test_passthrough_span_adapter_matches_ocr_contract_shape():
    engine = get_engine("passthrough")()
    bbox = [0.0, 0.0, 10.0, 12.0]

    out = engine.translate_spans(
        [{"span_id": "alpha-1", "text": "hello", "bbox": bbox}],
        src="en",
        tgt="fr",
    )

    assert len(out) == 1
    span = out[0]
    assert isinstance(span, SpanTranslation)
    assert span.span_id == "alpha-1"
    assert span.source_text == "hello"
    assert span.target_text == "hello"
    assert span.source_bbox == bbox
    assert span.source_bboxes == [bbox]
    assert span.source_language == "en"
    assert span.target_language == "fr"
    assert span.confidence == 1.0
    assert span.quality_score is None
    assert span.engine_id == "passthrough"


def test_span_adapter_preserves_count_ids_and_default_bbox():
    engine = get_engine("passthrough")()
    spans = [
        {"span_id": "s0", "text": "alpha", "bbox": [0.0, 0.0, 1.0, 1.0]},
        {"span_id": "s1", "text": "beta"},
    ]

    out = engine.translate_spans(spans, src="en", tgt="en")

    assert [span.span_id for span in out] == ["s0", "s1"]
    assert [span.target_text for span in out] == ["alpha", "beta"]
    assert out[1].source_bbox == [0.0, 0.0, 100.0, 12.0]


def test_span_adapter_uses_text_engine_translation_and_quality():
    engine = get_engine("deterministic_ci")()

    out = engine.translate_spans(
        [{"span_id": "s0", "text": "hello", "bbox": [0, 0, 1, 1]}],
        src="en",
        tgt="fr",
    )

    assert out[0].target_text == "hello [en->fr]"
    assert out[0].quality_score == 1.0
    assert out[0].engine_id == "deterministic_ci"


def test_span_adapter_honors_per_span_language_when_present():
    engine = get_engine("deterministic_ci")()

    out = engine.translate_spans(
        [
            {
                "span_id": "s0",
                "text": "bonjour",
                "bbox": [0, 0, 1, 1],
                "language": "fr",
            }
        ],
        src="en",
        tgt="de",
    )

    assert out[0].source_language == "fr"
    assert out[0].target_text == "bonjour [fr->de]"
