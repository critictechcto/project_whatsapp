"""Billing API shapes (docs/contracts/wave-2.md). Money is integer paise (``*_paise``)."""

from rest_framework import serializers

from .schema_enums import BILLING_INTERVALS, INVOICE_STATUSES, SUBSCRIPTION_STATUSES

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
    id = serializers.CharField(read_only=True, help_text="Plan slug: starter, growth or pro.")
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


class CheckoutSerializer(serializers.Serializer):
    plan_id = serializers.CharField(max_length=32, help_text="Plan slug: starter, growth or pro.")
    interval = serializers.ChoiceField(choices=BILLING_INTERVALS)

    def validate_plan_id(self, value: str) -> str:
        if value not in PLAN_SLUGS:
            raise serializers.ValidationError(f"Unknown plan; use one of {', '.join(PLAN_SLUGS)}.")
        return value


class CheckoutPrefillSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class CheckoutSessionSerializer(serializers.Serializer):
    """Options for Razorpay Checkout in subscription mode."""

    key_id = serializers.CharField(read_only=True)
    subscription_id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    prefill = CheckoutPrefillSerializer(read_only=True)


class CheckoutVerifySerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField(max_length=64)
    razorpay_subscription_id = serializers.CharField(max_length=64)
    razorpay_signature = serializers.CharField(max_length=256)


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

    def to_internal_value(self, data):
        if hasattr(data, "get") and isinstance(data.get("gstin"), str):
            data = {**data, "gstin": data["gstin"].strip().upper()}
        return super().to_internal_value(data)

    def validate(self, attrs: dict) -> dict:
        gstin, state_code = attrs.get("gstin"), attrs.get("state_code")
        if gstin and state_code and gstin[:2] != state_code:
            raise serializers.ValidationError(
                {"state_code": ["Must match the first two digits of the GSTIN."]}
            )
        return attrs


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
    download_url = serializers.CharField(read_only=True, allow_null=True)


class UsageMetricSerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True, help_text="whatsapp_numbers, members or contacts.")
    used = serializers.IntegerField(read_only=True)
    limit = serializers.IntegerField(read_only=True, allow_null=True, help_text="null = unlimited.")


class UsageSerializer(serializers.Serializer):
    metrics = UsageMetricSerializer(many=True, read_only=True)
