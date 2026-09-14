"""The commerce action registry other apps use to plug actions into the engine."""

import uuid
from types import SimpleNamespace

import pytest

from apps.automations import engine, hooks
from apps.automations.schema_enums import AUTOMATION_ACTION_TYPES


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr(hooks, "_commerce_actions", {})


def handler(**kwargs):
    return {}


def test_commerce_action_types_are_contract_enum_values():
    assert set(hooks.COMMERCE_ACTION_TYPES) == {"send_shop_menu", "send_catalog", "send_collection"}
    assert set(hooks.COMMERCE_ACTION_TYPES) <= set(AUTOMATION_ACTION_TYPES)


def test_register_get_and_unregister():
    assert hooks.get_commerce_action("send_catalog") is None

    assert hooks.register_commerce_action("send_catalog", handler) is handler
    assert hooks.get_commerce_action("send_catalog") is handler
    assert hooks.get_commerce_action("send_shop_menu") is None

    replacement = lambda **kwargs: {}  # noqa: E731
    hooks.register_commerce_action("send_catalog", replacement)
    assert hooks.get_commerce_action("send_catalog") is replacement

    hooks.unregister_commerce_action("send_catalog")
    hooks.unregister_commerce_action("send_catalog")
    assert hooks.get_commerce_action("send_catalog") is None


@pytest.mark.parametrize("action_type", ["send_text", "close_conversation", "reboot", ""])
def test_only_commerce_actions_can_be_registered(action_type):
    with pytest.raises(ValueError):
        hooks.register_commerce_action(action_type, handler)
    with pytest.raises(ValueError):
        hooks.unregister_commerce_action(action_type)
    assert hooks.get_commerce_action(action_type) is None


def test_handlers_must_be_callable():
    with pytest.raises(TypeError):
        hooks.register_commerce_action("send_shop_menu", "not callable")


def test_idempotency_key_is_shared_with_the_engine():
    rule = SimpleNamespace(pk=uuid.UUID(int=1))
    message_id = uuid.UUID(int=2)

    assert engine.idempotency_key is hooks.idempotency_key
    assert hooks.idempotency_key(rule, SimpleNamespace(wamid="wamid.A", pk=message_id), 2) == (
        f"automation:{rule.pk}:wamid.A:2"
    )
    assert hooks.idempotency_key(rule, SimpleNamespace(wamid=None, pk=message_id), 0) == (
        f"automation:{rule.pk}:{message_id}:0"
    )


def test_engine_failure_types_come_from_hooks():
    assert engine.ActionFailed is hooks.ActionFailed
    error = hooks.ActionSkipped("store_unavailable", hooks.STORE_UNAVAILABLE)
    assert (error.code, error.message) == ("store_unavailable", "Store is not available.")
