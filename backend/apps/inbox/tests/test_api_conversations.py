"""Inbox API: conversations (list, filters, pagination, get-or-create, assign/close/reopen/read)."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.contacts.factories import ContactFactory
from apps.inbox.factories import ConversationFactory, MessageFactory
from apps.inbox.models import Conversation, Message
from apps.tenants.factories import MembershipFactory
from apps.whatsapp.factories import PhoneNumberFactory
from common.roles import Role
from common.testing import assert_tenant_isolated, make_api_client

pytestmark = pytest.mark.django_db

BASE = "/api/v1/inbox/conversations/"


def detail(conversation, suffix=""):
    return f"{BASE}{conversation.pk}/{suffix}"


def ids(response) -> list[str]:
    assert response.status_code == 200, response.content
    return [item["id"] for item in response.json()["results"]]


@pytest.fixture
def frames(monkeypatch):
    """Realtime frames sent (after commit) during the test, as ``(group, frame)``."""
    from common import realtime

    sent: list = []
    monkeypatch.setattr(realtime, "_send", lambda group, frame: sent.append((group, frame)))
    return sent


# --- Access -------------------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["", "messages/", "notes/"])
def test_viewer_can_read(auth_client, conversation, suffix):
    client = auth_client(Role.VIEWER)

    assert client.get(detail(conversation, suffix)).status_code == 200
    assert client.get(BASE).status_code == 200


WRITES = [
    ("assign/", {"assignee_id": None}),
    ("close/", {}),
    ("reopen/", {}),
    ("read/", {}),
    ("messages/", {"type": "text", "text": "Hello"}),
    ("notes/", {"body": "Called the customer"}),
]


@pytest.mark.parametrize(("suffix", "body"), WRITES)
def test_writes_need_agent(auth_client, conversation, fake_graph, suffix, body):
    response = auth_client(Role.VIEWER).post(detail(conversation, suffix), body, format="json")
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "insufficient_role"

    response = auth_client(Role.AGENT).post(detail(conversation, suffix), body, format="json")
    assert response.status_code in (200, 201), response.content


def test_start_conversation_needs_agent(auth_client, contact, number):
    response = auth_client(Role.VIEWER).post(BASE, {"contact_id": str(contact.pk)}, format="json")

    assert response.status_code == 403


@pytest.mark.parametrize("suffix", ["", "messages/", "notes/"])
def test_tenant_isolation(auth_client, other_workspace, conversation, suffix):
    outsider = auth_client(workspace=other_workspace)

    assert_tenant_isolated(
        outsider,
        object_id=conversation.pk,
        list_url=BASE if suffix == "" else None,
        detail_url=detail(conversation, suffix),
    )


def test_writes_on_another_workspace_conversation_are_404(auth_client, other_workspace):
    foreign = ConversationFactory(workspace=other_workspace, window_open=True)
    client = auth_client(Role.ADMIN)

    for suffix, body in WRITES:
        response = client.post(detail(foreign, suffix), body, format="json")
        assert response.status_code == 404, (suffix, response.content)


def test_non_member_gets_404(user, other_workspace):
    response = make_api_client(user, other_workspace).get(BASE)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_anonymous_gets_401(workspace):
    assert make_api_client(None, workspace).get(BASE).status_code == 401


# --- List ---------------------------------------------------------------------------------------


def test_list_shape(auth_client, conversation, user, workspace):
    Conversation.objects.filter(pk=conversation.pk).update(assignee=user, unread_count=2)
    MessageFactory(conversation=conversation, inbound=True, text="Is it in stock?")
    latest = MessageFactory(conversation=conversation, text="x" * 500, status=Message.Status.READ)

    [item] = auth_client(Role.VIEWER).get(BASE).json()["results"]

    contact = conversation.contact
    phone = conversation.phone_number
    assert item["id"] == str(conversation.pk)
    assert item["contact"] == {
        "id": str(contact.pk),
        "name": contact.name,
        "phone_e164": contact.phone_e164,
        "marketing_opt_in_status": contact.marketing_opt_in_status,
    }
    assert item["phone_number"] == {
        "id": str(phone.pk),
        "display_phone_number": phone.display_phone_number,
        "verified_name": phone.verified_name,
    }
    assert item["assignee"] == {
        "id": str(user.pk),
        "full_name": user.full_name,
        "email": user.email,
    }
    assert item["status"] == "open"
    assert item["unread_count"] == 2
    assert item["window_open"] is True
    assert item["last_message"]["direction"] == "outbound"
    assert item["last_message"]["status"] == "read"
    assert item["last_message"]["type"] == "text"
    assert item["last_message"]["text"] == "x" * 200
    assert item["last_message"]["created_at"] is not None
    latest.refresh_from_db()
    assert item["last_message"]["created_at"].startswith(
        latest.created_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%dT%H:%M")
    )


def test_window_closed_and_no_messages(auth_client, workspace, number):
    ConversationFactory(workspace=workspace, phone_number=number)

    [item] = auth_client().get(BASE).json()["results"]

    assert item["window_open"] is False
    assert item["last_message"] is None
    assert item["assignee"] is None


def test_list_runs_a_constant_number_of_queries(
    auth_client, workspace, number, django_assert_max_num_queries
):
    client = auth_client(Role.VIEWER)

    def add(count):
        for _ in range(count):
            conversation = ConversationFactory(
                workspace=workspace,
                phone_number=number,
                assignee=MembershipFactory(workspace=workspace).user,
                window_open=True,
            )
            MessageFactory(conversation=conversation)
            MessageFactory(conversation=conversation, inbound=True)

    add(2)
    with django_assert_max_num_queries(3):
        assert len(ids(client.get(BASE))) == 2
    add(10)
    with django_assert_max_num_queries(3):
        assert len(ids(client.get(BASE))) == 12


def test_ordered_by_latest_activity_with_created_at_fallback(auth_client, workspace, number):
    now = timezone.now()
    older = ConversationFactory(
        workspace=workspace, phone_number=number, last_message_at=now - timedelta(hours=3)
    )
    newer = ConversationFactory(
        workspace=workspace, phone_number=number, last_message_at=now - timedelta(hours=1)
    )
    fresh = ConversationFactory(workspace=workspace, phone_number=number)  # no messages yet
    stale_empty = ConversationFactory(workspace=workspace, phone_number=number)
    Conversation.objects.filter(pk=stale_empty.pk).update(created_at=now - timedelta(days=2))

    assert ids(auth_client().get(BASE)) == [
        str(fresh.pk),
        str(newer.pk),
        str(older.pk),
        str(stale_empty.pk),
    ]


def test_cursor_pagination_walks_every_conversation_once(auth_client, workspace, number):
    moment = timezone.now() - timedelta(minutes=5)
    conversations = [
        ConversationFactory(
            workspace=workspace,
            phone_number=number,
            # Ties on the ordering field must still paginate without gaps or repeats.
            last_message_at=moment if index % 2 else moment - timedelta(minutes=index),
        )
        for index in range(7)
    ]
    ConversationFactory(workspace=workspace, phone_number=number)  # null last_message_at
    client = auth_client()

    seen: list[str] = []
    url = f"{BASE}?page_size=2"
    while url:
        body = client.get(url).json()
        assert len(body["results"]) <= 2
        seen.extend(item["id"] for item in body["results"])
        url = body["next"]

    assert len(seen) == len(set(seen)) == len(conversations) + 1
    assert seen == ids(client.get(f"{BASE}?page_size=50"))


# --- Filters ------------------------------------------------------------------------------------


@pytest.fixture
def people(workspace, number):
    priya = ContactFactory(workspace=workspace, name="Priya Sharma", phone_e164="+919812345601")
    rahul = ContactFactory(workspace=workspace, name="Rahul Verma", phone_e164="+919812345602")
    return {
        "priya": ConversationFactory(workspace=workspace, contact=priya, phone_number=number),
        "rahul": ConversationFactory(workspace=workspace, contact=rahul, phone_number=number),
    }


def filtered(client, query: str) -> set[str]:
    return set(ids(client.get(f"{BASE}?{query}")))


def test_filter_by_status(auth_client, people):
    Conversation.objects.filter(pk=people["rahul"].pk).update(status=Conversation.Status.CLOSED)
    client = auth_client()

    assert filtered(client, "status=closed") == {str(people["rahul"].pk)}
    assert filtered(client, "status=open") == {str(people["priya"].pk)}
    assert client.get(f"{BASE}?status=archived").status_code == 400


def test_filter_by_assignee(auth_client, people, workspace):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT).user
    client = auth_client(Role.AGENT, user=agent)
    Conversation.objects.filter(pk=people["priya"].pk).update(assignee=agent)

    assert filtered(client, "assignee=me") == {str(people["priya"].pk)}
    assert filtered(client, "assignee=none") == {str(people["rahul"].pk)}
    assert filtered(client, f"assignee={agent.pk}") == {str(people["priya"].pk)}
    assert filtered(client, f"assignee={uuid.uuid4()}") == set()
    response = client.get(f"{BASE}?assignee=someone")
    assert response.status_code == 400
    assert "assignee" in response.json()["error"]["details"]


def test_filter_by_phone_number(auth_client, people, workspace):
    second = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)
    other = ConversationFactory(
        workspace=workspace, contact=people["priya"].contact, phone_number=second
    )
    client = auth_client()

    assert filtered(client, f"phone_number={second.pk}") == {str(other.pk)}
    assert client.get(f"{BASE}?phone_number=nope").status_code == 400


def test_filter_by_unread(auth_client, people):
    Conversation.objects.filter(pk=people["priya"].pk).update(unread_count=3)
    client = auth_client()

    assert filtered(client, "unread=true") == {str(people["priya"].pk)}
    assert filtered(client, "unread=false") == {str(people["rahul"].pk)}
    assert client.get(f"{BASE}?unread=maybe").status_code == 400


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("priya", {"priya"}),
        ("VERMA", {"rahul"}),
        ("+919812345602", {"rahul"}),
        ("98123 45602", {"rahul"}),
        ("098123-45601", {"priya"}),
        ("45601", {"priya"}),
        ("98123", {"priya", "rahul"}),
        ("nobody", set()),
    ],
)
def test_search_by_name_or_phone(auth_client, people, search, expected):
    from urllib.parse import quote

    result = filtered(auth_client(), f"search={quote(search)}")

    assert result == {str(people[name].pk) for name in expected}


# --- Detail and create --------------------------------------------------------------------------


def test_retrieve(auth_client, conversation):
    response = auth_client(Role.VIEWER).get(detail(conversation))

    assert response.status_code == 200
    assert response.json()["id"] == str(conversation.pk)


def test_retrieve_unknown_is_404(auth_client):
    assert auth_client().get(f"{BASE}{uuid.uuid4()}/").status_code == 404


def test_start_conversation_get_or_create(
    auth_client, workspace, number, frames, django_capture_on_commit_callbacks
):
    contact = ContactFactory(workspace=workspace)
    client = auth_client(Role.AGENT)

    with django_capture_on_commit_callbacks(execute=True):
        created = client.post(BASE, {"contact_id": str(contact.pk)}, format="json")
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["contact"]["id"] == str(contact.pk)
    assert body["phone_number"]["id"] == str(number.pk)
    assert body["window_open"] is False
    assert [frame["type"] for _, frame in frames] == ["conversation.updated"]
    assert frames[0][1]["data"] == {"conversation_id": body["id"]}

    again = client.post(BASE, {"contact_id": str(contact.pk)}, format="json")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert Conversation.objects.filter(contact=contact).count() == 1


def test_start_conversation_on_an_explicit_number(auth_client, workspace, contact, number):
    second = PhoneNumberFactory(workspace=workspace, waba__workspace=workspace)

    response = auth_client(Role.AGENT).post(
        BASE, {"contact_id": str(contact.pk), "phone_number_id": str(second.pk)}, format="json"
    )

    assert response.status_code == 201
    assert response.json()["phone_number"]["id"] == str(second.pk)


def test_start_conversation_validation(auth_client, workspace, other_workspace, number):
    client = auth_client(Role.AGENT)
    foreign_contact = ContactFactory(workspace=other_workspace)
    foreign_number = PhoneNumberFactory(workspace=other_workspace, waba__workspace=other_workspace)
    contact = ContactFactory(workspace=workspace)

    cases = [
        ({}, "contact_id"),
        ({"contact_id": str(uuid.uuid4())}, "contact_id"),
        ({"contact_id": str(foreign_contact.pk)}, "contact_id"),
        (
            {"contact_id": str(contact.pk), "phone_number_id": str(foreign_number.pk)},
            "phone_number_id",
        ),
    ]
    for body, field in cases:
        response = client.post(BASE, body, format="json")
        assert response.status_code == 400, body
        assert field in response.json()["error"]["details"]


def test_start_conversation_without_a_default_number(auth_client, workspace):
    contact = ContactFactory(workspace=workspace)

    response = auth_client(Role.AGENT).post(BASE, {"contact_id": str(contact.pk)}, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "whatsapp_not_connected"


# --- Actions ------------------------------------------------------------------------------------


def test_assign_and_unassign(
    auth_client, conversation, workspace, frames, django_capture_on_commit_callbacks
):
    agent = MembershipFactory(workspace=workspace, role=Role.AGENT).user
    client = auth_client(Role.AGENT)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            detail(conversation, "assign/"), {"assignee_id": str(agent.pk)}, format="json"
        )
    assert response.status_code == 200, response.content
    assert response.json()["assignee"]["id"] == str(agent.pk)
    assert ("ws." + str(workspace.pk), frames[0][1]) == frames[0]
    assert frames[0][1]["type"] == "conversation.updated"

    response = client.post(detail(conversation, "assign/"), {"assignee_id": None}, format="json")
    assert response.status_code == 200
    assert response.json()["assignee"] is None


@pytest.mark.parametrize("who", ["stranger", "unknown", "other_member"])
def test_assignee_must_be_a_member(auth_client, conversation, other_workspace, who):
    assignee_id = {
        "stranger": lambda: UserFactory().pk,
        "unknown": uuid.uuid4,
        "other_member": lambda: MembershipFactory(workspace=other_workspace).user_id,
    }[who]()

    response = auth_client(Role.AGENT).post(
        detail(conversation, "assign/"), {"assignee_id": str(assignee_id)}, format="json"
    )

    assert response.status_code == 400
    assert "assignee_id" in response.json()["error"]["details"]


def test_close_and_reopen(auth_client, conversation):
    client = auth_client(Role.AGENT)

    response = client.post(detail(conversation, "close/"))
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert filtered(client, "status=closed") == {str(conversation.pk)}

    response = client.post(detail(conversation, "reopen/"))
    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_read_resets_unread_and_sends_a_receipt(auth_client, conversation, fake_graph):
    inbound = MessageFactory(conversation=conversation, inbound=True)
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=4)

    response = auth_client(Role.AGENT).post(detail(conversation, "read/"))

    assert response.status_code == 200
    assert response.json()["unread_count"] == 0
    [call] = fake_graph.calls_to("mark_read")
    assert call.kwargs["wamid"] == inbound.wamid
