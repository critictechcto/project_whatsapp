"""Billing API and Razorpay webhook. Bodies are stubs (501); roles and validation are enforced."""

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

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

NOT_IMPLEMENTED_MESSAGE = "This endpoint is not available yet."


class StubNotImplemented(exceptions.APIException):
    status_code = 501
    default_code = "not_implemented"
    default_detail = NOT_IMPLEMENTED_MESSAGE


class StubViewSet(WorkspaceScopedGenericViewSet):
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.OWNER

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class PlanViewSet(StubViewSet):
    """Plans a workspace can subscribe to (prices before GST)."""

    serializer_class = PlanSerializer
    pagination_class = None

    @extend_schema(operation_id="billing_plans_list", responses=PlanSerializer(many=True))
    def list(self, request):
        raise StubNotImplemented()


class SubscriptionViewSet(StubViewSet):
    """The workspace's subscription; changes are owner-only."""

    serializer_class = SubscriptionSerializer

    @extend_schema(operation_id="billing_subscription_retrieve", responses=SubscriptionSerializer)
    def retrieve(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="billing_subscription_checkout_create",
        request=CheckoutSerializer,
        responses=CheckoutSessionSerializer,
        description="Create a Razorpay subscription and return options for Razorpay Checkout.",
    )
    def checkout(self, request):
        self.validated(CheckoutSerializer)
        raise StubNotImplemented()

    @extend_schema(
        operation_id="billing_subscription_verify_create",
        request=CheckoutVerifySerializer,
        responses=SubscriptionSerializer,
        description="Verify the Checkout signature. Status may stay pending until the webhook.",
    )
    def verify(self, request):
        self.validated(CheckoutVerifySerializer)
        raise StubNotImplemented()

    @extend_schema(
        operation_id="billing_subscription_cancel_create",
        request=CancelSubscriptionSerializer,
        responses=SubscriptionSerializer,
    )
    def cancel(self, request):
        self.validated(CancelSubscriptionSerializer)
        raise StubNotImplemented()


class BillingProfileViewSet(StubViewSet):
    """Details printed on GST invoices. Admins can read it; only the owner can change it."""

    serializer_class = BillingProfileSerializer
    read_role = Role.ADMIN

    @extend_schema(operation_id="billing_profile_retrieve", responses=BillingProfileSerializer)
    def retrieve(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="billing_profile_partial_update",
        request=BillingProfileSerializer,
        responses=BillingProfileSerializer,
    )
    def partial_update(self, request):
        self.validated(BillingProfileSerializer, partial=True)
        raise StubNotImplemented()


class InvoiceViewSet(StubViewSet):
    serializer_class = InvoiceSerializer
    read_role = Role.ADMIN

    @extend_schema(operation_id="billing_invoices_list", responses=InvoiceSerializer(many=True))
    def list(self, request):
        raise StubNotImplemented()


class UsageViewSet(StubViewSet):
    """Current usage against the plan's limits."""

    serializer_class = UsageSerializer

    @extend_schema(operation_id="billing_usage_retrieve", responses=UsageSerializer)
    def retrieve(self, request):
        raise StubNotImplemented()


@csrf_exempt
@require_POST
def razorpay_webhook(request: HttpRequest) -> JsonResponse:
    """``POST /webhooks/razorpay/`` (public). Not in the OpenAPI schema.

    To build: verify ``X-Razorpay-Signature`` (HMAC-SHA256 of the raw body with
    ``RAZORPAY_WEBHOOK_SECRET``) and deduplicate on ``x-razorpay-event-id``.
    """
    error = {"code": "not_implemented", "message": NOT_IMPLEMENTED_MESSAGE, "details": None}
    return JsonResponse({"error": error}, status=501)
