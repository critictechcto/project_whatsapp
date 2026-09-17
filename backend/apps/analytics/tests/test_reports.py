"""Report numbers: status definitions, time-zone days, series, breakdowns and each report."""

import pytest

from apps.automations.factories import AutomationRunFactory
from apps.campaigns.factories import CampaignFactory
from apps.catalog.factories import ProductFactory
from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory
from apps.message_templates.factories import MessageTemplateFactory
from apps.orders.factories import OrderFactory, OrderItemFactory
from apps.tenants.factories import MembershipFactory
from common.roles import Role

from .helpers import backdate, local, message, url

pytestmark = pytest.mark.django_db

MARCH_10 = {"from": "2026-03-10", "to": "2026-03-10"}


def point(series: list[dict], day: str) -> dict:
    return next(p for p in series if p["date"] == day)


def all_statuses(conversation, when: str) -> None:
    for status in ("queued", "sending", "sent", "delivered", "delivered", "read", "failed"):
        message(conversation, when, status=status)
    message(conversation, when, inbound=True)
    message(conversation, when, inbound=True)


def test_status_counting_definitions(client, conversation):
    all_statuses(conversation, "2026-03-10 11:00")

    current = client.get(url("overview", **MARCH_10)).json()["current"]

    assert current["messages_sent"] == 4  # sent + delivered x2 + read
    assert current["messages_delivered"] == 3
    assert current["messages_read"] == 1
    assert current["messages_failed"] == 1
    assert current["messages_received"] == 2
    assert current["delivery_rate"] == "0.7500"
    assert current["read_rate"] == "0.3333"


def test_rates_are_null_without_a_denominator(client, conversation):
    message(conversation, "2026-03-10 11:00", status="queued")

    current = client.get(url("overview", **MARCH_10)).json()["current"]

    assert current["messages_sent"] == 0
    assert current["delivery_rate"] is None
    assert current["read_rate"] is None


def test_time_zone_day_boundaries(client, workspace, conversation):
    message(conversation, "2026-03-10 23:30")  # 18:00 UTC, still the 10th in IST
    message(conversation, "2026-03-11 00:30")  # 19:00 UTC on the 10th, the 11th in IST
    message(conversation, "2026-03-09 23:59")

    body = client.get(url("messages", **{"from": "2026-03-09", "to": "2026-03-11"})).json()

    assert [p["sent"] for p in body["series"]] == [1, 1, 1]
    assert client.get(url("overview", **MARCH_10)).json()["current"]["messages_sent"] == 1

    workspace.time_zone = "UTC"
    workspace.save(update_fields=["time_zone"])
    body = client.get(url("messages", **{"from": "2026-03-09", "to": "2026-03-11"})).json()
    assert body["range"]["time_zone"] == "UTC"
    assert [p["sent"] for p in body["series"]] == [1, 2, 0]


def test_series_is_zero_filled_and_oldest_first(client, conversation):
    message(conversation, "2026-03-05 10:00", status="read")
    message(conversation, "2026-03-05 10:05", inbound=True)

    body = client.get(url("messages", **{"from": "2026-03-01", "to": "2026-03-07"})).json()

    assert [p["date"] for p in body["series"]] == [f"2026-03-0{day}" for day in range(1, 8)]
    assert point(body["series"], "2026-03-05") == {
        "date": "2026-03-05",
        "sent": 1,
        "delivered": 1,
        "read": 1,
        "failed": 0,
        "received": 1,
    }
    empty = point(body["series"], "2026-03-01")
    assert empty == {
        "date": "2026-03-01",
        "sent": 0,
        "delivered": 0,
        "read": 0,
        "failed": 0,
        "received": 0,
    }


