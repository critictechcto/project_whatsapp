import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common import realtime


@pytest.fixture
def layer():
    layer = get_channel_layer()
    async_to_sync(layer.flush)()
    yield layer
    async_to_sync(layer.flush)()


def join(layer, group: str) -> str:
    channel = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)(group, channel)
    return channel


def receive(layer, channel: str) -> dict:
    return async_to_sync(layer.receive)(channel)


def test_group_names():
    workspace_id = uuid.uuid4()

    assert realtime.workspace_group(workspace_id) == f"ws.{workspace_id}"
    assert realtime.user_group(workspace_id) == f"user.{workspace_id}"


def test_build_frame_uses_json_types():
    workspace_id = uuid.uuid4()
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    frame = realtime.build_frame(
        "message.created", workspace_id, {"id": workspace_id, "at": moment, "cost": Decimal("1.5")}
    )

    assert frame == {
        "v": 1,
        "type": "message.created",
        "workspace_id": str(workspace_id),
        "data": {"id": str(workspace_id), "at": "2026-01-02T03:04:05Z", "cost": "1.5"},
    }


def test_build_frame_defaults_data_to_object():
    assert realtime.build_frame("ping", None, None)["data"] == {}


@pytest.mark.django_db
def test_broadcast_sends_to_workspace_group_after_commit(layer, django_capture_on_commit_callbacks):
    workspace_id = uuid.uuid4()
    channel = join(layer, realtime.workspace_group(workspace_id))

    with django_capture_on_commit_callbacks() as callbacks:
        realtime.broadcast(workspace_id, "conversation.updated", {"id": "c1"})
    assert len(callbacks) == 1

    callbacks[0]()
    message = receive(layer, channel)

    assert message == {
        "type": realtime.FRAME_MESSAGE_TYPE,
        "frame": {
            "v": 1,
            "type": "conversation.updated",
            "workspace_id": str(workspace_id),
            "data": {"id": "c1"},
        },
    }


@pytest.mark.django_db
def test_nothing_is_sent_before_commit(monkeypatch, django_capture_on_commit_callbacks):
    sent = []
    monkeypatch.setattr(realtime, "_send", lambda group, frame: sent.append((group, frame)))
    user_id = uuid.uuid4()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        realtime.broadcast_user(user_id, "session.revoked", {})
        assert sent == []

    assert len(callbacks) == 1
    callbacks[0]()
    assert sent == [(f"user.{user_id}", realtime.build_frame("session.revoked", None, {}))]


@pytest.mark.django_db
def test_broadcast_user_sends_to_user_group(layer, django_capture_on_commit_callbacks):
    user_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    channel = join(layer, realtime.user_group(user_id))

    with django_capture_on_commit_callbacks(execute=True):
        realtime.broadcast_user(
            user_id, "session.revoked", {"reason": "removed"}, workspace_id=workspace_id
        )

    frame = receive(layer, channel)["frame"]
    assert frame == {
        "v": 1,
        "type": "session.revoked",
        "workspace_id": str(workspace_id),
        "data": {"reason": "removed"},
    }


def test_send_failure_is_logged_not_raised(monkeypatch, caplog):
    class BrokenLayer:
        async def group_send(self, group, message):
            raise RuntimeError("redis down")

    monkeypatch.setattr(realtime, "get_channel_layer", lambda: BrokenLayer())

    realtime._send("ws.x", {"type": "message.created"})

    assert "could not be sent" in caplog.text


def test_send_without_layer_is_a_no_op(monkeypatch):
    monkeypatch.setattr(realtime, "get_channel_layer", lambda: None)

    realtime._send("ws.x", {"type": "message.created"})
