"""End to end: a socket opened with a ticket receives message.created for an inbound webhook."""

import time

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import Client

from apps.inbox.models import Message
from common.ws_auth import WS_PATH, issue_ticket
from config.asgi import application

from .conftest import inbound_text, signed_meta_request

pytestmark = pytest.mark.django_db(transaction=True)

ORIGIN = [(b"origin", b"http://testserver-frontend")]


@pytest.fixture
def layer():
    layer = get_channel_layer()
    async_to_sync(layer.flush)()
    yield layer
    async_to_sync(layer.flush)()


def test_inbound_webhook_reaches_the_open_socket(layer, user, workspace, e2e_number):
    ticket = issue_ticket(user.pk, workspace.pk)
    request = signed_meta_request(inbound_text("Hello", "wamid.E2E.WS1", int(time.time())))

    def deliver():
        # Outside a test transaction, on_commit callbacks (event processing, broadcasts) run for
        # real when the webhook's transactions commit.
        return Client().post(**request).status_code

    async def scenario():
        socket = WebsocketCommunicator(application, f"{WS_PATH}?ticket={ticket}", headers=ORIGIN)
        connected, _ = await socket.connect()
        assert connected
        assert await database_sync_to_async(deliver)() == 200
        frames = []
        while not any(frame["type"] == "message.created" for frame in frames):
            frames.append(await socket.receive_json_from(timeout=5))
        await socket.disconnect()
        return frames

    frames = run(scenario)

    message = Message.objects.get(wamid="wamid.E2E.WS1")
    [created] = [frame for frame in frames if frame["type"] == "message.created"]
    assert created == {
        "v": 1,
        "type": "message.created",
        "workspace_id": str(workspace.pk),
        "data": {
            "conversation_id": str(message.conversation_id),
            "message_id": str(message.pk),
            "direction": "inbound",
        },
    }


def run(scenario):
    return async_to_sync(scenario)()
