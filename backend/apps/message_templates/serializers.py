from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.whatsapp.models import WhatsAppBusinessAccount

from .models import MessageTemplate


@extend_schema_field(
    {
        "type": "array",
        "items": {"type": "object", "additionalProperties": True},
        "description": "Template components in Meta's format (HEADER, BODY, FOOTER, BUTTONS).",
    }
)
class ComponentsField(serializers.JSONField):
    pass


class MessageTemplateSerializer(serializers.ModelSerializer):
    waba = serializers.PrimaryKeyRelatedField(queryset=WhatsAppBusinessAccount.objects.none())
    components = ComponentsField()

    class Meta:
        model = MessageTemplate
        fields = (
            "id",
            "waba",
            "meta_template_id",
            "name",
            "language",
            "category",
            "previous_category",
            "status",
            "rejected_reason",
            "quality_score",
            "components",
            "submitted_at",
            "last_synced_at",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "meta_template_id",
            "previous_category",
            "status",
            "rejected_reason",
            "quality_score",
            "submitted_at",
            "last_synced_at",
            "created_by",
            "created_at",
            "updated_at",
        )
        # Uniqueness and Meta's rules are checked in services with clearer messages.
        validators = []

    def get_fields(self):
        fields = super().get_fields()
        workspace = self.context.get("workspace")
        if workspace is not None:
            fields["waba"].queryset = WhatsAppBusinessAccount.objects.filter(workspace=workspace)
        return fields


class PreviewRequestSerializer(serializers.Serializer):
    variables = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False, default=list
    )
    header_variables = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False, default=list
    )


class PreviewHeaderSerializer(serializers.Serializer):
    format = serializers.CharField()
    text = serializers.CharField(allow_null=True)


class PreviewButtonSerializer(serializers.Serializer):
    type = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    url = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False)


class PreviewSerializer(serializers.Serializer):
    header = PreviewHeaderSerializer(allow_null=True)
    body = serializers.CharField(allow_blank=True)
    footer = serializers.CharField(allow_null=True)
    buttons = PreviewButtonSerializer(many=True)


class SyncRequestSerializer(serializers.Serializer):
    waba_id = serializers.CharField(
        required=False,
        help_text="Our WABA id (UUID) or Meta's WABA id. Omit to sync every active account.",
    )


class SyncQueuedSerializer(serializers.Serializer):
    queued = serializers.ListField(child=serializers.UUIDField())
