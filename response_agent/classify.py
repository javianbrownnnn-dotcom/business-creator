"""
LLM classification/extraction for Agent 2, using Claude Haiku 4.5.

Haiku is cheap and strong at extraction; the pre-filter keeps volume tiny.
We force JSON-only output and parse defensively.

Returns a dict:
  is_application_response (bool), company, role, contact_name, contact_email,
  response_type, one_line_summary, suggested_next_step
Returns None on hard failure (so the runner can log + skip safely).
"""
import json
import os
import re

import config

_RESPONSE_TYPES = [
    "Interview request", "Assessment", "Auto-acknowledgment",
    "Recruiter outreach", "Rejection", "Offer", "Other",
]

_SYSTEM = (
    "You classify whether an email is a genuine response to a job the user "
    "applied to, and extract structured fields. You output JSON ONLY — no "
    "prose, no markdown fences. Be conservative: if it is a job-board alert, "
    "newsletter, marketing blast, or not actually about the user's own job "
    "application, set is_application_response to false."
)

_PROMPT_TEMPLATE = """Analyze this email and return ONLY a JSON object with EXACTLY these keys:

{{
  "is_application_response": true|false,
  "company": "string (employer name, best guess, or empty)",
  "role": "string (job title if mentioned, else empty)",
  "contact_name": "string (person who wrote it, else empty)",
  "contact_email": "string (their email, else empty)",
  "response_type": "one of: Interview request | Assessment | Auto-acknowledgment | Recruiter outreach | Rejection | Offer | Other",
  "one_line_summary": "string (<= 20 words)",
  "suggested_next_step": "string (concrete next action for the applicant)"
}}

Rules:
- is_application_response is true ONLY for a real reply about the user's own
  application or direct recruiter outreach about a specific role.
- "Assessment" covers take-homes / coding challenges / tasks.
- "Auto-acknowledgment" = automated "we received your application".
- If unsure whether it's a genuine response, prefer false.

EMAIL
From: {from_name} <{from_email}>
Subject: {subject}
Date: {date}
Body (truncated):
{body}
"""


def _extract_json(text):
    text = text.strip()
    # Strip accidental code fences.
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Grab the first {...} block as a fallback.
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def classify(email_msg):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[classify] ANTHROPIC_API_KEY not set — cannot classify.")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        print("[classify] `anthropic` package not installed (pip install anthropic).")
        return None

    client = Anthropic(api_key=api_key)
    prompt = _PROMPT_TEMPLATE.format(
        from_name=email_msg.get("from_name", ""),
        from_email=email_msg.get("from_email", ""),
        subject=email_msg.get("subject", ""),
        date=email_msg.get("date", ""),
        body=(email_msg.get("body", "") or "")[:6000],  # keep tokens small
    )

    try:
        resp = client.messages.create(
            model=config.RESPONSE_MODEL,
            max_tokens=500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[classify] Anthropic call failed: {exc}")
        return None

    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    parsed = _extract_json(text)
    if parsed is None:
        print(f"[classify] could not parse JSON from model output: {text[:200]!r}")
        return None

    # Normalize / validate fields defensively.
    rtype = parsed.get("response_type", "Other")
    if rtype not in _RESPONSE_TYPES:
        rtype = "Other"
    return {
        "is_application_response": bool(parsed.get("is_application_response")),
        "company": (parsed.get("company") or "").strip(),
        "role": (parsed.get("role") or "").strip(),
        "contact_name": (parsed.get("contact_name") or "").strip(),
        "contact_email": (parsed.get("contact_email") or "").strip(),
        "response_type": rtype,
        "one_line_summary": (parsed.get("one_line_summary") or "").strip(),
        "suggested_next_step": (parsed.get("suggested_next_step") or "").strip(),
    }
