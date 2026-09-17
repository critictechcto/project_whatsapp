"""CSV export: validation, headers, filename, money columns and formula escaping."""

import csv
import io

import pytest

from apps.campaigns.factories import CampaignFactory
from apps.orders.factories import OrderFactory

from .helpers import backdate, local, message, url

pytestmark = pytest.mark.django_db

RANGE = {"from": "2026-03-09", "to": "2026-03-10"}


def rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))


@pytest.mark.parametrize("report", ["", "overview", "bogus"])
def test_missing_or_unknown_report_is_invalid(client, report):
    response = client.get(url("export", report=report) if report else url("export"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid"
    assert "report" in response.json()["error"]["details"]


def test_export_validates_the_range(client):
    response = client.get(url("export", report="messages", to="2026-04-01"))

    assert response.status_code == 400
    assert "to" in response.json()["error"]["details"]


def test_messages_csv(client, conversation):
    message(conversation, "2026-03-10 23:30", status="read")
    message(conversation, "2026-03-10 10:00", inbound=True)

    response = client.get(url("export", report="messages", **RANGE))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="upchatz-messages-2026-03-09-2026-03-10.csv"'
    )
    assert rows(response) == [
        ["date", "sent", "delivered", "read", "failed", "received"],
        ["2026-03-09", "0", "0", "0", "0", "0"],
        ["2026-03-10", "1", "1", "1", "0", "1"],
    ]


def test_accept_text_csv_is_not_rejected(client):
    response = client.get(url("export", report="team", **RANGE), HTTP_ACCEPT="text/csv")

    assert response.status_code == 200
    assert rows(response)[0] == [
        "user_id",
        "name",
        "email",
        "role",
        "messages_sent",
        "conversations_assigned",
        "conversations_closed",
    ]


def test_campaigns_csv_escapes_formulas(client, conversation):
    phone = conversation.phone_number
    for name in ('=HYPERLINK("http://evil")', "+91 offer", "-50% sale", "@team", "Holi sale"):
        campaign = CampaignFactory(phone_number=phone, name=name, status="completed")
        backdate(campaign, local("2026-03-10 10:00"), "started_at")

    response = client.get(url("export", report="campaigns", **RANGE))

    table = rows(response)
    assert table[0][:4] == ["id", "name", "status", "started_at"]
    assert table[0][-3:] == ["delivery_rate", "read_rate", "reply_rate"]
    assert sorted(row[1] for row in table[1:]) == sorted(
        ['\'=HYPERLINK("http://evil")', "'+91 offer", "'-50% sale", "'@team", "Holi sale"]
    )
    assert (
        response["Content-Disposition"]
        == 'attachment; filename="upchatz-campaigns-2026-03-09-2026-03-10.csv"'
    )


def test_templates_csv_headers(client, conversation):
    message(
        conversation,
        "2026-03-10 10:00",
        type="template",
        template_name="order_update",
        template_language="en",
        template_category="utility",
    )

    table = rows(client.get(url("export", report="templates", **RANGE)))

    assert table[0] == [
        "template_id",
        "name",
        "language",
        "category",
        "sent",
        "delivered",
        "read",
        "failed",
        "delivery_rate",
        "read_rate",
    ]
    assert table[1] == ["", "order_update", "en", "utility", "1", "0", "0", "0", "0.0000", ""]


def test_commerce_csv_has_rupees(client, workspace):
    order = OrderFactory(workspace=workspace, total_paise=123456, payment_status="paid")
    backdate(order, local("2026-03-10 10:00"))

    response = client.get(url("export", report="commerce", **RANGE))

    assert rows(response) == [
        ["date", "orders", "revenue_inr"],
        ["2026-03-09", "0", "0.00"],
        ["2026-03-10", "1", "1234.56"],
    ]
    assert response["Content-Disposition"].endswith(
        'filename="upchatz-commerce-2026-03-09-2026-03-10.csv"'
    )
