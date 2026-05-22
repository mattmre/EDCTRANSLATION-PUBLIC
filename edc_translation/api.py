"""FastAPI surface for EDC_TRANSLATION."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from edc_translation.auth import Principal
from edc_translation.auth_middleware import (
    PrincipalAuthMiddleware,
    bind_request_tenant,
    current_principal,
    require_route_scope,
)
from edc_translation.errors import (
    auto_route_error_payload,
    auto_route_unavailable_message,
)
from edc_translation.language_catalog import language_catalog_payload
from edc_translation.routing import RoutingError
from edc_translation.service import (
    release_readiness_status,
    delete_glossary,
    discover_env_contracts,
    engine_routing_diagnostics,
    get_evidence_bundle,
    get_glossary,
    get_tenant_policy,
    get_text_file_batch_logs,
    get_text_file_batch_log_text,
    get_text_file_batch_outputs,
    get_text_file_batch_status,
    get_translation_job_bundle,
    get_translation_job_status,
    list_glossaries,
    list_engine_providers,
    list_instruction_sets,
    list_model_statuses,
    list_review_decisions,
    list_text_file_batch_jobs,
    list_translation_jobs,
    live_provider_smoke,
    local_model_ranking,
    record_review_decision,
    score_pair,
    save_text_file_batch_log,
    submit_document_bundle_job,
    submit_text_file_batch_job,
    submit_text_job,
    translate_document_bundle,
    update_tenant_policy,
    upsert_glossary,
    validate_custody_payload,
    validate_model_bundle,
)

app = FastAPI(title="EDC_TRANSLATION", version="0.1.0")
app.add_middleware(PrincipalAuthMiddleware)


class TranslateBundleRequest(BaseModel):
    document_bundle: dict[str, Any]
    target_language: str = Field(min_length=1)
    provider_id: str = "passthrough"
    allow_nc_licensed: bool = False
    certified: bool = False
    tenant_id: str = "standalone"
    glossary_ids: list[str] = Field(default_factory=list)
    instruction_set_id: str | None = None


class TranslateTextRequest(BaseModel):
    text: str = Field(min_length=1)
    source_language: str = Field("auto", min_length=1)
    target_language: str = Field(min_length=1)
    source_name: str = "raw-text.txt"
    provider_id: str = "passthrough"
    allow_nc_licensed: bool = False
    certified: bool = False
    tenant_id: str = "standalone"
    glossary_ids: list[str] = Field(default_factory=list)
    instruction_set_id: str | None = None


class ScorePairRequest(BaseModel):
    source_text: str
    translated_text: str
    source_language: str = "auto"
    target_language: str = "und"


class ReviewRequest(BaseModel):
    decision: str
    reviewer: str
    notes: str = ""


class LiveSmokeRequest(BaseModel):
    provider_id: str = "local_openai_compat"
    source_language: str = "auto"
    target_language: str = "fr"
    text: str = "Translate this sentence."
    max_tokens: int = 64


class TextFileBatchRequest(BaseModel):
    source_path: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)
    source_language: str = Field("auto", min_length=1)
    target_language: str = Field(min_length=1)
    provider_id: str = "deterministic_ci"
    input_encoding: str = "auto"
    output_encoding: str = "utf-8"
    recursive: bool = True
    file_extensions: list[str] = Field(default_factory=lambda: [".txt"])
    allow_nc_licensed: bool = False
    certified: bool = False
    tenant_id: str = "standalone"
    glossary_ids: list[str] = Field(default_factory=list)
    instruction_set_id: str | None = None
    write_translation_bundles: bool = True
    write_manifest: bool = True
    continue_on_error: bool = True


class TextFileBatchLogSaveRequest(BaseModel):
    log_path: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "edc_translation"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return health()


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {
        **health(),
        "readiness": "ready",
    }


@app.get("/api/v1/translation/engines")
def list_engines(
    request: Request,
    include_routing_diagnostics: bool = False,
    source_language: str = "und",
    target_language: str = "und",
    allow_nc_licensed: bool = False,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    del request
    require_route_scope(principal, "models:read")
    response: dict[str, Any] = {
        "engines": list_engine_providers(
            include_routing_diagnostics=include_routing_diagnostics,
            source_language=source_language,
            target_language=target_language,
            allow_nc_licensed=allow_nc_licensed,
        )
    }
    if include_routing_diagnostics:
        response["routing_diagnostics"] = engine_routing_diagnostics(
            source_language=source_language,
            target_language=target_language,
            allow_nc_licensed=allow_nc_licensed,
        )
    return response


@app.get("/api/v1/translation/languages")
def languages(principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return language_catalog_payload()


@app.get("/api/v1/translation/routing/diagnostics")
def routing_diagnostics(
    source_language: str = "und",
    target_language: str = "und",
    allow_nc_licensed: bool = False,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {
        "routing_diagnostics": engine_routing_diagnostics(
            source_language=source_language,
            target_language=target_language,
            allow_nc_licensed=allow_nc_licensed,
        )
    }


@app.get("/api/v1/translation/readiness/auto-route")
def auto_route_readiness(
    source_language: str = "en",
    target_language: str = "fr",
    allow_nc_licensed: bool = False,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    diagnostics = engine_routing_diagnostics(
        source_language=source_language,
        target_language=target_language,
        allow_nc_licensed=allow_nc_licensed,
    )
    if diagnostics["selected_provider_id"]:
        return {"status": "ready", "routing_diagnostics": diagnostics}

    message = auto_route_unavailable_message(
        source_language,
        target_language,
        diagnostics,
    )
    raise HTTPException(
        status_code=503,
        detail=auto_route_error_payload(message, diagnostics),
    )


@app.post("/api/v1/translation/bundles")
def translate_bundle(
    request: TranslateBundleRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:submit")
    tenant_id = bind_request_tenant(principal, request.tenant_id)
    try:
        bundle = translate_document_bundle(
            request.document_bundle,
            target_language=request.target_language,
            provider_id=request.provider_id,
            allow_nc_licensed=request.allow_nc_licensed,
            certified=request.certified,
            tenant_id=tenant_id,
            glossary_ids=request.glossary_ids,
            instruction_set_id=request.instruction_set_id,
        )
    except RoutingError as exc:
        raise HTTPException(
            status_code=409,
            detail=auto_route_error_payload(str(exc), exc.diagnostics),
        ) from exc
    return {"translation_bundle": bundle}


@app.post("/api/v1/translation/jobs", status_code=202)
def submit_translation_job(
    request: TranslateBundleRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:submit")
    tenant_id = bind_request_tenant(principal, request.tenant_id)
    job = submit_document_bundle_job(
        request.document_bundle,
        target_language=request.target_language,
        provider_id=request.provider_id,
        allow_nc_licensed=request.allow_nc_licensed,
        certified=request.certified,
        tenant_id=tenant_id,
        glossary_ids=request.glossary_ids,
        instruction_set_id=request.instruction_set_id,
    )
    return {"job": job}


@app.post("/api/v1/translation/jobs/text", status_code=202)
def submit_text_translation_job(
    request: TranslateTextRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:submit")
    tenant_id = bind_request_tenant(principal, request.tenant_id)
    job = submit_text_job(
        request.text,
        source_language=request.source_language,
        target_language=request.target_language,
        source_name=request.source_name,
        provider_id=request.provider_id,
        allow_nc_licensed=request.allow_nc_licensed,
        certified=request.certified,
        tenant_id=tenant_id,
        glossary_ids=request.glossary_ids,
        instruction_set_id=request.instruction_set_id,
    )
    return {"job": job}


@app.get("/api/v1/translation/jobs")
def translation_jobs(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    return {"jobs": list_translation_jobs()}


@app.post("/api/v1/translation/files/batch", status_code=202)
def submit_file_batch(
    request: TextFileBatchRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:submit")
    tenant_id = bind_request_tenant(principal, request.tenant_id)
    job = submit_text_file_batch_job(
        source_path=request.source_path,
        output_dir=request.output_dir,
        source_language=request.source_language,
        target_language=request.target_language,
        provider_id=request.provider_id,
        input_encoding=request.input_encoding,
        output_encoding=request.output_encoding,
        recursive=request.recursive,
        file_extensions=request.file_extensions,
        allow_nc_licensed=request.allow_nc_licensed,
        certified=request.certified,
        tenant_id=tenant_id,
        glossary_ids=request.glossary_ids,
        instruction_set_id=request.instruction_set_id,
        write_translation_bundles=request.write_translation_bundles,
        write_manifest=request.write_manifest,
        continue_on_error=request.continue_on_error,
        run_async=True,
    )
    return {"job": job}


@app.get("/api/v1/translation/files/batch")
def text_file_batch_jobs(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    return {"jobs": list_text_file_batch_jobs()}


@app.get("/api/v1/translation/files/batch/{job_id}")
def text_file_batch_status(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return {"job": get_text_file_batch_status(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="text file batch job not found") from exc


@app.get("/api/v1/translation/files/batch/{job_id}/logs")
def text_file_batch_logs(
    job_id: str,
    offset: int = 0,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return get_text_file_batch_logs(job_id, offset=offset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="text file batch job not found") from exc


@app.get(
    "/api/v1/translation/files/batch/{job_id}/logs/text",
    response_class=PlainTextResponse,
)
def text_file_batch_log_text(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> PlainTextResponse:
    require_route_scope(principal, "translation:read")
    try:
        return PlainTextResponse(get_text_file_batch_log_text(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="text file batch job not found") from exc


@app.post("/api/v1/translation/files/batch/{job_id}/logs/save")
def save_text_file_batch_log_endpoint(
    job_id: str,
    request: TextFileBatchLogSaveRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return {"log": save_text_file_batch_log(job_id, log_path=request.log_path)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="text file batch job not found") from exc


@app.get("/api/v1/translation/files/batch/{job_id}/outputs")
def text_file_batch_outputs(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return get_text_file_batch_outputs(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="text file batch job not found") from exc


@app.get("/api/v1/translation/jobs/{job_id}")
def translation_job_status(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return {"job": get_translation_job_status(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="translation job not found") from exc


@app.get("/api/v1/translation/jobs/{job_id}/bundle")
def translation_job_bundle(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        bundle = get_translation_job_bundle(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="translation job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"translation_bundle": bundle}


@app.get("/api/v1/translation/jobs/{job_id}/evidence")
def translation_job_evidence(
    job_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "evidence:read")
    try:
        return {"evidence_bundle": get_evidence_bundle(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="translation job not found") from exc


@app.post("/api/v1/translation/score-pair")
def score_translation_pair(
    request: ScorePairRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    return {
        "quality": score_pair(
            request.source_text,
            request.translated_text,
            source_language=request.source_language,
            target_language=request.target_language,
        )
    }


@app.post("/api/v1/translation/custody/validate")
def validate_custody(
    request: dict[str, Any],
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "evidence:read")
    return {"custody": validate_custody_payload(request)}


@app.get("/api/v1/translation/tenant-policy/{tenant_id}")
def tenant_policy(
    tenant_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "tenant:policy:read")
    bound_tenant_id = bind_request_tenant(principal, tenant_id)
    return {"tenant_policy": get_tenant_policy(bound_tenant_id)}


@app.put("/api/v1/translation/tenant-policy/{tenant_id}")
def put_tenant_policy(
    tenant_id: str,
    request: dict[str, Any],
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "tenant:policy:write")
    bound_tenant_id = bind_request_tenant(principal, tenant_id)
    return {"tenant_policy": update_tenant_policy(bound_tenant_id, request)}


@app.get("/api/v1/translation/glossaries")
def glossaries(principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    return {"glossaries": list_glossaries()}


@app.post("/api/v1/translation/glossaries")
def post_glossary(
    request: dict[str, Any],
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:submit")
    return {"glossary": upsert_glossary(request)}


@app.get("/api/v1/translation/glossaries/{glossary_id}")
def glossary(
    glossary_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    try:
        return {"glossary": get_glossary(glossary_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="glossary not found") from exc


@app.delete("/api/v1/translation/glossaries/{glossary_id}", status_code=204)
def remove_glossary(
    glossary_id: str,
    principal: Principal = Depends(current_principal),
) -> None:
    require_route_scope(principal, "translation:submit")
    try:
        delete_glossary(glossary_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="glossary not found") from exc


@app.get("/api/v1/translation/instruction-sets")
def instruction_sets(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {"instruction_sets": list_instruction_sets()}


@app.post("/api/v1/translation/models/validate")
def validate_model(
    request: dict[str, Any],
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:write")
    return {
        "model_status": validate_model_bundle(
            request["model_dir"],
            model_id=request.get("model_id"),
            enforce_supply_chain=bool(request.get("enforce_supply_chain", True)),
        )
    }


@app.get("/api/v1/translation/models")
def model_statuses(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {"models": list_model_statuses()}


@app.post("/api/v1/translation/live-smoke")
def live_smoke(
    request: LiveSmokeRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {
        "smoke": live_provider_smoke(
            request.provider_id,
            source_language=request.source_language,
            target_language=request.target_language,
            text=request.text,
            max_tokens=request.max_tokens,
        )
    }


@app.get("/api/v1/translation/local-model-ranking")
def local_ranking(
    source_language: str = "en",
    target_language: str = "fr",
    text: str = "Translate this sentence.",
    max_tokens: int = 64,
    max_models: int = 4,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {
        "models": local_model_ranking(
            source_language=source_language,
            target_language=target_language,
            text=text,
            max_tokens=max_tokens,
            max_models=max_models,
        )
    }


@app.get("/api/v1/translation/env-discovery")
def env_discovery(
    root: str = ".",
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "audit:read")
    return {"env_files": discover_env_contracts(root=root)}


@app.get("/api/v1/translation/readiness/evidence-status")
def readiness_status(principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_route_scope(principal, "audit:read")
    return {"readiness": release_readiness_status()}


@app.get("/api/v1/translation/reviews")
def reviews(
    job_id: str | None = None,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "translation:read")
    return {"reviews": list_review_decisions(job_id=job_id)}


@app.post("/api/v1/translation/jobs/{job_id}/reviews")
def post_review(
    job_id: str,
    request: ReviewRequest,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "reviews:write")
    try:
        review = record_review_decision(
            job_id,
            decision=request.decision,
            reviewer=request.reviewer,
            notes=request.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="translation job not found") from exc
    return {"review": review}


@app.get("/admin", response_class=HTMLResponse)
@app.get("/api/v1/translation/admin", response_class=HTMLResponse)
def admin_page(principal: Principal = Depends(current_principal)) -> HTMLResponse:
    require_route_scope(principal, "audit:read")
    html = Path(__file__).with_name("static").joinpath("admin.html").read_text(
        encoding="utf-8"
    )
    return HTMLResponse(html)


@app.get("/api/v1/translation/openapi-summary")
def openapi_summary(
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_route_scope(principal, "models:read")
    return {
        "service": "EDC_TRANSLATION",
        "endpoints": [
            "/health",
            "/api/v1/translation/engines",
            "/api/v1/translation/languages",
            "/api/v1/translation/routing/diagnostics",
            "/api/v1/translation/readiness/auto-route",
            "/api/v1/translation/bundles",
            "/api/v1/translation/jobs",
            "/api/v1/translation/jobs/text",
            "/api/v1/translation/files/batch",
            "/api/v1/translation/files/batch/{job_id}",
            "/api/v1/translation/files/batch/{job_id}/logs",
            "/api/v1/translation/files/batch/{job_id}/logs/text",
            "/api/v1/translation/files/batch/{job_id}/logs/save",
            "/api/v1/translation/files/batch/{job_id}/outputs",
            "/api/v1/translation/jobs/{job_id}",
            "/api/v1/translation/jobs/{job_id}/bundle",
            "/api/v1/translation/jobs/{job_id}/evidence",
            "/api/v1/translation/score-pair",
            "/api/v1/translation/custody/validate",
            "/api/v1/translation/tenant-policy/{tenant_id}",
            "/api/v1/translation/glossaries",
            "/api/v1/translation/instruction-sets",
            "/api/v1/translation/models",
            "/api/v1/translation/models/validate",
            "/api/v1/translation/live-smoke",
            "/api/v1/translation/local-model-ranking",
            "/api/v1/translation/env-discovery",
            "/api/v1/translation/readiness/evidence-status",
            "/api/v1/translation/reviews",
            "/api/v1/translation/jobs/{job_id}/reviews",
            "/api/v1/translation/admin",
        ],
    }


def app_json() -> str:
    """Return the OpenAPI schema as JSON for smoke tooling."""

    return json.dumps(app.openapi(), indent=2)
