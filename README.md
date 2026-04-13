# Lexico

A multilingual dictionary and spaced-repetition vocabulary companion for French, English, Italian, Spanish, and Portuguese. Built with Streamlit and deployable for free on Streamlit Community Cloud.

Look up a word. Save it to a deck. Come back every day and the app tells you exactly which words are due, in the right amount, in the right moment — so you actually remember them.

---

## Core concepts

Lexico has exactly four things to understand. Once these click, the rest of the UI is obvious.

### 1. Word entry

A **word entry** is one lemma in one language — the thing you'd find on a dictionary page. Every entry holds:

- the headword and its IPA pronunciation
- one or more **senses** (definitions), each with its part of speech and example sentences
- **translations** into the other four supported languages
- a short etymology nugget
- a CEFR difficulty estimate (A1 → C2)

Word entries are read-only dictionary content. You never edit them — you just look them up and decide whether they're worth saving.

### 2. Deck

A **deck** is your personal bucket of words to learn. Think of it as a labelled folder: *"Café French"*, *"Italian cooking vocab"*, *"Words I keep forgetting"*. Each deck has:

- a name (yours)
- a **source language** — the language of the words inside
- a **target language** — the language you want to translate *to* when reviewing

Decks are created on the **Decks** page, or on the fly from the **Lookup** page when you save a new word.

### 3. Card

A **card** is one word entry saved inside a deck, plus the learning state that belongs to *you* — your history with that specific word. When you add a word to a deck, Lexico wraps the entry in a card and starts tracking:

- when you first added it
- how many times you've reviewed it
- how well you remembered it last time
- **when it's next due** (computed by the FSRS scheduler, see below)

The same word can live in multiple decks as independent cards if you want.

### 4. Review and the FSRS scheduler

When you open the **Review** page, Lexico pulls the cards that are due right now and asks you to recall them one at a time. After each attempt you rate how it went with one of four buttons:

| Button | Meaning | Effect on schedule |
|---|---|---|
| ❌ **Again** | I didn't remember it | Shown again very soon |
| 🟠 **Hard** | I struggled | Short interval |
| 🟢 **Good** | I got it | Normal interval |
| ✨ **Easy** | Too easy | Long interval |

Behind the buttons is **FSRS** — a modern spaced-repetition algorithm that tracks each card's *stability* (how long you'll remember it) and *difficulty*. Every rating updates those two numbers and schedules the next review for exactly the moment you're about to forget. Cards you find easy drift toward monthly, yearly, then decade-long intervals. Cards you struggle with stay close until they stick.

You can review the same due card in **four different modes**, switchable from the top of the Review page:

- **Show** — classic flashcard: lemma on top, reveal the full entry
- **Cloze** — fill in the blank in an LLM-generated sentence
- **Typing** — type the translation; fuzzy-matched so near-misses count as "close"
- **Multiple choice** — pick the correct translation from LLM-generated distractors

### Putting it together

```
Word entry  →  Card  →  Deck  →  Review queue  →  FSRS schedule
(dictionary)   (yours)  (your    (today's due)    (tomorrow's
                        folder)                    due list)
```

Look up a word → save it into a deck as a card → review it → rate your recall → the scheduler picks the next date. Repeat daily.

---

## Features on top of the core loop

- **Word of the day** per language on the home dashboard (deterministic rotation so the same date gives the same word)
- **Daily challenge** — use three of your due words in one sentence; a small LLM call grades it warmly
- **Tutor chat** — free-form questions about a word, contrastive examples, register explanations
- **Gamification that doesn't nag** — per-language XP, A1 → C2 ranks, gentle streak counter. No leaderboards, no guilt.
- **Stats page** — retention curves, reviews per day, due counts, XP progress
- **Etymology nuggets** — one-line word histories shown on every entry

---

## Data sources and cost model

Lexico is designed to run at **zero dollars per month** by default.

