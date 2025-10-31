from __future__ import annotations

import json
import os
from email.utils import parseaddr
from typing import Iterable, Optional

try:
    import requests  # type: ignore
except Exception:
    requests = None  # Fallback if not installed; caller should handle

from flask import current_app
from app.extensions import mail


def _parse_sender(default_sender: str) -> tuple[str, str]:
    name, addr = parseaddr(default_sender)
    if not addr:
        # fallback
        return ("PiyuGuide", default_sender)
    return (name or "PiyuGuide", addr)


def send_email_with_fallback(subject: str,
                             recipients: Iterable[str],
                             html: Optional[str] = None,
                             body: Optional[str] = None) -> None:
    """
    Try SMTP via Flask-Mail first; if it fails or times out and BREVO_API_KEY is set,
    fall back to Brevo HTTP API v3.
    """
    # 1) Try SMTP
    try:
        from flask_mail import Message  # type: ignore
        msg = Message(subject=subject, recipients=list(recipients))
        if html:
            msg.html = html
        if body and not html:
            msg.body = body
        mail.send(msg)
        return
    except Exception as smtp_exc:
        # Only fallback if API key is configured
        try:
            current_app.logger.exception("SMTP send failed; evaluating Brevo API fallback")
        except Exception:
            pass
        api_key = current_app.config.get('BREVO_API_KEY') or os.getenv('BREVO_API_KEY')
        if not api_key:
            raise smtp_exc

    # 2) Fallback: Brevo HTTP API
    if requests is None:
        raise RuntimeError("requests is required for Brevo HTTP API fallback. Install 'requests' in your environment.")

    api_url = current_app.config.get('BREVO_API_URL', 'https://api.brevo.com/v3/smtp/email')
    default_sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'PiyuGuide <no-reply@piyuguide.live>')
    sender_name, sender_email = _parse_sender(default_sender)

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": r} for r in recipients],
        "subject": subject,
    }
    if html:
        payload["htmlContent"] = html
    if body and not html:
        payload["textContent"] = body

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": current_app.config.get('BREVO_API_KEY') or os.getenv('BREVO_API_KEY'),
    }

    try:
        resp = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=15)
    except Exception as api_exc:
        try:
            current_app.logger.exception("Brevo API HTTP request failed")
        except Exception:
            pass
        raise
    if resp.status_code >= 300:
        try:
            current_app.logger.error(
                "Brevo API send failed: status=%s body=%s", resp.status_code, resp.text[:500]
            )
        except Exception:
            pass
        raise RuntimeError(f"Brevo API send failed: {resp.status_code} {resp.text}")
