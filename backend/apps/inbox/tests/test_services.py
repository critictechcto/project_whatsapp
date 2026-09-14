from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.factories import UserFactory
from apps.inbox import services
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Conversation, ConversationNote
from apps.tenants.factories import MembershipFactory
from apps.whatsapp.client.errors import InvalidParameterError
from apps.whatsapp.models import WhatsAppBusinessAccount

pytestmark = pytest.mark.django_db


def test_assign_and_unassign(conversation, workspace, user):
    agent = MembershipFactory(workspace=workspace).user

    result = services.assign(conversation, agent, actor=user)
    assert result.assignee == agent
    assert Conversation.objects.get(pk=conversation.pk).assignee == agent

    result = services.assign(conversation, None, actor=user)
    assert result.assignee is None


def test_assignee_must_be_a_workspace_member(conversation, other_workspace, user):
    outsider = UserFactory()
    member_elsewhere = MembershipFactory(workspace=other_workspace).user

    for candidate in (outsider, member_elsewhere):
        with pytest.raises(ValidationError) as exc_info:
            services.assign(conversation, candidate, actor=user)
        assert "assignee_id" in exc_info.value.detail

    conversation.refresh_from_db()
    assert conversation.assignee is None


def test_close_and_reopen(conversation, user):
    assert services.close(conversation, actor=user).status == Conversation.Status.CLOSED
    assert services.close(conversation, actor=user).status == Conversation.Status.CLOSED
    assert services.reopen(conversation, actor=user).status == Conversation.Status.OPEN
    assert Conversation.objects.get(pk=conversation.pk).status == Conversation.Status.OPEN


def test_add_note(conversation, user):
    note = services.add_note(conversation, "  Customer prefers Hindi.  ", author=user)

    assert note.body == "Customer prefers Hindi."
    assert (note.author, note.conversation) == (user, conversation)
    assert note.workspace_id == conversation.workspace_id
    assert ConversationNote.objects.filter(conversation=conversation).count() == 1


def test_blank_note_is_invalid(conversation, user):
    with pytest.raises(ValidationError) as exc_info:
        services.add_note(conversation, "   ", author=user)

    assert "body" in exc_info.value.detail


def test_mark_read_sends_a_receipt_for_the_latest_inbound(conversation, fake_graph, user):
    now = timezone.now()
    MessageFactory(conversation=conversation, inbound=True, sent_at=now - timedelta(hours=2))
    latest = MessageFactory(
        conversation=conversation, inbound=True, sent_at=now - timedelta(minutes=1)
    )
    MessageFactory(conversation=conversation)  # outbound, newer
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=2)

    result = services.mark_read(conversation, actor=user)

    assert result.unread_count == 0
    [call] = fake_graph.calls_to("mark_read")
    assert call.kwargs == {
        "phone_number_id": conversation.phone_number.phone_number_id,
        "wamid": latest.wamid,
        "typing_indicator": False,
    }


def test_mark_read_without_unread_messages_sends_nothing(conversation, fake_graph, user):
    MessageFactory(conversation=conversation, inbound=True)

    services.mark_read(conversation, actor=user)

    assert fake_graph.calls_to("mark_read") == []


def test_mark_read_tolerates_graph_errors(conversation, fake_graph, user):
    MessageFactory(conversation=conversation, inbound=True)
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=1)
    fake_graph.fail("mark_read", InvalidParameterError("Message too old", code=100))

    result = services.mark_read(conversation, actor=user)

    assert result.unread_count == 0


def test_mark_read_on_disconnected_account_only_resets(conversation, fake_graph, user):
    MessageFactory(conversation=conversation, inbound=True)
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=3)
    waba = conversation.phone_number.waba
    waba.status = WhatsAppBusinessAccount.Status.DISCONNECTED
    waba.save()

    result = services.mark_read(conversation, actor=user)

    assert result.unread_count == 0
    assert fake_graph.calls_to("mark_read") == []
