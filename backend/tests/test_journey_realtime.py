"""Journey: an agent opens the live inbox (ticket → socket), sees a customer's message arrive, and
is disconnected the moment the owner removes her from the workspace."""

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from common.ws_auth import WS_PATH
from config.asgi import application

from .test_journey_support import Customer, invite_and_join, ok, results

pytest_plugins = ["tests.test_journey_support"]
# Real commits, so the webhook's on-commit broadcasts reach the channel layer as in production.
pytestmark = pytest.mark.django_db(transaction=True)

ORIGIN = [(b"origin", b"http://testserver-frontend")]


@pytest.fixture
def layer():
    layer = get_channel_layer()
    async_to_sync(layer.flush)()
    yield layer
    async_to_sync(layer.flush)()


async def receive_until(socket, frame_type: str) -> list[dict]:
    frames: list[dict] = []
    while not any(frame["type"] == frame_type for frame in frames):
        frames.append(await socket.receive_json_from(timeout=5))
    return frames


def test_live_inbox_frames_and_revocation_on_removal(
    layer, seller_api, run_on_commit, deliver_meta
):
    agent = invite_and_join(
        seller_api, run_on_commit, email="meera@sharmasweets.in", full_name="Meera", role="agent"
    )
    [membership] = [
        m
        for m in results(seller_api.get("/api/v1/workspaces/members/"))
        if m["user"]["email"] == "meera@sharmasweets.in"
    ]
    ticket = ok(agent.post("/api/v1/inbox/ws-ticket/"))["ticket"]
    customer = Customer(deliver_meta)

    async def scenario():
        socket = WebsocketCommunicator(application, f"{WS_PATH}?ticket={ticket}", headers=ORIGIN)
        connected, _ = await socket.connect()
        assert connected

        await socket.send_json_to({"type": "ping"})
        pong = await receive_until(socket, "pong")

        await database_sync_to_async(customer.says)("Is the shop open today?")
        inbox = await receive_until(socket, "message.created")

        response = await database_sync_to_async(seller_api.delete)(
            f"/api/v1/workspaces/members/{membership['id']}/"
        )
        assert response.status_code == 204, response.content
        revoked = await receive_until(socket, "session.revoked")
        closed = await socket.receive_output(timeout=5)
        await socket.disconnect()
        return pong, inbox, revoked, closed

    pong, inbox, revoked, closed = async_to_sync(scenario)()

    [conversation] = results(seller_api.get("/api/v1/inbox/conversations/"))
    [created] = [f for f in inbox if f["type"] == "message.created"]
    assert created["workspace_id"] == seller_api.workspace_id
    assert created["data"]["conversation_id"] == conversation["id"]
    assert created["data"]["direction"] == "inbound"
    assert pong[-1]["data"] == {}

    assert revoked[-1]["data"] == {"reason": "membership_removed"}
    assert closed == {"type": "websocket.close", "code": 4001}

    # The removed agent can't get a new ticket or read the workspace.
    assert agent.post("/api/v1/inbox/ws-ticket/").status_code in (403, 404)
    assert agent.get("/api/v1/inbox/conversations/").status_code in (403, 404)
