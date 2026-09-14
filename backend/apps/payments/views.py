"""Payments API and the per-seller Razorpay webhook (docs/contracts/wave-3-commerce.md).

The account view and the link list are implemented. Account changes, verification, webhook
rotation and webhook processing are contract stubs answering 501 ``not_implemented``.
"""

import logging
import uuid

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import services
from .exceptions import EndpointNotImplemented
from .models import PaymentAccount, PaymentLink
from .schema_enums import PAYMENT_LINK_STATUSES
from .serializers import PaymentAccountSerializer, PaymentLinkSerializer

logger = logging.getLogger(__name__)


class PaymentAccountViewSet(WorkspaceScopedGenericViewSet):
    """The workspace's own Razorpay account. Secrets are never returned."""

    queryset = PaymentAccount.objects.all()
    serializer_class = PaymentAccountSerializer
    filter_backends: list = []
    read_role = Role.ADMIN
    write_role = Role.ADMIN
    action_roles = {"destroy": Role.OWNER}

    @extend_schema(operation_id="payments_account_retrieve", responses=PaymentAccountSerializer)
    def retrieve(self, request):
        account = services.get_account(self.workspace) or PaymentAccount(workspace=self.workspace)
        return Response(PaymentAccountSerializer(account).data)

    @extend_schema(
        operation_id="payments_account_partial_update",
        request=PaymentAccountSerializer,
        responses=PaymentAccountSerializer,
        description="Changing a key resets status to unverified.",
    )
    def partial_update(self, request):
        raise EndpointNotImplemented()

    @extend_schema(operation_id="payments_account_destroy", responses={204: None})
    def destroy(self, request):
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="payments_account_verify_create",
        request=None,
        responses=PaymentAccountSerializer,
        description="409 payment_account_missing or payment_account_invalid.",
    )
    def verify(self, request):
        raise EndpointNotImplemented()

    @extend_schema(
        operation_id="payments_account_rotate_webhook_create",
        request=None,
        responses=PaymentAccountSerializer,
        description="Issue a new webhook URL; update it in Razorpay afterwards.",
    )
    def rotate_webhook(self, request):
        raise EndpointNotImplemented()


class PaymentLinkViewSet(WorkspaceScopedGenericViewSet):
    queryset = PaymentLink.objects.all()
    serializer_class = PaymentLinkSerializer
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    @extend_schema(
        operation_id="payments_links_list",
        parameters=[
            OpenApiParameter("order", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR, enum=PAYMENT_LINK_STATUSES),
        ],
        responses=PaymentLinkSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        if order := request.query_params.get("order"):
            try:
                queryset = queryset.filter(order_id=uuid.UUID(order))
            except ValueError:
                raise serializers.ValidationError({"order": ["Must be a valid UUID."]}) from None
        if status := request.query_params.get("status"):
            if status not in PAYMENT_LINK_STATUSES:
                raise serializers.ValidationError(
                    {"status": [f"Use one of: {', '.join(PAYMENT_LINK_STATUSES)}."]}
                )
            queryset = queryset.filter(status=status)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentLinkSerializer(page, many=True).data)


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": None}}, status=status
    )


@csrf_exempt
@require_POST
def merchant_webhook(request: HttpRequest, token: str) -> JsonResponse:
    """``POST /webhooks/razorpay/merchants/<token>/`` (public, not in the OpenAPI schema).

    404 for an unknown token. Signature checks and event handling are not built yet.
    """
    if not PaymentAccount.objects.filter(webhook_token=token).exists():
        return _error("not_found", "Not found.", 404)
    logger.info("Merchant Razorpay webhook received before webhook handling is implemented")
    return _error("not_implemented", str(EndpointNotImplemented.default_detail), 501)
