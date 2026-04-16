"""LLM usage guardrail: enforce per-user, global, and dollar caps."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when an LLM call would exceed a configured cap."""


class _UsageBackend(Protocol):
    """Subset of DeckStore / PgDeckStore that the guardrail actually needs."""

    def llm_calls_today(self, user_id: str | None = None) -> int: ...

    def llm_usd_today(self) -> float: ...

    def log_llm_usage(
        self,
        user_id: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        usd: float,
    ) -> None: ...


class UsageGuardrail:
    """Hard budget enforcer backed by a store's llm_usage_log table.

    The API is deliberately minimal: callers ask `allow(...)` before
    making an LLM call; if it returns normally, they proceed, then
    report actual usage back via `record(...)`. A tripped cap raises
    BudgetExceeded so UI code can show a friendly message.

    The guardrail accepts any store implementing ``_UsageBackend`` — both
    the SQLite ``DeckStore`` and the Postgres ``PgDeckStore`` qualify, so
    local and cloud deployments share this code unchanged.
    """

    def __init__(
        self,
        store: _UsageBackend,
        per_user_daily: int,
        global_daily: int,
        daily_usd_cap: float,
    ) -> None:
        self._store = store
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
        # Strict `>` so a cap of 0.00 doesn't trip on free calls (usd=0);
        # it only trips once a paid provider has actually charged something.
        if self._store.llm_usd_today() > self._daily_usd_cap:
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
