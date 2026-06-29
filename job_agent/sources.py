"""
Job sources — each fetcher returns a list of NORMALIZED dicts:

    {
        "title":       str,
        "company":     str,
        "location":    str,
        "remote":      bool,
        "posted_date": "YYYY-MM-DD" or None,
        "source":      str,    # e.g. "Greenhouse"
        "apply_url":   str,
        "description": str,    # plain-ish text used for keyword matching
    }

We deliberately use STRUCTURED, scrape-friendly endpoints (public ATS JSON +
free public job APIs) instead of brute-forcing LinkedIn/Indeed/Glassdoor.

Every fetcher is defensive: network/parse errors are caught and logged, and an
empty list is returned so one bad source never sinks the whole run.
"""
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

import config

_HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}


# --- small helpers ------------------------------------------------------------

def _get(url, params=None, headers=None, timeout=None):
    time.sleep(config.REQUEST_DELAY)  # be polite
    return requests.get(
        url,
        params=params,
        headers=headers or _HEADERS,
        timeout=timeout or config.HTTP_TIMEOUT,
    )


def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _iso_date(value):
    """Coerce many timestamp shapes into 'YYYY-MM-DD' or None."""
    if value is None or value == "":
        return None
    # epoch milliseconds (Lever) or seconds
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e12 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    # try a few common string formats
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S.%f", "%a, %d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 6], fmt).date().isoformat()
        except ValueError:
            continue
    # ISO with timezone offset, e.g. 2024-01-02T03:04:05+00:00
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    # RFC-822 (RSS pubDate), e.g. "Mon, 09 Jun 2026 17:00:00 +0000"
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _looks_remote(*texts):
    blob = " ".join(t for t in texts if t).lower()
    return any(tok in blob for tok in config.REMOTE_TOKENS)


# --- Greenhouse ---------------------------------------------------------------

