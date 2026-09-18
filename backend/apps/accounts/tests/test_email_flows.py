"""Email verification and password reset: tasks, tokens and the four endpoints."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core import mail, signing
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts import tasks, tokens
from apps.accounts.factories import DEFAULT_PASSWORD, UserFactory
from apps.accounts.models import User
from common import mail as mail_module
from common.mail_backends import EmailSendError
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

REGISTER = reverse("accounts:register")
TOKEN = reverse("accounts:token")
VERIFY = reverse("accounts:email-verify")
VERIFY_REQUEST = reverse("accounts:email-verify-request")
RESET = reverse("accounts:password-reset")
RESET_CONFIRM = reverse("accounts:password-reset-confirm")
INVALID = "This link is invalid or has expired."
NEW_PASSWORD = "Brand-new-pass-2026"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()
    yield
    cache.clear()


def link_token(message, path: str) -> str:
    """The token of the first ``path`` link in the plain-text body."""
    link = next(word for word in message.body.split() if f"{path}?token=" in word)
    assert link.startswith(f"http://testserver-frontend{path}?token=")
    [token] = parse_qs(urlsplit(link).query)["token"]
    return token


def field_error(response, field):
    assert response.status_code == 400, response.content
    body = response.json()["error"]
    assert body["code"] == "invalid"
    return body["details"][field]


def limit_email_send(monkeypatch, rate="2/hour"):
    monkeypatch.setattr(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "email_send": rate},
    )


# --- Tokens ------------------------------------------------------------------------------


def test_tokens_are_url_safe():
    user = UserFactory()
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.")
    assert set(tokens.make_verification_token(user)) <= allowed
    assert set(tokens.make_password_reset_token(user)) <= allowed
    uid = tokens.make_password_reset_token(user).split(".")[0]
    assert "." not in uid


# --- Register + verification email ------------------------------------------------------


def test_register_sends_a_verification_email_with_a_working_link(
    api_client, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            REGISTER,
            {"email": "Priya@Example.com", "password": "a-Very-long-pass-42", "full_name": "Priya"},
        )
    assert response.status_code == 201, response.content
    assert response.json()["user"]["email_verified_at"] is None

    [message] = mail.outbox
    assert message.to == ["priya@example.com"]
    assert message.subject == "Confirm your email for UpChatz"
    assert message.extra_headers["Idempotency-Key"].startswith("verify:")
    [(html, mimetype)] = message.alternatives
    assert mimetype == "text/html"
    assert "Confirm email" in html
    token = link_token(message, "/app/verify-email")

    assert make_api_client().post(VERIFY, {"token": token}).status_code == 204
    login = make_api_client().post(
        TOKEN, {"email": "priya@example.com", "password": "a-Very-long-pass-42"}
    )
    assert login.status_code == 200  # signing in never depended on verification
    assert User.objects.get(email="priya@example.com").email_verified_at is not None


def test_verification_task_skips_verified_inactive_and_missing_users():
    verified = UserFactory(email_verified_at=timezone.now())
    inactive = UserFactory(is_active=False)

    assert tasks.send_verification_email.delay(str(verified.pk)).get() is False
    assert tasks.send_verification_email.delay(str(inactive.pk)).get() is False
    assert (
        tasks.send_verification_email.delay("7b1c3f5e-0000-4000-8000-000000000000").get() is False
    )
    assert mail.outbox == []


# --- POST email/verify/ -----------------------------------------------------------------


def test_verify_marks_the_email_verified_and_is_idempotent(api_client):
    user = UserFactory()
    token = tokens.make_verification_token(user)

    assert api_client.post(VERIFY, {"token": token}).status_code == 204
    user.refresh_from_db()
    first = user.email_verified_at
    assert first is not None

    # The page may post twice; the second call is still a 204 and keeps the first time.
    assert api_client.post(VERIFY, {"token": token}).status_code == 204
    user.refresh_from_db()
    assert user.email_verified_at == first


def test_verify_works_without_authentication_even_with_a_bad_bearer(api_client):
    user = UserFactory()
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-jwt")

    response = api_client.post(VERIFY, {"token": tokens.make_verification_token(user)})

    assert response.status_code == 204


def test_verify_rejects_an_expired_token(api_client, settings, time_machine):
    time_machine.move_to(timezone.now(), tick=False)
    settings.EMAIL_VERIFICATION_MAX_AGE_DAYS = 3
    user = UserFactory()
    token = tokens.make_verification_token(user)
    time_machine.shift(timedelta(days=3, minutes=1))

    assert field_error(api_client.post(VERIFY, {"token": token}), "token") == [INVALID]
    user.refresh_from_db()
    assert user.email_verified_at is None


def test_verify_accepts_an_old_link_once_already_verified(api_client, time_machine):
    time_machine.move_to(timezone.now(), tick=False)
    user = UserFactory()
    token = tokens.make_verification_token(user)
    assert api_client.post(VERIFY, {"token": token}).status_code == 204
    time_machine.shift(timedelta(days=30))

    assert api_client.post(VERIFY, {"token": token}).status_code == 204


@pytest.mark.parametrize("mangle", ["tamper", "garbage", "other_salt", "empty"])
def test_verify_rejects_bad_tokens(api_client, mangle):
    user = UserFactory()
    token = tokens.make_verification_token(user)
    bad = {
        "tamper": token[:-2] + ("AA" if not token.endswith("AA") else "BB"),
        "garbage": "not-a-token",
        "other_salt": signing.TimestampSigner(salt="other", sep=".").sign_object(
            {"u": str(user.pk), "e": user.email}
        ),
        "empty": "",
    }[mangle]

    response = api_client.post(VERIFY, {"token": bad})

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.email_verified_at is None
    if mangle != "empty":
        assert field_error(response, "token") == [INVALID]


def test_verify_rejects_a_token_for_a_changed_email(api_client):
    user = UserFactory(email="old@example.com")
    token = tokens.make_verification_token(user)
    user.email = "new@example.com"
    user.save()

    assert field_error(api_client.post(VERIFY, {"token": token}), "token") == [INVALID]


# --- POST email/verify/request/ ---------------------------------------------------------


def test_verify_request_sends_a_new_link(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = make_api_client(user).post(VERIFY_REQUEST)

    assert response.status_code == 204
    [message] = mail.outbox
    assert message.to == [user.email]
    token = link_token(message, "/app/verify-email")
    assert tokens.check_verification_token(token).user == user


def test_verify_request_when_already_verified_sends_nothing(django_capture_on_commit_callbacks):
    user = UserFactory(email_verified_at=timezone.now())
    with django_capture_on_commit_callbacks(execute=True):
        response = make_api_client(user).post(VERIFY_REQUEST)

    assert response.status_code == 204
    assert mail.outbox == []


def test_verify_request_needs_a_signed_in_user(api_client):
    assert api_client.post(VERIFY_REQUEST).status_code == 401


def test_verify_request_is_throttled_per_user(monkeypatch, django_capture_on_commit_callbacks):
    limit_email_send(monkeypatch)
    user, other = UserFactory(), UserFactory()
    client = make_api_client(user)

    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(VERIFY_REQUEST).status_code == 204
        assert client.post(VERIFY_REQUEST).status_code == 204
        throttled = client.post(VERIFY_REQUEST)
        assert make_api_client(other).post(VERIFY_REQUEST).status_code == 204

    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "throttled"
    assert len(mail.outbox) == 3


# --- POST password/reset/ ---------------------------------------------------------------


def test_reset_request_emails_active_users_only(api_client, django_capture_on_commit_callbacks):
    UserFactory(email="asha@example.com")
    UserFactory(email="gone@example.com", is_active=False)

    with django_capture_on_commit_callbacks(execute=True):
        responses = [
            api_client.post(RESET, {"email": "ASHA@example.com"}),
            api_client.post(RESET, {"email": "nobody@example.com"}),
            api_client.post(RESET, {"email": "gone@example.com"}),
        ]

    assert [r.status_code for r in responses] == [204, 204, 204]
    assert all(r.content == b"" for r in responses)
    [message] = mail.outbox
    assert message.to == ["asha@example.com"]
    assert message.subject == "Reset your UpChatz password"
    assert "1 hour" in message.body
    [(html, _)] = message.alternatives
    assert "Choose a new password" in html
    assert link_token(message, "/app/reset-password")


def test_reset_request_validates_the_email(api_client):
    assert field_error(api_client.post(RESET, {"email": "not-an-email"}), "email")


def test_reset_request_is_throttled_per_email(api_client, monkeypatch):
    limit_email_send(monkeypatch)
    UserFactory(email="asha@example.com")

    for ip in ("203.0.113.1", "203.0.113.2"):
        assert (
            api_client.post(
                RESET, {"email": "asha@example.com"}, HTTP_X_FORWARDED_FOR=ip
            ).status_code
            == 204
        )
    throttled = api_client.post(
        RESET, {"email": " Asha@Example.com"}, HTTP_X_FORWARDED_FOR="198.51.100.7"
    )
    assert throttled.status_code == 429
    assert api_client.post(RESET, {"email": "ravi@example.com"}).status_code == 204


# --- POST password/reset/confirm/ -------------------------------------------------------


def request_reset_token(user) -> str:
    mail.outbox.clear()
    tasks.send_password_reset_email.delay(str(user.pk)).get()
    [message] = mail.outbox
    return link_token(message, "/app/reset-password")


def test_reset_confirm_sets_the_password_ends_sessions_and_verifies(api_client):
    user = UserFactory()
    assert user.email_verified_at is None
    login = api_client.post(TOKEN, {"email": user.email, "password": DEFAULT_PASSWORD})
    assert login.status_code == 200
    assert OutstandingToken.objects.filter(user=user).exists()
    token = request_reset_token(user)

    response = api_client.post(RESET_CONFIRM, {"token": token, "new_password": NEW_PASSWORD})

    assert response.status_code == 204, response.content
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert user.email_verified_at is not None
    outstanding = OutstandingToken.objects.filter(user=user)
    assert BlacklistedToken.objects.filter(token__in=outstanding).count() == outstanding.count()
    assert (
        api_client.post(TOKEN, {"email": user.email, "password": NEW_PASSWORD}).status_code == 200
    )


def test_reset_token_works_once(api_client):
    user = UserFactory()
    token = request_reset_token(user)
    assert (
        api_client.post(RESET_CONFIRM, {"token": token, "new_password": NEW_PASSWORD}).status_code
        == 204
    )

    reused = api_client.post(RESET_CONFIRM, {"token": token, "new_password": "Another-pass-2027"})

    assert field_error(reused, "token") == [INVALID]
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_reset_rejects_a_weak_password(api_client):
    user = UserFactory()
    token = request_reset_token(user)

    response = api_client.post(RESET_CONFIRM, {"token": token, "new_password": "12345678"})

    assert field_error(response, "new_password")
    user.refresh_from_db()
    assert user.check_password(DEFAULT_PASSWORD)


def test_reset_rejects_an_expired_token(api_client, settings, time_machine):
    time_machine.move_to(timezone.now(), tick=False)
    settings.PASSWORD_RESET_TIMEOUT = 3600
    user = UserFactory()
    token = request_reset_token(user)
    time_machine.shift(timedelta(hours=1, minutes=1))

    response = api_client.post(RESET_CONFIRM, {"token": token, "new_password": NEW_PASSWORD})

    assert field_error(response, "token") == [INVALID]


@pytest.mark.parametrize("bad", ["", "nodot", "bm9wZQ.abc-123", "!!!.abc", "a.b.c"])
def test_reset_rejects_bad_tokens(api_client, bad):
    UserFactory()
    response = api_client.post(RESET_CONFIRM, {"token": bad, "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    if bad:
        assert field_error(response, "token") == [INVALID]


def test_reset_rejects_inactive_users(api_client):
    user = UserFactory()
    token = tokens.make_password_reset_token(user)
    user.is_active = False
    user.save()

    response = api_client.post(RESET_CONFIRM, {"token": token, "new_password": NEW_PASSWORD})

    assert field_error(response, "token") == [INVALID]


def test_reset_task_reuses_its_token_on_retry():
    user = UserFactory()
    token = tokens.make_password_reset_token(user)
    tasks.send_password_reset_email.delay(str(user.pk), token=token).get()
    [message] = mail.outbox
    assert link_token(message, "/app/reset-password") == token
    assert message.extra_headers["Idempotency-Key"].startswith(f"reset:{user.pk}:")


def test_verification_retry_resends_the_same_link_and_key(monkeypatch, time_machine):
    time_machine.move_to(timezone.now(), tick=False)
    user = UserFactory()
    real_send = mail_module.send_templated_email
    calls = []

    def fail_once(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            # The retry runs later; a new token then would differ from the first one.
            time_machine.shift(timedelta(seconds=90))
            raise EmailSendError("Resend returned 503", retryable=True)
        real_send(**kwargs)

    monkeypatch.setattr(mail_module, "send_templated_email", fail_once)
    tasks.send_verification_email.apply(args=[str(user.pk)], throw=False)

    assert len(calls) == 2
    assert calls[0]["context"]["link"] == calls[1]["context"]["link"]
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]
    assert len(mail.outbox) == 1
