"""Worker runtime for queued DocumentBundle translation execution."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import sleep
from typing import Any, Callable, Protocol

from edc_translation.contracts import (
    TRANSLATION_BUNDLE_SCHEMA,
    validate_payload,
)
from edc_translation.errors import auto_route_error_payload
from edc_translation.jobs import TranslationWorkItem
from edc_translation.routing import RoutingError
from edc_translation.service import make_model_registry_store, translate_document_bundle
from edc_translation.stores import ModelRegistryStore


@dataclass(frozen=True)
class WorkerRuntimeSettings:
    """CLI/runtime settings shared by local and durable workers."""

    queue_backend: str = "local"
    worker_id: str = "local-worker"
    health_port: int | None = None
    model_profile: str = "local-cpu"
    max_items: int | None = None

    def to_health_payload(self) -> dict[str, Any]:
        return {
            "queue_backend": self.queue_backend,
            "worker_id": self.worker_id,
            "health_port": self.health_port,
            "model_profile": self.model_profile,
            "max_items": self.max_items,
            "status": "configured",
        }


@dataclass(frozen=True)
class TranslationWorkerResult:
    """Queue-safe result shape emitted by a translation worker."""

    job_id: str
    work_id: str
    document_id: str
    status: str
    target_language: str
    provider_id: str
    tenant_id: str
    translation_bundle: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def succeeded(
        cls,
        item: TranslationWorkItem,
        translation_bundle: dict[str, Any],
    ) -> "TranslationWorkerResult":
        validate_payload(translation_bundle, TRANSLATION_BUNDLE_SCHEMA)
        return cls(
            job_id=item.resolved_job_id,
            work_id=item.resolved_work_id,
            document_id=item.document_id,
            status="succeeded",
            target_language=item.target_language,
            provider_id=item.provider_id,
            tenant_id=item.tenant_id,
            translation_bundle=translation_bundle,
            metadata={"output_contract": TRANSLATION_BUNDLE_SCHEMA},
        )

    @classmethod
    def failed(
        cls,
        item: TranslationWorkItem,
        error: dict[str, Any],
    ) -> "TranslationWorkerResult":
        return cls(
            job_id=item.resolved_job_id,
            work_id=item.resolved_work_id,
            document_id=item.document_id,
            status="failed",
            target_language=item.target_language,
            provider_id=item.provider_id,
            tenant_id=item.tenant_id,
            error=error,
        )

    def to_message(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "work_id": self.work_id,
            "document_id": self.document_id,
            "status": self.status,
            "target_language": self.target_language,
            "provider_id": self.provider_id,
            "tenant_id": self.tenant_id,
            "metadata": self.metadata,
        }
        if self.translation_bundle is not None:
            payload["translation_bundle"] = self.translation_bundle
        if self.error is not None:
            payload["error"] = self.error
        return payload


class WorkQueue(Protocol):
    """Queue adapter boundary for local, Postgres, or Kafka consumers."""

    def poll(self) -> TranslationWorkItem | None:
        """Return the next available work item, or None if the queue is empty."""

    def ack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        """Mark a work item as completed by this worker."""

    def nack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        """Mark a work item as failed by this worker."""


class StopFlag(Protocol):
    """Minimal stop signal boundary shared by threading.Event-like flags."""

    def is_set(self) -> bool:
        """Return True when the worker should stop polling."""


class LocalWorkQueue:
    """Dependency-free FIFO queue for tests and local worker smoke runs."""

    def __init__(self, items: list[TranslationWorkItem] | None = None) -> None:
        self._items: deque[TranslationWorkItem] = deque(items or [])
        self.acked: list[TranslationWorkerResult] = []
        self.nacked: list[TranslationWorkerResult] = []

    def push(self, item: TranslationWorkItem) -> None:
        item.validate()
        self._items.append(item)

    def poll(self) -> TranslationWorkItem | None:
        if not self._items:
            return None
        return self._items.popleft()

    def ack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        del item
        self.acked.append(result)

    def nack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        del item
        self.nacked.append(result)


class _SignalStopFlag:
    """StopFlag driven by SIGTERM/SIGINT for production daemon graceful shutdown.

    On signal the flag is set; run_forever will finish the current in-flight
    item (drain) then exit the poll loop without claiming more work.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._installed = False
        try:
            # In test processes or restricted envs this may be a no-op; callers
            # can still call .stop() explicitly for simulation.
            signal.signal(signal.SIGTERM, self._on_signal)
            signal.signal(signal.SIGINT, self._on_signal)
            self._installed = True
        except (ValueError, OSError):
            # e.g. signal only works in main thread; tests use explicit stop()
            pass

    def _on_signal(self, signum: int, frame: Any) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def stop(self) -> None:
        """Force stop for tests / simulation (does not send real signal)."""
        self._event.set()


