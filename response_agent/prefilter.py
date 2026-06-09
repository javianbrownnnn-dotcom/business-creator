"""
Cheap, no-LLM pre-filter for Agent 2.

Goal: cut volume (and Claude cost) to near-zero by only passing through emails
that plausibly are real responses to job applications.

An email becomes a CANDIDATE if:
  - sender domain is a known ATS/recruiting domain, OR
  - subject/body contains recruiting language.
...UNLESS it trips the noise filter (job-board alerts / newsletters / digests),
which drops it outright.

Returns (is_candidate: bool, reason: str) so the runner can log decisions.
"""
import config


def _sender_domain(from_email):
    return from_email.split("@", 1)[1].lower() if "@" in from_email else ""


def is_noise(email_msg):
    """True if this is clearly a job-board alert / newsletter / digest."""
    subject = (email_msg.get("subject") or "").lower()
    domain = _sender_domain(email_msg.get("from_email", ""))

    if any(d in domain for d in config.NOISE_SENDER_DOMAINS):
        return True, f"noise sender domain ({domain})"
    if any(k in subject for k in config.NOISE_KEYWORDS):
        return True, "noise subject (job-board alert/newsletter)"
    return False, ""


def is_candidate(email_msg):
    """Decide whether to pass this email to the LLM classifier."""
    noisy, why = is_noise(email_msg)
    if noisy:
        return False, why

    domain = _sender_domain(email_msg.get("from_email", ""))
    if any(domain == d or domain.endswith("." + d) or d in domain
           for d in config.ATS_DOMAINS):
        return True, f"ATS domain ({domain})"

    blob = f"{email_msg.get('subject','')} {email_msg.get('body','')}".lower()
    if any(k in blob for k in config.RECRUITING_KEYWORDS):
        return True, "recruiting language match"

    return False, "no ATS domain / recruiting language"
