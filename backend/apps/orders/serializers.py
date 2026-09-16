"""Orders and store API shapes (docs/contracts/wave-3-commerce.md). ``FooSerializer`` produces
component ``Foo``."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inbox.models import Message
from apps.inbox.serializers import (
    ConversationContactSerializer,
    ConversationPhoneNumberSerializer,
    UserSummarySerializer,
)
from apps.payments.schema_enums import PAYMENT_LINK_STATUSES

from . import services
from .schema_enums import (
    ORDER_EVENT_ACTORS,
    ORDER_EVENT_TYPES,
    ORDER_SOURCES,
    ORDER_STATUSES,
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    SHOP_MODES,
    TRANSITION_TARGETS,
)

MAX_MENU_KEYWORDS = 20
MAX_PINCODES = 5000

# --- Orders ---------------------------------------------------------------------------------


class OrderAddressSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    phone_e164 = serializers.CharField(max_length=16)
    line1 = serializers.CharField(max_length=200)
    line2 = serializers.CharField(max_length=200, allow_blank=True, default="")
    landmark = serializers.CharField(max_length=200, allow_blank=True, default="")
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    pincode = serializers.RegexField(r"^[0-9]{6}$", help_text="6 digits.")
    country = serializers.CharField(max_length=2, default="IN")


class OrderItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = serializers.UUIDField(
        read_only=True, allow_null=True, help_text="Null once the product is deleted."
    )
    sku = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    image_url = serializers.URLField(read_only=True, allow_null=True)
    unit_price_paise = serializers.IntegerField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    line_total_paise = serializers.IntegerField(read_only=True)

    def to_representation(self, instance) -> dict:
        data = super().to_representation(instance)
        data["image_url"] = data["image_url"] or None
        return data


class OrderPaymentLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    short_url = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=PAYMENT_LINK_STATUSES, read_only=True)
    amount_paise = serializers.IntegerField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True, allow_null=True)
    paid_at = serializers.DateTimeField(read_only=True, allow_null=True)


class OrderListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    number = serializers.CharField(read_only=True, help_text="e.g. SS-1001")
    status = serializers.ChoiceField(choices=ORDER_STATUSES, read_only=True)
    payment_status = serializers.ChoiceField(choices=PAYMENT_STATUSES, read_only=True)
    payment_method = serializers.ChoiceField(
        choices=PAYMENT_METHODS, read_only=True, allow_null=True
    )
    source = serializers.ChoiceField(choices=ORDER_SOURCES, read_only=True)
    contact = ConversationContactSerializer(read_only=True)
    total_paise = serializers.IntegerField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance) -> dict:
        data = super().to_representation(instance)
        data["payment_method"] = data["payment_method"] or None
        return data


class OrderSerializer(OrderListItemSerializer):
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)
    phone_number = ConversationPhoneNumberSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal_paise = serializers.IntegerField(read_only=True)
    shipping_paise = serializers.IntegerField(read_only=True)
    cod_fee_paise = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True)
    address = OrderAddressSerializer(read_only=True, allow_null=True)
    courier_name = serializers.CharField(read_only=True)
    awb_number = serializers.CharField(read_only=True)
    tracking_url = serializers.CharField(read_only=True)
    payment_link = serializers.SerializerMethodField()
    notes = serializers.CharField(read_only=True, help_text="Seller-internal.")
    cancel_reason = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(
        read_only=True, allow_null=True, help_text="Checkout deadline."
    )
    confirmed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    packed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    shipped_at = serializers.DateTimeField(read_only=True, allow_null=True)
    delivered_at = serializers.DateTimeField(read_only=True, allow_null=True)
    cancelled_at = serializers.DateTimeField(read_only=True, allow_null=True)
    allowed_transitions = serializers.ListField(
        child=serializers.ChoiceField(choices=ORDER_STATUSES), read_only=True
    )

    @extend_schema_field(OrderPaymentLinkSerializer(allow_null=True))
    def get_payment_link(self, order) -> dict | None:
        links = sorted(order.payment_links.all(), key=lambda link: (link.created_at, str(link.pk)))
        return OrderPaymentLinkSerializer(links[-1]).data if links else None


class OrderEventSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    type = serializers.ChoiceField(choices=ORDER_EVENT_TYPES, read_only=True)
    from_status = serializers.CharField(read_only=True, help_text='"" when not a status change.')
    to_status = serializers.CharField(read_only=True, help_text='"" when not a status change.')
    actor = serializers.ChoiceField(choices=ORDER_EVENT_ACTORS, read_only=True)
    user = UserSummarySerializer(read_only=True, allow_null=True)
    detail = serializers.CharField(read_only=True)
    message_id = serializers.UUIDField(read_only=True, allow_null=True)
    message_status = serializers.SerializerMethodField(
        help_text="Current delivery status of the event's message; null without a message."
    )
    message_error_code = serializers.SerializerMethodField(
        help_text='Meta error code when that message failed, else "".'
    )
    created_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(serializers.ChoiceField(choices=Message.Status.values, allow_null=True))
    def get_message_status(self, event) -> str | None:
        return event.message.status if event.message_id and event.message else None

    @extend_schema_field(serializers.CharField())
    def get_message_error_code(self, event) -> str:
        message = event.message if event.message_id else None
        if message is None or message.status != Message.Status.FAILED:
            return ""
        return message.error_code or ""


class OrderTransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(
        choices=TRANSITION_TARGETS, help_text="confirmed only from needs_attention."
    )
    courier_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    awb_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    tracking_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    # No ``default=``: openapi-typescript types fields with a default as required. The view applies
    # the defaults (``REQUEST_DEFAULTS``).
    notify_buyer = serializers.BooleanField(required=False, help_text="Default true.")

    def validate_tracking_url(self, value: str) -> str:
        if value and not value.lower().startswith("https://"):
            raise serializers.ValidationError("Use an https:// link.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs.get("to_status") == "shipped":
            errors = {
                field: ["Required when marking an order shipped."]
                for field in ("courier_name", "awb_number")
                if not (attrs.get(field) or "").strip()
            }
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text='Default "".'
    )
    restock = serializers.BooleanField(required=False, help_text="Default true.")
    notify_buyer = serializers.BooleanField(required=False, help_text="Default true.")


# Values for the optional order action fields when a request leaves them out.
REQUEST_DEFAULTS = {"notify_buyer": True, "restock": True, "reason": ""}


def with_request_defaults(validated_data: dict) -> dict:
    return {**REQUEST_DEFAULTS, **validated_data}


class OrderNotesSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=2000, allow_blank=True)


class OrderSummarySerializer(serializers.Serializer):
    today_count = serializers.IntegerField(read_only=True)
    today_revenue_paise = serializers.IntegerField(read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    needs_attention_count = serializers.IntegerField(read_only=True)
    awaiting_payment_count = serializers.IntegerField(read_only=True)


# --- Store ----------------------------------------------------------------------------------


class OrderNotificationTemplatesSerializer(serializers.Serializer):
    confirmed = serializers.UUIDField(allow_null=True, required=False)
    packed = serializers.UUIDField(allow_null=True, required=False)
    shipped = serializers.UUIDField(allow_null=True, required=False)
    delivered = serializers.UUIDField(allow_null=True, required=False)
    cancelled = serializers.UUIDField(allow_null=True, required=False)
    payment_reminder = serializers.UUIDField(allow_null=True, required=False)


class StoreSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    shop_mode = serializers.ChoiceField(choices=SHOP_MODES, required=False)
    store_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    welcome_message = serializers.CharField(max_length=1024, required=False, allow_blank=True)
    menu_keywords = serializers.ListField(
        child=serializers.CharField(max_length=30),
        max_length=MAX_MENU_KEYWORDS,
        required=False,
        help_text="Case-insensitive exact matches that open the store menu.",
    )
    order_prefix = serializers.RegexField(r"^[A-Z]{2,5}$", required=False)
    min_order_paise = serializers.IntegerField(min_value=0, required=False)
    shipping_fee_paise = serializers.IntegerField(min_value=0, required=False)
    free_shipping_above_paise = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )
    cod_enabled = serializers.BooleanField(required=False)
    cod_fee_paise = serializers.IntegerField(min_value=0, required=False)
    cod_max_order_paise = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    serviceable_pincodes = serializers.ListField(
        child=serializers.RegexField(r"^[0-9]{6}$"),
        max_length=MAX_PINCODES,
        required=False,
        help_text="Empty means everywhere.",
    )
    support_message = serializers.CharField(max_length=1024, required=False, allow_blank=True)
    powered_by_footer = serializers.BooleanField(required=False)
    phone_number_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="Null uses the workspace default number."
    )
    store_link = serializers.SerializerMethodField()
    notification_templates = OrderNotificationTemplatesSerializer(required=False)
    updated_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(serializers.URLField(allow_null=True, read_only=True))
    def get_store_link(self, store_settings) -> str | None:
        return services.store_link(store_settings)


class StoreChecklistItemSerializer(serializers.Serializer):
    key = serializers.CharField(
        read_only=True,
        help_text=(
            "whatsapp_connected, products_added, payments_configured, order_templates_ready, "
            "alert_number_verified or store_enabled"
        ),
    )
    done = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True)


class StoreChecklistSerializer(serializers.Serializer):
    items = StoreChecklistItemSerializer(many=True, read_only=True)


class StarterTemplatesResultSerializer(serializers.Serializer):
    created = serializers.ListField(child=serializers.CharField(), read_only=True)
    existing = serializers.ListField(child=serializers.CharField(), read_only=True)
