"""Postgres schema and SQL adapters for durable translation state.

This module intentionally does not import a Postgres driver. It defines the
schema and parameterized SQL contract that a psycopg/asyncpg adapter can execute,
while keeping local tests dependency-free.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from edc_translation.auth import ApiTokenRecord, AuditEvent, AuditOutcome
from edc_translation.jobs import TranslationWorkItem
from edc_translation.jobs import TranslationJob
from edc_translation.jobs import utc_now_iso
from edc_translation.model_registry import ModelBundleStatus
from edc_translation.stores import ResultRecord
from edc_translation.worker import TranslationWorkerResult

SCHEMA_VERSION = "2026_05_16_001"


POSTGRES_SCHEMA_SQL = f"""
-- EDC_TRANSLATION durable backend schema {SCHEMA_VERSION}
CREATE TABLE IF NOT EXISTS edc_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS translation_jobs (
    job_id text PRIMARY KEY,
    document_id text NOT NULL,
    status text NOT NULL,
    target_language text NOT NULL,
    provider_id text NOT NULL,
    tenant_id text NOT NULL DEFAULT 'standalone',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    error jsonb,
    result_ref text
);

CREATE TABLE IF NOT EXISTS translation_work_queue (
    work_id text PRIMARY KEY,
    job_id text NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued',
    priority integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_by text,
    locked_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    payload jsonb NOT NULL,
    last_error jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_translation_work_queue_claim
    ON translation_work_queue(status, priority DESC, available_at, created_at);

CREATE INDEX IF NOT EXISTS idx_translation_work_queue_job
    ON translation_work_queue(job_id);

CREATE TABLE IF NOT EXISTS translation_results (
    job_id text PRIMARY KEY REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    document_id text NOT NULL,
    status text NOT NULL,
    translation_bundle jsonb,
    result_ref text,
    error jsonb,
    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_id text PRIMARY KEY,
    token_hash text NOT NULL,
    tenant_id text NOT NULL,
    scopes jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_tenant
    ON auth_tokens(tenant_id);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id bigserial PRIMARY KEY,
    event_type text NOT NULL,
    outcome text NOT NULL,
    tenant_id text NOT NULL,
    subject text NOT NULL,
    resource text NOT NULL,
    details jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_created
    ON audit_events(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS model_registry (
    model_id text PRIMARY KEY,
    path text NOT NULL,
    valid boolean NOT NULL,
    approved boolean NOT NULL,
    errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    provenance jsonb,
    engine_family text,
    license text,
    vram_profile text,
    cache_location text,
    quality_evidence_ref text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS current_model_state (
    model_id text PRIMARY KEY REFERENCES model_registry(model_id) ON DELETE CASCADE,
    state text NOT NULL,
    worker_id text,
    model_profile text,
    loaded_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb
);

CREATE TABLE IF NOT EXISTS evidence_bundles (
    job_id text PRIMARY KEY REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    evidence_bundle jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS translation_outbox (
    outbox_id bigserial PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    last_error jsonb
);

CREATE INDEX IF NOT EXISTS idx_translation_outbox_pending
    ON translation_outbox(status, created_at);

CREATE TABLE IF NOT EXISTS translation_dead_letters (
    dead_letter_id bigserial PRIMARY KEY,
    work_id text NOT NULL,
    job_id text NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    payload jsonb NOT NULL,
    error jsonb NOT NULL,
    attempts integer NOT NULL,
    worker_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_translation_dead_letters_job
    ON translation_dead_letters(job_id, created_at);

INSERT INTO edc_schema_migrations (version)
VALUES ('{SCHEMA_VERSION}')
ON CONFLICT (version) DO NOTHING;
""".strip()


INSERT_TRANSLATION_JOB_SQL = """
INSERT INTO translation_jobs (
    job_id, document_id, status, target_language, provider_id, tenant_id, metadata
)
VALUES (
    %(job_id)s,
    %(document_id)s,
    'queued',
    %(target_language)s,
    %(provider_id)s,
    %(tenant_id)s,
    %(metadata)s::jsonb
)
RETURNING job_id, status, document_id, target_language, provider_id,
          created_at, updated_at, completed_at, metadata, error, result_ref;
""".strip()


ENQUEUE_WORK_ITEM_SQL = """
INSERT INTO translation_work_queue (
    work_id, job_id, status, priority, payload
)
VALUES (
    %(work_id)s,
    %(job_id)s,
    'queued',
    %(priority)s,
    %(payload)s::jsonb
)
RETURNING work_id, job_id, payload, attempts;
""".strip()


GET_TRANSLATION_JOB_SQL = """
SELECT job_id, status, document_id, target_language, provider_id,
       created_at, updated_at, completed_at, metadata, error, result_ref
FROM translation_jobs
WHERE job_id = %(job_id)s;
""".strip()


LIST_TRANSLATION_JOBS_SQL = """
SELECT job_id, status, document_id, target_language, provider_id,
       created_at, updated_at, completed_at, metadata, error, result_ref
FROM translation_jobs
ORDER BY created_at, job_id;
""".strip()


MARK_JOB_RUNNING_SQL = """
UPDATE translation_jobs
SET status = 'running',
    updated_at = now()
WHERE job_id = %(job_id)s
RETURNING job_id, status, document_id, target_language, provider_id,
          created_at, updated_at, completed_at, metadata, error, result_ref;
""".strip()


MARK_JOB_SUCCEEDED_SQL = """
UPDATE translation_jobs
SET status = 'succeeded',
    updated_at = now(),
    completed_at = now(),
    error = NULL,
    result_ref = %(result_ref)s
WHERE job_id = %(job_id)s
RETURNING job_id, status, document_id, target_language, provider_id,
          created_at, updated_at, completed_at, metadata, error, result_ref;
""".strip()


MARK_JOB_FAILED_SQL = """
UPDATE translation_jobs
SET status = 'failed',
    updated_at = now(),
    completed_at = now(),
    error = %(error)s::jsonb
WHERE job_id = %(job_id)s
RETURNING job_id, status, document_id, target_language, provider_id,
          created_at, updated_at, completed_at, metadata, error, result_ref;
""".strip()


CLAIM_WORK_SQL = """
WITH next_work AS (
    SELECT work_id
    FROM translation_work_queue
    WHERE (
        status = 'queued'
        AND available_at <= now()
    )
    OR (
        status = 'running'
        AND locked_at < now() - (%(visibility_timeout_seconds)s || ' seconds')::interval
    )
    ORDER BY priority DESC, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE translation_work_queue q
SET status = 'running',
    locked_by = %(worker_id)s,
    locked_at = now(),
    attempts = attempts + 1,
    updated_at = now()
FROM next_work
WHERE q.work_id = next_work.work_id
RETURNING q.work_id, q.job_id, q.payload, q.attempts;
""".strip()


MARK_WORK_SUCCEEDED_SQL = """
UPDATE translation_work_queue
SET status = 'succeeded',
    locked_by = NULL,
    locked_at = NULL,
    updated_at = now()
WHERE work_id = %(work_id)s
  AND locked_by = %(worker_id)s;
""".strip()


MARK_WORK_FAILED_SQL = """
UPDATE translation_work_queue
SET status = CASE
        WHEN attempts >= %(max_attempts)s THEN 'failed'
        ELSE 'queued'
    END,
    available_at = CASE
        WHEN attempts >= %(max_attempts)s THEN now()
        ELSE now() + (%(retry_delay_seconds)s || ' seconds')::interval
    END,
    last_error = %(error)s::jsonb,
    locked_by = NULL,
    locked_at = NULL,
    updated_at = now()
WHERE work_id = %(work_id)s
  AND locked_by = %(worker_id)s
RETURNING status;
""".strip()


SAVE_RESULT_SQL = """
INSERT INTO translation_results (
    job_id, document_id, status, translation_bundle, result_ref, error, metadata
)
VALUES (
    %(job_id)s,
    %(document_id)s,
    %(status)s,
    %(translation_bundle)s::jsonb,
    %(result_ref)s,
    %(error)s::jsonb,
    %(metadata)s::jsonb
)
ON CONFLICT (job_id) DO UPDATE
SET document_id = EXCLUDED.document_id,
    status = EXCLUDED.status,
    translation_bundle = EXCLUDED.translation_bundle,
    result_ref = EXCLUDED.result_ref,
    error = EXCLUDED.error,
    metadata = EXCLUDED.metadata,
    updated_at = now()
RETURNING job_id, document_id, status, result_ref, translation_bundle,
          error, metadata, created_at, updated_at;
""".strip()


GET_RESULT_SQL = """
SELECT job_id, document_id, status, result_ref, translation_bundle,
       error, metadata, created_at, updated_at
FROM translation_results
WHERE job_id = %(job_id)s;
""".strip()


LIST_RESULTS_SQL = """
SELECT job_id, document_id, status, result_ref, translation_bundle,
       error, metadata, created_at, updated_at
FROM translation_results
ORDER BY created_at, job_id;
""".strip()


SAVE_EVIDENCE_BUNDLE_SQL = """
INSERT INTO evidence_bundles (
    job_id, evidence_bundle
)
VALUES (
    %(job_id)s,
    %(evidence_bundle)s::jsonb
)
ON CONFLICT (job_id) DO UPDATE
SET evidence_bundle = EXCLUDED.evidence_bundle
RETURNING job_id, evidence_bundle, created_at;
""".strip()


GET_EVIDENCE_BUNDLE_SQL = """
SELECT job_id, evidence_bundle, created_at
FROM evidence_bundles
WHERE job_id = %(job_id)s;
""".strip()


SAVE_AUDIT_EVENT_SQL = """
INSERT INTO audit_events (
    event_type, outcome, tenant_id, subject, resource, details, created_at
)
VALUES (
    %(event_type)s,
    %(outcome)s,
    %(tenant_id)s,
    %(subject)s,
    %(resource)s,
    %(details)s::jsonb,
    to_timestamp(%(timestamp)s)
);
""".strip()


LIST_AUDIT_EVENTS_SQL = """
SELECT event_type, outcome, tenant_id, subject, resource, details,
       extract(epoch from created_at)::bigint AS timestamp
FROM audit_events
WHERE (%(tenant_id)s::text IS NULL OR tenant_id = %(tenant_id)s)
  AND (%(event_type)s::text IS NULL OR event_type = %(event_type)s)
ORDER BY created_at, audit_id;
""".strip()


SAVE_TOKEN_SQL = """
INSERT INTO auth_tokens (
    token_id, token_hash, tenant_id, scopes, created_by, created_at,
    expires_at, revoked_at, last_used_at
)
VALUES (
    %(token_id)s,
    %(token_hash)s,
    %(tenant_id)s,
    %(scopes)s::jsonb,
    %(created_by)s,
    to_timestamp(%(created_at)s),
    CASE WHEN %(expires_at)s::bigint IS NULL THEN NULL ELSE to_timestamp(%(expires_at)s::bigint) END,
    CASE WHEN %(revoked_at)s::bigint IS NULL THEN NULL ELSE to_timestamp(%(revoked_at)s::bigint) END,
    CASE WHEN %(last_used_at)s::bigint IS NULL THEN NULL ELSE to_timestamp(%(last_used_at)s::bigint) END
)
ON CONFLICT (token_id) DO UPDATE
SET token_hash = EXCLUDED.token_hash,
    tenant_id = EXCLUDED.tenant_id,
    scopes = EXCLUDED.scopes,
    created_by = EXCLUDED.created_by,
    expires_at = EXCLUDED.expires_at,
    revoked_at = EXCLUDED.revoked_at,
    last_used_at = EXCLUDED.last_used_at;
""".strip()


GET_TOKEN_SQL = """
SELECT token_id, token_hash, tenant_id, scopes, created_by,
       extract(epoch from created_at)::bigint AS created_at,
       extract(epoch from expires_at)::bigint AS expires_at,
       extract(epoch from revoked_at)::bigint AS revoked_at,
       extract(epoch from last_used_at)::bigint AS last_used_at
FROM auth_tokens
WHERE token_id = %(token_id)s;
""".strip()


LIST_TOKENS_SQL = """
SELECT token_id, token_hash, tenant_id, scopes, created_by,
       extract(epoch from created_at)::bigint AS created_at,
       extract(epoch from expires_at)::bigint AS expires_at,
       extract(epoch from revoked_at)::bigint AS revoked_at,
       extract(epoch from last_used_at)::bigint AS last_used_at
FROM auth_tokens
WHERE (%(tenant_id)s::text IS NULL OR tenant_id = %(tenant_id)s)
ORDER BY created_at, token_id;
""".strip()


SAVE_MODEL_STATUS_SQL = """
INSERT INTO model_registry (
    model_id, path, valid, approved, errors, provenance, engine_family, license,
    vram_profile, cache_location, quality_evidence_ref, updated_at
)
VALUES (
    %(model_id)s,
    %(path)s,
    %(valid)s,
    %(approved)s,
    %(errors)s::jsonb,
    %(provenance)s::jsonb,
    %(engine_family)s,
    %(license)s,
    %(vram_profile)s,
    %(cache_location)s,
    %(quality_evidence_ref)s,
    now()
)
ON CONFLICT (model_id) DO UPDATE
SET path = EXCLUDED.path,
    valid = EXCLUDED.valid,
    approved = EXCLUDED.approved,
    errors = EXCLUDED.errors,
    provenance = EXCLUDED.provenance,
    engine_family = EXCLUDED.engine_family,
    license = EXCLUDED.license,
    vram_profile = EXCLUDED.vram_profile,
    cache_location = EXCLUDED.cache_location,
    quality_evidence_ref = EXCLUDED.quality_evidence_ref,
    updated_at = now()
RETURNING model_id, path, valid, approved, errors, provenance, engine_family,
          license, vram_profile, cache_location, quality_evidence_ref, updated_at;
""".strip()


GET_MODEL_STATUS_SQL = """
SELECT model_id, path, valid, approved, errors, provenance, engine_family,
       license, vram_profile, cache_location, quality_evidence_ref, updated_at
FROM model_registry
WHERE model_id = %(model_id)s;
""".strip()


LIST_MODEL_STATUSES_SQL = """
SELECT model_id, path, valid, approved, errors, provenance, engine_family,
       license, vram_profile, cache_location, quality_evidence_ref, updated_at
FROM model_registry
ORDER BY model_id;
""".strip()


UPSERT_CURRENT_MODEL_STATE_SQL = """
INSERT INTO current_model_state (
    model_id, state, worker_id, model_profile, loaded_at, metadata
)
VALUES (
    %(model_id)s,
    %(state)s,
    %(worker_id)s,
    %(model_profile)s,
    CASE WHEN %(loaded_at)s IS NULL THEN NULL ELSE to_timestamp(%(loaded_at)s) END,
    %(metadata)s::jsonb
)
ON CONFLICT (model_id) DO UPDATE
SET state = EXCLUDED.state,
    worker_id = EXCLUDED.worker_id,
    model_profile = EXCLUDED.model_profile,
    loaded_at = EXCLUDED.loaded_at,
    metadata = EXCLUDED.metadata,
    updated_at = now();
""".strip()


ENQUEUE_OUTBOX_EVENT_SQL = """
INSERT INTO translation_outbox (
    aggregate_type, aggregate_id, event_type, payload
)
VALUES (
    %(aggregate_type)s,
    %(aggregate_id)s,
    %(event_type)s,
    %(payload)s::jsonb
)
RETURNING outbox_id, aggregate_type, aggregate_id, event_type, payload,
          status, created_at, published_at, last_error;
""".strip()


CLAIM_OUTBOX_EVENTS_SQL = """
UPDATE translation_outbox o
SET status = 'publishing'
WHERE o.outbox_id IN (
    SELECT outbox_id
    FROM translation_outbox
    WHERE status = 'pending'
    ORDER BY created_at, outbox_id
    FOR UPDATE SKIP LOCKED
    LIMIT %(limit)s
)
RETURNING outbox_id, aggregate_type, aggregate_id, event_type, payload,
          status, created_at, published_at, last_error;
""".strip()


MARK_OUTBOX_PUBLISHED_SQL = """
UPDATE translation_outbox
SET status = 'published',
    published_at = now(),
    last_error = NULL
WHERE outbox_id = %(outbox_id)s;
""".strip()


MARK_OUTBOX_FAILED_SQL = """
UPDATE translation_outbox
SET status = CASE
        WHEN %(retry)s THEN 'pending'
        ELSE 'failed'
    END,
    published_at = NULL,
    last_error = %(error)s::jsonb
WHERE outbox_id = %(outbox_id)s;
""".strip()


INSERT_DEAD_LETTER_SQL = """
INSERT INTO translation_dead_letters (
    work_id, job_id, payload, error, attempts, worker_id
)
SELECT
    work_id,
    job_id,
    payload,
    %(error)s::jsonb,
    attempts,
    %(worker_id)s
FROM translation_work_queue
WHERE work_id = %(work_id)s;
""".strip()


@dataclass(frozen=True)
class PostgresQueueSettings:
    worker_id: str
    max_attempts: int = 3
    retry_delay_seconds: int = 30
    visibility_timeout_seconds: int = 900

    def claim_params(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "visibility_timeout_seconds": self.visibility_timeout_seconds,
        }

    def fail_params(self, *, work_id: str, error_json: str) -> dict[str, Any]:
        return {
            "work_id": work_id,
            "error": error_json,
            "worker_id": self.worker_id,
            "max_attempts": self.max_attempts,
            "retry_delay_seconds": self.retry_delay_seconds,
        }


def migration_sql() -> str:
    return POSTGRES_SCHEMA_SQL


def queue_sql_contract() -> dict[str, str]:
    return {
        "enqueue_work_item": ENQUEUE_WORK_ITEM_SQL,
        "claim_work": CLAIM_WORK_SQL,
        "mark_work_succeeded": MARK_WORK_SUCCEEDED_SQL,
        "mark_work_failed": MARK_WORK_FAILED_SQL,
    }


def durable_sql_contract() -> dict[str, str]:
    return {
        "insert_translation_job": INSERT_TRANSLATION_JOB_SQL,
        "get_translation_job": GET_TRANSLATION_JOB_SQL,
        "list_translation_jobs": LIST_TRANSLATION_JOBS_SQL,
        "mark_job_running": MARK_JOB_RUNNING_SQL,
        "mark_job_succeeded": MARK_JOB_SUCCEEDED_SQL,
        "mark_job_failed": MARK_JOB_FAILED_SQL,
        "save_result": SAVE_RESULT_SQL,
        "get_result": GET_RESULT_SQL,
        "list_results": LIST_RESULTS_SQL,
        "save_evidence_bundle": SAVE_EVIDENCE_BUNDLE_SQL,
        "get_evidence_bundle": GET_EVIDENCE_BUNDLE_SQL,
        "save_audit_event": SAVE_AUDIT_EVENT_SQL,
        "list_audit_events": LIST_AUDIT_EVENTS_SQL,
        "save_token": SAVE_TOKEN_SQL,
        "get_token": GET_TOKEN_SQL,
        "list_tokens": LIST_TOKENS_SQL,
        "save_model_status": SAVE_MODEL_STATUS_SQL,
        "get_model_status": GET_MODEL_STATUS_SQL,
        "list_model_statuses": LIST_MODEL_STATUSES_SQL,
        "upsert_current_model_state": UPSERT_CURRENT_MODEL_STATE_SQL,
        "enqueue_outbox_event": ENQUEUE_OUTBOX_EVENT_SQL,
        "claim_outbox_events": CLAIM_OUTBOX_EVENTS_SQL,
        "mark_outbox_published": MARK_OUTBOX_PUBLISHED_SQL,
        "mark_outbox_failed": MARK_OUTBOX_FAILED_SQL,
        "insert_dead_letter": INSERT_DEAD_LETTER_SQL,
    }


class DbCursor(Protocol):
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class DbConnection(Protocol):
    def cursor(self) -> DbCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class PostgresMigrationRunner:
    """Driver-neutral schema migration runner for DB-API compatible clients."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def apply(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(migration_sql())
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()


class PostgresJobRepository:
    """Driver-neutral durable job ledger adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        document_id: str,
        target_language: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranslationJob:
        metadata = metadata or {}
        params = {
            "job_id": str(metadata.get("job_id") or f"trjob_{uuid4().hex}"),
            "document_id": document_id,
            "target_language": target_language,
            "provider_id": provider_id,
            "tenant_id": str(metadata.get("tenant_id") or "standalone"),
            "metadata": _json_param(metadata),
        }
        return _execute_one_job(self.connection, INSERT_TRANSLATION_JOB_SQL, params)

    def mark_running(self, job_id: str) -> TranslationJob:
        return _execute_one_job(
            self.connection,
            MARK_JOB_RUNNING_SQL,
            {"job_id": job_id},
        )

    def mark_succeeded(
        self,
        job_id: str,
        *,
        translation_bundle: dict[str, Any],
    ) -> TranslationJob:
        result_ref = f"translation_results:{job_id}"
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SAVE_RESULT_SQL,
                {
                    "job_id": job_id,
                    "document_id": str(translation_bundle.get("document_id") or job_id),
                    "status": "succeeded",
                    "translation_bundle": _json_param(translation_bundle),
                    "result_ref": result_ref,
                    "error": _json_param(None),
                    "metadata": _json_param({"source": "postgres_job_repository"}),
                },
            )
            cursor.execute(
                MARK_JOB_SUCCEEDED_SQL,
                {"job_id": job_id, "result_ref": result_ref},
            )
            row = cursor.fetchone()
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        if row is None:
            raise KeyError({"job_id": job_id})
        job = _job_from_row(row)
        job.translation_bundle = dict(translation_bundle)
        return job

    def mark_failed(self, job_id: str, *, error: dict[str, Any]) -> TranslationJob:
        return _execute_one_job(
            self.connection,
            MARK_JOB_FAILED_SQL,
            {"job_id": job_id, "error": _json_param(error)},
        )

    def get(self, job_id: str) -> TranslationJob:
        return _execute_one_job(
            self.connection,
            GET_TRANSLATION_JOB_SQL,
            {"job_id": job_id},
        )

    def list(self) -> list[TranslationJob]:
        rows = _execute_all(self.connection, LIST_TRANSLATION_JOBS_SQL, {})
        return [_job_from_row(row) for row in rows]

    def clear(self) -> None:
        raise NotImplementedError("PostgresJobRepository.clear is intentionally absent")


class PostgresSubmitWorkQueue:
    """Durable submit adapter that queues work without executing it in-process."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def submit(
        self,
        work_item: TranslationWorkItem,
        *,
        repository: Any,
        executor: Any,
        error_mapper: Any,
    ) -> TranslationJob:
        del repository, executor, error_mapper
        metadata = dict(work_item.metadata)
        metadata.setdefault("job_id", work_item.resolved_job_id)
        metadata.setdefault("tenant_id", work_item.tenant_id)
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                INSERT_TRANSLATION_JOB_SQL,
                {
                    "job_id": work_item.resolved_job_id,
                    "document_id": work_item.document_id,
                    "target_language": work_item.target_language,
                    "provider_id": work_item.provider_id,
                    "tenant_id": work_item.tenant_id,
                    "metadata": _json_param(metadata),
                },
            )
            row = cursor.fetchone()
            cursor.execute(
                ENQUEUE_WORK_ITEM_SQL,
                {
                    "work_id": work_item.resolved_work_id,
                    "job_id": work_item.resolved_job_id,
                    "priority": int(metadata.get("priority", 0) or 0),
                    "payload": _json_param(work_item.to_message()),
                },
            )
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        if row is None:
            raise KeyError({"job_id": work_item.resolved_job_id})
        return _job_from_row(row)


class PostgresResultStore:
    """Driver-neutral result store adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def save(self, record: ResultRecord) -> ResultRecord:
        params = {
            "job_id": record.job_id,
            "document_id": record.document_id,
            "status": record.status,
            "translation_bundle": _json_param(record.translation_bundle),
            "result_ref": record.result_ref,
            "error": _json_param(record.error),
            "metadata": _json_param(record.metadata),
        }
        return _result_from_row(
            _execute_one(self.connection, SAVE_RESULT_SQL, params)
        )

    def get(self, job_id: str) -> ResultRecord:
        return _result_from_row(
            _execute_one(self.connection, GET_RESULT_SQL, {"job_id": job_id})
        )

    def list(self) -> list[ResultRecord]:
        rows = _execute_all(self.connection, LIST_RESULTS_SQL, {})
        return [_result_from_row(row) for row in rows]


class PostgresEvidenceStore:
    """Driver-neutral evidence bundle adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def save(self, job_id: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        row = _execute_one(
            self.connection,
            SAVE_EVIDENCE_BUNDLE_SQL,
            {
                "job_id": job_id,
                "evidence_bundle": _json_param(evidence_bundle),
            },
        )
        return _evidence_bundle_from_row(row)

    def get(self, job_id: str) -> dict[str, Any]:
        row = _execute_one(
            self.connection,
            GET_EVIDENCE_BUNDLE_SQL,
            {"job_id": job_id},
        )
        return _evidence_bundle_from_row(row)


class PostgresAuditStore:
    """Driver-neutral audit event adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def record(self, event: AuditEvent) -> AuditEvent:
        _execute_none(
            self.connection,
            SAVE_AUDIT_EVENT_SQL,
            {
                "event_type": event.event_type,
                "outcome": event.outcome.value,
                "tenant_id": event.tenant_id,
                "subject": event.subject,
                "resource": event.resource,
                "timestamp": event.timestamp,
                "details": _json_param(event.details),
            },
        )
        return event

    def list_events(
        self,
        *,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditEvent]:
        rows = _execute_all(
            self.connection,
            LIST_AUDIT_EVENTS_SQL,
            {"tenant_id": tenant_id, "event_type": event_type},
        )
        return [_audit_event_from_row(row) for row in rows]


class PostgresTokenStore:
    """Driver-neutral API token metadata adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def save(self, record: ApiTokenRecord) -> ApiTokenRecord:
        _execute_none(self.connection, SAVE_TOKEN_SQL, _token_params(record))
        return record

    def list(self, *, tenant_id: str | None = None) -> list[ApiTokenRecord]:
        rows = _execute_all(self.connection, LIST_TOKENS_SQL, {"tenant_id": tenant_id})
        return [_token_from_row(row) for row in rows]

    def get(self, token_id: str) -> ApiTokenRecord:
        return _token_from_row(
            _execute_one(self.connection, GET_TOKEN_SQL, {"token_id": token_id})
        )


class PostgresModelRegistryStore:
    """Driver-neutral model registry adapter."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def save(self, status: ModelBundleStatus) -> ModelBundleStatus:
        return _model_status_from_row(
            _execute_one(
                self.connection,
                SAVE_MODEL_STATUS_SQL,
                _model_status_params(status),
            )
        )

    def list(self) -> list[ModelBundleStatus]:
        rows = _execute_all(self.connection, LIST_MODEL_STATUSES_SQL, {})
        return [_model_status_from_row(row) for row in rows]

    def get(self, model_id: str) -> ModelBundleStatus:
        return _model_status_from_row(
            _execute_one(
                self.connection,
                GET_MODEL_STATUS_SQL,
                {"model_id": model_id},
            )
        )

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
        _execute_none(
            self.connection,
            UPSERT_CURRENT_MODEL_STATE_SQL,
            {
                "model_id": model_id,
                "state": state,
                "worker_id": worker_id,
                "model_profile": model_profile,
                "loaded_at": loaded_at,
                "metadata": _json_param(metadata or {}),
            },
        )


class PostgresOutbox:
    """Driver-neutral transactional outbox adapter for Kafka publishing."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    def enqueue(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = _execute_one(
            self.connection,
            ENQUEUE_OUTBOX_EVENT_SQL,
            {
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": _json_param(payload),
            },
        )
        return _outbox_event_from_row(row)

    def claim(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = _execute_all(
            self.connection,
            CLAIM_OUTBOX_EVENTS_SQL,
            {"limit": int(limit)},
        )
        return [_outbox_event_from_row(row) for row in rows]

    def mark_published(self, outbox_id: int) -> None:
        _execute_none(
            self.connection,
            MARK_OUTBOX_PUBLISHED_SQL,
            {"outbox_id": int(outbox_id)},
        )

    def mark_failed(
        self,
        outbox_id: int,
        *,
        error: dict[str, Any],
        retry: bool = True,
    ) -> None:
        _execute_none(
            self.connection,
            MARK_OUTBOX_FAILED_SQL,
            {
                "outbox_id": int(outbox_id),
                "error": _json_param(error),
                "retry": bool(retry),
            },
        )


class PostgresWorkQueue:
    """Postgres queue adapter for single-GPU durable worker consumption.

    The adapter is intentionally driver-neutral. A production deployment can
    pass a psycopg-style connection without this package depending on a driver
    during local tests.
    """

    def __init__(
        self,
        connection: DbConnection,
        *,
        settings: PostgresQueueSettings,
    ) -> None:
        self.connection = connection
        self.settings = settings

    def poll(self) -> TranslationWorkItem | None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(CLAIM_WORK_SQL, self.settings.claim_params())
            row = cursor.fetchone()
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        if row is None:
            return None
        return TranslationWorkItem.from_message(_payload_from_row(row))

    def ack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        if result.translation_bundle is None:
            raise ValueError("successful worker result must include translation_bundle")
        result_ref = f"translation_results:{item.resolved_job_id}"
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SAVE_RESULT_SQL,
                {
                    "job_id": item.resolved_job_id,
                    "document_id": item.document_id,
                    "status": "succeeded",
                    "translation_bundle": _json_param(result.translation_bundle),
                    "result_ref": result_ref,
                    "error": _json_param(None),
                    "metadata": _json_param(result.metadata),
                },
            )
            cursor.execute(
                MARK_JOB_SUCCEEDED_SQL,
                {"job_id": item.resolved_job_id, "result_ref": result_ref},
            )
            cursor.execute(
                MARK_WORK_SUCCEEDED_SQL,
                {
                    "work_id": item.resolved_work_id,
                    "worker_id": self.settings.worker_id,
                },
            )
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()

    def nack(self, item: TranslationWorkItem, result: TranslationWorkerResult) -> None:
        error_json = json.dumps(result.error or {}, ensure_ascii=False)
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                MARK_WORK_FAILED_SQL,
                self.settings.fail_params(
                    work_id=item.resolved_work_id,
                    error_json=error_json,
                ),
            )
            row = cursor.fetchone()
            status = row.get("status") if isinstance(row, dict) else row[0] if row else None
            if status == "failed":
                cursor.execute(
                    INSERT_DEAD_LETTER_SQL,
                    {
                        "work_id": item.resolved_work_id,
                        "error": error_json,
                        "worker_id": self.settings.worker_id,
                    },
                )
                cursor.execute(
                    MARK_JOB_FAILED_SQL,
                    {"job_id": item.resolved_job_id, "error": error_json},
                )
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()


def _payload_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        payload = row["payload"]
    else:
        payload = row[2]
    if isinstance(payload, str):
        return dict(json.loads(payload))
    return dict(payload)


def _execute_none(
    connection: DbConnection,
    sql: str,
    params: dict[str, Any],
) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
    except Exception:
        connection.rollback()
        raise
    connection.commit()


def _execute_one(
    connection: DbConnection,
    sql: str,
    params: dict[str, Any],
) -> Any:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    except Exception:
        connection.rollback()
        raise
    connection.commit()
    if row is None:
        raise KeyError(params)
    return row


def _execute_all(
    connection: DbConnection,
    sql: str,
    params: dict[str, Any],
) -> list[Any]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    except Exception:
        connection.rollback()
        raise
    connection.commit()
    return list(rows)


def _execute_one_job(
    connection: DbConnection,
    sql: str,
    params: dict[str, Any],
) -> TranslationJob:
    return _job_from_row(_execute_one(connection, sql, params))


def _json_param(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return _row_to_dict_with_keys(
        row,
        (
            "job_id",
            "status",
            "document_id",
            "target_language",
            "provider_id",
            "created_at",
            "updated_at",
            "completed_at",
            "metadata",
            "error",
            "result_ref",
        ),
    )


def _row_to_dict_with_keys(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {key: row[index] for index, key in enumerate(keys[: len(row)])}


def _job_from_row(row: Any) -> TranslationJob:
    payload = _row_to_dict_with_keys(
        row,
        (
            "job_id",
            "status",
            "document_id",
            "target_language",
            "provider_id",
            "created_at",
            "updated_at",
            "completed_at",
            "metadata",
            "error",
            "result_ref",
        ),
    )
    metadata = _decode_json_field(payload.get("metadata"), {})
    error = _decode_json_field(payload.get("error"), None)
    return TranslationJob(
        job_id=str(payload["job_id"]),
        status=str(payload["status"]),
        document_id=str(payload["document_id"]),
        target_language=str(payload["target_language"]),
        provider_id=str(payload["provider_id"]),
        created_at=str(payload.get("created_at") or utc_now_iso()),
        updated_at=str(payload.get("updated_at") or utc_now_iso()),
        completed_at=(
            None
            if payload.get("completed_at") is None
            else str(payload.get("completed_at"))
        ),
        error=error,
        metadata=dict(metadata),
    )


def _result_from_row(row: Any) -> ResultRecord:
    payload = _row_to_dict_with_keys(
        row,
        (
            "job_id",
            "document_id",
            "status",
            "result_ref",
            "translation_bundle",
            "error",
            "metadata",
            "created_at",
            "updated_at",
        ),
    )
    return ResultRecord(
        job_id=str(payload["job_id"]),
        document_id=str(payload["document_id"]),
        status=str(payload["status"]),
        result_ref=payload.get("result_ref"),
        translation_bundle=_decode_json_field(payload.get("translation_bundle"), None),
        error=_decode_json_field(payload.get("error"), None),
        metadata=dict(_decode_json_field(payload.get("metadata"), {})),
        created_at=str(payload.get("created_at") or utc_now_iso()),
        updated_at=str(payload.get("updated_at") or utc_now_iso()),
    )


def _evidence_bundle_from_row(row: Any) -> dict[str, Any]:
    payload = _row_to_dict_with_keys(
        row,
        (
            "job_id",
            "evidence_bundle",
            "created_at",
        ),
    )
    return dict(_decode_json_field(payload.get("evidence_bundle"), {}))


def _audit_event_from_row(row: Any) -> AuditEvent:
    payload = _row_to_dict_with_keys(
        row,
        (
            "event_type",
            "outcome",
            "tenant_id",
            "subject",
            "resource",
            "details",
            "timestamp",
        ),
    )
    return AuditEvent(
        event_type=str(payload["event_type"]),
        outcome=AuditOutcome(str(payload["outcome"])),
        tenant_id=str(payload["tenant_id"]),
        subject=str(payload["subject"]),
        resource=str(payload["resource"]),
        timestamp=int(payload["timestamp"]),
        details=dict(_decode_json_field(payload.get("details"), {})),
    )


def _token_from_row(row: Any) -> ApiTokenRecord:
    payload = _row_to_dict_with_keys(
        row,
        (
            "token_id",
            "token_hash",
            "tenant_id",
            "scopes",
            "created_by",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
        ),
    )
    return ApiTokenRecord(
        token_id=str(payload["token_id"]),
        token_hash=str(payload["token_hash"]),
        tenant_id=str(payload["tenant_id"]),
        scopes=frozenset(
            str(scope) for scope in _decode_json_field(payload["scopes"], [])
        ),
        created_by=str(payload["created_by"]),
        created_at=int(payload["created_at"]),
        expires_at=_optional_int(payload.get("expires_at")),
        revoked_at=_optional_int(payload.get("revoked_at")),
        last_used_at=_optional_int(payload.get("last_used_at")),
    )


def _model_status_from_row(row: Any) -> ModelBundleStatus:
    payload = _row_to_dict_with_keys(
        row,
        (
            "model_id",
            "path",
            "valid",
            "approved",
            "errors",
            "provenance",
            "engine_family",
            "license",
            "vram_profile",
            "cache_location",
            "quality_evidence_ref",
            "updated_at",
        ),
    )
    payload["errors"] = _decode_json_field(payload.get("errors"), [])
    payload["provenance"] = _decode_json_field(payload.get("provenance"), None)
    return ModelBundleStatus.from_dict(payload)


def _outbox_event_from_row(row: Any) -> dict[str, Any]:
    payload = _row_to_dict_with_keys(
        row,
        (
            "outbox_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
            "status",
            "created_at",
            "published_at",
            "last_error",
        ),
    )
    payload["payload"] = _decode_json_field(payload.get("payload"), {})
    payload["last_error"] = _decode_json_field(payload.get("last_error"), None)
    return payload


def _decode_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _token_params(record: ApiTokenRecord) -> dict[str, Any]:
    return {
        "token_id": record.token_id,
        "token_hash": record.token_hash,
        "tenant_id": record.tenant_id,
        "scopes": _json_param(sorted(record.scopes)),
        "created_by": record.created_by,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "revoked_at": record.revoked_at,
        "last_used_at": record.last_used_at,
    }


def _model_status_params(status: ModelBundleStatus) -> dict[str, Any]:
    return {
        "model_id": status.model_id,
        "path": status.path,
        "valid": status.valid,
        "approved": status.approved,
        "errors": _json_param(status.errors),
        "provenance": _json_param(status.provenance),
        "engine_family": status.engine_family,
        "license": status.license,
        "vram_profile": status.vram_profile,
        "cache_location": status.cache_location,
        "quality_evidence_ref": status.quality_evidence_ref,
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


# --- Live Postgres driver wiring (psycopg) and factories ---
# The adapter classes above are driver-neutral. The code below supplies real
# connections, the documented DSN default, idempotent schema application, and
# one-line factories for service wiring and integration tests.

try:
    import psycopg  # type: ignore[import-not-found]
    from psycopg.rows import dict_row  # type: ignore[import-not-found]
    HAS_PSYCOPG = True
except ImportError:  # pragma: no cover - exercised only when extra not installed
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    HAS_PSYCOPG = False

POSTGRES_DSN_ENV_VAR: str = "EDC_TRANSLATION_POSTGRES_DSN"
DEFAULT_POSTGRES_DSN: str = "postgresql://postgres:postgres@127.0.0.1:15432/edc_translation"


def get_postgres_dsn() -> str:
    """DSN from env (for prod/compose) or the test default matching docker-compose.local + task spec."""
    return os.environ.get(POSTGRES_DSN_ENV_VAR, DEFAULT_POSTGRES_DSN)


def connect(
    dsn: str | None = None,
    *,
    autocommit: bool = False,
    **kwargs: Any,
) -> Any:
    """Return psycopg connection wired for the DbCursor/DbConnection protocols + dict rows.

    Adapters perform their own commit/rollback; we keep autocommit off by default.
    """
    if not HAS_PSYCOPG:
        raise RuntimeError(
            "psycopg[binary]>=3.2 required for Postgres backend. "
            f"pip install '.[postgres]' and ensure {POSTGRES_DSN_ENV_VAR} or the default test DB is reachable."
        )
    target_dsn = dsn or get_postgres_dsn()
    conn = psycopg.connect(target_dsn, row_factory=dict_row, **kwargs)
    conn.autocommit = bool(autocommit)
    return conn


def ensure_schema(connection: DbConnection) -> None:
    """Run the embedded schema (CREATE IF NOT EXISTS + migration log row). Safe to call repeatedly."""
    PostgresMigrationRunner(connection).apply()


# One-call factories for the durable path (connect + migrate + adapter). These turn the
# contract into immediately usable objects for service.py, worker, CLI, and tests.
def make_postgres_job_repository(dsn: str | None = None) -> PostgresJobRepository:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresJobRepository(conn)


def make_postgres_submit_work_queue(dsn: str | None = None) -> PostgresSubmitWorkQueue:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresSubmitWorkQueue(conn)


def make_postgres_work_queue(
    dsn: str | None = None,
    *,
    worker_id: str = "default-worker",
    max_attempts: int = 3,
    retry_delay_seconds: int = 30,
    visibility_timeout_seconds: int = 900,
) -> PostgresWorkQueue:
    conn = connect(dsn)
    ensure_schema(conn)
    settings = PostgresQueueSettings(
        worker_id=worker_id,
        max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds,
        visibility_timeout_seconds=visibility_timeout_seconds,
    )
    return PostgresWorkQueue(conn, settings=settings)


def make_postgres_result_store(dsn: str | None = None) -> PostgresResultStore:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresResultStore(conn)


def make_postgres_audit_store(dsn: str | None = None) -> PostgresAuditStore:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresAuditStore(conn)


def make_postgres_token_store(dsn: str | None = None) -> PostgresTokenStore:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresTokenStore(conn)


def make_postgres_evidence_store(dsn: str | None = None) -> PostgresEvidenceStore:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresEvidenceStore(conn)


def make_postgres_model_registry_store(
    dsn: str | None = None,
) -> PostgresModelRegistryStore:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresModelRegistryStore(conn)


def make_postgres_outbox(dsn: str | None = None) -> PostgresOutbox:
    conn = connect(dsn)
    ensure_schema(conn)
    return PostgresOutbox(conn)


# Production note: replace the single-conn factories with a psycopg_pool.ConnectionPool
# holder that yields connections to the same adapter classes (they only need the protocol).
