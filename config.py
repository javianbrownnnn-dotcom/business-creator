"""
Shared, editable configuration for BOTH agents.

Tune everything here without touching core code:
  - Agent 1 (job discovery): company slugs, sources, keywords, scoring, location.
  - Agent 2 (response tracker): ATS domains, recruiting/noise keywords, model.

Secrets are NEVER stored here — they come from environment variables
(see .env.example). This file holds only non-secret knobs.
"""

# =============================================================================
# AGENT 1 — DAILY MARKETING-JOB DISCOVERY
# =============================================================================

# --- Notion target (database already exists; do NOT create a new one) --------
JOB_NOTION_DATABASE_ID = "1c4c54e264e44b57ad86f89a20fd0d42"

# --- Company slugs per ATS ----------------------------------------------------
# Add/remove freely. Each slug is the {company_slug} in the public board URL.
# Verify a slug by opening the endpoint in a browser (see README).
# All of these are real, well-known companies that post on these PUBLIC ATS
# boards — so every lead from them is inherently legitimate (no scam risk).
# Unknown/expired slugs simply 404 and are skipped, so it's safe to over-list.
GREENHOUSE_SLUGS = [
    "stripe", "airbnb", "databricks", "gitlab", "figma", "discord",
    "dropbox", "robinhood", "coinbase", "instacart", "doordash", "reddit",
    "asana", "brex", "samsara", "gusto", "sofi", "affirm", "lyft",
    "pinterest", "twitch", "cloudflare", "datadog", "hashicorp", "flexport",
    "webflow", "faire", "airtable", "calendly", "duolingo", "grammarly",
    "wealthsimple", "thumbtack", "cricut", "betterment",
]

LEVER_SLUGS = [
    "plaid",
    "attentive",     # email/SMS marketing platform — strongly on-profile
    "mozilla", "kickstarter", "ro", "fanatics", "lyst",
]

ASHBY_SLUGS = [
    "linear", "vanta", "posthog", "runway",
    "openai", "ramp", "mercury", "clay", "hex", "watershed", "replit",
    "gem", "browserbase", "sierra",
]

# --- Which sources to enable --------------------------------------------------
SOURCES_ENABLED = {
    "greenhouse": True,
    "lever": True,
    "ashby": True,
    "themuse": True,
    "remoteok": False,   # disabled — RemoteOK now charges for API access
    "remotive": True,    # free, no key — remote jobs, marketing category
    "jobicy": True,      # free, no key — remote jobs, industry=marketing
    "weworkremotely": True,  # free RSS, no key — remote marketing feeds
    "adzuna": True,      # keyed (free dev tier); auto-skips if no ADZUNA_APP_* set
    "jsearch": True,     # keyed (RapidAPI free tier); auto-skips if no RAPIDAPI_KEY
}

# --- JSearch (RapidAPI) -------------------------------------------------------
# Taps Google for Jobs (LinkedIn / Indeed / Glassdoor / ZipRecruiter). Needs a
# RapidAPI key in env var RAPIDAPI_KEY; skips gracefully if unset. Each query is
# one API request, so keep the list tight to stay inside the free monthly quota.
JSEARCH_QUERIES = [
    "lifecycle marketing",
    "email marketing coordinator",
    "growth marketing associate",
    "product marketing associate",
]
JSEARCH_DATE_POSTED = "week"   # all | today | 3days | week | month

# --- Recency ------------------------------------------------------------------
POSTED_WITHIN_DAYS = 7   # only keep roles first posted within this many days

# --- Keyword filters ----------------------------------------------------------
# A role must match at least one INCLUDE keyword (in title or description)
# and must NOT match any HARD_EXCLUDE keyword.
INCLUDE_KEYWORDS = [
    "marketing",
    "product marketing", "pmm",
    "email marketing", "email",
    "lifecycle", "retention", "crm", "klaviyo",
    "content marketing", "content",
    "copywriting", "copywriter", "copy",
    "brand", "growth",
    "communications", "social media",
    "marketing associate", "marketing coordinator", "marketing intern",
]