def _make_health_handler(settings: WorkerRuntimeSettings) -> type[BaseHTTPRequestHandler]:
    """Factory returning a request handler that serves runtime config + liveness."""

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.rstrip("/") in ("", "/health", "/readyz", "/live"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = settings.to_health_payload()
                payload["status"] = "alive"
                self.wfile.write(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8")
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Quiet in container logs unless DEBUG
            if os.environ.get("EDC_WORKER_HEALTH_DEBUG"):
                super().log_message(format, *args)

    return _HealthHandler


def _start_health_server(
    settings: WorkerRuntimeSettings, port: int | None
) -> threading.Thread | None:
    """Start a minimal HTTP health server on a background daemon thread (best-effort)."""
    if not port:
        return None
    try:
        handler_cls = _make_health_handler(settings)
        server = HTTPServer(("", port), handler_cls)
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name=f"worker-health-{port}",
        )
        thread.start()
        return thread
    except Exception:
        # Health server is best-effort; do not crash the worker on bind failure
        return None


class TranslationWorker:
    """Runs queued work through the existing contract-first service layer."""

    def process(self, item: TranslationWorkItem) -> TranslationWorkerResult:
        item.validate()
        try:
            translation_bundle = translate_document_bundle(
                item.document_bundle,
                target_language=item.target_language,
                provider_id=item.provider_id,
                allow_nc_licensed=item.allow_nc_licensed,
                certified=item.certified,
                tenant_id=item.tenant_id,
                glossary_ids=item.glossary_ids,
                instruction_set_id=item.instruction_set_id,
            )
        except RoutingError as exc:
            return TranslationWorkerResult.failed(
                item,
                auto_route_error_payload(str(exc), exc.diagnostics)["error"],
            )
        except Exception as exc:
            return TranslationWorkerResult.failed(
                item,
                {
                    "code": "translation_worker_failed",
                    "message": str(exc),
                },
            )
        return TranslationWorkerResult.succeeded(item, translation_bundle)

    def run_once(self, queue: WorkQueue) -> TranslationWorkerResult | None:
        item = queue.poll()
        if item is None:
            return None

        result = self.process(item)
        if result.status == "succeeded":
            queue.ack(item, result)
        else:
            queue.nack(item, result)
        return result

    def run_until_idle(
        self,
        queue: WorkQueue,
        *,
        max_idle_polls: int = 1,
        poll_interval_seconds: float = 0.0,
        max_items: int | None = None,
    ) -> list[TranslationWorkerResult]:
        """Run queued work until the queue is idle for the configured polls."""

        if max_idle_polls < 1:
            raise ValueError("max_idle_polls must be at least 1")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be at least 1 when provided")
        results: list[TranslationWorkerResult] = []
        idle_polls = 0
        while idle_polls < max_idle_polls:
            if max_items is not None and len(results) >= max_items:
                break
            result = self.run_once(queue)
            if result is None:
                idle_polls += 1
                if poll_interval_seconds > 0 and idle_polls < max_idle_polls:
                    sleep(poll_interval_seconds)
                continue
            results.append(result)
            idle_polls = 0
        return results

    def run_forever(
        self,
        queue: WorkQueue,
        *,
        stop_flag: StopFlag | None = None,
        poll_interval_seconds: float = 1.0,
        max_items: int | None = None,
        sleep_func: Callable[[float], None] = sleep,
        result_sink: Callable[[TranslationWorkerResult], None] | None = None,
    ) -> list[TranslationWorkerResult]:
        """Continuously poll work until stopped or a bounded item count is reached.

        When result_sink is provided (e.g. no-op for long-running daemons), results
        are forwarded to the sink instead of being retained in the returned list.
        This prevents unbounded memory growth in production worker daemons.
        """

        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be at least 1 when provided")

        results: list[TranslationWorkerResult] = []
        processed = 0
        while stop_flag is None or not stop_flag.is_set():
            if max_items is not None and processed >= max_items:
                break

            result = self.run_once(queue)
            if result is None:
                if poll_interval_seconds > 0:
                    sleep_func(poll_interval_seconds)
                continue
            processed += 1
            if result_sink is not None:
                result_sink(result)
            else:
                results.append(result)
        return results


def prewarm_models(
    registry: ModelRegistryStore, profile: str = "gpu-1x16", worker_id: str | None = None
) -> int:
    """Minimal prewarm for tranche 4: for each approved+valid model in the registry,
    record "prewarming" state via upsert_current_state (durable when Postgres backend).

    Does *not* perform actual model loading/weights (that is engine-specific, e.g. CT2
    or llama-server on the GPU profile). This provides the durable cache-state hook
    and observability for worker startup in production profiles.

    Returns number of models marked for prewarm.
    """
    marked = 0
    for status in registry.list():
        if status.approved and status.valid:
            vram = (status.vram_profile or "").lower()
            prof = profile.lower()
            # Affinity: match vram hint or any gpu/default profile (simple for now)
            if (
                prof in vram
                or not vram
                or "default" in prof
                or "gpu" in prof
                or "local" in prof
            ):
                registry.upsert_current_state(
                    model_id=status.model_id,
                    state="prewarming",
                    worker_id=worker_id,
                    model_profile=profile,
                    loaded_at=None,
                    metadata={"source": "worker_startup_prewarm", "profile": profile},
                )
                marked += 1
    return marked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edc-translation-worker")
    parser.add_argument(
        "--input",
        help="Path to a TranslationWorkItem JSON message. Reads stdin when omitted.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the worker result JSON.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Process local input messages until idle. Requires --input-dir.",
    )
    parser.add_argument(
        "--input-dir",
        help="Directory of TranslationWorkItem JSON messages for local loop mode.",
    )
    parser.add_argument(
        "--max-idle-polls",
        type=int,
        default=1,
        help="Idle polls before loop mode exits.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.0,
        help="Seconds to sleep between idle polls in loop mode.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="Maximum number of input messages to process in loop mode.",
    )
    parser.add_argument(
        "--queue-backend",
        choices=("local", "postgres", "kafka"),
        default="local",
        help="Queue backend to use. Unit tests use local; durable backends are opt-in.",
    )
    parser.add_argument(
        "--worker-id",
        default="local-worker",
        help="Stable worker identity used for durable queue claims and health.",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        help="Health endpoint port reserved for production worker deployments.",
    )
    parser.add_argument(
        "--model-profile",
        default="local-cpu",
        help="Runtime model/GPU profile label, for example gpu-1x16 or gpu-1x24.",
    )
    parser.add_argument(
        "--print-runtime-config",
        action="store_true",
        help="Print parsed runtime settings and exit without connecting to a queue.",
    )
    return parser


def runtime_settings_from_args(args: argparse.Namespace) -> WorkerRuntimeSettings:
    return WorkerRuntimeSettings(
        queue_backend=str(args.queue_backend),
        worker_id=str(args.worker_id),
        health_port=args.health_port,
        model_profile=str(args.model_profile),
        max_items=args.max_items,
    )


def main(argv: list[str] | None = None) -> int:
    """Run local worker input, bounded loops, or production daemon for durable queue backends.

    When --queue-backend=postgres (or future kafka) and neither --input nor --loop
    are supplied, the process enters long-running daemon mode:
    - Claims work via the durable PostgresWorkQueue (with built-in retry/DLQ)
    - Uses TranslationWorker.run_forever with signal-driven graceful shutdown
    - Starts a best-effort /readyz HTTP server if --health-port is given
    - Drains the current in-flight item on SIGTERM/SIGINT before exit
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    runtime_settings = runtime_settings_from_args(args)

    if args.print_runtime_config:
        print(
            json.dumps(
                runtime_settings.to_health_payload(),
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0

    backend = str(args.queue_backend)

    if backend == "local":
        if args.loop:
            if not args.input_dir:
                parser.error("--loop requires --input-dir")
            queue = LocalWorkQueue()
            for path in sorted(Path(args.input_dir).glob("*.json")):
                queue.push(
                    TranslationWorkItem.from_message(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
            results = TranslationWorker().run_until_idle(
                queue,
                max_idle_polls=args.max_idle_polls,
                poll_interval_seconds=args.poll_interval_seconds,
                max_items=runtime_settings.max_items,
            )
            print(
                json.dumps(
                    [result.to_message() for result in results],
                    ensure_ascii=False,
                    indent=2 if args.pretty else None,
                )
            )
            return 0 if all(result.status == "succeeded" for result in results) else 1

        # one-shot local mode
        raw = (
            Path(args.input).read_text(encoding="utf-8")
            if args.input
            else sys.stdin.read()
        )
        if not raw.strip():
            parser.error("local worker mode requires --input or --loop --input-dir")
        item = TranslationWorkItem.from_message(json.loads(raw))
        result = TranslationWorker().process(item)
        print(
            json.dumps(
                result.to_message(),
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0 if result.status == "succeeded" else 1

    # Durable backends (postgres for job state + queue; kafka for decoupled fanout via jobs/segments/results topics)
    if backend == "postgres":
        from .postgres_backend import make_postgres_work_queue

        queue = make_postgres_work_queue(
            worker_id=runtime_settings.worker_id,
            # retry/DLQ/visibility use the PostgresQueueSettings defaults
            # (max_attempts=3, retry 30s, visibility 15min) matching the tranche
        )
    elif backend == "kafka":
        from .kafka_backend import make_kafka_work_queue

        bootstrap = (
            os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
            or os.environ.get("REDPANDA_BOOTSTRAP_SERVERS")
            or os.environ.get("REDPANDA_BOOTSTRAP", "localhost:19092")
        )
        queue = make_kafka_work_queue(
            bootstrap_servers=bootstrap,
            group_id=f"edc-translation-workers-{runtime_settings.worker_id}".replace(":", "-"),
            # consume_topics=[TRANSLATION_SEGMENTS_TOPIC] for dedicated segment fanout workers
        )
    else:
        parser.error(f"unknown queue-backend: {backend}")

    # Start optional health/liveness HTTP endpoint (daemon or bounded test)
    _start_health_server(runtime_settings, runtime_settings.health_port)

    # Tranche 4 prewarm hook (runs for durable worker daemons): marks approved models
    # for the configured profile in the registry store (durable current_model_state when
    # backend=postgres). Safe no-op for in-memory; does not load weights.
    model_store: ModelRegistryStore = make_model_registry_store()
    prewarm_models(
        model_store,
        profile=runtime_settings.model_profile,
        worker_id=runtime_settings.worker_id,
    )

    # For durable consumption: use run_forever + signal stop flag.
    # If caller supplied --max-items we bound the run and collect results (test aid);
    # otherwise use a discard sink so the results list does not grow unbounded in prod.
    stop_flag = _SignalStopFlag()
    poll_interval = args.poll_interval_seconds
    if poll_interval <= 0:
        poll_interval = 1.0  # sensible daemon default (1s poll when idle)

    def _discard(_result: TranslationWorkerResult) -> None:
        # no-op: prevents OOM on long-running worker daemons
        return None

    use_sink = runtime_settings.max_items is None
    results = TranslationWorker().run_forever(
        queue,
        stop_flag=stop_flag,
        poll_interval_seconds=poll_interval,
        max_items=runtime_settings.max_items,
        result_sink=_discard if use_sink else None,
    )

    # Only emit output for bounded runs (max-items supplied); daemons exit silently on signal
    if results:
        print(
            json.dumps(
                [r.to_message() for r in results],
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0 if all(r.status == "succeeded" for r in results) else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
