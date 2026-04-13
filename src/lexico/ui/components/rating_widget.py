"""FSRS rating buttons (Again / Hard / Good / Easy)."""

from __future__ import annotations

import streamlit as st

from lexico.domain.enums import Rating


_BUTTONS: list[tuple[Rating, str]] = [
    (Rating.AGAIN, "❌ Again"),
    (Rating.HARD, "🟠 Hard"),
    (Rating.GOOD, "🟢 Good"),
    (Rating.EASY, "✨ Easy"),
]


def rating_buttons(key_prefix: str) -> Rating | None:
    cols = st.columns(4)
    for col, (rating, label) in zip(cols, _BUTTONS):
        if col.button(label, key=f"{key_prefix}_{rating.name}", use_container_width=True):
            return rating
    return None
