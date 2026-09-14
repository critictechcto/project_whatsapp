import pytest
from django.urls import reverse

from apps.whatsapp.client import errors
from apps.whatsapp.factories import PhoneNumberFactory, WhatsAppBusinessAccountFactory
from apps.whatsapp.models import PhoneNumber, WhatsAppBusinessAccount
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client, result_ids

from .conftest import PHONE_ID, SIGNUP_CODE, WABA_ID

pytestmark = pytest.mark.django_db

SIGNUP_CONFIG = reverse("whatsapp:signup-config")
EMBEDDED_SIGNUP = reverse("whatsapp:embedded-signup")
ACCOUNTS = reverse("whatsapp:account-list")
PHONES = reverse("whatsapp:phone-number-list")

Status = WhatsAppBusinessAccount.Status


def account_url(waba, name="detail"):
    return reverse(f"whatsapp:account-{name}", args=[waba.pk])


def phone_url(phone, name="detail"):
    return reverse(f"whatsapp:phone-number-{name}", args=[phone.pk])


def assert_no_secrets(response, *secrets):
    body = response.content.decode()
    assert '"access_token"' not in body
    assert '"pin"' not in body
    for secret in secrets:
        if secret:
            assert secret not in body


@pytest.fixture
def waba(workspace):
    return WhatsAppBusinessAccountFactory(workspace=workspace)


@pytest.fixture
def phone(waba):
    return PhoneNumberFactory(waba=waba, pin="654321", is_default=True)


@pytest.fixture
def foreign_phone(other_workspace):
    return PhoneNumberFactory(waba__workspace=other_workspace, pin="111222")


# --- Signup config -------------------------------------------------------------------------------


def test_signup_config_for_viewer(auth_client):
    response = auth_client(Role.VIEWER).get(SIGNUP_CONFIG)

    assert response.status_code == 200, response.content
    assert response.json() == {
        "app_id": "1234567890",
        "config_id": "test-config-id",
        "graph_api_version": "v24.0",
    }


def test_signup_config_requires_membership(user, other_workspace):
    assert make_api_client(user, other_workspace).get(SIGNUP_CONFIG).status_code == 404
    assert make_api_client(user).get(SIGNUP_CONFIG).status_code == 400
    assert make_api_client().get(SIGNUP_CONFIG).status_code == 401


# --- Embedded signup -----------------------------------------------------------------------------


def signup_body(**overrides):
    return {"code": SIGNUP_CODE, "waba_id": WABA_ID, "phone_number_id": PHONE_ID, **overrides}


