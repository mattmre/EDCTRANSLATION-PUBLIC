"""Core dataclasses for translation contracts.

These are the pure Python translation models extracted first from the
current OCR repo.  They intentionally carry no engine imports, no FastAPI
objects, and no persistence assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class EngineCapability:
    """Immutable descriptor of a translation engine's capabilities."""

    id: str
    is_local: bool
    is_cloud: bool
    supports_pairs: list[tuple[str, str]] | str
    quality_class: Literal["draft", "standard", "legal"]
    latency_class: Literal["realtime", "standard", "bulk"]
    license: str
    provider_retention_class: Literal[
        "local_only",
        "zero_retention_with_baa",
        "retention_enabled",
        "unknown",
    ]
    deployment_envs: list[str]
    cost_per_1m_chars_usd: float | None = None
    cost_per_1m_tokens_usd: float | None = None
    handles_handwriting_natively: bool = False


@dataclass
class SpanTranslation:
    """Translation for a single OCR span."""

    span_id: str
    source_text: str
    target_text: str
    source_bbox: list[float]
    source_bboxes: list[list[float]]
    source_language: str
    target_language: str
    confidence: float
    quality_score: float | None
    engine_id: str
    glossary_hits: list[str] = field(default_factory=list)


@dataclass
class PageTranslation:
    """All span translations for a single page."""

    page_num: int
    spans: list[SpanTranslation] = field(default_factory=list)


@dataclass
class DocumentTranslation:
    """Legacy sidecar-compatible document translation model."""

    schema_version: str
    document_id: str
    source_file: str
    source_language: str
    target_language: str
    certified: bool = False
    engine: dict = field(default_factory=dict)
    glossary: dict | None = None
    quality: dict = field(default_factory=dict)
    pages: list[PageTranslation] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    custody: dict = field(default_factory=dict)
    processing: dict = field(default_factory=dict)


@dataclass
class TranslationRequest:
    """Caller-side request describing desired translation behavior."""

    src_lang: str
    tgt_lang: str
    quality: str = "standard"
    latency: str = "standard"
    privilege_flag: bool = False
    tenant_id: str = "default"
