"""Campaign API (docs/contracts/wave-2.md)."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import services
from .models import Campaign, CampaignRecipient
from .schema_enums import CAMPAIGN_STATUSES, RECIPIENT_STATUSES
from .serializers import (
    AudiencePreviewSerializer,
    CampaignRecipientSerializer,
    CampaignSerializer,
    CampaignWriteSerializer,
    LaunchCampaignSerializer,
)


def _status_filter(request, allowed) -> str | None:
    value = request.query_params.get("status")
    if value in (None, ""):
        return None
    if value not in allowed:
        raise ValidationError({"status": [f"Use one of: {', '.join(allowed)}."]})
    return value


class CampaignViewSet(WorkspaceScopedGenericViewSet):
    """Bulk template sends to an audience of opted-in contacts."""

    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN
    action_roles = {"audience_preview": Role.VIEWER}

    def get_queryset(self):
        return super().get_queryset().select_related("template", "phone_number", "created_by")

    def validated(self, serializer_class, data=None, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data if data is None else data,
            context=self.get_serializer_context(),
            **kwargs,
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def respond(self, campaign: Campaign, status: int = http_status.HTTP_200_OK) -> Response:
        fresh = self.get_queryset().get(pk=campaign.pk)
        return Response(CampaignSerializer(fresh).data, status=status)

    @extend_schema(
        operation_id="campaigns_list",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=CAMPAIGN_STATUSES)],
        responses=CampaignSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        if status := _status_filter(request, CAMPAIGN_STATUSES):
            queryset = queryset.filter(status=status)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CampaignSerializer(page, many=True).data)

    @extend_schema(
        operation_id="campaigns_create",
        request=CampaignWriteSerializer,
        responses={201: CampaignSerializer},
        description="Create a draft campaign.",
    )
    def create(self, request):
        data = self.validated(CampaignWriteSerializer)
        campaign = services.create_campaign(self.workspace, data, actor=request.user)
        return self.respond(campaign, http_status.HTTP_201_CREATED)

    @extend_schema(operation_id="campaigns_retrieve", responses=CampaignSerializer)
    def retrieve(self, request, pk=None):
        return Response(CampaignSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="campaigns_partial_update",
        request=CampaignWriteSerializer,
        responses=CampaignSerializer,
        description="Only draft and scheduled campaigns can change (409 campaign_not_editable).",
    )
    def partial_update(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in Campaign.EDITABLE_STATUSES:
            raise services.CampaignNotEditable()
        body = request.data.dict() if hasattr(request.data, "dict") else request.data
        if not isinstance(body, dict):
            raise ValidationError({"non_field_errors": ["Send a JSON object."]})
        # Nested objects (audience, variable_mapping) are replaced as a whole.
        merged = {**services.write_representation(campaign), **body}
        data = self.validated(CampaignWriteSerializer, data=merged)
        campaign = services.update_campaign(campaign, data, changed=set(body))
        return self.respond(campaign)

    @extend_schema(
        operation_id="campaigns_destroy",
        responses={204: None},
        description="Only drafts can be deleted.",
    )
    def destroy(self, request, pk=None):
        services.delete_campaign(self.get_object())
        return Response(status=http_status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="campaigns_audience_preview_create",
        request=None,
        responses=AudiencePreviewSerializer,
        description="Count who would receive the campaign and who would be skipped.",
    )
    @action(detail=True, methods=["post"], url_path="audience-preview")
    def audience_preview(self, request, pk=None):
        preview = services.audience_preview(self.get_object())
        return Response(AudiencePreviewSerializer(preview).data)

    @extend_schema(
        operation_id="campaigns_launch_create",
        request=LaunchCampaignSerializer,
        responses=CampaignSerializer,
        description="Schedule or start sending. The template must be approved by Meta.",
    )
    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        campaign = self.get_object()
        data = self.validated(LaunchCampaignSerializer)
        scheduled_at = data.get("scheduled_at", services.UNSET)
        campaign = services.launch(campaign, actor=request.user, scheduled_at=scheduled_at)
        return self.respond(campaign)

    @extend_schema(
        operation_id="campaigns_pause_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self.respond(services.pause(self.get_object()))

    @extend_schema(
        operation_id="campaigns_resume_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self.respond(services.resume(self.get_object()))

    @extend_schema(
        operation_id="campaigns_cancel_create", request=None, responses=CampaignSerializer
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.respond(services.cancel(self.get_object()))

    @extend_schema(
        operation_id="campaigns_recipients_list",
        parameters=[OpenApiParameter("status", OpenApiTypes.STR, enum=RECIPIENT_STATUSES)],
        responses=CampaignRecipientSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        campaign = self.get_object()
        queryset = CampaignRecipient.objects.filter(
            workspace=self.workspace, campaign=campaign
        ).select_related("contact")
        if status := _status_filter(request, RECIPIENT_STATUSES):
            queryset = queryset.filter(status=status)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CampaignRecipientSerializer(page, many=True).data)
