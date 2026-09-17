import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.cookies import REFRESH_COOKIE_NAME, refresh_lifetime_seconds
from apps.accounts.factories import DEFAULT_PASSWORD, UserFactory
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

REGISTER = reverse("accounts:register")
TOKEN = reverse("accounts:token")
REFRESH = reverse("accounts:token-refresh")
LOGOUT = reverse("accounts:logout")
ME = reverse("accounts:me")
PASSWORD_CHANGE = reverse("accounts:password-change")

AUTH_HEADER = {"HTTP_X_UPCHATZ_AUTH": "1"}
ALLOWED_ORIGIN = "http://testserver-frontend"


def login(client, email, password=DEFAULT_PASSWORD):
    return client.post(TOKEN, {"email": email, "password": password})


def refresh(client, **extra):
    return client.post(REFRESH, **{**AUTH_HEADER, **extra})


def assert_refresh_cookie(response, *, secure=False):
    morsel = response.cookies[REFRESH_COOKIE_NAME]
    assert morsel.value
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "Strict"
    assert morsel["path"] == "/api/v1/auth/"
    assert int(morsel["max-age"]) == refresh_lifetime_seconds()
    assert bool(morsel["secure"]) is secure
    assert not morsel["domain"]
    return morsel.value


def assert_cookie_cleared(response):
    morsel = response.cookies[REFRESH_COOKIE_NAME]
    assert morsel.value == ""
    assert int(morsel["max-age"]) == 0
    assert morsel["path"] == "/api/v1/auth/"


def assert_no_refresh_in_body(response, refresh_token):
    body = response.json()
    assert "refresh" not in body
    assert "tokens" not in body
    assert refresh_token not in response.content.decode()


