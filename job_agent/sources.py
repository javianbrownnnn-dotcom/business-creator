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

    out += _fetch_themuse_locations()
    return out


def _fetch_themuse_locations():
    """
    Metro-targeted pass over the same free Muse API (no key). This carries the
    in-person/local coverage that the billable aggregators used to provide.
    """
    out = []
    base = "https://www.themuse.com/api/public/jobs"
    for loc_query in config.THEMUSE_LOCATIONS:
        for level in ("Entry Level", "Internship"):
            for page in range(config.THEMUSE_LOCATION_PAGES):
                try:
                    resp = _get(base, params={
                        "category": "Marketing",
                        "level": level,
                        "location": loc_query,
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
                    print(f"[themuse] {loc_query} p{page} ({level}): {exc}")
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


# --- Arbeitnow (free, no key) -------------------------------------------------

def fetch_arbeitnow(max_pages=3):
    """Free public job board API (no key). Global, many remote roles."""
    out = []
    base = "https://www.arbeitnow.com/api/job-board-api"
    for page in range(1, max_pages + 1):
        try:
            resp = _get(base, params={"page": page})
            if resp.status_code != 200:
                print(f"[arbeitnow] page {page}: HTTP {resp.status_code}")
                break
            data = resp.json().get("data", [])
            if not data:
                break
            for j in data:
                tags = j.get("tags") or []
                job_types = j.get("job_types") or []
                loc = j.get("location", "") or ""
                remote = bool(j.get("remote")) or _looks_remote(loc)
                out.append({
                    "title": j.get("title", ""),
                    "company": j.get("company_name", ""),
                    "location": loc or ("Remote" if remote else ""),
                    "remote": remote,
                    "posted_date": _iso_date(j.get("created_at")),
                    "source": "Arbeitnow",
                    "apply_url": j.get("url", ""),
                    "description": _strip_html(j.get("description", ""))
                    + " " + " ".join(tags) + " " + " ".join(job_types),
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[arbeitnow] page {page}: {exc}")
            break
    return out


# --- Himalayas (free, no key) -------------------------------------------------

def fetch_himalayas(limit=100):
    """Free remote-jobs API (no key). Every posting here is remote."""
    out = []
    try:
        resp = _get("https://himalayas.app/jobs/api", params={"limit": limit})
        if resp.status_code != 200:
            print(f"[himalayas] HTTP {resp.status_code}")
            return out
        for j in resp.json().get("jobs", []):
            locs = j.get("locationRestrictions") or []
            loc = ", ".join(locs) if isinstance(locs, list) else str(locs or "")
            cats = j.get("categories") or []
            out.append({
                "title": j.get("title", ""),
                "company": j.get("companyName", ""),
                "location": loc or "Remote",
                "remote": True,
                "posted_date": _iso_date(j.get("pubDate")),
                "source": "Himalayas",
                "apply_url": j.get("applicationLink") or j.get("guid", ""),
                "description": _strip_html(j.get("description") or j.get("excerpt", ""))
                + " " + " ".join(cats if isinstance(cats, list) else []),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[himalayas] {exc}")
    return out


# --- SmartRecruiters (free, no key — public ATS boards) -----------------------

def fetch_smartrecruiters(slugs):
    out = []
    for slug in slugs:
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        try:
            resp = _get(url, params={"limit": 100})
            if resp.status_code != 200:
                print(f"[smartrecruiters] {slug}: HTTP {resp.status_code}")
                continue
            for p in resp.json().get("content", []):
                if not isinstance(p, dict):
                    continue
                loc_obj = p.get("location") or {}
                loc = ", ".join(x for x in (
                    loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")
                ) if x)
                company = (p.get("company") or {}).get("name") or slug
                # The list endpoint omits the full ad; department/function still
                # give the keyword filters something beyond the title.
                extra = " ".join(str((p.get(k) or {}).get("label", ""))
                                 for k in ("department", "function", "industry"))
                out.append({
                    "title": p.get("name", ""),
                    "company": company,
                    "location": loc,
                    "remote": bool(loc_obj.get("remote")) or _looks_remote(loc),
                    "posted_date": _iso_date(p.get("releasedDate") or p.get("createdOn")),
                    "source": "SmartRecruiters",
                    "apply_url": f"https://jobs.smartrecruiters.com/{slug}/{p.get('id','')}",
                    "description": extra.strip(),
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[smartrecruiters] {slug}: {exc}")
    return out


# --- Recruitee (free, no key — public ATS boards) -----------------------------

def fetch_recruitee(slugs):
    out = []
    for slug in slugs:
        url = f"https://{slug}.recruitee.com/api/offers/"
        try:
            resp = _get(url)
            if resp.status_code != 200:
                print(f"[recruitee] {slug}: HTTP {resp.status_code}")
                continue
            for o in resp.json().get("offers", []):
                if not isinstance(o, dict):
                    continue
                loc = ", ".join(x for x in (o.get("city"), o.get("country")) if x) \
                    or (o.get("location") or "")
                desc = _strip_html(
                    (o.get("description") or "") + " " + (o.get("requirements") or "")
                )
                out.append({
                    "title": o.get("title", ""),
                    "company": o.get("company_name") or slug.replace("-", " ").title(),
                    "location": loc,
                    "remote": bool(o.get("remote")) or _looks_remote(loc),
                    "posted_date": _iso_date(o.get("published_at") or o.get("created_at")),
                    "source": "Recruitee",
                    "apply_url": o.get("careers_apply_url") or o.get("careers_url", ""),
                    "description": desc,
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[recruitee] {slug}: {exc}")
    return out


# --- Workable (free, no key — public ATS boards) ------------------------------

def fetch_workable(slugs):
    out = []
    for slug in slugs:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        try:
            resp = _get(url, params={"details": "true"})
            if resp.status_code != 200:
                print(f"[workable] {slug}: HTTP {resp.status_code}")
                continue
            data = resp.json()
            company = data.get("name") or slug.replace("-", " ").title()
            for j in data.get("jobs", []):
                if not isinstance(j, dict):
                    continue
                loc_obj = j.get("location") or {}
                if isinstance(loc_obj, dict):
                    loc = ", ".join(x for x in (
                        loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")
                    ) if x)
                    telecommuting = bool(loc_obj.get("telecommuting"))
                else:
                    loc, telecommuting = str(loc_obj or ""), False
                out.append({
                    "title": j.get("title", ""),
                    "company": company,
                    "location": loc,
                    "remote": telecommuting or _looks_remote(loc),
                    "posted_date": _iso_date(j.get("published_on") or j.get("created_at")),
                    "source": "Workable",
                    "apply_url": j.get("url") or j.get("shortlink", ""),
                    "description": _strip_html(j.get("description", "")),
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[workable] {slug}: {exc}")
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


# --- JSearch via RapidAPI (keyed — Google for Jobs aggregator) ----------------

def fetch_jsearch():
    """Pull from JSearch (LinkedIn/Indeed/Glassdoor via Google for Jobs)."""
    key = os.environ.get("RAPIDAPI_KEY")
    if not key:
        print("[jsearch] no RAPIDAPI_KEY set — skipping gracefully.")
        return []
    out = []
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        "Accept": "application/json",
    }
    # Some JSearch deployments serve "/search", others "/search-v2". Try the
    # first; if it 404s as "does not exist", fall back and lock onto the one
    # that works for the rest of the queries.
    endpoints = ["/search", "/search-v2"]
    working = None
    for query in config.JSEARCH_QUERIES:
        params = {
            "query": f"{query} in United States",
            "page": 1,
            "num_pages": 1,
            "date_posted": config.JSEARCH_DATE_POSTED,
            "country": "us",
        }
        for ep in ([working] if working else endpoints):
            try:
                resp = _get(f"https://jsearch.p.rapidapi.com{ep}", params=params, headers=headers)
            except Exception as exc:  # noqa: BLE001
                print(f"[jsearch] '{query}' {ep}: {exc}")
                break
            if resp.status_code == 200:
                working = ep
                try:
                    payload = resp.json()
                except Exception:  # noqa: BLE001
                    payload = {}
                data = payload.get("data", [])
                # /search returns data=[jobs]; /search-v2 returns
                # data={"jobs":[...], "cursor":...}. Unwrap both shapes.
                if isinstance(data, dict):
                    data = data.get("jobs") or data.get("results") or []
                items = [j for j in data if isinstance(j, dict)] if isinstance(data, list) else []
                if not items:
                    print(f"[jsearch] '{query}' {ep}: HTTP 200 but no jobs parsed.")
                for j in items:
                    city = j.get("job_city") or j.get("city") or ""
                    state = j.get("job_state") or j.get("state") or ""
                    country = j.get("job_country") or j.get("country") or ""
                    loc = ", ".join(p for p in (city, state, country) if p)
                    remote = bool(j.get("job_is_remote") or j.get("is_remote"))
                    out.append({
                        "title": j.get("job_title") or j.get("title") or "",
                        "company": (j.get("employer_name") or j.get("company_name")
                                    or j.get("employer") or ""),
                        "location": loc or ("Remote" if remote else ""),
                        "remote": remote,
                        "posted_date": _iso_date(j.get("job_posted_at_datetime_utc")
                                                 or j.get("job_posted_at") or j.get("posted_at")),
                        "source": "JSearch",
                        "apply_url": (j.get("job_apply_link") or j.get("apply_link")
                                      or j.get("url") or ""),
                        "description": _strip_html(j.get("job_description")
                                                   or j.get("description") or ""),
                    })
                break
            msg = (resp.text or "")[:160].replace("\n", " ")
            print(f"[jsearch] '{query}' {ep}: HTTP {resp.status_code} — {msg}")
            # Only try the next endpoint when this path simply doesn't exist.
            if not (resp.status_code == 404 and "does not exist" in msg):
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
    if enabled.get("arbeitnow"):
        jobs += fetch_arbeitnow()
    if enabled.get("himalayas"):
        jobs += fetch_himalayas()
    if enabled.get("smartrecruiters"):
        jobs += fetch_smartrecruiters(config.SMARTRECRUITERS_SLUGS)
    if enabled.get("recruitee"):
        jobs += fetch_recruitee(config.RECRUITEE_SLUGS)
    if enabled.get("workable"):
        jobs += fetch_workable(config.WORKABLE_SLUGS)
    if enabled.get("adzuna"):
        jobs += fetch_adzuna()
    if enabled.get("jsearch"):
        jobs += fetch_jsearch()
    print(f"[sources] fetched {len(jobs)} raw postings across enabled sources.")
    return jobs
