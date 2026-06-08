"""
Agent 2 runner — application-response tracker.

Flow:  fetch new mail (IMAP, read-only)
       -> pre-filter (cheap, no LLM)
       -> classify+extract (Claude Haiku)
       -> dedupe against Notion
       -> write row to 'Application Responses' Notion DB
       -> ntfy push
       -> apply Gmail label JobTracker/Logged (only write to mailbox)

Run locally:   python -m response_agent.main
Runs in CI via .github/workflows/response-agent.yml (hourly).

GUARDRAIL: read-only on email except the one label; when unsure, do NOT log.
"""
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import config
from shared import notify, notion
from response_agent import classify, gmail_client, prefilter

# Notion 'Response Type' select options differ slightly from the model's enum.
_RESPONSE_TYPE_MAP = {
    "Interview request": "Interview request",
    "Assessment": "Assessment / task",
    "Auto-acknowledgment": "Auto-acknowledgment",
    "Recruiter outreach": "Recruiter outreach",
    "Rejection": "Rejection",
    "Offer": "Offer",
    "Other": "Other",
}


def _email_date_iso(raw_date):
    try:
        dt = parsedate_to_datetime(raw_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).date().isoformat()


def _already_logged(thread_url, company, role):
    """Dedup: existing row with same Email Link, else same Company+Role."""
    try:
        if thread_url:
            rows = notion.query_database(
                config.RESPONSE_NOTION_DATABASE_ID,
                {"property": "Email Link", "url": {"equals": thread_url}},
            )
            if rows:
                return True
        if company and role:
            rows = notion.query_database(
                config.RESPONSE_NOTION_DATABASE_ID,
                {"and": [
                    {"property": "Company", "rich_text": {"equals": company}},
                    {"property": "Role", "rich_text": {"equals": role}},
                ]},
            )
            if rows:
                return True
    except Exception as exc:  # noqa: BLE001
        print(f"[dedup] Notion query failed (treating as not-duplicate): {exc}")
    return False


def _notion_properties(extracted, email_msg, source_domain):
    return {
        "Contact": notion.title(extracted.get("contact_name") or email_msg.get("from_name") or "Unknown"),
        "Company": notion.rich_text(extracted.get("company", "")),
        "Role": notion.rich_text(extracted.get("role", "")),
        "Email": notion.email(extracted.get("contact_email") or email_msg.get("from_email", "")),
        "Response Type": notion.select(_RESPONSE_TYPE_MAP.get(extracted.get("response_type"), "Other")),
        "Status": notion.select("New"),
        "Date Received": notion.date(_email_date_iso(email_msg.get("date", ""))),
        "Email Link": notion.url(email_msg.get("thread_url")),
        "Source": notion.rich_text(source_domain),
        "Next Step": notion.rich_text(extracted.get("suggested_next_step", "")),
        "Notes": notion.rich_text(extracted.get("one_line_summary", "")),
    }


def run():
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not (address and app_password):
        print("[run] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set — aborting.")
        return

    conn = gmail_client.connect(address, app_password)
    try:
        messages = gmail_client.fetch_recent(conn)

        logged = 0
        for msg in messages:
            cand, reason = prefilter.is_candidate(msg)
            if not cand:
                # Debug line so filters can be tuned (per guardrails).
                print(f"[prefilter] DROP «{msg.get('subject','')[:60]}» — {reason}")
                continue
            print(f"[prefilter] KEEP «{msg.get('subject','')[:60]}» — {reason}")

            extracted = classify.classify(msg)
            if extracted is None:
                print(f"[classify] skipped (no result): {msg.get('subject','')[:60]}")
                continue
            if not extracted["is_application_response"]:
                print(f"[classify] NOT a response (leaning out): {msg.get('subject','')[:60]}")
                # Still mark logged so we don't re-pay to classify it next hour.
                gmail_client.apply_logged_label(conn, msg["uid"])
                continue

            domain = msg.get("from_email", "").split("@", 1)[-1]
            if _already_logged(msg.get("thread_url"), extracted.get("company"), extracted.get("role")):
                print(f"[dedup] already logged: {extracted.get('company')} / {extracted.get('role')}")
                gmail_client.apply_logged_label(conn, msg["uid"])
                continue

            # Write to Notion.
            try:
                notion.create_page(
                    config.RESPONSE_NOTION_DATABASE_ID,
                    _notion_properties(extracted, msg, domain),
                )
                logged += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[notion] create failed: {exc}")
                continue  # don't label as logged if we failed to persist

            # Notify.
            company = extracted.get("company") or "Unknown company"
            role = extracted.get("role") or "a role"
            notify.send_ntfy(
                f"{extracted['response_type']}: {company} — {role}\n"
                f"{extracted.get('one_line_summary','')}",
                title="Application Response",
                click_url=msg.get("thread_url"),
                tags=["email"],
            )

            # Mark processed (the only mailbox write).
            gmail_client.apply_logged_label(conn, msg["uid"])

        print(f"[run] done. logged {logged} response(s) this run.")
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    run()
