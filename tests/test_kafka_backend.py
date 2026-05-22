from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edc_translation.kafka_backend import (
    KAFKA_CONTRACT_VERSION,
    KafkaEnvelope,
    KafkaWorkQueue,
    TranslationDeadLetterMessage,
    TranslationResultMessage,
    TranslationSegmentMessage,
    fanout_segments_for_work_item,
    kafka_contract,
    make_kafka_work_queue,
    outbox_event_for_envelope,
    outbox_events_for_fanout,
    reassembly_plan,
    topic_for_event,
)
from edc_translation.jobs import TranslationWorkItem
from edc_translation.worker import TranslationWorkerResult

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edc_contracts"


def _document_bundle() -> dict[str, Any]:
    return json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )


def test_kafka_contract_is_deterministic():
    contract = kafka_contract()

    assert contract["contract_version"] == KAFKA_CONTRACT_VERSION
    assert contract["jobs"] == "translation-jobs"
    assert contract["segments"] == "translation-segments"
    assert contract["results"] == "translation-results"
    assert contract["dlq"] == "translation-dlq"
    assert tuple(contract["required_keys"]) == (
        "contract_version",
        "event_type",
        "job_id",
        "tenant_id",
    )


def test_segment_message_round_trips_through_envelope_and_outbox():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_kafka",
        work_id="work_kafka",
        target_language="fr",
        provider_id="deterministic_ci",
        tenant_id="tenant-a",
        metadata={"priority": "normal"},
    )
    segment = TranslationSegmentMessage.from_work_item(
        item,
        segment_id="segment-000001",
        model_id="opus-small",
        engine_family="ct2_nmt",
    )

    envelope = segment.to_envelope()
    restored = TranslationSegmentMessage.from_payload(envelope.payload)
    outbox = outbox_event_for_envelope(envelope)

    assert restored == segment
    assert envelope.to_message()["contract_version"] == KAFKA_CONTRACT_VERSION
    assert outbox["kafka_topic"] == "translation-segments"
    assert outbox["kafka_key"] == "segment-000001"
    assert outbox["payload"]["payload"]["model_id"] == "opus-small"


def test_result_message_and_reassembly_plan_are_stable():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_kafka",
        work_id="work_kafka",
        target_language="fr",
        provider_id="deterministic_ci",
        tenant_id="tenant-a",
    )
    result = TranslationWorkerResult.failed(item, {"code": "boom"})
    message = TranslationResultMessage.from_worker_result(
        result,
        segment_id="segment-000001",
    )

    assert topic_for_event(message.to_envelope().event_type) == "translation-results"
    assert reassembly_plan(
        job_id="trjob_kafka",
        expected_segment_ids=["segment-000001", "segment-000002"],
        results=[message],
    ) == {
        "job_id": "trjob_kafka",
        "expected_segments": ["segment-000001", "segment-000002"],
        "received_segments": ["segment-000001"],
        "missing_segments": ["segment-000002"],
        "failed_segments": ["segment-000001"],
        "ready": False,
    }


def test_dead_letter_message_targets_dlq_topic():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_kafka",
        work_id="work_kafka",
        target_language="fr",
        provider_id="deterministic_ci",
        tenant_id="tenant-a",
    )
    result = TranslationResultMessage.from_worker_result(
        TranslationWorkerResult.failed(item, {"code": "boom"}),
        segment_id="segment-000001",
    )

    dead_letter = TranslationDeadLetterMessage.from_result(result, attempts=3)
    envelope = dead_letter.to_envelope()
    restored = TranslationDeadLetterMessage.from_payload(envelope.payload)

    assert restored == dead_letter
    assert topic_for_event(envelope.event_type) == "translation-dlq"
    assert envelope.headers["source_topic"] == "translation-segments"
    assert envelope.key == "segment-000001"


