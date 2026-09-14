"""Automation API: rules CRUD, the business-hours singleton and the run log."""

import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.billing import entitlements
from common.exceptions import FeatureNotAvailable
from common.roles import Role
from common.tenancy import WorkspaceScopedGenericViewSet

from .models import AutomationRule, AutomationRun, BusinessHours
from .schema_enums import AUTOMATION_RUN_STATUSES, AUTOMATION_TRIGGERS
from .serializers import (
    AutomationRuleSerializer,
    AutomationRunSerializer,
    BusinessHoursSerializer,
)

TRUE_VALUES = frozenset({"true", "1", "yes"})
FALSE_VALUES = frozenset({"false", "0", "no"})


class AutomationViewSet(WorkspaceScopedGenericViewSet):
    filter_backends: list = []
    read_role = Role.VIEWER
    write_role = Role.ADMIN

    def query_choice(self, name: str, choices) -> str | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        if value not in choices:
            raise serializers.ValidationError({name: [f"Use one of: {', '.join(choices)}."]})
        return value

    def query_uuid(self, name: str) -> uuid.UUID | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        try:
            return uuid.UUID(value)
        except ValueError:
            raise serializers.ValidationError({name: ["Must be a valid UUID."]}) from None

    def query_bool(self, name: str) -> bool | None:
        value = self.request.query_params.get(name)
        if value in (None, ""):
            return None
        if value.lower() in TRUE_VALUES:
            return True
        if value.lower() in FALSE_VALUES:
            return False
        raise serializers.ValidationError({name: ["Use true or false."]})

    def paginated(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(serializer_class(page, many=True).data)


class AutomationRuleViewSet(AutomationViewSet):
    """Rules that react to inbound messages, e.g. keyword auto-replies."""

    queryset = AutomationRule.objects.all()
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
        queryset = self.get_queryset()
        trigger = self.query_choice("trigger", AUTOMATION_TRIGGERS)
        if trigger is not None:
            queryset = queryset.filter(trigger=trigger)
        is_active = self.query_bool("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return self.paginated(queryset, AutomationRuleSerializer)

    @extend_schema(
        operation_id="automations_rules_create",
        request=AutomationRuleSerializer,
        responses={201: AutomationRuleSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.check_keyword_feature(serializer.validated_data, None)
        rule = serializer.save(workspace=self.workspace)
        return Response(self.get_serializer(rule).data, status=status.HTTP_201_CREATED)

    @extend_schema(operation_id="automations_rules_retrieve", responses=AutomationRuleSerializer)
    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(
        operation_id="automations_rules_partial_update",
        request=AutomationRuleSerializer,
        responses=AutomationRuleSerializer,
    )
    def partial_update(self, request, pk=None):
        rule = self.get_object()
        serializer = self.get_serializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.check_keyword_feature(serializer.validated_data, rule)
        rule = serializer.save()
        return Response(self.get_serializer(rule).data)

    @extend_schema(operation_id="automations_rules_destroy", responses={204: None})
    def destroy(self, request, pk=None):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def check_keyword_feature(self, attrs: dict, rule: AutomationRule | None) -> None:
        """Creating an active keyword rule, or making a rule an active keyword rule, needs the
        plan's ``keyword_automations`` feature. Other edits (including deactivating) don't."""
        trigger = attrs.get("trigger", rule.trigger if rule else None)
        is_active = attrs.get("is_active", rule.is_active if rule else True)
        if trigger != AutomationRule.Trigger.KEYWORD or not is_active:
            return
        if rule is not None and rule.trigger == AutomationRule.Trigger.KEYWORD and rule.is_active:
            return
        if not entitlements.has_feature(self.workspace, entitlements.KEYWORD_AUTOMATIONS):
            raise FeatureNotAvailable(
                "Keyword automations are not included in your plan. Upgrade your plan to use them."
            )


class BusinessHoursViewSet(AutomationViewSet):
    """The workspace's business hours (one per workspace)."""

    serializer_class = BusinessHoursSerializer

    def get_hours(self) -> BusinessHours:
        hours, _ = BusinessHours.objects.select_related("workspace").get_or_create(
            workspace=self.workspace
        )
        return hours

    @extend_schema(
        operation_id="automations_business_hours_retrieve", responses=BusinessHoursSerializer
    )
    def retrieve(self, request):
        return Response(self.get_serializer(self.get_hours()).data)

    @extend_schema(
        operation_id="automations_business_hours_partial_update",
        request=BusinessHoursSerializer,
        responses=BusinessHoursSerializer,
    )
    def partial_update(self, request):
        serializer = self.get_serializer(self.get_hours(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(serializer.save()).data)


class AutomationRunViewSet(AutomationViewSet):
    """History of rule executions."""

    queryset = AutomationRun.objects.select_related("rule")
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
        queryset = self.get_queryset()
        rule_id = self.query_uuid("rule")
        if rule_id is not None:
            queryset = queryset.filter(rule_id=rule_id)
        run_status = self.query_choice("status", AUTOMATION_RUN_STATUSES)
        if run_status is not None:
            queryset = queryset.filter(status=run_status)
        return self.paginated(queryset, AutomationRunSerializer)
