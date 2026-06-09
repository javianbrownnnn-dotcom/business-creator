"""
SQLite storage for seen-jobs and de-duplication (stdlib sqlite3 only).

Each record:
  id (sha256 of company+title+url), title, company, location, remote,
  posted_date, source, apply_url, fit_score, first_seen_date.

In GitHub Actions the DB is committed back to the repo each run so that
de-dup persists across cloud runs (see README / workflow).
"""
import hashlib
import os
import sqlite3
from datetime import date


def job_id(company, title, apply_url):
    """Stable id for a posting — used as the primary key and dedup token."""
    raw = f"{(company or '').strip().lower()}|{(title or '').strip().lower()}|{(apply_url or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id              TEXT PRIMARY KEY,
            title           TEXT,
            company         TEXT,
            location        TEXT,
            remote          INTEGER,
            posted_date     TEXT,
            source          TEXT,
            apply_url       TEXT,
            fit_score       INTEGER,
            first_seen_date TEXT
        )
        """
    )
    conn.commit()


def already_seen(conn, jid):
    cur = conn.execute("SELECT 1 FROM jobs WHERE id = ? LIMIT 1", (jid,))
    return cur.fetchone() is not None


def insert_job(conn, jid, record):
    """Insert a scored, normalized record. Idempotent (INSERT OR IGNORE)."""
    conn.execute(
        """
        INSERT OR IGNORE INTO jobs
            (id, title, company, location, remote, posted_date,
             source, apply_url, fit_score, first_seen_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            jid,
            record.get("title"),
            record.get("company"),
            record.get("location"),
            1 if record.get("remote") else 0,
            record.get("posted_date"),
            record.get("source"),
            record.get("apply_url"),
            record.get("fit_score"),
            date.today().isoformat(),
        ),
    )
    conn.commit()