def test_fanout_segments_for_work_item_are_deterministic_outbox_inputs():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_fanout",
        work_id="work_fanout",
        target_language="fr",
        provider_id="deterministic_ci",
        tenant_id="tenant-a",
    )

    segments = fanout_segments_for_work_item(
        item,
        max_spans_per_segment=1,
        model_id="opus-small",
        engine_family="ct2_nmt",
    )
    outbox_events = outbox_events_for_fanout(segments)

    assert [segment.segment_id for segment in segments] == [
        "segment-000001",
        "segment-000002",
    ]
    assert [segment.span_ids for segment in segments] == [["p1-s1"], ["p1-s2"]]
    assert [event["kafka_topic"] for event in outbox_events] == [
        "translation-segments",
        "translation-segments",
    ]
    assert [event["kafka_key"] for event in outbox_events] == [
        "segment-000001",
        "segment-000002",
    ]
    assert outbox_events[0]["payload"]["payload"]["model_id"] == "opus-small"


# =============================================================================
# KafkaWorkQueue tests (buffer fallback path + envelope roundtrips; real IO tested via docker redpanda when aiokafka present)
# =============================================================================


def test_kafka_work_queue_factory_and_buffer_submit_poll_roundtrip():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="kbuf_job",
        work_id="kbuf_work",
        target_language="es",
        provider_id="passthrough",
        tenant_id="tenant-k",
    )
    q: KafkaWorkQueue = make_kafka_work_queue()
    # submit (full sig, no repo)
    returned_job = q.submit(item)
    assert returned_job.status in ("queued", "created")
    assert returned_job.job_id == "kbuf_job"

    polled = q.poll()
    assert polled is not None
    assert polled.resolved_job_id == "kbuf_job"
    assert polled.target_language == "es"

    # second poll empty
    assert q.poll() is None


def test_kafka_work_queue_ack_nack_publish_to_result_topics_no_crash():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="kres_job",
        work_id="kres_work",
        target_language="it",
        provider_id="deterministic_ci",
        tenant_id="tenant-k",
    )
    q = make_kafka_work_queue(consume_topics=["translation-jobs"])
    q.submit(item)
    polled = q.poll()
    assert polled is not None

    # valid minimal result bundle (use the helper to satisfy schema in real path; here just ensure no crash in path)
    # For buffer path ack just queues envelope internally; we exercise the call
    ok_result = TranslationWorkerResult.failed(item, {"code": "test-fail-for-nack"})
    q.ack(polled, TranslationWorkerResult.succeeded(item, {
        "schema_version": "translation-bundle-v1",
        "document_id": item.document_id,
        "source_ocr_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "target_language": "it",
        "translated_spans": [],
        "engine_provider": {"id": "passthrough", "family": "passthrough", "is_local": True, "is_cloud": False, "license": "unknown", "provider_retention_class": "none"},
        "model_provenance": {"weights_sha256": "c" * 64, "runtime": "stub", "runtime_version": "1"},
        "quality_scores": {"mean_score": 0.9, "below_threshold_count": 0, "quality_class": "high"},
        "certified": False,
        "custody_chain_head": "head-1",
        "artifact_manifest": {"artifacts": []},
    }))
    q.nack(polled, ok_result)  # exercises dlq path too
    # no exception == success for buffer path


def test_kafka_work_queue_from_envelope_supports_segment_payloads():
    # direct static test for fanout path
    seg_env = KafkaEnvelope(
        event_type="translation.segment.requested",
        job_id="segjob",
        tenant_id="tseg",
        key="segment-000001",
        payload={
            "job_id": "segjob",
            "work_id": "wseg",
            "segment_id": "segment-000001",
            "document_id": "dseg",
            "source_language": "en",
            "target_language": "fr",
            "provider_id": "ct2",
            "tenant_id": "tseg",
            "text": "hello world segment",
            "span_ids": ["p1-s1"],
            "model_id": "test-model",
        },
    )
    item = KafkaWorkQueue.from_envelope(seg_env)
    assert item.document_id == "dseg"
    assert item.target_language == "fr"
    assert "hello world segment" in str(item.document_bundle.get("spans", [{}])[0].get("text", ""))
