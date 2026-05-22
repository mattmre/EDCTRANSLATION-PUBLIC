"""Command-line interface for EDC_TRANSLATION."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edc_translation.release_readiness import release_readiness_manifest, release_readiness_rubric_status
from edc_translation.errors import auto_route_error_payload
from edc_translation.routing import RoutingError
from edc_translation.service import (
    release_readiness_status,
    discover_env_contracts,
    engine_routing_diagnostics,
    get_evidence_bundle,
    get_tenant_policy,
    get_translation_job_bundle,
    get_translation_job_status,
    list_glossaries,
    list_instruction_sets,
    list_model_statuses,
    list_engine_providers,
    live_provider_smoke,
    local_model_ranking,
    local_runtime_readiness,
    record_review_decision,
    score_pair,
    submit_document_bundle_job,
    submit_text_job,
    translate_document_bundle,
    update_tenant_policy,
    upsert_glossary,
    validate_custody_payload,
    validate_model_bundle,
    _auth_store_backend,
    _job_backend,
    _model_registry_backend,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edc-translation")
    sub = parser.add_subparsers(dest="command", required=True)

    list_engines = sub.add_parser(
        "list-engines",
        help="List available provider engines.",
    )
    list_engines.add_argument(
        "--include-routing-diagnostics",
        action="store_true",
        help="Include auto-routing diagnostics in engine output.",
    )
    list_engines.add_argument("--source", default="und", help="Source language tag.")
    list_engines.add_argument("--target", default="und", help="Target language tag.")
    list_engines.add_argument(
        "--allow-nc-licensed",
        action="store_true",
        help="Allow non-commercial licensed engines in routing diagnostics.",
    )

    smoke = sub.add_parser(
        "smoke-auto-route",
        help="Fail if provider auto-routing cannot select an engine.",
    )
    smoke.add_argument("--source", default="en", help="Source language tag.")
    smoke.add_argument("--target", default="fr", help="Target language tag.")
    smoke.add_argument(
        "--allow-nc-licensed",
        action="store_true",
        help="Allow non-commercial licensed engines during auto-route smoke.",
    )

    translate = sub.add_parser("translate", help="Translate a DocumentBundle JSON file.")
    translate.add_argument("bundle", help="Path to DocumentBundle v1 JSON.")
    translate.add_argument("--target", required=True, help="Target language tag.")
    translate.add_argument("--provider", default="passthrough", help="Provider id.")
    translate.add_argument(
        "--engine",
        dest="provider",
        default=argparse.SUPPRESS,
        help="Alias for --provider.",
    )
    translate.add_argument(
        "--allow-nc-licensed",
        action="store_true",
        help="Allow non-commercial licensed engines during provider auto-routing.",
    )
    translate.add_argument("--out", help="Optional output path for TranslationBundle JSON.")

    submit_bundle = sub.add_parser(
        "submit-bundle",
        help="Submit a DocumentBundle translation job to the local job store.",
    )
    submit_bundle.add_argument("bundle", help="Path to DocumentBundle v1 JSON.")
    submit_bundle.add_argument("--target", required=True, help="Target language tag.")
    submit_bundle.add_argument("--provider", default="passthrough", help="Provider id.")
    submit_bundle.add_argument(
        "--engine",
        dest="provider",
        default=argparse.SUPPRESS,
        help="Alias for --provider.",
    )
    submit_bundle.add_argument(
        "--allow-nc-licensed",
        action="store_true",
        help="Allow non-commercial licensed engines during provider auto-routing.",
    )

    job_status = sub.add_parser("job-status", help="Get local translation job status.")
    job_status.add_argument("job_id", help="Translation job id.")

    get_bundle = sub.add_parser(
        "get-bundle",
        help="Get a completed TranslationBundle from the local job store.",
    )
    get_bundle.add_argument("job_id", help="Translation job id.")
    get_bundle.add_argument("--out", help="Optional output path for TranslationBundle JSON.")

    submit_text = sub.add_parser("submit-text", help="Submit a raw text translation job.")
    submit_text.add_argument("text", help="Raw source text.")
    submit_text.add_argument(
        "--source",
        default="auto",
        help="Source language tag, or auto to identify the submitted text.",
    )
    submit_text.add_argument("--target", required=True, help="Target language tag.")
    submit_text.add_argument("--provider", default="passthrough", help="Provider id.")
    submit_text.add_argument(
        "--engine",
        dest="provider",
        default=argparse.SUPPRESS,
        help="Alias for --provider.",
    )
    submit_text.add_argument("--source-name", default="raw-text.txt")
    submit_text.add_argument("--allow-nc-licensed", action="store_true")

    score = sub.add_parser("score-pair", help="Score a source/translation pair.")
    score.add_argument("--source", required=True, help="Path to source text file.")
    score.add_argument("--target", required=True, help="Path to translated text file.")
    score.add_argument("--source-language", default="auto")
    score.add_argument("--target-language", default="und")

    verify = sub.add_parser("verify-model-bundle", help="Validate a local model bundle.")
    verify.add_argument("model_dir", help="Model bundle directory.")
    verify.add_argument("--model-id")
    verify.add_argument("--allow-unverified", action="store_true")

    evidence = sub.add_parser("evidence-bundle", help="Get evidence bundle for a job.")
    evidence.add_argument("job_id")

    custody = sub.add_parser("validate-custody", help="Validate TranslationBundle custody.")
    custody.add_argument("bundle", help="Path to TranslationBundle v1 JSON.")

    tenant = sub.add_parser("tenant-policy", help="Get or update tenant policy.")
    tenant.add_argument("tenant_id")
    tenant.add_argument("--set-json", help="JSON object of policy fields to update.")

    glossaries = sub.add_parser("glossaries", help="List or upsert glossaries.")
    glossaries.add_argument("--upsert-json", help="Path to glossary JSON payload.")

    sub.add_parser("instruction-sets", help="List instruction sets.")

    sub.add_parser("model-status", help="List validated model statuses.")

    review = sub.add_parser("review-job", help="Record a review/certification decision.")
    review.add_argument("job_id")
    review.add_argument("--decision", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--notes", default="")

    live_smoke = sub.add_parser(
        "live-smoke",
        help="Run one opt-in tiny live provider smoke check.",
    )
    live_smoke.add_argument("--provider", default="local_openai_compat")
    live_smoke.add_argument("--source", default="en")
    live_smoke.add_argument("--target", default="fr")
    live_smoke.add_argument("--text", default="Translate this sentence.")
    live_smoke.add_argument("--max-tokens", type=int, default=64)

    rank_local = sub.add_parser(
        "rank-local-models",
        help="Rank discovered local OpenAI-compatible models with tiny probes.",
    )
    rank_local.add_argument("--source", default="en")
    rank_local.add_argument("--target", default="fr")
    rank_local.add_argument("--text", default="Translate this sentence.")
    rank_local.add_argument("--max-tokens", type=int, default=64)
    rank_local.add_argument("--max-models", type=int, default=4)

    runtime_readiness = sub.add_parser(
        "runtime-readiness",
        help="Probe local GPU/runtime readiness without loading or downloading models.",
    )
    runtime_readiness.add_argument("--provider", default="local_openai_compat")

    discover_env = sub.add_parser(
        "discover-env",
        help="List top-level env files and relevant variable names without values.",
    )
    discover_env.add_argument("--root", default=".")

    sub.add_parser(
        "readiness-check",
        help="Check release readiness evidence prerequisites without changing scores.",
    )
    readiness_run = sub.add_parser(
        "readiness-run",
        help="Run the lane-separated release readiness rubric without auto-claiming 100.",
    )
    readiness_run.add_argument("--manual-review-artifact", default="")
    readiness_run.add_argument("--local-evidence-artifact", default="")
    readiness_run.add_argument("--product-e2e-artifact", default="")
    readiness_run.add_argument("--live-smoke-artifact", default="")
    readiness_run.add_argument("--out", help="Optional output path for bounded release readiness manifest JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "list-engines":
        payload: dict[str, object] = {
            "engines": list_engine_providers(
                include_routing_diagnostics=args.include_routing_diagnostics,
                source_language=args.source,
                target_language=args.target,
                allow_nc_licensed=args.allow_nc_licensed,
            )
        }
        if args.include_routing_diagnostics:
            payload["routing_diagnostics"] = engine_routing_diagnostics(
                source_language=args.source,
                target_language=args.target,
                allow_nc_licensed=args.allow_nc_licensed,
            )
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "smoke-auto-route":
        diagnostics = engine_routing_diagnostics(
            source_language=args.source,
            target_language=args.target,
            allow_nc_licensed=args.allow_nc_licensed,
        )
        print(json.dumps({"routing_diagnostics": diagnostics}, indent=2))
        if diagnostics["selected_provider_id"]:
            return 0

        detail = "; ".join(
            f"{candidate['id']}: {candidate['reason']}"
            for candidate in diagnostics["candidates"]
        )
        print(
            "No auto-routeable translation engine selected"
            f" for {args.source}->{args.target}: {detail}",
            file=sys.stderr,
        )
        return 1

    if args.command == "translate":
        bundle_path = Path(args.bundle)
        document_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        try:
            translation_bundle = translate_document_bundle(
                document_bundle,
                target_language=args.target,
                provider_id=args.provider,
                allow_nc_licensed=args.allow_nc_licensed,
            )
        except RoutingError as exc:
            print(
                json.dumps(
                    auto_route_error_payload(str(exc), exc.diagnostics),
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        rendered = json.dumps(translation_bundle, ensure_ascii=False, indent=2)
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.command == "submit-bundle":
        bundle_path = Path(args.bundle)
        document_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        job = submit_document_bundle_job(
            document_bundle,
            target_language=args.target,
            provider_id=args.provider,
            allow_nc_licensed=args.allow_nc_licensed,
        )
        print(json.dumps({"job": job}, ensure_ascii=False, indent=2))
        return 0 if job["status"] == "succeeded" else 1

    if args.command == "job-status":
        try:
            job = get_translation_job_status(args.job_id)
        except KeyError:
            print(f"Translation job not found: {args.job_id}", file=sys.stderr)
            return 1
        print(json.dumps({"job": job}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "get-bundle":
        try:
            translation_bundle = get_translation_job_bundle(args.job_id)
        except KeyError:
            print(f"Translation job not found: {args.job_id}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        rendered = json.dumps(translation_bundle, ensure_ascii=False, indent=2)
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.command == "submit-text":
        job = submit_text_job(
            args.text,
            source_language=args.source,
            target_language=args.target,
            source_name=args.source_name,
            provider_id=args.provider,
            allow_nc_licensed=args.allow_nc_licensed,
        )
        print(json.dumps({"job": job}, ensure_ascii=False, indent=2))
        return 0 if job["status"] == "succeeded" else 1

    if args.command == "score-pair":
        source = Path(args.source).read_text(encoding="utf-8")
        target = Path(args.target).read_text(encoding="utf-8")
        print(
            json.dumps(
                {
                    "quality": score_pair(
                        source,
                        target,
                        source_language=args.source_language,
                        target_language=args.target_language,
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "verify-model-bundle":
        result = validate_model_bundle(
            args.model_dir,
            model_id=args.model_id,
            enforce_supply_chain=not args.allow_unverified,
        )
        print(json.dumps({"model_status": result}, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1

    if args.command == "evidence-bundle":
        try:
            evidence = get_evidence_bundle(args.job_id)
        except KeyError:
            print(f"Translation job not found: {args.job_id}", file=sys.stderr)
            return 1
        print(json.dumps({"evidence_bundle": evidence}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-custody":
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"custody": validate_custody_payload(bundle)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "tenant-policy":
        if args.set_json:
            policy = update_tenant_policy(args.tenant_id, json.loads(args.set_json))
        else:
            policy = get_tenant_policy(args.tenant_id)
        print(json.dumps({"tenant_policy": policy}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "glossaries":
        if args.upsert_json:
            payload = json.loads(Path(args.upsert_json).read_text(encoding="utf-8"))
            result: object = upsert_glossary(payload)
            print(json.dumps({"glossary": result}, ensure_ascii=False, indent=2))
        else:
            print(
                json.dumps(
                    {"glossaries": list_glossaries()},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if args.command == "instruction-sets":
        print(
            json.dumps(
                {"instruction_sets": list_instruction_sets()},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "model-status":
        print(json.dumps({"models": list_model_statuses()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "review-job":
        try:
            review = record_review_decision(
                args.job_id,
                decision=args.decision,
                reviewer=args.reviewer,
                notes=args.notes,
            )
        except KeyError:
            print(f"Translation job not found: {args.job_id}", file=sys.stderr)
            return 1
        print(json.dumps({"review": review}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "live-smoke":
        result = live_provider_smoke(
            args.provider,
            source_language=args.source,
            target_language=args.target,
            text=args.text,
            max_tokens=args.max_tokens,
        )
        print(json.dumps({"smoke": result}, ensure_ascii=False, indent=2))
        return 0 if result["success"] else 1

    if args.command == "rank-local-models":
        result = local_model_ranking(
            source_language=args.source,
            target_language=args.target,
            text=args.text,
            max_tokens=args.max_tokens,
            max_models=args.max_models,
        )
        print(json.dumps({"models": result}, ensure_ascii=False, indent=2))
        return 0 if any(item.get("success") for item in result) else 1

    if args.command == "runtime-readiness":
        result = local_runtime_readiness(provider_id=args.provider)
        print(json.dumps({"runtime_readiness": result}, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1

    if args.command == "discover-env":
        print(
            json.dumps(
                {
                    "env_files": discover_env_contracts(root=args.root),
                    "job_backend": _job_backend(),
                    "job_backend_env": "EDC_TRANSLATION_JOB_BACKEND",
                    "auth_store_backend": _auth_store_backend(),
                    "auth_store_backend_env": "EDC_TRANSLATION_AUTH_STORE_BACKEND",
                    "model_registry_backend": _model_registry_backend(),
                    "model_registry_backend_env": "EDC_TRANSLATION_MODEL_REGISTRY_BACKEND",
                    "note": "set to 'postgres' (after pip install '.[postgres]') to use durable Postgres*Store for jobs/queues/tokens/audit/models; 'json' for file-backed token/audit; model registry defaults to job backend when postgres",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "readiness-check":
        result = release_readiness_status()
        print(json.dumps({"readiness": result}, ensure_ascii=False, indent=2))
        return 0 if result["production_live"]["status"] == "ready_for_review" else 1

    if args.command == "readiness-run":
        result = release_readiness_rubric_status(
            manual_review_artifact=args.manual_review_artifact or None,
            local_evidence_artifact=args.local_evidence_artifact or None,
            product_e2e_artifact=args.product_e2e_artifact or None,
            live_smoke_artifact=args.live_smoke_artifact or None,
        )
        if args.out:
            manifest = release_readiness_manifest(
                manual_review_artifact=args.manual_review_artifact or None,
                local_evidence_artifact=args.local_evidence_artifact or None,
                product_e2e_artifact=args.product_e2e_artifact or None,
                live_smoke_artifact=args.live_smoke_artifact or None,
            )
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps({"readiness_rubric": result}, ensure_ascii=False, indent=2))
        return 0 if result["claimable_100"] else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