def test_previous_period_totals(client, workspace, conversation):
    message(conversation, "2026-03-10 09:00")
    message(conversation, "2026-03-09 09:00")
    message(conversation, "2026-03-08 09:00", status="read")
    message(conversation, "2026-03-07 23:59")  # outside both periods
    backdate(ContactFactory(workspace=workspace), local("2026-03-08 12:00"))
    opted = ContactFactory(workspace=workspace, opted_in_at=local("2026-03-10 08:00"))
    backdate(opted, local("2026-02-01 12:00"))

    body = client.get(url("overview", **{"from": "2026-03-10", "to": "2026-03-11"})).json()

    assert body["current"]["messages_sent"] == 1
    assert body["current"]["contacts_opted_in"] == 1
    assert body["current"]["contacts_added"] == 0
    assert body["previous"]["messages_sent"] == 2
    assert body["previous"]["messages_read"] == 1
    assert body["previous"]["contacts_added"] == 1
    assert body["previous"]["read_rate"] == "1.0000"


def test_overview_counts_other_apps(client, workspace, conversation):
    backdate(conversation, local("2026-03-10 08:00"))
    backdate(
        ContactFactory(workspace=workspace, opted_out_at=local("2026-03-10 09:00")),
        local("2026-03-10 07:00"),
    )
    backdate(
        CampaignFactory(phone_number=conversation.phone_number),
        local("2026-03-10 10:00"),
        "started_at",
    )
    CampaignFactory(phone_number=conversation.phone_number)  # never started
    run = AutomationRunFactory(message__conversation=conversation)
    backdate(run, local("2026-03-10 11:00"))
    skipped = AutomationRunFactory(message__conversation=conversation, status="skipped")
    backdate(skipped, local("2026-03-10 11:00"))
    for status, payment, total in (
        ("confirmed", "paid", 50000),
        ("delivered", "cod_collected", 25000),
        ("pending_payment", "unpaid", 10000),
        ("draft", "unpaid", 99999),
    ):
        order = OrderFactory(
            workspace=workspace, status=status, payment_status=payment, total_paise=total
        )
        backdate(order, local("2026-03-10 12:00"))

    current = client.get(url("overview", **MARCH_10)).json()["current"]

    # Only the fixture conversation; the automation runs reuse it.
    assert current["conversations_started"] == 1
    assert current["contacts_added"] == 1
    assert current["contacts_opted_out"] == 1
    assert current["campaigns_sent"] == 1
    assert current["automation_runs"] == 1
    assert current["orders"] == 3
    assert current["revenue_paise"] == 75000


def test_messages_breakdowns(client, conversation):
    when = "2026-03-10 10:00"
    message(
        conversation,
        when,
        source="campaign",
        status="read",
        type="template",
        template_category="marketing",
    )
    message(
        conversation,
        when,
        source="campaign",
        status="failed",
        type="template",
        template_category="marketing",
        error_code="131049",
    )
    message(
        conversation,
        when,
        source="campaign",
        status="failed",
        type="template",
        template_category="marketing",
        error_code="131049",
    )
    message(
        conversation,
        when,
        source="automation",
        status="delivered",
        type="template",
        template_category="utility",
    )
    message(conversation, when, source="inbox", status="failed")
    message(conversation, when, inbound=True)

    body = client.get(url("messages", **MARCH_10)).json()

    assert body["by_source"] == [
        {
            "source": "automation",
            "sent": 1,
            "delivered": 1,
            "read": 0,
            "failed": 0,
            "delivery_rate": "1.0000",
            "read_rate": "0.0000",
        },
        {
            "source": "campaign",
            "sent": 1,
            "delivered": 1,
            "read": 1,
            "failed": 2,
            "delivery_rate": "1.0000",
            "read_rate": "1.0000",
        },
        {
            "source": "inbox",
            "sent": 0,
            "delivered": 0,
            "read": 0,
            "failed": 1,
            "delivery_rate": None,
            "read_rate": None,
        },
    ]
    assert body["by_category"] == [
        {"category": "marketing", "sent": 1, "delivered": 1, "read": 1, "failed": 2},
        {"category": "utility", "sent": 1, "delivered": 1, "read": 0, "failed": 0},
        {"category": "", "sent": 0, "delivered": 0, "read": 0, "failed": 1},
    ]
    assert body["failure_reasons"] == [
        {"error_code": "131049", "count": 2},
        {"error_code": "", "count": 1},
    ]


