"""Password guessing can't dodge the login throttle by rotating ``X-Forwarded-For``."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.factories import DEFAULT_PASSWORD, UserFactory
from apps.accounts.views import LoginEmailThrottle

pytestmark = pytest.mark.django_db

TOKEN = reverse("accounts:token")


@pytest.fixture(autouse=True)
def small_login_rate(monkeypatch):
    monkeypatch.setattr(LoginEmailThrottle, "default_rate", "3/hour")
    cache.clear()
    yield
    cache.clear()


def _login(client, email, password, ip):
    return client.post(TOKEN, {"email": email, "password": password}, HTTP_X_FORWARDED_FOR=ip)


def test_login_attempts_are_limited_per_email_across_spoofed_ips(api_client):
    UserFactory(email="asha@example.com")

    for attempt in range(3):
        response = _login(api_client, "asha@example.com", "wrong-guess", f"203.0.113.{attempt}")
        assert response.status_code == 401

    # A new spoofed client IP and a different letter case still count against the same account,
    # and even the right password is refused until the window passes.
    response = _login(api_client, "ASHA@example.com ", DEFAULT_PASSWORD, "198.51.100.77")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"


def test_login_throttle_is_per_email(api_client):
    UserFactory(email="asha@example.com")
    UserFactory(email="ravi@example.com")

    for attempt in range(3):
        _login(api_client, "asha@example.com", "wrong-guess", f"203.0.113.{attempt}")

    response = _login(api_client, "ravi@example.com", DEFAULT_PASSWORD, "203.0.113.9")
    assert response.status_code == 200
