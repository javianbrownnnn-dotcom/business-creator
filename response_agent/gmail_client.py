"""
Read-only Gmail access over IMAP (Gmail App Password).

GUARDRAIL: This module NEVER sends, deletes, archives, or modifies messages.
The ONLY write it performs is adding the Gmail label `JobTracker/Logged`
(via IMAP X-GM-LABELS), so handled mail is never reprocessed and you can
eyeball what was captured. Setting an X-GM-LABELS value Gmail doesn't know
auto-creates the label.

Credentials come from env: GMAIL_ADDRESS, GMAIL_APP_PASSWORD.
"""
import email
import imaplib
from email.header import decode_header, make_header

import config

IMAP_HOST = "imap.gmail.com"


def connect(address, app_password):
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    conn.login(address, app_password)
    return conn


def _decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _body_text(msg):
    """Extract a plain-text body (fallback: stripped HTML)."""
    if msg.is_multipart():
        # Prefer text/plain, fall back to text/html.
        plain, html = "", ""
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:  # noqa: BLE001
                continue
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text
        return plain or _strip_html(html)
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            return _strip_html(text)
        return text
    return ""


def _strip_html(text):
    import re
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_recent(conn, lookback_days=None, logged_label=None):
    """
    Return a list of candidate-message dicts NOT already labeled logged:

        {uid, message_id, from_name, from_email, subject, date, body, thread_url}

    Uses Gmail's X-GM-RAW search so we can exclude the label and bound by age
    server-side (cheap, keeps volume tiny).
    """
    lookback_days = lookback_days or config.GMAIL_LOOKBACK_DAYS
    logged_label = logged_label or config.GMAIL_LOGGED_LABEL

    conn.select("INBOX")
    query = f'newer_than:{lookback_days}d -label:{logged_label}'
    typ, data = conn.uid("SEARCH", "X-GM-RAW", f'"{query}"')
    if typ != "OK":
        print("[gmail] search failed")
        return []

    uids = data[0].split()
    messages = []
    for uid in uids:
        typ, fetched = conn.uid("FETCH", uid, "(X-GM-THRID RFC822)")
        if typ != "OK" or not fetched or not fetched[0]:
            continue

        # X-GM-THRID lives in the response metadata line.
        thrid = None
        meta = b""
        for part in fetched:
            if isinstance(part, tuple):
                meta += part[0]
                raw = part[1]
            else:
                meta += part if isinstance(part, bytes) else b""
        import re
        m = re.search(rb"X-GM-THRID (\d+)", meta)
        if m:
            thrid = int(m.group(1))

        msg = email.message_from_bytes(raw)
        from_hdr = _decode(msg.get("From", ""))
        from_email = ""
        if "<" in from_hdr and ">" in from_hdr:
            from_email = from_hdr.split("<", 1)[1].split(">", 1)[0].strip().lower()
        else:
            from_email = from_hdr.strip().lower()
        from_name = from_hdr.split("<", 1)[0].strip().strip('"') if "<" in from_hdr else from_hdr

        thread_url = (
            f"https://mail.google.com/mail/u/0/#all/{format(thrid, 'x')}"
            if thrid else "https://mail.google.com/mail/u/0/#inbox"
        )

        messages.append({
            "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
            "message_id": _decode(msg.get("Message-ID", "")),
            "from_name": from_name,
            "from_email": from_email,
            "subject": _decode(msg.get("Subject", "")),
            "date": _decode(msg.get("Date", "")),
            "body": _body_text(msg),
            "thread_url": thread_url,
        })

    print(f"[gmail] {len(messages)} candidate message(s) since {lookback_days}d "
          f"(excluding already-logged).")
    return messages


def apply_logged_label(conn, uid, logged_label=None):
    """Add the JobTracker/Logged Gmail label to a message (creates if missing)."""
    logged_label = logged_label or config.GMAIL_LOGGED_LABEL
    if isinstance(uid, str):
        uid = uid.encode()
    typ, _ = conn.uid("STORE", uid, "+X-GM-LABELS", f'"{logged_label}"')
    return typ == "OK"
