# Job-Search Automation — two agents, one repo

Two small Python agents that run on a schedule and feed your Notion workspace:

| Agent | What it does | Schedule | Notion DB |
|---|---|---|---|
| **Agent 1 — Job Discovery** (`job_agent/`) | Pulls fresh marketing/intern roles from startup ATS boards + free job APIs, filters to your profile, scores fit 0–100, dedupes, writes ranked rows to your **Job Leads** DB, writes a dated markdown digest, pushes an ntfy notification. | Daily | `1c4c54e2…0d42` |
| **Agent 2 — Response Tracker** (`response_agent/`) | Reads Gmail (read-only), pre-filters to real recruiter replies, classifies/extracts with **Claude Haiku 4.5**, writes rows to your **Application Responses** DB, pushes ntfy, labels handled mail `JobTracker/Logged`. | Hourly | `ab97f9d5…6ce4` |

They share `config.py`, `shared/` (Notion client + notifier), and the GitHub
Actions setup.

> Both Notion databases **already exist** — the agents only *write rows* to
> them. They never create databases.

---

## Repository layout

```
config.py                  # ← tune everything here (no secrets)
shared/      notion.py      # Notion REST client + property builders
             notify.py      # ntfy push (+ Telegram / email stubs)
job_agent/   main.py        # runner: fetch→filter→score→store→Notion→digest→notify
             sources.py     # Greenhouse, Lever, Ashby, The Muse, RemoteOK, Adzuna
             filters.py     # include/exclude, seniority, recency, location, dedupe
             scoring.py     # 0–100 fit score + Function/Seniority classifiers
             storage.py     # SQLite seen-jobs DB
response_agent/ main.py     # runner: mail→prefilter→Haiku→dedupe→Notion→notify→label
             gmail_client.py # IMAP read-only + JobTracker/Logged label
             prefilter.py   # cheap ATS-domain + keyword gate, drops job alerts
             classify.py     # claude-haiku-4-5 JSON extraction
data/        jobs.db         # seen-jobs DB (committed by CI for cross-run dedup)
             digests/        # dated markdown digests (backup/log)
.github/workflows/          # job-agent.yml (daily) + response-agent.yml (hourly)
```

---

## 1. Quick start (run once, locally)

```bash
git clone <this repo> && cd business-creator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in your values
set -a; source .env; set +a # export them into the shell

# Agent 1 — job discovery
python -m job_agent.main

# Agent 2 — response tracker
python -m response_agent.main
```

Each agent degrades gracefully: if a secret is missing it skips that step and
logs why (e.g. no `NOTION_TOKEN` → still writes the digest; no Adzuna key →
that source is skipped).

---

## 2. Credentials (where each one comes from)

| Secret | Used by | How to get it |
|---|---|---|
| `NOTION_TOKEN` | both | https://www.notion.so/my-integrations → New integration (internal) → copy the **Internal Integration Secret**. Then open **each** database → `•••` → **Connections** → add your integration. |
| `NTFY_TOPIC` | both | Pick a long, unguessable string (e.g. `mktgjobs-x7f3q9`). Install the **ntfy** app, subscribe to that topic. No account needed. |
| `ANTHROPIC_API_KEY` | Agent 2 | https://console.anthropic.com → API Keys. |
| `GMAIL_ADDRESS` | Agent 2 | Your Gmail address. |
| `GMAIL_APP_PASSWORD` | Agent 2 | Enable 2FA, then https://myaccount.google.com/apppasswords → create an app password (16 chars). **Not** your normal password. |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Agent 1 (optional) | https://developer.adzuna.com — free dev tier. Omit to skip Adzuna. |

### Notion integration — important
The integration must be **explicitly connected to each database** (or a parent
page you share with it), or every write returns `404 / object_not_found`.

---

## 3. Tuning (`config.py`)

Everything you'll want to change lives in `config.py`:

- **Add a company** → append its slug to `GREENHOUSE_SLUGS`, `LEVER_SLUGS`, or
  `ASHBY_SLUGS`. Verify the slug works by opening one of:
  - `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`
  - `https://api.lever.co/v0/postings/<slug>?mode=json`
  - `https://api.ashbyhq.com/posting-api/job-board/<slug>`
