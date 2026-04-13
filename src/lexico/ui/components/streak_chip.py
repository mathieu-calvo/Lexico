"""Gentle streak counter chip."""

from __future__ import annotations

import streamlit as st


def streak_chip(streak: int) -> None:
    if streak <= 0:
        st.markdown("🌱 **Start your streak today!**")
        return
    flame = "🔥" if streak >= 3 else "✨"
    plural = "day" if streak == 1 else "days"
    st.markdown(f"{flame} **{streak}-{plural} streak**")
