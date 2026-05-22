"""Process-local review and certification workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any

from edc_translation.jobs import utc_now_iso


@dataclass
class ReviewDecision:
    review_id: str
    job_id: str
    decision: str
    reviewer: str
    notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReviewRepository:
    def __init__(self) -> None:
        self._decisions: dict[str, ReviewDecision] = {}
        self._lock = Lock()

    def add(
        self,
        *,
        job_id: str,
        decision: str,
        reviewer: str,
        notes: str = "",
    ) -> ReviewDecision:
        review = ReviewDecision(
            review_id=f"review_{len(self._decisions) + 1:06d}",
            job_id=job_id,
            decision=decision,
            reviewer=reviewer,
            notes=notes,
        )
        with self._lock:
            self._decisions[review.review_id] = review
        return review

    def list(self, *, job_id: str | None = None) -> list[ReviewDecision]:
        with self._lock:
            reviews = list(self._decisions.values())
        if job_id is None:
            return reviews
        return [review for review in reviews if review.job_id == job_id]
