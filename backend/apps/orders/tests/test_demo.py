import pytest

from apps.catalog.factories import ProductFactory
from apps.catalog.models import Product
from apps.contacts.models import Contact
from apps.orders import demo, services
from apps.orders.models import Order, OrderEvent, OrderItem, StoreSettings
from apps.whatsapp.factories import PhoneNumberFactory

pytestmark = pytest.mark.django_db


def counts(workspace) -> tuple[int, ...]:
    return (
        Order.objects.filter(workspace=workspace).count(),
        OrderItem.objects.filter(workspace=workspace).count(),
        OrderEvent.objects.filter(workspace=workspace).count(),
        Product.objects.filter(workspace=workspace).count(),
        Contact.objects.filter(workspace=workspace).count(),
    )


def test_seed_creates_orders_in_every_status_and_is_idempotent(workspace):
    PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)

    demo.seed(workspace)
    first = counts(workspace)
    demo.seed(workspace)

    orders = Order.objects.filter(workspace=workspace)
    assert set(orders.values_list("status", flat=True)) == set(Order.Status.values)
    assert all(order.items.exists() for order in orders)
    assert counts(workspace) == first
    store = StoreSettings.objects.get(workspace=workspace)
    assert (store.store_name, store.enabled, store.order_prefix) == ("Sharma Sweets", True, "SS")
    assert services.next_order_number(workspace) == "SS-1017"


def test_seed_uses_catalog_products_when_there_are_any(workspace):
    PhoneNumberFactory(workspace=workspace, waba__workspace=workspace, is_default=True)
    products = ProductFactory.create_batch(2, workspace=workspace)

    demo.seed(workspace)

    assert Product.objects.filter(workspace=workspace).count() == 2
    used = set(OrderItem.objects.filter(workspace=workspace).values_list("product_id", flat=True))
    assert used == {product.pk for product in products}
