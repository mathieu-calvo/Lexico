"""Review scheduling state (FSRS)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from lexico.domain.enums import Rating


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FSRSState(BaseModel):
    """Per-card scheduling state.

    FSRS models each card with stability (retention half-life in days)
    and difficulty (1-10, higher = harder). Next-due date is derived
    from stability at each review.
    """

    model_config = ConfigDict(frozen=True)

    stability: float = 0.0
    difficulty: float = 5.0
    due_at: datetime
    last_reviewed_at: datetime | None = None
    reps: int = 0
    lapses: int = 0
    last_rating: Rating | None = None

    @classmethod
    def new(cls, now: datetime | None = None) -> "FSRSState":
        t = now or _utcnow()
        return cls(due_at=t)

    @property
    def is_new(self) -> bool:
        return self.reps == 0


class ReviewLog(BaseModel):
    """A single review event, appended for analytics."""

    model_config = ConfigDict(frozen=True)

    card_id: int
    rating: Rating
    reviewed_at: datetime
    elapsed_days: float
    scheduled_days: float
    stability_after: float
    difficulty_after: float
