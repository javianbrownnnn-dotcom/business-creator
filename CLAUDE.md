# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two small, scheduled Python agents that feed a personal job-search Notion workspace:

- **Agent 1 — Job Discovery** (`job_agent/`): daily. Fetches marketing/entry-level roles from public ATS boards and free job APIs, filters, scores fit 0–100, dedupes, writes rows to the **Job Leads** Notion DB, writes a dated markdown digest to `data/digests/`, emails a daily summary, and sends an ntfy push.
- **Agent 2 — Response Tracker** (`response_agent/`): hourly. Reads Gmail over IMAP (read-only), pre-filters cheaply, classifies/extracts with Claude (`claude-haiku-4-5`), writes rows to the **Application Responses** Notion DB, pushes ntfy, and labels handled mail `JobTracker/Logged`.
- **Cleanup** (`job_agent/cleanup.py`): runs every Friday via CI but self-gates to alternating ISO weeks (`CLEANUP_WEEK_PARITY`), archiving applied/stale Job Leads rows to Notion trash.

There is no web app, no test suite, and no linter configured. Python 3.11 in CI; dependencies are only `requests` and `anthropic` (Agent 1 is stdlib + requests only — keep it that way).

## Commands

```bash
pip install -r requirements.txt

# Secrets come from env vars (see .env.example for the full list)
cp .env.example .env          # fill in values
set -a; source .env; set +a

python -m job_agent.main        # Agent 1 — job discovery
python -m response_agent.main   # Agent 2 — response tracker
python -m job_agent.cleanup     # biweekly cleanup (self-gated by week parity)
```

Always run modules with `python -m` from the repo root — `config.py` and `shared/` are imported as top-level modules.

Both agents degrade gracefully when a secret is missing (e.g. no `NOTION_TOKEN` → skips Notion but still writes the digest; no Adzuna keys → that source is skipped). This makes partial local runs possible without full credentials, and it's a convention to preserve in new code.

## Architecture

### Shared layer
- `config.py` — the single tuning surface for BOTH agents: company slugs, keyword/scam/location filters, scoring weights, ATS/noise domains, schedules' knobs, and shared paths. **Behavioral changes should land here as config, not as hardcoded values in agent code.** Never put secrets here; secrets are env vars only.
- `shared/notion.py` — thin Notion REST client (`requests`, no SDK) plus property builders (`title()`, `rich_text()`, `select()`, …). `adapt_properties()` reconciles intended property names against the live DB schema (exact → case-insensitive → fuzzy/by-type match) so a renamed Notion column never sinks a write — route all page creation through it.
- `shared/notify.py` — ntfy push + Gmail SMTP email-to-self. Notification failures are logged, never raised.

### Agent 1 pipeline (`job_agent/main.py`)
`sources.fetch_all()` → `filters.keep()` → dedupe → `scoring.score()` → Notion → digest → email → ntfy.

- `sources.py` — one fetcher per source (Greenhouse, Lever, Ashby, The Muse, RemoteOK, Adzuna). Each returns a list of normalized job dicts (`title`, `company`, `location`, `remote`, `posted_date`, `source`, `apply_url`, `description`) and is defensive: errors are caught and an empty list returned so one bad source never sinks the run. New sources must emit this same shape and respect `SOURCES_ENABLED` and `REQUEST_DELAY`.
- `filters.py` — include keywords, hard seniority exclusion, SEO-title exclusion, scam/MLM legitimacy gate, recency, location allow-list. Returns `(bool, reason)` so drops are explainable.
- `scoring.py` — transparent additive 0–100 score from `SCORE_WEIGHTS`, plus `classify_function()` / `classify_seniority()` which map onto the exact Notion select options. The "no General Marketing" exclusion is applied in `main.py` after classification, not in `filters.py`.
- `storage.py` — SQLite seen-jobs DB at `data/jobs.db`; `job_id()` is sha256 of company|title|url.

**Dedup is two-layered**: the SQLite DB plus a live query of existing Notion (company, title) keys at the start of each run. The Notion layer fails open (continues on query error). Preserve both layers when modifying the pipeline.

### Agent 2 pipeline (`response_agent/main.py`)
IMAP fetch → `prefilter.is_candidate()` (no LLM — ATS domains + recruiting keywords, minus noise/alert filters) → `classify.classify()` (Claude Haiku, JSON-only output, parsed defensively, returns `None` on hard failure) → Notion dedupe (by Email Link URL, else Company+Role) → Notion write → ntfy → apply `JobTracker/Logged` label.

- The label is applied even for "not a response" verdicts (so it's not re-classified next hour) but NOT when the Notion write fails (so it retries).
- `_RESPONSE_TYPE_MAP` in `main.py` translates the model's enum to the Notion select options — keep it in sync with `_RESPONSE_TYPES` in `classify.py`.

## Hard guardrails

- **Gmail is read-only** except for adding the single `JobTracker/Logged` label. `gmail_client.py` must never send, delete, archive, or modify messages.
- **Both Notion databases already exist** (IDs in `config.py`). The agents only write/archive rows — they never create databases or alter schemas.
- **When unsure whether an email is a real response, lean toward NOT logging** and print a debug line so filters can be tuned.
- `data/jobs.db` and `data/digests/` are **intentionally committed** (not gitignored): the daily CI run commits them back to `main` so dedup survives across ephemeral cloud runs. Do not gitignore them.

## CI / scheduling (`.github/workflows/`)

- `job-agent.yml` — daily, with multiple morning cron attempts because GitHub's scheduled cron is unreliable; dedup plus a one-email-per-day guard (`data/last_email_date.txt`) make extra attempts no-ops. After the run it commits `data/` back to `main` with a rebase-and-retry loop, and never fails the build over the commit-back.
- `response-agent.yml` — hourly, stateless w.r.t. the repo (dedup lives in Notion + the Gmail label).
- `cleanup.yml` — every Friday; the script itself gates to alternating weeks.

All cron times are UTC. Secrets are GitHub Actions repository secrets matching the names in `.env.example`.

## Conventions

- Logging is plain `print()` with a bracketed stage tag: `[run]`, `[prefilter]`, `[classify]`, `[dedup]`, `[notion]`, `[digest]`, `[email]`, `[notify]`. Follow this pattern — the README tells the user to tune filters by watching these lines.
- Failure philosophy: a missing secret, a failed source, a failed push notification, or a failed commit-back must never crash a run. Catch, log with the stage tag, and continue.
- Keyword matching throughout is lowercase-substring against a title+description blob (`_blob()` helpers); seniority exclusion is whole-word against the flattened title.
