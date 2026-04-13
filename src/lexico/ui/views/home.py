"""Home dashboard: word of the day, streak, XP per language."""

from __future__ import annotations

import streamlit as st

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.services import get_deck_store, get_lookup_service
from lexico.services.gamification import (
    compute_streak,
    word_of_the_day_index,
    xp_by_language,
)
from lexico.ui.components.streak_chip import streak_chip
from lexico.ui.components.xp_bar import xp_bar
from lexico.ui.components.word_card import render_word_card


def render(user_id: str) -> None:
    st.title("📚 Lexico")
    st.caption("Save words, practice with spaced repetition, never forget.")

    store = get_deck_store()
    lookup = get_lookup_service()
    logs = store.list_review_logs(user_id=user_id, limit=2000)

    col_streak, col_count = st.columns(2)
    with col_streak:
        streak_chip(compute_streak(logs))
    with col_count:
        st.markdown(f"📒 **{store.count_cards(user_id=user_id)}** saved cards")

    st.divider()
    st.subheader("Words of the day")

    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            lemma = _wotd_lemma(lookup, lang)
            if lemma is None:
                st.markdown(f"{lang.flag} *(none)*")
                continue
            try:
                entry = lookup.lookup(lemma, lang)
            except LookupError:
                st.markdown(f"{lang.flag} {lemma}")
                continue
            with st.container(border=True):
                render_word_card(entry)

    st.divider()
    st.subheader("Your XP")
    totals = xp_by_language(logs)
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            xp_bar(lang, totals.get(lang, 0))


def _wotd_lemma(lookup, language: Language) -> str | None:
    pool: list[str] = []
    for provider in lookup.providers:
        if hasattr(provider, "all_lemmas"):
            try:
                pool = provider.all_lemmas(language)  # type: ignore[attr-defined]
                if pool:
                    break
            except Exception:
                continue
    if not pool:
        return None
    idx = word_of_the_day_index(language, len(pool))
    return pool[idx]
