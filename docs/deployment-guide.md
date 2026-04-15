# Deployment guide — Streamlit Community Cloud

Lexico is designed to run for free on Streamlit Community Cloud with zero
recurring cost. This guide walks through a clean deployment from an empty
GitHub repo to a live public URL.

## Prerequisites

- A GitHub account with the Lexico repo pushed
- A free [Streamlit Community Cloud](https://share.streamlit.io) account
  (sign in with GitHub)
- *(Optional)* a free [Groq](https://console.groq.com) API key to enable
  the tutor + daily challenge features — see `docs/groq-api-key.md`

## 1. Push the repo

Push `main` to GitHub. Make sure the following files are committed:

- `requirements.txt` — Python dependencies
- `src/lexico/ui/app.py` — the Streamlit entry point
- `.streamlit/config.toml` (optional theme overrides)
- `.streamlit/secrets.toml.example` — template for the secrets you'll
  paste into the Cloud UI. **Do not commit a real `secrets.toml`.**

## 2. Create the Streamlit Cloud app

1. Go to <https://share.streamlit.io> and click **New app**.
2. Pick your repo and branch (usually `main`).
3. Set **Main file path** to `src/lexico/ui/app.py`.
4. Pick a subdomain (e.g. `lexico-yourname`).
5. Click **Deploy**.

First boot takes ~1 minute as Streamlit installs `requirements.txt`. If the
build fails, open the logs panel — missing dependencies and syntax errors
show up there.

## 3. Add secrets

From the app's **Settings → Secrets** page, paste the contents of
`.streamlit/secrets.toml.example` and replace the placeholders:

```toml
# Optional — unlocks real tutor / challenge / cloze responses.
# Without this, those features show a "no real LLM configured" banner and
# the stub returns deterministic placeholder output.
GROQ_API_KEY = "gsk_..."

# Optional — Supabase Postgres for multi-user state.
# Without this, Streamlit Cloud uses ephemeral SQLite at ~/.lexico/lexico.db,
# which resets on every cold start.
[database]
url = "postgresql://user:pass@host:5432/db"

# Optional — enables the login gate. If omitted, the app runs in
# single-user mode ("local") with no authentication.
[credentials]
usernames = { alice = { name = "Alice", password = "hashed_bcrypt_here" } }
cookie_name = "lexico_auth"
cookie_key = "generate_a_random_string"
cookie_expiry_days = 30
```

Save. Streamlit automatically reboots the app with the new secrets.

## 4. (Optional) Hook up Supabase for persistent storage

Streamlit Cloud's file system is ephemeral, so the default SQLite database
under `~/.lexico/lexico.db` vanishes on cold starts. For a serious deployment:

1. Create a free [Supabase](https://supabase.com) project.
2. In the SQL editor, run the schema block from `docs/architecture.md`
   (or simply rely on the app's `CREATE TABLE IF NOT EXISTS` bootstrap).
3. Copy the Postgres connection string from **Settings → Database**.
4. Paste it into `[database] url` in the Cloud Secrets editor.

On the next reboot the app will use Postgres transparently — no code change.

## 5. Verify the deployment

Open the app URL and walk through the smoke test:

1. **Home** — streak chip, saved-count, and the word / expression / quote
   of the day render for all five languages.
2. **Lookup** — search a common word in French, confirm the card renders
   with definition, IPA, examples, and translations.
3. **Decks** — create a new deck, add the word you looked up, delete a
   card to confirm the trash icon works.
4. **Review** — answer a card in Reveal mode, check that rating buttons
   only appear after "Reveal" is clicked, then rate to auto-advance.
5. **Daily challenge** — with no `GROQ_API_KEY`, confirm the banner shows.
   With a key, confirm grading returns real feedback.
6. **Tutor** — same banner behavior as the challenge page.
7. **Stats** — per-language counts match hand-verified totals; Recent
   reviews shows lemma + meaning + rating label + date.
8. **Mobile** — resize the browser to ~400px wide. Columns should stack
   vertically with no horizontal scroll.

## 6. Updating the app

Push to `main`. Streamlit Cloud auto-redeploys on every commit. For secret
changes, use the **Settings → Secrets** editor — you don't need to commit
or redeploy.

## Troubleshooting

- **"No module named lexico"** — confirm the **Main file path** is
  `src/lexico/ui/app.py` exactly; `app.py` prepends `src/` to `sys.path`
  at startup but only if it runs from that location.
- **LLM features return stubs even with a key set** — check that the
  secret name matches `GROQ_API_KEY` exactly (uppercase). The config
  loader in `config.py` reads it verbatim from `st.secrets`.
- **Database seems to lose data** — you're on ephemeral SQLite. Hook up
  Supabase (step 4) to persist across reboots.
- **Daily challenge shows "budget reached"** — bump
  `LEXICO_MAX_LLM_CALLS_PER_USER_PER_DAY` in Secrets if you're testing
  heavily; defaults to 50.
