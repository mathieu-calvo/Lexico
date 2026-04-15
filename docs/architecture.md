# Lexico architecture

A single-process Streamlit app backed by SQLite (or Postgres in production)
and a chain of pluggable dictionary + LLM providers. Everything fits in one
Python package, with strict layering: **domain → services → UI**.

```
src/lexico/
├── domain/          Pydantic models (WordEntry, Deck, Card, FSRSState, Rating)
├── providers/       DictionaryProvider + LlmProvider Protocols + implementations
├── cache/           memory LRU + SQLite blob two-tier cache
├── data/            curated data: seed decks, daily pools (WotD / expression / quote)
├── services/        LookupService, EnrichmentService, UsageGuardrail,
│                    ReviewScheduler, DeckStore, Gamification
├── ui/              Streamlit router, auth, components, views
└── utils/           prompts, text normalization
```

## Layers

### domain/
Frozen Pydantic models with no I/O. `WordEntry` is the dictionary unit —
lemma, senses, examples, translations, IPA, etymology, CEFR. `Deck` and
`Card` are the personal-state layer. `FSRSState` holds the scheduler's
stability/difficulty for a single card. Nothing here talks to the database,
an API, or Streamlit — these models serialize cleanly to JSON and are the
one contract every layer agrees on.

### providers/
Two protocols and a set of implementations:

- **`DictionaryProvider`** — `lookup(lemma, language) -> WordEntry`. Concrete
  implementations: `StubDictionaryProvider` (hand-curated demo entries),
  `WiktionaryNativeProvider` (live MediaWiki API per language).
- **`LlmProvider`** — `complete(system, user, …) -> LlmResponse`. Concrete
  implementations: `StubLlmProvider` (deterministic canned output),
  `GroqProvider` (free-tier Llama 3.3 70B), `ClaudeProvider` (opt-in, paid).

Providers are composed into a chain — first available wins. `stub` is first
in the chain so demo words always feel polished; live providers fill in the
long tail.

### cache/
Two-tier cache in front of the dictionary chain: an in-process LRU backed
by a SQLite blob store. Dictionary content has no TTL because lemma
definitions don't change — every word is fetched from the network exactly
once per install.

### data/
Hand-authored static content that isn't code and isn't user state:

- `seed_decks` — curated topic decks (Café French, Italian cooking, …) that
  clone into a user's account on one click.
- `daily_pool` — word-of-the-day, expression-of-the-day, and quote-of-the-day
  pools per language. `home.py` indexes into these deterministically by date.

### services/
The orchestration layer. No Streamlit imports; each service is independently
testable.

- **`LookupService`** — wraps the dictionary provider chain behind the
  two-tier cache. Normalizes lemmas (underscores → spaces, whitespace
  collapse, case variants).
- **`EnrichmentService`** — runs LLM features (cloze, multiple choice,
  challenge grading, tutor chat) through the provider chain + usage
  guardrail. `is_real_llm_available()` lets the UI show a "no real LLM
  configured" banner when the only available provider is the stub.
- **`UsageGuardrail`** — enforces per-user daily, global daily, and USD
  caps against `llm_usage_log`. Raises `BudgetExceeded` so the UI can show
  a friendly "come back tomorrow" message without crashing.
- **`ReviewScheduler`** — thin wrapper over the FSRS algorithm. Takes a
  card's current state + a rating and returns the new state + a `ReviewLog`.
- **`DeckStore`** — SQLite-backed CRUD for decks, cards, review logs, and
  LLM usage. Everything else in the app reads state through here.
- **`Gamification`** — streak computation, word-of-the-day rotation seed
  (XP is legacy; the current UI no longer surfaces it).

### ui/
Streamlit views and components. `app.py` is the router: sets page config,
injects a mobile-responsive CSS shim, handles the optional auth gate, and
dispatches to one of seven views (`home`, `lookup`, `decks`, `review`,
`challenge`, `tutor`, `stats`). Views pull state via the `services/` factory
helpers in `services/__init__.py`, which return `lru_cache`-memoized
singletons so Streamlit's script reruns don't re-open the database.

## Data flow: saving a word

1. **User types a word** in `lookup.py`.
2. View calls `LookupService.lookup(lemma, language)`.
3. LookupService checks the memory cache, then SQLite cache, then falls
   through the provider chain. First hit wins; result is cached indefinitely.
4. View renders the `WordEntry` via `word_card.render_word_card`.
5. User picks a deck and clicks "Add card".
6. View wraps the entry in a `Card.new(entry, deck_id)` (fresh FSRS state)
   and calls `DeckStore.add_card(card)`.

## Data flow: reviewing a card

1. `review.py` pulls the single next due card via
   `DeckStore.get_due_cards(user_id, limit=1)`.
2. The view renders one of four modes (Reveal / Cloze / Recall / Match)
   in the `question` phase. Rating buttons are hidden.
3. User reveals / checks / types. The view moves the card to the
   `answered` phase via session state and reruns.
4. Rating buttons appear. On click, the view calls
   `ReviewScheduler.schedule(card.fsrs_state, rating)`, writes the new
   state via `DeckStore.update_card_state`, logs the review via
   `DeckStore.log_review`, and reruns — which auto-advances to the next
   due card with no extra click.

## Cost model

Every LLM call is gated by `UsageGuardrail.allow(user_id)`. The USD cap
ships at **$0.00**, so paid providers like Claude literally cannot spend
money unless the operator both sets an API key *and* raises the cap. The
default provider chain (`stub,wiktionary,groq`) is 100% free-tier.

See `docs/deployment-guide.md` for Streamlit Cloud deployment steps and
`docs/groq-api-key.md` for enabling the LLM features.
