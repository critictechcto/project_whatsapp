"""Demo store for ``manage.py seed_demo``: "Sharma Sweets" settings and orders in every status.

Uses the catalog's demo products when there are any and otherwise creates a few minimal ones.
Rows are written directly (no messages are sent, no stock moves, no events are emitted) and keyed
on natural keys (SKU, phone, order number), so running the seeder again changes nothing.
"""

from datetime import timedelta

from django.utils import timezone

from apps.catalog.models import Product
from apps.contacts.models import Contact
from apps.whatsapp.models import PhoneNumber
from common.phone import to_wa_id

from . import transitions
from .models import Order, OrderCounter, OrderEvent, OrderItem, StoreSettings

STORE_NAME = "Sharma Sweets"
ORDER_PREFIX = "SS"
SHIPPING_FEE_PAISE = 4900
FREE_SHIPPING_ABOVE_PAISE = 99900
COD_FEE_PAISE = 2000

STORE_SETTINGS = {
    "enabled": True,
    "store_name": STORE_NAME,
    "welcome_message": (
        "Namaste! Welcome to Sharma Sweets. Fresh mithai and namkeen, delivered across India."
    ),
    "order_prefix": ORDER_PREFIX,
    "min_order_paise": 19900,
    "shipping_fee_paise": SHIPPING_FEE_PAISE,
    "free_shipping_above_paise": FREE_SHIPPING_ABOVE_PAISE,
    "cod_enabled": True,
    "cod_fee_paise": COD_FEE_PAISE,
    "cod_max_order_paise": 500000,
    "support_message": "Our team replies between 10 am and 7 pm. Tell us how we can help.",
}

# Used only when the catalog has no products: (sku, name, price_paise).
FALLBACK_PRODUCTS = [
    ("SS-KAJU-250", "Kaju Katli 250 g", 24900),
    ("SS-LADDOO-500", "Motichoor Laddoo 500 g", 29900),
    ("SS-SOAN-400", "Soan Papdi 400 g", 19900),
    ("SS-NAMKEEN-400", "Bhujia Namkeen 400 g", 14900),
]

# (name, phone, line1, city, state, pincode)
BUYERS = [
    ("Asha Verma", "+919812345701", "12, MG Road", "Pune", "Maharashtra", "411001"),
    ("Vikram Singh", "+919812345702", "44, Civil Lines", "Jaipur", "Rajasthan", "302006"),
    ("Meera Nair", "+919812345703", "7, Marine Drive", "Kochi", "Kerala", "682031"),
    ("Arjun Reddy", "+919812345704", "221, Banjara Hills", "Hyderabad", "Telangana", "500034"),
    ("Kavya Iyer", "+919812345705", "9, T Nagar", "Chennai", "Tamil Nadu", "600017"),
    ("Rohan Gupta", "+919812345706", "31, Sector 18", "Noida", "Uttar Pradesh", "201301"),
    ("Ishita Das", "+919812345707", "5, Salt Lake", "Kolkata", "West Bengal", "700091"),
    ("Farhan Ali", "+919812345708", "18, Koramangala", "Bengaluru", "Karnataka", "560034"),
]

DELHIVERY = {
    "courier_name": "Delhivery",
    "awb_number": "",
    "tracking_url": "https://www.delhivery.com/track/package/",
}

