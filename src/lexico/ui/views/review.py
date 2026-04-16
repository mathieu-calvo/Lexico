"""Review view: FSRS queue with Reveal / Cloze / Recall / Match modes.

Source-only, immersion-first. The user never has to read English (or any
pivot) to review a word — definitions and prompts stay in the card's own
language.

Each card goes through a two-phase state machine:

    question → answered

In the `question` phase the user sees a prompt and has a single primary
action (reveal, check, type, or pick). Rating buttons only appear once the
card has moved to `answered`, so you never grade a card blind. After rating,
the state is cleared and Streamlit reruns to show the next due card —
auto-advance with no extra click.
"""

from __future__ import annotations

import random

import streamlit as st
from rapidfuzz.distance import Levenshtein

from lexico.domain.deck import Card
from lexico.domain.enums import Language
from lexico.providers.stub_provider import _STUB_ENTRIES
from lexico.services import get_deck_store, get_enrichment_service
from lexico.services.review_scheduler import schedule
from lexico.services.usage_guardrail import BudgetExceeded
from lexico.ui.components.rating_widget import rating_buttons
from lexico.ui.components.word_card import render_word_card


_MODES = ["Reveal", "Cloze", "Recall", "Match"]
_ALL_LANGS = "All"
_CURRENT_CARD_KEY = "review_current_card_id"


def _answered_key(card_id: int | None) -> str:
    return f"review_answered_{card_id}"


def _mark_answered(card_id: int | None) -> None:
    if card_id is not None:
        st.session_state[_answered_key(card_id)] = True


def _is_answered(card_id: int | None) -> bool:
    return bool(card_id is not None and st.session_state.get(_answered_key(card_id)))


def _clear_card_state(card_id: int | None) -> None:
    if card_id is None:
        return
    for prefix in ("review_answered_", "reveal_", "cloze_", "cloze_reveal_",
                   "cloze_guess_", "recall_", "match_", "match_choice_",
                   "match_check_"):
        st.session_state.pop(f"{prefix}{card_id}", None)
    st.session_state.pop(_CURRENT_CARD_KEY, None)


def render(user_id: str) -> None:
    st.title("🧠 Review")
    st.caption("Spaced repetition queue — rate your recall to schedule the next review.")

    store = get_deck_store()
    enrichment = get_enrichment_service()

    decks = {d.id: d for d in store.list_decks(user_id=user_id)}
    if not decks:
        st.info("No decks yet — head to **Lookup** or **Decks** to create one.")
        return

    col_lang, col_mode = st.columns([1, 3])
    with col_lang:
        lang_choice = st.selectbox(
            "Language",
            [_ALL_LANGS, *[lang.value for lang in Language]],
            format_func=lambda v: "🌐 All" if v == _ALL_LANGS
            else f"{Language(v).flag} {Language(v).display_name}",
            key="review_language",
        )
    with col_mode:
        mode = st.radio("Mode", _MODES, horizontal=True, key="review_mode")

    due_cards = store.get_due_cards(user_id=user_id, limit=500)
    if lang_choice != _ALL_LANGS:
        due_cards = [c for c in due_cards if c.entry.language.value == lang_choice]
    if not due_cards:
        st.success("🎉 Nothing due for this selection. Come back later!")
        return

    card = _pick_current_card(due_cards)
    deck = decks.get(card.deck_id)
    if deck is None:
        st.warning("Card belongs to a missing deck.")
        return

    st.markdown(f"_{deck.source_lang.flag} {deck.name}_")

    if mode == "Reveal":
        _render_reveal(card)
    elif mode == "Cloze":
        _render_cloze(card, enrichment)
    elif mode == "Recall":
        _render_recall(card)
    elif mode == "Match":
        _render_match(card, deck.id, store)

    if not _is_answered(card.id):
        return

    st.divider()
    st.caption("Rate your recall to schedule the next review.")
    rating = rating_buttons(key_prefix=f"rate_{card.id}")
    if rating is not None and card.id is not None:
        new_state, log = schedule(card.fsrs_state, rating)
        store.update_card_state(card.id, new_state)
        log = log.model_copy(update={"card_id": card.id})
        store.log_review(log, user_id=user_id, language=card.entry.language)
        st.toast(f"Scheduled +{new_state.stability:.1f}d", icon="✅")
        _clear_card_state(card.id)
        st.rerun()


def _pick_current_card(due_cards: list[Card]) -> Card:
    """Stick with the same card across reruns; pick a fresh random one otherwise.

    The current card id is held in session state so that switching modes or
    typing a guess doesn't reshuffle mid-review. It's cleared after rating
    (see _clear_card_state), which is the signal to roll the dice again.
    """
    due_ids = {c.id for c in due_cards}
    current_id = st.session_state.get(_CURRENT_CARD_KEY)
    if current_id in due_ids:
        return next(c for c in due_cards if c.id == current_id)
    card = random.choice(due_cards)
    st.session_state[_CURRENT_CARD_KEY] = card.id
    return card


