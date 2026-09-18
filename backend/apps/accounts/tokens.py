"""Stateless, URL-safe tokens for email verification and password reset links.

- Verification: a signed ``{"u": user id, "e": email}`` with a timestamp. Valid for
  ``EMAIL_VERIFICATION_MAX_AGE_DAYS`` and only while the account still has that email.
- Password reset: ``<base64 user id>.<Django token>``. Django's token hashes the password and
  last login, so it stops working once used; it expires after ``PASSWORD_RESET_TIMEOUT``.

Both only use ``[A-Za-z0-9_.-]``, so they need no escaping in a URL.
"""

from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

VERIFY_SALT = "upchatz.email-verify"
# "." never appears in Django's URL-safe base64 or base62 timestamps, and needs no escaping.
_VERIFY_SEP = "."


def _verify_signer() -> signing.TimestampSigner:
    return signing.TimestampSigner(salt=VERIFY_SALT, sep=_VERIFY_SEP)


def frontend_link(path: str, token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}?{urlencode({'token': token})}"


# --- Email verification ------------------------------------------------------------------


def make_verification_token(user) -> str:
    return _verify_signer().sign_object({"u": str(user.pk), "e": user.email})


@dataclass(frozen=True)
class VerificationCheck:
    user: object
    expired: bool


def check_verification_token(token: str) -> VerificationCheck | None:
    """The user a correctly signed token names, if its email still matches; None otherwise.

    ``expired`` is True when the signature is valid but older than the max age.
    """
    if not isinstance(token, str) or not token or len(token) > 1024:
        return None
    max_age = timedelta(days=settings.EMAIL_VERIFICATION_MAX_AGE_DAYS)
    expired = False
    try:
        payload = _verify_signer().unsign_object(token, max_age=max_age)
    except signing.SignatureExpired:
        expired = True
        try:
            payload = _verify_signer().unsign_object(token)
        except (signing.BadSignature, ValueError):
            return None
    except (signing.BadSignature, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    user = _user_by_id(payload.get("u"))
    if user is None or not user.is_active or user.email != payload.get("e"):
        return None
    return VerificationCheck(user=user, expired=expired)


def verification_link(token: str) -> str:
    return frontend_link("/app/verify-email", token)


# --- Password reset ----------------------------------------------------------------------


def make_password_reset_token(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{uid}.{default_token_generator.make_token(user)}"


def check_password_reset_token(token: str):
    """The active user a valid, unused, unexpired reset token belongs to; None otherwise."""
    if not isinstance(token, str) or "." not in token or len(token) > 512:
        return None
    uid, _, secret = token.partition(".")
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    user = _user_by_id(user_id)
    if user is None or not user.is_active:
        return None
    if not default_token_generator.check_token(user, secret):
        return None
    return user


def password_reset_link(token: str) -> str:
    return frontend_link("/app/reset-password", token)


def _user_by_id(user_id):
    if not isinstance(user_id, str):
        return None
    try:
        return get_user_model().objects.filter(pk=user_id).first()
    except (ValueError, ValidationError):
        return None
