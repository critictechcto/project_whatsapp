"""Journey: a seller opens a WhatsApp store from the dashboard API (products, their own payment
gateway, an alert number, store settings); a buyer shops through the bot and pays online or cash
on delivery; the seller packs and ships from the dashboard; stale buttons change nothing."""

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.payments.models import PaymentLink
from apps.payments.testing import fake_payments  # noqa: F401  (pytest fixture)
from apps.tenants.models import Workspace

from .conftest import CUSTOMER_WA_ID, DISPLAY_PHONE_NUMBER, PHONE_NUMBER_ID
from .test_e2e_commerce_support import (
    WhatsAppUser,
    body_text,
    buyer_messages,
    checkout_to_payment_choice,
    last_buyer_message,
    option_id,
    platform_sends,
    reply_ids,
    store_sends,
)
from .test_journey_support import error, ok, results

pytest_plugins = ["tests.test_journey_support"]
pytestmark = pytest.mark.django_db

SELLER_PHONE = "+919700000001"
SELLER_WA_ID = SELLER_PHONE.removeprefix("+")
STALE_TEXT = "This option is no longer available."
SHIPPING = 5000
COD_FEE = 4000
KAJU = 24900


def order_api(api, order_id) -> dict:
    return ok(api.get(f"/api/v1/orders/{order_id}/"))


def open_store(seller_api, deliver_meta, fake_graph, *, gateway: bool = True) -> dict:
    """Everything a seller does in the dashboard before the first order. Returns the product."""
    checklist = {
        i["key"]: i["done"] for i in ok(seller_api.get("/api/v1/store/checklist/"))["items"]
    }
    assert checklist["whatsapp_connected"] is True
    assert checklist["products_added"] is False

    sweets = ok(
        seller_api.post(
            "/api/v1/catalog/collections/", {"name": "Sweets", "description": "Fresh every day"}
        ),
        201,
    )
    kaju = ok(
        seller_api.post(
            "/api/v1/catalog/products/",
            {
                "sku": "KAJU-250",
                "name": "Kaju Katli 250 g",
                "price_paise": KAJU,
                "collection_id": sweets["id"],
                "stock_qty": 10,
                "max_qty_per_order": 5,
            },
        ),
        201,
    )
    assert kaju["stock_qty"] == 10

    if gateway:
        account = ok(
            seller_api.patch(
                "/api/v1/payments/account/",
                {
                    "provider": "razorpay",
                    "key_id": "rzp_test_SharmaSweets01",
                    "key_secret": "sharma-sweets-secret",
                },
            )
        )
        assert (account["mode"], account["status"], account["has_key_secret"]) == (
            "test",
            "unverified",
            True,
        )
        assert "key_secret" not in account
        assert ok(seller_api.post("/api/v1/payments/account/verify/"))["status"] == "verified"

    # The owner's personal phone gets order alerts once it confirms from WhatsApp.
    recipient = ok(
        seller_api.post(
            "/api/v1/seller-alerts/recipients/", {"name": "Ravi", "phone_e164": SELLER_PHONE}
        ),
        201,
    )
    assert recipient["status"] == "pending"
    [verification] = platform_sends(fake_graph, SELLER_WA_ID)
    verify_id = f"upc:alerts:verify:{recipient['id']}"
    assert verify_id in reply_ids(verification)
    seller_phone(deliver_meta).taps_template_button(verify_id, "Yes, send alerts")
    [recipient] = results(seller_api.get("/api/v1/seller-alerts/recipients/"))
    assert recipient["status"] == "verified"

    store = ok(
        seller_api.patch(
            "/api/v1/store/settings/",
            {
                "enabled": True,
                "store_name": "Sharma Sweets",
                "welcome_message": "Namaste! Welcome to Sharma Sweets.",
                "order_prefix": "SS",
                "shipping_fee_paise": SHIPPING,
                "free_shipping_above_paise": 200000,
                "cod_enabled": True,
                "cod_fee_paise": COD_FEE,
                "cod_max_order_paise": 60000,
            },
        )
    )
    assert store["enabled"] is True
    checklist = {
        i["key"]: i["done"] for i in ok(seller_api.get("/api/v1/store/checklist/"))["items"]
    }
    assert checklist["products_added"] is True
    assert checklist["payments_configured"] is gateway
    assert checklist["alert_number_verified"] is True
    assert checklist["store_enabled"] is True
    return kaju


