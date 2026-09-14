"""The realtime WebSocket, driven through the real ASGI application (Origin + ticket + routing)."""

import json

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.inbox.consumers import (
    CLOSE_FORBIDDEN,
    CLOSE_SESSION_REVOKED,
    CLOSE_UNAUTHORIZED,
    InboxConsumer,
)
from apps.inbox.factories import ConversationFactory
from apps.tenants import services as tenant_services
from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common import events, realtime
from common.roles import Role
from common.ws_auth import WS_PATH, issue_ticket
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)

ORIGIN = [(b"origin", b"http://testserver-frontend")]
QUIET = 0.05


@pytest.fixture
def layer():
    layer = get_channel_layer()
    async_to_sync(layer.flush)()
    yield layer
    async_to_sync(layer.flush)()


def run(scenario, *args):
    return async_to_sync(scenario)(*args)


async def open_socket(ticket, headers=ORIGIN):
    url = WS_PATH if ticket is None else f"{WS_PATH}?ticket={ticket}"
    communicator = WebsocketCommunicator(application, url, headers=list(headers))
    connected, code = await communicator.connect()
    return communicator, connected, code


async def push(layer, group, frame):
    await layer.group_send(group, {"type": realtime.FRAME_MESSAGE_TYPE, "frame": frame})


def test_route_matches_the_ticket_path():
    from config.routing import websocket_urlpatterns

    [route] = [p for p in websocket_urlpatterns if getattr(p, "callback", None)]
    assert f"/{route.pattern}" == WS_PATH
    assert route.callback.consumer_class is InboxConsumer


def test_connects_joins_groups_and_forwards_frames(layer, user, workspace, other_workspace):
    ticket = issue_ticket(user.pk, workspace.pk)
    workspace_frame = realtime.build_frame(
        "conversation.updated", workspace.pk, {"conversation_id": "c1"}
    )
    user_frame = realtime.build_frame("campaign.progress", workspace.pk, {"campaign_id": "x"})
    foreign_frame = realtime.build_frame("conversation.updated", other_workspace.pk, {})

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        assert await socket.receive_nothing(QUIET)

        await push(layer, realtime.workspace_group(workspace.pk), workspace_frame)
        assert await socket.receive_json_from() == workspace_frame
        await push(layer, realtime.user_group(user.pk), user_frame)
        assert await socket.receive_json_from() == user_frame
        await push(layer, realtime.workspace_group(other_workspace.pk), foreign_frame)
        await push(layer, realtime.user_group(UserFactory.build().pk), user_frame)
        assert await socket.receive_nothing(QUIET)

        await socket.disconnect()

    run(scenario)

    assert not layer.groups.get(realtime.workspace_group(workspace.pk))
    assert not layer.groups.get(realtime.user_group(user.pk))


