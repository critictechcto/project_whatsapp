from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.testing import WebsocketCommunicator
from django.urls import path

from apps.tenants.factories import MembershipFactory
from common.roles import Role
from common.ws_auth import (
    WS_PATH,
    TicketAuthMiddleware,
    consume_ticket,
    issue_ticket,
    websocket_application,
)

pytestmark = pytest.mark.django_db(transaction=True)

ALLOWED_ORIGIN = "http://testserver-frontend"
ORIGIN_HEADER = (b"origin", ALLOWED_ORIGIN.encode())


class ScopeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send_json(
            {
                "user_id": str(self.scope["user"].pk),
                "workspace_id": str(self.scope["workspace_id"]),
                "role": self.scope["role"],
            }
        )


application = websocket_application(
    [path("ws/v1/", ScopeConsumer.as_asgi())], allowed_origins=[ALLOWED_ORIGIN]
)


async def _connect(ticket, headers):
    url = WS_PATH if ticket is None else f"{WS_PATH}?ticket={ticket}"
    communicator = WebsocketCommunicator(application, url, headers=list(headers))
    connected, _ = await communicator.connect()
    payload = None
    if connected:
        payload = await communicator.receive_json_from()
        await communicator.disconnect()
    return connected, payload


def connect(ticket, headers=(ORIGIN_HEADER,)):
    return async_to_sync(_connect)(ticket, headers)


def test_valid_ticket_connects_with_user_and_workspace(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    connected, payload = connect(ticket)

    assert connected is True
    assert payload == {
        "user_id": str(user.pk),
        "workspace_id": str(workspace.pk),
        "role": Role.OWNER,
    }


def test_ticket_is_single_use(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    assert connect(ticket)[0] is True
    assert connect(ticket)[0] is False


def test_expired_ticket_is_rejected(user, workspace, settings):
    ticket = issue_ticket(user.pk, workspace.pk)

    later = datetime.now(UTC) + timedelta(seconds=settings.WS_TICKET_TTL + 1)
    with time_machine.travel(later, tick=False):
        assert connect(ticket)[0] is False


def test_non_member_ticket_is_rejected(user, other_workspace):
    ticket = issue_ticket(user.pk, other_workspace.pk)

    assert connect(ticket)[0] is False


def test_membership_is_rechecked_on_connect(user, workspace):
    member = MembershipFactory(workspace=workspace, role=Role.AGENT)
    ticket = issue_ticket(member.user_id, workspace.pk)
    member.delete()

    assert connect(ticket)[0] is False


def test_inactive_user_is_rejected(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)
    user.is_active = False
    user.save(update_fields=["is_active"])

    assert connect(ticket)[0] is False


def test_inactive_workspace_is_rejected(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)
    workspace.is_active = False
    workspace.save(update_fields=["is_active"])

    assert connect(ticket)[0] is False


@pytest.mark.parametrize("ticket", [None, "", "not-a-ticket", "x" * 500])
def test_missing_or_unknown_ticket_is_rejected(ticket):
    assert connect(ticket)[0] is False


def test_bad_origin_is_rejected_without_consuming_the_ticket(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    assert connect(ticket, headers=[(b"origin", b"https://evil.example")])[0] is False
    assert connect(ticket, headers=[])[0] is False
    assert consume_ticket(ticket) == (user.pk, workspace.pk)


def test_consume_ticket_returns_claims_once(user, workspace):
    ticket = issue_ticket(user.pk, workspace.pk)

    assert consume_ticket(ticket) == (user.pk, workspace.pk)
    assert consume_ticket(ticket) is None


def test_ticket_is_not_stored_under_its_own_value(user, workspace):
    from django.core.cache import cache

    ticket = issue_ticket(user.pk, workspace.pk)

    assert cache.get(ticket) is None
    assert ticket not in str(cache._cache.keys())


def test_middleware_passes_non_websocket_scopes_through():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope)

    async_to_sync(TicketAuthMiddleware(inner))({"type": "http", "path": "/"}, None, None)

    assert seen == [{"type": "http", "path": "/"}]
