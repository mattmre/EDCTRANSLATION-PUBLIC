"""Translation engine registry."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edc_translation.engines.base import TranslationEngine

ENGINE_REGISTRY: dict[str, type["TranslationEngine"]] = {}


def register_engine(cls: type["TranslationEngine"]) -> type["TranslationEngine"]:
    """Register an engine class by ``capability.id``."""

    ENGINE_REGISTRY[cls.capability.id] = cls
    return cls


def get_engine(engine_id: str) -> type["TranslationEngine"]:
    """Return the registered engine class for *engine_id*."""

    try:
        return ENGINE_REGISTRY[engine_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown translation engine: {engine_id!r}. "
            f"Registered: {sorted(ENGINE_REGISTRY)}"
        ) from exc


def iter_engines():
    """Iterate ``(engine_id, engine_class)`` pairs."""

    return ENGINE_REGISTRY.items()


def _register_builtin_engines() -> None:
    importlib.import_module("edc_translation.engines.passthrough")
    importlib.import_module("edc_translation.engines.stub")
    importlib.import_module("edc_translation.engines.deterministic_ci")
    importlib.import_module("edc_translation.engines.local_ct2_opus")
    importlib.import_module("edc_translation.engines.local_ct2_nllb")
    importlib.import_module("edc_translation.engines.local_ct2_madlad")
    importlib.import_module("edc_translation.engines.local_openai_compat")
    importlib.import_module("edc_translation.engines.openrouter_llm")
    importlib.import_module("edc_translation.engines.google_gemini")


_register_builtin_engines()
