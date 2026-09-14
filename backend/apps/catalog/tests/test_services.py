"""Catalog services: cart pricing and stock reservation."""

import pytest

from apps.catalog import services
from apps.catalog.exceptions import OutOfStock
from apps.catalog.factories import ProductFactory
from apps.catalog.services import CartLine

pytestmark = pytest.mark.django_db


def test_price_items_totals_lines_and_uses_sale_price(workspace):
    tee = ProductFactory(workspace=workspace, price_paise=50000, sale_price_paise=40000)
    mug = ProductFactory(workspace=workspace, price_paise=25000)

    cart = services.price_items(
        workspace, [CartLine(quantity=2, product_id=tee.pk), CartLine(quantity=1, sku=mug.sku)]
    )

    assert [(line.product, line.quantity, line.line_total_paise) for line in cart.lines] == [
        (tee, 2, 80000),
        (mug, 1, 25000),
    ]
    assert cart.subtotal_paise == 105000
    assert cart.item_count == 3
    assert cart.dropped == ()
    assert not cart.is_empty


def test_price_items_merges_repeated_products(workspace):
    tee = ProductFactory(workspace=workspace, price_paise=10000)

    cart = services.price_items(
        workspace, [CartLine(quantity=1, sku=tee.sku), CartLine(quantity=2, product_id=tee.pk)]
    )

    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 3


def test_price_items_drops_unknown_inactive_and_out_of_stock(workspace, other_workspace):
    inactive = ProductFactory(workspace=workspace, is_active=False)
    sold_out = ProductFactory(workspace=workspace, stock_qty=0)
    marked_out = ProductFactory(workspace=workspace, availability="out_of_stock")
    foreign = ProductFactory(workspace=other_workspace)

    cart = services.price_items(
        workspace,
        [
            CartLine(quantity=1, sku="NOPE"),
            CartLine(quantity=1, product_id=inactive.pk),
            CartLine(quantity=2, product_id=sold_out.pk),
            CartLine(quantity=1, product_id=marked_out.pk),
            CartLine(quantity=1, product_id=foreign.pk),
        ],
    )

    assert cart.is_empty
    assert cart.subtotal_paise == 0
    reasons = [(line.reason, line.requested, line.available) for line in cart.dropped]
    assert reasons == [
        ("unknown", 1, None),
        ("inactive", 1, None),
        ("out_of_stock", 2, 0),
        ("out_of_stock", 1, 0),
        ("unknown", 1, None),
    ]


def test_price_items_caps_quantity_by_limit_and_stock(workspace):
    limited = ProductFactory(workspace=workspace, max_qty_per_order=3, price_paise=1000)
    scarce = ProductFactory(workspace=workspace, stock_qty=2, price_paise=1000)

    cart = services.price_items(
        workspace,
        [CartLine(quantity=5, product_id=limited.pk), CartLine(quantity=4, product_id=scarce.pk)],
    )

    assert [line.quantity for line in cart.lines] == [3, 2]
    assert cart.subtotal_paise == 5000
    assert [(line.reason, line.requested, line.available) for line in cart.dropped] == [
        ("quantity_capped", 5, 3),
        ("quantity_capped", 4, 2),
    ]


def test_reserve_and_release_stock(workspace):
    tracked = ProductFactory(workspace=workspace, stock_qty=5)
    untracked = ProductFactory(workspace=workspace, stock_qty=None)

    services.reserve_stock(workspace, [(tracked.pk, 3), (untracked.pk, 50)])
    tracked.refresh_from_db()
    untracked.refresh_from_db()
    assert tracked.stock_qty == 2
    assert untracked.stock_qty is None

    services.release_stock(workspace, [(tracked.pk, 3), (untracked.pk, 50)])
    tracked.refresh_from_db()
    assert tracked.stock_qty == 5


def test_reserve_stock_is_all_or_nothing(workspace):
    plenty = ProductFactory(workspace=workspace, stock_qty=10)
    scarce = ProductFactory(workspace=workspace, stock_qty=1, sku="SCARCE", name="Scarce tee")

    with pytest.raises(OutOfStock) as caught:
        services.reserve_stock(workspace, [(plenty.pk, 4), (scarce.pk, 2)])

    plenty.refresh_from_db()
    scarce.refresh_from_db()
    assert (plenty.stock_qty, scarce.stock_qty) == (10, 1)
    assert caught.value.default_code == "out_of_stock"
    assert caught.value.detail["items"] == [
        {"sku": "SCARCE", "name": "Scarce tee", "requested": 2, "available": 1}
    ]


def test_list_shoppable_products_pages_active_products(workspace):
    products = [ProductFactory(workspace=workspace, position=index) for index in range(4)]
    ProductFactory(workspace=workspace, position=9, is_active=False)

    first, has_more = services.list_shoppable_products(workspace, offset=0, limit=3)
    rest, has_more_after = services.list_shoppable_products(workspace, offset=3, limit=3)

    assert list(first) == products[:3]
    assert has_more
    assert list(rest) == products[3:]
    assert not has_more_after
