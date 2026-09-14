"""Realtime frames sent on commit by inbox events, services and membership changes."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.inbox import sending, services
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Conversation, Message
from apps.tenants import services as tenant_services
from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common import realtime
from common.events import (
    InboundMessage,
    MessageStatus,
    emit,
    inbound_message_received,
    message_status_updated,
)
from common.roles import Role

pytestmark = pytest.mark.django_db


@pytest.fixture
def frames(monkeypatch):
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(realtime, "_send", lambda group, frame: sent.append((group, frame)))
    return sent


def of_type(frames, frame_type):
    return [(group, frame) for group, frame in frames if frame["type"] == frame_type]


def test_outbound_send_broadcasts_created_updated_and_status(
    workspace, contact, conversation, fake_graph, frames, commit
):
    with commit():
        message = sending.send_message(
            workspace=workspace,
            contact=contact,
            content=sending.TextContent("Hello"),
            source=Message.Source.INBOX,
        )

    group = f"ws.{workspace.pk}"
    assert of_type(frames, "message.created") == [
        (
            group,
            {
                "v": 1,
                "type": "message.created",
                "workspace_id": str(workspace.pk),
                "data": {
                    "conversation_id": str(conversation.pk),
                    "message_id": str(message.pk),
                    "direction": "outbound",
                },
            },
        )
    ]
    assert [frame["data"] for _, frame in of_type(frames, "conversation.updated")] == [
        {"conversation_id": str(conversation.pk)}
    ]
    [(_, status)] = of_type(frames, "message.status")
    assert status["data"] == {
        "conversation_id": str(conversation.pk),
        "message_id": str(message.pk),
        "status": "sent",
    }


def test_nothing_is_broadcast_before_commit(
    workspace, contact, conversation, frames, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False):
        sending.send_message(
            workspace=workspace,
            contact=contact,
            content=sending.TextContent("Hello"),
            source=Message.Source.INBOX,
            dispatch=False,
        )
        services.close(conversation, actor=None)

    assert frames == []


def inbound_event(number, wamid="wamid.BROADCAST1"):
    return InboundMessage(
        workspace_id=number.workspace_id,
        waba_id=number.waba.waba_id,
        phone_number_id=number.phone_number_id,
        wamid=wamid,
        from_wa_id="919876543210",
        timestamp=timezone.now() - timedelta(seconds=5),
        type="text",
        text="Is the store open today?",
        profile_name="Kavya Nair",
    )


def test_inbound_message_broadcasts_once_per_stored_message(number, frames, commit):
    event = inbound_event(number)

    with commit():
        assert emit(inbound_message_received, event) == []
    with commit():
        assert emit(inbound_message_received, event) == []  # webhook retry

    message = Message.objects.get(wamid=event.wamid)
    [(_, created)] = of_type(frames, "message.created")
    assert created["data"] == {
        "conversation_id": str(message.conversation_id),
        "message_id": str(message.pk),
        "direction": "inbound",
    }
    assert len(of_type(frames, "conversation.updated")) == 1


def test_delivery_status_broadcasts_message_status(conversation, frames, commit):
    message = MessageFactory(conversation=conversation)
    event = MessageStatus(
        workspace_id=message.workspace_id,
        waba_id="waba",
        phone_number_id=conversation.phone_number.phone_number_id,
        wamid=message.wamid,
        recipient_wa_id="919876543210",
        status="delivered",
        timestamp=timezone.now(),
    )

    with commit():
        assert emit(message_status_updated, event) == []
    with commit():
        assert emit(message_status_updated, event) == []  # repeated status: no change, no frame

    assert [frame["data"] for _, frame in frames] == [
        {
            "conversation_id": str(conversation.pk),
            "message_id": str(message.pk),
            "status": "delivered",
        }
    ]


@pytest.mark.parametrize(
    "operation",
    [
        lambda c, u: services.assign(c, u, actor=u),
        lambda c, u: services.close(c, actor=u),
        lambda c, u: services.reopen(c, actor=u),
        lambda c, u: services.add_note(c, "Called back", author=u),
    ],
    ids=["assign", "close", "reopen", "add_note"],
)
def test_conversation_operations_broadcast_updates(conversation, user, frames, commit, operation):
    with commit():
        operation(conversation, user)

    assert frames == [
        (
            f"ws.{conversation.workspace_id}",
            realtime.build_frame(
                "conversation.updated",
                conversation.workspace_id,
                {"conversation_id": conversation.pk},
            ),
        )
    ]


def test_mark_read_broadcasts_only_when_something_was_unread(
    conversation, user, fake_graph, frames, commit
):
    with commit():
        services.mark_read(conversation, actor=user)
    assert frames == []

    Conversation.objects.filter(pk=conversation.pk).update(unread_count=2)
    with commit():
        services.mark_read(conversation, actor=user)
    assert [frame["type"] for _, frame in frames] == ["conversation.updated"]


def test_removed_member_gets_session_revoked(workspace, user, frames, commit):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    owner = Membership.objects.get(workspace=workspace, user=user)

    with commit():
        tenant_services.remove_member(actor=owner, membership=member)

    assert frames == [
        (
            f"user.{member.user_id}",
            realtime.build_frame("session.revoked", workspace.pk, {"reason": "membership_removed"}),
        )
    ]


def test_role_change_revokes_sessions(workspace, user, frames, commit):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    owner = Membership.objects.get(workspace=workspace, user=user)

    with commit():
        tenant_services.change_member_role(actor=owner, membership=member, role=Role.VIEWER)
        tenant_services.change_member_role(actor=owner, membership=member, role=Role.VIEWER)

    assert frames == [
        (
            f"user.{member.user_id}",
            realtime.build_frame("session.revoked", workspace.pk, {"reason": "role_changed"}),
        )
    ]


def test_other_membership_saves_do_not_revoke(workspace, frames, commit):
    with commit():
        member = MembershipFactory(workspace=workspace, role=Role.AGENT)
        member.save()
        member.save(update_fields=["updated_at"])
        Membership.objects.filter(pk=member.pk).update(role=Role.ADMIN)  # no signals

    assert frames == []
