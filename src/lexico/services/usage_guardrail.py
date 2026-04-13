"""LLM usage guardrail: enforce per-user, global, and dollar caps."""

from __future__ import annotations

import logging
from pathlib import Path

from lexico.services.deck_store import DeckStore

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when an LLM call would exceed a configured cap."""


class UsageGuardrail:
    """Hard budget enforcer backed by a DeckStore's llm_usage_log table.

    The API is deliberately minimal: callers ask `allow(...)` before
    making an LLM call; if it returns normally, they proceed, then
    report actual usage back via `record(...)`. A tripped cap raises
    BudgetExceeded so UI code can show a friendly message.
    """

    def __init__(
        self,
        db_path: str | Path,
        per_user_daily: int,
        global_daily: int,
        daily_usd_cap: float,
    ) -> None:
        self._store = DeckStore(db_path)
        self._per_user_daily = per_user_daily
        self._global_daily = global_daily
        self._daily_usd_cap = daily_usd_cap

    def allow(self, user_id: str) -> None:
        """Raise BudgetExceeded if the next call would exceed any cap."""
        if self._store.llm_calls_today(user_id) >= self._per_user_daily:
            raise BudgetExceeded(
                f"Per-user daily limit of {self._per_user_daily} LLM calls reached. "
                f"Dictionary lookups and reviews still work — come back tomorrow."
            )
        if self._store.llm_calls_today() >= self._global_daily:
            raise BudgetExceeded(
                f"Global daily limit of {self._global_daily} LLM calls reached."
            )
        if self._store.llm_usd_today() >= self._daily_usd_cap:
            raise BudgetExceeded(
                f"Global daily spend cap of ${self._daily_usd_cap:.2f} reached."
            )

    def record(
        self,
        user_id: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        usd: float,
    ) -> None:
        self._store.log_llm_usage(
            user_id=user_id,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            usd=usd,
        )
