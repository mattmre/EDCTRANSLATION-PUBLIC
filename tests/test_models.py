from __future__ import annotations

import dataclasses
import json

import pytest

from edc_translation.models import (
    DocumentTranslation,
    EngineCapability,
    PageTranslation,
    SpanTranslation,
    TranslationRequest,
)


def _span(span_id: str = "s0", text: str = "hello") -> SpanTranslation:
    return SpanTranslation(
        span_id=span_id,
        source_text=text,
        target_text=text,
        source_bbox=[0.0, 0.0, 100.0, 12.0],
        source_bboxes=[[0.0, 0.0, 100.0, 12.0]],
        source_language="en",
        target_language="en",
        confidence=1.0,
        quality_score=None,
        engine_id="passthrough",
    )


def test_engine_capability_is_frozen():
    capability = EngineCapability(
        id="passthrough",
        is_local=True,
        is_cloud=False,
        supports_pairs="any",
        quality_class="draft",
        latency_class="realtime",
        license="Apache-2.0",
        provider_retention_class="local_only",
        deployment_envs=["local"],
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        capability.id = "other"  # type: ignore[misc]


def test_translation_request_defaults():
    request = TranslationRequest(src_lang="en", tgt_lang="fr")
    assert request.quality == "standard"
    assert request.latency == "standard"
    assert request.privilege_flag is False
    assert request.tenant_id == "default"


def test_document_translation_certified_default_false():
    document = DocumentTranslation(
        schema_version="1.0",
        document_id="doc-1",
        source_file="source.pdf",
        source_language="en",
        target_language="fr",
    )
    assert document.certified is False


def test_document_translation_asdict_json_safe():
    document = DocumentTranslation(
        schema_version="1.0",
        document_id="doc-1",
        source_file="source.pdf",
        source_language="en",
        target_language="en",
        pages=[PageTranslation(page_num=1, spans=[_span()])],
    )

    payload = dataclasses.asdict(document)
    parsed = json.loads(json.dumps(payload))

    assert parsed["document_id"] == "doc-1"
    assert parsed["certified"] is False
    assert parsed["pages"][0]["spans"][0]["span_id"] == "s0"
