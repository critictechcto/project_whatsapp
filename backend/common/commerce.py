"""Shared commerce helpers: the interactive reply-id grammar and message claiming.

Every interactive button or list row that UpChatz commerce sends carries an id of the form
``upc:<scope>:<action>[:<arg>...]`` (see docs/contracts/wave-3-commerce.md). Buyers can tap stale
buttons, so handlers must re-validate every id against current state.

Commerce "claims" inbound messages it answers (carts, address replies, ``upc:`` replies and any
message a registered claimer accepts, such as store menu keywords). Automations skip claimed
messages so a buyer never gets two replies. Apps register claimers in ``AppConfig.ready`` or
their ``receivers.py``; claimers must be fast, side-effect free and never raise.

Changing the grammar here is a contract change: lead-owned.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from common.events import MessageRecorded

logger = logging.getLogger(__name__)

REPLY_ID_PREFIX = "upc"
# Meta allows 200 characters for list row ids and 256 for reply button ids.
REPLY_ID_MAX_LENGTH = 200
SCOPES = frozenset({"shop", "chk", "ord", "nfm", "alerts"})
# Message types always handled by commerce (a native WhatsApp cart).
CLAIMED_MESSAGE_TYPES = frozenset({"order"})

_PART_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


@dataclass(frozen=True, slots=True)
class ReplyId:
    scope: str
    action: str
    args: tuple[str, ...] = ()

    def __str__(self) -> str:
        return build_reply_id(self.scope, self.action, *self.args)


def build_reply_id(scope: str, action: str, *args: object) -> str:
    """``build_reply_id("shop", "add", product_id, 2)`` → ``"upc:shop:add:<uuid>:2"``."""
    parts = [scope, action, *(str(arg) for arg in args)]
    if scope not in SCOPES:
        raise ValueError(f"Unknown reply id scope {scope!r}.")
    for part in parts:
        if not _PART_RE.fullmatch(part):
            raise ValueError(f"Invalid reply id part {part!r}.")
    reply_id = ":".join([REPLY_ID_PREFIX, *parts])
    if len(reply_id) > REPLY_ID_MAX_LENGTH:
        raise ValueError("Reply id is too long.")
    return reply_id


def parse_reply_id(value: object) -> ReplyId | None:
    """The parsed id, or None when ``value`` is not a well-formed commerce reply id."""
    if not isinstance(value, str) or len(value) > REPLY_ID_MAX_LENGTH:
        return None
    prefix, _, rest = value.partition(":")
    if prefix != REPLY_ID_PREFIX:
        return None
    parts = rest.split(":")
    if len(parts) < 2 or parts[0] not in SCOPES or not all(_PART_RE.fullmatch(p) for p in parts):
        return None
    return ReplyId(scope=parts[0], action=parts[1], args=tuple(parts[2:]))


MessageClaimer = Callable[[MessageRecorded], bool]
_claimers: list[MessageClaimer] = []


def register_message_claimer(claimer: MessageClaimer) -> MessageClaimer:
    """Register ``claimer`` (idempotent). Usable as a decorator."""
    if claimer not in _claimers:
        _claimers.append(claimer)
    return claimer


def unregister_message_claimer(claimer: MessageClaimer) -> None:
    if claimer in _claimers:
        _claimers.remove(claimer)


def is_claimed_by_commerce(event: MessageRecorded) -> bool:
    """True when commerce answers this inbound message, so automations must skip it."""
    if event.direction != "inbound":
        return False
    if event.type in CLAIMED_MESSAGE_TYPES or parse_reply_id(event.reply_id) is not None:
        return True
    for claimer in list(_claimers):
        try:
            if claimer(event):
                return True
        except Exception:
            logger.exception("Commerce message claimer %r failed", claimer)
    return False
