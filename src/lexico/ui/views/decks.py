"""Decks view: browse, create, delete personal decks and individual cards."""

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
                        f"**{seed.source_lang.flag} {seed.name}**  · "
                        f"{len(seed.lemmas)} words"
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
        source = language_picker("Language", key="new_deck_src", default=Language.FR)
        description = st.text_area("Description (optional)", key="new_deck_desc")
        if st.button("Create deck", type="primary", key="new_deck_create") and name:
            store.create_deck(
                Deck(
                    user_id=user_id,
                    name=name,
                    source_lang=source,
                    description=description,
                )
            )
            st.success(f"Created **{name}**.")
            st.rerun()

    if not decks:
        st.info("No decks yet. Create one above to start saving words.")
        return

    all_langs = sorted({d.source_lang for d in decks}, key=lambda l: l.value)
    if len(all_langs) > 1:
        options = ["All"] + [f"{l.flag} {l.display_name}" for l in all_langs]
        choice = st.radio(
            "Filter by language",
            options,
            horizontal=True,
            key="decks_lang_filter",
        )
        if choice != "All":
            idx = options.index(choice) - 1
            decks = [d for d in decks if d.source_lang == all_langs[idx]]

    st.divider()
    for deck in decks:
        _render_deck(deck, store)


def _render_deck(deck: Deck, store) -> None:
    with st.container(border=True):
        cards = store.list_cards(deck.id) if deck.id else []
        head_col, btn_col = st.columns([4, 1])
        with head_col:
            st.markdown(f"### {deck.source_lang.flag} {deck.name}")
            if deck.description:
                st.caption(deck.description)
            st.write(f"**{len(cards)}** cards")
        with btn_col:
            if st.button("🗑 Delete deck", key=f"del_deck_{deck.id}"):
                if deck.id:
                    store.delete_deck(deck.id)
                st.rerun()

        if not cards:
            return

        filter_key = f"deck_filter_{deck.id}"
        query = st.text_input(
            "Filter cards",
            key=filter_key,
            placeholder="Type to narrow by lemma or definition…",
        )
        needle = (query or "").strip().lower()
        if needle:
            filtered = [
                c for c in cards
                if needle in c.entry.lemma.lower()
                or any(needle in s.gloss.lower() for s in c.entry.senses)
            ]
        else:
            filtered = cards

        with st.expander(f"Show cards ({len(filtered)}/{len(cards)})"):
            if not filtered:
                st.caption("No cards match that filter.")
                return
            for card in filtered:
                first_sense = card.entry.senses[0].gloss if card.entry.senses else "—"
                preview = (first_sense[:80] + "…") if len(first_sense) > 80 else first_sense
                row_main, row_btn = st.columns([6, 1])
                with row_main:
                    st.markdown(
                        f"**{card.entry.lemma}** — {preview}  "
                        f"· due {card.fsrs_state.due_at.date().isoformat()}"
                    )
                with row_btn:
                    if card.id is not None and st.button(
                        "🗑", key=f"del_card_{card.id}", help="Delete this card"
                    ):
                        store.delete_card(card.id)
                        st.rerun()
