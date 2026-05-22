"""Encoding-aware local text file batch translation jobs."""

from __future__ import annotations

import codecs
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from edc_translation.jobs import utc_now_iso
from edc_translation.language_id import detect_language


TERMINAL_BATCH_STATUSES = {"succeeded", "completed_with_errors", "failed"}
DEFAULT_TEXT_EXTENSIONS = [".txt"]
SUPPORTED_OUTPUT_ENCODINGS = {
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "cp1252",
    "ansi",
    "match-source",
}


@dataclass(frozen=True)
class TextEncodingDetection:
    encoding: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecodedTextFile:
    text: str
    encoding: str
    confidence: float
    detection_source: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TextFileBatchJob:
    job_id: str
    status: str
    source_path: str
    output_dir: str
    source_language: str
    target_language: str
    provider_id: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    files: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    manifest_path: str | None = None

    def status_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "source_path": self.source_path,
            "output_dir": self.output_dir,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "provider_id": self.provider_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "settings": self.settings,
            "manifest_path": self.manifest_path,
            "error": self.error,
            "terminal": self.status in TERMINAL_BATCH_STATUSES,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.status_payload()
        payload["files"] = self.files
        payload["logs"] = self.logs
        return payload


class TextFileBatchRepository:
    """Process-local batch job store for desktop/local workflows."""

    def __init__(self) -> None:
        self._jobs: dict[str, TextFileBatchJob] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        source_path: str,
        output_dir: str,
        source_language: str,
        target_language: str,
        provider_id: str,
        settings: dict[str, Any],
    ) -> TextFileBatchJob:
        now = utc_now_iso()
        job = TextFileBatchJob(
            job_id=f"tfjob_{uuid4().hex}",
            status="queued",
            source_path=source_path,
            output_dir=output_dir,
            source_language=source_language,
            target_language=target_language,
            provider_id=provider_id,
            created_at=now,
            updated_at=now,
            settings=settings,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> TextFileBatchJob:
        with self._lock:
            return self._jobs[job_id]

    def list(self) -> list[TextFileBatchJob]:
        with self._lock:
            return list(self._jobs.values())

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def mark_running(self, job_id: str) -> TextFileBatchJob:
        return self._update(job_id, status="running")

    def set_total(self, job_id: str, total_files: int) -> TextFileBatchJob:
        return self._update(job_id, total_files=total_files)

    def append_log(
        self,
        job_id: str,
        *,
        message: str,
        level: str = "info",
        file_path: str | None = None,
        output_path: str | None = None,
    ) -> TextFileBatchJob:
        entry = {
            "timestamp": utc_now_iso(),
            "level": level,
            "message": message,
        }
        if file_path is not None:
            entry["file_path"] = file_path
        if output_path is not None:
            entry["output_path"] = output_path
        with self._lock:
            job = self._jobs[job_id]
            job.logs.append(entry)
            job.updated_at = utc_now_iso()
            return job

    def add_file_result(self, job_id: str, result: dict[str, Any]) -> TextFileBatchJob:
        with self._lock:
            job = self._jobs[job_id]
            job.files.append(result)
            job.processed_files += 1
            if result["status"] != "succeeded":
                job.failed_files += 1
            job.updated_at = utc_now_iso()
            return job

    def mark_succeeded(
        self,
        job_id: str,
        *,
        manifest_path: str | None = None,
    ) -> TextFileBatchJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="succeeded",
            updated_at=now,
            completed_at=now,
            manifest_path=manifest_path,
            error=None,
        )

    def mark_completed_with_errors(
        self,
        job_id: str,
        *,
        manifest_path: str | None = None,
    ) -> TextFileBatchJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="completed_with_errors",
            updated_at=now,
            completed_at=now,
            manifest_path=manifest_path,
            error=None,
        )

    def mark_failed(self, job_id: str, *, error: dict[str, Any]) -> TextFileBatchJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="failed",
            updated_at=now,
            completed_at=now,
            error=error,
        )

    def _update(self, job_id: str, **changes: Any) -> TextFileBatchJob:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            if "updated_at" not in changes:
                job.updated_at = utc_now_iso()
            return job


