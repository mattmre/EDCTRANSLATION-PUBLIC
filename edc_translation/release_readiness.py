"""release readiness evidence prerequisite and rubric checks for EDC_TRANSLATION."""

from __future__ import annotations

import os
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edc_translation.auth import AuthMode, is_production_auth_mode
from edc_translation.llm_live import MOCK_LOCAL_MODEL_IDS

PRODUCTION_EVIDENCE_REQUIREMENTS = {
    "cloud-residency": {
        "env": "TRANSLATION_CLOUD_RESIDENCY_EVIDENCE",
        "kind": "typed_json",
        "description": "cloud residency, BAA, and zero-retention evidence",
        "controls": [
            "cloud_residency_approved",
            "baa_or_equivalent_reviewed",
            "zero_retention_confirmed",
        ],
    },
    "ct2-model": {
        "env": "TRANSLATION_CT2_MODEL_DIR",
        "kind": "typed_json",
        "description": "approved production CT2 model bundle evidence",
        "controls": [
            "model_directory_validated",
            "model_provenance_verified",
            "model_license_approved",
        ],
    },
    "kubeconfig": {
        "env": "KUBECONFIG",
        "kind": "typed_json",
        "description": "production or approved staging kubeconfig evidence",
        "controls": [
            "cluster_identity_recorded",
            "kubectl_context_verified",
            "operator_access_reviewed",
        ],
    },
    "live-tsa": {
        "env": "TRANSLATION_TSA_URL",
        "kind": "typed_json",
        "description": "approved RFC3161 TSA service evidence",
        "controls": [
            "tsa_url_reviewed",
            "timestamp_roundtrip_verified",
            "legal_tsa_approval_recorded",
        ],
    },
    "plugin-sandbox": {
        "env": "PLUGIN_SANDBOX_RUNTIME_PROOF",
        "kind": "typed_json",
        "description": "production plugin runtime attestation",
        "controls": [
            "sandbox_enabled",
            "filesystem_isolated",
            "network_policy_enforced",
        ],
    },
    "auth-provider": {
        "env": "TRANSLATION_AUTH_PROVIDER_EVIDENCE",
        "kind": "typed_json",
        "description": "production auth provider evidence with disabled auth rejected",
        "controls": [
            "jwt_validation_enforced",
            "ldap_or_oidc_group_mapping_verified",
            "disabled_auth_rejected",
        ],
    },
    "token-audit-store": {
        "env": "TRANSLATION_TOKEN_AUDIT_STORE_EVIDENCE",
        "kind": "typed_json",
        "description": "durable API token and audit store evidence",
        "controls": [
            "token_hashing_enabled",
            "revocation_enforced",
            "audit_events_persisted",
        ],
    },
    "cnpg-postgres": {
        "env": "TRANSLATION_CNPG_POSTGRES_EVIDENCE",
        "kind": "typed_json",
        "description": "CNPG/Postgres production datastore evidence",
        "controls": [
            "migrations_applied",
            "connection_pooling_configured",
            "retention_policy_reviewed",
        ],
    },
    "strimzi-kafka": {
        "env": "TRANSLATION_STRIMZI_KAFKA_EVIDENCE",
        "kind": "typed_json",
        "description": "Strimzi/Kafka queue evidence",
        "controls": [
            "topics_created",
            "consumer_group_verified",
            "dlq_or_retry_policy_verified",
        ],
    },
    "keda-scaling": {
        "env": "TRANSLATION_KEDA_EVIDENCE",
        "kind": "typed_json",
        "description": "KEDA scaling evidence",
        "controls": [
            "scaledobject_applied",
            "lag_metric_verified",
            "scale_test_recorded",
        ],
    },
    "argocd-gitops": {
        "env": "TRANSLATION_ARGOCD_EVIDENCE",
        "kind": "typed_json",
        "description": "ArgoCD/GitOps deployment evidence",
        "controls": [
            "application_synced",
            "drift_detection_enabled",
            "rollback_revision_recorded",
        ],
    },
    "network-rbac": {
        "env": "TRANSLATION_NETWORK_RBAC_EVIDENCE",
        "kind": "typed_json",
        "description": "Kubernetes NetworkPolicy and RBAC evidence",
        "controls": [
            "default_deny_network_policy",
            "least_privilege_service_account",
            "rbac_reviewed",
        ],
    },
    "secret-manager": {
        "env": "TRANSLATION_SECRET_MANAGER_EVIDENCE",
        "kind": "typed_json",
        "description": "external secret manager evidence",
        "controls": [
            "external_secret_source_configured",
            "no_plaintext_secret_values",
            "rotation_policy_reviewed",
        ],
    },
    "image-supply-chain": {
        "env": "TRANSLATION_IMAGE_SUPPLY_CHAIN_EVIDENCE",
        "kind": "typed_json",
        "description": "image SBOM, signature, and scan evidence",
        "controls": [
            "sbom_generated",
            "image_signature_verified",
            "critical_vulnerabilities_resolved",
        ],
    },
    "gpu-model-provenance": {
        "env": "TRANSLATION_GPU_MODEL_PROVENANCE_EVIDENCE",
        "kind": "typed_json",
        "description": "GPU scheduling and model provenance evidence",
        "controls": [
            "gpu_scheduling_verified",
            "model_provenance_verified",
            "model_quality_report_approved",
        ],
    },
    "backup-restore": {
        "env": "TRANSLATION_BACKUP_RESTORE_EVIDENCE",
        "kind": "typed_json",
        "description": "backup and restore drill evidence",
        "controls": [
            "backup_completed",
            "restore_drill_passed",
            "recovery_point_recorded",
        ],
    },
    "rollout-smoke-rollback": {
        "env": "TRANSLATION_ROLLOUT_SMOKE_ROLLBACK_EVIDENCE",
        "kind": "typed_json",
        "description": "production rollout, smoke, and rollback evidence",
        "controls": [
            "rollout_completed",
            "production_smoke_passed",
            "rollback_test_recorded",
        ],
    },
}

