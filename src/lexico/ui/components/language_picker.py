"""Language selector with flag emojis."""

from __future__ import annotations

import streamlit as st

from lexico.domain.enums import Language


def language_picker(label: str, key: str, default: Language = Language.FR) -> Language:
    options = list(Language)
    return st.selectbox(
        label,
        options,
        index=options.index(default),
        format_func=lambda l: f"{l.flag} {l.display_name}",
        key=key,
    )
