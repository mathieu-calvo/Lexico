"""Session-wide widget-state persistence across sidebar navigation.

Streamlit purges a widget's session_state entry after several reruns where
the widget isn't rendered (e.g. when you switch tabs and stay away). Users
see this as "my language picker reset itself". The fix is the shadow-key
pattern: copy each tracked key into a non-widget mirror after every render,
and copy it back before the widget is instantiated on the next visit.

Views don't need to know about this — ``restore_all``/``save_all`` are
called from ``app.main`` around the page render. To make a new widget
sticky, just add its ``key=...`` value to ``PERSIST_KEYS``.
"""

from __future__ import annotations

import streamlit as st


# Widget keys that should survive tab hops. Keep this list tight — only
# include filter/selector widgets whose values the user would expect to
# come back to, NOT transient state (text you just typed, answered-flag,
# game round ids, etc.).
PERSIST_KEYS: tuple[str, ...] = (
    # lookup
    "lookup_lang",
    # decks
    "decks_lang_filter",
    "new_deck_src",
    # review
    "review_language",
    "review_mode",
    # daily challenge
    "challenge_language",
    # quotes
    "quotes_mode",
    "quotes_browse_language",
    "quotes_guess_source",
    "quotes_guess_language",
)


_SHADOW_PREFIX = "_persist_"


def restore_all() -> None:
    """Copy shadow keys back into live widget keys before widgets render."""
    for k in PERSIST_KEYS:
        shadow = f"{_SHADOW_PREFIX}{k}"
        if shadow in st.session_state and k not in st.session_state:
            st.session_state[k] = st.session_state[shadow]


def save_all() -> None:
    """Snapshot current widget values into shadow keys after the page renders."""
    for k in PERSIST_KEYS:
        if k in st.session_state:
            st.session_state[f"{_SHADOW_PREFIX}{k}"] = st.session_state[k]
