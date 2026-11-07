"""One-time code issuing and checking."""

import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.messaging import send_email, send_sms
from apps.core.phone import mask_phone, normalize_phone

from .models import OTPCode, OTPPurpose


class OTPError(Exception):
    pass


@dataclass(frozen=True)
class Contact:
    """A normalized email address or phone number."""

    value: str
    channel: str  # "email" | "sms"

    @property
    def is_email(self) -> bool:
        return self.channel == "email"

    @property
    def masked(self) -> str:
        if self.is_email:
            name, _, domain = self.value.partition("@")
            return f"{name[:2]}***@{domain}"
        return mask_phone(self.value)


def parse_contact(identifier: str) -> Contact:
    """Raises InvalidPhoneNumber for bad phone input."""
    identifier = (identifier or "").strip()
    if "@" in identifier:
        return Contact(identifier.lower(), "email")
    return Contact(normalize_phone(identifier), "sms")


_MESSAGES = {
    OTPPurpose.LOGIN: "Your {name} login code is {code}. It expires in {ttl} minutes. "
    "Do not share this code with anyone.",
    OTPPurpose.VERIFY_CONTACT: "Your {name} verification code is {code}. It expires in {ttl} minutes.",
    OTPPurpose.PASSWORD_RESET: "Your {name} password reset code is {code}. It expires in {ttl} "
    "minutes. If you did not request this, ignore this message.",
}


def issue_otp(contact: Contact, purpose: str, deliver: bool = True) -> None:
    """Create a fresh code for `contact` and send it. Older codes are voided."""
    now = timezone.now()
    recent = OTPCode.objects.filter(
        target=contact.value, created_at__gte=now - timedelta(hours=1)
    ).count()
    if recent >= settings.OTP_MAX_PER_HOUR:
        raise OTPError("Too many codes requested. Please try again later.")

    code = "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))
    with transaction.atomic():
        OTPCode.objects.filter(
            target=contact.value, purpose=purpose, consumed_at__isnull=True
        ).update(consumed_at=now)
        OTPCode.objects.create(
            target=contact.value,
            purpose=purpose,
            code_hash=OTPCode.hash_code(code),
            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES),
        )

    if not deliver:
        return
    message = _MESSAGES[purpose].format(
        name=settings.PLATFORM_NAME, code=code, ttl=settings.OTP_TTL_MINUTES
    )
    if contact.is_email:
        send_email(contact.value, f"Your {settings.PLATFORM_NAME} code: {code}", message)
    else:
        send_sms(contact.value, message)


def check_otp(contact: Contact, purpose: str, code: str) -> None:
    """Consume a valid code or raise OTPError."""
    code = (code or "").strip()
    error = None
    # Errors are raised *after* the transaction commits so the failed-attempt
    # counter is persisted (raising inside atomic() would roll it back).
    with transaction.atomic():
        otp = (
            OTPCode.objects.select_for_update()
            .filter(target=contact.value, purpose=purpose, consumed_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if otp is None or otp.is_expired:
            error = "This code has expired. Request a new one."
        elif otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            error = "Too many wrong attempts. Request a new code."
        elif not otp.matches(code):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            error = "Incorrect code."
        else:
            otp.consumed_at = timezone.now()
            otp.save(update_fields=["consumed_at"])
    if error:
        raise OTPError(error)
