"""Billing API and the Razorpay webhook."""

import hashlib
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import cashfree, entitlements, invoice_pdf, prices, razorpay, services, webhooks
from .models import Invoice, Plan
from .serializers import (
    BillingProfileSerializer,
    CancelSubscriptionSerializer,
    CheckoutSerializer,
    CheckoutSessionSerializer,
    CheckoutVerifySerializer,
    InvoiceSerializer,
    PlanSerializer,
    PublicPlansSerializer,
    SubscriptionSerializer,
    UsageSerializer,
)

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"
EVENT_ID_MAX_LENGTH = 100
CASHFREE_SIGNATURE_HEADER = "x-webhook-signature"
CASHFREE_TIMESTAMP_HEADER = "x-webhook-timestamp"
# Browsers may keep the answer but must check it on every load (a 304 when the ETag still
# matches), so a plan id changed in admin shows on the next page load.
PUBLIC_CACHE_CONTROL = "no-cache"


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
        return Response(PlanSerializer(active_plans(), many=True).data)


def active_plans() -> list[Plan]:
    """Active plans in display order, with their Razorpay plan copies loaded in one query."""
    return prices.prefetch(Plan.objects.filter(is_active=True).order_by("sort_order", "slug"))


class PublicPlansView(APIView):
    """Plans and prices for the marketing site: no authentication, no workspace."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_plans"

    @extend_schema(
        operation_id="billing_public_plans_list",
        responses=PublicPlansSerializer,
        auth=[],
        description=(
            "Active plans with prices before GST (null when an interval can't be bought right "
            "now) and the GST rate added at checkout. Public: no authentication or workspace "
            "header; throttled per IP. Sent with an ETag and no-cache, so browsers revalidate "
            "on every load."
        ),
    )
    def get(self, request):
        data = PublicPlansSerializer(
            {"gst_rate_percent": services.gst_rate_percent(), "plans": active_plans()}
        ).data
        body = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        etag = f'"{hashlib.sha256(body.encode()).hexdigest()[:32]}"'
        if_none_match = request.headers.get("If-None-Match", "")
        matches = etag in (tag.strip().removeprefix("W/") for tag in if_none_match.split(","))
        response = Response(status=304) if matches else Response(data)
        response["ETag"] = etag
        response["Cache-Control"] = PUBLIC_CACHE_CONTROL
        response["Access-Control-Allow-Origin"] = "*"
        return response


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
        description=(
            "Start a checkout on the configured gateway. payment_mode autopay (the Razorpay "
            "default) creates a Razorpay subscription; one_time (the only mode on Cashfree) "
            "creates an order for one prepaid period, on Razorpay or Cashfree. 409 "
            "subscription_active while an auto-pay subscription is active, or for auto-pay "
            "while a prepaid period runs; an active prepaid plan may pay once again to renew or "
            "change plan."
        ),
    )
    def checkout(self, request):
        data = self.validated(CheckoutSerializer)
        session = services.start_checkout(
            workspace=self.workspace,
            plan_slug=data["plan_id"],
            interval=data["interval"],
            payment_mode=data.get("payment_mode"),
        )
        return Response(CheckoutSessionSerializer(session).data)

    @extend_schema(
        operation_id="billing_subscription_verify_create",
        request=CheckoutVerifySerializer,
        responses=SubscriptionSerializer,
        description=(
            "One-time payments (Cashfree order_id, or Razorpay razorpay_order_id with the payment "
            "id and signature): ask the gateway for the order and activate the prepaid plan once "
            "it is paid; 409 payment_not_completed otherwise. Razorpay auto-pay "
            "(razorpay_subscription_id): verify the Checkout signature; the status may stay "
            "pending until the webhook."
        ),
    )
    def verify(self, request):
        data = self.validated(CheckoutVerifySerializer)
        subscription = services.verify_checkout(workspace=self.workspace, **data)
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

    def perform_content_negotiation(self, request, force=False):
        # The PDF is a plain HttpResponse; an ``Accept: application/pdf`` client must not get 406,
        # and errors still render as JSON.
        return super().perform_content_negotiation(request, force=True)

    @extend_schema(
        operation_id="billing_invoices_pdf_retrieve",
        summary="Download an invoice as PDF",
        description="Rendered on demand from the invoice as it was issued.",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(invoice_pdf.render(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice_pdf.filename(invoice)}"'
        response["Cache-Control"] = "private, no-store"
        return response


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


@csrf_exempt
@require_POST
def cashfree_webhook(request: HttpRequest) -> JsonResponse:
    """``POST /webhooks/cashfree/billing/`` (public). Not in the OpenAPI schema.

    Verifies ``x-webhook-signature`` (base64 HMAC-SHA256 of ``x-webhook-timestamp`` + the raw
    body with ``BILLING_CASHFREE_SECRET``). Fulfilling is idempotent, so retries are harmless;
    unknown orders and event types answer 200 so Cashfree stops retrying.
    """
    secret = settings.BILLING_CASHFREE_SECRET
    if not secret:
        logger.error("BILLING_CASHFREE_SECRET is not configured; rejecting Cashfree webhook")
    body = request.body
    valid = cashfree.webhook_signature_is_valid(
        body,
        request.headers.get(CASHFREE_TIMESTAMP_HEADER),
        request.headers.get(CASHFREE_SIGNATURE_HEADER),
        secret,
    )
    if not valid:
        logger.warning("Cashfree billing webhook with a missing or invalid signature rejected")
        return _error("invalid_signature", "Invalid webhook signature.", 400)

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        return _error("invalid_payload", "The webhook body must be a JSON object.", 400)
    return JsonResponse({"status": webhooks.handle_cashfree_event(payload)})