def seller_phone(deliver_meta) -> WhatsAppUser:
    return WhatsAppUser(
        deliver_meta,
        wa_id=SELLER_WA_ID,
        name="Ravi",
        phone_number_id=settings.PLATFORM_WA_PHONE_NUMBER_ID,
        display=settings.PLATFORM_WA_DISPLAY_PHONE_NUMBER,
    )


def buyer_phone(deliver_meta) -> WhatsAppUser:
    return WhatsAppUser(
        deliver_meta,
        wa_id=CUSTOMER_WA_ID,
        name="Priya Sharma",
        phone_number_id=PHONE_NUMBER_ID,
        display=DISPLAY_PHONE_NUMBER,
    )


def test_buyer_pays_online_and_the_seller_ships_from_the_dashboard(
    seller_api,
    deliver_meta,
    fake_graph,
    fake_payments,  # noqa: F811
    run_on_commit,
):
    kaju = open_store(seller_api, deliver_meta, fake_graph)
    setup_sends = len(platform_sends(fake_graph, SELLER_WA_ID))  # verification + confirmation
    workspace = Workspace.objects.get(pk=seller_api.workspace_id)
    buyer = buyer_phone(deliver_meta)

    # hi → menu → collection → product → add to cart → checkout → address.
    checkout_to_payment_choice(buyer, workspace)
    [listed] = results(seller_api.get("/api/v1/orders/"))
    order = order_api(seller_api, listed["id"])
    assert order["number"].startswith("SS-")
    assert (order["status"], order["source"]) == ("awaiting_payment_method", "bot")
    assert (order["subtotal_paise"], order["shipping_paise"], order["total_paise"]) == (
        KAJU,
        SHIPPING,
        KAJU + SHIPPING,
    )
    assert order["address"]["pincode"] == "110001"
    offer = last_buyer_message(workspace)
    assert f"Cash on delivery adds ₹{COD_FEE // 100}" in body_text(offer)
    pay_online_id = option_id(offer, "Pay online")

    # Pay online: stock is held and the buyer gets the seller's own gateway link.
    buyer.taps(pay_online_id, "Pay online")
    order = order_api(seller_api, order["id"])
    assert (order["status"], order["payment_method"]) == ("pending_payment", "online")
    assert order["cod_fee_paise"] == 0
    link = order["payment_link"]
    assert (link["status"], link["amount_paise"]) == ("created", KAJU + SHIPPING)
    assert ok(seller_api.get(f"/api/v1/catalog/products/{kaju['id']}/"))["stock_qty"] == 9
    cta = store_sends(fake_graph)[-1]
    assert cta["interactive"]["type"] == "cta_url"
    assert cta["interactive"]["action"]["parameters"]["url"] == link["short_url"]
    assert platform_sends(fake_graph, SELLER_WA_ID)[setup_sends:] == []  # no alert before payment

    # The buyer pays and lands on the return page, which confirms the payment.
    provider_link_id = PaymentLink.objects.get(pk=link["id"]).provider_link_id
    fake_payments.mark_paid(provider_link_id)
    with run_on_commit():
        page = APIClient().get(reverse("payments_return:link-return", args=[link["id"]]))
    assert page.status_code == 200
    order = order_api(seller_api, order["id"])
    assert (order["status"], order["payment_status"]) == ("confirmed", "paid")
    assert order["payment_link"]["status"] == "paid"
    assert order["number"] in body_text(last_buyer_message(workspace))

    # The seller's phone gets one new-order alert from the UpChatz number.
    [alert] = platform_sends(fake_graph, SELLER_WA_ID)[setup_sends:]
    assert alert["phone_number_id"] == settings.PLATFORM_WA_PHONE_NUMBER_ID
    assert order["number"] in str(alert)

    # Opening the return page again (or polling) confirms nothing twice.
    with run_on_commit():
        APIClient().get(reverse("payments_return:link-return", args=[link["id"]]))
    assert len(platform_sends(fake_graph, SELLER_WA_ID)) == setup_sends + 1

    # A stale "Pay online" tap is refused and changes nothing.
    before = order_api(seller_api, order["id"])
    buyer.taps(pay_online_id, "Pay online")
    assert body_text(last_buyer_message(workspace)) == STALE_TEXT
    assert order_api(seller_api, order["id"]) == before
    assert len(fake_payments.calls_to("create_link")) == 1

    # Packed, then shipped from the dashboard; the buyer gets the tracking link.
    base = f"/api/v1/orders/{order['id']}/"
    assert "packed" in order["allowed_transitions"]
    packed = ok(seller_api.post(f"{base}transition/", {"to_status": "packed"}))
    assert packed["status"] == "packed"
    error(
        seller_api.post(f"{base}transition/", {"to_status": "confirmed"}),
        409,
        "invalid_order_transition",
    )
    shipped = ok(
        seller_api.post(
            f"{base}transition/",
            {
                "to_status": "shipped",
                "courier_name": "Delhivery",
                "awb_number": "1234567890",
                "tracking_url": "https://track.example/1234567890",
            },
        )
    )
    assert (shipped["status"], shipped["awb_number"]) == ("shipped", "1234567890")
    update = store_sends(fake_graph)[-1]
    assert update["to"] == CUSTOMER_WA_ID
    assert update["interactive"]["type"] == "cta_url"
    assert update["interactive"]["action"]["parameters"]["url"] == (
        "https://track.example/1234567890"
    )
    assert "Delhivery" in body_text(update)
    events = [e["to_status"] for e in results(seller_api.get(f"{base}events/", {"page_size": 50}))]
    assert [s for s in events if s] == [
        "awaiting_address",
        "awaiting_payment_method",
        "pending_payment",
        "confirmed",
        "packed",
        "shipped",
    ]
    assert Product.objects.get(pk=kaju["id"]).stock_qty == 9