def normalize_text_encoding(encoding: str) -> str:
    lowered = encoding.strip().lower().replace("_", "-")
    aliases = {
        "auto": "auto",
        "utf8": "utf-8",
        "utf-8-bom": "utf-8-sig",
        "utf16": "utf-16",
        "utf16-le": "utf-16-le",
        "utf16-be": "utf-16-be",
        "windows-1252": "cp1252",
        "ansi": "cp1252",
        "match": "match-source",
    }
    return aliases.get(lowered, lowered)


def detect_text_encoding(raw: bytes) -> TextEncodingDetection:
    if raw.startswith(codecs.BOM_UTF8):
        return TextEncodingDetection("utf-8-sig", 1.0, "bom")
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return TextEncodingDetection("utf-16", 1.0, "bom")

    utf16_guess = _detect_utf16_without_bom(raw)
    if utf16_guess is not None:
        return utf16_guess

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        return TextEncodingDetection("utf-8", 0.95, "strict-utf8")

    try:
        raw.decode("cp1252")
    except UnicodeDecodeError:
        normalized = _detect_with_charset_normalizer(raw)
        if normalized is not None:
            return normalized
        return TextEncodingDetection("latin-1", 0.25, "fallback")
    return TextEncodingDetection("cp1252", 0.65, "ansi-fallback")


def read_text_file(path: str | Path, *, input_encoding: str = "auto") -> DecodedTextFile:
    source = Path(path)
    raw = source.read_bytes()
    normalized = normalize_text_encoding(input_encoding)
    detection = (
        detect_text_encoding(raw)
        if normalized == "auto"
        else TextEncodingDetection(normalized, 1.0, "caller")
    )
    text = raw.decode(detection.encoding, errors="replace")
    return DecodedTextFile(
        text=text,
        encoding=detection.encoding,
        confidence=detection.confidence,
        detection_source=detection.source,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
    )


def write_text_file(
    path: str | Path,
    text: str,
    *,
    output_encoding: str,
    source_encoding: str,
) -> str:
    normalized = normalize_text_encoding(output_encoding)
    resolved_encoding = source_encoding if normalized == "match-source" else normalized
    resolved_encoding = normalize_text_encoding(resolved_encoding)
    if resolved_encoding not in SUPPORTED_OUTPUT_ENCODINGS - {"match-source", "ansi"}:
        raise ValueError(f"Unsupported output encoding: {output_encoding}")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding=resolved_encoding)
    return resolved_encoding


def discover_text_files(
    source_path: str | Path,
    *,
    output_dir: str | Path,
    recursive: bool = True,
    file_extensions: list[str] | None = None,
) -> list[Path]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist: {source}")
    output = Path(output_dir).resolve()
    extensions = _normalize_extensions(file_extensions)
    if source.is_file():
        return [source] if _matches_extension(source, extensions) else []
    pattern = "**/*" if recursive else "*"
    files: list[Path] = []
    for candidate in source.glob(pattern):
        if not candidate.is_file() or not _matches_extension(candidate, extensions):
            continue
        try:
            if candidate.resolve().is_relative_to(output):
                continue
        except OSError:
            pass
        files.append(candidate)
    return sorted(files)


def submit_text_file_batch_job(
    *,
    source_path: str | Path,
    output_dir: str | Path,
    source_language: str,
    target_language: str,
    provider_id: str = "deterministic_ci",
    input_encoding: str = "auto",
    output_encoding: str = "utf-8",
    recursive: bool = True,
    file_extensions: list[str] | None = None,
    allow_nc_licensed: bool = False,
    certified: bool = False,
    tenant_id: str = "standalone",
    glossary_ids: list[str] | None = None,
    instruction_set_id: str | None = None,
    write_translation_bundles: bool = True,
    write_manifest: bool = True,
    continue_on_error: bool = True,
    repository: TextFileBatchRepository,
    run_async: bool = True,
) -> dict[str, Any]:
    settings = {
        "input_encoding": normalize_text_encoding(input_encoding),
        "output_encoding": normalize_text_encoding(output_encoding),
        "recursive": recursive,
        "file_extensions": _normalize_extensions(file_extensions),
        "allow_nc_licensed": allow_nc_licensed,
        "certified": certified,
        "tenant_id": tenant_id,
        "glossary_ids": glossary_ids or [],
        "instruction_set_id": instruction_set_id,
        "write_translation_bundles": write_translation_bundles,
        "write_manifest": write_manifest,
        "continue_on_error": continue_on_error,
        "persistence": "process_local_in_memory",
        "language_detection": "facebook-fasttext-lid optional via EDC_TRANSLATION_FASTTEXT_LID_MODEL, fallback heuristic",
    }
    job = repository.create(
        source_path=str(source_path),
        output_dir=str(output_dir),
        source_language=source_language,
        target_language=target_language,
        provider_id=provider_id,
        settings=settings,
    )
    args = {
        "job_id": job.job_id,
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "source_language": source_language,
        "target_language": target_language,
        "provider_id": provider_id,
        "settings": settings,
        "repository": repository,
    }
    if run_async:
        Thread(target=_run_text_file_batch_job, kwargs=args, daemon=True).start()
    else:
        _run_text_file_batch_job(**args)
    return repository.get(job.job_id).status_payload()


