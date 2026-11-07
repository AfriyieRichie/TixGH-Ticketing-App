"""
Outbound SMS. Pick a provider with the SMS_BACKEND setting:

    console  - prints messages to the terminal (development)
    arkesel  - https://arkesel.com  (needs ARKESEL_API_KEY)
    hubtel   - https://hubtel.com   (needs HUBTEL_CLIENT_ID / HUBTEL_CLIENT_SECRET)

Callers should use `send_sms()` and never talk to a provider directly, so the
provider can be swapped without touching business code.
"""

import logging

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15


class SMSError(Exception):
    pass


class ConsoleSMSBackend:
    def send(self, to: str, message: str) -> None:
        print(f"\n[SMS] to={to} from={settings.SMS_SENDER_ID}\n{message}\n", flush=True)


class ArkeselSMSBackend:
    url = "https://sms.arkesel.com/api/v2/sms/send"

    def send(self, to: str, message: str) -> None:
        resp = requests.post(
            self.url,
            headers={"api-key": settings.ARKESEL_API_KEY},
            json={
                "sender": settings.SMS_SENDER_ID,
                "message": message,
                "recipients": [to.lstrip("+")],
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise SMSError(f"Arkesel error {resp.status_code}: {resp.text[:200]}")


class HubtelSMSBackend:
    url = "https://smsc.hubtel.com/v1/messages/send"

    def send(self, to: str, message: str) -> None:
        resp = requests.get(
            self.url,
            params={
                "clientid": settings.HUBTEL_CLIENT_ID,
                "clientsecret": settings.HUBTEL_CLIENT_SECRET,
                "from": settings.SMS_SENDER_ID,
                "to": to,
                "content": message,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise SMSError(f"Hubtel error {resp.status_code}: {resp.text[:200]}")


_BACKENDS = {
    "console": ConsoleSMSBackend,
    "arkesel": ArkeselSMSBackend,
    "hubtel": HubtelSMSBackend,
}


def get_sms_backend():
    try:
        return _BACKENDS[settings.SMS_BACKEND]()
    except KeyError as exc:
        raise SMSError(f"Unknown SMS_BACKEND '{settings.SMS_BACKEND}'") from exc


def send_sms(to: str, message: str) -> None:
    """Send an SMS to an E.164 number. Raises SMSError on provider failure."""
    try:
        get_sms_backend().send(to, message)
    except requests.RequestException as exc:
        logger.exception("SMS send failed to %s", to)
        raise SMSError("Could not reach SMS provider.") from exc


def send_email(to: str, subject: str, body: str) -> None:
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
