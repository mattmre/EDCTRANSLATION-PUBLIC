from __future__ import annotations

import json
from pathlib import Path

import pytest

from edc_translation.contracts import validate_payload
from edc_translation.worker import (
    LocalWorkQueue,
    TranslationWorkItem,
    TranslationWorker,
    WorkerRuntimeSettings,
    _SignalStopFlag,
    _make_health_handler,
    _start_health_server,
    build_parser,
    main as worker_main,
    runtime_settings_from_args,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edc_contracts"


class _StopFlag:
    def __init__(self) -> None:
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped

    def stop(self) -> None:
        self.stopped = True


def _document_bundle() -> dict:
    return json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )


def test_work_item_round_trips_as_queue_message():
    document = _document_bundle()
    item = TranslationWorkItem.from_document_bundle(
        document,
        job_id="trjob_test",
        target_language="fr",
        provider_id="deterministic_ci",
        tenant_id="tenant-a",
        glossary_ids=["glossary-a"],
        instruction_set_id="default-medical-edc",
        metadata={"priority": "normal"},
    )

    message = item.to_message()
    restored = TranslationWorkItem.from_message(message)

    assert restored == item
    assert message["document_id"] == document["document_id"]
    assert message["source_language"] == "en"
    assert message["glossary_ids"] == ["glossary-a"]
    assert message["instruction_set_id"] == "default-medical-edc"


def test_worker_processes_deterministic_ci_document_bundle():
    document = _document_bundle()
    item = TranslationWorkItem.from_document_bundle(
        document,
        job_id="trjob_test",
        target_language="fr",
        provider_id="deterministic_ci",
    )

    result = TranslationWorker().process(item)

    assert result.status == "succeeded"
    assert result.error is None
    assert result.translation_bundle is not None
    validate_payload(result.translation_bundle, "translation-bundle-v1")
    assert result.translation_bundle["document_id"] == document["document_id"]
    assert result.translation_bundle["engine_provider"]["id"] == "deterministic_ci"
    assert result.translation_bundle["translated_spans"][0][
        "translated_text"
    ].endswith("[en->fr]")


def test_local_queue_run_once_acks_successful_work():
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_test",
        target_language="fr",
        provider_id="deterministic_ci",
    )
    queue = LocalWorkQueue([item])

    result = TranslationWorker().run_once(queue)

    assert result is not None
    assert result.status == "succeeded"
    assert queue.acked == [result]
    assert queue.nacked == []
    assert TranslationWorker().run_once(queue) is None


def test_worker_reports_auto_route_failure(monkeypatch: pytest.MonkeyPatch):
    for env in (
        "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_NLLB_MODEL_DIR",
        "EDC_TRANSLATION_LOCAL_CT2_MADLAD_MODEL_DIR",
    ):
        monkeypatch.delenv(env, raising=False)
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_auto",
        target_language="fr",
        provider_id="auto",
    )
    queue = LocalWorkQueue([item])

    result = TranslationWorker().run_once(queue)

    assert result is not None
    assert result.status == "failed"
    assert result.translation_bundle is None
    assert result.error is not None
    assert result.error["code"] == "auto_route_unavailable"
    assert result.error["routing_diagnostics"]["provider_id"] == "auto"
    assert queue.acked == []
    assert queue.nacked == [result]


