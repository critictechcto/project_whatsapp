import zoneinfo

from django.contrib.auth import get_user_model
from rest_framework import serializers

from common.roles import Role

from .models import Invitation, Membership, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    my_role = serializers.ChoiceField(choices=Role.choices, read_only=True)

    class Meta:
        model = Workspace
        fields = ("id", "name", "slug", "time_zone", "my_role", "created_at")
        read_only_fields = ("id", "slug", "created_at")

    def validate_time_zone(self, value: str) -> str:
        if value not in zoneinfo.available_timezones():
            raise serializers.ValidationError("Unknown time zone.")
        return value


class WorkspaceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ("id", "name", "slug")


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "email", "full_name")


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user", "role", "created_at")
        read_only_fields = ("id", "user", "created_at")


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Invitation.Status.choices, read_only=True)
    invited_by = MemberUserSerializer(read_only=True)

    class Meta:
        model = Invitation
        fields = ("id", "email", "role", "status", "invited_by", "expires_at", "created_at")
        read_only_fields = ("id", "status", "invited_by", "expires_at", "created_at")


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()


class AcceptedInvitationSerializer(serializers.Serializer):
    workspace = WorkspaceSummarySerializer()
    role = serializers.ChoiceField(choices=Role.choices)
