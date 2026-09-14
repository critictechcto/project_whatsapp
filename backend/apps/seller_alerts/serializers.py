"""Seller alerts API shapes (docs/contracts/wave-3-commerce.md). ``FooSerializer`` produces
component ``Foo``; as a request body ``AlertRecipientSerializer`` is ``AlertRecipientRequest``."""

from rest_framework import serializers

from .schema_enums import ALERT_EVENTS, ALERT_RECIPIENT_STATUSES


class AlertRecipientSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=60)
    phone_e164 = serializers.CharField(max_length=20, help_text="Create only.")
    status = serializers.ChoiceField(choices=ALERT_RECIPIENT_STATUSES, read_only=True)
    events = serializers.ListField(
        child=serializers.ChoiceField(choices=ALERT_EVENTS),
        required=False,
        help_text="Defaults to all events.",
    )
    verified_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_sent_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)

    def validate_events(self, value: list[str]) -> list[str]:
        """Unique values in contract order."""
        return [event for event in ALERT_EVENTS if event in value]


class PlatformAlertsInfoSerializer(serializers.Serializer):
    available = serializers.BooleanField(read_only=True)
    display_phone_number = serializers.CharField(read_only=True)
