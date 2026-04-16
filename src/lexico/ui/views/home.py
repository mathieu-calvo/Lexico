"""Home dashboard: streak, saved count, quote + expression + word of the day."""

from __future__ import annotations

import streamlit as st

from lexico.data.daily_pool import (
    DailyExpression,
    expression_of_the_day,
    expression_to_word_entry,
    quote_of_the_day,
    word_of_the_day,
)
from lexico.domain.deck import Card, Deck
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
    st.subheader("Quote of the day")
    st.caption("Star a quote to keep it in your collection — browse and replay them on **Quotes**.")
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            _render_quote(lang, user_id, store)

    st.divider()
    st.subheader("Expression of the day")
    st.caption("Like one? Save it to a deck and it joins your review queue.")
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            _render_expression(lang, user_id, store)

    st.divider()
    st.subheader("Words of the day")
    st.caption("Like one? Save it to a deck and it joins your review queue.")
    cols = st.columns(len(Language))
    for col, lang in zip(cols, Language):
        with col:
            _render_word_of_the_day(lookup, lang, user_id, store)


def _render_word_of_the_day(lookup, language: Language, user_id: str, store) -> None:
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
        _render_save_to_deck(entry, language, user_id, store, key_prefix="wotd")


def _render_expression(language: Language, user_id: str, store) -> None:
    expr = expression_of_the_day(language)
    if expr is None:
        st.markdown(f"{language.flag} *(none)*")
        return
    with st.container(border=True):
        st.markdown(f"{language.flag} **{expr.text}**")
        st.caption(expr.meaning)
        _render_save_expression_ui(expr, language, user_id, store)


def _render_save_expression_ui(
    expr: DailyExpression, language: Language, user_id: str, store
) -> None:
    entry = expression_to_word_entry(expr, language)
    _render_save_to_deck(entry, language, user_id, store, key_prefix="expr")


def _render_save_to_deck(
    entry,
    language: Language,
    user_id: str,
    store,
    key_prefix: str,
) -> None:
    """Inline deck picker + save button for any WordEntry on the home page.

    Shows a popover (falling back to an expander on older Streamlit) so
    the five language columns stay compact — the UI only expands when
    the user actually wants to save. Used for both expression-of-the-day
    and word-of-the-day cards; the `key_prefix` keeps widget keys from
    colliding between them.
    """
    popover = getattr(st, "popover", None)
    container = popover("💾 Save") if popover else st.expander("💾 Save", expanded=False)
    with container:
        decks = [d for d in store.list_decks(user_id=user_id) if d.source_lang == language]
        if decks:
            deck = st.selectbox(
                "Deck",
                decks,
                format_func=lambda d: f"{d.source_lang.flag} {d.name}",
                key=f"{key_prefix}_deck_{language.value}",
            )
            if st.button("Add", key=f"{key_prefix}_save_{language.value}", type="primary"):
                if deck.id is not None:
                    store.add_card(Card.new(entry, deck_id=deck.id))
                    st.success(f"Added to *{deck.name}*.")
        else:
            default_name = "Expressions" if key_prefix == "expr" else "Words of the day"
            new_name = st.text_input(
                f"New {language.display_name} deck name",
                key=f"{key_prefix}_new_{language.value}",
                placeholder=default_name,
            )
            if st.button("Create & add", key=f"{key_prefix}_create_{language.value}", type="primary"):
                name = (new_name or default_name).strip() or default_name
                new_deck = store.create_deck(
                    Deck(user_id=user_id, name=name, source_lang=language)
                )
                if new_deck.id is not None:
                    store.add_card(Card.new(entry, deck_id=new_deck.id))
                    st.success(f"Created **{name}** and added.")
                    st.rerun()


def _render_quote(language: Language, user_id: str, store) -> None:
    quote = quote_of_the_day(language)
    if quote is None:
        st.markdown(f"{language.flag} *(none)*")
        return
    liked = store.is_quote_liked(user_id, language, quote.text)
    with st.container(border=True):
        st.markdown(f"{language.flag} _“{quote.text}”_")
        st.caption(f"— {quote.author}")
        label = "⭐ Starred" if liked else "☆ Star"
        if st.button(label, key=f"qotd_star_{language.value}"):
            if liked:
                store.unlike_quote(user_id, language, quote.text)
            else:
                store.like_quote(user_id, language, quote.text, quote.author)
            st.rerun()
