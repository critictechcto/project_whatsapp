import pytest

from apps.inbox import demo
from apps.inbox.models import Conversation, Message
from apps.tenants.factories import WorkspaceFactory
from common.roles import Role

pytestmark = pytest.mark.django_db


def counts(workspace):
    return (
        Conversation.objects.filter(workspace=workspace).count(),
        Message.objects.filter(workspace=workspace).count(),
    )


def test_seed_creates_a_varied_inbox(workspace, number, user, fake_graph, auth_client):
    demo.seed(workspace)

    conversations = Conversation.objects.filter(workspace=workspace)
    assert conversations.count() == len(demo.DEMO_CONVERSATIONS)
    assert set(conversations.values_list("status", flat=True)) == {"open", "pending", "closed"}
    assert list(conversations.exclude(assignee=None).values_list("assignee", flat=True)) == [
        user.pk
    ]
    assert conversations.filter(unread_count__gt=0).exists()
    statuses = set(Message.objects.filter(workspace=workspace).values_list("status", flat=True))
    assert statuses == {"queued", "sent", "delivered", "read", "failed", "received"}
    assert set(Message.objects.values_list("direction", flat=True)) == {"inbound", "outbound"}
    assert Message.objects.filter(type="template", template_name="order_shipped").exists()
    assert fake_graph.calls == []

    body = auth_client(Role.VIEWER).get("/api/v1/inbox/conversations/").json()
    by_name = {item["contact"]["name"]: item for item in body["results"]}
    assert by_name["Priya Sharma"]["window_open"] is True
    assert by_name["Priya Sharma"]["assignee"]["id"] == str(user.pk)
    assert by_name["Ananya Iyer"]["status"] == "closed"
    assert by_name["Ananya Iyer"]["window_open"] is False
    assert by_name["Sneha Patel"]["last_message"]["status"] == "queued"


def test_seed_is_idempotent_and_scoped_per_workspace(workspace, number):
    from apps.whatsapp.factories import PhoneNumberFactory

    demo.seed(workspace)
    first = counts(workspace)
    demo.seed(workspace)

    assert counts(workspace) == first

    other = WorkspaceFactory()
    PhoneNumberFactory(workspace=other, waba__workspace=other, is_default=True)
    demo.seed(other)
    assert counts(other) == first


def test_seed_without_a_phone_number_does_nothing(workspace):
    demo.seed(workspace)

    assert counts(workspace) == (0, 0)
