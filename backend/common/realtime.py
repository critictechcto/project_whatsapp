"""Server-to-browser realtime frames over Django Channels.

Frames are ``{"v": 1, "type": str, "workspace_id": uuid, "data": object}`` (see
docs/contracts/wave-2.md). Payloads stay thin; clients refetch through the REST API.

- :func:`broadcast` sends to every connection of a workspace (group ``ws.<workspace_id>``).
- :func:`broadcast_user` sends to every connection of one user (group ``user.<user_id>``).

Both send after the current transaction commits, so clients never refetch uncommitted rows.
A failed send is logged and swallowed: realtime is best effort and must not break the caller.

Consumers join :func:`workspace_group` and :func:`user_group` and handle channel-layer messages of
type :data:`FRAME_MESSAGE_TYPE` (method ``realtime_frame``) by sending ``event["frame"]`` as JSON.
"""

import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

logger = logging.getLogger(__name__)

FRAME_VERSION = 1
# Channel-layer message type; Channels dispatches it to a consumer's ``realtime_frame`` method.
FRAME_MESSAGE_TYPE = "realtime.frame"


def workspace_group(workspace_id) -> str:
    return f"ws.{workspace_id}"


def user_group(user_id) -> str:
    return f"user.{user_id}"


def build_frame(type: str, workspace_id, data) -> dict:
    """The frame as plain JSON types (UUIDs, datetimes and Decimals become strings)."""
    frame = {"v": FRAME_VERSION, "type": type, "workspace_id": workspace_id, "data": data or {}}
    return json.loads(json.dumps(frame, cls=DjangoJSONEncoder))


def broadcast(workspace_id, type: str, data) -> None:
    """Send a frame to every connection in the workspace once the transaction commits."""
    _send_on_commit(workspace_group(workspace_id), build_frame(type, workspace_id, data))


def broadcast_user(user_id, type: str, data, *, workspace_id=None) -> None:
    """Send a frame to every connection of one user once the transaction commits.

    ``workspace_id`` fills the frame's ``workspace_id`` (e.g. the workspace a ``session.revoked``
    refers to); it is ``null`` when omitted.
    """
    _send_on_commit(user_group(user_id), build_frame(type, workspace_id, data))


def _send_on_commit(group: str, frame: dict) -> None:
    transaction.on_commit(lambda: _send(group, frame))


def _send(group: str, frame: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": FRAME_MESSAGE_TYPE, "frame": frame})
    except Exception:
        logger.exception("Realtime frame %r to group %s could not be sent", frame["type"], group)
