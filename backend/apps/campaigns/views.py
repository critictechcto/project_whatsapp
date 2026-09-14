"""Campaign API. Endpoint bodies are stubs (501); roles and request validation are enforced."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions
from rest_framework.decorators import action

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from .schema_enums import CAMPAIGN_STATUSES, RECIPIENT_STATUSES
from .serializers import (
    AudiencePreviewSerializer,
    CampaignRecipientSerializer,
    CampaignSerializer,
    CampaignWriteSerializer,
    LaunchCampaignSerializer,
)


class StubNotImplemented(exceptions.APIException):
    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class CampaignViewSet(WorkspaceScopedGenericViewSet):
    """Bulk template sends to an audience of opted-in contacts."""

    serializer_class = CampaignSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN
    action_roles = {"audience_preview": Role.VIEWER}

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(
        operation_id="campaigns_list",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=CAMPAIGN_STATUSES)],
        responses=CampaignSerializer(many=True),
    )
    def list(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_create",
        request=CampaignWriteSerializer,
        responses={201: CampaignSerializer},
        description="Create a draft campaign.",
    )
    def create(self, request):
        self.validated(CampaignWriteSerializer)
        raise StubNotImplemented()

    @extend_schema(operation_id="campaigns_retrieve", responses=CampaignSerializer)
    def retrieve(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_partial_update",
        request=CampaignWriteSerializer,
        responses=CampaignSerializer,
        description="Only draft and scheduled campaigns can change (409 campaign_not_editable).",
    )
    def partial_update(self, request, pk=None):
        self.validated(CampaignWriteSerializer, partial=True)
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_destroy",
        responses={204: None},
        description="Only drafts can be deleted.",
    )
    def destroy(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_audience_preview_create",
        request=None,
        responses=AudiencePreviewSerializer,
        description="Count who would receive the campaign and who would be skipped.",
    )
    @action(detail=True, methods=["post"], url_path="audience-preview")
    def audience_preview(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_launch_create",
        request=LaunchCampaignSerializer,
        responses=CampaignSerializer,
        description="Schedule or start sending. The template must be approved by Meta.",
    )
    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        self.validated(LaunchCampaignSerializer)
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_pause_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_resume_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_cancel_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="campaigns_recipients_list",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=RECIPIENT_STATUSES)],
        responses=CampaignRecipientSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        raise StubNotImplemented()