# Seniority words that disqualify a role outright. Matched as WHOLE WORDS
# against the title (punctuation flattened first), so "VP," / "Sr." / "Manager"
# are all caught regardless of surrounding punctuation. "vice president" is
# handled separately as a phrase in filters.py.
HARD_EXCLUDE_TOKENS = {
    "senior", "sr", "staff", "principal", "lead", "manager", "mgr",
    "director", "vp", "chief", "president", "supervisor", "head",
}

# Junior qualifiers in a title. When one is present, the word "manager" is NOT
# treated as senior — e.g. "Associate Product Marketing Manager" (a real new-grad
# / APMM title) passes, while a bare "...Manager" is still excluded. Other senior
# tokens (senior, director, vp, head, lead, ...) still exclude regardless.
JUNIOR_TITLE_TOKENS = {
    "associate", "coordinator", "assistant", "junior", "jr",
    "intern", "apprentice", "fellow", "trainee",
}

# SEO-only roles are excluded per the profile. A role is dropped only if it is
# *primarily* SEO (SEO in the title) — not merely mentions SEO in passing.
SEO_TITLE_EXCLUDE = ["seo"]

# Down-rank (do NOT exclude) video-/design-heavy content roles.
DOWNRANK_KEYWORDS = [
    "video", "videographer", "motion", "graphic design", "designer",
    "art director", "illustrat", "photograph",
]

# Seniority tokens we KEEP (entry-ish). Roman numerals I/II are fine.
SENIORITY_ALLOW_TOKENS = [
    "intern", "internship", "entry", "junior", "jr", "associate",
    "coordinator", " i", " ii", " 1", " 2",
]

# --- Function exclusion -------------------------------------------------------
# Drop roles classified into these Notion "Function" buckets. Per your request:
# no generic "General Marketing" roles — keep Product Marketing, Email/Lifecycle,
# Content/Copywriting, Paid Ads, and Other.
EXCLUDED_FUNCTIONS = {"General Marketing"}

# --- Experience-requirement gate (the biggest "no-chance" fix) ----------------
# Many listings labeled "Associate/Specialist" actually demand 3-5 years. Drop a
# role when its description requires at least this many years. (Ranges like
# "1-2 years" use the LOWER bound, so "0-2"/"1-2" pass but "3-5"/"5+" are cut.)
EXPERIENCE_MAX_YEARS = 3

# Phrases that confirm a role is realistically attainable at intern / 0-2yr level.
# Their presence boosts a role's score (see scoring.py).
ENTRY_SIGNALS = [
    "entry level", "entry-level", "early career", "early-career",
    "new grad", "new graduate", "recent graduate", "recent grad",
    "0-1 year", "0-2 years", "1-2 years", "up to 2 years", "no prior experience",
    "no experience required", "no experience necessary", "internship", "intern",
    "apprenticeship", "rotational program", "development program",
    "training program", "we'll train you", "we will train you", "early-career",
]

# Senior-scope language that signals a role is really mid/senior even without a
# senior title or a stated year count. Penalized in scoring (not a hard cut, to
# avoid false drops — the year gate + title gate do the hard filtering).
SENIOR_SCOPE_SIGNALS = [
    "proven track record", "demonstrated track record", "deep expertise",
    "deep experience", "subject matter expert", "thought leader",
    "own the strategy", "own the roadmap", "set the vision", "set the strategy",
    "define the strategy", "drive the strategy", "end-to-end ownership",
    "own end-to-end", "lead and mentor", "mentor junior", "manage a team",
    "people management", "direct reports", "manage agency", "manage vendor",
    "agency relationships", "vendor relationships",
]

# Growth marketing terms — Growth is now its OWN kept Function (not General
# Marketing), so these roles surface instead of getting excluded.
GROWTH_KEYWORDS = [
    "growth marketing", "growth", "acquisition", "activation", "funnel",
    "experimentation", "a/b testing", "ab testing", "conversion rate optimization",
    "cohort", "paid acquisition", "performance marketing", "ltv", "cac",
    "amplitude", "mixpanel",
]