# (sequence, status, payment_status, payment_method, buyer, hours_ago, [(product, qty)], extra).
# Checkout-stage orders use distinct buyers: one active checkout per contact and number.
S, P = Order.Status, Order.PaymentStatus
ONLINE, COD = Order.PaymentMethod.ONLINE, Order.PaymentMethod.COD
DEMO_ORDERS = [
    (1001, S.DELIVERED, P.PAID, ONLINE, 0, 240, [(0, 2), (1, 1)], {"awb": "DL5100100101"}),
    (1002, S.DELIVERED, P.COD_COLLECTED, COD, 1, 200, [(2, 3)], {"awb": "DL5100100102"}),
    (1003, S.SHIPPED, P.PAID, ONLINE, 2, 72, [(1, 2), (3, 2)], {"awb": "DL5100100103"}),
    (1004, S.SHIPPED, P.COD_PENDING, COD, 3, 60, [(0, 1)], {"awb": "DL5100100104"}),
    (1005, S.PACKED, P.PAID, ONLINE, 4, 30, [(0, 4)], {}),
    (1006, S.CONFIRMED, P.PAID, ONLINE, 5, 6, [(1, 1), (2, 1)], {}),
    (1007, S.CONFIRMED, P.COD_PENDING, COD, 6, 3, [(3, 3)], {}),
    (
        1008,
        S.NEEDS_ATTENTION,
        P.PAID,
        ONLINE,
        7,
        20,
        [(0, 2)],
        {"detail": "Paid after the checkout expired, and Kaju Katli ran out. Refund or restock."},
    ),
    (
        1009,
        S.CANCELLED,
        P.REFUNDED_MANUAL,
        ONLINE,
        0,
        120,
        [(1, 2)],
        {"cancel_reason": "Out of stock"},
    ),
    (
        1010,
        S.CANCELLED,
        P.UNPAID,
        "",
        1,
        100,
        [(2, 1), (3, 1)],
        {"cancel_reason": "Cancelled by the buyer."},
    ),
    (1011, S.EXPIRED, P.UNPAID, "", 2, 50, [(0, 1), (3, 1)], {}),
    (1012, S.DRAFT, P.UNPAID, "", 3, 1, [(1, 1)], {}),
    (1013, S.AWAITING_CONFIRMATION, P.UNPAID, "", 4, 0.9, [(2, 2)], {"quoted_delta": -2000}),
    (1014, S.AWAITING_ADDRESS, P.UNPAID, "", 5, 0.5, [(0, 1), (1, 1)], {}),
    (1015, S.AWAITING_PAYMENT_METHOD, P.UNPAID, "", 6, 0.3, [(3, 2)], {}),
    (1016, S.PENDING_PAYMENT, P.UNPAID, ONLINE, 7, 0.2, [(0, 3)], {}),
]

# Statuses an order passed through, used for its timestamps.
PROGRESS = [S.CONFIRMED, S.PACKED, S.SHIPPED, S.DELIVERED]
TIMESTAMP_FIELDS = {
    S.CONFIRMED: "confirmed_at",
    S.PACKED: "packed_at",
    S.SHIPPED: "shipped_at",
    S.DELIVERED: "delivered_at",
}


def seed(workspace) -> None:
    phone_number = (
        PhoneNumber.objects.filter(workspace=workspace)
        .order_by("-is_default", "created_at")
        .first()
    )
    _seed_store_settings(workspace)
    if phone_number is None:
        return
    products = _products(workspace)
    now = timezone.now().replace(microsecond=0)
    for spec in DEMO_ORDERS:
        _seed_order(workspace, phone_number, products, spec, now)
    counter, _ = OrderCounter.objects.get_or_create(workspace=workspace)
    highest = max(spec[0] for spec in DEMO_ORDERS)
    if counter.last_value < highest:
        counter.last_value = highest
        counter.save(update_fields=["last_value", "updated_at"])


def _seed_store_settings(workspace) -> StoreSettings:
    store_settings, _ = StoreSettings.objects.get_or_create(
        workspace=workspace, defaults=STORE_SETTINGS
    )
    return store_settings


def _products(workspace) -> list[Product]:
    products = list(
        Product.objects.filter(workspace=workspace, is_active=True).order_by("position", "name")[
            : len(FALLBACK_PRODUCTS)
        ]
    )
    if products:
        return products
    created = []
    for position, (sku, name, price) in enumerate(FALLBACK_PRODUCTS):
        product, _ = Product.objects.get_or_create(
            workspace=workspace,
            sku=sku,
            defaults={"name": name, "price_paise": price, "position": position},
        )
        created.append(product)
    return created


def _contact(workspace, buyer) -> Contact:
    name, phone, *_ = buyer
    contact, _ = Contact.objects.get_or_create(
        workspace=workspace,
        phone_e164=phone,
        defaults={"wa_id": to_wa_id(phone), "name": name},
    )
    return contact


def _address(buyer) -> dict:
    name, phone, line1, city, state, pincode = buyer
    return {
        "name": name,
        "phone_e164": phone,
        "line1": line1,
        "line2": "",
        "landmark": "",
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": "IN",
    }