def test_embedded_signup_creates_account(
    auth_client, workspace, fake_graph, meta_signup, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(Role.ADMIN).post(EMBEDDED_SIGNUP, signup_body(business_id="42"))

    assert response.status_code == 201, response.content
    data = response.json()
    assert data["waba_id"] == WABA_ID
    assert data["business_id"] == "42"
    assert [p["phone_number_id"] for p in data["phone_numbers"]] == [PHONE_ID]
    waba = WhatsAppBusinessAccount.objects.get(workspace=workspace)
    assert waba.status == Status.ACTIVE
    assert_no_secrets(response, meta_signup, waba.phone_numbers.get().pin)


@pytest.mark.parametrize("role", [Role.AGENT, Role.VIEWER])
def test_embedded_signup_requires_admin(auth_client, fake_graph, meta_signup, role):
    response = auth_client(role).post(EMBEDDED_SIGNUP, signup_body())

    assert response.status_code == 403
    assert fake_graph.calls == []


def test_embedded_signup_scope_mismatch_is_400(auth_client, fake_graph):
    fake_graph.add_phone_number(WABA_ID, PHONE_ID)
    fake_graph.add_signup(SIGNUP_CODE, waba_id=WABA_ID, target_ids=["1"])

    response = auth_client().post(EMBEDDED_SIGNUP, signup_body())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "waba_not_granted"


def test_embedded_signup_waba_elsewhere_is_409(
    auth_client, other_workspace, fake_graph, meta_signup
):
    WhatsAppBusinessAccountFactory(workspace=other_workspace, waba_id=WABA_ID)

    response = auth_client().post(EMBEDDED_SIGNUP, signup_body())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "waba_already_connected"


@pytest.mark.parametrize(
    "body",
    [
        signup_body(waba_id="not-a-number"),
        signup_body(coexistence=True, phone_number_id=""),
        {"waba_id": WABA_ID},
    ],
)
def test_embedded_signup_validates_input(auth_client, fake_graph, body):
    response = auth_client().post(EMBEDDED_SIGNUP, body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid"
    assert fake_graph.calls == []


# --- Accounts ------------------------------------------------------------------------------------


def test_viewer_lists_and_retrieves_accounts(auth_client, waba, phone):
    client = auth_client(Role.VIEWER)

    listed = client.get(ACCOUNTS)
    detail = client.get(account_url(waba))

    assert listed.status_code == 200
    assert result_ids(listed) == {str(waba.pk)}
    assert detail.status_code == 200
    assert detail.json()["phone_numbers"][0]["id"] == str(phone.pk)
    for response in (listed, detail):
        assert_no_secrets(response, waba.access_token, phone.pin)


def test_accounts_are_tenant_isolated(auth_client, foreign_phone):
    foreign = foreign_phone.waba

    assert_tenant_isolated(
        auth_client(), object_id=foreign.pk, list_url=ACCOUNTS, detail_url=account_url(foreign)
    )
    client = auth_client()
    assert client.delete(account_url(foreign)).status_code == 404
    assert client.post(account_url(foreign, "resync")).status_code == 404


def test_admin_disconnects_account(auth_client, waba, phone, fake_graph):
    response = auth_client(Role.ADMIN).delete(account_url(waba))

    assert response.status_code == 204
    waba.refresh_from_db()
    assert waba.status == Status.DISCONNECTED
    assert waba.access_token == ""
    assert len(fake_graph.calls_to("unsubscribe_app")) == 1


@pytest.mark.parametrize("role", [Role.AGENT, Role.VIEWER])
def test_disconnect_and_resync_require_admin(auth_client, waba, fake_graph, role):
    client = auth_client(role)

    assert client.delete(account_url(waba)).status_code == 403
    assert client.post(account_url(waba, "resync")).status_code == 403
    waba.refresh_from_db()
    assert waba.status == Status.ACTIVE
    assert fake_graph.calls == []


def test_admin_resyncs_account(
    auth_client, waba, phone, fake_graph, django_capture_on_commit_callbacks
):
    fake_graph.add_phone_number(waba.waba_id, phone.phone_number_id, quality_rating="RED")

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(Role.ADMIN).post(account_url(waba, "resync"))

    assert response.status_code == 202, response.content
    assert waba.waba_id in fake_graph.subscribed_waba_ids
    phone.refresh_from_db()
    assert phone.quality_rating == "RED"
    assert_no_secrets(response, waba.access_token, phone.pin)


def test_resync_disconnected_account_conflicts(auth_client, waba, fake_graph):
    WhatsAppBusinessAccount.objects.filter(pk=waba.pk).update(status=Status.DISCONNECTED)

    response = auth_client().post(account_url(waba, "resync"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "waba_disconnected"


# --- Phone numbers -------------------------------------------------------------------------------


def test_viewer_lists_and_filters_phone_numbers(auth_client, waba, phone, workspace):
    other = PhoneNumberFactory(waba__workspace=workspace)
    client = auth_client(Role.VIEWER)

    everything = client.get(PHONES)
    filtered = client.get(PHONES, {"waba": str(waba.pk)})
    detail = client.get(phone_url(phone))

    assert result_ids(everything) == {str(phone.pk), str(other.pk)}
    assert result_ids(filtered) == {str(phone.pk)}
    assert detail.status_code == 200
    for response in (everything, filtered, detail):
        assert_no_secrets(response, waba.access_token, phone.pin)


def test_phone_numbers_are_tenant_isolated(auth_client, foreign_phone):
    client = auth_client()

    assert_tenant_isolated(
        client,
        object_id=foreign_phone.pk,
        list_url=PHONES,
        detail_url=phone_url(foreign_phone),
    )
    for name in ("refresh", "retry-registration", "set-default"):
        assert client.post(phone_url(foreign_phone, name)).status_code == 404


@pytest.mark.parametrize("role", [Role.AGENT, Role.VIEWER])
def test_phone_actions_require_admin(auth_client, phone, fake_graph, role):
    client = auth_client(role)

    for name in ("refresh", "retry-registration", "set-default"):
        assert client.post(phone_url(phone, name)).status_code == 403
    assert fake_graph.calls == []


def test_admin_refreshes_phone_number(auth_client, phone, fake_graph):
    fake_graph.add_phone_number(
        phone.waba.waba_id, phone.phone_number_id, quality_rating="YELLOW", verified_name="Renamed"
    )

    response = auth_client(Role.ADMIN).post(phone_url(phone, "refresh"))

    assert response.status_code == 200, response.content
    assert response.json()["quality_rating"] == "YELLOW"
    assert response.json()["verified_name"] == "Renamed"
    assert_no_secrets(response, phone.waba.access_token, phone.pin)


def test_refresh_with_revoked_token_requires_reconnect(auth_client, phone, fake_graph):
    fake_graph.fail("get_phone_number", errors.TokenInvalidError("Expired", code=190))

    response = auth_client().post(phone_url(phone, "refresh"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "reconnect_required"
    phone.waba.refresh_from_db()
    assert phone.waba.status == Status.DISCONNECTED


def test_refresh_upstream_outage_is_503(auth_client, phone, fake_graph):
    fake_graph.fail("get_phone_number", errors.NetworkError("timeout"))

    response = auth_client().post(phone_url(phone, "refresh"))

    assert response.status_code == 503


def test_admin_retries_registration(
    auth_client, waba, fake_graph, django_capture_on_commit_callbacks
):
    phone = PhoneNumberFactory(waba=waba, registration_status=PhoneNumber.RegistrationStatus.FAILED)
    fake_graph.add_phone_number(waba.waba_id, phone.phone_number_id)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(Role.ADMIN).post(phone_url(phone, "retry-registration"))

    assert response.status_code == 202, response.content
    phone.refresh_from_db()
    assert phone.registration_status == PhoneNumber.RegistrationStatus.REGISTERED
    assert fake_graph.registered_pins[phone.phone_number_id] == phone.pin
    assert_no_secrets(response, phone.pin, waba.access_token)


def test_retry_registration_rejects_coexistence_number(auth_client, waba, fake_graph):
    phone = PhoneNumberFactory(waba=waba, is_coexistence=True)

    response = auth_client().post(phone_url(phone, "retry-registration"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coexistence_number"


def test_admin_sets_default_number(auth_client, waba, phone):
    second = PhoneNumberFactory(waba=waba)

    response = auth_client(Role.ADMIN).post(phone_url(second, "set-default"))

    assert response.status_code == 200, response.content
    assert response.json()["is_default"] is True
    phone.refresh_from_db()
    second.refresh_from_db()
    assert (phone.is_default, second.is_default) == (False, True)
    assert PhoneNumber.objects.filter(workspace=waba.workspace, is_default=True).count() == 1


def test_set_default_is_idempotent(auth_client, phone):
    response = auth_client().post(phone_url(phone, "set-default"))

    assert response.status_code == 200
    phone.refresh_from_db()
    assert phone.is_default is True


def test_set_default_rejects_disconnected_account(auth_client, waba):
    phone = PhoneNumberFactory(waba=waba)
    WhatsAppBusinessAccount.objects.filter(pk=waba.pk).update(status=Status.DISCONNECTED)

    response = auth_client().post(phone_url(phone, "set-default"))

    assert response.status_code == 409
