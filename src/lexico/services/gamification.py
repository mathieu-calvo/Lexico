"""XP, language ranks, streaks, and word-of-the-day rotation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from lexico.domain.enums import CEFRLevel, Language, Rating


XP_PER_RATING: dict[Rating, int] = {
    Rating.AGAIN: 0,
    Rating.HARD: 5,
    Rating.GOOD: 10,
    Rating.EASY: 15,
}


RANK_THRESHOLDS: list[tuple[int, CEFRLevel]] = [
    (0, CEFRLevel.A1),
    (100, CEFRLevel.A2),
    (300, CEFRLevel.B1),
    (700, CEFRLevel.B2),
    (1500, CEFRLevel.C1),
    (3000, CEFRLevel.C2),
]


def xp_for(rating: Rating) -> int:
    return XP_PER_RATING[rating]


def rank_for(xp: int) -> CEFRLevel:
    rank = CEFRLevel.A1
    for threshold, level in RANK_THRESHOLDS:
        if xp >= threshold:
            rank = level
    return rank


def xp_to_next_rank(xp: int) -> tuple[int, int]:
    """Return (current, needed) XP toward next rank.

    If already at C2, returns (xp, xp) so the UI can show a "maxed" bar.
    """
    for i, (threshold, _) in enumerate(RANK_THRESHOLDS):
        if xp < threshold:
            prev_threshold = RANK_THRESHOLDS[i - 1][0] if i > 0 else 0
            return xp - prev_threshold, threshold - prev_threshold
    return xp, xp


def xp_by_language(review_logs: list[dict]) -> dict[Language, int]:
    """Sum XP per language from a list of review-log rows (from DeckStore)."""
    totals: dict[Language, int] = {lang: 0 for lang in Language}
    for row in review_logs:
        try:
            lang = Language(row["language"])
            rating = Rating(row["rating"])
            totals[lang] += xp_for(rating)
        except (ValueError, KeyError):
            continue
    return totals


def compute_streak(review_logs: list[dict], today: date | None = None) -> int:
    """Count consecutive days (including today) with at least one review."""
    if not review_logs:
        return 0
    today = today or datetime.now(timezone.utc).date()
    review_dates = {
        (row["reviewed_at"].date() if isinstance(row["reviewed_at"], datetime) else datetime.fromisoformat(str(row["reviewed_at"])).date())
        for row in review_logs
    }
    streak = 0
    cursor = today
    while cursor in review_dates:
        streak += 1
        cursor -= timedelta(days=1)
    if streak == 0 and (today - timedelta(days=1)) in review_dates:
        streak = 1
        cursor = today - timedelta(days=2)
        while cursor in review_dates:
            streak += 1
            cursor -= timedelta(days=1)
    return streak


def word_of_the_day_index(language: Language, pool_size: int, today: date | None = None) -> int:
    """Deterministic index into a pool of lemmas.

    Different languages advance on different offsets so all five WOTDs
    don't roll together in lockstep.
    """
    if pool_size <= 0:
        return 0
    t = today or datetime.now(timezone.utc).date()
    offset = {
        Language.FR: 0,
        Language.EN: 7,
        Language.IT: 13,
        Language.ES: 23,
        Language.PT: 31,
    }[language]
    return (t.toordinal() + offset) % pool_size