def _render_reveal(card: Card) -> None:
    with st.container(border=True):
        st.markdown(f"### {card.entry.lemma}")
        if not _is_answered(card.id):
            st.caption("Recall the meaning in your head, then reveal.")
            if st.button("Reveal", key=f"reveal_btn_{card.id}", type="primary"):
                _mark_answered(card.id)
                st.rerun()
            return
        render_word_card(card.entry)


def _render_cloze(card: Card, enrichment) -> None:
    cache_key = f"cloze_{card.id}"
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = enrichment.cloze(card.entry, user_id="local")
        except BudgetExceeded:
            st.warning("Daily LLM budget reached — try **Reveal** or **Recall** mode.")
            return
        except Exception as exc:
            st.error(f"Cloze generation failed: {exc}")
            return
    cloze = st.session_state[cache_key]
    with st.container(border=True):
        st.markdown("#### Fill in the blank")
        st.markdown(f"> {cloze.sentence}")
        guess = st.text_input("Your answer", key=f"cloze_guess_{card.id}")
        if not _is_answered(card.id):
            if st.button("Check", key=f"cloze_btn_{card.id}", type="primary"):
                _mark_answered(card.id)
                st.rerun()
            return
        _render_text_feedback(guess, cloze.answer)


def _render_recall(card: Card) -> None:
    """Definition shown in the card's own language; type the lemma back."""
    first_sense = card.entry.senses[0].gloss if card.entry.senses else ""
    with st.container(border=True):
        st.caption(f"{card.entry.language.display_name} — type the word for:")
        st.markdown(f"> {first_sense}")
        guess = st.text_input("Your answer", key=f"recall_{card.id}")
        if not _is_answered(card.id):
            if st.button("Check", key=f"recall_btn_{card.id}", type="primary"):
                _mark_answered(card.id)
                st.rerun()
            return
        _render_text_feedback(guess, card.entry.lemma)


def _render_text_feedback(guess: str, answer: str) -> None:
    """Shared feedback for typed-answer modes (Recall, Cloze)."""
    cleaned = (guess or "").strip()
    if not cleaned:
        st.info(f"Correct answer: **{answer}**")
        return
    distance = Levenshtein.distance(cleaned.lower(), answer.lower())
    if distance == 0:
        st.success(f"✅ Exact: **{answer}**")
    elif distance <= 2:
        st.info(f"🟡 Close — exact form: **{answer}**")
    else:
        st.error(f"❌ Correct answer: **{answer}**")


def _render_match(card: Card, deck_id: int | None, store) -> None:
    """Pick the correct source-language definition from four options.

    Distractors come from other cards in the same deck, falling back to
    stub entries in the same language. No LLM call needed.
    """
    correct = card.entry.senses[0].gloss if card.entry.senses else card.entry.lemma
    cache_key = f"match_{card.id}"
    if cache_key not in st.session_state:
        distractors = _match_distractors(card, deck_id, store)
        if len(distractors) < 3:
            st.warning(
                "Match needs at least 4 cards of the same language. "
                "Add more words to this deck, or use **Reveal** mode."
            )
            return
        rng = random.Random(hash((card.id, card.entry.lemma)))
        options = rng.sample(distractors, 3) + [correct]
        rng.shuffle(options)
        st.session_state[cache_key] = {"correct": correct, "options": options}

    payload = st.session_state[cache_key]
    with st.container(border=True):
        st.markdown(f"### {card.entry.lemma}")
        st.caption(f"Pick the correct {card.entry.language.display_name} definition:")
        choice = st.radio(
            "Choices",
            payload["options"],
            index=None,
            key=f"match_choice_{card.id}",
            label_visibility="collapsed",
        )
        if not _is_answered(card.id):
            if st.button("Check", key=f"match_check_{card.id}", type="primary"):
                _mark_answered(card.id)
                st.rerun()
            return
        if choice is None:
            st.info(f"Correct answer: _{payload['correct']}_")
        elif choice == payload["correct"]:
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Correct answer: _{payload['correct']}_")


def _match_distractors(card: Card, deck_id: int | None, store) -> list[str]:
    language = card.entry.language
    lemma = card.entry.lemma
    out: list[str] = []
    seen: set[str] = set()

    def _take(gloss: str) -> None:
        if gloss and gloss not in seen:
            out.append(gloss)
            seen.add(gloss)

    if deck_id is not None:
        for other in store.list_cards(deck_id):
            if other.entry.lemma == lemma or other.entry.language != language:
                continue
            if other.entry.senses:
                _take(other.entry.senses[0].gloss)

    if len(out) < 3:
        for stub in _STUB_ENTRIES:
            if stub.language != language or stub.lemma == lemma:
                continue
            if stub.senses:
                _take(stub.senses[0].gloss)
            if len(out) >= 8:
                break

    return out
