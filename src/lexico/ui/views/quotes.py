"""Quotes view: browse starred quotes + guess-the-author challenge."""

from __future__ import annotations

import hashlib
import random

import streamlit as st

from lexico.data.daily_pool import all_quotes
from lexico.domain.enums import Language
from lexico.services import get_deck_store, get_enrichment_service
from lexico.services.usage_guardrail import BudgetExceeded


_MODE_BROWSE = "⭐ Starred"
_MODE_GUESS = "🎭 Guess the author"
_ALL_LANGS = "All"
_SOURCE_STARRED = "My starred quotes"
_SOURCE_ALL = "All quotes"
_GAME_KEY = "quotes_guess_game"

# Widget keys whose values should survive switching to another tab and back.
# Streamlit can drop widget state when the widget stops being rendered across
# several reruns; the shadow-key pattern below copies values to/from a
# non-widget key so they always come back on the next visit.
_PERSIST_KEYS = (
    "quotes_mode",
    "quotes_guess_source",
    "quotes_guess_language",
)


def _restore_persisted() -> None:
    for k in _PERSIST_KEYS:
        shadow = f"_saved_{k}"
        if shadow in st.session_state and k not in st.session_state:
            st.session_state[k] = st.session_state[shadow]


def _save_persisted() -> None:
    for k in _PERSIST_KEYS:
        if k in st.session_state:
            st.session_state[f"_saved_{k}"] = st.session_state[k]


def render(user_id: str) -> None:
    _restore_persisted()
    st.title("🗣 Quotes")
    st.caption("Your collection of starred quotes — and a game to test who said what.")

    store = get_deck_store()
    enrichment = get_enrichment_service()
    mode = st.radio("Mode", [_MODE_BROWSE, _MODE_GUESS], horizontal=True, key="quotes_mode")

    if mode == _MODE_BROWSE:
        _render_browse(user_id, store, enrichment)
    else:
        _render_guess(user_id, store, enrichment)

    _save_persisted()


def _quote_key(language: Language, text: str) -> str:
    """Short stable id for session keys — quote text can be long/unicode."""
    h = hashlib.sha1(f"{language.value}::{text}".encode("utf-8")).hexdigest()
    return h[:12]


def _render_context_button(
    enrichment, language: Language, text: str, author: str, key_prefix: str
) -> None:
    """Show a 'Get context' button that caches the LLM answer per quote.

    Once fetched, the context stays in session_state so re-opening the page
    doesn't re-bill the call. The caller is expected to wrap this inside a
    container (st.container / popover / expander) for visual grouping.
    """
    qkey = _quote_key(language, text)
    cache_key = f"quote_ctx_{qkey}"
    trigger_key = f"{key_prefix}_ctx_btn_{qkey}"
    if cache_key not in st.session_state:
        if not enrichment.is_real_llm_available():
            st.caption("Set `GROQ_API_KEY` to enable quote context.")
            return
        if st.button("✨ Get context", key=trigger_key):
            try:
                with st.spinner("Asking the tutor…"):
                    st.session_state[cache_key] = enrichment.quote_context(
                        language, text, author, user_id="local"
                    )
            except BudgetExceeded:
                st.warning("Daily LLM budget reached — try again tomorrow.")
                return
            except Exception as exc:
                st.error(f"Context lookup failed: {exc}")
                return
    if cache_key in st.session_state:
        with st.expander("📖 Context", expanded=True):
            st.markdown(st.session_state[cache_key])


def _render_browse(user_id: str, store, enrichment) -> None:
    liked = store.list_liked_quotes(user_id=user_id)
    if not liked:
        st.info("No starred quotes yet — head to **Home** and tap ☆ on any Quote of the day.")
        return

    by_lang: dict[Language, list[dict]] = {}
    for q in liked:
        by_lang.setdefault(q["language"], []).append(q)

    for lang in Language:
        entries = by_lang.get(lang, [])
        if not entries:
            continue
        st.subheader(f"{lang.flag} {lang.display_name}")
        for entry in entries:
            with st.container(border=True):
                st.markdown(f"_“{entry['text']}”_")
                st.caption(f"— {entry['author']}")
                col_remove, col_ctx = st.columns([1, 3])
                with col_remove:
                    rm_key = f"unlike_{lang.value}_{_quote_key(lang, entry['text'])}"
                    if st.button("💔 Remove", key=rm_key):
                        store.unlike_quote(user_id, lang, entry["text"])
                        st.rerun()
                with col_ctx:
                    _render_context_button(
                        enrichment, lang, entry["text"], entry["author"], "browse"
                    )


