import pytest
from django.urls import reverse

from apps.accounts.factories import DEFAULT_PASSWORD, UserFactory
from common.testing import make_api_client

pytestmark = pytest.mark.django_db

REGISTER = reverse("accounts:register")
TOKEN = reverse("accounts:token")
REFRESH = reverse("accounts:token-refresh")
LOGOUT = reverse("accounts:logout")
ME = reverse("accounts:me")
PASSWORD_CHANGE = reverse("accounts:password-change")


def login(client, email, password=DEFAULT_PASSWORD):
    return client.post(TOKEN, {"email": email, "password": password})


def test_register_creates_user_and_returns_tokens(api_client):
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
    assert body["tokens"]["access"] and body["tokens"]["refresh"]
    assert "password" not in body["user"]


def test_register_rejects_duplicate_email_case_insensitively(api_client):
    UserFactory(email="taken@example.com")

    response = api_client.post(
        REGISTER, {"email": "TAKEN@example.com", "password": "a-Very-long-pass-42"}
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid"
    assert "email" in error["details"]


def test_register_rejects_weak_password(api_client):
    response = api_client.post(REGISTER, {"email": "new@example.com", "password": "12345678"})

    assert response.status_code == 400
    assert "password" in response.json()["error"]["details"]


def test_login_accepts_email_in_any_case(api_client):
    UserFactory(email="asha@example.com")

    response = login(api_client, "ASHA@example.com")

    assert response.status_code == 200, response.content
    assert {"access", "refresh"} <= response.json().keys()


def test_login_rejects_wrong_password(api_client):
    user = UserFactory()

    response = login(api_client, user.email, "wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "no_active_account"


def test_refresh_rotates_and_logout_blacklists(api_client):
    user = UserFactory()
    refresh = login(api_client, user.email).json()["refresh"]

    rotated = api_client.post(REFRESH, {"refresh": refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh"]
    assert api_client.post(REFRESH, {"refresh": refresh}).status_code == 401

    assert api_client.post(LOGOUT, {"refresh": new_refresh}).status_code == 200
    assert api_client.post(REFRESH, {"refresh": new_refresh}).status_code == 401


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
    refresh = login(api_client, user.email).json()["refresh"]
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
    assert api_client.post(REFRESH, {"refresh": refresh}).status_code == 401
    assert login(api_client, user.email, "another-Long-pass-99").status_code == 200
