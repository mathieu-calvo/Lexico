"""FSRS scheduler tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lexico.domain.enums import Rating
from lexico.domain.review import FSRSState
from lexico.services.review_scheduler import (
    MAX_DIFFICULTY,
    MIN_DIFFICULTY,
    schedule,
)


def test_new_card_good_sets_positive_stability(now):
    state = FSRSState.new(now)
    new_state, log = schedule(state, Rating.GOOD, now)
    assert new_state.stability > 0
    assert new_state.reps == 1
    assert new_state.last_rating == Rating.GOOD
    assert log.rating == Rating.GOOD
    assert log.stability_after == new_state.stability


def test_new_card_easy_has_larger_stability_than_good(now):
    state = FSRSState.new(now)
    good_state, _ = schedule(state, Rating.GOOD, now)
    easy_state, _ = schedule(state, Rating.EASY, now)
    assert easy_state.stability > good_state.stability


def test_again_increments_lapses(now):
    state = FSRSState.new(now)
    state, _ = schedule(state, Rating.GOOD, now)
    later = now + timedelta(days=2)
    state, _ = schedule(state, Rating.AGAIN, later)
    assert state.lapses == 1


def test_again_shrinks_stability(now):
    state = FSRSState.new(now)
    state, _ = schedule(state, Rating.GOOD, now)
    before = state.stability
    later = now + timedelta(days=2)
    state, _ = schedule(state, Rating.AGAIN, later)
    assert state.stability < before


def test_good_grows_stability_over_successive_reviews(now):
    state = FSRSState.new(now)
    state, _ = schedule(state, Rating.GOOD, now)
    s1 = state.stability
    later = now + timedelta(days=int(s1))
    state, _ = schedule(state, Rating.GOOD, later)
    s2 = state.stability
    assert s2 > s1


def test_difficulty_is_clamped(now):
    state = FSRSState.new(now)
    for _ in range(30):
        state, _ = schedule(state, Rating.AGAIN, state.due_at)
    assert state.difficulty <= MAX_DIFFICULTY
    state2 = FSRSState.new(now)
    for _ in range(30):
        state2, _ = schedule(state2, Rating.EASY, state2.due_at)
    assert state2.difficulty >= MIN_DIFFICULTY


def test_due_at_advances_by_stability(now):
    state = FSRSState.new(now)
    new_state, _ = schedule(state, Rating.GOOD, now)
    expected = now + timedelta(days=new_state.stability)
    assert abs((new_state.due_at - expected).total_seconds()) < 1


@pytest.mark.parametrize("rating", list(Rating))
def test_scheduler_is_pure(now, rating):
    state = FSRSState.new(now)
    original_dict = state.model_dump()
    schedule(state, rating, now)
    assert state.model_dump() == original_dict


def test_reps_increment_each_call(now):
    state = FSRSState.new(now)
    for i in range(1, 5):
        state, _ = schedule(state, Rating.GOOD, now + timedelta(days=i * 3))
        assert state.reps == i
