"""streamlit-authenticator wrapper.

Local dev runs without auth (`require_auth = False` in settings). When
`[credentials]` exists in `.streamlit/secrets.toml`, `_load_settings()`
flips `require_auth=True` and this module gates the app behind a login
form.
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)


def _to_mutable(obj: Any) -> Any:
    """Deep-copy `st.secrets` into plain Python (authenticator mutates it)."""
    if hasattr(obj, "to_dict"):
        return _to_mutable(obj.to_dict())
    if isinstance(obj, dict):
        return {k: _to_mutable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_mutable(x) for x in obj]
    return obj


def _get_authenticator():
    if "authenticator" in st.session_state:
        return st.session_state["authenticator"]
    import streamlit_authenticator as stauth

    creds = _to_mutable(st.secrets.get("credentials", {}))
    cookie = _to_mutable(st.secrets.get("cookie", {}))
    authenticator = stauth.Authenticate(
        credentials=creds,
        cookie_name=cookie.get("name", "lexico_auth"),
        cookie_key=cookie.get("key", "change-me-in-secrets"),
        cookie_expiry_days=cookie.get("expiry_days", 30),
    )
    st.session_state["authenticator"] = authenticator
    return authenticator


def login_gate() -> str | None:
    """Render the login form and return the authenticated user id, or None."""
    authenticator = _get_authenticator()
    try:
        authenticator.login(location="main")
    except Exception as exc:
        logger.warning("Login form error: %s", exc)

    status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")
    if status is False:
        st.error("Username or password incorrect.")
        return None
    if status is None:
        st.info("Please enter your username and password.")
        return None
    return username


def logout_button() -> None:
    if "authenticator" in st.session_state:
        st.session_state["authenticator"].logout(location="sidebar")
