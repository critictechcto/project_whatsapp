"""Native WhatsApp carts (``order`` messages) → re-priced checkout."""

from apps.catalog.factories import ProductFactory
from apps.catalog.services import CartLine
from apps.shop import content, services

from .helpers import body_of


def test_native_order_is_repriced_and_checked_out(buyer, store, workspace, product, orders_calls):
    laddu = ProductFactory(workspace=workspace, sku="LADDU-1", price_paise=9900)

    assert buyer.sends_order(
        [
            {
                "product_retailer_id": product.sku,
                "quantity": 2,
                "item_price": 450,
                "currency": "INR",
            },
            {
                "product_retailer_id": "LADDU-1",
                "quantity": 1,
                "item_price": "99.50",
                "currency": "INR",
            },
        ]
    )

    [call] = orders_calls.start_checkout
    assert call["source"] == "native_cart"
    assert call["source_wamid"] == buyer.last.wamid
    assert call["quoted_total_paise"] == 2 * 45000 + 9950  # what the buyer saw
    assert call["workspace"].pk == workspace.pk
    assert call["conversation"].pk == buyer.last.conversation_id
    cart = call["cart"]
    assert [(line.product.pk, line.quantity) for line in cart.lines] == [
        (product.pk, 2),
        (laddu.pk, 1),
    ]
    assert cart.subtotal_paise == 2 * 49900 + 9900  # the charge comes from the database
    assert buyer.replies() == []


def test_native_order_quantities_are_capped(buyer, store, product, orders_calls):
    product.stock_qty = 1
    product.save()

    buyer.sends_order([{"product_retailer_id": product.sku, "quantity": 3, "item_price": 499}])

    [call] = orders_calls.start_checkout
    assert [(line.product.pk, line.quantity) for line in call["cart"].lines] == [(product.pk, 1)]
    assert [line.reason for line in call["cart"].dropped] == ["quantity_capped"]
    assert call["quoted_total_paise"] == 3 * 49900


def test_native_order_with_nothing_available(buyer, store, orders_calls):
    assert buyer.sends_order([{"product_retailer_id": "GONE", "quantity": 1, "item_price": 10}])

    assert orders_calls.start_checkout == []
    [reply] = buyer.replies()
    assert body_of(reply) == "Sorry, the items in your cart are not available right now."


def test_native_order_is_handled_once(buyer, store, product, orders_calls):
    buyer.sends_order([{"product_retailer_id": product.sku, "quantity": 1, "item_price": 499}])

    assert services.handle_inbound(buyer.last.pk) is False

    assert len(orders_calls.start_checkout) == 1


def test_parse_native_order():
    lines, quoted = services.parse_native_order(
        {
            "order": {
                "product_items": [
                    {"product_retailer_id": "A", "quantity": 2, "item_price": 249.5},
                    {"product_retailer_id": "B", "quantity": True, "item_price": 1},  # not a number
                    {"product_retailer_id": "", "quantity": 1, "item_price": 1},
                    "junk",
                    {"product_retailer_id": "C", "quantity": "3", "item_price": "10"},
                ]
            }
        }
    )
    assert lines == [CartLine(quantity=2, sku="A"), CartLine(quantity=3, sku="C")]
    assert quoted == 49900 + 3000


def test_parse_native_order_without_valid_prices():
    items = [
        {"product_retailer_id": "A", "quantity": 1, "item_price": "NaN"},
        {"product_retailer_id": "B", "quantity": 1, "item_price": 10},
    ]
    lines, quoted = services.parse_native_order({"order": {"product_items": items}})
    assert len(lines) == 2
    assert quoted is None

    assert services.parse_native_order({"order": {"product_items": [{"quantity": 1}]}}) == (
        [],
        None,
    )
    assert services.parse_native_order({}) == ([], None)


def test_empty_cart_notice_fits_meta_limits():
    reply = content.empty_cart_content("x" * 5000)
    assert len(reply.interactive["body"]["text"]) == 1024
