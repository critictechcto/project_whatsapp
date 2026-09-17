"""Plans, roles, tenant isolation and date ranges."""

import pytest

from apps.billing.entitlements import ANALYTICS, COMMERCE
from apps.campaigns.factories import CampaignFactory
from apps.inbox.factories import ConversationFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client

from .helpers import REPORTS, backdate, drop_feature, local, message, set_plan, url

pytestmark = pytest.mark.django_db


def error(response) -> dict:
    return response.json()["error"]


@pytest.mark.parametrize("report", REPORTS)
def test_starter_gets_feature_not_available(client, workspace, report):
    set_plan(workspace, "starter")

    response = client.get(url(report))

    assert response.status_code == 409, response.content
    assert error(response)["code"] == "feature_not_available"
    assert error(response)["details"] == {"feature": ANALYTICS}


def test_starter_export_is_gated_too(client, workspace):
    set_plan(workspace, "starter")

    response = client.get(url("export", report="messages"))

    assert response.status_code == 409
    assert error(response)["details"] == {"feature": ANALYTICS}


@pytest.mark.parametrize("plan", ["growth", "pro"])
@pytest.mark.parametrize("report", REPORTS)
def test_growth_and_pro_can_read(client, workspace, plan, report):
    set_plan(workspace, plan)

    assert client.get(url(report)).status_code == 200


@pytest.mark.parametrize("report", REPORTS)
def test_every_role_can_read(frozen, auth_client, report):
    assert auth_client(Role.VIEWER).get(url(report)).status_code == 200


def test_non_members_get_404(frozen, other_workspace, workspace):
    stranger = other_workspace.memberships.get().user

    response = make_api_client(stranger, workspace).get(url("overview"))

    assert response.status_code == 404


def test_commerce_report_needs_the_commerce_feature(client, workspace):
    drop_feature("growth", COMMERCE)

    response = client.get(url("commerce"))
    assert response.status_code == 409
    assert error(response)["code"] == "feature_not_available"
    assert error(response)["details"] == {"feature": COMMERCE}

    export = client.get(url("export", report="commerce"))
    assert export.status_code == 409
    assert error(export)["details"] == {"feature": COMMERCE}

    overview = client.get(url("overview")).json()
    assert overview["current"]["orders"] is None
    assert overview["current"]["revenue_paise"] is None
    assert overview["previous"]["orders"] is None


def test_overview_includes_orders_with_commerce(client):
    overview = client.get(url("overview")).json()

    assert overview["current"]["orders"] == 0
    assert overview["current"]["revenue_paise"] == 0


def test_tenant_isolation(client, workspace, other_workspace, conversation):
    theirs = ConversationFactory(workspace=other_workspace)
    message(theirs, "2026-03-14 10:00")
    message(theirs, "2026-03-14 10:00", inbound=True)
    phone = PhoneNumberFactory(waba__workspace=other_workspace)
    campaign = CampaignFactory(phone_number=phone, status="completed")
    backdate(campaign, local("2026-03-14 09:00"), "started_at")

    assert_tenant_isolated(client, object_id=campaign.pk, list_url=url("campaigns"))
    overview = client.get(url("overview")).json()["current"]
    assert overview["messages_sent"] == 0
    assert overview["messages_received"] == 0
    assert overview["conversations_started"] == 1  # only the fixture's own conversation
    assert overview["campaigns_sent"] == 0
    series = client.get(url("messages")).json()["series"]
    assert sum(point["sent"] + point["received"] for point in series) == 0
    team = client.get(url("team")).json()["results"]
    assert [row["email"] for row in team] == [workspace.memberships.get().user.email]


# --- ranges ------------------------------------------------------------------------------------


def test_default_range_is_the_last_30_days(client):
    body = client.get(url("overview")).json()

    assert body["range"] == {
        "from": "2026-02-14",
        "to": "2026-03-15",
        "time_zone": "Asia/Kolkata",
        "previous_from": "2026-01-15",
        "previous_to": "2026-02-13",
    }


def test_from_defaults_to_29_days_before_to(client):
    body = client.get(url("messages", to="2026-03-01")).json()

    assert body["range"]["from"] == "2026-01-31"
    assert len(body["series"]) == 30


def test_explicit_range_and_previous_period(client):
    body = client.get(url("overview", **{"from": "2026-03-10", "to": "2026-03-12"})).json()

    assert body["range"]["previous_from"] == "2026-03-07"
    assert body["range"]["previous_to"] == "2026-03-09"


def test_92_days_is_the_maximum(client):
    ok = client.get(url("overview", **{"from": "2025-12-14", "to": "2026-03-15"}))
    too_long = client.get(url("overview", **{"from": "2025-12-13", "to": "2026-03-15"}))

    assert ok.status_code == 200
    assert too_long.status_code == 400
    assert error(too_long)["code"] == "invalid"
    assert "from" in error(too_long)["details"]


def test_to_cannot_be_in_the_future(client):
    response = client.get(url("overview", to="2026-03-16"))

    assert response.status_code == 400
    assert error(response)["code"] == "invalid"
    assert "to" in error(response)["details"]


def test_today_uses_the_workspace_time_zone(time_machine, auth_client, workspace):
    # 20:00 UTC on the 15th is already the 16th in IST.
    time_machine.move_to(local("2026-03-16 01:30"), tick=False)
    client = auth_client()

    assert client.get(url("overview", to="2026-03-16")).status_code == 200

    workspace.time_zone = "UTC"
    workspace.save(update_fields=["time_zone"])
    assert client.get(url("overview", to="2026-03-16")).status_code == 400


def test_from_after_to_is_invalid(client):
    response = client.get(url("overview", **{"from": "2026-03-12", "to": "2026-03-10"}))

    assert response.status_code == 400
    assert "from" in error(response)["details"]


def test_malformed_dates_are_invalid(client):
    response = client.get(url("overview", **{"from": "yesterday"}))

    assert response.status_code == 400
    assert "from" in error(response)["details"]
