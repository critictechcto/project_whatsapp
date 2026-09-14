"""Orders: checkout, fulfilment and the store settings behind them.

Money is integer paise (GST included), currency INR. The status machine lives in
``transitions.py``; every status change writes an :class:`OrderEvent`. There is at most one
active checkout per (contact, phone number), enforced by ``orders_one_active_checkout``.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from common.models import TenantScopedModel, UUIDTimeStampedModel

from . import transitions

CURRENCY = "INR"
FIRST_ORDER_VALUE = 1000  # OrderCounter.last_value; the first order is <prefix>-1001
DEFAULT_MENU_KEYWORDS = ("hi", "hello", "menu", "shop", "start")
DEFAULT_ORDER_PREFIX = "UPC"

order_prefix_validator = RegexValidator(r"^[A-Z]{2,5}$", "Use 2-5 capital letters.")


def default_menu_keywords() -> list[str]:
    return list(DEFAULT_MENU_KEYWORDS)


class StoreSettings(UUIDTimeStampedModel):
    """One per workspace, created lazily by ``services.get_store_settings``."""

    class ShopMode(models.TextChoices):
        BOT = "bot", "Bot"
        NATIVE_CATALOG = "native_catalog", "Native catalog"

    # Order notification key -> template FK field (the OrderNotificationTemplates component).
    NOTIFICATION_TEMPLATE_FIELDS = {
        "confirmed": "confirmed_template",
        "packed": "packed_template",
        "shipped": "shipped_template",
        "delivered": "delivered_template",
        "cancelled": "cancelled_template",
        "payment_reminder": "payment_reminder_template",
    }

    workspace = models.OneToOneField(
        "tenants.Workspace", on_delete=models.CASCADE, related_name="store_settings"
    )
    enabled = models.BooleanField(default=False)
    shop_mode = models.CharField(max_length=16, choices=ShopMode.choices, default=ShopMode.BOT)
    store_name = models.CharField(max_length=60, blank=True)
    welcome_message = models.TextField(max_length=1024, blank=True)
    menu_keywords = models.JSONField(default=default_menu_keywords, blank=True)
    order_prefix = models.CharField(
        max_length=5, default=DEFAULT_ORDER_PREFIX, validators=[order_prefix_validator]
    )
    min_order_paise = models.PositiveIntegerField(default=0)
    shipping_fee_paise = models.PositiveIntegerField(default=0)
    free_shipping_above_paise = models.PositiveIntegerField(null=True, blank=True)
    cod_enabled = models.BooleanField(default=False)
    cod_fee_paise = models.PositiveIntegerField(default=0)
    cod_max_order_paise = models.PositiveIntegerField(null=True, blank=True)
    serviceable_pincodes = models.JSONField(default=list, blank=True)
    support_message = models.TextField(max_length=1024, blank=True)
    powered_by_footer = models.BooleanField(default=True)
    # The store number; null means the workspace default number.
    phone_number = models.ForeignKey(
        "whatsapp.PhoneNumber",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    confirmed_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    packed_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    shipped_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    delivered_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancelled_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    payment_reminder_template = models.ForeignKey(
        "message_templates.MessageTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(UUIDTimeStampedModel.Meta):
        verbose_name = "store settings"
        verbose_name_plural = "store settings"

    def __str__(self) -> str:
        return f"Store settings for {self.workspace_id}"

    @property
    def notification_templates(self) -> dict:
        return {
            key: getattr(self, f"{field}_id")
            for key, field in self.NOTIFICATION_TEMPLATE_FIELDS.items()
        }


class OrderCounter(models.Model):
    """Last order number issued per workspace; the row is locked while a number is allocated."""

    workspace = models.OneToOneField(
        "tenants.Workspace",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="order_counter",
    )
    last_value = models.PositiveIntegerField(default=FIRST_ORDER_VALUE)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.workspace_id}: {self.last_value}"


class Order(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_CONFIRMATION = "awaiting_confirmation", "Awaiting confirmation"
        AWAITING_ADDRESS = "awaiting_address", "Awaiting address"
        AWAITING_PAYMENT_METHOD = "awaiting_payment_method", "Awaiting payment method"
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        CONFIRMED = "confirmed", "Confirmed"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        NEEDS_ATTENTION = "needs_attention", "Needs attention"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"
        COD_PENDING = "cod_pending", "COD pending"
        COD_COLLECTED = "cod_collected", "COD collected"
        REFUNDED_MANUAL = "refunded_manual", "Refunded manually"

    class PaymentMethod(models.TextChoices):
        ONLINE = "online", "Online"
        COD = "cod", "Cash on delivery"

    class Source(models.TextChoices):
        BOT = "bot", "Bot"
        NATIVE_CART = "native_cart", "Native cart"

    CHECKOUT_STATUSES = transitions.CHECKOUT_STATUSES
    OPEN_STATUSES = transitions.OPEN_STATUSES
    CLOSED_STATUSES = transitions.CLOSED_STATUSES

    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="+")
    conversation = models.ForeignKey(
        "inbox.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    phone_number = models.ForeignKey(
        "whatsapp.PhoneNumber", on_delete=models.CASCADE, related_name="+"
    )
    number = models.CharField(max_length=16)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    payment_method = models.CharField(max_length=8, choices=PaymentMethod.choices, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.BOT)
    # The inbound native-cart message this order came from ("" for bot orders).
    source_wamid = models.CharField(max_length=128, blank=True)

    item_count = models.PositiveIntegerField(default=0)  # sum of item quantities
    subtotal_paise = models.PositiveIntegerField(default=0)
    shipping_paise = models.PositiveIntegerField(default=0)
    cod_fee_paise = models.PositiveIntegerField(default=0)
    total_paise = models.PositiveIntegerField(default=0)
    # The total the buyer's WhatsApp cart showed, when it came from a native cart.
    quoted_total_paise = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default=CURRENCY)

    # OrderAddress: {name, phone_e164, line1, line2, landmark, city, state, pincode, country}.
    address = models.JSONField(null=True, blank=True)

    courier_name = models.CharField(max_length=100, blank=True)
    awb_number = models.CharField(max_length=64, blank=True)
    tracking_url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(max_length=2000, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    # True while this order holds reserved stock (released on cancel/expiry with restock).
    stock_reserved = models.BooleanField(default=False)
    # Payment link attempts; PaymentLink.reference_id is "<number>-<attempt>".
    checkout_attempt = models.PositiveSmallIntegerField(default=0)

    expires_at = models.DateTimeField(null=True, blank=True)  # checkout deadline
    confirmed_at = models.DateTimeField(null=True, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cod_collected_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workspace", "number"], name="orders_unique_number"),
            models.UniqueConstraint(
                fields=["workspace", "source_wamid"],
                condition=~Q(source_wamid=""),
                name="orders_unique_source_wamid",
            ),
            models.UniqueConstraint(
                fields=["workspace", "contact", "phone_number"],
                condition=Q(status__in=transitions.CHECKOUT_STATUSES),
                name="orders_one_active_checkout",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace", "status", "created_at"], name="orders_ws_status_created_idx"
            ),
            models.Index(fields=["workspace", "created_at"], name="orders_ws_created_idx"),
            models.Index(fields=["workspace", "payment_status"], name="orders_ws_pay_status_idx"),
            models.Index(fields=["workspace", "payment_method"], name="orders_ws_pay_method_idx"),
            models.Index(
                fields=["workspace", "contact", "created_at"], name="orders_ws_contact_idx"
            ),
            models.Index(fields=["status", "expires_at"], name="orders_status_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.number} ({self.status})"

    @property
    def stage(self) -> str:
        return transitions.stage_of(self.status)

    @property
    def allowed_transitions(self) -> list[str]:
        return transitions.allowed_transitions(self.status)


class OrderItem(TenantScopedModel):
    """A line snapshotted at checkout; it survives product edits and deletion."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    position = models.PositiveSmallIntegerField(default=0)
    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    image_url = models.URLField(max_length=500, blank=True)
    unit_price_paise = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()
    line_total_paise = models.PositiveIntegerField()

    class Meta(TenantScopedModel.Meta):
        ordering = ("position", "created_at")

    def __str__(self) -> str:
        return f"{self.quantity} x {self.sku} on {self.order_id}"


