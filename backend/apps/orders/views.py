"""Orders and store API (docs/contracts/wave-3-commerce.md, "Orders" and "Store").

Order actions go through ``services`` (status changes, OrderEvents, buyer notifications); store
changes, the checklist and starter templates through ``store_setup``.
"""

import uuid
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import DefaultCursorPagination
from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from . import services, store_setup, transitions
from .models import Order, OrderEvent
from .schema_enums import ORDER_STAGES, ORDER_STATUSES, PAYMENT_METHODS, PAYMENT_STATUSES
from .serializers import (
    CancelOrderSerializer,
    OrderEventSerializer,
    OrderListItemSerializer,
    OrderNotesSerializer,
    OrderSerializer,
    OrderSummarySerializer,
    OrderTransitionSerializer,
    StarterTemplatesResultSerializer,
    StoreChecklistSerializer,
    StoreSettingsSerializer,
)

# Orders that count as sales in the summary: confirmed or later, not cancelled or expired.
SALE_STATUSES = (
    transitions.CONFIRMED,
    transitions.PACKED,
    transitions.SHIPPED,
    transitions.DELIVERED,
    transitions.NEEDS_ATTENTION,
)


DASHBOARD = OrderEvent.Actor.DASHBOARD


class OldestFirstCursorPagination(DefaultCursorPagination):
    ordering = "created_at"


def _order_response(order: Order) -> Response:
    fresh = (
        Order.objects.select_related("contact", "phone_number")
        .prefetch_related("items", "payment_links")
        .get(pk=order.pk)
    )
    return Response(OrderSerializer(fresh).data)


def _query_uuid(request, name: str) -> uuid.UUID | None:
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise serializers.ValidationError({name: ["Must be a valid UUID."]}) from None


def _query_choice(request, name: str, choices) -> str | None:
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    if value not in choices:
        raise serializers.ValidationError({name: [f"Use one of: {', '.join(choices)}."]})
    return value


def _query_moment(request, name: str, tz: ZoneInfo) -> datetime | None:
    """An ISO 8601 datetime (naive = workspace time) or date (midnight in workspace time)."""
    value = request.query_params.get(name, "").strip()
    if not value:
        return None
    try:
        moment = parse_datetime(value)
        if moment is None and (day := parse_date(value)) is not None:
            moment = datetime.combine(day, time.min)
    except ValueError:
        moment = None
    if moment is None:
        raise serializers.ValidationError({name: ["Use an ISO 8601 date or date-time."]})
    return timezone.make_aware(moment, tz) if timezone.is_naive(moment) else moment


def _workspace_zone(workspace) -> ZoneInfo:
    try:
        return ZoneInfo(workspace.time_zone)
    except (KeyError, ValueError):
        return ZoneInfo("Asia/Kolkata")