def test_rejects_missing_ticket_and_bad_origin(layer, user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    async def scenario():
        _, without_ticket, _ = await open_socket(None)
        _, without_origin, _ = await open_socket(ticket, headers=[])
        _, reused, _ = await open_socket("not-a-ticket")
        return without_ticket, without_origin, reused

    assert run(scenario) == (False, False, False)


@pytest.mark.parametrize(
    ("scope_user", "code"),
    [
        ("anonymous", CLOSE_UNAUTHORIZED),
        ("missing", CLOSE_UNAUTHORIZED),
        ("stranger", CLOSE_FORBIDDEN),
    ],
)
def test_consumer_rechecks_the_scope(layer, workspace, scope_user, code):
    stranger = UserFactory()

    async def scenario():
        communicator = WebsocketCommunicator(InboxConsumer.as_asgi(), WS_PATH)
        if scope_user == "anonymous":
            communicator.scope["user"] = AnonymousUser()
        elif scope_user == "stranger":
            communicator.scope["user"] = stranger
        communicator.scope["workspace_id"] = workspace.pk
        return await communicator.connect()

    assert run(scenario) == (False, code)


def test_membership_removed_after_ticket_is_rejected(layer, workspace):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    ticket = issue_ticket(member.user_id, workspace.pk)
    member.delete()

    async def scenario():
        return (await open_socket(ticket))[1]

    assert run(scenario) is False


def test_ping_gets_pong_and_other_client_messages_are_ignored(layer, user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        await socket.send_to(text_data="not json")
        await socket.send_to(text_data=json.dumps({"type": "subscribe", "group": "ws.other"}))
        await socket.send_to(text_data=json.dumps(["ping"]))
        await socket.send_to(text_data=json.dumps({"type": "ping", "pad": "x" * 2000}))
        await socket.send_to(bytes_data=b"\x00\x01")
        assert await socket.receive_nothing(QUIET)

        await socket.send_json_to({"type": "ping"})
        pong = await socket.receive_json_from()
        await socket.disconnect()
        return pong

    assert run(scenario) == {"v": 1, "type": "pong", "workspace_id": str(workspace.pk), "data": {}}


def test_session_revoked_frame_is_sent_then_the_socket_closes(layer, user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)
    frame = realtime.build_frame("session.revoked", workspace.pk, {"reason": "role_changed"})

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        await push(layer, realtime.user_group(user.pk), frame)
        received = await socket.receive_json_from()
        closed = await socket.receive_output()
        await push(layer, realtime.workspace_group(workspace.pk), frame)
        return received, closed

    received, closed = run(scenario)

    assert received == frame
    assert closed == {"type": "websocket.close", "code": CLOSE_SESSION_REVOKED}


def test_removing_a_member_revokes_their_open_socket(layer, user, workspace):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    owner = Membership.objects.get(workspace=workspace, user=user)
    ticket = issue_ticket(member.user_id, workspace.pk)

    def remove():
        tenant_services.remove_member(actor=owner, membership=member)

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        await database_sync_to_async(remove)()
        return await socket.receive_json_from(), await socket.receive_output()

    frame, closed = run(scenario)

    assert frame == {
        "v": 1,
        "type": "session.revoked",
        "workspace_id": str(workspace.pk),
        "data": {"reason": "membership_removed"},
    }
    assert closed["type"] == "websocket.close"


def test_role_change_revokes_open_sockets(layer, user, workspace):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    owner = Membership.objects.get(workspace=workspace, user=user)
    ticket = issue_ticket(member.user_id, workspace.pk)

    def promote():
        tenant_services.change_member_role(actor=owner, membership=member, role=Role.ADMIN)

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        await database_sync_to_async(promote)()
        return await socket.receive_json_from()

    frame = run(scenario)

    assert frame["type"] == "session.revoked"
    assert frame["data"] == {"reason": "role_changed"}


def test_inbox_events_reach_the_socket(layer, user, workspace):
    conversation = ConversationFactory(workspace=workspace)
    ticket = issue_ticket(user.pk, workspace.pk)
    message_id = conversation.pk  # any uuid; frames are thin
    event = events.MessageRecorded(
        workspace_id=workspace.pk,
        message_id=message_id,
        conversation_id=conversation.pk,
        contact_id=conversation.contact_id,
        phone_number_id=conversation.phone_number_id,
        direction="inbound",
        source="inbound",
        source_ref="",
        type="text",
        text="Hi",
        reply_id=None,
        wamid="wamid.WS1",
        is_first_inbound=True,
        contact_created=False,
        created_at=timezone.now(),
    )

    async def scenario():
        socket, connected, _ = await open_socket(ticket)
        assert connected
        failures = await database_sync_to_async(events.emit)(events.message_recorded, event)
        assert failures == []
        frames = [await socket.receive_json_from(), await socket.receive_json_from()]
        await socket.disconnect()
        return frames

    created, updated = run(scenario)

    assert created["type"] == "message.created"
    assert created["data"] == {
        "conversation_id": str(conversation.pk),
        "message_id": str(message_id),
        "direction": "inbound",
    }
    assert updated == {
        "v": 1,
        "type": "conversation.updated",
        "workspace_id": str(workspace.pk),
        "data": {"conversation_id": str(conversation.pk)},
    }