def _run_text_file_batch_job(
    *,
    job_id: str,
    source_path: str,
    output_dir: str,
    source_language: str,
    target_language: str,
    provider_id: str,
    settings: dict[str, Any],
    repository: TextFileBatchRepository,
) -> None:
    from edc_translation.service import raw_text_to_document_bundle, translate_document_bundle

    repository.mark_running(job_id)
    repository.append_log(job_id, message="Batch translation started")
    try:
        if target_language == "auto":
            raise ValueError(
                "target_language=auto is not supported for translation; select a target language"
            )
        files = discover_text_files(
            source_path,
            output_dir=output_dir,
            recursive=bool(settings["recursive"]),
            file_extensions=list(settings["file_extensions"]),
        )
        repository.set_total(job_id, len(files))
        repository.append_log(job_id, message=f"Discovered {len(files)} text file(s)")
        if not files:
            raise FileNotFoundError("No matching text files were found")

        source_root = Path(source_path)
        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        for path in files:
            relative_path = _relative_output_path(path, source_root)
            output_path = output_root / relative_path
            try:
                decoded = read_text_file(path, input_encoding=str(settings["input_encoding"]))
                repository.append_log(
                    job_id,
                    message=f"Reading as {decoded.encoding}",
                    file_path=str(path),
                )
                language_detection = (
                    detect_language(decoded.text)
                    if source_language == "auto"
                    else None
                )
                effective_source_language = (
                    language_detection.language
                    if language_detection is not None
                    else source_language
                )
                if language_detection is not None:
                    repository.append_log(
                        job_id,
                        message=(
                            "Detected source language "
                            f"{language_detection.language} "
                            f"({language_detection.confidence:.2f}, "
                            f"{language_detection.provider})"
                        ),
                        file_path=str(path),
                    )
                bundle = raw_text_to_document_bundle(
                    decoded.text,
                    source_language=effective_source_language,
                    source_name=str(relative_path),
                )
                translated = translate_document_bundle(
                    bundle,
                    target_language=target_language,
                    provider_id=provider_id,
                    allow_nc_licensed=bool(settings["allow_nc_licensed"]),
                    certified=bool(settings["certified"]),
                    tenant_id=str(settings["tenant_id"]),
                    glossary_ids=list(settings["glossary_ids"]),
                    instruction_set_id=settings["instruction_set_id"],
                )
                translated_text = _bundle_to_text(translated)
                resolved_output_encoding = write_text_file(
                    output_path,
                    translated_text,
                    output_encoding=str(settings["output_encoding"]),
                    source_encoding=decoded.encoding,
                )
                bundle_path = None
                if settings["write_translation_bundles"]:
                    bundle_path = str(
                        output_path.with_suffix(
                            output_path.suffix + ".translation-bundle.json"
                        )
                    )
                    Path(bundle_path).write_text(
                        json.dumps(translated, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                result = {
                    "status": "succeeded",
                    "source_path": str(path),
                    "relative_path": str(relative_path),
                    "output_path": str(output_path),
                    "bundle_path": bundle_path,
                    "input_encoding": decoded.encoding,
                    "input_encoding_confidence": decoded.confidence,
                    "input_encoding_source": decoded.detection_source,
                    "output_encoding": resolved_output_encoding,
                    "requested_source_language": source_language,
                    "effective_source_language": effective_source_language,
                    "target_language": target_language,
                    "language_detection": language_detection.to_dict()
                    if language_detection is not None
                    else {
                        "language": effective_source_language,
                        "confidence": 1.0,
                        "provider": "caller",
                        "model_id": None,
                    },
                    "source_sha256": decoded.sha256,
                    "source_size_bytes": decoded.size_bytes,
                    "translation_bundle_schema": translated["schema_version"],
                }
                repository.add_file_result(job_id, result)
                repository.append_log(
                    job_id,
                    message="Converted file",
                    file_path=str(path),
                    output_path=str(output_path),
                )
            except Exception as exc:
                result = {
                    "status": "failed",
                    "source_path": str(path),
                    "relative_path": str(relative_path),
                    "output_path": str(output_path),
                    "error": str(exc),
                }
                repository.add_file_result(job_id, result)
                repository.append_log(
                    job_id,
                    level="error",
                    message=str(exc),
                    file_path=str(path),
                    output_path=str(output_path),
                )
                if not settings["continue_on_error"]:
                    raise

        manifest_path = (
            str(output_root / "translation-batch-report.json")
            if settings["write_manifest"]
            else None
        )
        job = repository.get(job_id)
        if job.failed_files:
            repository.mark_completed_with_errors(job_id, manifest_path=manifest_path)
        else:
            repository.mark_succeeded(job_id, manifest_path=manifest_path)
        repository.append_log(job_id, message="Batch translation completed")
        if manifest_path is not None:
            _write_manifest(repository.get(job_id), manifest_path)
    except Exception as exc:
        repository.mark_failed(
            job_id,
            error={"code": "text_file_batch_failed", "message": str(exc)},
        )
        repository.append_log(job_id, level="error", message=str(exc))


def _bundle_to_text(translation_bundle: dict[str, Any]) -> str:
    spans = sorted(
        translation_bundle["translated_spans"],
        key=lambda span: (int(span["page_number"]), str(span["span_id"])),
    )
    return "\n".join(str(span["translated_text"]) for span in spans)


def _write_manifest(job: TextFileBatchJob, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_batch_log(job: TextFileBatchJob) -> str:
    lines = []
    for entry in job.logs:
        suffix = ""
        if entry.get("file_path"):
            suffix += f" :: {entry['file_path']}"
        if entry.get("output_path"):
            suffix += f" -> {entry['output_path']}"
        lines.append(
            f"{entry['timestamp']} {str(entry['level']).upper()} "
            f"{entry['message']}{suffix}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def save_batch_log(
    job: TextFileBatchJob,
    *,
    log_path: str | Path | None = None,
) -> str:
    output_path = Path(log_path) if log_path else Path(job.output_dir) / "translation-batch.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_batch_log(job), encoding="utf-8")
    return str(output_path)


def _relative_output_path(path: Path, source_root: Path) -> Path:
    if source_root.is_file():
        return Path(path.name)
    return path.relative_to(source_root)


def _normalize_extensions(file_extensions: list[str] | None) -> list[str]:
    values = file_extensions or DEFAULT_TEXT_EXTENSIONS
    out = []
    for value in values:
        item = value.strip().lower()
        if not item:
            continue
        out.append(item if item.startswith(".") else f".{item}")
    return out or DEFAULT_TEXT_EXTENSIONS


def _matches_extension(path: Path, extensions: list[str]) -> bool:
    return path.suffix.lower() in extensions


def _detect_utf16_without_bom(raw: bytes) -> TextEncodingDetection | None:
    if len(raw) < 4:
        return None
    even_nulls = raw[0::2].count(0)
    odd_nulls = raw[1::2].count(0)
    half_length = max(1, len(raw) // 2)
    if odd_nulls / half_length > 0.3 and even_nulls / half_length < 0.05:
        return TextEncodingDetection("utf-16-le", 0.8, "null-byte-pattern")
    if even_nulls / half_length > 0.3 and odd_nulls / half_length < 0.05:
        return TextEncodingDetection("utf-16-be", 0.8, "null-byte-pattern")
    return None


def _detect_with_charset_normalizer(raw: bytes) -> TextEncodingDetection | None:
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return None
    best = from_bytes(raw).best()
    if best is None or not best.encoding:
        return None
    encoding = normalize_text_encoding(best.encoding)
    confidence = max(0.0, min(1.0, 1.0 - float(best.chaos or 0.0)))
    return TextEncodingDetection(encoding, confidence, "charset-normalizer")
