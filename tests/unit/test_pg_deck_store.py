"""Reconnect behaviour of PgDeckStore, using a fake psycopg2 connection."""

from __future__ import annotations

import psycopg2
import pytest

from lexico.services import pg_deck_store
from lexico.services.pg_deck_store import PgDeckStore


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if self._conn.drop_on_next_execute:
            # What psycopg2 does when the server side has gone away.
            self._conn.drop_on_next_execute = False
            self._conn.closed = 2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        if self._conn.fail_on_next_execute:
            self._conn.fail_on_next_execute = False
            raise psycopg2.errors.SyntaxError("boom")

    def fetchone(self):
        return (7,)

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self) -> None:
        self.closed = 0
        self.autocommit = True
        self.drop_on_next_execute = False
        self.fail_on_next_execute = False
        self.rollbacks = 0

    def cursor(self):
        if self.closed:
            raise psycopg2.InterfaceError("connection already closed")
        return _FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = 1


@pytest.fixture
def store(monkeypatch):
    conns: list[_FakeConn] = []

    def fake_connect(*args, **kwargs):
        conns.append(_FakeConn())
        return conns[-1]

    monkeypatch.setattr(pg_deck_store.psycopg2, "connect", fake_connect)
    s = PgDeckStore("postgresql://u:p@example.pooler.supabase.com/db")
    return s, conns


def test_reconnects_after_connection_already_closed(store):
    s, conns = store
    conns[0].closed = 2

    assert s.count_cards("u") == 7
    assert len(conns) == 2
    assert s._conn is conns[1]


def test_reconnects_when_query_finds_server_gone(store):
    s, conns = store
    conns[0].drop_on_next_execute = True

    assert s.list_review_logs("u") == []
    assert len(conns) == 2


def test_other_errors_roll_back_without_reconnecting(store):
    s, conns = store
    conns[0].fail_on_next_execute = True

    with pytest.raises(psycopg2.Error):
        s.count_cards("u")
    assert conns[0].rollbacks == 1
    assert len(conns) == 1
    assert s.count_cards("u") == 7
