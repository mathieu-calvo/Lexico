"""Per-language XP bar with rank chip."""

from __future__ import annotations

import streamlit as st

from lexico.domain.enums import Language
from lexico.services.gamification import rank_for, xp_to_next_rank


def xp_bar(language: Language, xp: int) -> None:
    rank = rank_for(xp)
    current, needed = xp_to_next_rank(xp)
    progress = current / needed if needed else 1.0
    st.markdown(f"{language.flag} **{language.display_name}** — `{rank.value}` · {xp} XP")
    st.progress(min(1.0, progress), text=f"{current}/{needed} XP to next rank")
