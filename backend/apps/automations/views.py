"""Automation API. Endpoint bodies are stubs (501); roles and request validation are enforced."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions

from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from .schema_enums import AUTOMATION_RUN_STATUSES, AUTOMATION_TRIGGERS
from .serializers import (
    AutomationRuleSerializer,
    AutomationRunSerializer,
    BusinessHoursSerializer,
)


class StubNotImplemented(exceptions.APIException):
    status_code = 501
    default_code = "not_implemented"
    default_detail = "This endpoint is not available yet."


class StubViewSet(WorkspaceScopedGenericViewSet):
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    def validated(self, serializer_class, **kwargs) -> dict:
        serializer = serializer_class(
            data=self.request.data, context=self.get_serializer_context(), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class AutomationRuleViewSet(StubViewSet):
    """Rules that react to inbound messages, e.g. keyword auto-replies."""

    serializer_class = AutomationRuleSerializer
    lookup_value_converter = "uuid"

    @extend_schema(
        operation_id="automations_rules_list",
        parameters=[
            OpenApiParameter("trigger", OpenApiTypes.STR, enum=AUTOMATION_TRIGGERS),
            OpenApiParameter("is_active", OpenApiTypes.BOOL),
        ],
        responses=AutomationRuleSerializer(many=True),
    )
    def list(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="automations_rules_create",
        request=AutomationRuleSerializer,
        responses={201: AutomationRuleSerializer},
    )
    def create(self, request):
        self.validated(AutomationRuleSerializer)
        raise StubNotImplemented()

    @extend_schema(operation_id="automations_rules_retrieve", responses=AutomationRuleSerializer)
    def retrieve(self, request, pk=None):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="automations_rules_partial_update",
        request=AutomationRuleSerializer,
        responses=AutomationRuleSerializer,
    )
    def partial_update(self, request, pk=None):
        self.validated(AutomationRuleSerializer, partial=True)
        raise StubNotImplemented()

    @extend_schema(operation_id="automations_rules_destroy", responses={204: None})
    def destroy(self, request, pk=None):
        raise StubNotImplemented()


class BusinessHoursViewSet(StubViewSet):
    """The workspace's business hours (one per workspace)."""

    serializer_class = BusinessHoursSerializer

    @extend_schema(
        operation_id="automations_business_hours_retrieve", responses=BusinessHoursSerializer
    )
    def retrieve(self, request):
        raise StubNotImplemented()

    @extend_schema(
        operation_id="automations_business_hours_partial_update",
        request=BusinessHoursSerializer,
        responses=BusinessHoursSerializer,
    )
    def partial_update(self, request):
        self.validated(BusinessHoursSerializer, partial=True)
        raise StubNotImplemented()


class AutomationRunViewSet(StubViewSet):
    """History of rule executions."""

    serializer_class = AutomationRunSerializer

    @extend_schema(
        operation_id="automations_runs_list",
        parameters=[
            OpenApiParameter("rule", OpenApiTypes.UUID, description="Rule id."),
            OpenApiParameter("status", OpenApiTypes.STR, enum=AUTOMATION_RUN_STATUSES),
        ],
        responses=AutomationRunSerializer(many=True),
    )
    def list(self, request):
        raise StubNotImplemented()
