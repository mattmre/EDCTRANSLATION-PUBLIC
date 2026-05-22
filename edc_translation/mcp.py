"""Minimal MCP-style tool surface for the Phase 2 skeleton."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from edc_translation.auth import (
    AuthError,
    Principal,
    disabled_auth_principal,
    require_mcp_tool_scope,
)
from edc_translation.service import (
    release_readiness_status,
    discover_env_contracts,
    engine_routing_diagnostics,
    get_evidence_bundle,
    get_translation_job_bundle,
    get_translation_job_status,
    list_engine_providers,
    local_model_ranking,
    live_provider_smoke,
    score_pair,
    submit_document_bundle_job,
    submit_text_job,
    validate_custody_payload,
    validate_model_bundle,
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "translation_list_engines",
        "description": "List available translation provider engines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_routing_diagnostics": {"type": "boolean"},
                "source_language": {"type": "string"},
                "target_language": {"type": "string"},
                "allow_nc_licensed": {"type": "boolean"},
            },
        },
    },
    {
        "name": "translation_submit_bundle",
        "description": "Submit a DocumentBundle v1 translation job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_bundle": {"type": "object"},
                "target_language": {"type": "string"},
                "provider_id": {"type": "string"},
                "allow_nc_licensed": {"type": "boolean"},
            },
            "required": ["document_bundle", "target_language"],
        },
    },
    {
        "name": "translation_get_job_status",
        "description": "Get local translation job status.",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "translation_get_bundle",
        "description": "Get a completed TranslationBundle v1 by job id.",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "translation_submit_text",
        "description": "Submit raw text as a normalized DocumentBundle translation job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "source_language": {"type": "string"},
                "target_language": {"type": "string"},
                "provider_id": {"type": "string"},
                "source_name": {"type": "string"},
                "allow_nc_licensed": {"type": "boolean"},
            },
            "required": ["text", "target_language"],
        },
    },
    {
        "name": "translation_score_pair",
        "description": "Score a source/translation text pair.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_text": {"type": "string"},
                "translated_text": {"type": "string"},
                "source_language": {"type": "string"},
                "target_language": {"type": "string"},
            },
            "required": ["source_text", "translated_text"],
        },
    },
    {
        "name": "translation_validate_model_bundle",
        "description": "Validate a local model bundle and provenance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_dir": {"type": "string"},
                "model_id": {"type": "string"},
                "enforce_supply_chain": {"type": "boolean"},
            },
            "required": ["model_dir"],
        },
    },
    {
        "name": "translation_get_evidence_bundle",
        "description": "Get a translation evidence bundle by job id.",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "translation_validate_custody",
        "description": "Validate TranslationBundle custody fields.",
        "input_schema": {
            "type": "object",
            "properties": {"translation_bundle": {"type": "object"}},
            "required": ["translation_bundle"],
        },
    },
    {
        "name": "translation_live_smoke",
        "description": "Run one opt-in tiny live provider smoke check.",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_id": {"type": "string"},
                "source_language": {"type": "string"},
                "target_language": {"type": "string"},
                "text": {"type": "string"},
                "max_tokens": {"type": "integer"},
            },
        },
    },
    {
        "name": "translation_rank_local_models",
        "description": "Rank local OpenAI-compatible models with tiny opt-in probes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_language": {"type": "string"},
                "target_language": {"type": "string"},
                "text": {"type": "string"},
                "max_tokens": {"type": "integer"},
                "max_models": {"type": "integer"},
            },
        },
    },
    {
        "name": "translation_discover_env",
        "description": "Scan top-level env files for relevant variable names without values.",
        "input_schema": {
            "type": "object",
            "properties": {"root": {"type": "string"}},
        },
    },
    {
        "name": "translation_release_readiness_status",
        "description": "Check release readiness evidence prerequisites without changing scores.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


def call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    principal: Principal | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    effective_principal = principal or disabled_auth_principal(
        tenant_id=str(args.get("tenant_id", "standalone"))
    )
    try:
        require_mcp_tool_scope(effective_principal, name)
    except AuthError as exc:
        return {
            "is_error": True,
            "error": {
                "code": "mcp_authorization_failed",
                "message": str(exc),
            },
        }
    if name == "translation_list_engines":
        include_routing_diagnostics = bool(
            args.get("include_routing_diagnostics", False)
        )
        source_language = str(args.get("source_language", "und"))
        target_language = str(args.get("target_language", "und"))
        allow_nc_licensed = bool(args.get("allow_nc_licensed", False))
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
    if name == "translation_submit_bundle":
        try:
            tenant_id = _bound_mcp_tenant(effective_principal, args)
        except AuthError as exc:
            return _mcp_auth_error(exc)
        job = submit_document_bundle_job(
            args["document_bundle"],
            target_language=args["target_language"],
            provider_id=args.get("provider_id", "passthrough"),
            allow_nc_licensed=bool(args.get("allow_nc_licensed", False)),
            tenant_id=tenant_id,
        )
        response: dict[str, Any] = {"job": job}
        if job["status"] == "succeeded":
            response["translation_bundle"] = get_translation_job_bundle(job["job_id"])
        if job["status"] == "failed":
            response["is_error"] = True
            response["error"] = job["error"]
        return response
    if name == "translation_submit_text":
        try:
            tenant_id = _bound_mcp_tenant(effective_principal, args)
        except AuthError as exc:
            return _mcp_auth_error(exc)
        job = submit_text_job(
            str(args["text"]),
            source_language=str(args.get("source_language", "auto")),
            target_language=str(args["target_language"]),
            provider_id=str(args.get("provider_id", "passthrough")),
            source_name=str(args.get("source_name", "raw-text.txt")),
            allow_nc_licensed=bool(args.get("allow_nc_licensed", False)),
            tenant_id=tenant_id,
        )
        response = {"job": job}
        if job["status"] == "succeeded":
            response["translation_bundle"] = get_translation_job_bundle(job["job_id"])
        if job["status"] == "failed":
            response["is_error"] = True
            response["error"] = job["error"]
        return response
    if name == "translation_get_job_status":
        try:
            return {"job": get_translation_job_status(str(args["job_id"]))}
        except KeyError:
            return {
                "is_error": True,
                "error": {
                    "code": "translation_job_not_found",
                    "message": f"Translation job not found: {args['job_id']}",
                },
            }
    if name == "translation_get_bundle":
        try:
            return {"translation_bundle": get_translation_job_bundle(str(args["job_id"]))}
        except KeyError:
            return {
                "is_error": True,
                "error": {
                    "code": "translation_job_not_found",
                    "message": f"Translation job not found: {args['job_id']}",
                },
            }
        except ValueError as exc:
            return {
                "is_error": True,
                "error": {
                    "code": "translation_bundle_unavailable",
                    "message": str(exc),
                },
            }
    if name == "translation_score_pair":
        return {
            "quality": score_pair(
                str(args["source_text"]),
                str(args["translated_text"]),
                source_language=str(args.get("source_language", "und")),
                target_language=str(args.get("target_language", "und")),
            )
        }
    if name == "translation_validate_model_bundle":
        result = validate_model_bundle(
            str(args["model_dir"]),
            model_id=args.get("model_id"),
            enforce_supply_chain=bool(args.get("enforce_supply_chain", True)),
        )
        return {"model_status": result, "is_error": not result["valid"]}
    if name == "translation_get_evidence_bundle":
        try:
            return {"evidence_bundle": get_evidence_bundle(str(args["job_id"]))}
        except KeyError:
            return {
                "is_error": True,
                "error": {
                    "code": "translation_job_not_found",
                    "message": f"Translation job not found: {args['job_id']}",
                },
            }
    if name == "translation_validate_custody":
        return {
            "custody": validate_custody_payload(
                dict(args["translation_bundle"]),
            )
        }
    if name == "translation_live_smoke":
        return {
            "smoke": live_provider_smoke(
                str(args.get("provider_id", "local_openai_compat")),
                source_language=str(args.get("source_language", "en")),
                target_language=str(args.get("target_language", "fr")),
                text=str(args.get("text", "Translate this sentence.")),
                max_tokens=int(args.get("max_tokens", 64)),
            )
        }
    if name == "translation_rank_local_models":
        return {
            "models": local_model_ranking(
                source_language=str(args.get("source_language", "en")),
                target_language=str(args.get("target_language", "fr")),
                text=str(args.get("text", "Translate this sentence.")),
                max_tokens=int(args.get("max_tokens", 64)),
                max_models=int(args.get("max_models", 4)),
            )
        }
    if name == "translation_discover_env":
        return {"env_files": discover_env_contracts(root=str(args.get("root", ".")))}
    if name == "translation_release_readiness_status":
        return {"readiness": release_readiness_status()}
    raise ValueError(f"Unknown MCP tool: {name!r}")


def _bound_mcp_tenant(principal: Principal, args: dict[str, Any]) -> str:
    """MCP analogue of bind_request_tenant.

    Tenant always derived from Principal for authenticated principals (Auth tranche).
    disabled auth allows caller tenant_id for local flexibility.
    """
    requested = str(args.get("tenant_id", principal.tenant_id))
    if principal.auth_type == "disabled":
        return requested
    if requested != principal.tenant_id:
        raise AuthError(
            f"principal tenant {principal.tenant_id!r} cannot access {requested!r}"
        )
    return principal.tenant_id


def _mcp_auth_error(exc: AuthError) -> dict[str, Any]:
    return {
        "is_error": True,
        "error": {
            "code": "mcp_authorization_failed",
            "message": str(exc),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edc-translation-mcp")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--call-tool")
    parser.add_argument("--arguments-json", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_tools:
        print(json.dumps(list_tools(), indent=2))
        return 0
    if args.call_tool:
        result = call_tool(args.call_tool, json.loads(args.arguments_json))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(list_tools(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