# --- Legitimacy / anti-scam filter -------------------------------------------
# Aggregators (esp. Adzuna) carry MLM / commission-only / door-to-door "marketing"
# listings that are really sales gigs or outright scams. We DROP anything whose
# title or description trips these signals, so you never engage with a lead that
# could waste your time or fish for your information. ATS boards (Greenhouse /
# Lever / Ashby) and The Muse are real companies and rarely trip these.
SCAM_TITLE_SIGNALS = [
    "marketing representative", "marketing agent", "retail and marketing",
    "brand ambassador", "promoter", "canvasser", "canvassing",
    "appointment setter", "sales representative", "door to door",
    "door-to-door", "commission", "management trainee",
]
SCAM_BODY_SIGNALS = [
    "commission only", "commission-only", "100% commission",
    "uncapped commission", "be your own boss", "unlimited earning",
    "unlimited income", "earning potential", "no experience necessary",
    "no experience required", "weekly pay", "daily pay", "make money",
    "work from home opportunity", "mlm", "multi-level", "network marketing",
    "pyramid", "1099 commission", "independent distributor",
]
# Company names too vague to verify the employer is real → drop.
VAGUE_COMPANY_NAMES = {
    "", "n/a", "confidential", "company confidential", "established company",
    "private company", "a leading company", "undisclosed", "various",
}

# --- Scoring weights (transparent 0-100 fit score) ---------------------------
# Highest-priority signals first, per the profile.
SCORE_WEIGHTS = {
    # email / lifecycle / retention / CRM / Klaviyo  -> the top priority
    "email_lifecycle": 30,
    # product marketing / PMM
    "product_marketing": 18,
    # copywriting / written content
    "copywriting": 16,
    # entry-level signals
    "entry_level": 14,
    # remote-friendly
    "remote": 8,
    # startup / VC signal
    "startup": 6,
    # generic marketing relevance
    "generic_marketing": 8,
    # growth marketing relevance
    "growth": 12,
    # explicit entry-level signals ("new grad", "0-2 years", "training program")
    "entry_signal": 14,
    # penalties (negative)
    "seo_only_penalty": -25,
    "video_design_penalty": -12,
    "senior_scope_penalty": -16,   # "own the strategy", "manage a team", etc.
}

EMAIL_LIFECYCLE_KEYWORDS = [
    "email", "lifecycle", "retention", "crm", "klaviyo", "braze",
    "marketo", "hubspot", "iterable", "customer.io", "newsletter",
    "drip", "nurture", "churn",
]
PRODUCT_MARKETING_KEYWORDS = ["product marketing", "pmm", "go-to-market", "gtm", "positioning"]
COPYWRITING_KEYWORDS = ["copywrit", "copy ", "content", "writer", "writing", "editorial"]
STARTUP_KEYWORDS = ["startup", "seed", "series a", "series b", "early stage", "venture"]

# --- Location -----------------------------------------------------------------
# Remote (US) roles are always allowed and flagged. In-person roles are kept
# ONLY if their location matches one of these tokens (case-insensitive substring).
# Covers Miami / Nashville / Orlando / Dallas metros (~45 min radius incl.
# suburbs), NYC, Washington DC, plus all of Colorado and California.
LOCATION_ALLOW_TOKENS = [
    # ---- Miami / South Florida (Ft Lauderdale included) ----
    "miami", "miami beach", "coral gables", "hialeah", "doral", "aventura",
    "fort lauderdale", "ft lauderdale", "ft. lauderdale", "hollywood, fl",
    "pembroke pines", "boca raton", "pompano", "davie", "sunrise, fl",
    "plantation, fl", "miramar", "homestead", "kendall", "south florida",
    # ---- Nashville metro ----
    "nashville", "franklin, tn", "brentwood, tn", "murfreesboro",
    "hendersonville, tn", "smyrna, tn", "mount juliet", "gallatin",
    "lebanon, tn", "spring hill, tn",
    # ---- Orlando metro ----
    "orlando", "winter park", "kissimmee", "sanford, fl", "altamonte",
    "lake mary", "winter garden", "apopka", "oviedo", "clermont",
    "maitland", "lake nona", "central florida",
    # ---- Dallas / Fort Worth metroplex ----
    "dallas", "fort worth", "ft worth", "plano", "irving", "arlington, tx",
    "frisco", "mckinney", "richardson", "garland", "denton", "carrollton",
    "grapevine", "allen, tx", "addison", "las colinas", "dfw",
    # ---- NYC ----
    "new york", "nyc", "manhattan", "brooklyn", "queens", "new york, ny",
    # ---- Washington DC ----
    "washington, dc", "washington dc", "district of columbia",
    "arlington, va", "alexandria, va", "bethesda", " dc ",
    # ---- Colorado (whole state) ----
    "colorado", "denver", "boulder", "colorado springs", "fort collins",
    "aurora, co", "lakewood, co", ", co", " co ",
    # ---- California (whole state) ----
    "california", "san francisco", "los angeles", "san diego", "san jose",
    "oakland", "sacramento", "palo alto", "mountain view", "santa monica",
    "berkeley", "sunnyvale", "irvine", "pasadena", "long beach", "ca",
    ", ca", " ca ",
]

