"""Seller alerts API (docs/contracts/wave-3-commerce.md, "Seller alerts").

The platform info and the recipient list are implemented. Adding, changing, removing and
re-verifying recipients are contract stubs answering 501 ``not_implemented``.
"""

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from .exceptions import EndpointNotImplemented
from .models import AlertRecipient
from .serializers import AlertRecipientSerializer, PlatformAlertsInfoSerializer


def platform_alerts_available() -> bool:
    return bool(settings.PLATFORM_WA_PHONE_NUMBER_ID and settings.PLATFORM_WA_ACCESS_TOKEN)


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
        responses={status.HTTP_201_CREATED: AlertRecipientSerializer},
        description=(
            "Sends the verification template from the UpChatz number (409 "
            "platform_alerts_unavailable, alert_recipient_limit)."
        ),
    )
    def create(self, request):
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="seller_alerts_recipients_partial_update",
        request=AlertRecipientSerializer,
        responses=AlertRecipientSerializer,
        description="phone_e164 can't change after create.",
    )
    def partial_update(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(operation_id="seller_alerts_recipients_destroy", responses={204: None})
    def destroy(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="seller_alerts_recipients_resend_verification_create",
        request=None,
        responses=AlertRecipientSerializer,
        description="409 verification_recently_sent within 5 minutes of the last one.",
    )
    @action(detail=True, methods=["post"], url_path="resend-verification")
    def resend_verification(self, request, pk=None):
        self.get_object()
        raise EndpointNotImplemented()
