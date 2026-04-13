"""Tutor view: free-form chat scoped to vocabulary practice."""

from __future__ import annotations

import streamlit as st

from lexico.services import get_enrichment_service
from lexico.services.usage_guardrail import BudgetExceeded


def render(user_id: str) -> None:
    st.title("💬 Tutor")
    st.caption("Ask about a word, request examples, compare nuances.")

    history: list[tuple[str, str]] = st.session_state.setdefault("tutor_history", [])
    for role, msg in history:
        with st.chat_message(role):
            st.write(msg)

    question = st.chat_input("Ask the tutor anything…")
    if not question:
        return

    history.append(("user", question))
    with st.chat_message("user"):
        st.write(question)

    enrichment = get_enrichment_service()
    try:
        answer = enrichment.tutor(question, user_id=user_id)
    except BudgetExceeded:
        answer = "Daily LLM budget reached — come back tomorrow! Dictionary lookups and reviews still work."
    except Exception as exc:
        answer = f"Sorry, the tutor failed: {exc}"

    history.append(("assistant", answer))
    with st.chat_message("assistant"):
        st.write(answer)
