"""Automation actions run by the shop: ``send_shop_menu {}``, ``send_catalog {}`` and
``send_collection {collection_id}`` (registered in ``receivers.py`` through
``apps.automations.hooks``)."""

from typing import Any

from apps.automations.hooks import (
    STORE_UNAVAILABLE,
    ActionFailed,
    ActionSkipped,
    idempotency_key,
)
from apps.catalog.models import Collection
from apps.inbox import sending
from apps.inbox.models import Message

from . import content, services

STORE_UNAVAILABLE_CODE = "store_unavailable"


def _store(message, conversation):
    store = services.available_store(message.workspace, conversation.phone_number_id)
    if store is None:
        raise ActionSkipped(STORE_UNAVAILABLE_CODE, STORE_UNAVAILABLE)
    return store


def _send(rule, message, conversation, index, message_content) -> dict[str, Any]:
    sent = sending.send_message(
        workspace=message.workspace,
        contact=conversation.contact,
        content=message_content,
        conversation=conversation,
        source=Message.Source.AUTOMATION,
        source_ref=str(rule.pk),
        idempotency_key=idempotency_key(rule, message, index),
    )
    return {"message_id": str(sent.pk)}


def send_shop_menu(*, rule, message, conversation, config, index) -> dict[str, Any]:
    store = _store(message, conversation)
    return _send(rule, message, conversation, index, content.menu_content(store))


def send_catalog(*, rule, message, conversation, config, index) -> dict[str, Any]:
    store = _store(message, conversation)
    browse = services.browse_content(store, message.workspace, conversation)
    if browse is None:
        raise ActionSkipped("store_empty", "The store has no products to show.")
    return _send(rule, message, conversation, index, browse)


def send_collection(*, rule, message, conversation, config, index) -> dict[str, Any]:
    store = _store(message, conversation)
    collection_id = services._uuid((config or {}).get("collection_id"))
    collection = (
        Collection.objects.filter(
            workspace_id=message.workspace_id, pk=collection_id, is_active=True
        ).first()
        if collection_id
        else None
    )
    if collection is None:
        raise ActionFailed("collection_not_found", "The collection no longer exists.")
    page = services.collection_content(store, message.workspace, conversation, collection)
    if page is None:
        raise ActionSkipped("collection_empty", "The collection has no products to show.")
    return _send(rule, message, conversation, index, page)


ACTIONS = {
    "send_shop_menu": send_shop_menu,
    "send_catalog": send_catalog,
    "send_collection": send_collection,
}
