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

# Carousel state for the Starred browser.
_BROWSE_ORDER_KEY = "quotes_browse_order"
_BROWSE_INDEX_KEY = "quotes_browse_index"
_BROWSE_SIG_KEY = "quotes_browse_signature"


def render(user_id: str) -> None:
    st.title("🗣 Quotes")
    st.caption("Your collection of starred quotes — and a game to test who said what.")

    store = get_deck_store()
    enrichment = get_enrichment_service()
    mode = st.radio("Mode", [_MODE_BROWSE, _MODE_GUESS], horizontal=True, key="quotes_mode")

    if mode == _MODE_BROWSE:
        _render_browse(user_id, store, enrichment)
    else:
        _render_guess(user_id, store, enrichment)


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
    """Carousel browser for starred quotes: language filter + Prev/Next."""
    liked = store.list_liked_quotes(user_id=user_id)
    if not liked:
        st.info("No starred quotes yet — head to **Home** and tap ☆ on any Quote of the day.")
        return

    lang_choice = st.selectbox(
        "Language",
        [_ALL_LANGS, *[lang.value for lang in Language]],
        format_func=lambda v: "🌐 All" if v == _ALL_LANGS
        else f"{Language(v).flag} {Language(v).display_name}",
        key="quotes_browse_language",
    )
    if lang_choice != _ALL_LANGS:
        filtered = [q for q in liked if q["language"].value == lang_choice]
    else:
        filtered = liked
    if not filtered:
        st.info("No starred quotes in this language yet.")
        return

    # Reshuffle whenever the filter or collection size changes. The signature
    # also catches "user just unstarred the current card" — we can't stay on
    # the same index because the list shrank.
    signature = (lang_choice, len(filtered))
    if st.session_state.get(_BROWSE_SIG_KEY) != signature:
        order = list(range(len(filtered)))
        random.shuffle(order)
        st.session_state[_BROWSE_ORDER_KEY] = order
        st.session_state[_BROWSE_INDEX_KEY] = 0
        st.session_state[_BROWSE_SIG_KEY] = signature

    order: list[int] = st.session_state[_BROWSE_ORDER_KEY]
    idx = st.session_state[_BROWSE_INDEX_KEY] % len(order)
    entry = filtered[order[idx]]
    lang = entry["language"]

    # Centered large slide — narrow side columns act as visual margins so the
    # card doesn't stretch edge-to-edge on wide monitors.
    _, card_col, _ = st.columns([1, 6, 1])
    with card_col:
        with st.container(border=True):
            st.markdown(
                f"<div style='text-align:center; font-size:1rem; opacity:0.7; "
                f"margin-bottom:0.5rem;'>{lang.flag} {lang.display_name}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:center; font-size:1.6rem; "
                f"line-height:1.5; font-style:italic; padding:1.5rem 1rem;'>"
                f"“{entry['text']}”</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:center; font-size:1.1rem; "
                f"margin-bottom:1rem;'>— <b>{entry['author']}</b></div>",
                unsafe_allow_html=True,
            )

        nav_prev, nav_pos, nav_next = st.columns([1, 2, 1])
        with nav_prev:
            if st.button("⬅ Prev", key="quotes_browse_prev", use_container_width=True):
                st.session_state[_BROWSE_INDEX_KEY] = (idx - 1) % len(order)
                st.rerun()
        with nav_pos:
            st.markdown(
                f"<div style='text-align:center; padding-top:0.4rem; "
                f"opacity:0.7;'>{idx + 1} / {len(order)}</div>",
                unsafe_allow_html=True,
            )
        with nav_next:
            if st.button("Next ➡", key="quotes_browse_next", use_container_width=True):
                st.session_state[_BROWSE_INDEX_KEY] = (idx + 1) % len(order)
                st.rerun()

        action_ctx, action_rm = st.columns([3, 1])
        with action_ctx:
            _render_context_button(
                enrichment, lang, entry["text"], entry["author"], "browse"
            )
        with action_rm:
            rm_key = f"unlike_{lang.value}_{_quote_key(lang, entry['text'])}"
            if st.button("💔 Remove", key=rm_key, use_container_width=True):
                store.unlike_quote(user_id, lang, entry["text"])
                st.rerun()


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
