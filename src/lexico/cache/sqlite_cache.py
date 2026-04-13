"""SQLite-backed persistent cache for dictionary entries and LLM outputs."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS kv_cache (
    cache_key TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT
)
"""


class SQLiteCache:
    """Persistent JSON-blob cache.

    Entries with expires_at = NULL are cached indefinitely — used for
    dictionary lookups, which are stable content.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_CREATE_TABLE)
            self._conn.commit()

    def get(self, key: str) -> Any | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json, expires_at FROM kv_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        if row[1] is not None:
            expires_at = datetime.fromisoformat(row[1])
            if datetime.now(timezone.utc) > expires_at:
                self.invalidate(key)
                return None
        return json.loads(row[0])

    def put(self, key: str, data: Any, ttl_hours: int | None = None) -> None:
        now = datetime.now(timezone.utc)
        expires_at = (
            (now + timedelta(hours=ttl_hours)).isoformat() if ttl_hours else None
        )
        blob = json.dumps(data, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv_cache (cache_key, data_json, fetched_at, expires_at) VALUES (?, ?, ?, ?)",
                (key, blob, now.isoformat(), expires_at),
            )
            self._conn.commit()

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM kv_cache WHERE cache_key = ?", (key,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM kv_cache")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