class OrderViewSet(WorkspaceScopedGenericViewSet):
    """The workspace's orders, newest first."""

    queryset = Order.objects.select_related("contact", "phone_number")
    serializer_class = OrderSerializer
    lookup_value_converter = "uuid"
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.AGENT
    action_roles = {"mark_refunded": Role.ADMIN}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("items", "payment_links")
        return queryset

    @extend_schema(
        operation_id="orders_list",
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                description=(
                    "Comma-separated OrderStatusEnum values. Drafts are listed only when asked "
                    "for here."
                ),
            ),
            OpenApiParameter("stage", OpenApiTypes.STR, enum=ORDER_STAGES),
            OpenApiParameter("payment_status", OpenApiTypes.STR, enum=PAYMENT_STATUSES),
            OpenApiParameter("payment_method", OpenApiTypes.STR, enum=PAYMENT_METHODS),
            OpenApiParameter("contact", OpenApiTypes.UUID),
            OpenApiParameter(
                "search", OpenApiTypes.STR, description="Order number, contact name or phone."
            ),
            OpenApiParameter(
                "created_after", OpenApiTypes.DATETIME, description="Inclusive lower bound."
            ),
            OpenApiParameter(
                "created_before", OpenApiTypes.DATETIME, description="Exclusive upper bound."
            ),
        ],
        responses=OrderListItemSerializer(many=True),
    )
    def list(self, request):
        queryset = self.get_queryset()
        statuses: list[str] = []
        if raw_status := request.query_params.get("status", "").strip():
            statuses = [value.strip() for value in raw_status.split(",") if value.strip()]
            invalid = [value for value in statuses if value not in ORDER_STATUSES]
            if invalid:
                raise serializers.ValidationError(
                    {"status": [f"Use values from: {', '.join(ORDER_STATUSES)}."]}
                )
            queryset = queryset.filter(status__in=statuses)
        if transitions.DRAFT not in statuses:
            queryset = queryset.exclude(status=transitions.DRAFT)
        if stage := _query_choice(request, "stage", ORDER_STAGES):
            queryset = queryset.filter(status__in=transitions.STAGE_STATUSES[stage])
        if payment_status := _query_choice(request, "payment_status", PAYMENT_STATUSES):
            queryset = queryset.filter(payment_status=payment_status)
        if payment_method := _query_choice(request, "payment_method", PAYMENT_METHODS):
            queryset = queryset.filter(payment_method=payment_method)
        if contact_id := _query_uuid(request, "contact"):
            queryset = queryset.filter(contact_id=contact_id)
        if search := request.query_params.get("search", "").strip():
            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(contact__name__icontains=search)
                | Q(contact__phone_e164__icontains=search)
            )
        tz = _workspace_zone(self.workspace)
        if created_after := _query_moment(request, "created_after", tz):
            queryset = queryset.filter(created_at__gte=created_after)
        if created_before := _query_moment(request, "created_before", tz):
            queryset = queryset.filter(created_at__lt=created_before)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(OrderListItemSerializer(page, many=True).data)

    @extend_schema(operation_id="orders_retrieve", responses=OrderSerializer)
    def retrieve(self, request, pk=None):
        return Response(OrderSerializer(self.get_object()).data)

    @extend_schema(
        operation_id="orders_partial_update",
        request=OrderNotesSerializer,
        responses=OrderSerializer,
        description="Update the seller-internal notes.",
    )
    def partial_update(self, request, pk=None):
        order = self.get_object()
        serializer = OrderNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_notes(
            order, serializer.validated_data["notes"], actor=DASHBOARD, user=request.user
        )
        return _order_response(order)

    @extend_schema(
        operation_id="orders_events_list",
        responses=OrderEventSerializer(many=True),
        description="The order timeline, oldest first.",
    )
    @action(detail=True, methods=["get"], pagination_class=OldestFirstCursorPagination)
    def events(self, request, pk=None):
        order = self.get_object()
        queryset = OrderEvent.objects.filter(workspace=self.workspace, order=order).select_related(
            "user"
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(OrderEventSerializer(page, many=True).data)

    @extend_schema(
        operation_id="orders_transition_create",
        request=OrderTransitionSerializer,
        responses=OrderSerializer,
        description="409 invalid_order_transition when the move isn't allowed.",
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        order = self.get_object()
        serializer = OrderTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.transition(
            order,
            data["to_status"],
            actor=DASHBOARD,
            user=request.user,
            courier_name=data.get("courier_name", ""),
            awb_number=data.get("awb_number", ""),
            tracking_url=data.get("tracking_url", ""),
            notify_buyer=data["notify_buyer"],
        )
        return _order_response(order)

    @extend_schema(
        operation_id="orders_cancel_create",
        request=CancelOrderSerializer,
        responses=OrderSerializer,
        description="Also cancels an open payment link.",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.cancel_order(
            order,
            actor=DASHBOARD,
            user=request.user,
            reason=data["reason"],
            restock=data["restock"],
            notify_buyer=data["notify_buyer"],
        )
        return _order_response(order)

    @extend_schema(
        operation_id="orders_mark_cod_collected_create",
        request=None,
        responses=OrderSerializer,
        description="Only COD orders that are shipped or delivered.",
    )
    @action(detail=True, methods=["post"], url_path="mark-cod-collected")
    def mark_cod_collected(self, request, pk=None):
        order = self.get_object()
        services.mark_cod_collected(order, actor=DASHBOARD, user=request.user)
        return _order_response(order)

    @extend_schema(
        operation_id="orders_mark_refunded_create",
        request=None,
        responses=OrderSerializer,
        description="Only paid orders that are cancelled or need attention; refund in Razorpay.",
    )
    @action(detail=True, methods=["post"], url_path="mark-refunded")
    def mark_refunded(self, request, pk=None):
        order = self.get_object()
        services.mark_refunded(order, actor=DASHBOARD, user=request.user)
        return _order_response(order)

    @extend_schema(operation_id="orders_summary_retrieve", responses=OrderSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        tz = _workspace_zone(self.workspace)
        today_start = datetime.combine(timezone.now().astimezone(tz).date(), time.min, tzinfo=tz)
        orders = Order.objects.filter(workspace=self.workspace)
        today = orders.filter(
            created_at__gte=today_start.astimezone(UTC), status__in=SALE_STATUSES
        ).aggregate(count=Count("pk"), revenue=Sum("total_paise"))
        counts = orders.aggregate(
            open_count=Count("pk", filter=Q(status__in=transitions.OPEN_STATUSES)),
            needs_attention_count=Count("pk", filter=Q(status=transitions.NEEDS_ATTENTION)),
            awaiting_payment_count=Count("pk", filter=Q(status=transitions.PENDING_PAYMENT)),
        )
        data = {
            "today_count": today["count"] or 0,
            "today_revenue_paise": today["revenue"] or 0,
            **counts,
        }
        return Response(OrderSummarySerializer(data).data)


class StoreViewSet(WorkspaceScopedGenericViewSet):
    """Store settings (one per workspace), the setup checklist and starter templates."""

    serializer_class = StoreSettingsSerializer
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    @extend_schema(operation_id="store_settings_retrieve", responses=StoreSettingsSerializer)
    def retrieve(self, request):
        store_settings = services.get_store_settings(self.workspace)
        return Response(StoreSettingsSerializer(store_settings).data)

    @extend_schema(
        operation_id="store_settings_partial_update",
        request=StoreSettingsSerializer,
        responses=StoreSettingsSerializer,
        description=(
            "Turning on enabled needs the commerce feature, an active product and a connected "
            "number (409 commerce_not_enabled)."
        ),
    )
    def partial_update(self, request):
        serializer = StoreSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        store_settings = store_setup.update_store_settings(
            self.workspace, serializer.validated_data
        )
        return Response(StoreSettingsSerializer(store_settings).data)

    @extend_schema(operation_id="store_checklist_retrieve", responses=StoreChecklistSerializer)
    def checklist(self, request):
        return Response(StoreChecklistSerializer(store_setup.checklist(self.workspace)).data)

    @extend_schema(
        operation_id="store_starter_templates_create",
        request=None,
        responses=StarterTemplatesResultSerializer,
        description="Create missing order templates in the store number's WABA and map them.",
    )
    def starter_templates(self, request):
        result = store_setup.create_starter_templates(self.workspace, user=request.user)
        return Response(StarterTemplatesResultSerializer(result).data)
