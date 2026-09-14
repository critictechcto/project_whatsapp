"""Message builders stay inside Meta's interactive limits for any seller data."""

from types import SimpleNamespace

import pytest

from apps.catalog.models import Collection, Product
from apps.catalog.services import PricedCart, PricedLine
from apps.shop import content

from .helpers import assert_meta_limits

LONG = "Extra Special Premium Dry Fruit Kaju Katli Gift Box " * 5


def store(**overrides):
    values = {
        "store_name": "Sharma Sweets",
        "welcome_message": "",
        "powered_by_footer": True,
        "support_message": "",
    }
    return SimpleNamespace(**{**values, **overrides})


def product(name=LONG, price=99_99_999, sale=None, **kwargs):
    return Product(
        name=name, description=LONG * 3, price_paise=price, sale_price_paise=sale, **kwargs
    )


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (99, "₹0.99"),
        (24900, "₹249.00"),
        (145000, "₹1,450.00"),
        (10000000, "₹1,00,000.00"),
        (1234567890, "₹1,23,45,678.90"),
    ],
)
def test_format_inr(paise, text):
    assert content.format_inr(paise) == text


def test_menu_limits_with_the_longest_welcome_message():
    menu = content.menu_content(store(welcome_message="w" * 1024), notice=content.UNAVAILABLE)

    assert_meta_limits(menu.interactive)
    assert menu.interactive["body"]["text"].startswith(content.UNAVAILABLE)


def test_collections_list_has_at_most_ten_rows():
    collections = [Collection(name=f"{LONG} {i}", description=LONG) for i in range(15)]

    for has_other in (True, False):
        listing = content.collections_content(store(), collections, has_other=has_other)
        assert_meta_limits(listing.interactive)
        rows = listing.interactive["action"]["sections"][0]["rows"]
        assert len(rows) == 10
        assert (rows[-1]["title"] == "Other products") is has_other


def test_product_page_limits():
    products = [product(sale=1_00_000 + i) for i in range(12)]

    page = content.products_content(
        title=LONG, description=LONG, key="all", offset=99990, products=products, has_more=True
    )

    assert_meta_limits(page.interactive)
    rows = page.interactive["action"]["sections"][0]["rows"]
    assert len(rows) == 10
    assert rows[-1]["id"] == "upc:shop:col:all:99999"


def test_product_card_limits():
    card = content.product_card(product(sale=100), back_id=content.shop_id("browse"))

    assert_meta_limits(card.interactive)
    assert "header" not in card.interactive  # no image


def test_quantity_list_is_capped_at_ten_rows():
    listing = content.quantity_content(product(), 99)

    assert_meta_limits(listing.interactive)
    assert len(listing.interactive["action"]["sections"][0]["rows"]) == 10


def test_cart_with_many_long_lines_fits_the_body():
    lines = tuple(PricedLine(product(), 99, 99_99_999, 99 * 99_99_999) for _ in range(60))
    cart = PricedCart(
        lines=lines, dropped=(), subtotal_paise=sum(line.line_total_paise for line in lines)
    )
    notes = [f"{LONG} is out of stock and was removed."] * 10

    reply = content.cart_content(cart, notes=notes)

    assert_meta_limits(reply.interactive)
    assert "more" in reply.interactive["body"]["text"]


def test_added_and_catalog_content_limits():
    added = content.added_content(
        product(),
        requested=5,
        added=2,
        in_cart=2,
        cap=2,
        item_count=999,
        subtotal_paise=99_99_99_999,
        back_id=content.shop_id("col", "other", 99999),
    )
    assert_meta_limits(added.interactive)

    catalog_message = content.catalog_content(store(store_name=LONG), thumbnail_sku="SKU-1")
    assert_meta_limits(catalog_message.interactive)

    product_list = content.product_list_content("123", LONG, [f"SKU-{i}" for i in range(40)])
    assert len(product_list.interactive["action"]["sections"][0]["product_items"]) == 30
    assert len(product_list.interactive["header"]["text"]) <= 60
