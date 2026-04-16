-- Supabase / PostgreSQL schema for Lexico.
--
-- Paste this entire file into the Supabase SQL editor and click Run.
-- Safe to re-run: every CREATE uses IF NOT EXISTS.
--
-- The app also calls these statements at startup as a safety net, but running
-- them once up front surfaces permission/connectivity issues early.

CREATE TABLE IF NOT EXISTS decks (
    id           SERIAL PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    name         TEXT NOT NULL,
    source_lang  TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS cards (
    id          SERIAL PRIMARY KEY,
    deck_id     INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    entry_json  JSONB NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    fsrs_json   JSONB NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS review_logs (
    id                SERIAL PRIMARY KEY,
    card_id           INTEGER NOT NULL,
    user_id           TEXT NOT NULL DEFAULT 'local',
    language          TEXT NOT NULL,
    rating            INTEGER NOT NULL,
    reviewed_at       TIMESTAMPTZ NOT NULL,
    elapsed_days      DOUBLE PRECISION NOT NULL,
    scheduled_days    DOUBLE PRECISION NOT NULL,
    stability_after   DOUBLE PRECISION NOT NULL,
    difficulty_after  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_usage_log (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'local',
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL,
    tokens_out  INTEGER NOT NULL,
    usd         DOUBLE PRECISION NOT NULL,
    called_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS liked_quotes (
    user_id   TEXT NOT NULL,
    language  TEXT NOT NULL,
    text      TEXT NOT NULL,
    author    TEXT NOT NULL,
    liked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, language, text)
);

CREATE INDEX IF NOT EXISTS idx_cards_deck         ON cards (deck_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user       ON review_logs (user_id, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_usage_user_time    ON llm_usage_log (user_id, called_at);
CREATE INDEX IF NOT EXISTS idx_liked_quotes_user  ON liked_quotes (user_id, liked_at);
