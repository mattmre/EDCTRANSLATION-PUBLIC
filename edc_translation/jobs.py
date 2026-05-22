"""Local translation job repository abstractions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Protocol
from uuid import uuid4


TERMINAL_JOB_STATUSES = {"succeeded", "failed"}


class JobRepository(Protocol):
    """Storage boundary for local and future durable translation job ledgers."""

    def create(
        self,
        *,
        document_id: str,
        target_language: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> "TranslationJob": ...

    def mark_running(self, job_id: str) -> "TranslationJob": ...

    def mark_succeeded(
        self,
        job_id: str,
        *,
        translation_bundle: dict[str, Any],
    ) -> "TranslationJob": ...

    def mark_failed(self, job_id: str, *, error: dict[str, Any]) -> "TranslationJob": ...

    def get(self, job_id: str) -> "TranslationJob": ...

    def list(self) -> list["TranslationJob"]: ...

    def clear(self) -> None: ...


@dataclass(frozen=True)
class TranslationWorkItem:
    """Queue payload for one DocumentBundle translation job."""

    document_bundle: dict[str, Any]
    target_language: str
    provider_id: str
    allow_nc_licensed: bool = False
    certified: bool = False
    tenant_id: str = "standalone"
    glossary_ids: list[str] | None = None
    instruction_set_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    job_id: str | None = None
    work_id: str | None = None
    source_language: str | None = None

    @classmethod
    def from_document_bundle(
        cls,
        document_bundle: dict[str, Any],
        *,
        job_id: str,
        work_id: str | None = None,
        target_language: str,
        provider_id: str = "passthrough",
        tenant_id: str = "standalone",
        source_language: str | None = None,
        allow_nc_licensed: bool = False,
        certified: bool = False,
        glossary_ids: list[str] | None = None,
        instruction_set_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "TranslationWorkItem":
        return cls(
            document_bundle=document_bundle,
            target_language=target_language,
            provider_id=provider_id,
            allow_nc_licensed=allow_nc_licensed,
            certified=certified,
            tenant_id=tenant_id,
            glossary_ids=list(glossary_ids or []),
            instruction_set_id=instruction_set_id,
            metadata=dict(metadata or {}),
            job_id=job_id,
            work_id=work_id or f"{job_id}:document",
            source_language=source_language or _source_language(document_bundle),
        )

    @classmethod
    def from_message(cls, payload: dict[str, Any]) -> "TranslationWorkItem":
        item = cls(
            document_bundle=dict(payload["document_bundle"]),
            target_language=str(payload["target_language"]),
            provider_id=str(payload["provider_id"]),
            allow_nc_licensed=bool(payload.get("allow_nc_licensed", False)),
            certified=bool(payload.get("certified", False)),
            tenant_id=str(payload.get("tenant_id", "standalone")),
            glossary_ids=[str(value) for value in payload.get("glossary_ids", [])],
            instruction_set_id=payload.get("instruction_set_id"),
            metadata=dict(payload.get("metadata", {})),
            job_id=str(payload["job_id"]),
            work_id=str(payload["work_id"]),
            source_language=str(payload.get("source_language") or ""),
        )
        item.validate()
        if payload.get("document_id") and str(payload["document_id"]) != item.document_id:
            raise ValueError(
                "work item document_id does not match DocumentBundle document_id"
            )
        return item

    @property
    def document_id(self) -> str:
        return str(self.document_bundle["document_id"])

    @property
    def resolved_job_id(self) -> str:
        return self.job_id or str(self.metadata.get("job_id") or self.document_id)

    @property
    def resolved_work_id(self) -> str:
        return self.work_id or f"{self.resolved_job_id}:document"

    @property
    def resolved_source_language(self) -> str:
        return self.source_language or _source_language(self.document_bundle)

    def to_message(self) -> dict[str, Any]:
        self.validate()
        return {
            "job_id": self.resolved_job_id,
            "work_id": self.resolved_work_id,
            "document_id": self.document_id,
            "source_language": self.resolved_source_language,
            "target_language": self.target_language,
            "provider_id": self.provider_id,
            "tenant_id": self.tenant_id,
            "document_bundle": self.document_bundle,
            "allow_nc_licensed": self.allow_nc_licensed,
            "certified": self.certified,
            "glossary_ids": list(self.glossary_ids or []),
            "instruction_set_id": self.instruction_set_id,
            "metadata": self.metadata,
        }

    def validate(self) -> None:
        if "document_id" not in self.document_bundle:
            raise ValueError("work item document_bundle must include document_id")


TranslationWorkExecutor = Callable[[TranslationWorkItem], dict[str, Any]]
TranslationErrorMapper = Callable[[Exception], dict[str, Any]]


class WorkQueue(Protocol):
    """Execution boundary for local synchronous and future queued backends."""

    def submit(
        self,
        work_item: TranslationWorkItem,
        *,
        repository: JobRepository,
        executor: TranslationWorkExecutor,
        error_mapper: TranslationErrorMapper,
    ) -> TranslationJob: ...


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_language(document_bundle: dict[str, Any]) -> str:
    metadata = document_bundle.get("language_metadata", {})
    if metadata.get("primary_language"):
        return str(metadata["primary_language"])
    for span in document_bundle.get("spans", []):
        if span.get("language"):
            return str(span["language"])
    return "und"


@dataclass
class TranslationJob:
    job_id: str
    status: str
    document_id: str
    target_language: str
    provider_id: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    translation_bundle: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranslationJob":
        return cls(
            job_id=str(payload["job_id"]),
            status=str(payload["status"]),
            document_id=str(payload["document_id"]),
            target_language=str(payload["target_language"]),
            provider_id=str(payload["provider_id"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            completed_at=payload.get("completed_at"),
            translation_bundle=payload.get("translation_bundle"),
            error=payload.get("error"),
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "document_id": self.document_id,
            "target_language": self.target_language,
            "provider_id": self.provider_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "translation_bundle": self.translation_bundle,
            "error": self.error,
            "metadata": self.metadata,
        }

    def status_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "document_id": self.document_id,
            "target_language": self.target_language,
            "provider_id": self.provider_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }
        if self.error is not None:
            payload["error"] = self.error
        if self.translation_bundle is not None:
            payload["translation_bundle_available"] = True
        else:
            payload["translation_bundle_available"] = False
        return payload


class LocalSynchronousWorkQueue:
    """Local adapter that preserves today's immediate in-process job execution."""

    def submit(
        self,
        work_item: TranslationWorkItem,
        *,
        repository: JobRepository,
        executor: TranslationWorkExecutor,
        error_mapper: TranslationErrorMapper,
    ) -> TranslationJob:
        job = repository.create(
            document_id=work_item.document_id,
            target_language=work_item.target_language,
            provider_id=work_item.provider_id,
            metadata=work_item.metadata,
        )
        repository.mark_running(job.job_id)
        try:
            translation_bundle = executor(work_item)
        except Exception as exc:
            return repository.mark_failed(job.job_id, error=error_mapper(exc))
        return repository.mark_succeeded(
            job.job_id,
            translation_bundle=translation_bundle,
        )


