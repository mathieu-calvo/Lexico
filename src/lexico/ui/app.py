"""Streamlit entry point — router, sidebar nav, optional auth gate."""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit Cloud runs `streamlit run src/lexico/ui/app.py` from the repo root,
# so the `src` directory isn't on sys.path by default. Add it explicitly.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from lexico.config import settings  # noqa: E402
from lexico.ui import auth  # noqa: E402
from lexico.ui.views import (  # noqa: E402
    challenge,
    decks,
    home,
    lookup,
    review,
    stats,
    tutor,
)


_PAGES = {
    "🏠 Home": home.render,
    "🔍 Lookup": lookup.render,
    "📒 Decks": decks.render,
    "🧠 Review": review.render,
    "🎯 Daily challenge": challenge.render,
    "💬 Tutor": tutor.render,
    "📊 Stats": stats.render,
}


_MOBILE_CSS = """
<style>
/* Mobile shim: on narrow viewports, collapse st.columns into a vertical
   stack so word cards / quote cards / rating buttons don't overflow. */
@media (max-width: 640px) {
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }
    .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }
    h1, h2, h3 {
        word-break: break-word;
    }
}
</style>
"""


def _inject_mobile_css() -> None:
    st.markdown(_MOBILE_CSS, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Lexico — vocabulary that sticks",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_mobile_css()

    if settings.require_auth:
        user_id = auth.login_gate()
        if user_id is None:
            return
    else:
        user_id = "local"

    st.sidebar.title("📚 Lexico")
    st.sidebar.caption(f"Signed in as `{user_id}`")
    page = st.sidebar.radio("Navigation", list(_PAGES.keys()), key="nav")
    st.sidebar.divider()
    st.sidebar.caption(
        "Free Wiktionary-backed dictionary + free-tier LLM enrichment, "
        "with hard cost caps."
    )
    if settings.require_auth:
        auth.logout_button()

    _PAGES[page](user_id)


main()
