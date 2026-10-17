"""Offers API (docs/contracts/services-and-offers.md, "Offers"): read viewer, write admin,
redeem agent. Writes and redemptions need the plan's ``commerce`` feature."""

import uuid

from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from apps.billing import entitlements
from common.exceptions import FeatureNotAvailable
from common.pagination import DefaultCursorPagination
from common.roles import Role
from common.tenancy import (
    WorkspaceScopedAPIView,
    WorkspaceScopedGenericViewSet,
    WorkspaceScopedViewSet,
)

from . import services
from .models import OfferClaim, OfferCode
from .schema_enums import CLAIM_STATUSES
from .serializers import (
    CounterRedeemSerializer,
    OfferClaimSerializer,
    OfferCodeSerializer,
    OfferStatsSerializer,
    RedeemClaimSerializer,
)

COMMERCE_REQUIRED = "Offer codes are part of the WhatsApp store. Upgrade your plan to use them."


class CommerceGateMixin:
    """Unsafe requests need the plan's ``commerce`` feature."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in SAFE_METHODS and not entitlements.has_feature(
            self.workspace, entitlements.COMMERCE
        ):
            raise FeatureNotAvailable(COMMERCE_REQUIRED)


class OfferCodeViewSet(CommerceGateMixin, WorkspaceScopedViewSet):
    """The workspace's offer codes, newest first, with claim counters."""

    queryset = OfferCode.objects.annotate(
        claims_count=Count("claims"),
        redeemed_count=Count("claims", filter=Q(claims__status=OfferClaim.Status.REDEEMED)),
    )
    serializer_class = OfferCodeSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    def perform_destroy(self, instance):
        if instance.claims.exists():
            raise services.OfferInUse()
        instance.delete()

    @extend_schema(responses=OfferStatsSerializer)
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        offer = self.get_object()
        return Response(OfferStatsSerializer(services.offer_stats(offer)).data)


class OfferClaimViewSet(CommerceGateMixin, WorkspaceScopedGenericViewSet, mixins.ListModelMixin):
    """Claims of the workspace's offer codes, newest first."""

    queryset = OfferClaim.objects.select_related("offer", "contact", "order", "redeemed_by")
    serializer_class = OfferClaimSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    pagination_class = DefaultCursorPagination
    read_role = Role.VIEWER
    write_role = Role.ADMIN
    action_roles = {"redeem": Role.AGENT}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset
        params = self.request.query_params
        offer_id = params.get("offer")
        if offer_id:
            try:
                queryset = queryset.filter(offer_id=uuid.UUID(offer_id))
            except ValueError:
                raise serializers.ValidationError({"offer": ["Must be a valid UUID."]}) from None
        claim_status = params.get("status")
        if claim_status:
            if claim_status not in CLAIM_STATUSES:
                raise serializers.ValidationError(
                    {"status": [f"Use one of: {', '.join(CLAIM_STATUSES)}."]}
                )
            queryset = queryset.filter(status=claim_status)
        phone = (params.get("phone") or "").strip()
        if phone:
            queryset = queryset.filter(contact__phone_e164__contains=phone)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("offer", OpenApiTypes.UUID, description="Offer code id."),
            OpenApiParameter("status", OpenApiTypes.STR, enum=CLAIM_STATUSES),
            OpenApiParameter("phone", OpenApiTypes.STR, description="Part of the phone number."),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=RedeemClaimSerializer, responses=OfferClaimSerializer)
    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        claim = self.get_object()
        body = RedeemClaimSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        claim = services.redeem_claim(
            claim, bill_paise=body.validated_data.get("bill_paise"), user=request.user
        )
        return Response(OfferClaimSerializer(self.get_queryset().get(pk=claim.pk)).data)


class CounterRedeemView(CommerceGateMixin, WorkspaceScopedAPIView):
    """Redeem a code at the counter by the buyer's phone (creates the contact when new)."""

    serializer_class = CounterRedeemSerializer
    queryset = OfferClaim.objects.all()
    write_role = Role.AGENT

    @extend_schema(
        operation_id="offers_redeem_create",
        request=CounterRedeemSerializer,
        responses={201: OfferClaimSerializer},
    )
    def post(self, request):
        body = CounterRedeemSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        claim = services.redeem_at_counter(
            self.workspace,
            code=body.validated_data["code"],
            phone=body.validated_data["phone"],
            bill_paise=body.validated_data.get("bill_paise"),
            user=request.user,
        )
        claim = OfferClaim.objects.select_related("offer", "contact", "order", "redeemed_by").get(
            pk=claim.pk
        )
        return Response(OfferClaimSerializer(claim).data, status=status.HTTP_201_CREATED)
