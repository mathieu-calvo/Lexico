-- Supabase / PostgreSQL schema for Lexico on the SHARED `hobby-apps` project.
--
-- This project hosts multiple small apps (Lexico, Incomplete-Info-Problem,
-- and any future hobby app) under one Supabase free-tier project. Each app
-- owns its own schema so tables never collide, and all apps write lightweight
-- traffic events to a single `shared.app_events` table so "traffic per app"
-- and "traffic per user" are one GROUP BY away.
--
-- Portfolio-Simulator stays on its OWN Supabase project (see its README).
--
-- Paste this entire file into the Supabase SQL editor and click Run.
-- Safe to re-run: every CREATE uses IF NOT EXISTS.

-- ---------------------------------------------------------------------------
-- Schemas
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS lexico;
CREATE SCHEMA IF NOT EXISTS shared;

-- ---------------------------------------------------------------------------
-- Lexico tables (content-heavy: decks, cards, reviews, liked quotes, LLM log)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lexico.decks (
    id           SERIAL PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'local',
    name         TEXT NOT NULL,
    source_lang  TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS lexico.cards (
    id          SERIAL PRIMARY KEY,
    deck_id     INTEGER NOT NULL REFERENCES lexico.decks(id) ON DELETE CASCADE,
    entry_json  JSONB NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    fsrs_json   JSONB NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lexico.review_logs (
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

CREATE TABLE IF NOT EXISTS lexico.llm_usage_log (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'local',
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL,
    tokens_out  INTEGER NOT NULL,
    usd         DOUBLE PRECISION NOT NULL,
    called_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lexico.liked_quotes (
    user_id   TEXT NOT NULL,
    language  TEXT NOT NULL,
    text      TEXT NOT NULL,
    author    TEXT NOT NULL,
    liked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, language, text)
);

CREATE INDEX IF NOT EXISTS idx_cards_deck         ON lexico.cards (deck_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user       ON lexico.review_logs (user_id, reviewed_at);
CREATE INDEX IF NOT EXISTS idx_usage_user_time    ON lexico.llm_usage_log (user_id, called_at);
CREATE INDEX IF NOT EXISTS idx_liked_quotes_user  ON lexico.liked_quotes (user_id, liked_at);

-- ---------------------------------------------------------------------------
-- shared.app_events — cross-app traffic / engagement log
--
-- ONE row per interesting event across every app on this Supabase project.
-- Deliberately tiny so it stays cheap: storage cost is dominated by Lexico's
-- cards and IIP's hands, not this table.
--
-- Event vocabulary (add more as needed, but keep cardinality small):
--   lexico: session_start, lookup, review, deck_created, quote_liked
--   iip:    session_start, hand_played
--
-- `user_id` is app-specific:
--   - lexico: the authenticated login username
--   - iip:    the browser-session UUID (same as `session_id`)
-- so queries always GROUP BY (app, user_id).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shared.app_events (
    id           BIGSERIAL PRIMARY KEY,
    app          TEXT NOT NULL,
    event        TEXT NOT NULL,
    user_id      TEXT,
    session_id   TEXT,
    app_version  TEXT,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    meta         JSONB
);

CREATE INDEX IF NOT EXISTS idx_app_events_app_time
    ON shared.app_events (app, occurred_at);
CREATE INDEX IF NOT EXISTS idx_app_events_app_user_time
    ON shared.app_events (app, user_id, occurred_at);

-- Lexico connects via psycopg2 as the postgres superuser, so no RLS needed
-- here. IIP writes via the anon key through PostgREST, so its schema SQL
-- (scripts/supabase_schema.sql in that repo) adds the RLS policies for
-- `shared.app_events`. Running both files is idempotent.
