"""
Filtering logic for Agent 1.

A posting must pass ALL of these to make the digest:
  1. Keyword include (matches >=1 INCLUDE keyword in title/description)
  2. Not a hard-excluded seniority (senior/lead/manager/director/...)
  3. Not an SEO-primary role (SEO in the title)
  4. Legitimate (not a scam/MLM/commission-only/door-to-door listing; real employer)
  5. Recent (posted within POSTED_WITHIN_DAYS; kept if date unknown)
  6. Location allowed (remote OR matches the in-person allow-list)

(Note: the "no General Marketing" rule is applied in main.py after the role's
Function is classified, not here.)

Each returns (bool, reason) so the runner can log WHY something was dropped.
"""
import re
from datetime import date, datetime, timedelta

import config


def _blob(job):
    return f"{job.get('title','')} {job.get('description','')}".lower()


def _title_tokens(job):
    """Lowercased title with punctuation flattened to spaces -> word set."""
    title = (job.get("title") or "").lower()
    norm = re.sub(r"[^a-z0-9]+", " ", title)
    return norm, set(norm.split())


def passes_keywords(job):
    # Gate on the TITLE, not the description — incidental keyword hits in a JD
    # (e.g. a backend role that mentions "growth") were leaking junk through.
    title = (job.get("title") or "").lower()
    if not any(k in title for k in config.INCLUDE_KEYWORDS):
        return False, "no include-keyword match in title"
    return True, ""


def passes_seniority(job):
    norm, tokens = _title_tokens(job)
    # Multi-word senior signals.
    if "vice president" in norm:
        return False, "excluded seniority: vice president"
    # Single-word senior signals matched as whole words (punctuation-proof:
    # catches "VP,", "Sr.", "Manager", "Supervisor", "Lead", etc.).
    hard = config.HARD_EXCLUDE_TOKENS
    # "Manager" is allowed when a junior qualifier is present (e.g. "Associate
    # Product Marketing Manager" / "Assistant Marketing Manager").
    if tokens & config.JUNIOR_TITLE_TOKENS:
        hard = hard - {"manager", "mgr"}
    hit = tokens & hard
    if hit:
        return False, f"excluded seniority: {', '.join(sorted(hit))}"
    return True, ""


def passes_seo(job):
    title = (job.get("title") or "").lower()
    if any(tok in title for tok in config.SEO_TITLE_EXCLUDE):
        return False, "SEO-primary title"
    return True, ""


def passes_recency(job):
    posted = job.get("posted_date")
    if not posted:
        return True, ""  # unknown date — keep, don't penalize on filter
    try:
        d = datetime.strptime(posted, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return True, ""
    cutoff = date.today() - timedelta(days=config.POSTED_WITHIN_DAYS)
    if d < cutoff:
        return False, f"older than {config.POSTED_WITHIN_DAYS}d ({posted})"
    return True, ""


def passes_legitimacy(job):
    """
    Drop scam / MLM / commission-only / door-to-door listings, and roles whose
    employer can't be identified. Protects you from wasting time on (or handing
    info to) anything that isn't a real marketing job at a real company.
    """
    company = (job.get("company") or "").strip().lower()
    if company in config.VAGUE_COMPANY_NAMES:
        return False, f"unverifiable employer ('{job.get('company')}')"

    title = (job.get("title") or "").lower()
    if any(sig in title for sig in config.SCAM_TITLE_SIGNALS):
        return False, "scam/sales signal in title"

    blob = _blob(job)
    if any(sig in blob for sig in config.SCAM_BODY_SIGNALS):
        return False, "scam/MLM signal in description"

    return True, ""


_WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
              "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_YEAR_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:-|–|to)\s*\d{1,2}\s*\+?\s*(?:years|yrs)\b")
_YEAR_SINGLE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs)\b")
_YEAR_WORD_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*\+?\s*(?:years|yrs)\b")


def _required_years(text):
    """Highest 'minimum years required' the JD asks for (ranges use lower bound)."""
    reqs = []
    # Ranges first ("3-5 years" requires 3); then mask them out.
    for m in _YEAR_RANGE_RE.finditer(text):
        reqs.append(int(m.group(1)))
    masked = _YEAR_RANGE_RE.sub(" ", text)
    for m in _YEAR_SINGLE_RE.finditer(masked):
        reqs.append(int(m.group(1)))
    for m in _YEAR_WORD_RE.finditer(masked):
        reqs.append(_WORD_NUMS[m.group(1)])
    return max(reqs) if reqs else 0


def passes_experience(job):
    """Drop roles requiring >= EXPERIENCE_MAX_YEARS years (the 'no-chance' fix)."""
    years = _required_years(_blob(job))
    if years >= config.EXPERIENCE_MAX_YEARS:
        return False, f"requires {years}+ years experience"
    return True, ""


def passes_location(job):
    if job.get("remote"):
        return True, ""
    loc = (job.get("location") or "").lower().strip()
    if not loc:
        # No location given and not flagged remote — keep but it'll often be
        # remote/unspecified at small startups; let scoring sort it.
        return True, ""
    if any(tok in loc for tok in config.LOCATION_ALLOW_TOKENS):
        return True, ""
    # Also treat explicit "remote" text in the location string as allowed.
    if any(tok in loc for tok in config.REMOTE_TOKENS):
        return True, ""
    return False, f"location not in allow-list ({job.get('location')})"


def keep(job):
    """Run every filter. Return (kept: bool, reason: str)."""
    for check in (passes_keywords, passes_seniority, passes_seo,
                  passes_legitimacy, passes_experience, passes_recency,
                  passes_location):
        ok, reason = check(job)
        if not ok:
            return False, reason
    return True, "kept"
