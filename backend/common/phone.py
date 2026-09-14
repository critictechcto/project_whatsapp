import re

import phonenumbers
from django.conf import settings

_SEPARATORS = re.compile(r"[\s().\-]")


class InvalidPhoneNumber(ValueError):
    pass


def normalize_e164(raw: str | int | None, default_region: str | None = None) -> str:
    """Normalize user input or a WhatsApp ``wa_id`` to E.164 (``+919876543210``).

    - ``+91 98765 43210``, ``098765 43210`` and ``9876543210`` use the default region (India).
    - A bare international number such as a wa_id (``919876543210``) is read as already
      including its country code.

    Raises InvalidPhoneNumber when the number can't be parsed or isn't valid.
    """
    if raw is None:
        raise InvalidPhoneNumber("Phone number is required.")
    region = default_region or getattr(settings, "DEFAULT_PHONE_REGION", "IN")
    value = _SEPARATORS.sub("", str(raw).strip())
    if not value:
        raise InvalidPhoneNumber("Phone number is required.")
    if value.isdigit() and len(value) > 10 and not value.startswith("0"):
        value = f"+{value}"
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber(f"'{raw}' is not a phone number.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber(f"'{raw}' is not a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def to_wa_id(e164: str) -> str:
    """WhatsApp identifies users by the E.164 number without the leading '+'."""
    return e164.removeprefix("+")
