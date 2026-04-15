"""Daily challenge: write one sentence using 3 due words."""

from __future__ import annotations

import streamlit as st

from lexico.services import get_deck_store, get_enrichment_service
from lexico.services.usage_guardrail import BudgetExceeded


def render(user_id: str) -> None:
    st.title("🎯 Daily challenge")
    st.caption("Use three of your due words in one sentence — the tutor grades it.")

    enrichment = get_enrichment_service()
    if not enrichment.is_real_llm_available():
        st.warning(
            "⚠️ No real LLM configured. Set `GROQ_API_KEY` in your environment "
            "(or Streamlit secrets) to get real grading. In the meantime you can "
            "still write sentences — the stub will return a placeholder score."
        )

    store = get_deck_store()
    due = store.get_due_cards(user_id=user_id, limit=20)
    if len(due) < 3:
        st.info("You need at least **3 due cards** to play. Save more words on Lookup!")
        return

    picks = due[:3]
    language = picks[0].entry.language
    required = [c.entry.lemma for c in picks]

    st.markdown(f"**Language:** {language.flag} {language.display_name}")
    st.markdown("**Use all of these words:**")
    # Stack vertically on narrow screens (the mobile CSS shim collapses
    # st.columns to single-column below ~480px).
    cols = st.columns(len(required))
    for col, word in zip(cols, required):
        with col:
            with st.container(border=True):
                st.markdown(f"### {word}")

    sentence = st.text_area("Your sentence", key="challenge_input", height=100)
    if not st.button("Grade", type="primary", key="challenge_grade"):
        return
    if not sentence.strip():
        st.warning("Write a sentence first.")
        return

    try:
        result = enrichment.grade_challenge(language, required, sentence, user_id=user_id)
    except BudgetExceeded:
        st.warning("Daily LLM budget reached — come back tomorrow!")
        return
    except Exception as exc:
        st.error(f"Grading failed: {exc}")
        return

    score = max(0, min(100, result.grade))
    st.metric("Grade", f"{score}/100")
    st.progress(score / 100)
    if result.feedback:
        st.info(result.feedback)
    if result.correction:
        with st.expander("Suggested correction"):
            st.write(result.correction)
