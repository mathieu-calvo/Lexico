"""Gamification tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from lexico.domain.enums import CEFRLevel, Language, Rating
from lexico.services.gamification import (
    compute_streak,
    rank_for,
    word_of_the_day_index,
    xp_by_language,
    xp_for,
    xp_to_next_rank,
)


def test_xp_scales_with_rating():
    assert xp_for(Rating.AGAIN) == 0
    assert xp_for(Rating.HARD) < xp_for(Rating.GOOD) < xp_for(Rating.EASY)


def test_rank_for_zero_is_a1():
    assert rank_for(0) == CEFRLevel.A1


def test_rank_for_threshold_boundaries():
    assert rank_for(100) == CEFRLevel.A2
    assert rank_for(299) == CEFRLevel.A2
    assert rank_for(300) == CEFRLevel.B1
    assert rank_for(10_000) == CEFRLevel.C2


def test_xp_to_next_rank_within_a2():
    current, needed = xp_to_next_rank(150)
    assert needed == 200  # B1 threshold 300 minus A2 threshold 100
    assert current == 50


def test_xp_by_language_sums_per_lang():
    logs = [
        {"language": "fr", "rating": int(Rating.GOOD), "reviewed_at": datetime.now(timezone.utc)},
        {"language": "fr", "rating": int(Rating.EASY), "reviewed_at": datetime.now(timezone.utc)},
        {"language": "it", "rating": int(Rating.HARD), "reviewed_at": datetime.now(timezone.utc)},
    ]
    totals = xp_by_language(logs)
    assert totals[Language.FR] == xp_for(Rating.GOOD) + xp_for(Rating.EASY)
    assert totals[Language.IT] == xp_for(Rating.HARD)
    assert totals[Language.EN] == 0


def test_streak_counts_consecutive_days():
    today = date(2026, 4, 13)
    logs = [
        {"reviewed_at": datetime(2026, 4, 13, tzinfo=timezone.utc), "rating": 3, "language": "fr"},
        {"reviewed_at": datetime(2026, 4, 12, tzinfo=timezone.utc), "rating": 3, "language": "fr"},
        {"reviewed_at": datetime(2026, 4, 11, tzinfo=timezone.utc), "rating": 3, "language": "fr"},
    ]
    assert compute_streak(logs, today) == 3


def test_streak_breaks_on_gap():
    today = date(2026, 4, 13)
    logs = [
        {"reviewed_at": datetime(2026, 4, 13, tzinfo=timezone.utc), "rating": 3, "language": "fr"},
        {"reviewed_at": datetime(2026, 4, 10, tzinfo=timezone.utc), "rating": 3, "language": "fr"},
    ]
    assert compute_streak(logs, today) == 1


def test_streak_is_zero_with_no_logs():
    assert compute_streak([], date(2026, 4, 13)) == 0


def test_wotd_index_is_deterministic():
    a = word_of_the_day_index(Language.FR, 5, date(2026, 4, 13))
    b = word_of_the_day_index(Language.FR, 5, date(2026, 4, 13))
    assert a == b
    assert 0 <= a < 5


def test_wotd_indices_differ_across_languages():
    today = date(2026, 4, 13)
    indices = {
        lang: word_of_the_day_index(lang, 50, today) for lang in Language
    }
    # with a pool of 50 and 5 distinct offsets, at least two should differ
    assert len(set(indices.values())) >= 2