- **Enable / disable a source** → flip a flag in `SOURCES_ENABLED`.
- **Keywords** → `INCLUDE_KEYWORDS`, `HARD_EXCLUDE_TOKENS`, `SEO_TITLE_EXCLUDE`,
  `DOWNRANK_KEYWORDS`.
- **Recency window** → `POSTED_WITHIN_DAYS` (default 7).
- **Locations** → `LOCATION_ALLOW_TOKENS` (currently remote-US + ~45-min radius
  of Miami / Nashville / Orlando / Dallas, plus NYC, DC, all of Colorado &
  California). Remote roles are always kept and flagged.
- **Scoring weights** → `SCORE_WEIGHTS` (+ the keyword lists it references).
  Email / lifecycle / retention / CRM / Klaviyo is weighted highest.
- **Agent 2 filters** → `ATS_DOMAINS`, `RECRUITING_KEYWORDS`, `NOISE_KEYWORDS`,
  `NOISE_SENDER_DOMAINS`. Watch the `[prefilter] DROP/KEEP` and `[classify]`
  log lines to see what got captured and adjust.

---

## 4. Daily / hourly scheduling

### Option A — GitHub Actions (recommended, no machine to keep on)

1. Push this repo to GitHub.
2. **Settings → Secrets and variables → Actions** → add the secrets from §2.
3. Done. Workflows are already in `.github/workflows/`:
   - `job-agent.yml` — daily at 13:00 UTC; commits the digest + dedup DB back.
   - `response-agent.yml` — hourly.
4. Trigger a test run anytime: **Actions tab → pick the workflow → Run
   workflow** (uses `workflow_dispatch`).

Change the times by editing the `cron:` lines. Cron is **UTC**.

> The job agent commits `data/jobs.db` back so de-dup survives across cloud
> runs — that's why `jobs.db` is intentionally **not** gitignored.

### Option B — local cron (macOS / Linux)

```bash
crontab -e
```
Add (adjust paths; cron needs the venv python and your env file):
```cron
# Agent 1 — daily at 9:00am local
0 9 * * *  cd /path/to/business-creator && set -a && . .env && set +a && .venv/bin/python -m job_agent.main >> data/job-agent.log 2>&1
# Agent 2 — hourly
0 * * * *  cd /path/to/business-creator && set -a && . .env && set +a && .venv/bin/python -m response_agent.main >> data/response-agent.log 2>&1
```

### Option B (Windows — Task Scheduler)
Create two Basic Tasks pointing at
`...\.venv\Scripts\python.exe -m job_agent.main` (Daily) and
`...\-m response_agent.main` (Hourly), "Start in" = the repo folder, with the
env vars set at the user/system level.

---

## 5. Testing Agent 2 on a single email before going live

1. Set your env vars locally (`source .env`).
2. Temporarily set `GMAIL_LOOKBACK_DAYS = 1` in `config.py` and make sure you
   have one recent recruiter email in your inbox.
3. Run `python -m response_agent.main` and watch the logs:
   - `[prefilter] KEEP/DROP …` shows the cheap gate's decisions.
   - `[classify] …` shows Haiku's verdict.
   - Confirm the row appears in the Notion DB and the email gets the
     `JobTracker/Logged` label.
4. The agent is **read-only** on your mailbox except adding that one label — it
   never sends, deletes, archives, or modifies messages. When it's unsure
   whether something is a real response, it leans toward **not** logging and
   prints a debug line so you can tune the filters.

---

## Notion field mappings (reference)

**Job Leads** (`1c4c54e2…0d42`): `Job Title` (title), `Company` (text),
`Location` (text), `Remote` (checkbox), `Fit Score` (number), `Function`
(select), `Seniority` (select), `Source` (text), `Posted Date` (date), `Apply`
(url), `Status` (select → `New`).

**Application Responses** (`ab97f9d5…6ce4`): `Contact` (title), `Company`
(text), `Role` (text), `Email` (email), `Response Type` (select), `Status`
(select → `New`), `Date Received` (date), `Email Link` (url), `Source` (text),
`Next Step` (text), `Notes` (text).

---

## Phase 2 (not built yet)

Auto-drafting a 3-sentence tailored application opener (email-retention /
lifecycle / Klaviyo / DTC background) for the top-N highest-fit roles each day,
ready to paste — **never auto-submitted**. Say the word and I'll add it as a
post-step in `job_agent/main.py`.