RELEASE_READINESS_RUBRIC = {
    "local": [
        {
            "id": "contracts-and-local-surfaces",
            "points": 40,
            "required": [
                "schema tests",
                "API/CLI/MCP tests",
                "local Helm render",
            ],
        },
        {
            "id": "local-quality-and-governance",
            "points": 30,
            "required": [
                "tenant policy tests",
                "custody/evidence tests",
                "model validation tests",
            ],
        },
        {
            "id": "local-deployment-scaffold",
            "points": 30,
            "required": [
                "worker/MCP Helm render",
                "Postgres SQL contract tests",
                "auth middleware tests",
            ],
        },
    ],
    "product_e2e": [
        {
            "id": "deployed-product-smoke",
            "points": 50,
            "required": ["deployed local stack smoke artifact"],
        },
        {
            "id": "live-provider-smoke",
            "points": 50,
            "required": ["opt-in live provider smoke artifact"],
        },
    ],
    "production_live": [
        {
            "id": "operator-and-cluster-evidence",
            "points": 30,
            "required": [
                "KUBECONFIG",
                "CNPG/Postgres evidence",
                "Strimzi/Kafka evidence",
                "KEDA evidence",
                "ArgoCD evidence",
                "GPU/operator scale evidence",
            ],
        },
        {
            "id": "model-and-quality-evidence",
            "points": 25,
            "required": [
                "approved model provenance",
                "quality evidence",
                "image SBOM/signature evidence",
            ],
        },
        {
            "id": "legal-and-custody-evidence",
            "points": 25,
            "required": [
                "TSA evidence",
                "residency/BAA/zero-retention evidence",
                "backup/restore evidence",
            ],
        },
        {
            "id": "runtime-and-security-evidence",
            "points": 20,
            "required": [
                "plugin sandbox proof",
                "auth provider evidence",
                "token/audit production evidence",
                "NetworkPolicy/RBAC evidence",
                "secret manager evidence",
                "rollout/smoke/rollback evidence",
            ],
        },
    ],
}


