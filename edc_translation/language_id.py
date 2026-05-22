"""Language identification helpers for local text translation workflows."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


FASTTEXT_LID_MODEL_ENV = "EDC_TRANSLATION_FASTTEXT_LID_MODEL"


@dataclass(frozen=True)
class LanguageDetection:
    language: str
    confidence: float
    provider: str
    model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_language(
    text: str,
    *,
    model_path: str | Path | None = None,
) -> LanguageDetection:
    """Identify text language with optional Facebook fastText LID fallback."""

    normalized = " ".join(text.split())
    if not normalized:
        return LanguageDetection("und", 0.0, "empty")

    fasttext_detection = _detect_with_fasttext(normalized, model_path=model_path)
    if fasttext_detection is not None:
        return fasttext_detection

    return _heuristic_language_detection(normalized)


def _detect_with_fasttext(
    text: str,
    *,
    model_path: str | Path | None,
) -> LanguageDetection | None:
    configured_path = str(model_path or os.environ.get(FASTTEXT_LID_MODEL_ENV, ""))
    if not configured_path:
        return None
    path = Path(configured_path)
    if not path.is_file():
        return None
    try:
        import fasttext  # type: ignore[import-not-found]
    except ImportError:
        return None
    model = fasttext.load_model(str(path))
    labels, probabilities = model.predict(text.replace("\n", " "), k=1)
    if not labels:
        return None
    language = str(labels[0]).replace("__label__", "")
    confidence = float(probabilities[0]) if probabilities else 0.0
    return LanguageDetection(
        language=language,
        confidence=confidence,
        provider="facebook-fasttext-lid",
        model_id=path.name,
    )


def _heuristic_language_detection(text: str) -> LanguageDetection:
    lowered = text.casefold()
    tokens = re.findall(r"[\w']+", lowered, flags=re.UNICODE)
    token_set = set(tokens)
    scores = {
        "en": _keyword_score(
            token_set,
            {"the", "and", "hello", "world", "contract", "this", "is", "signed"},
        ),
        "fr": _keyword_score(
            token_set,
            {"le", "la", "les", "bonjour", "monde", "contrat", "est", "signé"},
        ),
        "es": _keyword_score(
            token_set,
            {"el", "la", "los", "hola", "mundo", "contrato", "está", "firmado"},
        ),
        "de": _keyword_score(
            token_set,
            {"der", "die", "das", "hallo", "welt", "vertrag", "ist"},
        ),
        "it": _keyword_score(
            token_set,
            {"il", "la", "ciao", "mondo", "contratto", "firmato"},
        ),
        "pt": _keyword_score(
            token_set,
            {"o", "a", "olá", "mundo", "contrato", "assinado"},
        ),
    }
    best_language, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score > 0:
        confidence = min(0.85, 0.45 + best_score * 0.1)
        return LanguageDetection(best_language, confidence, "heuristic")
    if text.isascii():
        return LanguageDetection("en", 0.35, "ascii-default")
    return LanguageDetection("und", 0.1, "heuristic")


def _keyword_score(tokens: set[str], keywords: set[str]) -> int:
    return len(tokens.intersection(keywords))
