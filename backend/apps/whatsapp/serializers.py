from rest_framework import serializers

from .models import PhoneNumber, WhatsAppBusinessAccount

META_ID_REGEX = r"^\d{1,64}$"


class SignupConfigSerializer(serializers.Serializer):
    app_id = serializers.CharField()
    config_id = serializers.CharField()
    graph_api_version = serializers.CharField()


class EmbeddedSignupSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=2048, trim_whitespace=True)
    waba_id = serializers.RegexField(META_ID_REGEX)
    phone_number_id = serializers.RegexField(META_ID_REGEX, required=False, allow_blank=True)
    business_id = serializers.RegexField(META_ID_REGEX, required=False, allow_blank=True)
    coexistence = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs.get("coexistence") and not attrs.get("phone_number_id"):
            raise serializers.ValidationError(
                {"phone_number_id": ["Required when onboarding a WhatsApp Business app number."]}
            )
        return attrs


class PhoneNumberSerializer(serializers.ModelSerializer):
    """Never exposes the registration PIN."""

    class Meta:
        model = PhoneNumber
        fields = (
            "id",
            "waba",
            "phone_number_id",
            "display_phone_number",
            "phone_e164",
            "verified_name",
            "name_status",
            "quality_rating",
            "messaging_limit_tier",
            "throughput_level",
            "platform_type",
            "code_verification_status",
            "meta_status",
            "registration_status",
            "is_coexistence",
            "is_default",
            "last_synced_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WhatsAppBusinessAccountSerializer(serializers.ModelSerializer):
    """Never exposes the access token."""

    phone_numbers = PhoneNumberSerializer(many=True, read_only=True)

    class Meta:
        model = WhatsAppBusinessAccount
        fields = (
            "id",
            "waba_id",
            "business_id",
            "name",
            "currency",
            "timezone_id",
            "message_template_namespace",
            "status",
            "onboarding_status",
            "last_error",
            "subscribed_at",
            "token_expires_at",
            "connected_by",
            "phone_numbers",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
