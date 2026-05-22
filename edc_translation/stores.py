"""Store boundaries for local and durable EDC_TRANSLATION backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Protocol

from edc_translation.auth import ApiTokenRecord, AuditEvent
from edc_translation.jobs import utc_now_iso
from edc_translation.model_registry import ModelBundleStatus


@dataclass(frozen=True)
class ResultRecord:
    job_id: str
    document_id: str
    status: str
    result_ref: str | None = None
    translation_bundle: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResultStore(Protocol):
    def save(self, record: ResultRecord) -> ResultRecord: ...

    def get(self, job_id: str) -> ResultRecord: ...

    def list(self) -> list[ResultRecord]: ...


class AuditStore(Protocol):
    def record(self, event: AuditEvent) -> AuditEvent: ...

    def list_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]: ...


class TokenStore(Protocol):
    def save(self, record: ApiTokenRecord) -> ApiTokenRecord: ...

    def list(self, *, tenant_id: str | None = None) -> list[ApiTokenRecord]: ...

    def get(self, token_id: str) -> ApiTokenRecord: ...


class ModelRegistryStore(Protocol):
    def save(self, status: ModelBundleStatus) -> ModelBundleStatus: ...

    def list(self) -> list[ModelBundleStatus]: ...

    def get(self, model_id: str) -> ModelBundleStatus: ...

    def upsert_current_state(
        self,
        *,
        model_id: str,
        state: str,
        worker_id: str | None = None,
        model_profile: str | None = None,
        loaded_at: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class EvidenceStore(Protocol):
    def save(self, job_id: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]: ...

    def get(self, job_id: str) -> dict[str, Any]: ...


class InMemoryResultStore:
    def __init__(self) -> None:
        self._records: dict[str, ResultRecord] = {}
        self._lock = Lock()

    def save(self, record: ResultRecord) -> ResultRecord:
        with self._lock:
            self._records[record.job_id] = record
        return record

    def get(self, job_id: str) -> ResultRecord:
        with self._lock:
            return self._records[job_id]

    def list(self) -> list[ResultRecord]:
        with self._lock:
            return list(self._records.values())


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    def record(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]:
        with self._lock:
            events = list(self._events)
        if tenant_id is not None:
            events = [event for event in events if event.tenant_id == tenant_id]
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        return events


class InMemoryTokenStore:
    def __init__(self) -> None:
        self._records: dict[str, ApiTokenRecord] = {}
        self._lock = Lock()

    def save(self, record: ApiTokenRecord) -> ApiTokenRecord:
        with self._lock:
            self._records[record.token_id] = record
        return record

    def list(self, *, tenant_id: str | None = None) -> list[ApiTokenRecord]:
        with self._lock:
            records = list(self._records.values())
        if tenant_id is None:
            return records
        return [record for record in records if record.tenant_id == tenant_id]

    def get(self, token_id: str) -> ApiTokenRecord:
        with self._lock:
            return self._records[token_id]


class InMemoryModelRegistryStore:
    def __init__(self) -> None:
        self._statuses: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def save(self, status: ModelBundleStatus) -> ModelBundleStatus:
        payload = status.to_dict()
        with self._lock:
            self._statuses[status.model_id] = payload
        return ModelBundleStatus.from_dict(payload)

    def list(self) -> list[ModelBundleStatus]:
        with self._lock:
            statuses = list(self._statuses.values())
        return [ModelBundleStatus.from_dict(status) for status in statuses]

    def get(self, model_id: str) -> ModelBundleStatus:
        with self._lock:
            status = self._statuses[model_id]
        return ModelBundleStatus.from_dict(status)

    def upsert_current_state(
        self,
        *,
        model_id: str,
        state: str,
        worker_id: str | None = None,
        model_profile: str | None = None,
        loaded_at: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        # Local in-memory: prewarm/current-state tracking is advisory only.
        # (Durable tracking lives in the Postgres current_model_state table.)
        pass


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._bundles: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def save(self, job_id: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._bundles[job_id] = evidence_bundle
        return evidence_bundle

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._bundles[job_id]