def test_cash_on_delivery_adds_the_fee_and_stops_above_the_limit(
    seller_api,
    deliver_meta,
    fake_graph,
    fake_payments,  # noqa: F811
):
    open_store(seller_api, deliver_meta, fake_graph)
    setup_sends = len(platform_sends(fake_graph, SELLER_WA_ID))
    workspace = Workspace.objects.get(pk=seller_api.workspace_id)
    buyer = buyer_phone(deliver_meta)

    # One box: COD is offered, and the fee is added to the total.
    checkout_to_payment_choice(buyer, workspace)
    offer = last_buyer_message(workspace)
    buyer.taps(option_id(offer, "Cash on delivery"), "Cash on delivery")
    [listed] = results(seller_api.get("/api/v1/orders/"))
    order = order_api(seller_api, listed["id"])
    assert (order["status"], order["payment_method"], order["payment_status"]) == (
        "confirmed",
        "cod",
        "cod_pending",
    )
    assert (order["cod_fee_paise"], order["total_paise"]) == (COD_FEE, KAJU + SHIPPING + COD_FEE)
    assert order["payment_link"] is None
    assert fake_payments.calls_to("create_link") == []
    [alert] = platform_sends(fake_graph, SELLER_WA_ID)[setup_sends:]
    assert order["number"] in str(alert)
    assert ok(seller_api.get("/api/v1/orders/summary/"))["open_count"] == 1

    # Replaying the COD tap is refused and changes nothing.
    messages = len(buyer_messages(workspace))
    buyer.taps(option_id(offer, "Cash on delivery"), "Cash on delivery")
    assert body_text(last_buyer_message(workspace)) == STALE_TEXT
    assert len(buyer_messages(workspace)) == messages + 1
    assert order_api(seller_api, order["id"]) == order

    # Three boxes (₹747 + ₹50 shipping) are above the ₹600 COD limit: only online payment.
    checkout_to_payment_choice(buyer, workspace, quantity_taps=3)
    offer = last_buyer_message(workspace)
    option_id(offer, "Pay online")
    with pytest.raises(AssertionError):
        option_id(offer, "Cash on delivery")
    big = Order.objects.filter(workspace=workspace).latest("created_at")
    assert (big.subtotal_paise, big.shipping_paise) == (3 * KAJU, SHIPPING)

    # A forged COD button for that order is refused by the server.
    buyer.taps(f"upc:chk:pay:{big.pk}:cod", "Cash on delivery")
    assert "Cash on delivery isn't available for this order." in body_text(
        last_buyer_message(workspace)
    )
    big.refresh_from_db()
    assert (big.status, big.payment_method, big.cod_fee_paise) == (
        "awaiting_payment_method",
        "",
        0,
    )
    assert Product.objects.get(sku="KAJU-250", workspace=workspace).stock_qty == 9
