"""Phone number helpers. Numbers are stored in E.164 format, e.g. +233241234567."""

import phonenumbers

DEFAULT_REGION = "GH"


class InvalidPhoneNumber(ValueError):
    pass


def normalize_phone(raw: str, region: str = DEFAULT_REGION) -> str:
    """
    Accepts local ("024 123 4567") or international ("+233241234567",
    "233241234567") input and returns E.164. Raises InvalidPhoneNumber.
    """
    raw = (raw or "").strip()
    if not raw:
        raise InvalidPhoneNumber("Phone number is required.")
    if raw.startswith("233") and not raw.startswith("+"):
        raw = "+" + raw
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber("Enter a valid phone number.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber("Enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def looks_like_phone(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and "@" not in value and any(c.isdigit() for c in value)


def mask_phone(e164: str) -> str:
    """+233241234567 -> +233 24 *** 4567"""
    if len(e164) < 8:
        return e164
    return f"{e164[:4]} {e164[4:6]} *** {e164[-4:]}"
