from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, viewsets
from rest_framework.response import Response

from common.roles import Role, role_at_least
from common.routers import UUID_LOOKUP_REGEX
from common.tenancy import InsufficientRole, WorkspaceScopedMixin

from . import services
from .models import Invitation, Membership, Workspace
from .serializers import (
    AcceptedInvitationSerializer,
    InvitationAcceptSerializer,
    InvitationSerializer,
    MembershipSerializer,
    WorkspaceSerializer,
)


class WorkspaceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Workspaces the caller belongs to. Addressed by id in the URL, not the header."""

    serializer_class = WorkspaceSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields = ("name",)
    ordering_fields = ("created_at",)
    action_roles = {"partial_update": Role.ADMIN, "destroy": Role.OWNER}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Workspace.objects.none()
        user = self.request.user
        my_role = Membership.objects.filter(workspace=OuterRef("pk"), user=user).values("role")[:1]
        return Workspace.objects.filter(is_active=True, memberships__user=user).annotate(
            my_role=Subquery(my_role)
        )

    def get_object(self):
        workspace = super().get_object()
        required = self.action_roles.get(self.action)
        if required and not role_at_least(workspace.my_role, required):
            raise InsufficientRole(
                f"This action requires the {Role(required).label.lower()} role or higher."
            )
        return workspace

    def perform_create(self, serializer):
        workspace = services.create_workspace(user=self.request.user, **serializer.validated_data)
        workspace.my_role = Role.OWNER
        serializer.instance = workspace

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class MemberViewSet(
    WorkspaceScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Members of the header workspace. Anyone may leave; admins manage others."""

    queryset = Membership.objects.select_related("user")
    serializer_class = MembershipSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    http_method_names = ["get", "patch", "delete", "head", "options"]
    filterset_fields = ("role",)
    search_fields = ("user__email", "user__full_name")
    ordering_fields = ("created_at",)
    action_roles = {"destroy": Role.VIEWER}

    def perform_update(self, serializer):
        serializer.instance = services.change_member_role(
            actor=self.membership,
            membership=serializer.instance,
            role=serializer.validated_data.get("role", serializer.instance.role),
        )

    def perform_destroy(self, instance):
        services.remove_member(actor=self.membership, membership=instance)


class InvitationViewSet(
    WorkspaceScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Open invitations for the header workspace. Deleting one revokes it."""

    queryset = Invitation.objects.open().select_related("invited_by")
    serializer_class = InvitationSerializer
    lookup_value_regex = UUID_LOOKUP_REGEX
    read_role = Role.ADMIN
    ordering_fields = ("created_at",)

    def perform_create(self, serializer):
        serializer.instance = services.create_invitation(
            workspace=self.workspace,
            invited_by=self.membership,
            email=serializer.validated_data["email"],
            role=serializer.validated_data.get("role", Role.AGENT),
        )

    def perform_destroy(self, instance):
        services.revoke_invitation(instance)


class AcceptInvitationView(generics.GenericAPIView):
    serializer_class = InvitationAcceptSerializer

    @extend_schema(responses={200: AcceptedInvitationSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            raw_token=serializer.validated_data["token"], user=request.user
        )
        body = AcceptedInvitationSerializer(
            {"workspace": membership.workspace, "role": membership.role}
        ).data
        return Response(body)