def _seed_order(workspace, phone_number, products, spec, now) -> None:
    sequence, status, payment_status, method, buyer_index, hours_ago, lines, extra = spec
    number = f"{ORDER_PREFIX}-{sequence}"
    if Order.objects.filter(workspace=workspace, number=number).exists():
        return
    buyer = BUYERS[buyer_index]
    contact = _contact(workspace, buyer)
    created_at = now - timedelta(hours=hours_ago)

    items = []
    for position, (product_index, quantity) in enumerate(lines):
        product = products[product_index % len(products)]
        unit_price = product.sale_price_paise or product.price_paise
        items.append((position, product, unit_price, quantity))
    subtotal = sum(unit_price * quantity for _, _, unit_price, quantity in items)
    shipping = 0 if subtotal >= FREE_SHIPPING_ABOVE_PAISE else SHIPPING_FEE_PAISE
    cod_fee = COD_FEE_PAISE if method == COD else 0
    in_checkout = status in transitions.CHECKOUT_STATUSES
    has_address = status not in (S.DRAFT, S.AWAITING_CONFIRMATION, S.AWAITING_ADDRESS)

    order = Order(
        workspace=workspace,
        contact=contact,
        phone_number=phone_number,
        number=number,
        status=status,
        payment_status=payment_status,
        payment_method=method,
        item_count=sum(quantity for *_, quantity in items),
        subtotal_paise=subtotal,
        shipping_paise=shipping,
        cod_fee_paise=cod_fee,
        total_paise=subtotal + shipping + cod_fee,
        address=_address(buyer) if has_address else None,
        cancel_reason=extra.get("cancel_reason", ""),
        stock_reserved=status in (S.PENDING_PAYMENT, *transitions.OPEN_STATUSES),
        checkout_attempt=1 if method == ONLINE else 0,
        expires_at=now + timedelta(minutes=30) if in_checkout else None,
    )
    if "quoted_delta" in extra:
        order.quoted_total_paise = subtotal + extra["quoted_delta"]
    if extra.get("awb"):
        order.courier_name = DELHIVERY["courier_name"]
        order.awb_number = extra["awb"]
        order.tracking_url = DELHIVERY["tracking_url"] + extra["awb"]
    _set_timestamps(order, status, payment_status, created_at)
    order.save()
    Order.objects.filter(pk=order.pk).update(created_at=created_at)

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                workspace=workspace,
                order=order,
                product=product,
                position=position,
                sku=product.sku,
                name=product.name[:200],
                unit_price_paise=unit_price,
                quantity=quantity,
                line_total_paise=unit_price * quantity,
            )
            for position, product, unit_price, quantity in items
        ]
    )
    _seed_events(order, extra, created_at)


def _set_timestamps(order: Order, status: str, payment_status: str, created_at) -> None:
    step = timedelta(hours=1)
    if status in PROGRESS or status == S.NEEDS_ATTENTION:
        reached = PROGRESS[: PROGRESS.index(status) + 1] if status in PROGRESS else []
        for index, passed in enumerate(reached):
            setattr(order, TIMESTAMP_FIELDS[passed], created_at + step * (index + 1) / 4)
    if status == S.CANCELLED:
        order.cancelled_at = created_at + step
    if status == S.EXPIRED:
        order.expired_at = created_at + step
    if payment_status in (P.PAID, P.REFUNDED_MANUAL):
        order.paid_at = created_at + step / 6
    if payment_status == P.COD_COLLECTED:
        order.cod_collected_at = order.delivered_at
    if payment_status == P.REFUNDED_MANUAL:
        order.refunded_at = created_at + step * 2


def _seed_events(order: Order, extra: dict, created_at) -> None:
    events = [(OrderEvent.Type.CREATED, OrderEvent.Actor.BUYER, "", "", "Checkout started (bot).")]
    if order.status != S.DRAFT:
        actor = (
            OrderEvent.Actor.DASHBOARD
            if order.status in (S.PACKED, S.SHIPPED, S.DELIVERED)
            or (order.status == S.CANCELLED and order.payment_status == P.REFUNDED_MANUAL)
            else OrderEvent.Actor.SYSTEM
        )
        events.append(
            (
                OrderEvent.Type.STATUS_CHANGED,
                actor,
                "",
                order.status,
                extra.get("detail", ""),
            )
        )
    if order.payment_status in (P.PAID, P.REFUNDED_MANUAL):
        events.append(
            (OrderEvent.Type.PAYMENT_RECEIVED, OrderEvent.Actor.SYSTEM, "", "", "Paid online.")
        )
    if order.payment_status == P.REFUNDED_MANUAL:
        events.append(
            (
                OrderEvent.Type.REFUNDED_MANUAL,
                OrderEvent.Actor.DASHBOARD,
                "",
                "",
                "Refund recorded; the refund itself is made in the payment gateway.",
            )
        )
    for index, (event_type, actor, from_status, to_status, detail) in enumerate(events):
        event = OrderEvent.objects.create(
            workspace_id=order.workspace_id,
            order=order,
            type=event_type,
            actor=actor,
            from_status=from_status,
            to_status=to_status,
            detail=detail,
        )
        OrderEvent.objects.filter(pk=event.pk).update(
            created_at=created_at + timedelta(minutes=5 * index)
        )
