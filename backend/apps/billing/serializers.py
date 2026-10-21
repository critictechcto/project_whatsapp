"""Billing API shapes (docs/contracts/wave-2.md, billing-cashfree.md). Money is integer paise
(``*_paise``)."""

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.phone import InvalidPhoneNumber, normalize_e164

from . import gst, services
from .schema_enums import (
    BILLING_INTERVALS,
    BILLING_PROVIDERS,
    CASHFREE_MODES,
    INVOICE_STATUSES,
    PAYMENT_MODES,
    SUBSCRIPTION_STATUSES,
)

PLAN_SLUGS = ("starter", "growth", "pro")
GSTIN_PATTERN = r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
STATE_CODE_PATTERN = r"^\d{2}$"
POSTAL_CODE_PATTERN = r"^\d{6}$"

# --- Plans and subscription -----------------------------------------------------------------


class PlanLimitsSerializer(serializers.Serializer):
    whatsapp_numbers = serializers.IntegerField(read_only=True, allow_null=True)
    members = serializers.IntegerField(read_only=True, allow_null=True)
    contacts = serializers.IntegerField(read_only=True, allow_null=True)


class PlanSerializer(serializers.Serializer):
    id = serializers.CharField(
        source="slug", read_only=True, help_text="Plan slug: starter, growth or pro."
    )
    name = serializers.CharField(read_only=True)
    monthly_price_paise = serializers.IntegerField(read_only=True, help_text="Before GST.")
    annual_price_paise = serializers.IntegerField(read_only=True, help_text="Before GST.")
    limits = PlanLimitsSerializer(read_only=True, help_text="null means unlimited.")
    features = serializers.ListField(child=serializers.CharField(), read_only=True)


class SubscriptionSerializer(serializers.Serializer):
    plan = PlanSerializer(read_only=True)
    status = serializers.ChoiceField(choices=SUBSCRIPTION_STATUSES, read_only=True)
    interval = serializers.ChoiceField(choices=BILLING_INTERVALS, read_only=True)
    trial_ends_at = serializers.DateTimeField(read_only=True, allow_null=True)
    current_period_start = serializers.DateTimeField(read_only=True, allow_null=True)
    current_period_end = serializers.DateTimeField(read_only=True, allow_null=True)
    cancel_at_period_end = serializers.BooleanField(read_only=True)
    provider = serializers.ChoiceField(
        choices=BILLING_PROVIDERS,
        source="provider_or_none",
        read_only=True,
        allow_null=True,
        help_text="Gateway of the paid plan; null on a trial.",
    )
    payment_mode = serializers.ChoiceField(
        choices=PAYMENT_MODES,
        read_only=True,
        allow_null=True,
        help_text=(
            "autopay (a Razorpay subscription that charges again by itself) or one_time (a "
            "prepaid period, renewed by paying again); null before a paid plan, e.g. on a trial."
        ),
    )
    auto_renews = serializers.BooleanField(
        read_only=True,
        help_text="True for an active auto-pay subscription; prepaid plans never renew.",
    )
    gst_rate_percent = serializers.SerializerMethodField(
        help_text="GST added to plan prices at checkout; 0 while UpChatz doesn't charge GST."
    )
    checkout_provider = serializers.SerializerMethodField(
        help_text="The gateway a new checkout uses."
    )

    def get_gst_rate_percent(self, obj) -> int:
        return services.gst_rate_percent()

    @extend_schema_field(serializers.ChoiceField(choices=BILLING_PROVIDERS))
    def get_checkout_provider(self, obj) -> str:
        return settings.BILLING_PROVIDER


class CheckoutSerializer(serializers.Serializer):
    plan_id = serializers.CharField(max_length=32, help_text="Plan slug: starter, growth or pro.")
    interval = serializers.ChoiceField(choices=BILLING_INTERVALS)
    payment_mode = serializers.ChoiceField(
        choices=PAYMENT_MODES,
        required=False,
        help_text=(
            "autopay (a Razorpay subscription) or one_time (one prepaid period). Defaults to "
            "autopay on Razorpay and one_time on Cashfree, which has no auto-pay."
        ),
    )

    def validate_plan_id(self, value: str) -> str:
        if value not in PLAN_SLUGS:
            raise serializers.ValidationError(f"Unknown plan; use one of {', '.join(PLAN_SLUGS)}.")
        return value


class CheckoutPrefillSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class CheckoutSessionSerializer(serializers.Serializer):
    """Options for Razorpay Checkout (an auto-pay subscription or a one-time order) or Cashfree
    Checkout (a one-time order); fields another flow doesn't use are null."""

    provider = serializers.ChoiceField(choices=BILLING_PROVIDERS, read_only=True)
    payment_mode = serializers.ChoiceField(
        choices=PAYMENT_MODES,
        read_only=True,
        help_text="autopay (Razorpay subscription) or one_time (prepaid order).",
    )
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    prefill = CheckoutPrefillSerializer(read_only=True)
    key_id = serializers.CharField(read_only=True, allow_null=True, help_text="Razorpay only.")
    subscription_id = serializers.CharField(
        read_only=True, allow_null=True, help_text="Razorpay auto-pay only."
    )
    order_id = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="One-time payments: the Razorpay order_… id or the Cashfree order id.",
    )
    payment_session_id = serializers.CharField(
        read_only=True, allow_null=True, help_text="Cashfree only."
    )
    mode = serializers.ChoiceField(
        choices=CASHFREE_MODES, read_only=True, allow_null=True, help_text="Cashfree only."
    )
    amount_paise = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="One-time payments: the amount charged (GST-inclusive when GST is on).",
    )


