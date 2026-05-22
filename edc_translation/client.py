"""Python client facade for local EDC_TRANSLATION workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edc_translation.language_catalog import language_catalog_payload
from edc_translation.service import (
    release_readiness_status,
    discover_env_contracts,
    get_evidence_bundle,
    get_text_file_batch_logs,
    get_text_file_batch_log_text,
    get_text_file_batch_outputs,
    get_text_file_batch_status,
    get_translation_job_bundle,
    get_translation_job_status,
    list_engine_providers,
    list_text_file_batch_jobs,
    live_provider_smoke,
    local_model_ranking,
    score_pair,
    save_text_file_batch_log,
    submit_document_bundle_job,
    submit_text_file_batch_job,
    submit_text_job,
    validate_custody_payload,
    validate_model_bundle,
)


class TranslationClient:
    """In-process Python client backed by the shared service layer."""

    def list_engines(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list_engine_providers(**kwargs)

    def list_languages(self) -> dict[str, Any]:
        return language_catalog_payload()

    def submit_bundle(
        self,
        document_bundle: dict[str, Any],
        *,
        target_language: str,
        provider_id: str = "passthrough",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return submit_document_bundle_job(
            document_bundle,
            target_language=target_language,
            provider_id=provider_id,
            **kwargs,
        )

    def submit_text(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str = "auto",
        provider_id: str = "passthrough",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return submit_text_job(
            text,
            source_language=source_language,
            target_language=target_language,
            provider_id=provider_id,
            **kwargs,
        )

    def submit_text_file_batch(
        self,
        *,
        source_path: str | Path,
        output_dir: str | Path,
        target_language: str,
        source_language: str = "auto",
        provider_id: str = "deterministic_ci",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return submit_text_file_batch_job(
            source_path=source_path,
            output_dir=output_dir,
            source_language=source_language,
            target_language=target_language,
            provider_id=provider_id,
            **kwargs,
        )

    def list_text_file_batches(self) -> list[dict[str, Any]]:
        return list_text_file_batch_jobs()

    def get_text_file_batch_status(self, job_id: str) -> dict[str, Any]:
        return get_text_file_batch_status(job_id)

    def get_text_file_batch_logs(self, job_id: str, *, offset: int = 0) -> dict[str, Any]:
        return get_text_file_batch_logs(job_id, offset=offset)

    def get_text_file_batch_log_text(self, job_id: str) -> str:
        return get_text_file_batch_log_text(job_id)

    def save_text_file_batch_log(
        self,
        job_id: str,
        *,
        log_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return save_text_file_batch_log(job_id, log_path=log_path)

    def get_text_file_batch_outputs(self, job_id: str) -> dict[str, Any]:
        return get_text_file_batch_outputs(job_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        return get_translation_job_status(job_id)

    def get_bundle(self, job_id: str) -> dict[str, Any]:
        return get_translation_job_bundle(job_id)

    def score_pair(
        self,
        source_text: str,
        translated_text: str,
        *,
        source_language: str = "und",
        target_language: str = "und",
    ) -> dict[str, object]:
        return score_pair(
            source_text,
            translated_text,
            source_language=source_language,
            target_language=target_language,
        )

    def validate_model_bundle(
        self,
        model_dir: str | Path,
        *,
        model_id: str | None = None,
        enforce_supply_chain: bool = True,
    ) -> dict[str, Any]:
        return validate_model_bundle(
            model_dir,
            model_id=model_id,
            enforce_supply_chain=enforce_supply_chain,
        )

    def get_evidence_bundle(self, job_id: str) -> dict[str, Any]:
        return get_evidence_bundle(job_id)

    def validate_custody(self, translation_bundle: dict[str, Any]) -> dict[str, Any]:
        return validate_custody_payload(translation_bundle)

    def live_smoke(
        self,
        provider_id: str = "local_openai_compat",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return live_provider_smoke(provider_id, **kwargs)

    def rank_local_models(self, **kwargs: Any) -> list[dict[str, Any]]:
        return local_model_ranking(**kwargs)

    def discover_env(self, **kwargs: Any) -> list[dict[str, Any]]:
        return discover_env_contracts(**kwargs)

    def release_readiness_status(self) -> dict[str, Any]:
        return release_readiness_status()