def test_templates_report(client, workspace, conversation):
    template = MessageTemplateFactory(
        waba=conversation.phone_number.waba,
        name="order_update",
        language="en_IN",
        category="utility",
    )
    when = "2026-03-10 10:00"
    fields = {
        "type": "template",
        "template_name": "order_update",
        "template_language": "en_IN",
        "template_category": "utility",
    }
    message(conversation, when, status="read", template=template, **fields)
    message(conversation, when, status="sent", **fields)
    gone = {
        "type": "template",
        "template_name": "diwali_offer",
        "template_language": "hi",
        "template_category": "marketing",
    }
    message(conversation, when, status="delivered", **gone)
    message(conversation, when, status="read")  # not a template

    results = client.get(url("templates", **MARCH_10)).json()["results"]

    assert results == [
        {
            "template_id": str(template.pk),
            "name": "order_update",
            "language": "en_IN",
            "category": "utility",
            "sent": 2,
            "delivered": 1,
            "read": 1,
            "failed": 0,
            "delivery_rate": "0.5000",
            "read_rate": "1.0000",
        },
        {
            "template_id": None,
            "name": "diwali_offer",
            "language": "hi",
            "category": "marketing",
            "sent": 1,
            "delivered": 1,
            "read": 0,
            "failed": 0,
            "delivery_rate": "1.0000",
            "read_rate": "0.0000",
        },
    ]


def test_campaigns_report(client, conversation):
    phone = conversation.phone_number
    older = CampaignFactory(
        phone_number=phone,
        name="Holi sale",
        status="completed",
        total_count=100,
        sent_count=90,
        delivered_count=80,
        read_count=40,
        failed_count=10,
        replied_count=8,
    )
    newer = CampaignFactory(phone_number=phone, name="Restock", status="running")
    outside = CampaignFactory(phone_number=phone, status="completed")
    backdate(older, local("2026-03-09 10:00"), "started_at")
    backdate(newer, local("2026-03-10 10:00"), "started_at")
    backdate(outside, local("2026-03-01 10:00"), "started_at")

    results = client.get(url("campaigns", **{"from": "2026-03-09", "to": "2026-03-10"})).json()[
        "results"
    ]

    assert [row["id"] for row in results] == [str(newer.pk), str(older.pk)]
    assert results[1] == {
        "id": str(older.pk),
        "name": "Holi sale",
        "status": "completed",
        "started_at": "2026-03-09T10:00:00+05:30",
        "total_count": 100,
        "sent_count": 90,
        "delivered_count": 80,
        "read_count": 40,
        "failed_count": 10,
        "replied_count": 8,
        "delivery_rate": "0.8889",
        "read_rate": "0.5000",
        "reply_rate": "0.1000",
    }
    assert results[0]["delivery_rate"] is None


def test_team_report(client, workspace, user, conversation):
    user.full_name = "Zoya Khan"
    user.save(update_fields=["full_name"])
    agent = MembershipFactory(
        workspace=workspace, role=Role.AGENT, user__full_name="Arjun Mehta"
    ).user
    viewer = MembershipFactory(
        workspace=workspace, role=Role.VIEWER, user__full_name="Bina Rao"
    ).user
    when = "2026-03-10 10:00"
    message(conversation, when, sent_by=agent)
    message(conversation, when, sent_by=agent)
    message(conversation, when, sent_by=agent, source="campaign")  # not an inbox reply
    message(conversation, "2026-03-01 10:00", sent_by=agent)  # outside the range
    message(conversation, when, sent_by=user)
    for status in ("open", "closed", "closed"):
        other = ConversationFactory(workspace=workspace, assignee=agent, status=status)
        backdate(other, local(when), "last_message_at")
    stale = ConversationFactory(workspace=workspace, assignee=agent, status="closed")
    backdate(stale, local("2026-03-01 10:00"), "last_message_at")

    results = client.get(url("team", **MARCH_10)).json()["results"]

    assert results == [
        {
            "user_id": str(agent.pk),
            "name": "Arjun Mehta",
            "email": agent.email,
            "role": "agent",
            "messages_sent": 2,
            "conversations_assigned": 3,
            "conversations_closed": 2,
        },
        {
            "user_id": str(user.pk),
            "name": "Zoya Khan",
            "email": user.email,
            "role": "owner",
            "messages_sent": 1,
            "conversations_assigned": 0,
            "conversations_closed": 0,
        },
        {
            "user_id": str(viewer.pk),
            "name": "Bina Rao",
            "email": viewer.email,
            "role": "viewer",
            "messages_sent": 0,
            "conversations_assigned": 0,
            "conversations_closed": 0,
        },
    ]


