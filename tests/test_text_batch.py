from __future__ import annotations

import json
from pathlib import Path

from edc_translation.client import TranslationClient
from edc_translation.service import (
    get_text_file_batch_log_text,
    get_text_file_batch_logs,
    get_text_file_batch_outputs,
    get_text_file_batch_status,
    save_text_file_batch_log,
    submit_text_file_batch_job,
)
from edc_translation.text_batch import (
    TextFileBatchRepository,
    detect_text_encoding,
    read_text_file,
)


def test_detect_text_encoding_handles_utf8_utf16_and_ansi(tmp_path: Path):
    utf8 = tmp_path / "utf8.txt"
    utf16 = tmp_path / "utf16.txt"
    ansi = tmp_path / "ansi.txt"
    utf8.write_text("Hello café", encoding="utf-8")
    utf16.write_text("Hello café", encoding="utf-16")
    ansi.write_bytes("Hello café".encode("cp1252"))

    assert detect_text_encoding(utf8.read_bytes()).encoding == "utf-8"
    assert detect_text_encoding(utf16.read_bytes()).encoding == "utf-16"

    decoded = read_text_file(ansi)
    assert decoded.text == "Hello café"
    assert decoded.encoding in {"cp1252", "cp1250", "latin-1"}


def test_text_file_batch_translates_folder_and_writes_outputs(tmp_path: Path):
    source = tmp_path / "input"
    nested = source / "nested"
    output = tmp_path / "output"
    nested.mkdir(parents=True)
    (source / "utf8.txt").write_text("Hello.", encoding="utf-8")
    (nested / "utf16.txt").write_text("World.", encoding="utf-16")
    (source / "ansi.txt").write_bytes("Café.".encode("cp1252"))
    repository = TextFileBatchRepository()

    job = submit_text_file_batch_job(
        source_path=source,
        output_dir=output,
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
        output_encoding="utf-16",
        repository=repository,
        run_async=False,
    )

    assert job["status"] == "succeeded"
    assert job["total_files"] == 3
    assert job["processed_files"] == 3
    assert job["failed_files"] == 0
    assert (output / "utf8.txt").read_text(encoding="utf-16") == "Hello. [en->fr]"
    assert (output / "nested" / "utf16.txt").read_text(encoding="utf-16") == (
        "World. [en->fr]"
    )
    assert (output / "ansi.txt.translation-bundle.json").is_file()

    status = get_text_file_batch_status(job["job_id"], repository=repository)
    logs = get_text_file_batch_logs(job["job_id"], repository=repository)
    outputs = get_text_file_batch_outputs(job["job_id"], repository=repository)
    manifest = json.loads(Path(status["manifest_path"]).read_text(encoding="utf-8"))

    assert status["terminal"] is True
    assert any("Converted file" in entry["message"] for entry in logs["logs"])
    assert len(outputs["files"]) == 3
    assert manifest["job_id"] == job["job_id"]
    assert manifest["status"] == "succeeded"
    assert manifest["manifest_path"] == status["manifest_path"]


def test_text_file_batch_auto_detects_source_language_and_saves_log(tmp_path: Path):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "english.txt").write_text("Hello world.", encoding="utf-8")
    repository = TextFileBatchRepository()

    job = submit_text_file_batch_job(
        source_path=source,
        output_dir=output,
        source_language="auto",
        target_language="fr",
        provider_id="deterministic_ci",
        repository=repository,
        run_async=False,
    )
    outputs = get_text_file_batch_outputs(job["job_id"], repository=repository)
    log_text = get_text_file_batch_log_text(job["job_id"], repository=repository)
    saved = save_text_file_batch_log(
        job["job_id"],
        log_path=output / "custom.log",
        repository=repository,
    )

    assert outputs["files"][0]["effective_source_language"] == "en"
    assert outputs["files"][0]["language_detection"]["provider"] in {
        "heuristic",
        "ascii-default",
        "facebook-fasttext-lid",
    }
    assert "Detected source language en" in log_text
    assert Path(saved["log_path"]).read_text(encoding="utf-8") == log_text


def test_text_file_batch_rejects_auto_target_language(tmp_path: Path):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "english.txt").write_text("Hello world.", encoding="utf-8")
    repository = TextFileBatchRepository()

    job = submit_text_file_batch_job(
        source_path=source,
        output_dir=output,
        source_language="auto",
        target_language="auto",
        provider_id="deterministic_ci",
        repository=repository,
        run_async=False,
    )

    assert job["status"] == "failed"
    assert "target_language=auto is not supported" in job["error"]["message"]


def test_text_file_batch_match_source_output_encoding(tmp_path: Path):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "source.txt").write_text("Hello.", encoding="utf-16")
    repository = TextFileBatchRepository()

    job = submit_text_file_batch_job(
        source_path=source,
        output_dir=output,
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
        output_encoding="match-source",
        repository=repository,
        run_async=False,
    )
    outputs = get_text_file_batch_outputs(job["job_id"], repository=repository)

    assert outputs["files"][0]["output_encoding"] == "utf-16"
    assert (output / "source.txt").read_text(encoding="utf-16") == "Hello. [en->fr]"


def test_translation_client_supports_text_file_batch(tmp_path: Path):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "one.txt").write_text("Hello.", encoding="utf-8")
    client = TranslationClient()

    job = client.submit_text_file_batch(
        source_path=source,
        output_dir=output,
        source_language="en",
        target_language="fr",
        provider_id="deterministic_ci",
        run_async=False,
    )

    assert client.get_text_file_batch_status(job["job_id"])["status"] == "succeeded"
    assert client.get_text_file_batch_outputs(job["job_id"])["files"][0]["status"] == (
        "succeeded"
    )
    assert any(
        entry["message"] == "Batch translation completed"
        for entry in client.get_text_file_batch_logs(job["job_id"])["logs"]
    )
    assert "Batch translation completed" in client.get_text_file_batch_log_text(
        job["job_id"]
    )
    saved = client.save_text_file_batch_log(job["job_id"], log_path=output / "client.log")
    assert Path(saved["log_path"]).is_file()
