"""
Biweekly Job Leads cleanup — runs every other Friday.

Archives (to Notion's trash, recoverable for 30 days) any Job Leads row that:
  - has its "Applied" checkbox ticked, OR
  - was added more than CLEANUP_STALE_DAYS ago and was never applied to.

The GitHub workflow fires every Friday; this script self-gates to alternating
weeks via ISO-week parity (config.CLEANUP_WEEK_PARITY), so it only acts every
OTHER Friday. Archived rows stay in the SQLite dedup DB, so the daily agent
never re-adds them. A short summary is emailed + pushed.

Run locally:   python -m job_agent.cleanup
"""
import datetime as dt
import os

import config
from shared import notify, notion


def _page_title(page):
    try:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title" and prop.get("title"):
                return "".join(t.get("plain_text", "") for t in prop["title"])
    except Exception:  # noqa: BLE001
        pass
    return "(untitled)"


def run():
    today = dt.date.today()
    week = today.isocalendar()[1]
    if week % 2 != config.CLEANUP_WEEK_PARITY:
        print(f"[cleanup] ISO week {week} (parity {week % 2}) != target "
              f"{config.CLEANUP_WEEK_PARITY} — not a cleanup week, skipping.")
        return

    if not os.environ.get("NOTION_TOKEN"):
        print("[cleanup] NOTION_TOKEN not set — aborting.")
        return

    cutoff = (today - dt.timedelta(days=config.CLEANUP_STALE_DAYS)).isoformat()
    filt = {
        "or": [
            {"property": "Applied", "checkbox": {"equals": True}},
            {"and": [
                {"property": "Applied", "checkbox": {"equals": False}},
                {"timestamp": "created_time", "created_time": {"on_or_before": cutoff}},
            ]},
        ]
    }

    try:
        rows = notion.query_database(config.JOB_NOTION_DATABASE_ID, filt)
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] query failed: {exc}")
        return

    print(f"[cleanup] {len(rows)} row(s) match (Applied, or stale > "
          f"{config.CLEANUP_STALE_DAYS}d and never applied).")

    archived = 0
    for page in rows:
        try:
            notion.archive_page(page["id"])
            archived += 1
            print(f"[cleanup] archived: {_page_title(page)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] failed to archive {page.get('id')}: {exc}")

    print(f"[cleanup] done. archived {archived} row(s).")

    # Summary email + push (best-effort).
    if config.EMAIL_DIGEST_ENABLED:
        subject = f"🧹 Job Leads cleanup — archived {archived} lead(s)"
        body = (
            f"Your biweekly cleanup archived {archived} lead(s) from the Job Leads "
            f"board:\n  • everything marked Applied\n  • leads older than "
            f"{config.CLEANUP_STALE_DAYS} days you never applied to\n\n"
            f"They're in Notion's trash and recoverable for 30 days if you need them."
        )
        notify.send_email_self(subject, body)
    notify.send_ntfy(
        f"Archived {archived} finished/stale lead(s) from your board.",
        title="Job Leads Cleanup",
        tags=["broom"],
    )


if __name__ == "__main__":
    run()
