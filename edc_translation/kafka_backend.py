"""Kafka contract helpers for production translation fanout.

This module intentionally has no Kafka client dependency. It defines stable
message shapes, topic names, and deterministic helpers that an aiokafka or
confluent-kafka adapter can use behind the existing worker/result boundaries.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

from edc_translation.jobs import TranslationJob, TranslationWorkItem, WorkQueue as SubmitWorkQueue, utc_now_iso
# NOTE: Do NOT import from worker at module level (would create circular import via service -> kafka -> worker -> service when
# _queue_backend=kafka causes early import of kafka_backend during service module initialization).
# The poll/ack/nack methods satisfy the worker.WorkQueue protocol structurally (duck-typing + postponed annotations).
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edc_translation.worker import TranslationWorkerResult


try:
    # Optional at runtime for actual Kafka connectivity.
    # The rest of the module stays importable without aiokafka installed.
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer  # type: ignore
except ImportError:  # pragma: no cover
    AIOKafkaProducer = None  # type: ignore
    AIOKafkaConsumer = None  # type: ignore

from collections import deque
import asyncio
import queue as thread_queue
import threading

KAFKA_CONTRACT_VERSION = "translation-kafka-v1"
TRANSLATION_JOBS_TOPIC = "translation-jobs"
TRANSLATION_SEGMENTS_TOPIC = "translation-segments"
TRANSLATION_RESULTS_TOPIC = "translation-results"
TRANSLATION_EVENTS_TOPIC = "translation-events"
TRANSLATION_DLQ_TOPIC = "translation-dlq"


@dataclass(frozen=True)
class KafkaTopicContract:
    """Deterministic topic contract for deployment scaffolding and tests."""

    jobs: str = TRANSLATION_JOBS_TOPIC
    segments: str = TRANSLATION_SEGMENTS_TOPIC
    results: str = TRANSLATION_RESULTS_TOPIC
    events: str = TRANSLATION_EVENTS_TOPIC
    dlq: str = TRANSLATION_DLQ_TOPIC
    required_keys: tuple[str, ...] = (
        "contract_version",
        "event_type",
        "job_id",
        "tenant_id",
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = KAFKA_CONTRACT_VERSION
        return payload


@dataclass(frozen=True)
class KafkaEnvelope:
    """Provider-neutral Kafka message envelope."""

    contract_version: ClassVar[str] = KAFKA_CONTRACT_VERSION

    event_type: str
    job_id: str
    tenant_id: str
    key: str
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def to_message(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "event_type": self.event_type,
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "key": self.key,
            "headers": dict(sorted(self.headers.items())),
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_message(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "KafkaEnvelope":
        if message.get("contract_version") != KAFKA_CONTRACT_VERSION:
            raise ValueError("unsupported Kafka contract version")
        return cls(
            event_type=str(message["event_type"]),
            job_id=str(message["job_id"]),
            tenant_id=str(message["tenant_id"]),
            key=str(message["key"]),
            headers={str(k): str(v) for k, v in dict(message.get("headers", {})).items()},
            payload=dict(message["payload"]),
        )


@dataclass(frozen=True)
class TranslationSegmentMessage:
    """Kafka segment work item for multi-GPU fanout."""

    job_id: str
    work_id: str
    segment_id: str
    document_id: str
    source_language: str
    target_language: str
    provider_id: str
    tenant_id: str
    text: str
    span_ids: list[str]
    model_id: str | None = None
    engine_family: str | None = None
    attempt: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_work_item(
        cls,
        item: TranslationWorkItem,
        *,
        segment_id: str = "segment-000001",
        text: str | None = None,
        span_ids: list[str] | None = None,
        model_id: str | None = None,
        engine_family: str | None = None,
    ) -> "TranslationSegmentMessage":
        spans = item.document_bundle.get("spans", [])
        selected_span_ids = (
            list(span_ids)
            if span_ids is not None
            else [str(span["span_id"]) for span in spans]
        )
        selected_text = text
        if selected_text is None:
            selected_text = "\n".join(str(span.get("text", "")) for span in spans)
        return cls(
            job_id=item.resolved_job_id,
            work_id=item.resolved_work_id,
            segment_id=segment_id,
            document_id=item.document_id,
            source_language=item.resolved_source_language,
            target_language=item.target_language,
            provider_id=item.provider_id,
            tenant_id=item.tenant_id,
            text=selected_text,
            span_ids=selected_span_ids,
            model_id=model_id,
            engine_family=engine_family,
            metadata=dict(item.metadata),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_envelope(self) -> KafkaEnvelope:
        return KafkaEnvelope(
            event_type="translation.segment.requested",
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            key=self.segment_id,
            headers={
                "document_id": self.document_id,
                "provider_id": self.provider_id,
            },
            payload=self.to_payload(),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TranslationSegmentMessage":
        return cls(
            job_id=str(payload["job_id"]),
            work_id=str(payload["work_id"]),
            segment_id=str(payload["segment_id"]),
            document_id=str(payload["document_id"]),
            source_language=str(payload["source_language"]),
            target_language=str(payload["target_language"]),
            provider_id=str(payload["provider_id"]),
            tenant_id=str(payload["tenant_id"]),
            text=str(payload["text"]),
            span_ids=[str(value) for value in payload.get("span_ids", [])],
            model_id=_optional_str(payload.get("model_id")),
            engine_family=_optional_str(payload.get("engine_family")),
            attempt=int(payload.get("attempt", 0)),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class TranslationResultMessage:
    """Kafka result message emitted by workers."""

    job_id: str
    work_id: str
    document_id: str
    status: str
    target_language: str
    provider_id: str
    tenant_id: str
    segment_id: str | None = None
    translation_bundle: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_worker_result(
        cls,
        result: TranslationWorkerResult,
        *,
        segment_id: str | None = None,
    ) -> "TranslationResultMessage":
        return cls(
            job_id=result.job_id,
            work_id=result.work_id,
            document_id=result.document_id,
            status=result.status,
            target_language=result.target_language,
            provider_id=result.provider_id,
            tenant_id=result.tenant_id,
            segment_id=segment_id,
            translation_bundle=result.translation_bundle,
            error=result.error,
            metadata=dict(result.metadata),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_envelope(self) -> KafkaEnvelope:
        return KafkaEnvelope(
            event_type=f"translation.result.{self.status}",
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            key=self.segment_id or self.work_id,
            headers={
                "document_id": self.document_id,
                "provider_id": self.provider_id,
            },
            payload=self.to_payload(),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TranslationResultMessage":
        return cls(
            job_id=str(payload["job_id"]),
            work_id=str(payload["work_id"]),
            document_id=str(payload["document_id"]),
            status=str(payload["status"]),
            target_language=str(payload["target_language"]),
            provider_id=str(payload["provider_id"]),
            tenant_id=str(payload["tenant_id"]),
            segment_id=_optional_str(payload.get("segment_id")),
            translation_bundle=(
                dict(payload["translation_bundle"])
                if isinstance(payload.get("translation_bundle"), dict)
                else None
            ),
            error=dict(payload["error"]) if isinstance(payload.get("error"), dict) else None,
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class TranslationDeadLetterMessage:
    """Kafka dead-letter message for terminal segment or job failures."""

    job_id: str
    work_id: str
    tenant_id: str
    source_topic: str
    source_key: str
    error: dict[str, Any]
    payload: dict[str, Any]
    attempts: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(
        cls,
        result: TranslationResultMessage,
        *,
        source_topic: str = TRANSLATION_SEGMENTS_TOPIC,
        attempts: int = 1,
    ) -> "TranslationDeadLetterMessage":
        return cls(
            job_id=result.job_id,
            work_id=result.work_id,
            tenant_id=result.tenant_id,
            source_topic=source_topic,
            source_key=result.segment_id or result.work_id,
            error=dict(result.error or {}),
            payload=result.to_payload(),
            attempts=attempts,
            metadata=dict(result.metadata),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_envelope(self) -> KafkaEnvelope:
        return KafkaEnvelope(
            event_type="translation.dead_letter.recorded",
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            key=self.source_key,
            headers={
                "source_topic": self.source_topic,
                "work_id": self.work_id,
            },
            payload=self.to_payload(),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TranslationDeadLetterMessage":
        return cls(
            job_id=str(payload["job_id"]),
            work_id=str(payload["work_id"]),
            tenant_id=str(payload["tenant_id"]),
            source_topic=str(payload["source_topic"]),
            source_key=str(payload["source_key"]),
            error=dict(payload["error"]),
            payload=dict(payload["payload"]),
            attempts=int(payload["attempts"]),
            metadata=dict(payload.get("metadata", {})),
        )


def kafka_contract() -> dict[str, Any]:
    """Return a deterministic summary of the Kafka runtime contract."""

    return KafkaTopicContract().to_dict()


def outbox_event_for_envelope(envelope: KafkaEnvelope) -> dict[str, Any]:
    """Build a Postgres outbox payload from a Kafka envelope."""

    message = envelope.to_message()
    return {
        "aggregate_type": "translation_job",
        "aggregate_id": envelope.job_id,
        "event_type": envelope.event_type,
        "payload": message,
        "kafka_topic": topic_for_event(envelope.event_type),
        "kafka_key": envelope.key,
    }


def fanout_segments_for_work_item(
    item: TranslationWorkItem,
    *,
    max_spans_per_segment: int = 1,
    model_id: str | None = None,
    engine_family: str | None = None,
) -> list[TranslationSegmentMessage]:
    """Split a work item into deterministic Kafka segment requests."""

    if max_spans_per_segment < 1:
        raise ValueError("max_spans_per_segment must be at least 1")
    item.validate()
    spans = list(item.document_bundle.get("spans", []))
    if not spans:
        return [
            TranslationSegmentMessage.from_work_item(
                item,
                model_id=model_id,
                engine_family=engine_family,
            )
        ]

    segments: list[TranslationSegmentMessage] = []
    for start in range(0, len(spans), max_spans_per_segment):
        chunk = spans[start : start + max_spans_per_segment]
        segment_number = len(segments) + 1
        span_ids = [str(span["span_id"]) for span in chunk]
        text = "\n".join(str(span.get("text", "")) for span in chunk)
        segments.append(
            TranslationSegmentMessage.from_work_item(
                item,
                segment_id=f"segment-{segment_number:06d}",
                text=text,
                span_ids=span_ids,
                model_id=model_id,
                engine_family=engine_family,
            )
        )
    return segments


def outbox_events_for_fanout(
    segments: list[TranslationSegmentMessage],
) -> list[dict[str, Any]]:
    """Build ordered Postgres outbox rows for Kafka segment fanout."""

    return [
        outbox_event_for_envelope(segment.to_envelope())
        for segment in segments
    ]


def topic_for_event(event_type: str) -> str:
    if event_type == "translation.segment.requested":
        return TRANSLATION_SEGMENTS_TOPIC
    if event_type.startswith("translation.result."):
        return TRANSLATION_RESULTS_TOPIC
    if event_type.startswith("translation.job."):
        return TRANSLATION_JOBS_TOPIC
    if event_type.startswith("translation.dead_letter."):
        return TRANSLATION_DLQ_TOPIC
    return TRANSLATION_EVENTS_TOPIC


def reassembly_plan(
    *,
    job_id: str,
    expected_segment_ids: list[str],
    results: list[TranslationResultMessage],
) -> dict[str, Any]:
    """Return deterministic segment reassembly readiness metadata."""

    by_segment = {
        result.segment_id: result
        for result in results
        if result.segment_id is not None and result.job_id == job_id
    }
    missing = [
        segment_id
        for segment_id in expected_segment_ids
        if segment_id not in by_segment
    ]
    failed = sorted(
        segment_id
        for segment_id, result in by_segment.items()
        if result.status != "succeeded"
    )
    return {
        "job_id": job_id,
        "expected_segments": list(expected_segment_ids),
        "received_segments": sorted(by_segment),
        "missing_segments": missing,
        "failed_segments": failed,
        "ready": not missing and not failed,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

# =============================================================================
# Kafka WorkQueue Adapter (started 2026-05-18)
# =============================================================================
#
# Implements the WorkQueue protocol for Kafka-backed job fanout.
# Uses the contracts and envelopes defined above.
# Real Kafka client (aiokafka / confluent-kafka) is intentionally not required
# at import time so the module stays importable in minimal environments.
#
# This is the beginning of the Kafka tranche after Postgres durability was completed.


class KafkaWorkQueue(SubmitWorkQueue):  # also satisfies worker.WorkQueue (poll/ack/nack) via duck typing
    """
    Kafka-backed WorkQueue adapter (production-style for fanout).

    - submit()  → produces TranslationWorkItem (as envelope) to TRANSLATION_JOBS_TOPIC (or segments)
    - poll()    → consumes from configured topics (jobs or segments for fanout) via bg thread
    - ack/nack  → produces results to TRANSLATION_RESULTS_TOPIC (+ DLQ envelope on nack)

    Uses aiokafka in a dedicated background thread+loop so the sync WorkQueue protocol
    (used by service submit and worker poll loops) stays unchanged. When aiokafka or
    broker is unavailable, falls back to in-memory buffer for local dev/tests.

    Supports segment and result topics via ctor params and helpers.
    Can be used alongside Postgres (job/repo state in PG, work distribution/fanout via Kafka/Redpanda/Strimzi).
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "edc-translation-workers",
        client_id: str = "edc-translation-kafka-queue",
        consume_topics: list[str] | None = None,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.client_id = client_id
        self.consume_topics = consume_topics or [TRANSLATION_JOBS_TOPIC]
        self._local_buffer: deque[TranslationWorkItem] = deque()
        self._connected = False

        # Background IO thread bridges sync protocol <-> async aiokafka producer/consumer
        self._io_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._submit_q: thread_queue.Queue = thread_queue.Queue()
        self._poll_q: thread_queue.Queue = thread_queue.Queue()
        self._result_q: thread_queue.Queue = thread_queue.Queue()
        self._producer: Any = None
        self._consumer: Any = None

    def _ensure_io_thread(self) -> None:
        if AIOKafkaProducer is None:
            return
        if self._io_thread and self._io_thread.is_alive():
            return
        self._stop_event.clear()
        self._io_thread = threading.Thread(
            target=self._kafka_io_loop, daemon=True, name="kafka-io-thread"
        )
        self._io_thread.start()

    def _kafka_io_loop(self) -> None:
        """Dedicated event loop in bg thread: handles all producer sends and consumer polls."""
        async def _run_io() -> None:
            if AIOKafkaProducer is None:
                return
            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers, client_id=self.client_id
            )
            consumer = AIOKafkaConsumer(
                *self.consume_topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                client_id=self.client_id + "-consumer",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            try:
                await producer.start()
                await consumer.start()
                self._producer = producer
                self._consumer = consumer
                self._connected = True
                while not self._stop_event.is_set():
                    # Drain pending work-item submits (from .submit)
                    for _ in range(20):
                        try:
                            envelope: KafkaEnvelope = self._submit_q.get_nowait()
                            val = envelope.to_json().encode("utf-8")
                            topic = topic_for_event(envelope.event_type) or TRANSLATION_JOBS_TOPIC
                            await producer.send_and_wait(
                                topic,
                                value=val,
                                key=(envelope.key or "default").encode("utf-8"),
                            )
                        except thread_queue.Empty:
                            break
                    # Poll configured topics (jobs or segments) and enqueue work items
                    try:
                        batch = await consumer.getmany(timeout_ms=120, max_records=5)
                        for _tp, messages in batch.items():
                            for m in messages:
                                try:
                                    data = json.loads(m.value.decode("utf-8"))
                                    env = KafkaEnvelope.from_message(data)
                                    item = self.from_envelope(env)
                                    self._poll_q.put(item)
                                except Exception:
                                    # Skip malformed; real impl would dead-letter
                                    continue
                    except Exception:
                        pass
                    # Drain result / DLQ publishes from ack/nack
                    for _ in range(20):
                        try:
                            envelope: KafkaEnvelope = self._result_q.get_nowait()
                            val = envelope.to_json().encode("utf-8")
                            topic = topic_for_event(envelope.event_type) or TRANSLATION_RESULTS_TOPIC
                            await producer.send_and_wait(
                                topic,
                                value=val,
                                key=(envelope.key or "result").encode("utf-8"),
                            )
                        except thread_queue.Empty:
                            break
                    await asyncio.sleep(0.05)
            except Exception:
                # Broker unreachable or client error → thread exits; callers fall back to buffer
                self._connected = False
            finally:
                try:
                    if self._producer:
                        await self._producer.stop()
                    if self._consumer:
                        await self._consumer.stop()
                except Exception:
                    pass
                self._connected = False

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_run_io())
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # Submit side (jobs.py WorkQueue protocol) - now full signature for compatibility
    # ------------------------------------------------------------------
    def submit(
        self,
        work_item: TranslationWorkItem,
        *,
        repository: Any = None,
        executor: Any = None,
        error_mapper: Any = None,
    ) -> TranslationJob:
        """Publish work item envelope to Kafka jobs topic (decoupled execution).

        Alongside Postgres: if repository passed, also create the job record (source of truth).
        The executor is never invoked here (that's for the worker consuming the topic).
        """
        del executor, error_mapper
        env = self.work_item_to_envelope(work_item)
        if AIOKafkaProducer is None:
            self._local_buffer.append(work_item)
        else:
            self._ensure_io_thread()
            if self._connected:
                self._submit_q.put(env)
            else:
                # Broker startup/availability is asynchronous. Keep local and test
                # flows non-dropping when no Kafka broker can be reached.
                self._local_buffer.append(work_item)

        if repository is not None:
            try:
                return repository.create(
                    document_id=work_item.document_id,
                    target_language=work_item.target_language,
                    provider_id=work_item.provider_id,
                    metadata=dict(work_item.metadata),
                )
            except Exception:
                pass  # job may pre-exist or transient; still published to queue

        # Fallback constructed job (status indicates queued async path)
        now = utc_now_iso()
        return TranslationJob(
            job_id=work_item.resolved_job_id or env.job_id,
            status="queued",
            document_id=work_item.document_id,
            target_language=work_item.target_language,
            provider_id=work_item.provider_id,
            created_at=now,
            updated_at=now,
            metadata=dict(work_item.metadata),
        )

    # ------------------------------------------------------------------
    # Poll side (worker.py WorkQueue protocol)
    # ------------------------------------------------------------------
    def poll(self) -> TranslationWorkItem | None:
        """Non-blocking poll: local buffer first, then any items enqueued by bg consumer."""
        if self._local_buffer:
            return self._local_buffer.popleft()
        if AIOKafkaProducer is None:
            return None
        self._ensure_io_thread()
        try:
            return self._poll_q.get_nowait()
        except thread_queue.Empty:
            return None

    def ack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        """Publish success result envelope to results topic (via bg producer)."""
        if AIOKafkaProducer is None:
            return
        try:
            rmsg = TranslationResultMessage.from_worker_result(result)
            env = rmsg.to_envelope()
            self._ensure_io_thread()
            self._result_q.put(env)
        except Exception:
            pass

    def nack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        """Publish failure result + DLQ envelope."""
        if AIOKafkaProducer is None:
            return
        try:
            rmsg = TranslationResultMessage.from_worker_result(result)
            env = rmsg.to_envelope()
            self._ensure_io_thread()
            self._result_q.put(env)
            dlq = TranslationDeadLetterMessage.from_result(
                rmsg,
                source_topic=(self.consume_topics[0] if self.consume_topics else TRANSLATION_SEGMENTS_TOPIC),
            )
            self._result_q.put(dlq.to_envelope())
        except Exception:
            pass

    @staticmethod
    def from_envelope(envelope: KafkaEnvelope) -> TranslationWorkItem:
        """Reconstruct TranslationWorkItem from envelope (handles both job and segment payloads for fanout)."""
        p = envelope.payload or {}
        # Segment path (for TRANSLATION_SEGMENTS_TOPIC consumers / fanout)
        if "segment_id" in p or ("text" in p and "span_ids" in p):
            doc_id = str(p.get("document_id", "segment-doc"))
            text = str(p.get("text", ""))
            span_ids = [str(s) for s in p.get("span_ids", ["seg-1"])]
            spans = [{"span_id": sid, "text": text} for sid in span_ids] if text else []
            if not spans:
                spans = [{"span_id": "seg-1", "text": text or ""}]
            bundle = {
                "document_id": doc_id,
                "source_ocr_sha256": "kafka-segment:" + str(p.get("segment_id", "")),
                "spans": spans,
            }
            return TranslationWorkItem(
                document_bundle=bundle,
                target_language=str(p.get("target_language", "en")),
                provider_id=str(p.get("provider_id", "passthrough")),
                tenant_id=str(p.get("tenant_id", "standalone")),
                source_language=p.get("source_language"),
                job_id=envelope.job_id,
            )
        # Standard job submit payload
        return TranslationWorkItem(
            document_bundle=p.get("document_bundle", {}),
            target_language=p.get("target_language", "en"),
            provider_id=p.get("provider_id", "passthrough"),
            tenant_id=p.get("tenant_id", "standalone"),
            source_language=p.get("source_language"),
            allow_nc_licensed=bool(p.get("allow_nc_licensed", False)),
            certified=bool(p.get("certified", False)),
            job_id=envelope.job_id,
        )

    @staticmethod
    def work_item_to_envelope(item: TranslationWorkItem) -> KafkaEnvelope:
        """Helper: convert TranslationWorkItem to KafkaEnvelope for submission (jobs topic)."""
        return KafkaEnvelope(
            event_type="translation.job.submitted",
            job_id=item.job_id or "unknown",
            tenant_id=item.tenant_id,
            key=item.job_id or str(id(item)),
            payload={
                "document_bundle": item.document_bundle,
                "target_language": item.target_language,
                "provider_id": item.provider_id,
                "tenant_id": item.tenant_id,
                "source_language": item.source_language,
                "allow_nc_licensed": item.allow_nc_licensed,
                "certified": item.certified,
            },
        )

    async def start(self) -> None:
        """Kick off the background producer/consumer thread (safe to call multiple times)."""
        self._ensure_io_thread()

    async def stop(self) -> None:
        """Signal the IO thread to shut down cleanly."""
        self._stop_event.set()
        if self._io_thread:
            self._io_thread.join(timeout=3.0)
        self._connected = False


