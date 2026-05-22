"""Local governance repositories for tenant policy, glossaries, and instructions."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any


DEFAULT_TENANT_ID = "standalone"
DEFAULT_INSTRUCTION_SET_ID = "baseline-legal-neutral"


@dataclass
class TenantPolicy:
    tenant_id: str = DEFAULT_TENANT_ID
    default_provider_id: str = "passthrough"
    allow_nc_licensed: bool = False
    allowed_provider_families: list[str] = field(
        default_factory=lambda: [
            "passthrough",
            "ct2_nmt",
            "llm_local",
            "quality_estimation",
        ]
    )
    blocked_provider_families: list[str] = field(default_factory=lambda: ["llm_cloud"])
    approved_instruction_set_ids: list[str] = field(
        default_factory=lambda: [DEFAULT_INSTRUCTION_SET_ID]
    )
    glossary_ids: list[str] = field(default_factory=list)
    cloud_residency_evidence_required: bool = True
    retention_policy: str = "process_local_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Glossary:
    glossary_id: str
    name: str
    source_language: str
    target_language: str
    entries: dict[str, str]
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstructionSet:
    instruction_set_id: str
    version: str
    allowed_engine_families: list[str]
    document_classes: list[str]
    target_language_constraints: list[str]
    template: str
    deterministic_settings: dict[str, Any]
    safety_constraints: list[str]
    approval: dict[str, Any]
    deprecated: bool = False

    @property
    def template_sha256(self) -> str:
        return hashlib.sha256(self.template.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["template_sha256"] = self.template_sha256
        return payload


class TenantPolicyRepository:
    def __init__(self) -> None:
        self._policies: dict[str, TenantPolicy] = {
            DEFAULT_TENANT_ID: TenantPolicy(),
        }
        self._lock = Lock()

    def get(self, tenant_id: str = DEFAULT_TENANT_ID) -> TenantPolicy:
        with self._lock:
            return self._policies.setdefault(tenant_id, TenantPolicy(tenant_id=tenant_id))

    def set(self, policy: TenantPolicy) -> TenantPolicy:
        with self._lock:
            self._policies[policy.tenant_id] = policy
            return policy

    def update(self, tenant_id: str, updates: dict[str, Any]) -> TenantPolicy:
        current = self.get(tenant_id)
        payload = current.to_dict()
        allowed_fields = set(payload)
        for key, value in updates.items():
            if key in allowed_fields and key != "tenant_id":
                payload[key] = value
        payload["tenant_id"] = tenant_id
        return self.set(TenantPolicy(**payload))


class GlossaryRepository:
    def __init__(self) -> None:
        self._glossaries: dict[str, Glossary] = {}
        self._lock = Lock()

    def upsert(self, glossary: Glossary) -> Glossary:
        with self._lock:
            self._glossaries[glossary.glossary_id] = glossary
            return glossary

    def get(self, glossary_id: str) -> Glossary:
        with self._lock:
            return self._glossaries[glossary_id]

    def list(self) -> list[Glossary]:
        with self._lock:
            return list(self._glossaries.values())

    def delete(self, glossary_id: str) -> None:
        with self._lock:
            del self._glossaries[glossary_id]


class InstructionSetRepository:
    def __init__(self) -> None:
        default = InstructionSet(
            instruction_set_id=DEFAULT_INSTRUCTION_SET_ID,
            version="1.0.0",
            allowed_engine_families=["passthrough", "ct2_nmt", "llm_local"],
            document_classes=["general", "legal", "edc"],
            target_language_constraints=["*"],
            template=(
                "Translate faithfully, preserve legal meaning, preserve span "
                "boundaries, and do not add facts."
            ),
            deterministic_settings={"temperature": 0, "seed": 42},
            safety_constraints=[
                "no_unapproved_cloud_routing",
                "preserve_privilege_markers",
                "emit_translation_bundle_v1_only",
            ],
            approval={
                "status": "approved",
                "approved_by": "local-skeleton-policy",
                "approved_at": "2026-05-14T00:00:00Z",
            },
        )
        self._instruction_sets: dict[str, InstructionSet] = {
            default.instruction_set_id: default,
        }
        self._lock = Lock()

    def get(self, instruction_set_id: str) -> InstructionSet:
        with self._lock:
            return self._instruction_sets[instruction_set_id]

    def list(self) -> list[InstructionSet]:
        with self._lock:
            return list(self._instruction_sets.values())

    def upsert(self, instruction_set: InstructionSet) -> InstructionSet:
        with self._lock:
            self._instruction_sets[instruction_set.instruction_set_id] = instruction_set
            return instruction_set


def find_glossary_hits(text: str, glossaries: list[Glossary]) -> list[str]:
    lowered = text.casefold()
    hits: list[str] = []
    for glossary in glossaries:
        if not glossary.approved:
            continue
        for term in glossary.entries:
            if term.casefold() in lowered:
                hits.append(f"{glossary.glossary_id}:{term}")
    return hits
