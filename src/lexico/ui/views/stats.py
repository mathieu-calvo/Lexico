"""Stats view: totals, streak, per-language counts, recent reviews."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from lexico.domain.enums import Language, Rating
from lexico.services import get_deck_store
from lexico.services.gamification import compute_streak
from lexico.ui.components.streak_chip import streak_chip


def render(user_id: str) -> None:
    st.title("📊 Stats")
    st.caption("Your learning, measured.")

    store = get_deck_store()
    logs = store.list_review_logs(user_id=user_id, limit=5000)
    decks = store.list_decks(user_id=user_id)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        streak_chip(compute_streak(logs))
    with col_b:
        st.metric("Cards saved", store.count_cards(user_id=user_id))
    with col_c:
        due = store.get_due_cards(user_id=user_id, limit=10000)
        st.metric("Due now", len(due))

    st.divider()
    st.subheader("Per-language totals")

    cards_by_lang: dict[Language, int] = defaultdict(int)
    for deck in decks:
        if deck.id is None:
            continue
        cards_by_lang[deck.source_lang] += len(store.list_cards(deck.id))
    reviews_by_lang: dict[Language, int] = defaultdict(int)
    for row in logs:
        try:
            reviews_by_lang[Language(row["language"])] += 1
        except ValueError:
            continue

    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            with st.container(border=True):
                st.markdown(f"### {lang.flag} {lang.display_name}")
                st.caption(f"{cards_by_lang.get(lang, 0)} saved")
                st.caption(f"{reviews_by_lang.get(lang, 0)} reviews")

    st.divider()
    st.subheader("Reviews over the last 30 days")
    if not logs:
        st.info("No reviews yet — head to the **Review** page to get started.")
        return

    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    counts: dict = defaultdict(int)
    for row in logs:
        d = row["reviewed_at"].date() if isinstance(row["reviewed_at"], datetime) else None
        if d:
            counts[d] += 1
    df = pd.DataFrame(
        {"date": days, "reviews": [counts.get(d, 0) for d in days]}
    ).set_index("date")
    st.bar_chart(df)

    with st.expander("Recent reviews"):
        rows = []
        for row in logs[:25]:
            try:
                rating_label = Rating(row["rating"]).label
            except ValueError:
                rating_label = str(row["rating"])
            reviewed = row["reviewed_at"]
            date_str = (
                reviewed.strftime("%Y-%m-%d %H:%M")
                if isinstance(reviewed, datetime)
                else str(reviewed)
            )
            try:
                lang_flag = Language(row["language"]).flag
            except ValueError:
                lang_flag = ""
            rows.append(
                {
                    "When": date_str,
                    "Language": lang_flag,
                    "Word": row.get("lemma") or "(deleted)",
                    "Meaning": row.get("gloss") or "",
                    "Rating": rating_label,
                }
            )
        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
