from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.roles import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name", "date_joined", "email_verified_at")
        read_only_fields = ("id", "email", "date_joined", "email_verified_at")


class WorkspaceMembershipSummarySerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(source="workspace.id")
    workspace_name = serializers.CharField(source="workspace.name")
    workspace_slug = serializers.CharField(source="workspace.slug")
    role = serializers.ChoiceField(choices=Role.choices)


class MeSerializer(UserSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = (*UserSerializer.Meta.fields, "memberships")

    @extend_schema_field(WorkspaceMembershipSummarySerializer(many=True))
    def get_memberships(self, user):
        memberships = (
            user.memberships.filter(workspace__is_active=True)
            .select_related("workspace")
            .order_by("workspace__name")
        )
        return WorkspaceMembershipSummarySerializer(memberships, many=True).data


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except Exception as exc:
            messages = getattr(exc, "messages", [str(exc)])
            raise serializers.ValidationError({"password": messages}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
        )


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class RegisterResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, user=self.context["request"].user)
        return value
