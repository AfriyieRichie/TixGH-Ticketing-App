"""
Send email through Brevo's HTTPS API (port 443).

Free hosting plans (e.g. Render free) block outgoing SMTP ports, so a normal
SMTP backend can't deliver mail there. Configure with:

    EMAIL_BACKEND=apps.core.email_backends.BrevoAPIBackend
    BREVO_API_KEY=xkeysib-...
    DEFAULT_FROM_EMAIL=TixGH <verified-sender@example.com>
"""

import base64
import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_URL = "https://api.brevo.com/v3/smtp/email"


def _address(raw: str) -> dict:
    name, email = parseaddr(raw)
    return {"email": email, "name": name} if name else {"email": email}


class BrevoAPIBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for msg in email_messages:
            try:
                self._send(msg)
                sent += 1
            except Exception:
                logger.exception("Brevo send failed to %s", msg.to)
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, msg):
        payload = {
            "sender": _address(msg.from_email or settings.DEFAULT_FROM_EMAIL),
            "to": [_address(a) for a in msg.to],
            "subject": msg.subject,
            "textContent": msg.body or " ",
        }
        if msg.cc:
            payload["cc"] = [_address(a) for a in msg.cc]
        if msg.bcc:
            payload["bcc"] = [_address(a) for a in msg.bcc]
        if msg.reply_to:
            payload["replyTo"] = _address(msg.reply_to[0])
        for content, mimetype in getattr(msg, "alternatives", []):
            if mimetype == "text/html":
                payload["htmlContent"] = content
        attachments = []
        for att in msg.attachments:
            if isinstance(att, tuple):  # (filename, content, mimetype)
                filename, content = att[0], att[1]
                data = content.encode() if isinstance(content, str) else content
                attachments.append({"name": filename, "content": base64.b64encode(data).decode()})
        if attachments:
            payload["attachment"] = attachments

        resp = requests.post(
            API_URL,
            json=payload,
            headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
            timeout=getattr(settings, "EMAIL_TIMEOUT", None) or 15,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Brevo error {resp.status_code}: {resp.text[:300]}")
