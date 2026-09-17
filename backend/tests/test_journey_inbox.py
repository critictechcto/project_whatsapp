"""Journey: a customer writes in, the team answers inside the 24-hour window, falls back to a
template after it, assigns, notes and closes the chat; STOP opts the customer out; Meta's retries
change nothing."""

from datetime import timedelta

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.contacts.models import ConsentEvent
from apps.inbox.models import Message
from apps.webhooks.models import WebhookEvent

from .conftest import CUSTOMER_WA_ID, status_update
from .test_journey_support import (
    Customer,
    approved_template,
    error,
    invite_and_join,
    log_in_again,
    now_ts,
    ok,
    results,
)

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db

CONVERSATIONS = "/api/v1/inbox/conversations/"


def test_inbox_conversation_through_the_service_window(
    seller_api, seller_number_id, customer, deliver_meta, fake_graph, run_on_commit, time_machine
):
    agent = invite_and_join(
        seller_api, run_on_commit, email="meera@sharmasweets.in", full_name="Meera", role="agent"
    )
    viewer = invite_and_join(
        seller_api, run_on_commit, email="audit@sharmasweets.in", full_name="Audit", role="viewer"
    )
    reminder = approved_template(
        seller_api,
        deliver_meta,
        name="order_follow_up",
        body="Hi {{1}}, your order {{2}} is ready for pickup.",
    )

    # 1. The customer writes in: a conversation opens with a 24-hour window.
    sent_at = now_ts()
    first = customer.says("Namaste, is kaju katli available today?", timestamp=sent_at)
    [conversation] = results(agent.get(CONVERSATIONS))
    url = f"{CONVERSATIONS}{conversation['id']}/"
    assert conversation["status"] == "open"
    assert conversation["window_open"] is True
    assert conversation["unread_count"] == 1
    assert conversation["contact"]["phone_e164"] == f"+{CUSTOMER_WA_ID}"
    assert conversation["phone_number"]["id"] == seller_number_id
    expires = parse_datetime(conversation["service_window_expires_at"])
    assert expires.timestamp() == sent_at + 24 * 3600
    assert conversation["last_message"]["direction"] == "inbound"

    # Meta retries the same delivery: nothing is stored twice.
    deliver_meta(first)
    assert len(results(agent.get(f"{url}messages/"))) == 1
    assert ok(agent.get(url))["unread_count"] == 1

    # 2. The agent reads and replies with text (a double-click sends once).
    read = ok(agent.post(f"{url}read/"))
    assert read["unread_count"] == 0
    assert fake_graph.calls_to("mark_read")
    reply = {"type": "text", "text": "Yes! Fresh batch at 11 am."}
    headers = {"Idempotency-Key": "reply-1"}
    created = ok(agent.post(f"{url}messages/", reply, headers=headers), 201)
    again = ok(agent.post(f"{url}messages/", reply, headers=headers), 201)
    assert created["id"] == again["id"]
    assert created["status"] == "queued"
    assert created["source"] == "inbox"
    texts = [m for m in fake_graph.sent_messages if m["type"] == "text"]
    assert [(m["to"], m["text"]["body"]) for m in texts] == [(CUSTOMER_WA_ID, reply["text"])]
    [latest, _] = results(agent.get(f"{url}messages/"))
    assert (latest["id"], latest["status"], latest["sent_by"]["full_name"]) == (
        created["id"],
        "sent",
        "Meera",
    )

    deliver_meta(status_update(latest["wamid"], "delivered", now_ts(), wa_id=CUSTOMER_WA_ID))
    deliver_meta(status_update(latest["wamid"], "read", now_ts() + 1, wa_id=CUSTOMER_WA_ID))
    assert results(agent.get(f"{url}messages/"))[0]["status"] == "read"

    # Viewers read but never write.
    assert ok(viewer.get(url))["id"] == conversation["id"]
    error(viewer.post(f"{url}messages/", reply), 403, "insufficient_role")

    # 3. A day later the window has closed: free text is refused, an approved template works.
    time_machine.move_to(timezone.now() + timedelta(hours=25))
    log_in_again(seller_api, agent, viewer)
    assert ok(agent.get(url))["window_open"] is False
    error(agent.post(f"{url}messages/", reply), 409, "outside_service_window")
    template_message = ok(
        agent.post(
            f"{url}messages/",
            {
                "type": "template",
                "template_id": reminder["id"],
                "body_params": ["Priya", "SS-1001"],
            },
        ),
        201,
    )
    assert template_message["type"] == "template"
    [template_send] = [m for m in fake_graph.sent_messages if m["type"] == "template"]
    assert template_send["template"]["name"] == "order_follow_up"
    assert results(agent.get(f"{url}messages/"))[0]["status"] == "sent"

    # 4. Assign, note, close.
    me = ok(agent.get("/api/v1/auth/me/"))
    assigned = ok(agent.post(f"{url}assign/", {"assignee_id": me["id"]}))
    assert assigned["assignee"]["email"] == "meera@sharmasweets.in"
    assert [c["id"] for c in results(agent.get(CONVERSATIONS, {"assignee": "me"}))] == [
        conversation["id"]
    ]
    assert results(seller_api.get(CONVERSATIONS, {"assignee": "me"})) == []
    note = ok(agent.post(f"{url}notes/", {"body": "Wants 2 kg for Diwali, call back."}), 201)
    assert note["author"]["email"] == "meera@sharmasweets.in"
    assert [n["body"] for n in results(viewer.get(f"{url}notes/"))] == [note["body"]]
    closed = ok(agent.post(f"{url}close/"))
    assert closed["status"] == "closed"
    assert results(agent.get(CONVERSATIONS, {"status": "open"})) == []

    # 5. The customer texts STOP: opted out, the chat reopens with a fresh window.
    stop = customer.says("STOP")
    conversation = ok(agent.get(url))
    assert (conversation["status"], conversation["window_open"]) == ("open", True)
    assert conversation["contact"]["marketing_opt_in_status"] == "opted_out"
    error(
        agent.post(
            f"{url}messages/",
            {"type": "template", "template_id": reminder["id"], "body_params": ["Priya", "1"]},
        ),
        409,
        "contact_opted_out",
    )

    # A retry of the STOP delivery changes nothing.
    messages_before = Message.objects.count()
    deliver_meta(stop)
    assert Message.objects.count() == messages_before
    contact_id = conversation["contact"]["id"]
    assert ConsentEvent.objects.filter(contact_id=contact_id).count() == 1
    assert set(WebhookEvent.objects.values_list("status", flat=True)) == {"processed"}

    # Writing again after STOP lets the team reply in the window, but templates stay blocked.
    time_machine.move_to(timezone.now() + timedelta(minutes=2))
    log_in_again(agent)
    customer.says("Sorry, wrong button. Is the shop open tomorrow?")
    ok(agent.post(f"{url}messages/", {"type": "text", "text": "Yes, 9 am to 9 pm."}), 201)
    assert results(agent.get(f"{url}messages/"))[0]["status"] == "sent"


