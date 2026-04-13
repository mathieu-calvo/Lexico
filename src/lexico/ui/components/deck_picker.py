"""Reusable deck dropdown."""

from __future__ import annotations

import streamlit as st

from lexico.domain.deck import Deck


def deck_picker(decks: list[Deck], key: str, label: str = "Deck") -> Deck | None:
    if not decks:
        st.info("No decks yet — create one on the Decks page.")
        return None
    return st.selectbox(
        label,
        decks,
        format_func=lambda d: f"{d.source_lang.flag} {d.name}",
        key=key,
    )