class CheckoutVerifySerializer(serializers.Serializer):
    """One of: ``order_id`` (Cashfree); ``razorpay_payment_id`` + ``razorpay_order_id`` +
    ``razorpay_signature`` (Razorpay one-time); ``razorpay_payment_id`` +
    ``razorpay_subscription_id`` + ``razorpay_signature`` (Razorpay auto-pay)."""

    FORMS = (
        ("order_id",),
        ("razorpay_payment_id", "razorpay_order_id", "razorpay_signature"),
        ("razorpay_payment_id", "razorpay_subscription_id", "razorpay_signature"),
    )

    order_id = serializers.CharField(max_length=64, required=False, help_text="Cashfree.")
    razorpay_payment_id = serializers.CharField(max_length=64, required=False)
    razorpay_order_id = serializers.CharField(
        max_length=64, required=False, help_text="Razorpay one-time payments."
    )
    razorpay_subscription_id = serializers.CharField(
        max_length=64, required=False, help_text="Razorpay auto-pay."
    )
    razorpay_signature = serializers.CharField(max_length=256, required=False)

    def validate(self, attrs: dict) -> dict:
        sent = {field for field, value in attrs.items() if value}
        if any(sent == set(form) for form in self.FORMS):
            return attrs
        raise serializers.ValidationError(
            "Send order_id; or razorpay_payment_id, razorpay_order_id and razorpay_signature; "
            "or razorpay_payment_id, razorpay_subscription_id and razorpay_signature."
        )


class CancelSubscriptionSerializer(serializers.Serializer):
    at_period_end = serializers.BooleanField(
        default=True, help_text="Keep access until the paid period ends."
    )


# --- Billing profile, invoices, usage -------------------------------------------------------


class BillingProfileSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=255)
    gstin = serializers.RegexField(
        GSTIN_PATTERN, allow_blank=True, help_text='15-character GSTIN, or "" if unregistered.'
    )
    email = serializers.EmailField()
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, allow_blank=True, default="")
    city = serializers.CharField(max_length=120)
    state_code = serializers.RegexField(STATE_CODE_PATTERN, help_text="2-digit GST state code.")
    postal_code = serializers.RegexField(POSTAL_CODE_PATTERN, help_text="6-digit PIN code.")
    phone = serializers.CharField(
        max_length=20,
        allow_blank=True,
        required=False,
        help_text="E.164 (a 10-digit Indian number is accepted). Needed for Cashfree checkout.",
    )

    def validate_phone(self, value: str) -> str:
        if not value.strip():
            return ""
        try:
            return normalize_e164(value, "IN")
        except InvalidPhoneNumber:
            raise serializers.ValidationError(
                "Enter a 10-digit Indian mobile number or an international number with +."
            ) from None

    def to_internal_value(self, data):
        if hasattr(data, "get") and isinstance(data.get("gstin"), str):
            data = {**data, "gstin": data["gstin"].strip().upper()}
        return super().to_internal_value(data)

    def validate_gstin(self, value: str) -> str:
        errors = gst.gstin_errors(value) if value else []
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate_state_code(self, value: str) -> str:
        if value not in gst.GST_STATE_CODES:
            raise serializers.ValidationError("Enter a valid 2-digit GST state code.")
        return value

    def validate(self, attrs: dict) -> dict:
        # On PATCH, check the GSTIN against the stored state code (and vice versa).
        gstin = attrs.get("gstin", getattr(self.instance, "gstin", ""))
        state_code = attrs.get("state_code", getattr(self.instance, "state_code", ""))
        if gstin and state_code and gstin[:2] != state_code:
            field = "state_code" if "state_code" in attrs else "gstin"
            raise serializers.ValidationError(
                {field: ["The state code must match the first two digits of the GSTIN."]}
            )
        return attrs

    def update(self, instance, validated_data: dict):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class InvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    number = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=INVOICE_STATUSES, read_only=True)
    issued_at = serializers.DateTimeField(read_only=True)
    period_start = serializers.DateTimeField(read_only=True)
    period_end = serializers.DateTimeField(read_only=True)
    subtotal_paise = serializers.IntegerField(read_only=True)
    cgst_paise = serializers.IntegerField(read_only=True)
    sgst_paise = serializers.IntegerField(read_only=True)
    igst_paise = serializers.IntegerField(read_only=True)
    total_paise = serializers.IntegerField(read_only=True)
    download_url = serializers.CharField(
        read_only=True, help_text="API path of the PDF; send the usual auth and workspace headers."
    )


class UsageMetricSerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True, help_text="whatsapp_numbers, members or contacts.")
    used = serializers.IntegerField(read_only=True)
    limit = serializers.IntegerField(read_only=True, allow_null=True, help_text="null = unlimited.")


class UsageSerializer(serializers.Serializer):
    metrics = UsageMetricSerializer(many=True, read_only=True)
