"""Campaign API shapes (docs/contracts/wave-2.md). ``FooSerializer`` produces component ``Foo``."""

from rest_framework import serializers

from apps.inbox.serializers import (
    ConversationContactSerializer,
    ConversationPhoneNumberSerializer,
    UserSummarySerializer,
)
from apps.message_templates.models import MessageTemplate

from .schema_enums import (
    AUDIENCE_MATCHES,
    CAMPAIGN_STATUSES,
    RECIPIENT_STATUSES,
    VARIABLE_SOURCE_TYPES,
)

CONTACT_FIELDS = ("name", "phone_e164", "email")
MAX_AUDIENCE_IDS = 5000

# --- Variables and audience -----------------------------------------------------------------


class VariableSourceSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=VARIABLE_SOURCE_TYPES)
    value = serializers.CharField(
        max_length=1024,
        help_text="Contact field (name, phone_e164, email), attribute key, or static text.",
    )
    fallback = serializers.CharField(
        max_length=1024, allow_blank=True, default="", help_text="Used when the value is empty."
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["source"] == "contact_field" and attrs["value"] not in CONTACT_FIELDS:
            raise serializers.ValidationError(
                {"value": [f"Use one of the contact fields: {', '.join(CONTACT_FIELDS)}."]}
            )
        return attrs


class VariableMappingSerializer(serializers.Serializer):
    body = VariableSourceSerializer(many=True, required=False, default=list)
    header = VariableSourceSerializer(required=False, allow_null=True, default=None)
    buttons = serializers.DictField(
        child=VariableSourceSerializer(),
        required=False,
        default=dict,
        help_text="Button variables keyed by button index ('0', '1', ...).",
    )

    def validate_buttons(self, value: dict) -> dict:
        if any(not str(key).isdigit() for key in value):
            raise serializers.ValidationError("Keys must be button indexes such as '0'.")
        return value


class CampaignAudienceSerializer(serializers.Serializer):
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=MAX_AUDIENCE_IDS
    )
    match = serializers.ChoiceField(
        choices=AUDIENCE_MATCHES,
        default="any",
        help_text="Contacts with any of the tags, or all of them.",
    )
    contact_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=MAX_AUDIENCE_IDS
    )


# --- Campaigns ------------------------------------------------------------------------------


class CampaignStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField(read_only=True)
    skipped = serializers.IntegerField(read_only=True)
    queued = serializers.IntegerField(read_only=True)
    sent = serializers.IntegerField(read_only=True)
    delivered = serializers.IntegerField(read_only=True)
    read = serializers.IntegerField(read_only=True)
    failed = serializers.IntegerField(read_only=True)
    replied = serializers.IntegerField(read_only=True)


class CostEstimateSerializer(serializers.Serializer):
    currency = serializers.CharField(read_only=True, help_text="Always INR.")
    amount = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)
    note = serializers.CharField(read_only=True)


class CampaignTemplateSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    language = serializers.CharField(read_only=True)
    category = serializers.ChoiceField(choices=MessageTemplate.Category.choices, read_only=True)


class CampaignSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=CAMPAIGN_STATUSES, read_only=True)
    template = CampaignTemplateSerializer(read_only=True)
    phone_number = ConversationPhoneNumberSerializer(read_only=True)
    audience = CampaignAudienceSerializer(read_only=True)
    variable_mapping = VariableMappingSerializer(read_only=True)
    scheduled_at = serializers.DateTimeField(read_only=True, allow_null=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    consent_attested = serializers.BooleanField(read_only=True)
    stats = CampaignStatsSerializer(read_only=True)
    estimated_cost = CostEstimateSerializer(read_only=True, allow_null=True)
    last_error = serializers.CharField(read_only=True)
    created_by = UserSummarySerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CampaignWriteSerializer(serializers.Serializer):
    """Create (always a draft) or PATCH a draft/scheduled campaign."""

    name = serializers.CharField(max_length=255)
    template_id = serializers.UUIDField()
    phone_number_id = serializers.UUIDField(
        required=False, allow_null=True, help_text="Workspace default number when omitted."
    )
    audience = CampaignAudienceSerializer()
    variable_mapping = VariableMappingSerializer()
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class AudienceSkippedSerializer(serializers.Serializer):
    opted_out = serializers.IntegerField(read_only=True)
    not_opted_in = serializers.IntegerField(read_only=True)
    invalid = serializers.IntegerField(read_only=True)


class AudiencePreviewSerializer(serializers.Serializer):
    total = serializers.IntegerField(read_only=True)
    eligible = serializers.IntegerField(read_only=True)
    skipped = AudienceSkippedSerializer(read_only=True)


class LaunchCampaignSerializer(serializers.Serializer):
    consent_attested = serializers.BooleanField(
        help_text="Confirms every recipient agreed to receive these messages. Must be true."
    )
    scheduled_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="Null or omitted sends now."
    )

    def validate_consent_attested(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Confirm the recipients opted in before launching.")
        return value


class CampaignRecipientSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    contact = ConversationContactSerializer(read_only=True)
    status = serializers.ChoiceField(choices=RECIPIENT_STATUSES, read_only=True)
    skip_reason = serializers.CharField(read_only=True)
    error_code = serializers.CharField(read_only=True)
    message_id = serializers.UUIDField(read_only=True, allow_null=True)
    updated_at = serializers.DateTimeField(read_only=True)
