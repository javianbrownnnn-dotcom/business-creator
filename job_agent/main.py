"""
Agent 1 runner — daily marketing-job discovery.

Flow:  fetch -> filter -> score -> dedupe(SQLite) -> push to Notion
       -> write dated markdown digest -> ntfy push.

Run locally:   python -m job_agent.main
Runs in CI via .github/workflows/job-agent.yml (daily).
"""
import os
from datetime import date

import config
from shared import notify, notion
from job_agent import filters, scoring, sources, storage


def _notion_properties(job):
    """Build the exact property map for the 'Job Leads' Notion database."""
    return {
        "Job Title": notion.title(job["title"]),
        "Company": notion.rich_text(job.get("company", "")),
        "Location": notion.rich_text(job.get("location", "") or ("Remote" if job.get("remote") else "")),
        "Remote": notion.checkbox(job.get("remote")),
        "Fit Score": notion.number(job.get("fit_score", 0)),
        "Function": notion.select(scoring.classify_function(job)),
        "Seniority": notion.select(scoring.classify_seniority(job)),
        "Source": notion.rich_text(job.get("source", "")),
        "Posted Date": notion.date(job.get("posted_date")),
        "Apply": notion.url(job.get("apply_url")),
        "Status": notion.select("New"),
    }


def _write_digest(rows):
    """Write a dated markdown digest to data/digests/ as a backup/log."""
    os.makedirs(config.DIGEST_DIR, exist_ok=True)
    today = date.today().isoformat()
    path = os.path.join(config.DIGEST_DIR, f"{today}.md")
    lines = [f"# Marketing Job Digest — {today}", ""]
    if not rows:
        lines.append("_No new roles passed the filter today._")
    else:
        lines.append(f"**{len(rows)} new role(s)**, sorted by fit score.\n")
        for j in rows:
            remote = " · 🌐 Remote" if j.get("remote") else ""
            lines.append(
                f"- **[{j['fit_score']}]** [{j['title']}]({j.get('apply_url','')}) "
                f"— {j.get('company','')} · {j.get('location','') or 'N/A'}{remote} "
                f"· _{j.get('source','')}_ · {j.get('posted_date') or 'date n/a'}"
            )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[digest] wrote {path}")
    return path


def _email_bodies(rows):
    """Build (subject, text_body, html_body) for the daily lead email."""
    today = date.today().isoformat()
    n = len(rows)
    if n:
        subject = f"📋 {n} new marketing lead{'s' if n != 1 else ''} — {today}"
    else:
        subject = f"No new marketing leads today — {today}"

    # Plain-text fallback.
    text_lines = [f"{n} new marketing lead(s) added to your Job Leads board today.", ""]
    for j in rows:
        loc = j.get("location") or ("Remote" if j.get("remote") else "N/A")
        text_lines.append(
            f"[{j['fit_score']}] {j['title']} — {j.get('company','')} "
            f"({loc}) · {j.get('source','')}\n    {j.get('apply_url','')}"
        )
    if not rows:
        text_lines.append("Nothing new passed the filter today. The run executed "
                           "fine — this just means no fresh, on-profile roles appeared.")
    text_body = "\n".join(text_lines)

    # HTML version with clickable apply links.
    notion_url = f"https://www.notion.so/{config.JOB_NOTION_DATABASE_ID.replace('-', '')}"
    html = [f"<h2>{n} new marketing lead{'s' if n != 1 else ''} — {today}</h2>"]
    if rows:
        html.append("<p>Sorted by fit score. Newest leads are in your "
                    f'<a href="{notion_url}">Job Leads board</a>.</p><ul>')
        for j in rows:
            loc = j.get("location") or ("Remote" if j.get("remote") else "N/A")
            html.append(
                f'<li><b>[{j["fit_score"]}]</b> '
                f'<a href="{j.get("apply_url","")}">{j["title"]}</a> — '
                f'{j.get("company","")} · {loc} · <i>{j.get("source","")}</i></li>'
            )
        html.append("</ul>")
    else:
        html.append("<p>Nothing new passed the filter today. The run executed "
                    "fine — no fresh, on-profile roles appeared since yesterday.</p>")
    return subject, text_body, "\n".join(html)


def _email_already_sent_today():
    """True if today's daily email has already gone out (across cron retries)."""
    try:
        with open(config.LAST_EMAIL_DATE_PATH, encoding="utf-8") as f:
            return f.read().strip() == date.today().isoformat()
    except FileNotFoundError:
        return False
    except Exception:  # noqa: BLE001
        return False


def _mark_email_sent_today():
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(config.LAST_EMAIL_DATE_PATH, "w", encoding="utf-8") as f:
            f.write(date.today().isoformat())
    except Exception as exc:  # noqa: BLE001
        print(f"[email] could not record send-date: {exc}")


def run():
    conn = storage.connect(config.JOBS_DB_PATH)

    raw = sources.fetch_all()

    # Filter + score, dropping anything already seen.
    kept = []
    seen_ids = set()
    dropped = 0
    for job in raw:
        if not job.get("title") or not job.get("apply_url"):
            continue
        ok, reason = filters.keep(job)
        if not ok:
            dropped += 1
            continue
        jid = storage.job_id(job.get("company"), job.get("title"), job.get("apply_url"))
        if jid in seen_ids or storage.already_seen(conn, jid):
            continue
        # Drop excluded Function buckets (e.g. "General Marketing") per config.
        if scoring.classify_function(job) in config.EXCLUDED_FUNCTIONS:
            dropped += 1
            continue
        seen_ids.add(jid)
        job["fit_score"] = scoring.score(job)
        job["_id"] = jid
        kept.append(job)

    kept.sort(key=lambda j: j["fit_score"], reverse=True)
    print(f"[run] {len(kept)} new role(s) kept, {dropped} filtered out.")

    # Push to Notion + persist to SQLite.
    pushed = 0
    notion_ok = bool(os.environ.get("NOTION_TOKEN"))
    for job in kept:
        if notion_ok:
            try:
                props = notion.adapt_properties(
                    config.JOB_NOTION_DATABASE_ID, _notion_properties(job)
                )
                notion.create_page(config.JOB_NOTION_DATABASE_ID, props)
                pushed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[notion] failed for '{job['title']}': {exc}")
        storage.insert_job(conn, job["_id"], job)

    if not notion_ok:
        print("[notion] NOTION_TOKEN not set — skipped Notion, still wrote digest + DB.")

    # Backup digest + notifications.
    _write_digest(kept)

    # Daily email digest. Multiple morning cron attempts run for reliability, so
    # guard to one email/day: always email when NEW leads are found; otherwise
    # send the "0 new" heartbeat only if we haven't already emailed today.
    if config.EMAIL_DIGEST_ENABLED:
        should_email = bool(kept) or (
            config.EMAIL_SEND_WHEN_ZERO and not _email_already_sent_today()
        )
        if should_email:
            subject, text_body, html_body = _email_bodies(kept)
            if notify.send_email_self(subject, text_body, html_body=html_body):
                _mark_email_sent_today()

    if kept:
        top = kept[0]
        msg = (f"{len(kept)} new marketing roles today — top pick: "
               f"{top['title']} @ {top.get('company','')} (fit {top['fit_score']})")
        notify.send_ntfy(
            msg,
            title="Daily Marketing Jobs",
            click_url=f"https://www.notion.so/{config.JOB_NOTION_DATABASE_ID.replace('-', '')}",
            tags=["briefcase"],
        )

    conn.close()
    print(f"[run] done. pushed {pushed} row(s) to Notion.")


if __name__ == "__main__":
    run()
