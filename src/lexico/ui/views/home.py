"""Home dashboard: streak, saved count, word + expression + quote of the day."""

from __future__ import annotations

import streamlit as st

from lexico.data.daily_pool import (
    expression_of_the_day,
    quote_of_the_day,
    word_of_the_day,
)
from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.services import get_deck_store, get_lookup_service
from lexico.services.gamification import compute_streak
from lexico.ui.components.streak_chip import streak_chip
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
            _render_word_of_the_day(lookup, lang)

    st.divider()
    st.subheader("Expression of the day")
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            _render_expression(lang)

    st.divider()
    st.subheader("Quote of the day")
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            _render_quote(lang)


def _render_word_of_the_day(lookup, language: Language) -> None:
    lemma = word_of_the_day(language)
    if lemma is None:
        st.markdown(f"{language.flag} *(none)*")
        return
    try:
        entry = lookup.lookup(lemma, language)
    except LookupError:
        with st.container(border=True):
            st.markdown(f"{language.flag} **{lemma}**")
            st.caption("Dictionary lookup unavailable.")
        return
    with st.container(border=True):
        render_word_card(entry)


def _render_expression(language: Language) -> None:
    expr = expression_of_the_day(language)
    if expr is None:
        st.markdown(f"{language.flag} *(none)*")
        return
    with st.container(border=True):
        st.markdown(f"{language.flag} **{expr.text}**")
        st.caption(expr.meaning)


def _render_quote(language: Language) -> None:
    quote = quote_of_the_day(language)
    if quote is None:
        st.markdown(f"{language.flag} *(none)*")
        return
    with st.container(border=True):
        st.markdown(f"{language.flag} _“{quote.text}”_")
        st.caption(f"— {quote.author}")
