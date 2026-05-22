"""Translation service layer for DocumentBundle v1 inputs."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from edc_translation.contracts import (
    DOCUMENT_BUNDLE_SCHEMA,
    TRANSLATION_BUNDLE_SCHEMA,
    canonical_json_sha256,
    validate_payload,
)
from edc_translation.release_readiness import release_readiness_lane_status
from edc_translation.custody import (
    evidence_bundle_for_job,
    validate_translation_custody,
)
from edc_translation.engines import get_engine, iter_engines
from edc_translation.engines.metadata import (
    engine_list_entry,
    engine_model_provenance,
    engine_provider_payload,
    quality_scores_payload,
)
from edc_translation.errors import auto_route_error_payload
from edc_translation.governance import (
    DEFAULT_TENANT_ID,
    Glossary,
    GlossaryRepository,
    InstructionSet,
    InstructionSetRepository,
    TenantPolicyRepository,
    find_glossary_hits,
)
from edc_translation.language_id import LanguageDetection, detect_language
from edc_translation.jobs import (
    FileTranslationJobRepository,
    InMemoryTranslationJobRepository,
    JobRepository,
    LocalSynchronousWorkQueue,
    TranslationWorkItem,
    WorkQueue,
)
from edc_translation.llm_live import (
    discover_env_variable_names,
    local_runtime_readiness as llm_local_runtime_readiness,
    rank_local_models,
    smoke_provider,
)
from edc_translation.model_registry import ModelRegistry
from edc_translation.models import SpanTranslation, TranslationRequest
from edc_translation.quality import score_translation_pair
from edc_translation.review import ReviewRepository
from edc_translation.routing import (
    EngineRoutingPolicy,
    RoutingError,
    diagnose_auto_route,
    resolve_provider_id,
)
from edc_translation.stores import (
    AuditStore,
    InMemoryAuditStore,
    InMemoryModelRegistryStore,
    InMemoryTokenStore,
    ModelRegistryStore,
    TokenStore,
)
from edc_translation.text_batch import (
    TextFileBatchRepository,
    format_batch_log,
    save_batch_log,
    submit_text_file_batch_job as submit_text_file_batch_job_to_repository,
)


def _default_job_repository() -> InMemoryTranslationJobRepository | FileTranslationJobRepository:
    job_store_dir = os.environ.get("EDC_TRANSLATION_JOB_STORE_DIR")
    if job_store_dir:
        return FileTranslationJobRepository(job_store_dir)
    return InMemoryTranslationJobRepository()


def _job_backend() -> str:
    """'postgres' enables durable PostgresJobRepository + PostgresSubmitWorkQueue via env; else local."""
    return os.environ.get("EDC_TRANSLATION_JOB_BACKEND", "local").strip().lower()


def _queue_backend() -> str:
    """Queue backend for work distribution/fanout.

    'kafka' enables KafkaWorkQueue (producer/consumer to jobs/segments/results topics, Redpanda/Strimzi ready)
    alongside Postgres (or local) for job repository/state. Falls back to _job_backend() for compatibility.
    """
    qenv = os.environ.get("EDC_TRANSLATION_QUEUE_BACKEND", "").strip().lower()
    if qenv in ("kafka", "postgres", "local"):
        return qenv
    jb = _job_backend()
    return jb if jb in ("postgres", "kafka") else "local"


def _build_job_repository() -> JobRepository:
    if _job_backend() == "postgres":
        from .postgres_backend import make_postgres_job_repository

        return make_postgres_job_repository()
    return _default_job_repository()


def _build_work_queue() -> WorkQueue:
    qb = _queue_backend()
    if qb == "kafka":
        from .kafka_backend import make_kafka_work_queue

        return make_kafka_work_queue()
    if qb == "postgres":
        from .postgres_backend import make_postgres_submit_work_queue

        return make_postgres_submit_work_queue()
    return LocalSynchronousWorkQueue()


def _auth_store_backend() -> str:
    """'postgres' enables durable Postgres*Store for Token/Audit; 'json' uses JsonTokenAuditStore when EDC_TOKEN_AUDIT_STORE_PATH set; else in-memory."""
    return os.environ.get("EDC_TRANSLATION_AUTH_STORE_BACKEND", "json").strip().lower()


def _build_token_store() -> TokenStore:
    backend = _auth_store_backend()
    if backend == "postgres":
        from .postgres_backend import make_postgres_token_store

        return make_postgres_token_store()
    if backend == "json":
        store_path = os.getenv("EDC_TOKEN_AUDIT_STORE_PATH", "").strip()
        if store_path:
            from .auth import JsonTokenAuditStore

            return JsonTokenAuditStore(store_path)
    return InMemoryTokenStore()


def _build_audit_store() -> AuditStore:
    backend = _auth_store_backend()
    if backend == "postgres":
        from .postgres_backend import make_postgres_audit_store

        return make_postgres_audit_store()
    if backend == "json":
        store_path = os.getenv("EDC_TOKEN_AUDIT_STORE_PATH", "").strip()
        if store_path:
            from .auth import JsonTokenAuditStore

            return JsonTokenAuditStore(store_path)
    return InMemoryAuditStore()


def _model_registry_backend() -> str:
    """'postgres' enables PostgresModelRegistryStore + current state tracking; else 'local' InMemory.
    When JOB_BACKEND=postgres, default model registry to postgres too (consistent durable path).
    """
    env = os.environ.get("EDC_TRANSLATION_MODEL_REGISTRY_BACKEND", "").strip().lower()
    if env in {"postgres", "local"}:
        return env
    if _job_backend() == "postgres":
        return "postgres"
    return "local"


def make_model_registry_store(backend: str | None = None) -> ModelRegistryStore:
    """Public factory returning a ModelRegistryStore (in-memory or Postgres-backed).
    Used by service surfaces, worker prewarm, CLI/MCP wiring, and tests.
    """
    if backend is None:
        backend = _model_registry_backend()
    if backend == "postgres":
        from .postgres_backend import make_postgres_model_registry_store

        return make_postgres_model_registry_store()
    return InMemoryModelRegistryStore()


DEFAULT_JOB_REPOSITORY: JobRepository = _build_job_repository()
DEFAULT_WORK_QUEUE: WorkQueue = _build_work_queue()
DEFAULT_POLICY_REPOSITORY = TenantPolicyRepository()
DEFAULT_GLOSSARY_REPOSITORY = GlossaryRepository()
DEFAULT_INSTRUCTION_REPOSITORY = InstructionSetRepository()
DEFAULT_MODEL_REGISTRY = ModelRegistry()  # legacy validator (used transiently for bundle validation logic)
DEFAULT_MODEL_REGISTRY_STORE: ModelRegistryStore = make_model_registry_store()
DEFAULT_REVIEW_REPOSITORY = ReviewRepository()
DEFAULT_TEXT_FILE_BATCH_REPOSITORY = TextFileBatchRepository()

DEFAULT_TOKEN_STORE: TokenStore = _build_token_store()
DEFAULT_AUDIT_STORE: AuditStore = _build_audit_store()


def translate_document_bundle(
    document_bundle: dict[str, Any],
    *,
    target_language: str,
    provider_id: str = "passthrough",
    allow_nc_licensed: bool = False,
    certified: bool = False,
    tenant_id: str = DEFAULT_TENANT_ID,
    glossary_ids: list[str] | None = None,
    instruction_set_id: str | None = None,
    policy_repository: TenantPolicyRepository = DEFAULT_POLICY_REPOSITORY,
    glossary_repository: GlossaryRepository = DEFAULT_GLOSSARY_REPOSITORY,
    instruction_repository: InstructionSetRepository = DEFAULT_INSTRUCTION_REPOSITORY,
) -> dict[str, Any]:
    """Translate a validated DocumentBundle and emit TranslationBundle v1."""

    validate_payload(document_bundle, DOCUMENT_BUNDLE_SCHEMA)
    source_language = _source_language(document_bundle)
    policy = policy_repository.get(tenant_id)
    effective_allow_nc = bool(allow_nc_licensed or policy.allow_nc_licensed)
    effective_provider_id = provider_id
    if effective_provider_id == "tenant_default":
        effective_provider_id = policy.default_provider_id
    selected_instruction_set_id = (
        instruction_set_id or policy.approved_instruction_set_ids[0]
    )
    instruction_set = instruction_repository.get(selected_instruction_set_id)
    active_glossaries = _resolve_glossaries(
        glossary_ids if glossary_ids is not None else policy.glossary_ids,
        glossary_repository,
        source_language=source_language,
        target_language=target_language,
    )
    request = TranslationRequest(
        src_lang=source_language,
        tgt_lang=target_language,
        tenant_id=tenant_id,
    )
    resolved_provider_id = resolve_provider_id(
        effective_provider_id,
        request,
        policy=EngineRoutingPolicy(allow_nc_licensed=effective_allow_nc),
    )
    engine = get_engine(resolved_provider_id)()
    _validate_policy_allows_engine(engine, policy.to_dict(), instruction_set)
    capability = engine.capability
    source_bundle_sha256 = canonical_json_sha256(document_bundle)

    source_spans = _source_spans_for_engine(document_bundle)
    translated = engine.translate_spans(
        source_spans,
        request.src_lang,
        request.tgt_lang,
        glossary=[glossary.to_dict() for glossary in active_glossaries],
    )
    translated_spans = _translated_spans(translated, source_spans)
    glossary_hits = _apply_glossary_hits(translated_spans, active_glossaries)

    translation_bundle = {
        "schema_version": TRANSLATION_BUNDLE_SCHEMA,
        "document_id": document_bundle["document_id"],
        "source_ocr_sha256": document_bundle["source_ocr_sha256"],
        "source_bundle_sha256": source_bundle_sha256,
        "target_language": target_language,
        "translated_spans": translated_spans,
        "engine_provider": engine_provider_payload(engine),
        "model_provenance": engine_model_provenance(engine),
        "quality_scores": quality_scores_payload(
            translated_spans,
            quality_class=capability.quality_class,
        ),
        "certified": certified,
        "custody_chain_head": document_bundle["custody_chain_head"],
        "artifact_manifest": {
            "artifacts": [
                {
                    "artifact_id": "source_document_bundle",
                    "artifact_type": "document_bundle",
                    "sha256": source_bundle_sha256,
                },
                {
                    "artifact_id": "translation_bundle",
                    "artifact_type": "translation_bundle",
                },
            ]
        },
        "glossary_hits": glossary_hits,
        "model_approval_refs": [
            f"instruction_set:{instruction_set.instruction_set_id}@{instruction_set.version}"
        ],
    }
    validate_payload(translation_bundle, TRANSLATION_BUNDLE_SCHEMA)
    return translation_bundle


def submit_document_bundle_job(
    document_bundle: dict[str, Any],
    *,
    target_language: str,
    provider_id: str = "passthrough",
    allow_nc_licensed: bool = False,
    certified: bool = False,
    tenant_id: str = DEFAULT_TENANT_ID,
    glossary_ids: list[str] | None = None,
    instruction_set_id: str | None = None,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
    work_queue: WorkQueue = DEFAULT_WORK_QUEUE,
) -> dict[str, Any]:
    """Submit a DocumentBundle translation job and run it synchronously locally."""

    validate_payload(document_bundle, DOCUMENT_BUNDLE_SCHEMA)
    work_item = TranslationWorkItem(
        document_bundle=document_bundle,
        target_language=target_language,
        provider_id=provider_id,
        allow_nc_licensed=allow_nc_licensed,
        certified=certified,
        tenant_id=tenant_id,
        glossary_ids=glossary_ids,
        instruction_set_id=instruction_set_id,
        metadata={
            "persistence": "process_local_in_memory",
            "input_contract": DOCUMENT_BUNDLE_SCHEMA,
            "output_contract": TRANSLATION_BUNDLE_SCHEMA,
            "tenant_id": tenant_id,
            "glossary_ids": glossary_ids or [],
            "instruction_set_id": instruction_set_id,
        },
    )
    submitted = work_queue.submit(
        work_item,
        repository=repository,
        executor=_execute_translation_work_item,
        error_mapper=_translation_job_error,
    )
    return submitted.status_payload()


def submit_text_job(
    text: str,
    *,
    source_language: str,
    target_language: str,
    provider_id: str = "passthrough",
    source_name: str = "raw-text.txt",
    allow_nc_licensed: bool = False,
    certified: bool = False,
    tenant_id: str = DEFAULT_TENANT_ID,
    glossary_ids: list[str] | None = None,
    instruction_set_id: str | None = None,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
    work_queue: WorkQueue = DEFAULT_WORK_QUEUE,
) -> dict[str, Any]:
    language_detection = None
    effective_source_language = source_language
    if source_language.casefold() == "auto":
        language_detection = detect_language(text)
        effective_source_language = language_detection.language
    document_bundle = raw_text_to_document_bundle(
        text,
        source_language=effective_source_language,
        source_name=source_name,
        language_detection=language_detection,
    )
    return submit_document_bundle_job(
        document_bundle,
        target_language=target_language,
        provider_id=provider_id,
        allow_nc_licensed=allow_nc_licensed,
        certified=certified,
        tenant_id=tenant_id,
        glossary_ids=glossary_ids,
        instruction_set_id=instruction_set_id,
        repository=repository,
        work_queue=work_queue,
    )


def _execute_translation_work_item(work_item: TranslationWorkItem) -> dict[str, Any]:
    return translate_document_bundle(
        work_item.document_bundle,
        target_language=work_item.target_language,
        provider_id=work_item.provider_id,
        allow_nc_licensed=work_item.allow_nc_licensed,
        certified=work_item.certified,
        tenant_id=work_item.tenant_id,
        glossary_ids=work_item.glossary_ids,
        instruction_set_id=work_item.instruction_set_id,
    )


def _translation_job_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, RoutingError):
        return auto_route_error_payload(str(exc), exc.diagnostics)["error"]
    return {
        "code": "translation_job_failed",
        "message": str(exc),
    }


def raw_text_to_document_bundle(
    text: str,
    *,
    source_language: str,
    source_name: str = "raw-text.txt",
    language_detection: LanguageDetection | None = None,
) -> dict[str, Any]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document_id = f"raw-text-{digest[:16]}"
    bundle = {
        "schema_version": DOCUMENT_BUNDLE_SCHEMA,
        "document_id": document_id,
        "source_file_name": source_name,
        "source_file_sha256": digest,
        "source_ocr_sha256": digest,
        "pages": [{"page_number": 1, "text": text, "span_ids": ["span-1"]}],
        "spans": [
            {
                "span_id": "span-1",
                "page_number": 1,
                "text": text,
                "bbox": [0, 0, 0, 0],
                "bboxes": [[0, 0, 0, 0]],
                "language": source_language,
            }
        ],
        "language_metadata": _raw_text_language_metadata(
            source_language,
            language_detection=language_detection,
        ),
        "ocr_engine_metadata": {"engine_id": "raw_text_normalizer"},
        "custody_chain_head": f"raw-text:{digest}",
        "artifact_manifest": {
            "artifacts": [
                {
                    "artifact_id": "raw_text_input",
                    "artifact_type": "text",
                    "sha256": digest,
                    "mime_type": "text/plain",
                }
            ]
        },
    }
    validate_payload(bundle, DOCUMENT_BUNDLE_SCHEMA)
    return bundle


def _raw_text_language_metadata(
    source_language: str,
    *,
    language_detection: LanguageDetection | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "primary_language": source_language,
        "detected_languages": [source_language],
        "source": "raw_text_submission",
    }
    if language_detection is not None:
        metadata["source"] = "raw_text_auto_detection"
        metadata["detector"] = language_detection.to_dict()
    return metadata


def get_translation_job_status(
    job_id: str,
    *,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
) -> dict[str, Any]:
    return repository.get(job_id).status_payload()


def get_translation_job_bundle(
    job_id: str,
    *,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
) -> dict[str, Any]:
    job = repository.get(job_id)
    if job.translation_bundle is None:
        raise ValueError(f"TranslationBundle is not available for job {job_id!r}")
    validate_payload(job.translation_bundle, TRANSLATION_BUNDLE_SCHEMA)
    return job.translation_bundle


def list_translation_jobs(
    *,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
) -> list[dict[str, Any]]:
    return [job.status_payload() for job in repository.list()]


def get_evidence_bundle(
    job_id: str,
    *,
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
) -> dict[str, Any]:
    return evidence_bundle_for_job(repository.get(job_id))


def validate_custody_payload(translation_bundle: dict[str, Any]) -> dict[str, Any]:
    validate_payload(translation_bundle, TRANSLATION_BUNDLE_SCHEMA)
    return validate_translation_custody(translation_bundle)


def score_pair(
    source_text: str,
    translated_text: str,
    *,
    source_language: str = "und",
    target_language: str = "und",
) -> dict[str, object]:
    return score_translation_pair(
        source_text,
        translated_text,
        source_language=source_language,
        target_language=target_language,
    )


def get_tenant_policy(
    tenant_id: str = DEFAULT_TENANT_ID,
    *,
    repository: TenantPolicyRepository = DEFAULT_POLICY_REPOSITORY,
) -> dict[str, Any]:
    return repository.get(tenant_id).to_dict()


def update_tenant_policy(
    tenant_id: str,
    updates: dict[str, Any],
    *,
    repository: TenantPolicyRepository = DEFAULT_POLICY_REPOSITORY,
) -> dict[str, Any]:
    return repository.update(tenant_id, updates).to_dict()


def upsert_glossary(
    payload: dict[str, Any],
    *,
    repository: GlossaryRepository = DEFAULT_GLOSSARY_REPOSITORY,
) -> dict[str, Any]:
    glossary = Glossary(
        glossary_id=str(payload["glossary_id"]),
        name=str(payload.get("name", payload["glossary_id"])),
        source_language=str(payload["source_language"]),
        target_language=str(payload["target_language"]),
        entries={str(k): str(v) for k, v in dict(payload.get("entries", {})).items()},
        approved=bool(payload.get("approved", False)),
    )
    return repository.upsert(glossary).to_dict()


def list_glossaries(
    *,
    repository: GlossaryRepository = DEFAULT_GLOSSARY_REPOSITORY,
) -> list[dict[str, Any]]:
    return [glossary.to_dict() for glossary in repository.list()]


def get_glossary(
    glossary_id: str,
    *,
    repository: GlossaryRepository = DEFAULT_GLOSSARY_REPOSITORY,
) -> dict[str, Any]:
    return repository.get(glossary_id).to_dict()


def delete_glossary(
    glossary_id: str,
    *,
    repository: GlossaryRepository = DEFAULT_GLOSSARY_REPOSITORY,
) -> None:
    repository.delete(glossary_id)


def list_instruction_sets(
    *,
    repository: InstructionSetRepository = DEFAULT_INSTRUCTION_REPOSITORY,
) -> list[dict[str, Any]]:
    return [instruction.to_dict() for instruction in repository.list()]


def validate_model_bundle(
    model_dir: str | Path,
    *,
    model_id: str | None = None,
    enforce_supply_chain: bool = True,
    model_registry_store: ModelRegistryStore = DEFAULT_MODEL_REGISTRY_STORE,
) -> dict[str, Any]:
    # Transient legacy instance only for the validation/provenance logic + CT2 bundle checks.
    # Its internal dict side-effect is ignored; we persist the resulting status to the
    # configured store (InMemory or Postgres) so list/approve surfaces see durable data.
    temp_registry = ModelRegistry()
    status = temp_registry.validate_bundle(
        model_dir,
        model_id=model_id,
        enforce_supply_chain=enforce_supply_chain,
    )
    model_registry_store.save(status)
    return status.to_dict()


def list_model_statuses(
    *,
    model_registry_store: ModelRegistryStore = DEFAULT_MODEL_REGISTRY_STORE,
) -> list[dict[str, Any]]:
    return [status.to_dict() for status in model_registry_store.list()]


def record_review_decision(
    job_id: str,
    *,
    decision: str,
    reviewer: str,
    notes: str = "",
    repository: JobRepository = DEFAULT_JOB_REPOSITORY,
    review_repository: ReviewRepository = DEFAULT_REVIEW_REPOSITORY,
) -> dict[str, Any]:
    job = repository.get(job_id)
    review = review_repository.add(
        job_id=job_id,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
    )
    if job.translation_bundle is not None:
        bundle = dict(job.translation_bundle)
        decisions = list(bundle.get("review_decisions", []))
        decisions.append(review.to_dict())
        bundle["review_decisions"] = decisions
        if decision == "certified":
            bundle["certified"] = True
        repository.mark_succeeded(job_id, translation_bundle=bundle)
    return review.to_dict()


def list_review_decisions(
    *,
    job_id: str | None = None,
    review_repository: ReviewRepository = DEFAULT_REVIEW_REPOSITORY,
) -> list[dict[str, Any]]:
    return [review.to_dict() for review in review_repository.list(job_id=job_id)]


def live_provider_smoke(
    provider_id: str,
    *,
    source_language: str = "en",
    target_language: str = "fr",
    text: str = "Translate this sentence.",
    max_tokens: int = 64,
) -> dict[str, Any]:
    return smoke_provider(
        provider_id,
        source_language=source_language,
        target_language=target_language,
        text=text,
        max_tokens=max_tokens,
    )


def local_model_ranking(
    *,
    source_language: str = "en",
    target_language: str = "fr",
    text: str = "Translate this sentence.",
    max_tokens: int = 64,
    max_models: int = 4,
) -> list[dict[str, Any]]:
    return rank_local_models(
        source_language=source_language,
        target_language=target_language,
        text=text,
        max_tokens=max_tokens,
        max_models=max_models,
    )


def local_runtime_readiness(
    *,
    provider_id: str = "local_openai_compat",
) -> dict[str, Any]:
    return llm_local_runtime_readiness(provider_id=provider_id)


def discover_env_contracts(
    *,
    root: str | Path = ".",
) -> list[dict[str, Any]]:
    return discover_env_variable_names(root=root)


def release_readiness_status(
    *,
    live_smoke_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return release_readiness_lane_status(live_smoke_results=live_smoke_results)


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
    tenant_id: str = DEFAULT_TENANT_ID,
    glossary_ids: list[str] | None = None,
    instruction_set_id: str | None = None,
    write_translation_bundles: bool = True,
    write_manifest: bool = True,
    continue_on_error: bool = True,
    run_async: bool = True,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> dict[str, Any]:
    return submit_text_file_batch_job_to_repository(
        source_path=source_path,
        output_dir=output_dir,
        source_language=source_language,
        target_language=target_language,
        provider_id=provider_id,
        input_encoding=input_encoding,
        output_encoding=output_encoding,
        recursive=recursive,
        file_extensions=file_extensions,
        allow_nc_licensed=allow_nc_licensed,
        certified=certified,
        tenant_id=tenant_id,
        glossary_ids=glossary_ids,
        instruction_set_id=instruction_set_id,
        write_translation_bundles=write_translation_bundles,
        write_manifest=write_manifest,
        continue_on_error=continue_on_error,
        repository=repository,
        run_async=run_async,
    )


def get_text_file_batch_status(
    job_id: str,
    *,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> dict[str, Any]:
    return repository.get(job_id).status_payload()


def list_text_file_batch_jobs(
    *,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> list[dict[str, Any]]:
    return [job.status_payload() for job in repository.list()]


def get_text_file_batch_logs(
    job_id: str,
    *,
    offset: int = 0,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> dict[str, Any]:
    logs = repository.get(job_id).logs
    start = max(0, offset)
    return {
        "job_id": job_id,
        "offset": start,
        "next_offset": len(logs),
        "logs": logs[start:],
    }


def get_text_file_batch_log_text(
    job_id: str,
    *,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> str:
    return format_batch_log(repository.get(job_id))


def save_text_file_batch_log(
    job_id: str,
    *,
    log_path: str | Path | None = None,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> dict[str, Any]:
    path = save_batch_log(repository.get(job_id), log_path=log_path)
    return {"job_id": job_id, "log_path": path}


def get_text_file_batch_outputs(
    job_id: str,
    *,
    repository: TextFileBatchRepository = DEFAULT_TEXT_FILE_BATCH_REPOSITORY,
) -> dict[str, Any]:
    job = repository.get(job_id)
    return {
        "job_id": job_id,
        "files": job.files,
        "manifest_path": job.manifest_path,
    }


def list_engine_providers(
    *,
    include_routing_diagnostics: bool = False,
    source_language: str = "und",
    target_language: str = "und",
    allow_nc_licensed: bool = False,
) -> list[dict[str, Any]]:
    providers = [
        engine_list_entry(engine_cls())
        for _engine_id, engine_cls in iter_engines()
    ]
    if include_routing_diagnostics:
        diagnostics = engine_routing_diagnostics(
            source_language=source_language,
            target_language=target_language,
            allow_nc_licensed=allow_nc_licensed,
        )
        candidates_by_id = {
            candidate["id"]: candidate
            for candidate in diagnostics["candidates"]
        }
        for provider in providers:
            provider["auto_routing"] = candidates_by_id.get(
                provider["id"],
                {
                    "id": provider["id"],
                    "eligible": False,
                    "selected": False,
                    "reason": "not an auto-routing candidate",
                },
            )
    return providers


def engine_routing_diagnostics(
    *,
    source_language: str,
    target_language: str,
    allow_nc_licensed: bool = False,
) -> dict[str, object]:
    request = TranslationRequest(
        src_lang=source_language,
        tgt_lang=target_language,
        tenant_id="standalone",
    )
    return diagnose_auto_route(
        request,
        policy=EngineRoutingPolicy(allow_nc_licensed=allow_nc_licensed),
    )


def _resolve_glossaries(
    glossary_ids: list[str],
    repository: GlossaryRepository,
    *,
    source_language: str,
    target_language: str,
) -> list[Glossary]:
    glossaries: list[Glossary] = []
    for glossary_id in glossary_ids:
        glossary = repository.get(glossary_id)
        if (
            glossary.source_language == source_language
            and glossary.target_language == target_language
        ):
            glossaries.append(glossary)
    return glossaries


def _apply_glossary_hits(
    translated_spans: list[dict[str, Any]],
    glossaries: list[Glossary],
) -> list[str]:
    all_hits: list[str] = []
    for span in translated_spans:
        hits = find_glossary_hits(str(span["source_text"]), glossaries)
        span["glossary_hits"] = hits
        all_hits.extend(hits)
    return sorted(set(all_hits))


def _validate_policy_allows_engine(
    engine: Any,
    policy: dict[str, Any],
    instruction_set: InstructionSet,
) -> None:
    provider = engine_provider_payload(engine)
    family = provider["family"]
    if family in policy["blocked_provider_families"]:
        raise ValueError(f"provider family blocked by tenant policy: {family}")
    if family not in policy["allowed_provider_families"]:
        raise ValueError(f"provider family not allowed by tenant policy: {family}")
    if family not in instruction_set.allowed_engine_families:
        raise ValueError(
            "provider family not allowed by instruction set "
            f"{instruction_set.instruction_set_id}: {family}"
        )


def _source_language(document_bundle: dict[str, Any]) -> str:
    metadata = document_bundle.get("language_metadata", {})
    if metadata.get("primary_language"):
        return str(metadata["primary_language"])
    for span in document_bundle.get("spans", []):
        if span.get("language"):
            return str(span["language"])
    return "und"


def _source_spans_for_engine(document_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "span_id": span["span_id"],
            "page_number": span["page_number"],
            "text": span["text"],
            "bbox": span["bbox"],
            "bboxes": span.get("bboxes", [span["bbox"]]),
            "language": span.get("language"),
        }
        for span in document_bundle["spans"]
    ]


def _translated_spans(
    translated: list[SpanTranslation],
    source_spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_by_id = {span["span_id"]: span for span in source_spans}
    out: list[dict[str, Any]] = []
    for index, span_model in enumerate(translated):
        source = source_by_id.get(span_model.span_id, source_spans[index])
        out.append(
            {
                "span_id": span_model.span_id,
                "page_number": int(source["page_number"]),
                "source_text": span_model.source_text,
                "translated_text": span_model.target_text,
                "source_bbox": span_model.source_bbox,
                "source_bboxes": span_model.source_bboxes,
                "source_language": span_model.source_language,
                "target_language": span_model.target_language,
                "confidence": span_model.confidence,
                "quality_score": span_model.quality_score,
                "engine_id": span_model.engine_id,
                "glossary_hits": span_model.glossary_hits,
            }
        )
    return out
