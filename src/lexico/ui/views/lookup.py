"""Lookup view: search a word, render the entry, save to a deck."""

from __future__ import annotations

import streamlit as st

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.services import get_deck_store, get_lookup_service
from lexico.ui.components.deck_picker import deck_picker
from lexico.ui.components.language_picker import language_picker
from lexico.ui.components.word_card import render_word_card


def render(user_id: str) -> None:
    st.title("🔍 Lookup")
    st.caption("Find a word, save it to a deck, build your personal vocabulary.")

    col_lang, col_query = st.columns([1, 2])
    with col_lang:
        language = language_picker("Language", key="lookup_lang", default=Language.FR)
    with col_query:
        query = st.text_input(
            "Word",
            key="lookup_query",
            placeholder="éphémère, chat, flâner …",
            value=st.session_state.pop("lookup_prefill", ""),
        )

    if not query:
        return

    lookup = get_lookup_service()
    try:
        with st.spinner(f"Looking up **{query}** in {language.display_name}…"):
            entry = lookup.lookup(query.strip(), language)
    except LookupError:
        st.warning(
            f"No entry found for **{query}** in {language.display_name}. "
            "Check the spelling, or try a different language."
        )
        return

    with st.container(border=True):
        render_word_card(entry)

    st.divider()
    st.subheader("Save to a deck")

    store = get_deck_store()
    decks = store.list_decks(user_id=user_id)
    deck = deck_picker(decks, key="lookup_deck")

    if deck is not None and deck.id is not None:
        if st.button("➕ Add card", type="primary", key="lookup_save"):
            card = Card.new(entry, deck_id=deck.id)
            store.add_card(card)
            st.success(f"Added **{entry.lemma}** to *{deck.name}*.")
    else:
        with st.expander("Or create a new deck"):
            name = st.text_input("Deck name", key="lookup_new_deck_name")
            if st.button("Create deck", key="lookup_new_deck_btn") and name:
                new_deck = store.create_deck(
                    Deck(user_id=user_id, name=name, source_lang=language)
                )
                if new_deck.id:
                    store.add_card(Card.new(entry, deck_id=new_deck.id))
                st.success(f"Created **{name}** and added **{entry.lemma}**.")
                st.rerun()
