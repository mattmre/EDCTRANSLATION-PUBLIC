from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edc_translation.jobs import (
    InMemoryTranslationJobRepository,
    LocalSynchronousWorkQueue,
    TranslationWorkItem,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "edc_contracts"


def _document_bundle() -> dict[str, Any]:
    return json.loads(
        (FIXTURES / "document-bundle-v1.valid.json").read_text(encoding="utf-8")
    )


def test_local_work_queue_runs_executor_and_persists_completed_job():
    repository = InMemoryTranslationJobRepository()
    queue = LocalSynchronousWorkQueue()
    document = _document_bundle()
    bundle = {
        "schema_version": "translation-bundle-v1",
        "document_id": document["document_id"],
    }

    job = queue.submit(
        TranslationWorkItem(
            document_bundle=document,
            target_language="fr",
            provider_id="deterministic_ci",
            metadata={"persistence": "process_local_in_memory"},
        ),
        repository=repository,
        executor=lambda _work_item: bundle,
        error_mapper=lambda exc: {"code": "unexpected", "message": str(exc)},
    )

    status = repository.get(job.job_id).status_payload()
    assert status["status"] == "succeeded"
    assert status["document_id"] == document["document_id"]
    assert status["translation_bundle_available"] is True
    assert status["metadata"]["persistence"] == "process_local_in_memory"
    assert repository.get(job.job_id).translation_bundle == bundle


def test_local_work_queue_maps_executor_failure_to_job_error():
    repository = InMemoryTranslationJobRepository()
    queue = LocalSynchronousWorkQueue()

    def fail(_work_item: TranslationWorkItem) -> dict[str, Any]:
        raise ValueError("boom")

    job = queue.submit(
        TranslationWorkItem(
            document_bundle=_document_bundle(),
            target_language="fr",
            provider_id="deterministic_ci",
        ),
        repository=repository,
        executor=fail,
        error_mapper=lambda exc: {"code": "mapped_failure", "message": str(exc)},
    )

    status = repository.get(job.job_id).status_payload()
    assert status["status"] == "failed"
    assert status["translation_bundle_available"] is False
    assert status["error"] == {"code": "mapped_failure", "message": "boom"}
