"""
Transparent 0-100 fit scoring + Function/Seniority classification for Notion.

Scoring is intentionally simple and explainable (see SCORE_WEIGHTS in config).
classify_function / classify_seniority map a role onto the exact Notion select
options the database expects.
"""
import config


def _blob(job):
    return f"{job.get('title','')} {job.get('description','')}".lower()


def score(job):
    """Return an int 0-100 fit score."""
    blob = _blob(job)
    title = (job.get("title") or "").lower()
    w = config.SCORE_WEIGHTS
    s = 0

    # Highest priority: email / lifecycle / retention / CRM / Klaviyo
    if any(k in blob for k in config.EMAIL_LIFECYCLE_KEYWORDS):
        s += w["email_lifecycle"]

    # Product marketing / PMM
    if any(k in blob for k in config.PRODUCT_MARKETING_KEYWORDS):
        s += w["product_marketing"]

    # Copywriting / written content
    if any(k in blob for k in config.COPYWRITING_KEYWORDS):
        s += w["copywriting"]

    # Entry-level signals (title-weighted)
    if any(tok.strip() in title for tok in config.SENIORITY_ALLOW_TOKENS if tok.strip()):
        s += w["entry_level"]

    # Remote-friendly
    if job.get("remote"):
        s += w["remote"]

    # Startup / VC signal
    if any(k in blob for k in config.STARTUP_KEYWORDS) or job.get("source") in (
        "Greenhouse", "Lever", "Ashby"
    ):
        s += w["startup"]

    # Generic marketing relevance (always some credit if it got this far)
    if "marketing" in blob:
        s += w["generic_marketing"]

    # --- penalties (still surfaced, just ranked lower) ---
    if "seo" in blob and "seo" not in title:
        s += w["seo_only_penalty"] // 2  # mentions SEO but not primary -> mild
    if any(k in blob for k in config.DOWNRANK_KEYWORDS):
        s += w["video_design_penalty"]

    return max(0, min(100, s))


def classify_function(job):
    """Map to one of the Notion 'Function' select options."""
    blob = _blob(job)
    if any(k in blob for k in config.EMAIL_LIFECYCLE_KEYWORDS):
        return "Email / Lifecycle"
    if any(k in blob for k in config.PRODUCT_MARKETING_KEYWORDS):
        return "Product Marketing"
    if any(k in blob for k in ("copywrit", "content", "editorial", "writer", "writing")):
        return "Content / Copywriting"
    if any(k in blob for k in ("paid", "ppc", "performance marketing", "demand gen",
                               "ads", "sem", "acquisition")):
        return "Paid Ads"
    if "marketing" in blob:
        return "General Marketing"
    return "Other"


def classify_seniority(job):
    """Map to one of the Notion 'Seniority' select options."""
    title = (job.get("title") or "").lower()
    if "intern" in title:
        return "Internship"
    if "coordinator" in title:
        return "Coordinator"
    if "associate" in title or "junior" in title or " jr" in title:
        return "Junior / Associate"
    # default bucket for entry-level / I / II
    return "Entry Level"
