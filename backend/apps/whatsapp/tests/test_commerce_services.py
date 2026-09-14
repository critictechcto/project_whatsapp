"""Commerce helpers: catalog permissions on the seller's token and the business portfolio id."""

import pytest

from apps.whatsapp import services
from apps.whatsapp.client import errors
from apps.whatsapp.factories import WhatsAppBusinessAccountFactory
from common.exceptions import UpstreamUnavailable

from .conftest import PHONE_ID, SIGNUP_CODE, WABA_ID

pytestmark = pytest.mark.django_db

CATALOG_SCOPES = {"catalog_management": [], "business_management": ["5550001"]}


@pytest.fixture
def waba(workspace, fake_graph):
    fake_graph.add_waba(WABA_ID, name="Sharma Sweets")
    return WhatsAppBusinessAccountFactory(workspace=workspace, waba_id=WABA_ID, business_id="")


def grant(fake_graph, waba, scopes):
    """Make ``waba``'s token debuggable with ``scopes`` on top of the WhatsApp ones."""
    fake_graph.add_signup(
        f"code-{waba.pk}", waba_id=waba.waba_id, token=waba.access_token, extra_scopes=scopes
    )


# --- catalog_permissions_granted ----------------------------------------------------------------


def test_catalog_permissions_are_granted_with_both_scopes(waba, fake_graph):
    grant(fake_graph, waba, CATALOG_SCOPES)

    assert services.catalog_permissions_granted(waba) is True
    assert len(fake_graph.calls_to("debug_token")) == 1


@pytest.mark.parametrize(
    "scopes",
    [None, {"catalog_management": []}, {"business_management": ["5550001"]}],
)
def test_catalog_permissions_need_both_scopes(waba, fake_graph, scopes):
    grant(fake_graph, waba, scopes)

    assert services.catalog_permissions_granted(waba) is False


def test_flat_scopes_count_when_there_are_no_granular_entries(waba, fake_graph):
    grant(fake_graph, waba, None)
    fake_graph._token_debug[waba.access_token]["scopes"] += list(CATALOG_SCOPES)

    assert services.catalog_permissions_granted(waba) is True


@pytest.mark.parametrize("override", [{"is_valid": False}, {"app_id": "999"}])
def test_invalid_or_foreign_tokens_are_not_granted(waba, fake_graph, override):
    grant(fake_graph, waba, CATALOG_SCOPES)
    fake_graph._token_debug[waba.access_token].update(override)

    assert services.catalog_permissions_granted(waba) is False


def test_unknown_token_is_not_granted(waba, fake_graph):
    assert services.catalog_permissions_granted(waba) is False


def test_disconnected_account_is_not_granted_without_calling_meta(waba, fake_graph):
    waba.access_token = ""

    assert services.catalog_permissions_granted(waba) is False
    assert fake_graph.calls_to("debug_token") == []


def test_catalog_permission_check_upstream_outage(waba, fake_graph):
    fake_graph.fail("debug_token", errors.TransientError("Service unavailable", code=2))

    with pytest.raises(UpstreamUnavailable):
        services.catalog_permissions_granted(waba)


def test_catalog_permission_check_rejected_by_meta(waba, fake_graph):
    fake_graph.fail("debug_token", errors.InvalidParameterError("Bad token", code=190))

    assert services.catalog_permissions_granted(waba) is False


# --- business_id_for ----------------------------------------------------------------------------


def test_business_id_comes_from_owner_business_info_and_is_stored(waba, fake_graph):
    assert services.business_id_for(waba) == "5550001"

    waba.refresh_from_db()
    assert waba.business_id == "5550001"
    [call] = fake_graph.calls_to("get_waba")
    assert call.access_token == waba.access_token


def test_meta_business_id_replaces_a_stale_value(waba, fake_graph):
    waba.business_id = "111"
    waba.save()
    fake_graph.wabas[WABA_ID]["owner_business_info"] = {"id": "222", "name": "New owner"}

    assert services.business_id_for(waba) == "222"
    waba.refresh_from_db()
    assert waba.business_id == "222"


@pytest.mark.parametrize(("stored", "expected"), [("", None), ("777", "777")])
def test_stored_business_id_is_the_fallback(waba, fake_graph, stored, expected):
    waba.business_id = stored
    waba.save()
    del fake_graph.wabas[WABA_ID]["owner_business_info"]

    assert services.business_id_for(waba) == expected


@pytest.mark.parametrize(("stored", "expected"), [("", None), ("777", "777")])
def test_rejected_waba_lookup_falls_back(waba, fake_graph, stored, expected):
    waba.business_id = stored
    waba.save()
    fake_graph.fail("get_waba", errors.GraphPermissionError("No access", code=200))

    assert services.business_id_for(waba) == expected


def test_business_id_lookup_upstream_outage(waba, fake_graph):
    fake_graph.fail("get_waba", errors.TransientError("Service unavailable", code=2))

    with pytest.raises(UpstreamUnavailable):
        services.business_id_for(waba)


def test_disconnected_account_uses_the_stored_business_id(waba, fake_graph):
    waba.access_token = ""
    waba.business_id = "777"

    assert services.business_id_for(waba) == "777"
    assert fake_graph.calls_to("get_waba") == []


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"owner_business_info": {"id": "5550001", "name": "Shop"}}, "5550001"),
        ({"owner_business_info": {"id": 5550001}}, "5550001"),
        ({"owner_business_info": {"id": True}}, ""),
        ({"owner_business_info": {"id": "../me"}}, ""),
        ({"owner_business_info": "5550001"}, ""),
        ({}, ""),
    ],
)
def test_owner_business_id(data, expected):
    assert services.owner_business_id(data) == expected


# --- Embedded Signup ----------------------------------------------------------------------------


def signup(workspace, user, **kwargs):
    return services.complete_embedded_signup(
        workspace=workspace,
        user=user,
        code=SIGNUP_CODE,
        waba_id=WABA_ID,
        phone_number_id=PHONE_ID,
        **kwargs,
    )


def test_signup_works_without_catalog_scopes(
    workspace, user, fake_graph, meta_signup, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        waba = signup(workspace, user)

    waba.refresh_from_db()
    assert waba.status == waba.Status.ACTIVE
    assert waba.business_id == "5550001"
    assert services.catalog_permissions_granted(waba) is False


def test_signup_with_catalog_scopes_can_manage_catalogs(
    workspace, user, fake_graph, django_capture_on_commit_callbacks
):
    fake_graph.add_waba(WABA_ID, name="Sharma Sweets")
    fake_graph.add_phone_number(WABA_ID, PHONE_ID)
    fake_graph.add_signup(SIGNUP_CODE, waba_id=WABA_ID, extra_scopes=CATALOG_SCOPES)

    with django_capture_on_commit_callbacks(execute=True):
        waba = signup(workspace, user)

    assert services.catalog_permissions_granted(waba) is True


def test_signup_keeps_the_client_business_id_when_meta_omits_it(
    workspace, user, fake_graph, meta_signup
):
    del fake_graph.wabas[WABA_ID]["owner_business_info"]

    waba = signup(workspace, user, business_id="555")

    assert waba.business_id == "555"