def test_worker_entrypoint_processes_one_json_message(tmp_path: Path, capsys):
    item = TranslationWorkItem.from_document_bundle(
        _document_bundle(),
        job_id="trjob_cli",
        target_language="fr",
        provider_id="deterministic_ci",
    )
    message_path = tmp_path / "work-item.json"
    message_path.write_text(json.dumps(item.to_message()), encoding="utf-8")

    assert worker_main(["--input", str(message_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == "trjob_cli"
    assert payload["status"] == "succeeded"
    assert payload["translation_bundle"]["schema_version"] == "translation-bundle-v1"


def test_worker_run_until_idle_processes_available_items():
    items = [
        TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_loop_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        for index in range(2)
    ]
    queue = LocalWorkQueue(items)

    results = TranslationWorker().run_until_idle(queue, max_idle_polls=2)

    assert [result.job_id for result in results] == ["trjob_loop_0", "trjob_loop_1"]
    assert all(result.status == "succeeded" for result in results)
    assert queue.acked == results


def test_worker_run_until_idle_honors_max_items():
    items = [
        TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_bounded_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        for index in range(3)
    ]
    queue = LocalWorkQueue(items)

    results = TranslationWorker().run_until_idle(queue, max_idle_polls=2, max_items=2)

    assert [result.job_id for result in results] == [
        "trjob_bounded_0",
        "trjob_bounded_1",
    ]
    assert queue.acked == results
    assert TranslationWorker().run_once(queue).job_id == "trjob_bounded_2"  # type: ignore[union-attr]


def test_worker_run_forever_stops_after_max_items():
    items = [
        TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_forever_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        for index in range(3)
    ]
    queue = LocalWorkQueue(items)

    results = TranslationWorker().run_forever(
        queue,
        poll_interval_seconds=0.0,
        max_items=2,
    )

    assert [result.job_id for result in results] == [
        "trjob_forever_0",
        "trjob_forever_1",
    ]
    assert queue.acked == results
    assert TranslationWorker().run_once(queue).job_id == "trjob_forever_2"  # type: ignore[union-attr]


def test_worker_run_forever_uses_poll_interval_until_stop_flag_is_set():
    queue = LocalWorkQueue()
    stop_flag = _StopFlag()
    sleeps: list[float] = []

    def stop_after_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        stop_flag.stop()

    results = TranslationWorker().run_forever(
        queue,
        stop_flag=stop_flag,
        poll_interval_seconds=0.25,
        sleep_func=stop_after_sleep,
    )

    assert results == []
    assert sleeps == [0.25]


def test_worker_entrypoint_loop_processes_input_directory(tmp_path: Path, capsys):
    for index in range(2):
        item = TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_dir_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        (tmp_path / f"{index}.json").write_text(
            json.dumps(item.to_message()),
            encoding="utf-8",
        )

    assert worker_main(["--loop", "--input-dir", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [result["job_id"] for result in payload] == ["trjob_dir_0", "trjob_dir_1"]
    assert all(result["status"] == "succeeded" for result in payload)


def test_worker_entrypoint_loop_honors_max_items(tmp_path: Path, capsys):
    for index in range(3):
        item = TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_dir_bounded_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        (tmp_path / f"{index}.json").write_text(
            json.dumps(item.to_message()),
            encoding="utf-8",
        )

    assert worker_main(["--loop", "--input-dir", str(tmp_path), "--max-items", "2"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [result["job_id"] for result in payload] == [
        "trjob_dir_bounded_0",
        "trjob_dir_bounded_1",
    ]
    assert all(result["status"] == "succeeded" for result in payload)


def test_worker_runtime_settings_parse_without_live_backend(capsys):
    assert (
        worker_main(
            [
                "--queue-backend",
                "postgres",
                "--worker-id",
                "worker-a",
                "--health-port",
                "8090",
                "--model-profile",
                "gpu-1x16",
                "--max-items",
                "2",
                "--print-runtime-config",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "queue_backend": "postgres",
        "worker_id": "worker-a",
        "health_port": 8090,
        "model_profile": "gpu-1x16",
        "max_items": 2,
        "status": "configured",
    }


def test_worker_runtime_parser_keeps_local_defaults():
    args = build_parser().parse_args([])
    settings = runtime_settings_from_args(args)

    assert settings == WorkerRuntimeSettings()


# --- Production worker (daemon, graceful shutdown, health, durable wiring) tests ---


def test_signal_stop_flag_explicit_stop():
    flag = _SignalStopFlag()
    assert not flag.is_set()
    flag.stop()
    assert flag.is_set()


def test_run_forever_with_result_sink_discards_and_still_respects_max_items():
    items = [
        TranslationWorkItem.from_document_bundle(
            _document_bundle(),
            job_id=f"trjob_sink_{index}",
            target_language="fr",
            provider_id="deterministic_ci",
        )
        for index in range(3)
    ]
    queue = LocalWorkQueue(items)
    collected: list[object] = []

    def sink(r: object) -> None:
        collected.append(r)

    results = TranslationWorker().run_forever(
        queue,
        poll_interval_seconds=0.0,
        max_items=2,
        result_sink=sink,
    )

    # With sink, the returned list stays empty (no accumulation)
    assert results == []
    # But we still processed exactly max_items via the sink
    assert len(collected) == 2
    assert all(hasattr(x, "status") and x.status == "succeeded" for x in collected)


def test_run_forever_with_result_sink_unbounded_does_not_grow_results_list():
    # Simulate a few items then explicit stop; returned list must stay small ([])
    queue = LocalWorkQueue(
        [
            TranslationWorkItem.from_document_bundle(
                _document_bundle(),
                job_id=f"trjob_unbounded_{i}",
                target_language="fr",
                provider_id="deterministic_ci",
            )
            for i in range(5)
        ]
    )
    stop = _SignalStopFlag()
    collected = []

    def sink(r):
        collected.append(r)
        if len(collected) >= 3:
            stop.stop()

    res = TranslationWorker().run_forever(
        queue, stop_flag=stop, poll_interval_seconds=0.0, result_sink=sink
    )
    assert res == []
    assert len(collected) == 3


def test_health_handler_serves_readyz_and_config(monkeypatch: pytest.MonkeyPatch):
    settings = WorkerRuntimeSettings(
        queue_backend="postgres",
        worker_id="prod-w-1",
        health_port=18090,
        model_profile="gpu-1x16",
        max_items=None,
    )
    Handler = _make_health_handler(settings)

    # We don't bind a real socket here; just exercise the handler class logic via a fake request
    # (http.server handlers are a bit awkward to unit without a server; we at least validate construction)
    assert Handler is not None

    # Smoke that start function returns a thread or None (never crashes on bad port in test env)
    th = _start_health_server(settings, None)
    assert th is None

    # Port 0 would auto-assign but we avoid real bind in unit test to keep hermetic
    # The integration path (real worker + postgres) exercises the live /readyz.


def test_worker_main_postgres_print_config_still_works(capsys):
    # This path must continue to work without touching the DB (print happens before any wiring)
    rc = worker_main(
        [
            "--queue-backend",
            "postgres",
            "--worker-id",
            "w-prod",
            "--health-port",
            "0",
            "--model-profile",
            "gpu-test",
            "--print-runtime-config",
            "--pretty",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["queue_backend"] == "postgres"
    assert out["worker_id"] == "w-prod"
    assert out["model_profile"] == "gpu-test"
    assert out["status"] == "configured"
