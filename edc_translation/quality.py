"""Deterministic local quality-estimation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PairQualityScore:
    source_language: str
    target_language: str
    score: float
    quality_class: str
    provider_id: str
    signals: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score_translation_pair(
    source_text: str,
    translated_text: str,
    *,
    source_language: str = "und",
    target_language: str = "und",
    provider_id: str = "deterministic_local_qe",
) -> dict[str, object]:
    """Return a bounded deterministic score for local skeleton workflows."""

    source_chars = _normalized_chars(source_text)
    target_chars = _normalized_chars(translated_text)
    if not source_chars or not target_chars:
        score = 0.0
        overlap = 0.0
        length_ratio = 0.0
    else:
        overlap = _jaccard(source_chars, target_chars)
        length_ratio = min(len(source_chars), len(target_chars)) / max(
            len(source_chars),
            len(target_chars),
        )
        score = round((0.35 * overlap) + (0.65 * length_ratio), 4)

    if score >= 0.85:
        quality_class = "high"
    elif score >= 0.65:
        quality_class = "review"
    else:
        quality_class = "low"

    return PairQualityScore(
        source_language=source_language,
        target_language=target_language,
        score=score,
        quality_class=quality_class,
        provider_id=provider_id,
        signals={
            "character_jaccard": round(overlap, 4),
            "length_ratio": round(length_ratio, 4),
        },
    ).to_dict()


def _normalized_chars(text: str) -> list[str]:
    return [char.casefold() for char in text if not char.isspace()]


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)
