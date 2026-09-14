"""Automation actions registered by the shop."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automations import hooks
from apps.automations.engine import process_inbound
from apps.automations.factories import AutomationRuleFactory
from apps.automations.hooks import ActionFailed, ActionSkipped
from apps.catalog.factories import CollectionFactory, MetaCatalogFactory, ProductFactory
from apps.catalog.models import Product
from apps.inbox.factories import MessageFactory
from apps.inbox.models import Message
from apps.inbox.sending import OutsideServiceWindow
from apps.orders.models import StoreSettings
from apps.shop import actions
from apps.shop.content import shop_id

from .helpers import assert_message_limits, button_ids, interactive_of, row_ids


@pytest.fixture
def rule(workspace):
    return AutomationRuleFactory(workspace=workspace, keywords=["price"])


@pytest.fixture
def message(conversation):
    return MessageFactory(conversation=conversation, inbound=True, text="price")


def run(handler, rule, message, conversation, config=None, index=0):
    return handler(
        rule=rule, message=message, conversation=conversation, config=config or {}, index=index
    )


def sent(result) -> Message:
    return Message.objects.get(pk=result["message_id"])


def test_actions_are_registered():
    assert hooks.get_commerce_action("send_shop_menu") is actions.send_shop_menu
    assert hooks.get_commerce_action("send_catalog") is actions.send_catalog
    assert hooks.get_commerce_action("send_collection") is actions.send_collection


def test_send_shop_menu(store, rule, message, conversation):
    result = run(actions.send_shop_menu, rule, message, conversation, index=1)

    reply = sent(result)
    assert button_ids(reply) == [shop_id("browse"), shop_id("orders"), shop_id("talk")]
    assert (reply.source, reply.source_ref) == (Message.Source.AUTOMATION, str(rule.pk))
    assert reply.idempotency_key == hooks.idempotency_key(rule, message, 1)
    assert_message_limits(reply)

    again = run(actions.send_shop_menu, rule, message, conversation, index=1)
    assert again == result


@pytest.mark.parametrize(
    "handler", [actions.send_shop_menu, actions.send_catalog, actions.send_collection]
)
def test_actions_skip_when_the_store_is_unavailable(store, rule, message, conversation, handler):
    store.enabled = False
    store.save()

    with pytest.raises(ActionSkipped) as excinfo:
        run(handler, rule, message, conversation, {"collection_id": "x"})

    assert excinfo.value.code == "store_unavailable"
    assert excinfo.value.message == hooks.STORE_UNAVAILABLE


def test_send_catalog_in_bot_mode(store, sweets, product, rule, message, conversation):
    reply = sent(run(actions.send_catalog, rule, message, conversation))

    assert row_ids(reply) == [shop_id("col", sweets.pk, 0)]


def test_send_catalog_in_native_mode(store, number, product, rule, message, conversation):
    store.shop_mode = StoreSettings.ShopMode.NATIVE_CATALOG
    store.save()
    MetaCatalogFactory(waba=number.waba)

    reply = sent(run(actions.send_catalog, rule, message, conversation))

    assert interactive_of(reply)["type"] == "catalog_message"


def test_send_catalog_without_products(store, rule, message, conversation):
    with pytest.raises(ActionSkipped) as excinfo:
        run(actions.send_catalog, rule, message, conversation)

    assert excinfo.value.code == "store_empty"


def test_send_collection(store, workspace, sweets, rule, message, conversation):
    products = [
        ProductFactory(workspace=workspace, collection=sweets, position=i) for i in range(10)
    ]

    reply = sent(
        run(actions.send_collection, rule, message, conversation, {"collection_id": str(sweets.pk)})
    )

    ids = row_ids(reply)
    assert ids[:9] == [shop_id("prod", p.pk) for p in products[:9]]
    assert ids[9] == shop_id("col", sweets.pk, 9)
    assert_message_limits(reply)


def test_send_collection_in_native_mode(
    store, workspace, number, sweets, rule, message, conversation
):
    store.shop_mode = StoreSettings.ShopMode.NATIVE_CATALOG
    store.save()
    meta_catalog = MetaCatalogFactory(waba=number.waba)
    synced = ProductFactory(
        workspace=workspace, collection=sweets, meta_sync_status=Product.SyncStatus.SYNCED
    )
    ProductFactory(workspace=workspace, collection=sweets)  # not synced: not in Meta's catalog

    reply = sent(
        run(actions.send_collection, rule, message, conversation, {"collection_id": str(sweets.pk)})
    )

    data = interactive_of(reply)
    assert data["type"] == "product_list"
    assert data["action"] == {
        "catalog_id": meta_catalog.catalog_id,
        "sections": [{"title": "Sweets", "product_items": [{"product_retailer_id": synced.sku}]}],
    }


@pytest.mark.parametrize(
    "config",
    [{}, {"collection_id": "nope"}, {"collection_id": "0b7f6f7e-4a57-4b3e-9a4a-4b0d1f3f7c11"}],
)
def test_send_collection_unknown_collection(store, rule, message, conversation, config):
    with pytest.raises(ActionFailed) as excinfo:
        run(actions.send_collection, rule, message, conversation, config)

    assert excinfo.value.code == "collection_not_found"


def test_send_collection_of_another_workspace_or_inactive(
    store, other_workspace, workspace, rule, message, conversation
):
    foreign = CollectionFactory(workspace=other_workspace)
    inactive = CollectionFactory(workspace=workspace, is_active=False)
    ProductFactory(workspace=workspace, collection=inactive)

    for collection in (foreign, inactive):
        with pytest.raises(ActionFailed):
            run(
                actions.send_collection,
                rule,
                message,
                conversation,
                {"collection_id": str(collection.pk)},
            )


def test_send_collection_without_products(store, sweets, rule, message, conversation):
    with pytest.raises(ActionSkipped) as excinfo:
        run(actions.send_collection, rule, message, conversation, {"collection_id": str(sweets.pk)})

    assert excinfo.value.code == "collection_empty"


def test_outside_the_service_window_the_policy_error_propagates(store, rule, message, conversation):
    conversation.service_window_expires_at = timezone.now() - timedelta(hours=1)
    conversation.save()

    with pytest.raises(OutsideServiceWindow):
        run(actions.send_shop_menu, rule, message, conversation)


def test_engine_runs_a_shop_action(store, workspace, sweets, product, conversation):
    rule = AutomationRuleFactory(
        workspace=workspace,
        keywords=["price"],
        actions=[{"type": "send_collection", "config": {"collection_id": str(sweets.pk)}}],
    )
    message = MessageFactory(conversation=conversation, inbound=True, text="price")

    [automation_run] = process_inbound(message.pk)

    assert automation_run.status == "succeeded"
    [result] = automation_run.action_results
    reply = Message.objects.get(pk=result["message_id"])
    assert reply.source_ref == str(rule.pk)
    assert row_ids(reply) == [shop_id("prod", product.pk)]


def test_engine_records_a_skipped_shop_action(workspace, conversation):
    AutomationRuleFactory(
        workspace=workspace, keywords=["price"], actions=[{"type": "send_shop_menu", "config": {}}]
    )
    message = MessageFactory(conversation=conversation, inbound=True, text="price")

    [automation_run] = process_inbound(message.pk)

    assert automation_run.status == "skipped"
    assert automation_run.action_results[0]["code"] == "store_unavailable"
