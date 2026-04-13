"""Guardrail tests."""

from __future__ import annotations

import pytest

from lexico.services.usage_guardrail import BudgetExceeded, UsageGuardrail


@pytest.fixture
def guardrail(tmp_path):
    return UsageGuardrail(
        tmp_path / "lexico.db",
        per_user_daily=3,
        global_daily=5,
        daily_usd_cap=0.10,
    )


def test_allow_passes_under_caps(guardrail):
    guardrail.allow("alice")


def test_per_user_cap_trips(guardrail):
    for _ in range(3):
        guardrail.record("alice", "stub", "stub-1", 10, 20, 0.0)
    with pytest.raises(BudgetExceeded, match="Per-user"):
        guardrail.allow("alice")


def test_per_user_cap_isolates_users(guardrail):
    for _ in range(3):
        guardrail.record("alice", "stub", "stub-1", 10, 20, 0.0)
    guardrail.allow("bob")  # bob is fresh


def test_global_cap_trips(guardrail):
    for i in range(5):
        user = f"u{i}"
        guardrail.record(user, "stub", "stub-1", 10, 20, 0.0)
    with pytest.raises(BudgetExceeded, match="Global daily"):
        guardrail.allow("u_new")


def test_usd_cap_trips(guardrail):
    guardrail.record("alice", "claude", "haiku", 100, 200, 0.15)
    with pytest.raises(BudgetExceeded, match="spend cap"):
        guardrail.allow("alice")


def test_zero_usd_cap_allows_free_calls(tmp_path):
    """A $0 cap must not block free-tier calls (usd=0)."""
    g = UsageGuardrail(
        tmp_path / "lexico.db",
        per_user_daily=100,
        global_daily=100,
        daily_usd_cap=0.00,
    )
    g.allow("alice")
    g.record("alice", "groq", "llama-3.3", 50, 100, 0.0)
    g.allow("alice")  # still fine — no money spent


def test_zero_usd_cap_blocks_any_paid_call(tmp_path):
    """A $0 cap trips as soon as a paid provider records any charge."""
    g = UsageGuardrail(
        tmp_path / "lexico.db",
        per_user_daily=100,
        global_daily=100,
        daily_usd_cap=0.00,
    )
    g.record("alice", "claude", "haiku", 10, 20, 0.0001)
    with pytest.raises(BudgetExceeded, match="spend cap"):
        g.allow("alice")
