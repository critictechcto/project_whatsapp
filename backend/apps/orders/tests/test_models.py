"""Orders models, store defaults and money formatting."""

import pytest
from django.db import IntegrityError, transaction

from apps.contacts.factories import ContactFactory
from apps.orders import services
from apps.orders.factories import OrderFactory, StoreSettingsFactory
from apps.orders.models import Order, OrderEvent, StoreSettings
from apps.orders.money import format_inr
from apps.orders.schema_enums import (
    ORDER_EVENT_ACTORS,
    ORDER_EVENT_TYPES,
    ORDER_SOURCES,
    ORDER_STATUSES,
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    SHOP_MODES,
)
from apps.tenants.factories import WorkspaceFactory
from apps.whatsapp.factories import PhoneNumberFactory


@pytest.mark.django_db
def test_one_active_checkout_per_contact_and_number(workspace):
    first = OrderFactory(workspace=workspace, status="awaiting_address")
    same = {"workspace": workspace, "contact": first.contact, "phone_number": first.phone_number}

    OrderFactory(**same, status="confirmed")
    OrderFactory(**same, status="expired")
    other_contact = ContactFactory(workspace=workspace)
    OrderFactory(**{**same, "contact": other_contact}, status="draft")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderFactory(**same, status="pending_payment")


@pytest.mark.django_db
def test_source_wamid_is_unique_per_workspace_when_set(workspace, other_workspace):
    OrderFactory(workspace=workspace, source="native_cart", source_wamid="wamid.CART1")
    OrderFactory(workspace=other_workspace, source="native_cart", source_wamid="wamid.CART1")
    OrderFactory(workspace=workspace, source_wamid="")
    OrderFactory(workspace=workspace, source_wamid="")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderFactory(workspace=workspace, source="native_cart", source_wamid="wamid.CART1")


@pytest.mark.django_db
def test_order_numbers_are_unique_per_workspace(workspace, other_workspace):
    OrderFactory(workspace=workspace, number="SS-1001")
    OrderFactory(workspace=other_workspace, number="SS-1001")

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderFactory(workspace=workspace, number="SS-1001")


@pytest.mark.django_db
def test_order_stage_and_allowed_transitions(workspace):
    order = OrderFactory(workspace=workspace, status="packed")

    assert order.stage == "open"
    assert order.allowed_transitions == ["shipped", "cancelled"]


def test_model_choices_match_contract_enums():
    assert tuple(Order.Status.values) == ORDER_STATUSES
    assert tuple(Order.PaymentStatus.values) == PAYMENT_STATUSES
    assert tuple(Order.PaymentMethod.values) == PAYMENT_METHODS
    assert tuple(Order.Source.values) == ORDER_SOURCES
    assert tuple(OrderEvent.Type.values) == ORDER_EVENT_TYPES
    assert tuple(OrderEvent.Actor.values) == ORDER_EVENT_ACTORS
    assert tuple(StoreSettings.ShopMode.values) == SHOP_MODES


@pytest.mark.django_db
def test_store_settings_are_created_lazily_with_defaults():
    workspace = WorkspaceFactory(name="Chaicraft")

    store_settings = services.get_store_settings(workspace)

    assert store_settings.store_name == "Chaicraft"
    assert store_settings.order_prefix == "CHA"
    assert store_settings.menu_keywords == ["hi", "hello", "menu", "shop", "start"]
    assert store_settings.powered_by_footer is True
    assert not store_settings.enabled
    assert services.get_store_settings(workspace).pk == store_settings.pk


@pytest.mark.parametrize(
    ("store_name", "prefix"),
    [
        ("Sharma Sweets", "SS"),
        ("The Good Grain Co", "TGGC"),
        ("a b c d e f g", "ABCDE"),
        ("Chaicraft", "CHA"),
        ("Q", "UPC"),
        ("123 !!", "UPC"),
        ("", "UPC"),
    ],
)
def test_derive_order_prefix(store_name, prefix):
    assert services.derive_order_prefix(store_name) == prefix


@pytest.mark.django_db
def test_store_link_uses_the_chosen_or_default_number(workspace):
    store_settings = StoreSettingsFactory(workspace=workspace)
    assert services.store_link(store_settings) is None

    PhoneNumberFactory(
        workspace=workspace,
        waba__workspace=workspace,
        is_default=True,
        display_phone_number="+91 98000 11111",
    )
    assert services.store_link(store_settings) == "https://wa.me/919800011111?text=Hi"

    chosen = PhoneNumberFactory(
        workspace=workspace, waba__workspace=workspace, display_phone_number="+91 99000 22222"
    )
    store_settings.phone_number = chosen
    assert services.store_link(store_settings) == "https://wa.me/919900022222?text=Hi"


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (5, "₹0.05"),
        (145000, "₹1,450.00"),
        (12345678, "₹1,23,456.78"),
        (1000000000, "₹1,00,00,000.00"),
        (-24950, "-₹249.50"),
    ],
)
def test_format_inr(paise, text):
    assert format_inr(paise) == text
