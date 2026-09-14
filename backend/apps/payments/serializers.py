"""Payments API shapes (docs/contracts/wave-3-commerce.md). ``FooSerializer`` produces ``Foo``.

Secrets are write-only: responses expose only ``has_key_secret``/``has_webhook_secret``.
"""

from rest_framework import serializers

from . import services
from .models import WEBHOOK_EVENTS
from .schema_enums import (
    PAYMENT_ACCOUNT_STATUSES,
    PAYMENT_LINK_STATUSES,
    PAYMENT_MODES,
    PAYMENT_PROVIDERS,
)


class PaymentAccountSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=PAYMENT_PROVIDERS, read_only=True)
    mode = serializers.ChoiceField(
        choices=PAYMENT_MODES,
        read_only=True,
        allow_null=True,
        help_text="From the rzp_test_/rzp_live_ key prefix; null until key_id is set.",
    )
    key_id = serializers.RegexField(
        r"^rzp_(test|live)_[A-Za-z0-9]{1,50}$", max_length=64, required=False, allow_blank=True
    )
    key_secret = serializers.CharField(
        max_length=128, write_only=True, required=False, style={"input_type": "password"}
    )
    webhook_secret = serializers.CharField(
        max_length=128, write_only=True, required=False, style={"input_type": "password"}
    )
    has_key_secret = serializers.BooleanField(read_only=True)
    has_webhook_secret = serializers.BooleanField(read_only=True)
    status = serializers.ChoiceField(choices=PAYMENT_ACCOUNT_STATUSES, read_only=True)
    verified_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_error = serializers.CharField(read_only=True)
    webhook_url = serializers.SerializerMethodField(
        help_text='Enter this URL in Razorpay webhooks ("" until the account is saved).'
    )
    webhook_events = serializers.SerializerMethodField()
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)

    def get_webhook_url(self, account) -> str:
        return services.webhook_url(account)

    def get_webhook_events(self, account) -> list[str]:
        return list(WEBHOOK_EVENTS)


class PaymentLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    order_id = serializers.UUIDField(read_only=True)
    provider = serializers.ChoiceField(choices=PAYMENT_PROVIDERS, read_only=True)
    provider_link_id = serializers.CharField(read_only=True)
    reference_id = serializers.CharField(read_only=True)
    short_url = serializers.CharField(read_only=True)
    amount_paise = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(choices=PAYMENT_LINK_STATUSES, read_only=True)
    expires_at = serializers.DateTimeField(read_only=True, allow_null=True)
    paid_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
