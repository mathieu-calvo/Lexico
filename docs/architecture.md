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

**Source of the daily pool content.** Three different sources, one for
each pool type:

- **Word-of-the-day lemmas** are hand-authored Python literals in
  `daily_pool.py`. Small, curated list per language. The home view then
  calls `LookupService.lookup(lemma, language)` to render a full word
  card, so the lemma is static but the definition behind it is fetched
  dynamically from Wiktionary (and cached in SQLite forever after the
  first fetch).
- **Quote-of-the-day** items are hand-authored Python literals in
  `daily_pool.py`. Short aphorisms by well-known authors, pure
  in-memory tuples.
- **Expression-of-the-day** items are **harvested from Wiktionary** by
  `scripts/fetch_expressions.py` (see below) and written to a shipped
  JSON snapshot at `src/lexico/data/expressions_data.json`. The snapshot
  is loaded once at import time by `_load_expression_pools` and exposed
  as `EXPRESSION_POOLS`. If the snapshot file is missing (e.g. the script
  has never been run), a small hand-authored fallback in
  `_FALLBACK_EXPRESSIONS` keeps the home view working with a handful of
  idioms per language.

None of the three pools depends on a network call at runtime — the JSON
snapshot is a build-time artifact that ships in the repo, and the lookup
cache makes the WotD card-render a one-time network hit per install.

**When the pools roll over.** The `_day_index` helper computes
`(today.toordinal() + language_offset + salt) % pool_size` where `today`
defaults to `datetime.now(timezone.utc).date()`. Consequences:

- All three items flip at **00:00 UTC**, globally, for every user.
- There is no per-user state — the function is pure, so the same date
  produces the same trio on every reload.
- Three desynchronizers keep the items from lockstepping: independent
  salts per pool type (`0` / `101` / `211`), per-language offsets
  (`FR=0, EN=7, IT=13, ES=23, PT=31`), and different pool sizes (~20
  words, 10 expressions, 7 quotes per language) so each cycles on its
  own period.

To refresh or extend a pool:

- **Words and quotes** — edit the tuples in `daily_pool.py` directly and
  redeploy. They're pure code, no tooling needed.
- **Expressions** — re-run `python scripts/fetch_expressions.py` (see
  below) to regenerate `expressions_data.json`, then commit the new
  snapshot and redeploy. Pass `--lang <code>` to refresh a single
  language, or `--target <n>` to change the cap.

## scripts/fetch_expressions.py

A one-shot build-time script that populates the expression pools. Not
called at runtime; run it manually whenever you want to refresh the
snapshot.

The script:

1. Queries each per-language Wiktionary's MediaWiki Action API for
   idiom/locution categories. We pick per-language category names
   carefully — each edition uses its own scheme (French has
   `Catégorie:Locutions verbales en français` etc., Italian splits by
   phrase type under `Categoria:Locuzioni …`, Spanish uses
   `Categoría:ES:Locuciones …`, Portuguese uses
   `Categoria:Locução … (Português)`). "Nominal" / "substantiva"
   locution categories are deliberately skipped because they're
   dominated by compound common nouns (species names, chemical
   compounds) rather than real idioms.
2. Paginates each category, filters out namespaced pages (`Annexe:`,
   `Appendix:`), single-word entries, and numeric noise.
3. Feeds every candidate title through the existing
   `WiktionaryNativeProvider`, which already knows how to parse each
   per-language edition's HTML into a `WordEntry` with native-language
   glosses. The first sense's gloss becomes the expression's meaning.
4. Writes `(text, meaning)` pairs to `src/lexico/data/expressions_data.json`
   with a small `_meta` block naming Wiktionary + CC-BY-SA 3.0 as the
   source.

Roughly 1 lookup/sec end-to-end (Wiktionary HTTP + parse + a polite
0.15s throttle), so a full 5-language × 400-per-language run takes
~30–40 minutes. Re-running is idempotent — the existing snapshot is
loaded and only the requested languages are overwritten.

The daily-pool module loads the snapshot once at import time and falls
back to a tiny hand-authored list if the file is missing, so the app
is never broken by a failed or skipped fetch run.

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