def test_removing_a_member_returns_their_chats_to_the_unassigned_queue(
    seller_api, customer, run_on_commit
):
    agent = invite_and_join(
        seller_api, run_on_commit, email="meera@sharmasweets.in", full_name="Meera", role="agent"
    )
    customer.says("Namaste, I need 2 kg kaju katli for Friday.")
    Customer(customer.deliver, wa_id="919812345699", name="Rohan").says("Hello")
    conversations = results(agent.get(CONVERSATIONS))
    assert len(conversations) == 2
    me = ok(agent.get("/api/v1/auth/me/"))
    for conversation in conversations:
        ok(agent.post(f"{CONVERSATIONS}{conversation['id']}/assign/", {"assignee_id": me["id"]}))
    assert results(seller_api.get(CONVERSATIONS, {"assignee": "none"})) == []

    [membership] = [
        m
        for m in results(seller_api.get("/api/v1/workspaces/members/"))
        if m["user"]["id"] == me["id"]
    ]
    ok(seller_api.delete(f"/api/v1/workspaces/members/{membership['id']}/"), 204)

    # Nobody left in the workspace owns those chats any more: they're back in the queue.
    assert results(seller_api.get(CONVERSATIONS, {"assignee": me["id"]})) == []
    unassigned = results(seller_api.get(CONVERSATIONS, {"assignee": "none"}))
    assert sorted(c["id"] for c in unassigned) == sorted(c["id"] for c in conversations)
    assert all(c["assignee"] is None for c in unassigned)