def test_register_creates_user_sets_cookie_and_returns_access_only(api_client):
    response = api_client.post(
        REGISTER,
        {
            "email": "Priya@Example.com",
            "password": "a-Very-long-pass-42",
            "full_name": "Priya Shah",
        },
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["user"]["email"] == "priya@example.com"
    assert set(body) == {"user", "access"}
    assert "password" not in body["user"]
    token = assert_refresh_cookie(response)
    assert_no_refresh_in_body(response, token)
    assert RefreshToken(token)["user_id"] == body["user"]["id"]


def test_register_rejects_duplicate_email_case_insensitively(api_client):
    UserFactory(email="taken@example.com")

    response = api_client.post(
        REGISTER, {"email": "TAKEN@example.com", "password": "a-Very-long-pass-42"}
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid"
    assert "email" in error["details"]
    assert REFRESH_COOKIE_NAME not in response.cookies


def test_register_rejects_weak_password(api_client):
    response = api_client.post(REGISTER, {"email": "new@example.com", "password": "12345678"})

    assert response.status_code == 400
    assert "password" in response.json()["error"]["details"]


def test_login_accepts_email_in_any_case_and_sets_cookie(api_client):
    UserFactory(email="asha@example.com")

    response = login(api_client, "ASHA@example.com")

    assert response.status_code == 200, response.content
    assert set(response.json()) == {"access"}
    token = assert_refresh_cookie(response)
    assert_no_refresh_in_body(response, token)


@override_settings(AUTH_REFRESH_COOKIE_SECURE=True)
def test_cookie_secure_flag_follows_setting(api_client):
    user = UserFactory()

    assert_refresh_cookie(login(api_client, user.email), secure=True)
    assert_refresh_cookie(refresh(api_client), secure=True)


@override_settings(AUTH_REFRESH_COOKIE_DOMAIN="upchatz.test")
def test_cookie_domain_follows_setting(api_client):
    user = UserFactory()

    assert login(api_client, user.email).cookies[REFRESH_COOKIE_NAME]["domain"] == "upchatz.test"


def test_login_rejects_wrong_password(api_client):
    user = UserFactory()

    response = login(api_client, user.email, "wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "no_active_account"
    assert REFRESH_COOKIE_NAME not in response.cookies


def test_refresh_reads_cookie_rotates_and_rejects_reuse(api_client):
    user = UserFactory()
    first = login(api_client, user.email).cookies[REFRESH_COOKIE_NAME].value

    rotated = refresh(api_client, HTTP_ORIGIN=ALLOWED_ORIGIN)
    assert rotated.status_code == 200, rotated.content
    assert set(rotated.json()) == {"access"}
    second = assert_refresh_cookie(rotated)
    assert second != first
    assert_no_refresh_in_body(rotated, second)
    assert BlacklistedToken.objects.filter(token__jti=RefreshToken(first, verify=False)["jti"])
    access_client = make_api_client()
    access_client.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated.json()['access']}")
    assert access_client.get(ME).status_code == 200

    # A stolen or replayed old cookie is refused, and the response clears the cookie.
    replay = make_api_client()
    replay.cookies[REFRESH_COOKIE_NAME] = first
    reused = refresh(replay)
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "token_not_valid"
    assert_cookie_cleared(reused)

    # The current cookie still works.
    assert refresh(api_client).status_code == 200


def test_refresh_ignores_a_body_token(api_client):
    user = UserFactory()
    token = str(RefreshToken.for_user(user))

    response = api_client.post(REFRESH, {"refresh": token}, **AUTH_HEADER)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert_cookie_cleared(response)


def test_refresh_without_cookie_is_401_and_clears(api_client):
    response = refresh(api_client)

    assert response.status_code == 401
    assert set(response.json()["error"]) == {"code", "message", "details"}
    assert_cookie_cleared(response)


def test_refresh_with_garbage_cookie_is_401(api_client):
    api_client.cookies[REFRESH_COOKIE_NAME] = "not-a-jwt"

    response = refresh(api_client)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_valid"
    assert_cookie_cleared(response)


def test_refresh_requires_the_auth_header(api_client):
    user = UserFactory()
    login(api_client, user.email)

    response = api_client.post(REFRESH)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "auth_header_required"
    assert_cookie_cleared(response)


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
def test_refresh_rejects_a_foreign_origin(api_client, origin):
    user = UserFactory()
    token = login(api_client, user.email).cookies[REFRESH_COOKIE_NAME].value

    response = refresh(api_client, HTTP_ORIGIN=origin)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"
    assert_cookie_cleared(response)
    # The token was not rotated or revoked by the refused request.
    assert not BlacklistedToken.objects.filter(token__jti=RefreshToken(token, verify=False)["jti"])


@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5180"])
def test_refresh_accepts_cors_and_same_origins(api_client):
    user = UserFactory()
    login(api_client, user.email)

    assert refresh(api_client, HTTP_ORIGIN="http://localhost:5180").status_code == 200
    assert refresh(api_client, HTTP_ORIGIN=ALLOWED_ORIGIN).status_code == 200  # FRONTEND_URL
    assert refresh(api_client, HTTP_ORIGIN="http://testserver").status_code == 200  # same origin


def test_logout_blacklists_and_clears(api_client):
    user = UserFactory()
    token = login(api_client, user.email).cookies[REFRESH_COOKIE_NAME].value

    response = api_client.post(LOGOUT, HTTP_ORIGIN=ALLOWED_ORIGIN, **AUTH_HEADER)

    assert response.status_code == 204
    assert_cookie_cleared(response)
    assert BlacklistedToken.objects.filter(token__jti=RefreshToken(token, verify=False)["jti"])
    replay = make_api_client()
    replay.cookies[REFRESH_COOKIE_NAME] = token
    assert refresh(replay).status_code == 401


def test_logout_without_cookie_still_clears(api_client):
    response = api_client.post(LOGOUT, **AUTH_HEADER)

    assert response.status_code == 204
    assert_cookie_cleared(response)


def test_logout_requires_header_and_allowed_origin(api_client):
    user = UserFactory()
    login(api_client, user.email)

    no_header = api_client.post(LOGOUT)
    assert no_header.status_code == 403
    assert no_header.json()["error"]["code"] == "auth_header_required"
    bad_origin = api_client.post(LOGOUT, HTTP_ORIGIN="https://evil.example", **AUTH_HEADER)
    assert bad_origin.status_code == 403
    # Neither refused request ended the session.
    assert refresh(api_client).status_code == 200


def test_cors_preflight_allows_credentials_and_auth_header(api_client):
    response = api_client.options(
        REFRESH,
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-upchatz-auth",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response["Access-Control-Allow-Credentials"] == "true"
    assert "x-upchatz-auth" in response["Access-Control-Allow-Headers"]


def test_me_requires_authentication(api_client):
    response = api_client.get(ME)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_lists_active_workspace_memberships(user, workspace):
    response = make_api_client(user).get(ME)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["memberships"] == [
        {
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "workspace_slug": workspace.slug,
            "role": "owner",
        }
    ]


def test_me_patch_updates_name_but_not_email(user):
    client = make_api_client(user)

    response = client.patch(ME, {"full_name": "New Name", "email": "hijack@example.com"})

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.full_name == "New Name"
    assert user.email != "hijack@example.com"


def test_password_change_requires_current_password_and_revokes_sessions(api_client):
    user = UserFactory()
    login(api_client, user.email)
    client = make_api_client(user)

    wrong = client.post(
        PASSWORD_CHANGE, {"current_password": "nope", "new_password": "another-Long-pass-99"}
    )
    assert wrong.status_code == 400

    ok = client.post(
        PASSWORD_CHANGE,
        {"current_password": DEFAULT_PASSWORD, "new_password": "another-Long-pass-99"},
    )
    assert ok.status_code == 204
    assert refresh(api_client).status_code == 401
    assert login(api_client, user.email, "another-Long-pass-99").status_code == 200
