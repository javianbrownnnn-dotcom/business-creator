"""
Lightweight preference learning from your Notion board.

Each run this reads which roles you SKIPPED (Skip checkbox or Status=Skipping)
and which you APPLIED to (Applied checkbox or Status=Applied), and derives small,
CAPPED score adjustments so future listings drift toward what you act on and away
from what you skip. It's transparent and bounded — only nudges ranking, never a
hard block — so it can't run away or hide good roles. Learns more as you skip
more. Persisted to data/learned_prefs.json (committed by CI across runs).
"""
import json
import os
import re
from collections import Counter
from datetime import date

import config


def _text(prop, kind):
    return "".join(t.get("plain_text", "") for t in (prop.get(kind) or []))


def _row(page):
    """Extract (title, company, function, skipped, applied) from a Notion page."""
    title = company = function = status = ""
    skipped = applied = False
    for name, p in page.get("properties", {}).items():
        t = p.get("type")
        if t == "title":
            title = _text(p, "title")
        elif name.lower() == "company" and t == "rich_text":
            company = _text(p, "rich_text")
        elif name == "Function" and t == "select" and p.get("select"):
            function = p["select"]["name"]
        elif name == "Skip" and t == "checkbox":
            skipped = bool(p.get("checkbox"))
        elif name == "Applied" and t == "checkbox":
            applied = bool(p.get("checkbox"))
        elif name == "Status" and t == "select" and p.get("select"):
            status = p["select"]["name"]
    if status == "Skipping":
        skipped = True
    if status == "Applied":
        applied = True
    return title, company, function, skipped, applied


def _tokens(title):
    words = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).split()
    return [w for w in words if len(w) >= 3 and w not in config.LEARN_STOPWORDS]


def _clamp(v, cap):
    return max(-cap, min(cap, v))


def learn(rows):
    """Build + persist preference weights from board rows. Returns the prefs dict."""
    skip_titles, apply_titles = [], []
    skip_funcs, apply_funcs = Counter(), Counter()
    skip_cos, apply_cos = Counter(), Counter()
    n_skip = n_apply = 0

    for page in rows:
        title, company, function, skipped, applied = _row(page)
        if applied:                      # applied wins over skip if both set
            n_apply += 1
            apply_titles += _tokens(title)
            if function:
                apply_funcs[function] += 1
            if company:
                apply_cos[company.strip().lower()] += 1
        elif skipped:
            n_skip += 1
            skip_titles += _tokens(title)
            if function:
                skip_funcs[function] += 1
            if company:
                skip_cos[company.strip().lower()] += 1

    st, at = Counter(skip_titles), Counter(apply_titles)
    tokens = {}
    for tok in set(st) | set(at):
        net = at[tok] - st[tok]
        if (st[tok] + at[tok]) >= config.LEARN_MIN_OCCURRENCES and net != 0:
            tokens[tok] = _clamp(net * config.LEARN_TOKEN_STEP, config.LEARN_TOKEN_CAP)

    funcs = {}
    for fn in set(skip_funcs) | set(apply_funcs):
        net = apply_funcs[fn] - skip_funcs[fn]
        if net != 0:
            funcs[fn] = _clamp(net * config.LEARN_FUNCTION_STEP, config.LEARN_FUNCTION_CAP)

    # Companies you skipped and never applied to → down-rank future roles there.
    companies = {}
    for co, n in skip_cos.items():
        if co not in apply_cos:
            companies[co] = -min(config.LEARN_COMPANY_CAP, n * config.LEARN_COMPANY_STEP)

    prefs = {
        "tokens": tokens, "functions": funcs, "companies": companies,
        "n_skipped": n_skip, "n_applied": n_apply,
        "generated": date.today().isoformat(),
    }
    _save(prefs)
    print(f"[learning] from {n_skip} skipped + {n_apply} applied → "
          f"{len(tokens)} keyword, {len(funcs)} function, {len(companies)} company signal(s).")
    return prefs


def _save(prefs):
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(config.LEARNED_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2, sort_keys=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[learning] could not save prefs: {exc}")


def load():
    try:
        with open(config.LEARNED_PREFS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001
        return {}


def adjustment(job, prefs):
    """Bounded fit-score delta for a candidate job, from learned prefs."""
    if not prefs:
        return 0
    delta = 0
    title_tokens = set(_tokens(job.get("title", "")))
    for tok, w in prefs.get("tokens", {}).items():
        if tok in title_tokens:
            delta += w
    fn = job.get("_function")
    if fn:
        delta += prefs.get("functions", {}).get(fn, 0)
    co = (job.get("company") or "").strip().lower()
    delta += prefs.get("companies", {}).get(co, 0)
    return _clamp(int(delta), config.LEARN_ADJ_CLAMP)
