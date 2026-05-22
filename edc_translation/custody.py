"""Translation custody and evidence bundle helpers."""

from __future__ import annotations

from typing import Any

from edc_translation.contracts import canonical_json_sha256
from edc_translation.jobs import TranslationJob, utc_now_iso


def evidence_bundle_for_job(job: TranslationJob) -> dict[str, Any]:
    bundle = job.translation_bundle
    translation_sha256 = canonical_json_sha256(bundle) if bundle else None
    return {
        "schema_version": "translation-evidence-bundle-v1",
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": job.status,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "generated_at": utc_now_iso(),
        "source_bundle_sha256": bundle.get("source_bundle_sha256") if bundle else None,
        "translation_bundle_sha256": translation_sha256,
        "custody_chain_head": bundle.get("custody_chain_head") if bundle else None,
        "artifacts": bundle.get("artifact_manifest", {}).get("artifacts", [])
        if bundle
        else [],
        "job_metadata": job.metadata,
    }


def validate_translation_custody(translation_bundle: dict[str, Any]) -> dict[str, Any]:
    artifacts = translation_bundle.get("artifact_manifest", {}).get("artifacts", [])
    artifact_ids = {
        artifact.get("artifact_id")
        for artifact in artifacts
        if isinstance(artifact, dict)
    }
    missing: list[str] = []
    if not translation_bundle.get("custody_chain_head"):
        missing.append("custody_chain_head")
    if "source_document_bundle" not in artifact_ids:
        missing.append("artifact_manifest.source_document_bundle")
    if "translation_bundle" not in artifact_ids:
        missing.append("artifact_manifest.translation_bundle")
    if not translation_bundle.get("source_bundle_sha256"):
        missing.append("source_bundle_sha256")

    return {
        "valid": not missing,
        "missing": missing,
        "translation_bundle_sha256": canonical_json_sha256(translation_bundle),
    }
