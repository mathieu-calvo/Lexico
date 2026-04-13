"""SQLite-backed persistence for decks, cards, review logs, and LLM usage."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language
from lexico.domain.review import FSRSState, ReviewLog
from lexico.domain.word import WordEntry

logger = logging.getLogger(__name__)


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT 'local',
        name TEXT NOT NULL,
        source_lang TEXT NOT NULL,
        target_lang TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(user_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER NOT NULL,
        entry_json TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        fsrs_json TEXT NOT NULL,
        added_at TEXT NOT NULL,
        FOREIGN KEY(deck_id) REFERENCES decks(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS review_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL,
        user_id TEXT NOT NULL DEFAULT 'local',
        language TEXT NOT NULL,
        rating INTEGER NOT NULL,
        reviewed_at TEXT NOT NULL,
        elapsed_days REAL NOT NULL,
        scheduled_days REAL NOT NULL,
        stability_after REAL NOT NULL,
        difficulty_after REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS llm_usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT 'local',
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        tokens_in INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL,
        usd REAL NOT NULL,
        called_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cards_deck ON cards(deck_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_user ON review_logs(user_id, reviewed_at)",
    "CREATE INDEX IF NOT EXISTS idx_usage_user_time ON llm_usage_log(user_id, called_at)",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeckStore:
    """CRUD over decks, cards, review logs, and llm usage in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock:
            for stmt in _SCHEMA:
                self._conn.execute(stmt)
            self._conn.commit()

    # ---------- decks ----------

    def create_deck(self, deck: Deck) -> Deck:
        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO decks (user_id, name, source_lang, target_lang, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, name) DO UPDATE SET description = excluded.description""",
                (
                    deck.user_id,
                    deck.name,
                    deck.source_lang.value,
                    deck.target_lang.value,
                    deck.description,
                    deck.created_at.isoformat(),
                ),
            )
            self._conn.commit()
            deck_id = cursor.lastrowid or self._get_deck_id(deck.user_id, deck.name)
        return deck.model_copy(update={"id": deck_id})

    def _get_deck_id(self, user_id: str, name: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM decks WHERE user_id = ? AND name = ?", (user_id, name)
        ).fetchone()
        if row is None:
            raise KeyError(f"Deck {name!r} not found for {user_id}")
        return row[0]

    def list_decks(self, user_id: str = "local") -> list[Deck]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, user_id, name, source_lang, target_lang, description, created_at
                   FROM decks WHERE user_id = ? ORDER BY created_at""",
                (user_id,),
            ).fetchall()
        return [
            Deck(
                id=row[0],
                user_id=row[1],
                name=row[2],
                source_lang=Language(row[3]),
                target_lang=Language(row[4]),
                description=row[5],
                created_at=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]

    def delete_deck(self, deck_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cards WHERE deck_id = ?", (deck_id,))
            self._conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
            self._conn.commit()

    # ---------- cards ----------

    def add_card(self, card: Card) -> Card:
        if card.deck_id is None:
            raise ValueError("Card must have a deck_id before saving")
        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO cards (deck_id, entry_json, note, fsrs_json, added_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    card.deck_id,
                    card.entry.model_dump_json(),
                    card.note,
                    card.fsrs_state.model_dump_json(),
                    card.added_at.isoformat(),
                ),
            )
            self._conn.commit()
            return card.model_copy(update={"id": cursor.lastrowid})

    def update_card_state(self, card_id: int, state: FSRSState) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE cards SET fsrs_json = ? WHERE id = ?",
                (state.model_dump_json(), card_id),
            )
            self._conn.commit()

    def list_cards(self, deck_id: int) -> list[Card]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, deck_id, entry_json, note, fsrs_json, added_at
                   FROM cards WHERE deck_id = ? ORDER BY added_at""",
                (deck_id,),
            ).fetchall()
        return [self._row_to_card(row) for row in rows]

    def get_due_cards(
        self, user_id: str = "local", now: datetime | None = None, limit: int = 50
    ) -> list[Card]:
        t = (now or datetime.now(timezone.utc)).isoformat()
        with self._lock:
            rows = self._conn.execute(
                """SELECT c.id, c.deck_id, c.entry_json, c.note, c.fsrs_json, c.added_at
                   FROM cards c
                   JOIN decks d ON d.id = c.deck_id
                   WHERE d.user_id = ?
                   ORDER BY json_extract(c.fsrs_json, '$.due_at') ASC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        cards = [self._row_to_card(row) for row in rows]
        return [c for c in cards if c.fsrs_state.due_at.isoformat() <= t]

    def count_cards(self, user_id: str = "local") -> int:
        with self._lock:
            row = self._conn.execute(
                """SELECT COUNT(*) FROM cards c
                   JOIN decks d ON d.id = c.deck_id
                   WHERE d.user_id = ?""",
                (user_id,),
            ).fetchone()
        return row[0]

    def _row_to_card(self, row: tuple) -> Card:
        return Card(
            id=row[0],
            deck_id=row[1],
            entry=WordEntry.model_validate_json(row[2]),
            note=row[3],
            fsrs_state=FSRSState.model_validate_json(row[4]),
            added_at=datetime.fromisoformat(row[5]),
        )

    # ---------- review logs ----------

    def log_review(self, log: ReviewLog, user_id: str = "local", language: Language = Language.FR) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO review_logs
                   (card_id, user_id, language, rating, reviewed_at, elapsed_days,
                    scheduled_days, stability_after, difficulty_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log.card_id,
                    user_id,
                    language.value,
                    int(log.rating),
                    log.reviewed_at.isoformat(),
                    log.elapsed_days,
                    log.scheduled_days,
                    log.stability_after,
                    log.difficulty_after,
                ),
            )
            self._conn.commit()

    def list_review_logs(
        self, user_id: str = "local", limit: int = 1000
    ) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT card_id, language, rating, reviewed_at, elapsed_days,
                          scheduled_days, stability_after, difficulty_after
                   FROM review_logs WHERE user_id = ?
                   ORDER BY reviewed_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "card_id": r[0],
                "language": r[1],
                "rating": r[2],
                "reviewed_at": datetime.fromisoformat(r[3]),
                "elapsed_days": r[4],
                "scheduled_days": r[5],
                "stability_after": r[6],
                "difficulty_after": r[7],
            }
            for r in rows
        ]

    # ---------- llm usage ----------

    def log_llm_usage(
        self,
        user_id: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        usd: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO llm_usage_log
                   (user_id, provider, model, tokens_in, tokens_out, usd, called_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, provider, model, tokens_in, tokens_out, usd, _now_iso()),
            )
            self._conn.commit()

    def llm_calls_today(self, user_id: str | None = None) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            if user_id:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_log WHERE user_id = ? AND date(called_at) = ?",
                    (user_id, today),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_log WHERE date(called_at) = ?",
                    (today,),
                ).fetchone()
        return row[0]

    def llm_usd_today(self) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(usd), 0) FROM llm_usage_log WHERE date(called_at) = ?",
                (today,),
            ).fetchone()
        return float(row[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
