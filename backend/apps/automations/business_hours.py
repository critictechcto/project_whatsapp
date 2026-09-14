"""Pure business-hours logic: slot parsing, validation and "is this moment inside the hours".

A schedule is a list of slots ``{"day": 0-6, "start": "HH:MM", "end": "HH:MM"}`` where day 0 is
Monday. Times are wall-clock times in the workspace time zone. ``start`` is inclusive and ``end``
exclusive. A slot with ``end < start`` runs overnight: it starts on ``day`` and ends on the next
day (Sunday wraps to Monday). ``end == "00:00"`` therefore means "until midnight".
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIME_ZONE = "Asia/Kolkata"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True, slots=True)
class Slot:
    day: int
    start: time
    end: time

    @property
    def overnight(self) -> bool:
        return self.end < self.start

    def contains(self, weekday: int, moment: time) -> bool:
        if self.start == self.end:
            return False
        if not self.overnight:
            return weekday == self.day and self.start <= moment < self.end
        # Evening part on ``day``, early-morning part on the following day.
        return (weekday == self.day and moment >= self.start) or (
            weekday == (self.day + 1) % 7 and moment < self.end
        )


def parse_time(value: Any) -> time:
    match = TIME_RE.match(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"Invalid time {value!r}; use HH:MM (24-hour).")
    return time(int(match.group(1)), int(match.group(2)))


def slot_error(raw: Mapping[str, Any]) -> str | None:
    """Why ``raw`` is not a valid slot, or None."""
    day = raw.get("day")
    if not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6:
        return "day must be 0 (Monday) to 6 (Sunday)."
    try:
        start, end = parse_time(raw.get("start")), parse_time(raw.get("end"))
    except ValueError as exc:
        return str(exc)
    if start == end:
        return "start and end must differ."
    return None


def parse_schedule(raw: Iterable[Any] | None) -> list[Slot]:
    """Valid slots from stored JSON; malformed entries are ignored."""
    slots = []
    for item in raw or ():
        if isinstance(item, Mapping) and slot_error(item) is None:
            slots.append(Slot(item["day"], parse_time(item["start"]), parse_time(item["end"])))
    return slots


def resolve_time_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def is_open(slots: Iterable[Slot], moment: datetime, time_zone: str | None) -> bool:
    """Whether aware ``moment`` falls inside any slot, in ``time_zone`` wall-clock time."""
    local = moment.astimezone(resolve_time_zone(time_zone))
    weekday, wall_clock = local.weekday(), local.time().replace(tzinfo=None)
    return any(slot.contains(weekday, wall_clock) for slot in slots)


def is_outside(
    *, enabled: bool, schedule: Iterable[Any] | None, moment: datetime, time_zone: str | None
) -> bool:
    """The ``outside_business_hours`` trigger: hours are enabled and ``moment`` is in no slot.

    Disabled hours never count as "outside". An enabled, empty schedule is always outside.
    """
    return enabled and not is_open(parse_schedule(schedule), moment, time_zone)
