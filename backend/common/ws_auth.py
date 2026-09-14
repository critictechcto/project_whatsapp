"""WebSocket authentication with single-use tickets.

Browsers can't set an ``Authorization`` header on a WebSocket, and JWTs in URLs end up in logs.
Instead the dashboard calls ``POST /api/v1/inbox/ws-ticket/`` (JWT + ``X-Workspace-ID``) and
connects to ``/ws/v1/?ticket=<ticket>`` within ``WS_TICKET_TTL`` seconds.

- Tickets are random, stored in the Django cache (only a SHA-256 of the ticket is used as the key)
  and map to ``(user_id, workspace_id)``.
- A ticket is consumed on first use: only the connection whose ``cache.delete`` succeeds wins.
- On connect the membership is re-checked (active user, active workspace, still a member).

:class:`TicketAuthMiddleware` sets ``scope["user"]``, ``scope["workspace_id"]`` (UUID) and
``scope["role"]``, or denies the handshake (HTTP 403). :func:`websocket_application` wraps routes
with the Origin check (``WS_ALLOWED_ORIGINS``) and the ticket middleware.
"""

import hashlib
import logging
import secrets
import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.security.websocket import OriginValidator, WebsocketDenier
from django.apps import apps
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

WS_PATH = "/ws/v1/"
TICKET_CACHE_PREFIX = "ws-ticket:"
_MAX_TICKET_LENGTH = 128


def _cache_key(ticket: str) -> str:
    return TICKET_CACHE_PREFIX + hashlib.sha256(ticket.encode()).hexdigest()


def issue_ticket(user_id, workspace_id) -> str:
    """Create a single-use ticket for ``user_id`` in ``workspace_id``, valid ``WS_TICKET_TTL`` s."""
    ticket = secrets.token_urlsafe(32)
    cache.set(
        _cache_key(ticket),
        {"user_id": str(user_id), "workspace_id": str(workspace_id)},
        timeout=settings.WS_TICKET_TTL,
    )
    return ticket


def consume_ticket(ticket: str | None) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Return ``(user_id, workspace_id)`` and invalidate the ticket, or None if not valid."""
    if not ticket or len(ticket) > _MAX_TICKET_LENGTH:
        return None
    key = _cache_key(ticket)
    claims = cache.get(key)
    # delete() reports whether this call removed the key, so concurrent uses can't both win.
    if not isinstance(claims, dict) or not cache.delete(key):
        return None
    try:
        return uuid.UUID(claims["user_id"]), uuid.UUID(claims["workspace_id"])
    except (KeyError, TypeError, ValueError):
        return None


def resolve_ticket(ticket: str | None):
    """Consume ``ticket`` and return the caller's current Membership, or None."""
    claims = consume_ticket(ticket)
    if claims is None:
        return None
    user_id, workspace_id = claims
    membership_model = apps.get_model("tenants", "Membership")
    return (
        membership_model.objects.select_related("user")
        .filter(
            user_id=user_id,
            workspace_id=workspace_id,
            user__is_active=True,
            workspace__is_active=True,
        )
        .first()
    )


def _ticket_from_scope(scope) -> str | None:
    query = parse_qs(scope.get("query_string", b"").decode("latin1"))
    values = query.get("ticket")
    return values[0] if values else None


class TicketAuthMiddleware:
    """Authenticate WebSocket connections with a ticket from ``?ticket=``; deny otherwise."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.inner(scope, receive, send)

        ticket = _ticket_from_scope(scope)
        membership = await database_sync_to_async(resolve_ticket)(ticket) if ticket else None
        if membership is None:
            logger.info("WebSocket connection denied: missing, used, expired or invalid ticket")
            return await WebsocketDenier.as_asgi()(scope, receive, send)

        scope = {
            **scope,
            "user": membership.user,
            "workspace_id": membership.workspace_id,
            "role": membership.role,
        }
        return await self.inner(scope, receive, send)


def websocket_application(urlpatterns, allowed_origins=None):
    """ASGI app for WebSockets: Origin check, then ticket auth, then URL routing."""
    from channels.routing import URLRouter

    origins = settings.WS_ALLOWED_ORIGINS if allowed_origins is None else allowed_origins
    return OriginValidator(TicketAuthMiddleware(URLRouter(urlpatterns)), list(origins))