- **Dictionary content** comes from **[Kaikki.org](https://kaikki.org/)** — pre-parsed Wiktionary dumps shipped as structured data, free, offline, redistributable under CC-BY-SA. One download per language, then every lookup is an in-memory read. No API, no rate limits, no ongoing cost.
- **LLM enrichment** (cloze sentences, multiple-choice distractors, daily-challenge grading, tutor chat) uses **[Groq](https://console.groq.com/)**'s free tier — Llama 3.3 70B, ~14 400 requests/day at time of writing. Zero dollars per call. Only used when you actually open a feature that needs it; the core dictionary + review loop never calls an LLM.

### Cost caps

Even though the default providers are free, every LLM call routes through `services/usage_guardrail.py`, which enforces three hard limits against a SQLite `llm_usage_log` table:

| Cap | Default | Override |
|---|---|---|
| Per-user calls per day | 50 | `LEXICO_MAX_LLM_CALLS_PER_USER_PER_DAY` |
| Global calls per day | 500 | `LEXICO_MAX_LLM_CALLS_PER_DAY` |
| Global USD spend per day | **$0.00** | `LEXICO_DAILY_USD_CAP` |

**Paid LLMs are disabled out of the box.** The USD cap ships at `$0.00`, and the default provider chain is `stub,kaikki,groq` — no paid backend is registered. If you ever want to opt into paid Claude, you'd need to both set `ANTHROPIC_API_KEY` *and* raise `LEXICO_DAILY_USD_CAP` above zero. Nothing in the codebase spends money by default.

When a cap trips, the UI shows a friendly "daily budget reached" message and the dictionary + review features keep working normally.

---

## Quick start

```bash
pip install -e ".[dev]"
streamlit run src/lexico/ui/app.py
```

The app runs immediately with zero setup. The default provider chain falls back to a built-in **stub dictionary** — ~25 hand-curated demo words across all 5 languages — so every page (home, lookup, decks, review modes, challenge, tutor, stats) is fully clickable before you download anything.

To enable the full Wiktionary dictionary once the Kaikki loader lands:

```bash
export LEXICO_PROVIDER_ORDER=stub,kaikki
streamlit run src/lexico/ui/app.py
```

To enable tutor / cloze / challenge features with a real LLM, grab a free Groq API key at [console.groq.com](https://console.groq.com) and add it to `.streamlit/secrets.toml`:

```toml
GROQ_API_KEY = "gsk_..."
```

Then set `LEXICO_PROVIDER_ORDER=stub,kaikki,groq`.

---

## Configuration

All settings use the `LEXICO_` prefix and can be set via environment variables or a `.env` file. See `src/lexico/config.py` for the full list.

| Setting | Default | Meaning |
|---|---|---|
| `LEXICO_PROVIDER_ORDER` | `stub,kaikki,groq` | Provider fallback chain (dictionary + LLM) |
| `LEXICO_MAX_LLM_CALLS_PER_USER_PER_DAY` | `50` | Per-user daily LLM call cap |
| `LEXICO_MAX_LLM_CALLS_PER_DAY` | `500` | Global daily LLM call cap |
| `LEXICO_DAILY_USD_CAP` | `0.00` | Global daily USD spend cap (paid LLMs off by default) |
| `LEXICO_DATABASE_URL` | unset | Postgres URL (Supabase). Omit → SQLite at `~/.lexico/lexico.db`. |
| `LEXICO_REQUIRE_AUTH` | `false` | Enable `streamlit-authenticator` gate |

---

## Architecture

```
src/lexico/
├── domain/          frozen Pydantic models (WordEntry, Deck, Card, FSRSState, Rating)
├── providers/       DictionaryProvider + LlmProvider Protocols + implementations
├── cache/           memory LRU + SQLite blob two-tier cache
├── data/            Kaikki loader + themed seed decks
├── services/        LookupService, EnrichmentService, UsageGuardrail,
│                    ReviewScheduler, DeckStore, Gamification
├── ui/              Streamlit router, auth, components, views
├── config.py        pydantic-settings
└── utils/           prompts, text normalization
tests/unit/          pytest, stub-backed, no network
```

Layering: **domain → services → UI**. Providers are `Protocol`-based so swapping Kaikki for another dictionary source, or Groq for another LLM, is a one-file change.

---

## Tests

```bash
pytest -m "not slow"   # unit tests, no network, no keys required
pytest -m slow         # integration tests hitting real Groq (needs GROQ_API_KEY)
```

---

## Deployment

Push to GitHub, connect the repo on [share.streamlit.io](https://share.streamlit.io), paste the contents of `.streamlit/secrets.toml.example` into the web Secrets editor with real values. Supabase Postgres on the free tier handles multi-user state; SQLite handles local dev.

---

## License

Dictionary content from Kaikki.org derives from Wiktionary and is licensed **CC-BY-SA 3.0**. Code in this repository is **MIT**.