# Tokens that mark a role as remote (and remote-friendly is always allowed).
REMOTE_TOKENS = ["remote", "anywhere", "work from home", "wfh", "distributed", "virtual"]

# --- Adzuna geographic targeting ---------------------------------------------
# Adzuna is location-aware and refreshes constantly, so it's the best lever for
# fresh daily volume. We query each of your target metros plus a national pass.
# Listings still go through the same keyword / seniority / scam / function
# filters, so widening here adds coverage without lowering quality.
ADZUNA_CITIES = [
    "Miami, FL", "Fort Lauderdale, FL", "Orlando, FL",
    "Nashville, TN", "Dallas, TX", "Fort Worth, TX",
    "Denver, CO", "Colorado Springs, CO",
    "New York, NY", "Washington, DC",
    "Los Angeles, CA", "San Francisco, CA", "San Diego, CA",
]
ADZUNA_PAGES_PER_CITY = 1     # 1 page (~20 roles) per city keeps it fast
ADZUNA_NATIONAL_PAGES = 2     # extra national pass for remote-friendly roles


# =============================================================================
# AGENT 2 — APPLICATION-RESPONSE TRACKER
# =============================================================================

# --- Notion target (database already exists; do NOT create a new one) --------
RESPONSE_NOTION_DATABASE_ID = "ab97f9d59f14477ca5ac40ceab2b6ce4"

# --- Claude model for classification/extraction ------------------------------
RESPONSE_MODEL = "claude-haiku-4-5"

# --- Gmail lookback -----------------------------------------------------------
# How far back to scan each run. The hourly schedule means 2 days is plenty of
# overlap safety; the JobTracker/Logged label prevents reprocessing.
GMAIL_LOOKBACK_DAYS = 2
GMAIL_LOGGED_LABEL = "JobTracker/Logged"

# --- Pre-filter: known ATS / recruiting sender domains -----------------------
# If the sender's domain matches (or ends with) one of these, the email is a
# strong candidate regardless of keywords.
ATS_DOMAINS = [
    "greenhouse.io", "greenhouse-mail.io", "us.greenhouse-mail.io",
    "lever.co", "hire.lever.co",
    "ashbyhq.com",
    "myworkday.com", "workday.com",
    "smartrecruiters.com",
    "icims.com",
    "workable.com", "workablemail.com",
    "recruitee.com",
    "bamboohr.com",
    "jobvite.com",
    "breezy.hr",
    "rippling.com",
    "ashby.email",
]

# --- Pre-filter: recruiting language ------------------------------------------
RECRUITING_KEYWORDS = [
    "your application", "thank you for applying", "regarding your application",
    "application for", "next steps", "schedule a", "schedule time",
    "interview", "assessment", "take-home", "take home", "coding challenge",
    "unfortunately", "move forward", "moving forward", "offer",
    "we received your application", "application has been received",
    "talent team", "recruiting team", "hiring team", "recruiter",
]

