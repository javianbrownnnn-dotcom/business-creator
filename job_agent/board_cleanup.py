"""
One-off / on-demand Job Leads board cleanup.

Re-judges every EXISTING row with the CURRENT pipeline and archives the misfits
(to Notion's trash — recoverable for 30 days). A row is removed if:
  - its Source is RemoteOK (that source was dropped), OR
  - its title fails the seniority gate (senior / director / VP / "manager"
    without a junior qualifier / ...), OR
  - re-classifying its title lands in an off-target Function (General Marketing
    or Other) — i.e. not Email/Lifecycle, Growth, Product Marketing,
    Content/Copywriting, or Paid Ads.

Re-deriving the Function from the title (not trusting the stored value) means
older rows mislabelled before the Growth/function changes are judged correctly.

Run on demand via the board-cleanup workflow (workflow_dispatch).
"""
import os

import config
from shared import notion
from job_agent import filters, scoring

OFF_TARGET_FUNCTIONS = set(config.EXCLUDED_FUNCTIONS) | {"Other"}


def _text(prop, kind):
    return "".join(t.get("plain_text", "") for t in (prop.get(kind) or []))


def _row_fields(page):
    title = source = ""
    for name, p in page.get("properties", {}).items():
        ptype = p.get("type")
        if ptype == "title":
            title = _text(p, "title")
        elif name.lower() == "source" and ptype == "rich_text":
            source = _text(p, "rich_text")
    return title, source


def _removal_reason(title, source):
    if source.strip().lower() == "remoteok":
        return "RemoteOK source"
    ok, reason = filters.passes_seniority({"title": title})
    if not ok:
        return reason
    fn = scoring.classify_function({"title": title, "description": ""})
    if fn in OFF_TARGET_FUNCTIONS:
        return f"off-target function ({fn})"
    return None


def run():
    if not os.environ.get("NOTION_TOKEN"):
        print("[board-cleanup] NOTION_TOKEN not set — aborting.")
        return
    rows = notion.query_database(config.JOB_NOTION_DATABASE_ID)
    print(f"[board-cleanup] {len(rows)} rows on the board.")

    reasons = {}
    removed = 0
    for page in rows:
        title, source = _row_fields(page)
        why = _removal_reason(title, source)
        if not why:
            continue
        try:
            notion.archive_page(page["id"])
            removed += 1
            reasons[why] = reasons.get(why, 0) + 1
            print(f"[board-cleanup] archived: {title[:55]:<55} — {why}")
        except Exception as exc:  # noqa: BLE001
            print(f"[board-cleanup] failed {page.get('id')}: {exc}")

    print(f"[board-cleanup] done. archived {removed}/{len(rows)} rows; kept {len(rows) - removed}.")
    for why, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"[board-cleanup]   {n:>3} × {why}")


if __name__ == "__main__":
    run()