def _render_guess(user_id: str, store, enrichment) -> None:
    st.markdown("Pick the author of the quote below.")

    col_src, col_lang = st.columns(2)
    with col_src:
        source = st.radio(
            "Source",
            [_SOURCE_STARRED, _SOURCE_ALL],
            horizontal=True,
            key="quotes_guess_source",
        )
    with col_lang:
        lang_choice = st.selectbox(
            "Language",
            [_ALL_LANGS, *[lang.value for lang in Language]],
            format_func=lambda v: "🌐 All" if v == _ALL_LANGS
            else f"{Language(v).flag} {Language(v).display_name}",
            key="quotes_guess_language",
        )

    pool = _build_guess_pool(user_id, store, source, lang_choice)
    if len(pool) < 4:
        if source == _SOURCE_STARRED:
            st.info(
                "Need at least 4 quotes from distinct authors to play. "
                "Star a few more on **Home**, or switch source to **All quotes**."
            )
        else:
            st.info("Not enough quotes in the pool for this filter.")
        return

    game = st.session_state.get(_GAME_KEY)
    signature = (source, lang_choice, len(pool))
    if game is None or game.get("signature") != signature:
        game = _new_round(pool, signature)
        st.session_state[_GAME_KEY] = game

    quote = game["quote"]
    st.divider()
    with st.container(border=True):
        lang = quote["language"]
        st.markdown(f"{lang.flag} _“{quote['text']}”_")

    choice = st.radio(
        "Who said it?",
        game["options"],
        index=None,
        key=f"quotes_guess_choice_{game['round_id']}",
    )
    col_check, col_next = st.columns(2)
    with col_check:
        if st.button("Check", type="primary", key=f"quotes_guess_check_{game['round_id']}"):
            game["answered"] = True
            game["picked"] = choice
            st.session_state[_GAME_KEY] = game
    with col_next:
        if st.button("Next quote", key=f"quotes_guess_next_{game['round_id']}"):
            st.session_state[_GAME_KEY] = _new_round(pool, signature)
            st.rerun()

    if game.get("answered"):
        correct = quote["author"]
        picked = game.get("picked")
        if picked is None:
            st.info(f"Answer: **{correct}**")
        elif picked == correct:
            st.success(f"✅ Correct — **{correct}**")
        else:
            st.error(f"❌ It was **{correct}**")
        _render_star_toggle(
            user_id, store, quote["language"], quote["text"], correct, "guess"
        )
        _render_context_button(
            enrichment, quote["language"], quote["text"], correct, "guess"
        )


def _render_star_toggle(
    user_id: str,
    store,
    language: Language,
    text: str,
    author: str,
    key_prefix: str,
) -> None:
    """Add/remove this quote from the user's starred collection."""
    liked = store.is_quote_liked(user_id, language, text)
    label = "⭐ Starred" if liked else "☆ Star this quote"
    btn_key = f"{key_prefix}_star_{_quote_key(language, text)}"
    if st.button(label, key=btn_key):
        if liked:
            store.unlike_quote(user_id, language, text)
        else:
            store.like_quote(user_id, language, text, author)
        st.rerun()


def _build_guess_pool(user_id: str, store, source: str, lang_choice: str) -> list[dict]:
    if source == _SOURCE_STARRED:
        raw = store.list_liked_quotes(user_id=user_id)
        items = [
            {"language": q["language"], "text": q["text"], "author": q["author"]}
            for q in raw
        ]
    else:
        items = [
            {"language": lang, "text": q.text, "author": q.author}
            for lang in Language
            for q in all_quotes(lang)
        ]
    if lang_choice != _ALL_LANGS:
        items = [q for q in items if q["language"].value == lang_choice]
    return items


def _new_round(pool: list[dict], signature: tuple) -> dict:
    quote = random.choice(pool)
    correct = quote["author"]
    distractors = _pick_distractors(pool, correct)
    options = distractors + [correct]
    random.shuffle(options)
    return {
        "signature": signature,
        "quote": quote,
        "options": options,
        "answered": False,
        "picked": None,
        "round_id": random.randint(0, 10**9),
    }


def _pick_distractors(pool: list[dict], correct: str) -> list[str]:
    authors: list[str] = []
    seen = {correct}
    shuffled = list(pool)
    random.shuffle(shuffled)
    for item in shuffled:
        author = item["author"]
        if author in seen:
            continue
        authors.append(author)
        seen.add(author)
        if len(authors) == 3:
            break
    while len(authors) < 3:
        authors.append("Anonymous")
    return authors