@dataclass(frozen=True)
class EvidenceRequirementStatus:
    requirement: str
    env: str
    kind: str
    present: bool
    valid: bool
    description: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def production_evidence_status(
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if env is None:
        env = os.environ
    return [
        _check_requirement(name, spec, env).to_dict()
        for name, spec in PRODUCTION_EVIDENCE_REQUIREMENTS.items()
    ]


def release_readiness_lane_status(
    *,
    env: dict[str, str] | None = None,
    live_smoke_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = production_evidence_status(env)
    production_ready = all(item["valid"] for item in evidence)
    live_success = any(item.get("success") for item in live_smoke_results or [])
    return {
        "local": {
            "status": "ready_for_local_review",
            "reason": "repo tests and local product-surface checks are required evidence",
        },
        "product_e2e": {
            "status": "live_provider_smoke_passed" if live_success else "needs_live_smoke",
            "reason": "at least one enabled provider smoke must pass",
        },
        "production_live": {
            "status": "ready_for_review" if production_ready else "blocked",
            "missing": [
                item["env"]
                for item in evidence
                if not item["valid"]
            ],
            "reason": "production score increase requires all external evidence",
        },
        "requirements": evidence,
    }


def release_readiness_rubric_status(
    *,
    env: dict[str, str] | None = None,
    live_smoke_results: list[dict[str, Any]] | None = None,
    live_smoke_artifact: str | None = None,
    manual_review_artifact: str | None = None,
    local_evidence_artifact: str | None = None,
    product_e2e_artifact: str | None = None,
) -> dict[str, Any]:
    """Return a lane-separated release readiness rubric without auto-claiming 100."""

    live_artifact = live_smoke_artifact_status(live_smoke_artifact)
    effective_live_results = list(live_smoke_results or [])
    if live_artifact["valid"]:
        effective_live_results.append({"success": True})
    lanes = release_readiness_lane_status(env=env, live_smoke_results=effective_live_results)
    local_artifact = local_evidence_artifact_status(local_evidence_artifact)
    product_artifact = product_e2e_artifact_status(product_e2e_artifact)
    local_score = 100 if local_artifact["valid"] else 0
    product_score = 0
    if product_artifact["valid"]:
        product_score += 50
    if lanes["product_e2e"]["status"] == "live_provider_smoke_passed":
        product_score += 50
    production_score = (
        100 if lanes["production_live"]["status"] == "ready_for_review" else 0
    )
    manual_review_valid = bool(
        manual_review_artifact and Path(manual_review_artifact).is_file()
    )
    blockers: list[str] = []
    if local_score < 100:
        blockers.append("local lane requires a recorded local validation artifact")
    if product_score < 100:
        blockers.append("product_e2e requires both deployed/demo E2E and live smoke artifacts")
    if production_score < 100:
        blockers.extend(lanes["production_live"].get("missing", []))
    if not manual_review_valid:
        blockers.append("manual reviewed score artifact is required before 100 claim")

    claimable_100 = (
        local_score == 100
        and product_score == 100
        and production_score == 100
        and manual_review_valid
    )
    total_score = min(local_score, product_score, production_score)
    if not claimable_100:
        total_score = min(total_score, 99)

    return {
        "rubric_version": "2026-05-16",
        "rubric": RELEASE_READINESS_RUBRIC,
        "lanes": {
            "local": {
                "status": lanes["local"]["status"],
                "score": local_score,
                "reason": (
                    "recorded local validation artifact passed"
                    if local_artifact["valid"]
                    else "local score requires a recorded validation artifact"
                ),
                "artifact": local_artifact,
            },
            "product_e2e": {
                "status": (
                    "demo_e2e_artifact_passed"
                    if product_artifact["valid"]
                    else lanes["product_e2e"]["status"]
                ),
                "score": product_score,
                "reason": (
                    "recorded demo/deployed E2E artifact passed"
                    if product_artifact["valid"]
                    else lanes["product_e2e"]["reason"]
                ),
                "artifact": product_artifact,
                "live_smoke_artifact": live_artifact,
                "live_smoke_passed": lanes["product_e2e"]["status"] == "live_provider_smoke_passed",
            },
            "production_live": {
                "status": lanes["production_live"]["status"],
                "score": production_score,
                "reason": lanes["production_live"]["reason"],
                "missing": lanes["production_live"].get("missing", []),
            },
        },
        "manual_review": {
            "artifact": manual_review_artifact or "",
            "valid": manual_review_valid,
        },
        "total_score": total_score,
        "claimable_100": claimable_100,
        "blockers": blockers,
    }


def release_readiness_manifest(
    *,
    env: dict[str, str] | None = None,
    live_smoke_results: list[dict[str, Any]] | None = None,
    live_smoke_artifact: str | None = None,
    manual_review_artifact: str | None = None,
    local_evidence_artifact: str | None = None,
    product_e2e_artifact: str | None = None,
) -> dict[str, Any]:
    """Return a bounded release readiness manifest without evidence values or file paths."""

    status = release_readiness_rubric_status(
        env=env,
        live_smoke_results=live_smoke_results,
        live_smoke_artifact=live_smoke_artifact,
        manual_review_artifact=manual_review_artifact,
        local_evidence_artifact=local_evidence_artifact,
        product_e2e_artifact=product_e2e_artifact,
    )
    env_names = [
        spec["env"]
        for spec in PRODUCTION_EVIDENCE_REQUIREMENTS.values()
    ]
    production_requirements = production_evidence_status(env)
    return {
        "manifest_version": "2026-05-16",
        "timestamp": datetime.now(UTC).isoformat(),
        "env_var_names": env_names,
        "production_requirements": [
            {
                "requirement": item["requirement"],
                "env": item["env"],
                "present": item["present"],
                "valid": item["valid"],
                "reason": item["reason"],
            }
            for item in production_requirements
        ],
        "blockers": status["blockers"],
        "claimable_100": status["claimable_100"],
        "local_evidence_artifact_valid": status["lanes"]["local"]["artifact"]["valid"],
        "product_e2e_artifact_valid": status["lanes"]["product_e2e"]["artifact"]["valid"],
        "live_smoke_artifact_valid": status["lanes"]["product_e2e"]["live_smoke_artifact"]["valid"],
    }


def local_evidence_artifact_status(artifact_path: str | None) -> dict[str, Any]:
    required_commands = {
        "pytest",
        "ruff",
        "helm_template_default",
        "helm_template_production",
        "readiness_run_nonclaimable",
    }
    if not artifact_path:
        return {
            "path": "",
            "valid": False,
            "reason": "missing local evidence artifact path",
            "missing_commands": sorted(required_commands),
        }
    path = Path(artifact_path)
    if not path.is_file():
        return {
            "path": str(path),
            "valid": False,
            "reason": "local evidence artifact file does not exist",
            "missing_commands": sorted(required_commands),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "valid": False,
            "reason": f"local evidence artifact is not valid JSON: {exc.msg}",
            "missing_commands": sorted(required_commands),
        }
    observed = {
        str(command.get("id") if isinstance(command, dict) else command)
        for command in payload.get("commands", [])
    }
    missing = sorted(required_commands - observed)
    valid = bool(
        payload.get("artifact_type") == "edc_translation_local_evidence"
        and payload.get("status") == "passed"
        and not missing
        and str(payload.get("reviewed_by", "")).strip()
        and str(payload.get("timestamp", "")).strip()
    )
    return {
        "path": str(path),
        "valid": valid,
        "reason": "artifact passed required local validation commands" if valid else "artifact missing required local evidence fields",
        "missing_commands": missing,
    }


def product_e2e_artifact_status(artifact_path: str | None) -> dict[str, Any]:
    required_surfaces = {
        "api",
        "cli",
        "mcp",
        "python_client",
        "custody_evidence",
        "readiness_product_e2e",
    }
    if not artifact_path:
        return {
            "path": "",
            "valid": False,
            "reason": "missing product E2E artifact path",
            "missing_surfaces": sorted(required_surfaces),
        }
    path = Path(artifact_path)
    if not path.is_file():
        return {
            "path": str(path),
            "valid": False,
            "reason": "product E2E artifact file does not exist",
            "missing_surfaces": sorted(required_surfaces),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "valid": False,
            "reason": f"product E2E artifact is not valid JSON: {exc.msg}",
            "missing_surfaces": sorted(required_surfaces),
        }
    observed = {str(surface) for surface in payload.get("surfaces", [])}
    missing = sorted(required_surfaces - observed)
    dataset = payload.get("dataset", {})
    commands = payload.get("commands", [])
    valid = bool(
        payload.get("artifact_type") == "edc_translation_product_e2e"
        and payload.get("status") == "passed"
        and str(payload.get("reviewed_by", "")).strip()
        and str(payload.get("timestamp", "")).strip()
        and bool(dataset.get("license"))
        and bool(commands)
        and not missing
    )
    return {
        "path": str(path),
        "valid": valid,
        "reason": (
            "artifact passed required product E2E surfaces"
            if valid
            else "artifact missing required reviewed product E2E fields"
        ),
        "missing_surfaces": missing,
        "dataset_name": str(dataset.get("name", "")),
        "dataset_license": str(dataset.get("license", "")),
    }


def live_smoke_artifact_status(artifact_path: str | None) -> dict[str, Any]:
    if not artifact_path:
        return {
            "path": "",
            "valid": False,
            "reason": "missing live smoke artifact path",
        }
    path = Path(artifact_path)
    if not path.is_file():
        return {
            "path": str(path),
            "valid": False,
            "reason": "live smoke artifact file does not exist",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "valid": False,
            "reason": f"live smoke artifact is not valid JSON: {exc.msg}",
        }
    smoke = payload.get("smoke", {})
    reason = _live_smoke_artifact_invalid_reason(payload)
    valid = reason == ""
    return {
        "path": str(path),
        "valid": valid,
        "reason": "artifact passed required live smoke fields" if valid else reason,
        "provider_id": str(smoke.get("provider_id", "")) if isinstance(smoke, dict) else "",
        "model_id": str(smoke.get("model_id", "")) if isinstance(smoke, dict) else "",
    }


def _live_smoke_artifact_invalid_reason(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "live smoke artifact must be a JSON object"
    if payload.get("artifact_type") != "edc_translation_live_smoke":
        return "artifact_type must be edc_translation_live_smoke"
    if payload.get("status") != "passed":
        return "artifact status must be passed"
    if not str(payload.get("reviewed_by", "")).strip():
        return "artifact reviewed_by is required"
    if not str(payload.get("timestamp", "")).strip():
        return "artifact timestamp is required"

    smoke = payload.get("smoke", {})
    if not isinstance(smoke, dict):
        return "artifact smoke must be a JSON object"
    if smoke.get("success") is not True:
        return "artifact smoke.success must be true"
    provider_id = str(smoke.get("provider_id", "")).strip()
    model_id = str(smoke.get("model_id", "")).strip()
    if not provider_id:
        return "artifact smoke.provider_id is required"
    if not model_id:
        return "artifact smoke.model_id is required"
    if provider_id == "local_openai_compat":
        return _local_runtime_smoke_invalid_reason(payload, model_id)
    return ""


def _local_runtime_smoke_invalid_reason(payload: dict[str, Any], model_id: str) -> str:
    mock_model_ids = {mock_model_id.casefold() for mock_model_id in MOCK_LOCAL_MODEL_IDS}
    if model_id.casefold() in mock_model_ids:
        return "mock local smoke model is not approved local GPU/runtime evidence"
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        return "local OpenAI-compatible smoke artifacts require runtime evidence"
    if runtime.get("runtime_kind") != "local_openai_compatible_gpu":
        return "runtime_kind must be local_openai_compatible_gpu"
    if runtime.get("approved_runtime") is not True:
        return "runtime approved_runtime must be true"
    if runtime.get("mock_runtime") is True:
        return "mock runtime is not approved local GPU/runtime evidence"
    if not str(runtime.get("model_provenance_ref", "")).strip():
        return "runtime model_provenance_ref is required"

    gpu = runtime.get("gpu_readiness")
    if not isinstance(gpu, dict):
        return "runtime gpu_readiness is required"
    if gpu.get("available") is not True or int(gpu.get("gpu_count") or 0) < 1:
        return "runtime gpu_readiness must show at least one available GPU"
    return ""


def _check_requirement(
    name: str,
    spec: dict[str, str],
    env: dict[str, str],
) -> EvidenceRequirementStatus:
    env_name = spec["env"]
    kind = spec["kind"]
    raw_value = env.get(env_name, "").strip()
    if not raw_value:
        return EvidenceRequirementStatus(
            requirement=name,
            env=env_name,
            kind=kind,
            present=False,
            valid=False,
            description=spec["description"],
            reason=f"missing {env_name}",
        )

    return _check_typed_json_requirement(name, spec, raw_value)


def _check_typed_json_requirement(
    name: str,
    spec: dict[str, Any],
    raw_value: str,
) -> EvidenceRequirementStatus:
    path = Path(raw_value)
    if not path.is_file():
        return EvidenceRequirementStatus(
            requirement=name,
            env=spec["env"],
            kind=spec["kind"],
            present=True,
            valid=False,
            description=spec["description"],
            reason="configured evidence artifact file does not exist",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return EvidenceRequirementStatus(
            requirement=name,
            env=spec["env"],
            kind=spec["kind"],
            present=True,
            valid=False,
            description=spec["description"],
            reason=f"evidence artifact is not valid JSON: {exc.msg}",
        )

    reason = _typed_artifact_invalid_reason(name, spec, payload)
    return EvidenceRequirementStatus(
        requirement=name,
        env=spec["env"],
        kind=spec["kind"],
        present=True,
        valid=reason == "",
        description=spec["description"],
        reason="typed production evidence artifact validated" if reason == "" else reason,
    )


def _typed_artifact_invalid_reason(
    name: str,
    spec: dict[str, Any],
    payload: Any,
) -> str:
    if not isinstance(payload, dict):
        return "evidence artifact must be a JSON object"
    if payload.get("artifact_type") != "edc_translation_production_evidence":
        return "artifact_type must be edc_translation_production_evidence"
    if payload.get("requirement") != name:
        return f"artifact requirement must be {name}"
    env = payload.get("environment")
    status = payload.get("status")
    if status not in {"passed", "approved"}:
        return "artifact status must be passed or approved"
    if env not in {"production", "approved_staging"}:
        return "artifact environment must be production or approved_staging"
    if not str(payload.get("reviewed_by", "")).strip():
        return "artifact reviewed_by is required"
    if not str(payload.get("timestamp", "")).strip():
        return "artifact timestamp is required"

    controls = payload.get("controls", [])
    if not isinstance(controls, list):
        return "artifact controls must be a list"
    for control in controls:
        if not isinstance(control, dict):
            return "artifact controls must be structured objects"
        if control.get("passed") is not True:
            return "artifact controls must have passed=true"
        if not str(control.get("evidence_ref", "")).strip():
            return "artifact controls must include evidence_ref"
        if not str(control.get("command", "")).strip():
            return "artifact controls must include command"
    observed = {str(control.get("id")) for control in controls}
    required = {str(control) for control in spec.get("controls", [])}
    missing_controls = sorted(required - observed)
    if missing_controls:
        return "artifact missing controls: " + ", ".join(missing_controls)

    if name == "auth-provider":
        auth_mode = str(payload.get("auth_mode", AuthMode.DISABLED.value))
        if not is_production_auth_mode(auth_mode):
            return "auth provider evidence must reject disabled auth"
    return ""
