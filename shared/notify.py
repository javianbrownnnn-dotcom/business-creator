"""
Phone push notifications.

Primary: ntfy (https://ntfy.sh) — zero-setup, just subscribe to a topic in the
ntfy mobile app. The topic comes from the NTFY_TOPIC env var.

Email-to-self (Gmail SMTP) is implemented below and powers Agent 1's daily lead
digest. Telegram is left as a clean, commented stub.
"""
import os
import requests

_TIMEOUT = 15


def send_ntfy(message, title=None, click_url=None, tags=None, topic=None):
    """
    Send a push via ntfy. Returns True on success, False on any failure
    (failures are logged, never raised — a missed push must not crash a run).

    tags: list of ntfy emoji shortcodes, e.g. ["briefcase"], ["email"].
    """
    topic = topic or os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[notify] NTFY_TOPIC not set — skipping push notification.")
        return False

    # Be forgiving about the secret's format: accept a bare topic, a full
    # https://ntfy.sh/<topic> URL, or anything with stray slashes/whitespace.
    topic = topic.strip().strip("/").split("/")[-1]
    if not topic:
        print("[notify] NTFY_TOPIC looks empty after parsing — skipping push.")
        return False

    headers = {}
    if title:
        headers["Title"] = title
    if click_url:
        headers["Click"] = click_url
    if tags:
        headers["Tags"] = ",".join(tags)

    try:
        resp = requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort notifier
        print(f"[notify] ntfy push failed: {exc}")
        return False


# -----------------------------------------------------------------------------
# STUB: Telegram bot notifier
# -----------------------------------------------------------------------------
# To use:
#   1. Create a bot via @BotFather, get TELEGRAM_BOT_TOKEN.
#   2. Get your chat id (message the bot, then read getUpdates).
#   3. Set env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and finish this fn.
#
# def send_telegram(message, click_url=None):
#     token = os.environ.get("TELEGRAM_BOT_TOKEN")
#     chat_id = os.environ.get("TELEGRAM_CHAT_ID")
#     if not (token and chat_id):
#         print("[notify] Telegram not configured — skipping.")
#         return False
#     text = message + (f"\n{click_url}" if click_url else "")
#     resp = requests.post(
#         f"https://api.telegram.org/bot{token}/sendMessage",
#         json={"chat_id": chat_id, "text": text},
#         timeout=_TIMEOUT,
#     )
#     return resp.ok


# -----------------------------------------------------------------------------
# Email-to-self notifier (Gmail SMTP) — used for the daily lead digest.
# -----------------------------------------------------------------------------
# Reuses the SAME Gmail credentials Agent 2 already uses (GMAIL_ADDRESS +
# GMAIL_APP_PASSWORD) — a Gmail App Password works for SMTP send as well as IMAP
# read. No new secret needed. Sends to EMAIL_TO if set, else back to yourself.
def send_email_self(subject, text_body, html_body=None, to_addr=None):
    """Send an email via Gmail SMTP. Returns True/False; never raises."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    user = os.environ.get("GMAIL_ADDRESS")
    pwd = os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pwd):
        print("[notify] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set — skipping email.")
        return False
    to_addr = to_addr or os.environ.get("EMAIL_TO") or user

    try:
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(text_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_addr

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(user, pwd)
            s.sendmail(user, [to_addr], msg.as_string())
        print(f"[notify] emailed digest to {to_addr}")
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort notifier
        print(f"[notify] email send failed: {exc}")
        return False
