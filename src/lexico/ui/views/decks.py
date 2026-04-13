"""Decks view: browse, create, delete personal decks."""

from __future__ import annotations

import streamlit as st

from lexico.domain.deck import Deck
from lexico.domain.enums import Language
from lexico.services import get_deck_store, get_lookup_service
from lexico.services.seed_decks import clone_seed_deck, list_seed_decks
from lexico.ui.components.language_picker import language_picker


def render(user_id: str) -> None:
    st.title("📒 Decks")
    st.caption("Your personal vocabulary collections.")

    store = get_deck_store()
    decks = store.list_decks(user_id=user_id)

    seeds = list_seed_decks()
    if seeds:
        with st.expander("🌱 Clone a themed deck"):
            st.caption(
                "One click to start learning a curated topic. "
                "Each word is looked up and added to a new deck."
            )
            for seed in seeds:
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f"**{seed.source_lang.flag}→{seed.target_lang.flag} "
                        f"{seed.name}**  · {len(seed.lemmas)} words"
                    )
                    if seed.description:
                        st.caption(seed.description)
                with col_btn:
                    if st.button("Clone", key=f"clone_{seed.slug}"):
                        lookup = get_lookup_service()
                        with st.spinner(f"Cloning *{seed.name}*…"):
                            _, added, skipped = clone_seed_deck(
                                seed, store, lookup, user_id=user_id
                            )
                        msg = f"Added {added} cards to **{seed.name}**."
                        if skipped:
                            msg += f" ({skipped} skipped)"
                        st.success(msg)
                        st.rerun()

    with st.expander("➕ New deck", expanded=not decks):
        name = st.text_input("Name", key="new_deck_name")
        col_src, col_tgt = st.columns(2)
        with col_src:
            source = language_picker("Source", key="new_deck_src", default=Language.FR)
        with col_tgt:
            target = language_picker("Target", key="new_deck_tgt", default=Language.EN)
        description = st.text_area("Description (optional)", key="new_deck_desc")
        if st.button("Create deck", type="primary", key="new_deck_create") and name:
            store.create_deck(
                Deck(
                    user_id=user_id,
                    name=name,
                    source_lang=source,
                    target_lang=target,
                    description=description,
                )
            )
            st.success(f"Created **{name}**.")
            st.rerun()

    if not decks:
        st.info("No decks yet. Create one above to start saving words.")
        return

    st.divider()
    for deck in decks:
        with st.container(border=True):
            cards = store.list_cards(deck.id) if deck.id else []
            head_col, btn_col = st.columns([4, 1])
            with head_col:
                st.markdown(
                    f"### {deck.source_lang.flag}→{deck.target_lang.flag} {deck.name}"
                )
                if deck.description:
                    st.caption(deck.description)
                st.write(f"**{len(cards)}** cards")
            with btn_col:
                if st.button("🗑 Delete", key=f"del_{deck.id}"):
                    if deck.id:
                        store.delete_deck(deck.id)
                    st.rerun()

            if cards:
                with st.expander(f"Show cards ({len(cards)})"):
                    for card in cards:
                        translations = card.entry.primary_translation(deck.target_lang) or "—"
                        st.markdown(
                            f"- **{card.entry.lemma}** → {translations}"
                            f"  · due {card.fsrs_state.due_at.date().isoformat()}"
                        )