def fetch_greenhouse(slugs):
    out = []
    for slug in slugs:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        try:
            resp = _get(url, params={"content": "true"})
            if resp.status_code != 200:
                print(f"[greenhouse] {slug}: HTTP {resp.status_code}")
                continue
            jobs = resp.json().get("jobs", [])
            for j in jobs:
                loc = (j.get("location") or {}).get("name", "") or ""
                content = _strip_html(j.get("content", ""))
                out.append({
                    "title": j.get("title", ""),
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "remote": _looks_remote(loc, j.get("title", "")),
                    "posted_date": _iso_date(j.get("updated_at") or j.get("first_published")),
                    "source": "Greenhouse",
                    "apply_url": j.get("absolute_url", ""),
                    "description": content,
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[greenhouse] {slug}: {exc}")
    return out


# --- Lever --------------------------------------------------------------------

def fetch_lever(slugs):
    out = []
    for slug in slugs:
        url = f"https://api.lever.co/v0/postings/{slug}"
        try:
            resp = _get(url, params={"mode": "json"})
            if resp.status_code != 200:
                print(f"[lever] {slug}: HTTP {resp.status_code}")
                continue
            for p in resp.json():
                cats = p.get("categories") or {}
                loc = cats.get("location", "") or ""
                commitment = cats.get("commitment", "") or ""
                desc = _strip_html(p.get("descriptionPlain") or p.get("description", ""))
                out.append({
                    "title": p.get("text", ""),
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "remote": _looks_remote(loc, commitment, p.get("workplaceType", "")),
                    "posted_date": _iso_date(p.get("createdAt")),
                    "source": "Lever",
                    "apply_url": p.get("hostedUrl", ""),
                    "description": desc,
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[lever] {slug}: {exc}")
    return out


# --- Ashby --------------------------------------------------------------------

def fetch_ashby(slugs):
    out = []
    for slug in slugs:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        try:
            resp = _get(url, params={"includeCompensation": "false"})
            if resp.status_code != 200:
                print(f"[ashby] {slug}: HTTP {resp.status_code}")
                continue
            jobs = resp.json().get("jobs", [])
            for j in jobs:
                loc = j.get("location", "") or ""
                desc = _strip_html(j.get("descriptionPlain") or j.get("descriptionHtml", ""))
                out.append({
                    "title": j.get("title", ""),
                    "company": slug.replace("-", " ").title(),
                    "location": loc,
                    "remote": bool(j.get("isRemote")) or _looks_remote(loc),
                    "posted_date": _iso_date(j.get("publishedAt") or j.get("updatedAt")),
                    "source": "Ashby",
                    "apply_url": j.get("applyUrl") or j.get("jobUrl", ""),
                    "description": desc,
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[ashby] {slug}: {exc}")
    return out


# --- The Muse -----------------------------------------------------------------

def fetch_themuse(max_pages=5):
    out = []
    base = "https://www.themuse.com/api/public/jobs"
    for level in ("Entry Level", "Internship"):
        for page in range(max_pages):
            try:
                resp = _get(base, params={
                    "category": "Marketing",
                    "level": level,
                    "page": page,
                })
                if resp.status_code != 200:
                    break
                results = resp.json().get("results", [])
                if not results:
                    break
                for r in results:
                    locs = [l.get("name", "") for l in (r.get("locations") or [])]
                    loc = ", ".join(locs)
                    out.append({
                        "title": r.get("name", ""),
                        "company": (r.get("company") or {}).get("name", ""),
                        "location": loc,
                        "remote": _looks_remote(loc),
                        "posted_date": _iso_date(r.get("publication_date")),
                        "source": "The Muse",
                        "apply_url": (r.get("refs") or {}).get("landing_page", ""),
                        "description": _strip_html(r.get("contents", "")),
                    })
            except Exception as exc:  # noqa: BLE001
                print(f"[themuse] page {page} ({level}): {exc}")
                break
    return out


# --- RemoteOK -----------------------------------------------------------------

def fetch_remoteok():
    out = []
    try:
        # RemoteOK wants a browser-ish UA and returns a leading metadata element.
        resp = _get("https://remoteok.com/api",
                    headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
        if resp.status_code != 200:
            print(f"[remoteok] HTTP {resp.status_code}")
            return out
        data = resp.json()
        for r in data:
            if not isinstance(r, dict) or "position" not in r:
                continue  # skip the legal/metadata element
            out.append({
                "title": r.get("position", ""),
                "company": r.get("company", ""),
                "location": r.get("location", "") or "Remote",
                "remote": True,  # everything here is remote
                "posted_date": _iso_date(r.get("date")),
                "source": "RemoteOK",
                "apply_url": r.get("url", ""),
                "description": _strip_html(r.get("description", ""))
                + " " + " ".join(r.get("tags", [])),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[remoteok] {exc}")
    return out


# --- Remotive (free, no key) --------------------------------------------------

def fetch_remotive():
    out = []
    try:
        resp = _get("https://remotive.com/api/remote-jobs",
                    params={"category": "marketing", "limit": 80})
        if resp.status_code != 200:
            print(f"[remotive] HTTP {resp.status_code}")
            return out
        for j in resp.json().get("jobs", []):
            out.append({
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location", "") or "Remote",
                "remote": True,
                "posted_date": _iso_date(j.get("publication_date")),
                "source": "Remotive",
                "apply_url": j.get("url", ""),
                "description": _strip_html(j.get("description", "")),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[remotive] {exc}")
    return out


# --- Jobicy (free, no key) ----------------------------------------------------

def fetch_jobicy():
    out = []
    try:
        resp = _get("https://jobicy.com/api/v2/remote-jobs",
                    params={"count": 50, "industry": "marketing"})
        if resp.status_code != 200:
            print(f"[jobicy] HTTP {resp.status_code}")
            return out
        for j in resp.json().get("jobs", []):
            out.append({
                "title": j.get("jobTitle", ""),
                "company": j.get("companyName", ""),
                "location": j.get("jobGeo", "") or "Remote",
                "remote": True,
                "posted_date": _iso_date(j.get("pubDate")),
                "source": "Jobicy",
                "apply_url": j.get("url", ""),
                "description": _strip_html(j.get("jobExcerpt", "") or j.get("jobDescription", "")),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[jobicy] {exc}")
    return out


# --- We Work Remotely (free RSS, no key) --------------------------------------

def fetch_weworkremotely():
    out = []
    # WWR consolidated marketing into the sales-and-marketing category.
    feeds = [
        "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
    ]
    for url in feeds:
        try:
            resp = _get(url, headers={"User-Agent": config.USER_AGENT,
                                      "Accept": "application/rss+xml"})
            if resp.status_code != 200:
                print(f"[wwr] {url.rsplit('/', 1)[-1]}: HTTP {resp.status_code}")
                continue
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                raw_title = (item.findtext("title") or "").strip()
                # WWR titles are formatted "Company: Role".
                if ":" in raw_title:
                    company, _, title = raw_title.partition(":")
                    company, title = company.strip(), title.strip()
                else:
                    company, title = "", raw_title
                region = (item.findtext("region") or "").strip()
                out.append({
                    "title": title,
                    "company": company,
                    "location": region or "Remote",
                    "remote": True,
                    "posted_date": _iso_date(item.findtext("pubDate")),
                    "source": "We Work Remotely",
                    "apply_url": (item.findtext("link") or "").strip(),
                    "description": _strip_html(item.findtext("description") or ""),
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[wwr] {url.rsplit('/', 1)[-1]}: {exc}")
    return out


# --- Adzuna (optional — needs API key) ---------------------------------------

def _adzuna_page(app_id, app_key, page, where=None):
    """Fetch one Adzuna page (optionally scoped to a `where` location)."""
    url = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": "marketing",
        "max_days_old": config.POSTED_WITHIN_DAYS,
        "results_per_page": 25,
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
        params["distance"] = 50  # km radius — covers the ~45-min metro you asked for
    resp = _get(url, params=params)
    if resp.status_code != 200:
        print(f"[adzuna] where={where or 'US'} page {page}: HTTP {resp.status_code}")
        return []
    rows = []
    for r in resp.json().get("results", []):
        loc = (r.get("location") or {}).get("display_name", "") or ""
        rows.append({
            "title": r.get("title", ""),
            "company": (r.get("company") or {}).get("display_name", ""),
            "location": loc,
            "remote": _looks_remote(loc, r.get("title", "")),
            "posted_date": _iso_date(r.get("created")),
            "source": "Adzuna",
            "apply_url": r.get("redirect_url", ""),
            "description": _strip_html(r.get("description", "")),
        })
    return rows


def fetch_adzuna():
    """Query each target metro (location-scoped) plus a national/remote pass."""
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        print("[adzuna] no API key set — skipping gracefully.")
        return []
    out = []
    # Per-city passes (your metros, ~50km radius each).
    for city in config.ADZUNA_CITIES:
        for page in range(1, config.ADZUNA_PAGES_PER_CITY + 1):
            try:
                out += _adzuna_page(app_id, app_key, page, where=city)
            except Exception as exc:  # noqa: BLE001
                print(f"[adzuna] {city} page {page}: {exc}")
                break
    # National pass (catches remote-friendly roles not tied to a city).
    for page in range(1, config.ADZUNA_NATIONAL_PAGES + 1):
        try:
            out += _adzuna_page(app_id, app_key, page)
        except Exception as exc:  # noqa: BLE001
            print(f"[adzuna] national page {page}: {exc}")
            break
    return out


# --- Orchestrator -------------------------------------------------------------

def fetch_all():
    """Run every enabled source and return one combined, normalized list."""
    enabled = config.SOURCES_ENABLED
    jobs = []
    if enabled.get("greenhouse"):
        jobs += fetch_greenhouse(config.GREENHOUSE_SLUGS)
    if enabled.get("lever"):
        jobs += fetch_lever(config.LEVER_SLUGS)
    if enabled.get("ashby"):
        jobs += fetch_ashby(config.ASHBY_SLUGS)
    if enabled.get("themuse"):
        jobs += fetch_themuse()
    if enabled.get("remoteok"):
        jobs += fetch_remoteok()
    if enabled.get("remotive"):
        jobs += fetch_remotive()
    if enabled.get("jobicy"):
        jobs += fetch_jobicy()
    if enabled.get("weworkremotely"):
        jobs += fetch_weworkremotely()
    if enabled.get("adzuna"):
        jobs += fetch_adzuna()
    print(f"[sources] fetched {len(jobs)} raw postings across enabled sources.")
    return jobs