class InMemoryTranslationJobRepository:
    """Process-local job store for skeleton and desktop/local deployments."""

    def __init__(self) -> None:
        self._jobs: dict[str, TranslationJob] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        document_id: str,
        target_language: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranslationJob:
        now = utc_now_iso()
        job = TranslationJob(
            job_id=f"trjob_{uuid4().hex}",
            status="queued",
            document_id=document_id,
            target_language=target_language,
            provider_id=provider_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def mark_running(self, job_id: str) -> TranslationJob:
        return self._update(job_id, status="running")

    def mark_succeeded(
        self,
        job_id: str,
        *,
        translation_bundle: dict[str, Any],
    ) -> TranslationJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="succeeded",
            updated_at=now,
            completed_at=now,
            translation_bundle=translation_bundle,
            error=None,
        )

    def mark_failed(self, job_id: str, *, error: dict[str, Any]) -> TranslationJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="failed",
            updated_at=now,
            completed_at=now,
            error=error,
        )

    def get(self, job_id: str) -> TranslationJob:
        with self._lock:
            return self._jobs[job_id]

    def list(self) -> list[TranslationJob]:
        with self._lock:
            return list(self._jobs.values())

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def _update(self, job_id: str, **changes: Any) -> TranslationJob:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            if "updated_at" not in changes:
                job.updated_at = utc_now_iso()
            return job


class FileTranslationJobRepository:
    """Local durable job store using one JSON file per job."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create(
        self,
        *,
        document_id: str,
        target_language: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranslationJob:
        now = utc_now_iso()
        job = TranslationJob(
            job_id=f"trjob_{uuid4().hex}",
            status="queued",
            document_id=document_id,
            target_language=target_language,
            provider_id=provider_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        with self._lock:
            self._write(job)
        return job

    def mark_running(self, job_id: str) -> TranslationJob:
        return self._update(job_id, status="running")

    def mark_succeeded(
        self,
        job_id: str,
        *,
        translation_bundle: dict[str, Any],
    ) -> TranslationJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="succeeded",
            updated_at=now,
            completed_at=now,
            translation_bundle=translation_bundle,
            error=None,
        )

    def mark_failed(self, job_id: str, *, error: dict[str, Any]) -> TranslationJob:
        now = utc_now_iso()
        return self._update(
            job_id,
            status="failed",
            updated_at=now,
            completed_at=now,
            error=error,
        )

    def get(self, job_id: str) -> TranslationJob:
        with self._lock:
            return self._read(job_id)

    def list(self) -> list[TranslationJob]:
        with self._lock:
            return [
                TranslationJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
                for path in sorted(self.root.glob("trjob_*.json"))
            ]

    def clear(self) -> None:
        with self._lock:
            for path in self.root.glob("trjob_*.json"):
                path.unlink()

    def _update(self, job_id: str, **changes: Any) -> TranslationJob:
        with self._lock:
            job = self._read(job_id)
            for key, value in changes.items():
                setattr(job, key, value)
            if "updated_at" not in changes:
                job.updated_at = utc_now_iso()
            self._write(job)
            return job

    def _path(self, job_id: str) -> Path:
        if not job_id.startswith("trjob_") or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for char in job_id.lower()
        ):
            raise KeyError(job_id)
        return self.root / f"{job_id}.json"

    def _read(self, job_id: str) -> TranslationJob:
        path = self._path(job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return TranslationJob.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _write(self, job: TranslationJob) -> None:
        self._path(job.job_id).write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
