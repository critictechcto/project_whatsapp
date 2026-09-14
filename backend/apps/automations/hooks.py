"""Integration hooks for automation actions implemented by other apps.

``apps.shop`` registers the commerce send actions (``send_shop_menu``, ``send_catalog``,
``send_collection``) at startup, e.g. in its ``receivers.py``::

    from apps.automations.hooks import ActionFailed, ActionSkipped, idempotency_key
    from apps.automations.hooks import register_commerce_action

    def send_shop_menu(*, rule, message, conversation, config, index) -> dict:
        ...  # send with idempotency_key(rule, message, index) and source "automation"
        return {"message_id": str(sent.pk)}

    register_commerce_action("send_shop_menu", send_shop_menu)

Handlers run inside a savepoint with the conversation row locked. They return extra result
fields (usually ``message_id``), raise :class:`ActionSkipped` when the action can't apply (e.g. the
store is disabled), :class:`ActionFailed` for a failure with a code, or let policy ``APIException``
errors (``outside_service_window``) propagate: the engine records them on the run. Without a
registered handler the action is skipped with "Store is not available.".
"""

from collections.abc import Callable
from typing import Any

__all__ = (
    "COMMERCE_ACTION_TYPES",
    "STORE_UNAVAILABLE",
    "ActionFailed",
    "ActionHandler",
    "ActionSkipped",
    "get_commerce_action",
    "idempotency_key",
    "register_commerce_action",
    "unregister_commerce_action",
)

COMMERCE_ACTION_TYPES = frozenset({"send_shop_menu", "send_catalog", "send_collection"})
STORE_UNAVAILABLE = "Store is not available."

# Called with keyword arguments ``rule, message, conversation, config, index``.
ActionHandler = Callable[..., dict[str, Any]]


class ActionFailed(Exception):
    """The action failed; recorded as ``failed`` with ``code`` and ``message``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ActionSkipped(Exception):
    """The action does not apply now; recorded as ``skipped`` with ``code`` and ``message``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def idempotency_key(rule, message, index: int) -> str:
    """The send idempotency key for action ``index`` of ``rule`` answering ``message``."""
    return f"automation:{rule.pk}:{message.wamid or message.pk}:{index}"


_commerce_actions: dict[str, ActionHandler] = {}


def _check_type(action_type: str) -> None:
    if action_type not in COMMERCE_ACTION_TYPES:
        raise ValueError(
            f"Unknown commerce action {action_type!r}; expected one of "
            f"{sorted(COMMERCE_ACTION_TYPES)}."
        )


def register_commerce_action(action_type: str, handler: ActionHandler) -> ActionHandler:
    """Install ``handler`` for ``action_type`` (replacing any previous one). Returns it."""
    _check_type(action_type)
    if not callable(handler):
        raise TypeError("A commerce action handler must be callable.")
    _commerce_actions[action_type] = handler
    return handler


def unregister_commerce_action(action_type: str) -> None:
    _check_type(action_type)
    _commerce_actions.pop(action_type, None)


def get_commerce_action(action_type: str) -> ActionHandler | None:
    """The registered handler, or None (also for action types that aren't commerce actions)."""
    return _commerce_actions.get(action_type)
