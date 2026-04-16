"""PostgreSQL-backed persistence for decks, cards, review logs, LLM usage,
and liked quotes — mirrors the SQLite DeckStore API so call-sites don't care.

The Streamlit Cloud deployment uses this via Supabase. Local dev keeps the
SQLite backend; the factory in ``services/__init__.py`` picks based on whether
``settings.database_url`` is set.

Dialect deltas from the SQLite version:
- ``SERIAL`` in place of ``AUTOINCREMENT``, ``%s`` placeholders, native
  JSONB columns, TIMESTAMPTZ for all time columns.
- ``ON CONFLICT ... DO UPDATE`` is identical to SQLite's syntax.
- ``json_extract(col, '$.k')`` becomes ``(col ->> 'k')``.
- Due-card filtering happens in SQL using the ``fsrs_json ->> 'due_at'``
  ISO-string comparison; same ordering and limit semantics as SQLite.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, time, timedelta, timezone

import psycopg2
import psycopg2.extras

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language
from lexico.domain.review import FSRSState, ReviewLog
from lexico.domain.word import WordEntry

logger = logging.getLogger(__name__)


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS decks (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'local',
        name TEXT NOT NULL,
        source_lang TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS cards (
        id SERIAL PRIMARY KEY,
        deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
        entry_json JSONB NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        fsrs_json JSONB NOT NULL,
        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS review_logs (
        id SERIAL PRIMARY KEY,
        card_id INTEGER NOT NULL,
        user_id TEXT NOT NULL DEFAULT 'local',
        language TEXT NOT NULL,
        rating INTEGER NOT NULL,
        reviewed_at TIMESTAMPTZ NOT NULL,
        elapsed_days DOUBLE PRECISION NOT NULL,
        scheduled_days DOUBLE PRECISION NOT NULL,
        stability_after DOUBLE PRECISION NOT NULL,
        difficulty_after DOUBLE PRECISION NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS llm_usage_log (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'local',
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        tokens_in INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL,
        usd DOUBLE PRECISION NOT NULL,
        called_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS liked_quotes (
        user_id TEXT NOT NULL,
        language TEXT NOT NULL,
        text TEXT NOT NULL,
        author TEXT NOT NULL,
        liked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, language, text)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cards_deck ON cards(deck_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_user ON review_logs(user_id, reviewed_at)",
    "CREATE INDEX IF NOT EXISTS idx_usage_user_time ON llm_usage_log(user_id, called_at)",
    "CREATE INDEX IF NOT EXISTS idx_liked_quotes_user ON liked_quotes(user_id, liked_at)",
]


def _ensure_ssl(url: str) -> str:
    """Supabase requires SSL; tack ?sslmode=require on if the caller forgot."""
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _today_utc_bounds() -> tuple[datetime, datetime]:
    """Return [start, end) of today in UTC for range-based date filtering."""
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _to_jsonb(obj) -> str:
    """Serialize a Pydantic model (or dict) to a JSON string for a ::jsonb cast.

    We use ``model_dump_json()`` rather than ``model_dump()`` + ``json.dumps``
    because Pydantic's JSON encoder already handles ``datetime`` correctly
    (ISO-8601 strings). ``psycopg2.extras.Json`` would use the stdlib encoder
    instead and choke on datetime values inside FSRS state.
    """
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()
    return json.dumps(obj, default=str)


class PgDeckStore:
    """Public API mirrors ``DeckStore`` — callers don't care which backend.

    Thread-safety: psycopg2 connections are not inherently thread-safe, so
    every read/write is serialized via ``self._lock``. Streamlit's rerun
    model keeps contention low; we don't need a pool.
    """

    def __init__(self, database_url: str) -> None:
        url = _ensure_ssl(database_url)
        try:
            self._conn = psycopg2.connect(url, connect_timeout=10)
        except psycopg2.OperationalError as exc:
            raise RuntimeError(
                f"Failed to connect to PostgreSQL: {exc}. "
                "Use the Supabase Session pooler connection string — the hostname "
                "must contain 'pooler.supabase.com'. URL-encode any special "
                "characters in the password."
            ) from exc
        self._conn.autocommit = False
        self._lock = threading.Lock()
        self._bootstrap_schema()

    def _bootstrap_schema(self) -> None:
        with self._lock, self._conn.cursor() as cur:
            for stmt in _SCHEMA:
                cur.execute(stmt)
            self._conn.commit()

    # ---------- decks ----------

    def create_deck(self, deck: Deck) -> Deck:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO decks (user_id, name, source_lang, description, created_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, name)
                   DO UPDATE SET description = EXCLUDED.description
                   RETURNING id""",
                (
                    deck.user_id,
                    deck.name,
                    deck.source_lang.value,
                    deck.description,
                    deck.created_at,
                ),
            )
            deck_id = cur.fetchone()[0]
            self._conn.commit()
        return deck.model_copy(update={"id": deck_id})

    def list_decks(self, user_id: str = "local") -> list[Deck]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT id, user_id, name, source_lang, description, created_at
                   FROM decks WHERE user_id = %s ORDER BY created_at""",
                (user_id,),
            )
            rows = cur.fetchall()
        return [
            Deck(
                id=row[0],
                user_id=row[1],
                name=row[2],
                source_lang=Language(row[3]),
                description=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    def delete_deck(self, deck_id: int) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("DELETE FROM decks WHERE id = %s", (deck_id,))
            self._conn.commit()

    # ---------- cards ----------

    def add_card(self, card: Card) -> Card:
        if card.deck_id is None:
            raise ValueError("Card must have a deck_id before saving")
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cards (deck_id, entry_json, note, fsrs_json, added_at)
                   VALUES (%s, %s::jsonb, %s, %s::jsonb, %s)
                   RETURNING id""",
                (
                    card.deck_id,
                    _to_jsonb(card.entry),
                    card.note,
                    _to_jsonb(card.fsrs_state),
                    card.added_at,
                ),
            )
            card_id = cur.fetchone()[0]
            self._conn.commit()
        return card.model_copy(update={"id": card_id})

    def delete_card(self, card_id: int) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute("DELETE FROM review_logs WHERE card_id = %s", (card_id,))
            cur.execute("DELETE FROM cards WHERE id = %s", (card_id,))
            self._conn.commit()

    def update_card_state(self, card_id: int, state: FSRSState) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                "UPDATE cards SET fsrs_json = %s::jsonb WHERE id = %s",
                (_to_jsonb(state), card_id),
            )
            self._conn.commit()

    def list_cards(self, deck_id: int) -> list[Card]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT id, deck_id, entry_json, note, fsrs_json, added_at
                   FROM cards WHERE deck_id = %s ORDER BY added_at""",
                (deck_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_card(row) for row in rows]

    def get_due_cards(
        self, user_id: str = "local", now: datetime | None = None, limit: int = 50
    ) -> list[Card]:
        """Return at most `limit` cards whose due_at is in the past.

        We order by the ISO-string ``fsrs_json ->> 'due_at'`` in SQL (ISO 8601
        sorts lexicographically), take the earliest N, and then filter in
        Python — exactly the same shape as the SQLite backend so behavior
        stays identical.
        """
        cutoff = (now or datetime.now(timezone.utc)).isoformat()
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT c.id, c.deck_id, c.entry_json, c.note, c.fsrs_json, c.added_at
                   FROM cards c
                   JOIN decks d ON d.id = c.deck_id
                   WHERE d.user_id = %s
                   ORDER BY (c.fsrs_json ->> 'due_at') ASC
                   LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
        cards = [self._row_to_card(row) for row in rows]
        return [c for c in cards if c.fsrs_state.due_at.isoformat() <= cutoff]

    def count_cards(self, user_id: str = "local") -> int:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM cards c
                   JOIN decks d ON d.id = c.deck_id
                   WHERE d.user_id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
        return int(row[0])

    def _row_to_card(self, row: tuple) -> Card:
        # psycopg2 auto-decodes JSONB into Python dicts, so we use
        # model_validate (dict) rather than model_validate_json (str).
        entry = row[2] if isinstance(row[2], (dict, list)) else json.loads(row[2])
        fsrs = row[4] if isinstance(row[4], (dict, list)) else json.loads(row[4])
        return Card(
            id=row[0],
            deck_id=row[1],
            entry=WordEntry.model_validate(entry),
            note=row[3],
            fsrs_state=FSRSState.model_validate(fsrs),
            added_at=row[5],
        )

    # ---------- review logs ----------

    def log_review(
        self, log: ReviewLog, user_id: str = "local", language: Language = Language.FR
    ) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO review_logs
                   (card_id, user_id, language, rating, reviewed_at, elapsed_days,
                    scheduled_days, stability_after, difficulty_after)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    log.card_id,
                    user_id,
                    language.value,
                    int(log.rating),
                    log.reviewed_at,
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
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT r.card_id, r.language, r.rating, r.reviewed_at,
                          r.elapsed_days, r.scheduled_days,
                          r.stability_after, r.difficulty_after,
                          c.entry_json
                   FROM review_logs r
                   LEFT JOIN cards c ON c.id = r.card_id
                   WHERE r.user_id = %s
                   ORDER BY r.reviewed_at DESC LIMIT %s""",
                (user_id, limit),
            )
            rows = cur.fetchall()
        out: list[dict] = []
        for r in rows:
            lemma = ""
            gloss = ""
            entry_raw = r[8]
            if entry_raw is not None:
                try:
                    entry_dict = entry_raw if isinstance(entry_raw, dict) else json.loads(entry_raw)
                    entry = WordEntry.model_validate(entry_dict)
                    lemma = entry.lemma
                    if entry.senses:
                        gloss = entry.senses[0].gloss
                except Exception:
                    pass
            out.append(
                {
                    "card_id": r[0],
                    "language": r[1],
                    "rating": r[2],
                    "reviewed_at": r[3],
                    "elapsed_days": r[4],
                    "scheduled_days": r[5],
                    "stability_after": r[6],
                    "difficulty_after": r[7],
                    "lemma": lemma,
                    "gloss": gloss,
                }
            )
        return out

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
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_usage_log
                   (user_id, provider, model, tokens_in, tokens_out, usd, called_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    user_id,
                    provider,
                    model,
                    tokens_in,
                    tokens_out,
                    usd,
                    datetime.now(timezone.utc),
                ),
            )
            self._conn.commit()

    def llm_calls_today(self, user_id: str | None = None) -> int:
        start, end = _today_utc_bounds()
        with self._lock, self._conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """SELECT COUNT(*) FROM llm_usage_log
                       WHERE user_id = %s AND called_at >= %s AND called_at < %s""",
                    (user_id, start, end),
                )
            else:
                cur.execute(
                    """SELECT COUNT(*) FROM llm_usage_log
                       WHERE called_at >= %s AND called_at < %s""",
                    (start, end),
                )
            row = cur.fetchone()
        return int(row[0])

    def llm_usd_today(self) -> float:
        start, end = _today_utc_bounds()
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM(usd), 0) FROM llm_usage_log
                   WHERE called_at >= %s AND called_at < %s""",
                (start, end),
            )
            row = cur.fetchone()
        return float(row[0])

    # ---------- liked quotes ----------

    def like_quote(
        self, user_id: str, language: Language, text: str, author: str
    ) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO liked_quotes (user_id, language, text, author, liked_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, language, text)
                   DO UPDATE SET author = EXCLUDED.author""",
                (user_id, language.value, text, author, datetime.now(timezone.utc)),
            )
            self._conn.commit()

    def unlike_quote(self, user_id: str, language: Language, text: str) -> None:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """DELETE FROM liked_quotes
                   WHERE user_id = %s AND language = %s AND text = %s""",
                (user_id, language.value, text),
            )
            self._conn.commit()

    def is_quote_liked(self, user_id: str, language: Language, text: str) -> bool:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM liked_quotes
                   WHERE user_id = %s AND language = %s AND text = %s""",
                (user_id, language.value, text),
            )
            row = cur.fetchone()
        return row is not None

    def list_liked_quotes(
        self, user_id: str = "local", language: Language | None = None
    ) -> list[dict]:
        with self._lock, self._conn.cursor() as cur:
            if language is None:
                cur.execute(
                    """SELECT language, text, author, liked_at
                       FROM liked_quotes WHERE user_id = %s
                       ORDER BY liked_at DESC""",
                    (user_id,),
                )
            else:
                cur.execute(
                    """SELECT language, text, author, liked_at
                       FROM liked_quotes WHERE user_id = %s AND language = %s
                       ORDER BY liked_at DESC""",
                    (user_id, language.value),
                )
            rows = cur.fetchall()
        return [
            {
                "language": Language(r[0]),
                "text": r[1],
                "author": r[2],
                "liked_at": r[3],
            }
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
