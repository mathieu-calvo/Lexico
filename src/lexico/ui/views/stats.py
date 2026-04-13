"""Stats view: per-language XP, retention, streak, due counts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from lexico.domain.enums import Language
from lexico.services import get_deck_store
from lexico.services.gamification import compute_streak, xp_by_language
from lexico.ui.components.streak_chip import streak_chip
from lexico.ui.components.xp_bar import xp_bar


def render(user_id: str) -> None:
    st.title("📊 Stats")
    st.caption("Your learning, measured.")

    store = get_deck_store()
    logs = store.list_review_logs(user_id=user_id, limit=5000)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        streak_chip(compute_streak(logs))
    with col_b:
        st.metric("Cards saved", store.count_cards(user_id=user_id))
    with col_c:
        due = store.get_due_cards(user_id=user_id, limit=10000)
        st.metric("Due now", len(due))

    st.divider()
    st.subheader("XP per language")
    xp_totals = xp_by_language(logs)
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            xp_bar(lang, xp_totals.get(lang, 0))

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
        recent = pd.DataFrame(logs[:25])
        if not recent.empty:
            st.dataframe(recent, use_container_width=True)
