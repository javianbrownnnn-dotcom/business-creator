"""
One-off Job Leads purge — remove anything older than 2 weeks, keep the rest.

Archives (to Notion's trash — recoverable for 30 days) EVERY Job Leads row
whose Notion created_time is more than PURGE_OLDER_THAN_DAYS ago, regardless of
whether it was applied to / skipped. Everything newer than the cutoff is kept.

This differs from cleanup.py (biweekly, only never-applied stale rows) and
board_cleanup.py (misfit re-judging): here the ONLY criterion is age on the
board. Run on demand via the purge-old workflow (workflow_dispatch).

Run locally:   python -m job_agent.purge_old
"""
import datetime as dt
import os

import config

from shared import notion

# "Over 2 weeks" = older than 14 days. Overridable via env for a one-off tweak.
PURGE_OLDER_THAN_DAYS = int(os.environ.get("PURGE_OLDER_THAN_DAYS", "14"))


def _page_title(page):
    try:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title" and prop.get("title"):
                return "".join(t.get("plain_text", "") for t in prop["title"])
    except Exception:  # noqa: BLE001
        pass
    return "(untitled)"


def run():
    if not os.environ.get("NOTION_TOKEN"):
        print("[purge] NOTION_TOKEN not set — aborting.")
        return

    # Cutoff is a full timestamp: strictly older than N days from now.
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(days=PURGE_OLDER_THAN_DAYS)).isoformat()
    filt = {"timestamp": "created_time", "created_time": {"before": cutoff}}

    try:
        rows = notion.query_database(config.JOB_NOTION_DATABASE_ID, filt)
    except Exception as exc:  # noqa: BLE001
        print(f"[purge] query failed: {exc}")
        return

    print(f"[purge] {len(rows)} row(s) older than {PURGE_OLDER_THAN_DAYS} days "
          f"(added on/before {cutoff[:10]}) — archiving all of them.")

    archived = 0
    for page in rows:
        try:
            notion.archive_page(page["id"])
            archived += 1
            print(f"[purge] archived: {_page_title(page)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[purge] failed to archive {page.get('id')}: {exc}")

    print(f"[purge] done. archived {archived} row(s); everything newer than "
          f"{PURGE_OLDER_THAN_DAYS} days was kept.")


if __name__ == "__main__":
    run()
