import zoneinfo

from django.contrib.auth import get_user_model
from rest_framework import serializers

from common.roles import Role, role_at_least

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


class OnboardingSerializer(serializers.Serializer):
    """The caller's onboarding in the workspace of the ``X-Workspace-ID`` header."""

    goal = serializers.ChoiceField(
        choices=Workspace.Goal.choices,
        allow_blank=True,
        required=False,
        help_text='The workspace\'s first goal; "" until chosen. Admins and owners may set it.',
    )
    welcome_completed = serializers.BooleanField(required=False)
    tour_completed = serializers.BooleanField(required=False)
    checklist_dismissed = serializers.BooleanField(required=False)
    can_set_goal = serializers.BooleanField(read_only=True)

    def to_representation(self, membership: Membership) -> dict:
        return {
            "goal": membership.workspace.business_goal,
            "welcome_completed": membership.welcome_completed_at is not None,
            "tour_completed": membership.tour_completed_at is not None,
            "checklist_dismissed": membership.checklist_dismissed_at is not None,
            "can_set_goal": role_at_least(membership.role, Role.ADMIN),
        }
