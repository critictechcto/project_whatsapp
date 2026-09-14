"""Billing API and the Razorpay webhook."""

import hashlib
import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import entitlements, razorpay, services, webhooks
from .models import Invoice, Plan
from .serializers import (
    BillingProfileSerializer,
    CancelSubscriptionSerializer,
    CheckoutSerializer,
    CheckoutSessionSerializer,
    CheckoutVerifySerializer,
    InvoiceSerializer,
    PlanSerializer,
    SubscriptionSerializer,
    UsageSerializer,
)

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"
EVENT_ID_MAX_LENGTH = 100


class BillingViewSet(WorkspaceScopedGenericViewSet):
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.OWNER

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class PlanViewSet(BillingViewSet):
    """Plans a workspace can subscribe to (prices before GST)."""

    serializer_class = PlanSerializer
    pagination_class = None

    @extend_schema(operation_id="billing_plans_list", responses=PlanSerializer(many=True))
    def list(self, request):
        plans = Plan.objects.filter(is_active=True)
        return Response(PlanSerializer(plans, many=True).data)


class SubscriptionViewSet(BillingViewSet):
    """The workspace's subscription; changes are owner-only."""

    serializer_class = SubscriptionSerializer

    @extend_schema(operation_id="billing_subscription_retrieve", responses=SubscriptionSerializer)
    def retrieve(self, request):
        return Response(SubscriptionSerializer(services.get_subscription(self.workspace)).data)

    @extend_schema(
        operation_id="billing_subscription_checkout_create",
        request=CheckoutSerializer,
        responses=CheckoutSessionSerializer,
        description="Create a Razorpay subscription and return options for Razorpay Checkout.",
    )
    def checkout(self, request):
        data = self.validated(CheckoutSerializer)
        session = services.start_checkout(
            workspace=self.workspace, plan_slug=data["plan_id"], interval=data["interval"]
        )
        return Response(CheckoutSessionSerializer(session).data)

    @extend_schema(
        operation_id="billing_subscription_verify_create",
        request=CheckoutVerifySerializer,
        responses=SubscriptionSerializer,
        description="Verify the Checkout signature. Status may stay pending until the webhook.",
    )
    def verify(self, request):
        data = self.validated(CheckoutVerifySerializer)
        subscription = services.verify_checkout(
            workspace=self.workspace,
            payment_id=data["razorpay_payment_id"],
            subscription_id=data["razorpay_subscription_id"],
            signature=data["razorpay_signature"],
        )
        return Response(SubscriptionSerializer(subscription).data)

    @extend_schema(
        operation_id="billing_subscription_cancel_create",
        request=CancelSubscriptionSerializer,
        responses=SubscriptionSerializer,
    )
    def cancel(self, request):
        data = self.validated(CancelSubscriptionSerializer)
        subscription = services.cancel_subscription(
            workspace=self.workspace, at_period_end=data["at_period_end"]
        )
        return Response(SubscriptionSerializer(subscription).data)


class BillingProfileViewSet(BillingViewSet):
    """Details printed on GST invoices. Admins can read it; only the owner can change it."""

    serializer_class = BillingProfileSerializer
    read_role = Role.ADMIN

    @extend_schema(operation_id="billing_profile_retrieve", responses=BillingProfileSerializer)
    def retrieve(self, request):
        profile = services.get_billing_profile(self.workspace)
        return Response(BillingProfileSerializer(profile).data)

    @extend_schema(
        operation_id="billing_profile_partial_update",
        request=BillingProfileSerializer,
        responses=BillingProfileSerializer,
    )
    def partial_update(self, request):
        profile = services.get_billing_profile(self.workspace)
        serializer = BillingProfileSerializer(
            profile, data=request.data, partial=True, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class InvoiceViewSet(BillingViewSet):
    # GST invoices for the workspace, newest first. (No docstring: it would change the schema.)

    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.all()
    read_role = Role.ADMIN

    @extend_schema(operation_id="billing_invoices_list", responses=InvoiceSerializer(many=True))
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class UsageViewSet(BillingViewSet):
    """Current usage against the plan's limits."""

    serializer_class = UsageSerializer

    @extend_schema(operation_id="billing_usage_retrieve", responses=UsageSerializer)
    def retrieve(self, request):
        counts = services.usage_counts(self.workspace)
        metrics = [
            {
                "key": metric,
                "used": counts[metric],
                "limit": entitlements.effective_limit(self.workspace, metric, counts[metric]),
            }
            for metric in entitlements.METRICS
        ]
        return Response(UsageSerializer({"metrics": metrics}).data)


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": None}}, status=status
    )


@csrf_exempt
@require_POST
def razorpay_webhook(request: HttpRequest) -> JsonResponse:
    """``POST /webhooks/razorpay/`` (public). Not in the OpenAPI schema.

    Verifies ``X-Razorpay-Signature`` (HMAC-SHA256 of the raw body with
    ``RAZORPAY_WEBHOOK_SECRET``) and deduplicates on ``X-Razorpay-Event-Id``.
    """
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured; rejecting Razorpay webhook")
    body = request.body
    if not razorpay.webhook_signature_is_valid(body, request.headers.get(SIGNATURE_HEADER), secret):
        logger.warning("Razorpay webhook with a missing or invalid signature rejected")
        return _error("invalid_signature", "Invalid webhook signature.", 400)

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        return _error("invalid_payload", "The webhook body must be a JSON object.", 400)

    event_id = request.headers.get(EVENT_ID_HEADER, "").strip()
    if not event_id or len(event_id) > EVENT_ID_MAX_LENGTH:
        event_id = f"sha256:{hashlib.sha256(body).hexdigest()}"
    outcome = webhooks.handle_delivery(event_id, payload)
    return JsonResponse({"status": outcome})
