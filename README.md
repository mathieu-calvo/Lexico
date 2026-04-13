# Lexico

A multilingual dictionary and spaced-repetition vocabulary companion for French, English, Italian, Spanish, and Portuguese. Runs on Streamlit Community Cloud.

Lexico is the 2026 rewrite of an older Dash app that scraped Reverso.net for dictionary entries. The scraping approach was fragile, slow, and rate-limited. Lexico replaces it with two bounded-cost data sources: pre-parsed Wiktionary dumps from Kaikki.org for dictionary lookups (free, offline, redistributable) and a free-tier LLM (Groq / Llama 3.3 70B) for the enrichment features — tutor chat, cloze generation, daily-challenge grading, tailored examples.

## Why no scraping

- **Fragile**: HTML parsing breaks whenever the target site ships a redesign.
- **Slow and rate-limited**: per-request network round trip, spaced sleeps, 403s on burst.
- **No ToS guarantees**: scraping a commercial dictionary is a gray area.

Kaikki ships the full Wiktionary content as parquet, so lookups are offline and free forever. An LLM only runs when the user explicitly asks for an enrichment feature (tutor, cloze, grade), bounded by hard daily caps in `services/usage_guardrail.py`.

## Features

- **Lookup**: definitions, IPA, part of speech, examples, cross-language translations, etymology nugget.
- **Personal decks**: save words into user-owned decks, clone curated themed decks ("Café French", "Italian cooking", "Lisbon weekend").
- **FSRS spaced repetition**: Again / Hard / Good / Easy ratings schedule each card with the FSRS algorithm, not the fake 0-5 widget in the old app.
- **Three review modes**: show/reveal, cloze (LLM-generated fill-in-the-blank), typing (fuzzy match), multiple choice (auto-generated distractors).
- **Daily challenge**: use 3 due words in one sentence, graded playfully by the LLM.
- **Gamification that doesn't nag**: streak counter, XP per language, A1→C2 ranks, word of the day — no guilt, no leaderboards, undoable ratings.
- **Cost caps**: per-user daily LLM limit, global daily limit, dollar cap. Enforced in SQLite `llm_usage_log`.

## Quick start

```bash
pip install -e ".[dev]"
streamlit run src/lexico/ui/app.py
```

The app runs immediately with zero API keys. On first launch the dictionary backs onto a built-in stub of ~25 demo words across all 5 languages so you can exercise every feature end-to-end before downloading real Kaikki dumps.

To enable real dictionary content:

```bash
export LEXICO_PROVIDER_ORDER=kaikki
# First run downloads and prunes Kaikki dumps to ~/.lexico/kaikki/ (1-2 min per language, one-time).
streamlit run src/lexico/ui/app.py
```

To enable tutor / cloze / challenge features, get a free Groq API key from console.groq.com and add it to `.streamlit/secrets.toml`:

```toml
GROQ_API_KEY = "gsk_..."
```

## Configuration

All settings use the `LEXICO_` prefix and can be set via environment variables or `.env`. See `src/lexico/config.py` for the full list.

Key settings:

| Setting | Default | Meaning |
|---|---|---|
| `LEXICO_PROVIDER_ORDER` | `kaikki,groq,claude` | Provider fallback chain for dictionary + LLM |
| `LEXICO_MAX_LLM_CALLS_PER_USER_PER_DAY` | `50` | Per-user daily LLM call cap |
| `LEXICO_MAX_LLM_CALLS_PER_DAY` | `500` | Global daily LLM call cap |
| `LEXICO_DAILY_USD_CAP` | `0.25` | Global daily USD spend cap |
| `LEXICO_DATABASE_URL` | unset | Postgres URL (Supabase). Omit → SQLite at `~/.lexico/lexico.db`. |
| `LEXICO_REQUIRE_AUTH` | `false` | Enable streamlit-authenticator gate |

## Architecture

```
src/lexico/
├── domain/          frozen Pydantic models (WordEntry, Deck, Card, FSRSState, Rating)
├── providers/       DictionaryProvider + LlmProvider Protocols + implementations
├── cache/           memory LRU + SQLite blob two-tier cache
├── data/            Kaikki loader + themed seed decks
├── services/        LookupService, EnrichmentService, UsageGuardrail,
│                    ReviewScheduler, DeckStore, Gamification
├── analytics/       retention, streaks, stats (pure functions)
├── ui/              Streamlit router, auth, components, views
├── config.py        pydantic-settings
└── utils/           prompts, text normalization
tests/unit/          pytest, stub-backed
```

The layering mirrors [Portfolio-Simulator](../Portfolio-Simulator/): domain → services → UI, protocol-based providers, two-tier cache, dual-store factory.

## Tests

```bash
pytest -m "not slow"   # unit tests, no network
pytest -m slow         # integration tests hitting real Kaikki + Groq (needs keys)
```

## Deployment

Push to GitHub, connect the repo on [share.streamlit.io](https://share.streamlit.io), paste the contents of `.streamlit/secrets.toml.example` into the web Secrets editor with real values. Supabase Postgres on the free tier handles multi-user state; SQLite handles local dev.

See `docs/deployment.md` once written.

## License

Dictionary content from Kaikki.org derives from Wiktionary and is licensed CC-BY-SA 3.0. Code in this repo is MIT.
