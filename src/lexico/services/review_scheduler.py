"""FSRS-inspired spaced-repetition scheduler.

A simplified implementation of the FSRS algorithm that captures its
essential behavior: each card has a stability (retention half-life in
days) and a difficulty (1-10, higher is harder). Ratings update both
and derive the next due date.

For a portfolio project this is enough to produce realistic learning
curves and testable math. Upgrading to full FSRS v4 with per-user
parameter fitting is a v2 concern.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from lexico.domain.enums import Rating
from lexico.domain.review import FSRSState, ReviewLog


MIN_STABILITY = 0.1
MAX_STABILITY = 36500.0
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    return math.exp(-elapsed_days / stability)


def _initial_stability(rating: Rating) -> float:
    return {
        Rating.AGAIN: 0.5,
        Rating.HARD: 1.0,
        Rating.GOOD: 3.0,
        Rating.EASY: 7.0,
    }[rating]


def _initial_difficulty(rating: Rating) -> float:
    base = 5.0
    delta = {
        Rating.AGAIN: 2.0,
        Rating.HARD: 0.5,
        Rating.GOOD: 0.0,
        Rating.EASY: -1.0,
    }[rating]
    return _clamp(base + delta, MIN_DIFFICULTY, MAX_DIFFICULTY)


def _update_stability(
    stability: float, rating: Rating, retrievability: float
) -> float:
    if rating == Rating.AGAIN:
        new_s = stability * 0.2
    elif rating == Rating.HARD:
        new_s = stability * (1.2 + 0.2 * retrievability)
    elif rating == Rating.GOOD:
        new_s = stability * (2.0 + 1.5 * retrievability)
    else:  # EASY
        new_s = stability * (3.0 + 2.5 * retrievability)
    return _clamp(new_s, MIN_STABILITY, MAX_STABILITY)


def _update_difficulty(difficulty: float, rating: Rating) -> float:
    delta = {
        Rating.AGAIN: 1.5,
        Rating.HARD: 0.5,
        Rating.GOOD: -0.1,
        Rating.EASY: -0.5,
    }[rating]
    return _clamp(difficulty + delta, MIN_DIFFICULTY, MAX_DIFFICULTY)


def schedule(
    state: FSRSState,
    rating: Rating,
    now: datetime | None = None,
) -> tuple[FSRSState, ReviewLog]:
    """Compute the next state and a review log entry.

    Pure function: `state` is not mutated, a new FSRSState is returned.
    """
    reviewed_at = now or datetime.now(timezone.utc)

    if state.is_new:
        new_stability = _initial_stability(rating)
        new_difficulty = _initial_difficulty(rating)
        elapsed_days = 0.0
    else:
        last = state.last_reviewed_at or state.due_at
        elapsed_days = max(0.0, (reviewed_at - last).total_seconds() / 86400.0)
        retrievability = _retrievability(elapsed_days, state.stability)
        new_stability = _update_stability(state.stability, rating, retrievability)
        new_difficulty = _update_difficulty(state.difficulty, rating)

    new_due = reviewed_at + timedelta(days=new_stability)
    new_lapses = state.lapses + (1 if rating == Rating.AGAIN else 0)

    new_state = FSRSState(
        stability=new_stability,
        difficulty=new_difficulty,
        due_at=new_due,
        last_reviewed_at=reviewed_at,
        reps=state.reps + 1,
        lapses=new_lapses,
        last_rating=rating,
    )
    log = ReviewLog(
        card_id=0,  # caller fills this in
        rating=rating,
        reviewed_at=reviewed_at,
        elapsed_days=elapsed_days,
        scheduled_days=new_stability,
        stability_after=new_stability,
        difficulty_after=new_difficulty,
    )
    return new_state, log