def test_commerce_report(client, workspace):
    kaju = ProductFactory(workspace=workspace, name="Kaju Katli 250 g")
    rows = (
        ("2026-03-09 10:00", "confirmed", "paid", "online", 60000),
        ("2026-03-10 23:30", "delivered", "cod_collected", "cod", 30000),
        ("2026-03-10 09:00", "pending_payment", "unpaid", "online", 20000),
        ("2026-03-10 09:00", "cancelled", "unpaid", "", 5000),
        ("2026-03-10 09:00", "draft", "unpaid", "", 99900),
    )
    orders = []
    for when, status, payment, method, total in rows:
        order = OrderFactory(
            workspace=workspace,
            status=status,
            payment_status=payment,
            payment_method=method,
            total_paise=total,
        )
        orders.append(backdate(order, local(when)))
    OrderItemFactory(
        order=orders[0], product=kaju, name="Kaju Katli 250 g", quantity=2, unit_price_paise=24900
    )
    OrderItemFactory(
        order=orders[1], product=kaju, name="Kaju Katli", quantity=1, unit_price_paise=24900
    )
    OrderItemFactory(
        order=orders[1], product=None, name="Gift box", quantity=1, unit_price_paise=5100
    )
    OrderItemFactory(order=orders[2], product=kaju, quantity=5, unit_price_paise=4000)  # unpaid

    body = client.get(url("commerce", **{"from": "2026-03-08", "to": "2026-03-10"})).json()

    assert body["series"] == [
        {"date": "2026-03-08", "orders": 0, "revenue_paise": 0},
        {"date": "2026-03-09", "orders": 1, "revenue_paise": 60000},
        {"date": "2026-03-10", "orders": 3, "revenue_paise": 30000},
    ]
    assert body["orders"] == 4
    assert body["paid_orders"] == 2
    assert body["revenue_paise"] == 90000
    assert body["average_order_paise"] == 45000
    assert body["by_status"] == [
        {"status": "cancelled", "count": 1},
        {"status": "confirmed", "count": 1},
        {"status": "delivered", "count": 1},
        {"status": "pending_payment", "count": 1},
    ]
    assert body["by_payment_method"] == [
        {"payment_method": "online", "orders": 2, "revenue_paise": 60000},
        {"payment_method": "", "orders": 1, "revenue_paise": 0},
        {"payment_method": "cod", "orders": 1, "revenue_paise": 30000},
    ]
    assert body["top_products"] == [
        {
            "product_id": str(kaju.pk),
            "name": "Kaju Katli 250 g",
            "quantity": 3,
            "revenue_paise": 74700,
        },
        {"product_id": None, "name": "Gift box", "quantity": 1, "revenue_paise": 5100},
    ]


def test_commerce_average_is_null_without_paid_orders(client):
    body = client.get(url("commerce")).json()

    assert body["orders"] == 0
    assert body["average_order_paise"] is None
    assert len(body["series"]) == 30


def test_reports_are_cached_briefly(client, conversation):
    message(conversation, "2026-03-10 10:00")
    first = client.get(url("overview", **MARCH_10)).json()
    message(conversation, "2026-03-10 11:00")

    assert client.get(url("overview", **MARCH_10)).json() == first
