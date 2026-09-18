"""Account emails. Tokens are made inside the task and reused on retry, so a retried send keeps
the same link and Resend idempotency key."""

import hashlib

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from common.mail import send_or_retry

from . import tokens


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _name(user) -> str:
    return user.get_short_name() if user.full_name else "there"


def _duration_label(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} day" if days == 1 else f"{days} days"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, seconds // 60)
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


@shared_task(bind=True, name="accounts.send_verification_email")
def send_verification_email(self, user_id: str, token: str | None = None) -> bool:
    """Email a link that confirms the user's address. Skips gone, inactive or verified users."""
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None or not user.is_active or user.email_verified_at is not None:
        return False
    check = tokens.check_verification_token(token) if token else None
    if check is None or check.expired or check.user.pk != user.pk:
        token = tokens.make_verification_token(user)
    send_or_retry(
        self,
        to=user.email,
        template="verify_email",
        context={
            "name": _name(user),
            "email": user.email,
            "link": tokens.verification_link(token),
            "expires_days": settings.EMAIL_VERIFICATION_MAX_AGE_DAYS,
        },
        idempotency_key=f"verify:{user.pk}:{_token_digest(token)}",
        retry_kwargs={"user_id": str(user.pk), "token": token},
    )
    return True


@shared_task(bind=True, name="accounts.send_password_reset_email")
def send_password_reset_email(self, user_id: str, token: str | None = None) -> bool:
    """Email a one-time password reset link. Skips gone or inactive users."""
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None or not user.is_active:
        return False
    if not token or tokens.check_password_reset_token(token) != user:
        token = tokens.make_password_reset_token(user)
    send_or_retry(
        self,
        to=user.email,
        template="password_reset",
        context={
            "name": _name(user),
            "email": user.email,
            "link": tokens.password_reset_link(token),
            "expires_label": _duration_label(settings.PASSWORD_RESET_TIMEOUT),
        },
        idempotency_key=f"reset:{user.pk}:{_token_digest(token)}",
        retry_kwargs={"user_id": str(user.pk), "token": token},
    )
    return True
