# Deployment Guide — Streamlit Community Cloud + Supabase

This guide walks through deploying Lexico as a 24/7 hosted app with user
authentication and per-user persistence (saved words, expressions, liked
quotes, review history).

**Stack:**
- **Hosting:** Streamlit Community Cloud (free)
- **Database:** Supabase PostgreSQL (free tier, 500 MB)
- **Auth:** `streamlit-authenticator` (bcrypt whitelist, one entry per user)
- **LLM (optional):** Groq free tier for tutor / challenge / cloze. Without a
  key, the app still works as a full offline dictionary + SRS.

---

## Prerequisites

- A GitHub account with the Lexico repo pushed
- Python 3.11+ installed locally (to generate password hashes)
- `streamlit-authenticator` installed locally:
  ```bash
  pip install streamlit-authenticator
  ```

---

## Step 1: Commit and push to GitHub

```bash
cd "C:/Users/mathi/Documents/Github repos/Lexico"
git add -A
git commit -m "deploy"
git push origin main
```

---

## Step 2: Create a Supabase project

1. Go to <https://supabase.com> and click **Start your project** (sign up with
   GitHub if needed).
2. Click **New project** and fill in:
   - **Project name:** `lexico`
   - **Database password:** pick a strong password and **save it** — you'll
     need it in Step 4.
   - **Region:** closest to your users (e.g. `West EU (London)`).
3. Click **Create new project** and wait ~2 minutes for it to spin up.

---

## Step 3: Create the schema in Supabase

1. Open your project → **SQL Editor** (left sidebar) → **New query**.
2. Paste the contents of
   [`scripts/supabase_schema.sql`](../scripts/supabase_schema.sql) and click
   **Run**. The script is idempotent — safe to re-run on schema changes.

You should see `Success. No rows returned.` The SQL creates five tables
(`decks`, `cards`, `review_logs`, `llm_usage_log`, `liked_quotes`) plus four
indexes. Every row is tagged with `user_id`, so users never see each other's
data.

> **Note:** The app also runs every `CREATE TABLE IF NOT EXISTS` statement on
> startup as a safety net. Running the script up front just surfaces
> connectivity / permission issues earlier.

---

## Step 4: Get your Supabase connection string

> **CRITICAL:** Use the **Session pooler** connection string, NOT the Direct
> connection. Supabase's direct connection is IPv6-only and Streamlit Cloud
> doesn't support outbound IPv6 — you'll get `psycopg2.OperationalError` if
> you use it.

1. Supabase → **Project Settings** (gear icon) → **Database**.
2. Scroll to **Connection string** and click the **Session pooler** tab.
3. You'll see something like:
   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
   ```
   (hostname contains `pooler.supabase.com`, username is `postgres.<project-ref>`).
4. Replace `[YOUR-PASSWORD]` with the database password from Step 2.
5. **Copy the full string** — you'll paste it into secrets in Step 6.

> **Why session pooler, not transaction pooler?** Transaction pooler (port
> 6543) doesn't support prepared statements, which `psycopg2` uses. Session
> pooler (port 5432) is a drop-in replacement for the direct connection and
> works perfectly.

---

## Step 5: Generate password hashes for your users

For each user you want to allow in, generate a bcrypt hash of their
password. Run this in your terminal, once per user:

```bash
python -c "import streamlit_authenticator as stauth; print(stauth.Hasher.hash('the_password_here'))"
```

Replace `the_password_here` with the actual password. Output:

```
$2b$12$xK7Gq3Z...long hash...
```

Copy the full hash (starting with `$2b$12$...`). The hash — not the plaintext
password — is what goes into the Streamlit secrets.

> **Note:** This uses the `streamlit-authenticator` v0.4+ API. Older versions
> used `stauth.Hasher([password]).generate()` which no longer works.

Also generate a random cookie key (one per deployment, not per user):

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

Save this hex string — you'll paste it as `[cookie] key` below.

---

## Step 6: Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> → **Sign in** with GitHub.
2. Click **New app** and fill in:
   - **Repository:** `mathieu-calvo/Lexico`
   - **Branch:** `main`
   - **Main file path:** `src/lexico/ui/app.py`
3. Click **Advanced settings**.
4. Set **Python version** to `3.11`.
5. In the **Secrets** text box, paste this template and fill in your values:

```toml
# ---- LLM providers (optional) ----
GROQ_API_KEY = "gsk_..."          # optional — enables tutor / challenge / cloze / context
# ANTHROPIC_API_KEY = "sk-ant-..."  # optional — only needed if you opt in to Claude

# ---- Supabase Postgres ----
[database]
url = "postgresql://postgres.abcdefgh:YOUR_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"

# ---- Authentication ----
# One [credentials.usernames.<login>] block per allowed user.
# The <login> key IS the username they type at the login form.
[credentials.usernames.mathieu]
email = "mathieu@example.com"
name = "Mathieu"
password = "$2b$12$PASTE_THE_HASH_FROM_STEP_5_HERE"

[credentials.usernames.anotherperson]
email = "friend@example.com"
name = "Friend"
password = "$2b$12$THEIR_HASH_FROM_STEP_5_HERE"

[cookie]
name = "lexico_auth"
key = "PASTE_THE_HEX_FROM_STEP_5_HERE"
expiry_days = 30
```

**Key details:**
- Each `[credentials.usernames.xxx]` block = one allowed user. `xxx` is their
  login username (lower-case, no spaces).
- Password field holds the **bcrypt hash**, not the plaintext password.
- Presence of `[credentials]` auto-enables the login screen. Remove the whole
  block to run in single-user mode (`local` user, no login).
- Presence of `[database] url` switches storage from ephemeral SQLite to
  Postgres — no code changes needed.

6. Click **Deploy!**

---

## Step 7: Verify it works

1. Wait 2–3 minutes for the first build. Watch the logs in the Streamlit
   Cloud dashboard if you want to see progress.
2. Once deployed, you'll get a URL like
   `https://lexico-mathieu-calvo.streamlit.app`.
