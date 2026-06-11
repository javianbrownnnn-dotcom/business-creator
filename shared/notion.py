"""
Thin Notion REST client (no SDK dependency — just `requests`).

Used by both agents to query a database (for de-dup) and create pages (rows).
Reads the integration token from the NOTION_TOKEN environment variable.

Property-builder helpers at the bottom keep main.py readable and ensure we
always send Notion the exact shape each property type expects.
"""
import os
import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_TIMEOUT = 30


def _headers():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError(
            "NOTION_TOKEN is not set. Add it to your .env (local) or as a "
            "GitHub repository Secret (Actions)."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def query_database(database_id, filter_payload=None, page_size=100):
    """Return all rows (handles pagination). Optional Notion filter object."""
    url = f"{NOTION_API}/databases/{database_id}/query"
    results = []
    payload = {"page_size": page_size}
    if filter_payload:
        payload["filter"] = filter_payload
    while True:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
        if resp.status_code >= 400:
            raise RuntimeError(f"Notion query failed {resp.status_code}: {resp.text}")
        data = resp.json()
        results.extend(data.get("results", []))
        if data.get("has_more") and data.get("next_cursor"):
            payload["start_cursor"] = data["next_cursor"]
        else:
            break
    return results


_schema_cache = {}


def get_schema(database_id, refresh=False):
    """Return {property_name: notion_type} for a database (cached per run)."""
    if not refresh and database_id in _schema_cache:
        return _schema_cache[database_id]
    url = f"{NOTION_API}/databases/{database_id}"
    resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"Notion get_schema failed {resp.status_code}: {resp.text}")
    props = resp.json().get("properties", {})
    schema = {name: meta.get("type") for name, meta in props.items()}
    _schema_cache[database_id] = schema
    return schema


def adapt_properties(database_id, desired):
    """
    Reconcile our intended properties against the database's REAL schema so a
    renamed/re-cased property never sinks the whole write.

    For each desired property: keep it if the name matches exactly, else match
    case-insensitively, else — if exactly one property in the DB has the same
    Notion type — map onto that one (this self-heals e.g. a 'Posted Date' that
    was actually named 'Date Posted'). Otherwise drop it with a debug line.
    """
    schema = get_schema(database_id)
    by_lower = {name.lower(): name for name in schema}
    by_type = {}
    for name, ntype in schema.items():
        by_type.setdefault(ntype, []).append(name)

    out = {}
    for key, value in desired.items():
        vtype = next(iter(value))  # payload key == notion type (date/rich_text/...)
        if key in schema:
            out[key] = value
        elif key.lower() in by_lower:
            out[by_lower[key.lower()]] = value
        else:
            # Fuzzy: a same-typed property whose name contains the key (or vice
            # versa) — handles odd names like 'date:Posted Date:start' for our
            # 'Posted Date', even when another date property (e.g. 'Applied
            # Date') would make the single-type fallback ambiguous.
            same_type = by_type.get(vtype, [])
            fuzzy = [n for n in same_type
                     if key.lower() in n.lower() or n.lower() in key.lower()]
            if len(fuzzy) == 1:
                print(f"[notion] mapped '{key}' -> '{fuzzy[0]}' (fuzzy name match)")
                out[fuzzy[0]] = value
            elif len(same_type) == 1:
                actual = same_type[0]
                print(f"[notion] mapped '{key}' -> '{actual}' (matched by type '{vtype}')")
                out[actual] = value
            else:
                print(f"[notion] skipping '{key}' — no matching property in DB schema")
    return out


def create_page(database_id, properties):
    """Create one row in `database_id` with the given Notion `properties` dict."""
    url = f"{NOTION_API}/pages"
    payload = {"parent": {"database_id": database_id}, "properties": properties}
    resp = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"Notion create_page failed {resp.status_code}: {resp.text}")
    return resp.json()


def archive_page(page_id):
    """Move a page to Notion's trash (recoverable for 30 days). Idempotent."""
    url = f"{NOTION_API}/pages/{page_id}"
    resp = requests.patch(url, headers=_headers(), json={"archived": True}, timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"Notion archive_page failed {resp.status_code}: {resp.text}")
    return resp.json()


# --- Property builders --------------------------------------------------------
# Notion truncates rich_text/title at 2000 chars per block; we clamp defensively.

def title(text):
    return {"title": [{"text": {"content": (text or "")[:2000]}}]}


def rich_text(text):
    return {"rich_text": [{"text": {"content": (text or "")[:2000]}}]}


def number(value):
    return {"number": value}


def checkbox(value):
    return {"checkbox": bool(value)}


def select(name):
    # Passing None clears the select; otherwise Notion creates the option if new.
    return {"select": {"name": name}} if name else {"select": None}


def date(iso_date):
    return {"date": {"start": iso_date}} if iso_date else {"date": None}


def url(value):
    return {"url": value or None}


def email(value):
    return {"email": value or None}
