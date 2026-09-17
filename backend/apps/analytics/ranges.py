"""Report date ranges: inclusive dates in the workspace time zone (docs/contracts/analytics.md)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import serializers

DEFAULT_TIME_ZONE = "Asia/Kolkata"
DEFAULT_DAYS = 30
MAX_DAYS = 92


def workspace_zone(workspace) -> ZoneInfo:
    try:
        return ZoneInfo(workspace.time_zone or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def local_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=zone)


@dataclass(frozen=True, slots=True)
class ReportRange:
    from_date: date
    to_date: date
    zone: ZoneInfo
    today: date

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    @property
    def previous_to(self) -> date:
        return self.from_date - timedelta(days=1)

    @property
    def previous_from(self) -> date:
        return self.from_date - timedelta(days=self.days)

    @property
    def start(self) -> datetime:
        """Aware start of the range (inclusive)."""
        return local_midnight(self.from_date, self.zone)

    @property
    def end(self) -> datetime:
        """Aware end of the range (exclusive): midnight after ``to``."""
        return local_midnight(self.to_date + timedelta(days=1), self.zone)

    @property
    def previous_start(self) -> datetime:
        return local_midnight(self.previous_from, self.zone)

    @property
    def is_closed(self) -> bool:
        """The range ended before today, so its numbers only change through late updates."""
        return self.to_date < self.today

    def dates(self) -> list[date]:
        return [self.from_date + timedelta(days=offset) for offset in range(self.days)]

    def as_dict(self) -> dict:
        return {
            "from": self.from_date,
            "to": self.to_date,
            "time_zone": self.zone.key,
            "previous_from": self.previous_from,
            "previous_to": self.previous_to,
        }


class RangeQuerySerializer(serializers.Serializer):
    """Validates ``from``/``to`` query params. Needs ``zone`` in the context."""

    to = serializers.DateField(required=False)

    def get_fields(self):
        fields = super().get_fields()
        return {"from": serializers.DateField(required=False), **fields}

    def validate(self, attrs):
        zone = self.context["zone"]
        today = timezone.now().astimezone(zone).date()
        to_date = attrs.get("to") or today
        from_date = attrs.get("from") or to_date - timedelta(days=DEFAULT_DAYS - 1)
        if to_date > today:
            raise serializers.ValidationError({"to": ["The end date can't be in the future."]})
        if from_date > to_date:
            raise serializers.ValidationError(
                {"from": ["The start date must be on or before the end date."]}
            )
        if (to_date - from_date).days + 1 > MAX_DAYS:
            raise serializers.ValidationError(
                {"from": [f"The range can be at most {MAX_DAYS} days."]}
            )
        return ReportRange(from_date=from_date, to_date=to_date, zone=zone, today=today)


def parse_range(query_params, workspace) -> ReportRange:
    serializer = RangeQuerySerializer(
        data={key: query_params[key] for key in ("from", "to") if query_params.get(key)},
        context={"zone": workspace_zone(workspace)},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