3. Open it — you should see a **login screen**.
4. Log in with your username (e.g. `mathieu`) and the **plaintext password**
   you hashed in Step 5.
5. Walk through the smoke test:
   - **Home** — word/expression/quote of the day renders for all 5 languages.
     Star a quote; it should persist after refresh.
   - **Lookup** — search `éphémère` in French, save it to a new deck.
   - **Decks** — your new deck is there with the card.
   - **Review** — the card is due; try all 4 modes (Reveal / Cloze / Recall /
     Match). Rate it; the next one auto-advances.
   - **Daily challenge** — with `GROQ_API_KEY`, you should get real grading.
     Without, you'll see the "no real LLM configured" banner.
   - **Tutor** / **Quotes** — similar banner behavior; context lookups on
     starred quotes should return real explanations when Groq is configured.
   - **Stats** — shows real counts for your account.
6. **User isolation check:** log out → log in as the other user → they
   should see an empty deck list. Their cards never mix with yours.

---

## Managing users

### Adding a new user

1. Generate their bcrypt hash (Step 5).
2. Streamlit Cloud dashboard → your app → **Settings** → **Secrets**.
3. Add a new block:
   ```toml
   [credentials.usernames.newuser]
   email = "newuser@example.com"
   name = "New User"
   password = "$2b$12$THEIR_HASH_HERE"
   ```
4. Save — the app restarts automatically.

### Removing a user

Delete their `[credentials.usernames.xxx]` block from secrets and save. Their
existing data remains in Supabase under that `user_id`; to wipe it:

```sql
DELETE FROM liked_quotes  WHERE user_id = 'newuser';
DELETE FROM review_logs   WHERE user_id = 'newuser';
DELETE FROM cards         WHERE deck_id IN (SELECT id FROM decks WHERE user_id = 'newuser');
DELETE FROM decks         WHERE user_id = 'newuser';
```

### Rotating a password

Generate a new hash (Step 5) and replace the `password = "..."` field for
that user. Save. Their session cookie stays valid until `expiry_days` passes
— rotate `[cookie] key` too if you want to invalidate all active sessions.

---

## Updating the app

Any push to `main` on GitHub auto-deploys:

```bash
git add -A
git commit -m "your change"
git push origin main
```

The app rebuilds in ~2 minutes. Secret changes don't need a push — edit them
in the **Settings → Secrets** panel and they take effect immediately.

---

## Local development

Running the app locally without a `database_url` or `[credentials]` block
uses SQLite at `~/.lexico/lexico.db` and skips authentication (user id is
hard-coded to `local`):

```bash
streamlit run src/lexico/ui/app.py
```

To test the auth + Postgres flow locally, create `.streamlit/secrets.toml`
(already gitignored) with the same structure as the cloud secrets.

---

## Architecture notes

- **Storage switch:** `services/__init__.py :: get_deck_store()` returns a
  `PgDeckStore` if `database_url` is set, otherwise the SQLite `DeckStore`.
  Both classes expose the same public API, so view code is backend-agnostic.
- **Auth switch:** `config.py :: _load_settings()` flips `require_auth=True`
  whenever `[credentials]` appears in secrets. `ui/app.py` then gates the
  rest of the app behind the login form.
- **User isolation:** every write and query is scoped by `user_id` — the
  authenticated username from the login form. Users physically cannot see
  another user's decks, cards, reviews, or liked quotes.
- **LLM budget:** hard caps enforced by `UsageGuardrail` (per-user per day,
  global per day, and USD cap). Tripped caps bubble up as friendly
  "come back tomorrow" messages without breaking the rest of the app.
- **Dictionary cache:** lookups are memoized in a local SQLite cache. On
  Streamlit Cloud this is ephemeral (rebuilds from Wiktionary on wake-up),
  which is fine — it's a cache, not user state.
- **Sleep behavior:** Streamlit Cloud free tier sleeps after ~15 min of
  inactivity and wakes in ~30 s. The Postgres session persists so no data
  is lost; the dictionary cache repopulates on first lookup.

---

## Troubleshooting

- **`psycopg2.OperationalError: could not translate host name`** — you're
  using the direct connection string (IPv6). Switch to the **Session
  pooler** URL (Step 4).
- **`Failed to connect to PostgreSQL: ... password authentication failed`**
  — the password in the URL is wrong, or has a special character that needs
  URL-encoding (e.g. `@` → `%40`, `#` → `%23`).
- **Login form says "Username or password incorrect"** — the bcrypt hash
  doesn't match the plaintext you typed. Re-run Step 5 with the exact
  password you want to use and paste the full new hash.
- **LLM features return stubs even with a key set** — check that the secret
  name is `GROQ_API_KEY` (uppercase, exact). Also confirm the provider order
  in config (`LEXICO_PROVIDER_ORDER`) puts `groq` before `stub`.
- **"Daily LLM budget reached"** — bump
  `LEXICO_MAX_LLM_CALLS_PER_USER_PER_DAY` in Secrets when testing; default
  is 50 calls/user/day.
- **Data seems to disappear between sessions** — you're on ephemeral SQLite
  (no `[database] url` in secrets). Complete Steps 2–4 to persist.