# --- Pre-filter: NOISE to drop (job-board alerts / newsletters) --------------
# If subject/sender clearly matches one of these, drop even if keywords hit.
NOISE_KEYWORDS = [
    "jobs you may like", "jobs for you", "recommended jobs",
    "new jobs", "job alert", "job alerts", "jobs matching",
    "people you may know", "who's hiring", "weekly digest", "daily digest",
    "newsletter", "promotions", "view all jobs",
]
NOISE_SENDER_DOMAINS = [
    "linkedin.com", "indeed.com", "indeedemail.com", "ziprecruiter.com",
    "glassdoor.com", "wellfound.com", "angel.co", "monster.com",
    "google.com/alerts", "talent.com", "dice.com",
]

# --- Notifier selection (Agent 2) --------------------------------------------
# "ntfy" is implemented. "telegram" and "email" are documented stubs in
# shared/notify.py.
RESPONSE_NOTIFIER = "ntfy"


# =============================================================================
# DAILY EMAIL DIGEST (Agent 1)
# =============================================================================
# After each job-discovery run, email you a summary of how many NEW leads were
# added (and the list, with apply links). Uses your existing Gmail credentials
# (GMAIL_ADDRESS + GMAIL_APP_PASSWORD) over SMTP — no new secret needed.
# The email is sent every run, so it also confirms the 8 AM job actually fired.
EMAIL_DIGEST_ENABLED = True
EMAIL_SEND_WHEN_ZERO = True     # still email "0 new leads today" as a heartbeat
# Recipient defaults to GMAIL_ADDRESS; override with the EMAIL_TO env var.


# =============================================================================
# BIWEEKLY CLEANUP (Agent 1 maintenance) — every other Friday
# =============================================================================
# Archives finished/stale leads off the Job Leads board to Notion's trash
# (recoverable for 30 days). Archives a row if EITHER:
#   - its "Applied" checkbox is ticked, OR
#   - it was added more than CLEANUP_STALE_DAYS ago and was never applied to.
# The workflow runs every Friday but the script self-gates to alternating weeks
# via ISO-week parity, so it only fires every OTHER Friday.
CLEANUP_STALE_DAYS = 14
CLEANUP_WEEK_PARITY = 1          # 1 = odd ISO weeks → first run Fri 2026-06-19


# =============================================================================
# SHARED PATHS
# =============================================================================
import os

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DIGEST_DIR = os.path.join(DATA_DIR, "digests")
JOBS_DB_PATH = os.path.join(DATA_DIR, "jobs.db")
# Tracks the last date the daily email was sent, so multiple morning cron
# attempts (added for reliability) still produce at most one email per day.
LAST_EMAIL_DATE_PATH = os.path.join(DATA_DIR, "last_email_date.txt")
# Preferences the agent learns from what you Skip / Apply on the Notion board.
LEARNED_PREFS_PATH = os.path.join(DATA_DIR, "learned_prefs.json")

# --- Learning-from-skips tuning (all bounded, so it only nudges ranking) ------
LEARN_MIN_OCCURRENCES = 2     # a title keyword needs this many sightings to count
LEARN_TOKEN_STEP = 4          # points per net (applied-skipped) keyword occurrence
LEARN_TOKEN_CAP = 8           # max +/- per keyword
LEARN_FUNCTION_STEP = 5       # points per net function preference
LEARN_FUNCTION_CAP = 12
LEARN_COMPANY_STEP = 6        # penalty per skip for a never-applied company
LEARN_COMPANY_CAP = 15
LEARN_ADJ_CLAMP = 22          # total learned adjustment per role is capped here
# Generic words ignored when learning title keywords (too common to be a signal).
LEARN_STOPWORDS = {
    "the", "and", "of", "for", "to", "a", "an", "in", "on", "at", "with", "or",
    "by", "marketing", "remote", "us", "usa", "united", "states", "job", "jobs",
    "full", "time", "part", "hybrid", "new", "team", "role", "and/or",
}

# Polite HTTP defaults for all outbound scraping/API calls.
USER_AGENT = "marketing-job-agent/1.0 (personal job search; contact via repo)"
HTTP_TIMEOUT = 30          # seconds
REQUEST_DELAY = 0.8        # seconds between successive source requests