class OrderEvent(TenantScopedModel):
    """Append-only order timeline, oldest first."""

    class Type(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status changed"
        PRICE_CHANGED = "price_changed", "Price changed"
        ADDRESS_RECEIVED = "address_received", "Address received"
        PAYMENT_LINK_CREATED = "payment_link_created", "Payment link created"
        PAYMENT_RECEIVED = "payment_received", "Payment received"
        PAYMENT_LINK_EXPIRED = "payment_link_expired", "Payment link expired"
        COD_COLLECTED = "cod_collected", "COD collected"
        REFUNDED_MANUAL = "refunded_manual", "Refunded manually"
        STOCK_RELEASED = "stock_released", "Stock released"
        NOTIFICATION_SENT = "notification_sent", "Notification sent"
        NOTIFICATION_FAILED = "notification_failed", "Notification failed"
        NOTE = "note", "Note"

    class Actor(models.TextChoices):
        BUYER = "buyer", "Buyer"
        DASHBOARD = "dashboard", "Dashboard"
        SELLER_WHATSAPP = "seller_whatsapp", "Seller on WhatsApp"
        SYSTEM = "system", "System"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=24, choices=Type.choices)
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, blank=True)
    actor = models.CharField(max_length=16, choices=Actor.choices, default=Actor.SYSTEM)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    detail = models.TextField(blank=True)
    message = models.ForeignKey(
        "inbox.Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["order", "created_at"], name="orders_event_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.type} on {self.order_id}"


class ShopperAddress(TenantScopedModel):
    """The buyer's last used delivery address, offered as the default next time."""

    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="+")
    address = models.JSONField(default=dict, blank=True)
    meta_saved_address_id = models.CharField(max_length=128, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name_plural = "shopper addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "contact"], name="orders_shopper_address_unique_contact"
            ),
        ]

    def __str__(self) -> str:
        return f"Address of {self.contact_id}"
