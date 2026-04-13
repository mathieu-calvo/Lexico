"""Review view: FSRS queue with show/cloze/typing/MC modes."""

from __future__ import annotations

import random

import streamlit as st
from rapidfuzz.distance import Levenshtein

from lexico.domain.deck import Card
from lexico.domain.enums import Language, Rating
from lexico.services import get_deck_store, get_enrichment_service
from lexico.services.review_scheduler import schedule
from lexico.services.usage_guardrail import BudgetExceeded
from lexico.ui.components.rating_widget import rating_buttons
from lexico.ui.components.word_card import render_word_card


_MODES = ["Show", "Cloze", "Typing", "Multiple choice"]


def render(user_id: str) -> None:
    st.title("🧠 Review")
    st.caption("Spaced repetition queue — rate your recall to schedule the next review.")

    store = get_deck_store()
    enrichment = get_enrichment_service()

    decks = {d.id: d for d in store.list_decks(user_id=user_id)}
    if not decks:
        st.info("No decks yet — head to **Lookup** or **Decks** to create one.")
        return

    mode = st.radio("Mode", _MODES, horizontal=True, key="review_mode")
    due_cards = store.get_due_cards(user_id=user_id, limit=1)
    if not due_cards:
        st.success("🎉 Nothing due right now. Come back later!")
        return

    card = due_cards[0]
    deck = decks.get(card.deck_id)
    if deck is None:
        st.warning("Card belongs to a missing deck.")
        return

    st.markdown(f"_{deck.source_lang.flag}→{deck.target_lang.flag} {deck.name}_")
    target_lang = deck.target_lang

    if mode == "Show":
        _render_show(card)
    elif mode == "Cloze":
        _render_cloze(card, enrichment)
    elif mode == "Typing":
        _render_typing(card, target_lang)
    elif mode == "Multiple choice":
        _render_mc(card, target_lang, enrichment)

    st.divider()
    rating = rating_buttons(key_prefix=f"rate_{card.id}")
    if rating is not None and card.id is not None:
        new_state, log = schedule(card.fsrs_state, rating)
        store.update_card_state(card.id, new_state)
        log = log.model_copy(update={"card_id": card.id})
        store.log_review(log, user_id=user_id, language=card.entry.language)
        st.toast(f"Scheduled +{new_state.stability:.1f}d", icon="✅")
        st.rerun()


def _render_show(card: Card) -> None:
    with st.container(border=True):
        st.markdown(f"### {card.entry.lemma}")
        if not st.toggle("Reveal", key=f"reveal_{card.id}"):
            st.caption("Recall the meaning, then reveal.")
            return
        render_word_card(card.entry)


def _render_cloze(card: Card, enrichment) -> None:
    cache_key = f"cloze_{card.id}"
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = enrichment.cloze(card.entry, user_id="local")
        except BudgetExceeded:
            st.warning("Daily LLM budget reached — try **Show** or **Typing** mode.")
            return
        except Exception as exc:
            st.error(f"Cloze generation failed: {exc}")
            return
    cloze = st.session_state[cache_key]
    with st.container(border=True):
        st.markdown(f"#### Fill in the blank")
        st.markdown(f"> {cloze.sentence}")
        if st.toggle("Reveal answer", key=f"cloze_reveal_{card.id}"):
            st.success(f"**{cloze.answer}**")


def _render_typing(card: Card, target_lang: Language) -> None:
    correct = card.entry.primary_translation(target_lang) or card.entry.lemma
    with st.container(border=True):
        st.markdown(f"### {card.entry.lemma}")
        st.caption(f"Type the {target_lang.display_name} translation:")
        guess = st.text_input("Your answer", key=f"typing_{card.id}")
        if guess:
            distance = Levenshtein.distance(guess.strip().lower(), correct.lower())
            if distance == 0:
                st.success(f"✅ Exact: **{correct}**")
            elif distance <= 2:
                st.info(f"🟡 Close — exact form: **{correct}**")
            else:
                st.error(f"❌ Correct answer: **{correct}**")


def _render_mc(card: Card, target_lang: Language, enrichment) -> None:
    correct = card.entry.primary_translation(target_lang) or card.entry.lemma
    cache_key = f"mc_{card.id}"
    if cache_key not in st.session_state:
        try:
            mc = enrichment.multiple_choice(card.entry, target_lang, correct, user_id="local")
            st.session_state[cache_key] = mc
        except BudgetExceeded:
            st.warning("Daily LLM budget reached — try **Show** or **Typing** mode.")
            return
        except Exception as exc:
            st.error(f"MC generation failed: {exc}")
            return
    mc = st.session_state[cache_key]
    with st.container(border=True):
        st.markdown(f"### {card.entry.lemma}")
        st.caption(f"Pick the {target_lang.display_name} translation:")
        choice = st.radio(
            "Choices",
            mc.all_options,
            key=f"mc_choice_{card.id}",
            label_visibility="collapsed",
        )
        if st.button("Check", key=f"mc_check_{card.id}"):
            if choice == mc.correct:
                st.success(f"✅ Correct: **{mc.correct}**")
            else:
                st.error(f"❌ Correct answer: **{mc.correct}**")
