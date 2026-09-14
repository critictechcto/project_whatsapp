"""Seller alerts API (docs/contracts/wave-3-commerce.md, "Seller alerts")."""

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import services
from .models import AlertRecipient
from .platform import platform_alerts_available
from .serializers import AlertRecipientSerializer, PlatformAlertsInfoSerializer


class PlatformAlertsViewSet(WorkspaceScopedGenericViewSet):
    serializer_class = PlatformAlertsInfoSerializer
    filter_backends: list = []
    read_role = Role.VIEWER

    @extend_schema(
        operation_id="seller_alerts_platform_retrieve", responses=PlatformAlertsInfoSerializer
    )
    def retrieve(self, request):
        available = platform_alerts_available()
        data = {
            "available": available,
            "display_phone_number": settings.PLATFORM_WA_DISPLAY_PHONE_NUMBER if available else "",
        }
        return Response(PlatformAlertsInfoSerializer(data).data)


class AlertRecipientViewSet(WorkspaceScopedGenericViewSet):
    """Personal WhatsApp numbers that get order alerts from the UpChatz number (at most 3)."""

    queryset = AlertRecipient.objects.all()
    serializer_class = AlertRecipientSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    @extend_schema(
        operation_id="seller_alerts_recipients_list",
        responses=AlertRecipientSerializer(many=True),
    )
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(AlertRecipientSerializer(page, many=True).data)

    @extend_schema(
        operation_id="seller_alerts_recipients_create",
        request=AlertRecipientSerializer,
        responses={
            status.HTTP_201_CREATED: AlertRecipientSerializer,
            status.HTTP_409_CONFLICT: OpenApiResponse(
                description="platform_alerts_unavailable, alert_recipient_limit"
            ),
        },
        description=(
            "Sends the verification template from the UpChatz number (409 "
            "platform_alerts_unavailable, alert_recipient_limit). A number WhatsApp can't reach "
            "is a 400 on phone_e164."
        ),
    )
    def create(self, request):
        services.ensure_platform_available()
        serializer = AlertRecipientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        recipient = services.create_recipient(
            self.workspace,
            name=data["name"],
            phone_e164=data["phone_e164"],
            events=data.get("events"),
        )
        return Response(AlertRecipientSerializer(recipient).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="seller_alerts_recipients_partial_update",
        request=AlertRecipientSerializer,
        responses=AlertRecipientSerializer,
        description="phone_e164 can't change after create.",
    )
    def partial_update(self, request, pk=None):
        recipient = self.get_object()
        serializer = AlertRecipientSerializer(recipient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if (
            "phone_e164" in data
            and services.normalize_recipient_phone(data["phone_e164"]) != recipient.phone_e164
        ):
            raise ValidationError(
                {
                    "phone_e164": [
                        "The number can't be changed. Remove it and add the new number instead."
                    ]
                }
            )
        recipient = services.update_recipient(
            recipient, name=data.get("name"), events=data.get("events")
        )
        return Response(AlertRecipientSerializer(recipient).data)

    @extend_schema(operation_id="seller_alerts_recipients_destroy", responses={204: None})
    def destroy(self, request, pk=None):
        services.delete_recipient(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="seller_alerts_recipients_resend_verification_create",
        request=None,
        responses=AlertRecipientSerializer,
        description="409 verification_recently_sent within 5 minutes of the last one.",
    )
    @action(detail=True, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request, pk=None):
        recipient = services.resend_verification(self.get_object())
        return Response(AlertRecipientSerializer(recipient).data)
