"""Realtime WebSocket for the dashboard at ``/ws/v1/?ticket=<ticket>``.

``common.ws_auth`` has already checked the Origin and consumed the ticket, setting
``scope["user"]`` and ``scope["workspace_id"]``. On connect the membership is checked again, then
the connection joins the workspace group (``ws.<workspace_id>``) and the user group
(``user.<user_id>``). Frames from ``common.realtime`` arrive as ``realtime.frame`` channel-layer
messages and are forwarded unchanged. A ``session.revoked`` frame is forwarded and then the
connection is closed, so the client refreshes its memberships and asks for a new ticket.

Clients only receive. The one client message handled is ``{"type": "ping"}``, answered with a
``pong`` frame; anything else is ignored.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.tenants.models import Membership
from common.realtime import FRAME_VERSION, user_group, workspace_group

logger = logging.getLogger(__name__)

# Application close codes (4000-4999).
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_SESSION_REVOKED = 4001

SESSION_REVOKED = "session.revoked"
MAX_CLIENT_MESSAGE_LENGTH = 1024


@database_sync_to_async
def _is_member(user_id, workspace_id) -> bool:
    return Membership.objects.filter(
        user_id=user_id,
        workspace_id=workspace_id,
        user__is_active=True,
        workspace__is_active=True,
    ).exists()


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.joined_groups: list[str] = []
        self.closing = False
        user = self.scope.get("user")
        workspace_id = self.scope.get("workspace_id")
        if user is None or not getattr(user, "is_authenticated", False) or workspace_id is None:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        if not await _is_member(user.pk, workspace_id):
            logger.info("WebSocket connection closed: user is no longer a workspace member")
            await self.close(code=CLOSE_FORBIDDEN)
            return
        for group in (workspace_group(workspace_id), user_group(user.pk)):
            await self.channel_layer.group_add(group, self.channel_name)
            self.joined_groups.append(group)
        await self.accept()

    async def disconnect(self, code):
        for group in getattr(self, "joined_groups", []):
            await self.channel_layer.group_discard(group, self.channel_name)
        self.joined_groups = []

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if not text_data or len(text_data) > MAX_CLIENT_MESSAGE_LENGTH:
            return
        try:
            content = json.loads(text_data)
        except ValueError:
            return
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json(
                {
                    "v": FRAME_VERSION,
                    "type": "pong",
                    "workspace_id": str(self.scope["workspace_id"]),
                    "data": {},
                }
            )

    async def realtime_frame(self, event):
        if getattr(self, "closing", False):
            return
        frame = event.get("frame")
        if not isinstance(frame, dict):
            return
        await self.send_json(frame)
        if frame.get("type") == SESSION_REVOKED:
            self.closing = True
            await self.close(code=CLOSE_SESSION_REVOKED)