# Factory (consistent with postgres_backend pattern; supports segment/result topics)
def make_kafka_work_queue(
    *,
    bootstrap_servers: str = "localhost:9092",
    group_id: str = "edc-translation-workers",
    consume_topics: list[str] | None = None,
) -> "KafkaWorkQueue":
    """Factory for KafkaWorkQueue.

    consume_topics can be [TRANSLATION_SEGMENTS_TOPIC] for fanout workers, or jobs for standard.
    Results always published to results topic on ack/nack.
    """
    return KafkaWorkQueue(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        consume_topics=consume_topics,
    )

# ------------------------------------------------------------------
# Intended integration point (for service.py / worker.py when ready)
# ------------------------------------------------------------------
# from edc_translation.stores import make_work_queue
#
# if backend == "kafka":
#     queue = make_kafka_work_queue(
#         bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
#     )
#
# This keeps the same factory pattern already used for Postgres.

# Small incremental helper for result side (Kafka track, 1-min cadence)
def build_result_envelope(
    *,
    job_id: str,
    work_id: str,
    status: str,
    tenant_id: str,
    payload: dict[str, Any],
) -> KafkaEnvelope:
    """Helper to build a result message envelope for the results topic."""
    return KafkaEnvelope(
        event_type="translation.result",
        job_id=job_id,
        tenant_id=tenant_id,
        key=work_id,
        payload={"status": status, **payload},
    )

# Helper for segment fanout messages.
def build_segment_envelope(
    *,
    job_id: str,
    segment_id: str,
    tenant_id: str,
    payload: dict[str, Any],
) -> KafkaEnvelope:
    """Build a segment work message for the translation-segments topic."""
    return KafkaEnvelope(
        event_type="translation.segment",
        job_id=job_id,
        tenant_id=tenant_id,
        key=segment_id,
        payload=payload,
    )
