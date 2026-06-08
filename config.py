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
GREENHOUSE_SLUGS = [
    "stripe",
    "airbnb",
    "databricks",
    "gitlab",
    "figma",
    "discord",
]

LEVER_SLUGS = [
    "ramp",
    "plaid",
    "notion",
    "attentive",   # email/SMS marketing platform — strongly on-profile
]

ASHBY_SLUGS = [
    "linear",
    "vanta",
    "posthog",
    "runway",
]

# --- Which sources to enable --------------------------------------------------
SOURCES_ENABLED = {
    "greenhouse": True,
    "lever": True,
    "ashby": True,
    "themuse": True,
    "remoteok": True,
    "adzuna": True,   # auto-skips if ADZUNA_APP_ID / ADZUNA_APP_KEY are unset
}

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

# Seniority words that disqualify a role outright.
HARD_EXCLUDE_KEYWORDS = [
    "senior", "sr.", "staff", "principal", "lead ", "team lead",
    "manager", "mgr", "head of", "director", "vp ", "vice president",
    "chief", "president",
]

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
    # penalties (negative)
    "seo_only_penalty": -25,
    "video_design_penalty": -12,
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
# SHARED PATHS
# =============================================================================
import os

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DIGEST_DIR = os.path.join(DATA_DIR, "digests")
JOBS_DB_PATH = os.path.join(DATA_DIR, "jobs.db")

# Polite HTTP defaults for all outbound scraping/API calls.
USER_AGENT = "marketing-job-agent/1.0 (personal job search; contact via repo)"
HTTP_TIMEOUT = 30          # seconds
REQUEST_DELAY = 0.8        # seconds between successive source requests
