"""
Tamper-proof QR codes.

A QR encodes  TX1:<ticket code>:<signature>
where the signature is an HMAC of the code using a key unique to the event.
Gate scanners (Phase 6) download only the keys for the events they scan, so
they can reject forged QR codes even while offline, and a leaked key only
affects one event. Transferring a ticket issues a new code, so the old QR
stops working.
"""

import base64
import hashlib
import hmac

from django.conf import settings

PREFIX = "TX1"


def _master_key() -> bytes:
    return (getattr(settings, "TICKET_SIGNING_KEY", "") or settings.SECRET_KEY).encode()


def event_key(event_id: int) -> bytes:
    return hmac.new(_master_key(), f"event-key:{event_id}".encode(), hashlib.sha256).digest()


def event_key_b64(event_id: int) -> str:
    """For handing to scanner devices."""
    return base64.urlsafe_b64encode(event_key(event_id)).decode()


def sign_code(event_id: int, code: str) -> str:
    digest = hmac.new(event_key(event_id), code.encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode()[:12]


def qr_payload(ticket) -> str:
    return f"{PREFIX}:{ticket.code}:{sign_code(ticket.event_id, ticket.code)}"


def parse_payload(payload: str, event_id: int) -> str | None:
    """Return the ticket code if `payload` is a genuine QR for `event_id`, else None.

    Also accepts a bare ticket code typed in by hand (looked up server-side).
    """
    payload = (payload or "").strip()
    parts = payload.split(":")
    if len(parts) == 3 and parts[0] == PREFIX:
        _, code, sig = parts
        if hmac.compare_digest(sig, sign_code(event_id, code)):
            return code
        return None
    if len(parts) == 1 and 8 <= len(payload) <= 12 and payload.isalnum():
        return payload.upper()
    return None
