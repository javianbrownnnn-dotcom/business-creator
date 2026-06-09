"""
Phone push notifications.

Primary: ntfy (https://ntfy.sh) — zero-setup, just subscribe to a topic in the
ntfy mobile app. The topic comes from the NTFY_TOPIC env var.

Alternate notifiers (Telegram bot, email-to-self) are left as clean, commented
stubs — flip RESPONSE_NOTIFIER in config.py and fill in the stub to switch.
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
# STUB: Email-to-self notifier (SMTP)
# -----------------------------------------------------------------------------
# To use: set SMTP_HOST / SMTP_USER / SMTP_PASS and finish this function.
#
# import smtplib
# from email.mime.text import MIMEText
#
# def send_email_self(subject, body):
#     host = os.environ.get("SMTP_HOST")
#     user = os.environ.get("SMTP_USER")
#     pwd = os.environ.get("SMTP_PASS")
#     if not (host and user and pwd):
#         print("[notify] SMTP not configured — skipping.")
#         return False
#     msg = MIMEText(body)
#     msg["Subject"] = subject
#     msg["From"] = user
#     msg["To"] = user
#     with smtplib.SMTP_SSL(host, 465) as s:
#         s.login(user, pwd)
#         s.send_message(msg)
#     return True
