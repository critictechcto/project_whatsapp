"""Analytics reports (docs/contracts/analytics.md). Every endpoint is a GET open to any member."""

from django.core.cache import cache
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.billing import entitlements
from common.exceptions import FeatureNotAvailable
from common.roles import Role
from common.tenancy import WorkspaceScopedAPIView

from . import exports, reports
from .ranges import ReportRange, parse_range
from .schema_enums import REPORTS
from .serializers import (
    AnalyticsCampaignsSerializer,
    AnalyticsCommerceSerializer,
    AnalyticsMessagesSerializer,
    AnalyticsOverviewSerializer,
    AnalyticsTeamSerializer,
    AnalyticsTemplatesSerializer,
)

CACHE_SECONDS = 60
CLOSED_RANGE_CACHE_SECONDS = 10 * 60

RANGE_PARAMETERS = [
    OpenApiParameter(
        "from",
        OpenApiTypes.DATE,
        description="First day (inclusive, workspace time zone). Defaults to `to` minus 29 days.",
    ),
    OpenApiParameter(
        "to",
        OpenApiTypes.DATE,
        description="Last day (inclusive, workspace time zone). Defaults to today.",
    ),
]
REPORT_DESCRIPTION = (
    "Dates are inclusive and read in the workspace time zone. Readable by every member; needs "
    "the plan's `analytics` feature."
)
ERROR_RESPONSES = {
    400: OpenApiResponse(description="`invalid`: bad range or report"),
    409: OpenApiResponse(description="`feature_not_available`: the plan lacks the feature"),
}

FEATURE_MESSAGES = {
    entitlements.ANALYTICS: "Analytics is not included in your plan. Upgrade your plan to use it.",
    entitlements.COMMERCE: (
        "Commerce analytics need the WhatsApp store, which your plan does not include."
    ),
}


def feature_not_available(feature: str) -> FeatureNotAvailable:
    message = FEATURE_MESSAGES[feature]
    exc = FeatureNotAvailable(message)
    # The error envelope takes the message from default_detail and details from a dict detail.
    exc.default_detail = message
    exc.detail = {"feature": feature}
    return exc


class Report:
    """How to build, serialize and gate one report."""

    def __init__(self, name, serializer_class, build, *, commerce: bool = False):
        self.name = name
        self.serializer_class = serializer_class
        self.build = build
        self.requires_commerce = commerce


REPORT_REGISTRY = {
    "overview": Report("overview", AnalyticsOverviewSerializer, None),
    "messages": Report("messages", AnalyticsMessagesSerializer, reports.messages),
    "templates": Report("templates", AnalyticsTemplatesSerializer, reports.templates),
    "campaigns": Report("campaigns", AnalyticsCampaignsSerializer, reports.campaigns),
    "team": Report("team", AnalyticsTeamSerializer, reports.team),
    "commerce": Report("commerce", AnalyticsCommerceSerializer, reports.commerce, commerce=True),
}


class AnalyticsView(WorkspaceScopedAPIView):
    read_role = Role.VIEWER
    filter_backends: list = []
    pagination_class = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.require_feature(entitlements.ANALYTICS)

    def require_feature(self, feature: str) -> None:
        if not entitlements.has_feature(self.workspace, feature):
            raise feature_not_available(feature)

    def report_data(self, report: Report, rng: ReportRange) -> dict:
        """The serialized report, cached per workspace, report and range."""
        if report.requires_commerce:
            self.require_feature(entitlements.COMMERCE)
        has_commerce = entitlements.has_feature(self.workspace, entitlements.COMMERCE)
        key = ":".join(
            [
                "analytics",
                "v1",
                str(self.workspace.pk),
                report.name,
                rng.from_date.isoformat(),
                rng.to_date.isoformat(),
                rng.zone.key,
                "c" if has_commerce else "n",
            ]
        )
        data = cache.get(key)
        if data is None:
            if report.name == "overview":
                raw = reports.overview(self.workspace, rng, commerce=has_commerce)
            else:
                raw = report.build(self.workspace, rng)
            data = dict(report.serializer_class(raw).data)
            timeout = CLOSED_RANGE_CACHE_SECONDS if rng.is_closed else CACHE_SECONDS
            cache.set(key, data, timeout)
        return data


def report_view(report_name: str, summary: str) -> type[AnalyticsView]:
    report = REPORT_REGISTRY[report_name]

    class _ReportView(AnalyticsView):
        serializer_class = report.serializer_class

        @extend_schema(
            operation_id=f"analytics_{report_name}_retrieve",
            summary=summary,
            description=REPORT_DESCRIPTION
            + (" Also needs the `commerce` feature." if report.requires_commerce else ""),
            parameters=RANGE_PARAMETERS,
            responses={200: report.serializer_class, **ERROR_RESPONSES},
        )
        def get(self, request):
            rng = parse_range(request.query_params, self.workspace)
            return Response(self.report_data(report, rng))

    _ReportView.__name__ = f"Analytics{report_name.title()}View"
    _ReportView.__qualname__ = _ReportView.__name__
    return _ReportView


OverviewView = report_view("overview", "Totals for the range and the previous period")
MessagesView = report_view("messages", "Daily message series and breakdowns")
TemplatesView = report_view("templates", "Template performance")
CampaignsView = report_view("campaigns", "Campaigns started in the range")
TeamView = report_view("team", "Per-member activity")
CommerceView = report_view("commerce", "Orders and revenue (needs the commerce feature)")


class ExportQuerySerializer(serializers.Serializer):
    report = serializers.ChoiceField(choices=REPORTS)


class ExportView(AnalyticsView):
    serializer_class = ExportQuerySerializer

    def perform_content_negotiation(self, request, force=False):
        # The file is a plain HttpResponse; an ``Accept: text/csv`` client must not get 406, and
        # errors still render as JSON.
        return super().perform_content_negotiation(request, force=True)

    @extend_schema(
        operation_id="analytics_export_retrieve",
        summary="Download a report as CSV",
        description=(
            "The rows of the matching report (the daily series for `messages` and `commerce`), "
            "with money in rupees. Same range and plan checks as that report."
        ),
        parameters=[
            OpenApiParameter("report", str, enum=list(REPORTS), required=True),
            *RANGE_PARAMETERS,
        ],
        responses={
            (200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="CSV file"),
            **ERROR_RESPONSES,
        },
    )
    def get(self, request):
        query = ExportQuerySerializer(data={"report": request.query_params.get("report", "")})
        query.is_valid(raise_exception=True)
        report_name = query.validated_data["report"]
        rng = parse_range(request.query_params, self.workspace)
        data = self.report_data(REPORT_REGISTRY[report_name], rng)
        response = HttpResponse(
            exports.render_csv(report_name, data), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{exports.filename(report_name, data)}"'
        )
        return response
