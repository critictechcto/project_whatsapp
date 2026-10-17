"""Booking days, windows and times (docs/contracts/services-and-offers.md, "Checkout").

All dates and windows are in the workspace time zone (``Workspace.time_zone``, India by default).
A day is offered when it is a ``booking_days`` weekday with at least one window still ahead
(today's windows that have started are not offered); the buyer sees the next
``booking_days_ahead`` such days, at most :data:`MAX_DAY_ROWS` (one list message).
"""

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

DEFAULT_ZONE = "Asia/Kolkata"
MAX_DAY_ROWS = 10  # rows in one WhatsApp list message
SEARCH_DAYS = 62  # how far ahead to look for open days
MAX_SERVICE_NAMES = 120
_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DAY_ARG_FORMAT = "%Y%m%d"


def workspace_zone(workspace) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(workspace, "time_zone", "") or DEFAULT_ZONE)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_ZONE)


def local_now(workspace, now=None) -> datetime:
    return (now or timezone.now()).astimezone(workspace_zone(workspace))


def parse_time(value) -> time | None:
    match = _TIME_RE.fullmatch(str(value or ""))
    return time(int(match.group(1)), int(match.group(2))) if match else None


def windows(store_settings) -> list[dict]:
    """The configured windows that are well formed (index = position in ``booking_windows``;
    malformed entries keep their index but are never offered)."""
    raw = store_settings.booking_windows if isinstance(store_settings.booking_windows, list) else []
    result = []
    for window in raw:
        if not isinstance(window, dict):
            result.append(None)
            continue
        start, end = parse_time(window.get("start")), parse_time(window.get("end"))
        label = str(window.get("label") or "").strip()
        if start is None or end is None or start >= end or not label:
            result.append(None)
            continue
        result.append({"label": label[:24], "start": window["start"], "end": window["end"]})
    return result


def window_start(day: date, window: dict, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, parse_time(window["start"]), tzinfo=tz)


def open_windows(store_settings, workspace, day: date, *, now=None) -> list[tuple[int, dict]]:
    """``(index, window)`` pairs bookable on ``day``: none before today, and today only the
    windows that haven't started yet."""
    now_local = local_now(workspace, now)
    if day < now_local.date():
        return []
    tz = workspace_zone(workspace)
    return [
        (index, window)
        for index, window in enumerate(windows(store_settings))
        if window is not None
        and (day > now_local.date() or window_start(day, window, tz) > now_local)
    ]


def _weekdays(store_settings) -> set[int]:
    days = store_settings.booking_days if isinstance(store_settings.booking_days, list) else []
    return {day for day in days if isinstance(day, int) and 0 <= day <= 6}


def bookable_days(store_settings, workspace, *, now=None) -> list[date]:
    """The next ``booking_days_ahead`` open days (at most :data:`MAX_DAY_ROWS`), today first."""
    wanted = max(1, min(int(store_settings.booking_days_ahead or 1), MAX_DAY_ROWS))
    weekdays = _weekdays(store_settings)
    today = local_now(workspace, now).date()
    days: list[date] = []
    for offset in range(SEARCH_DAYS):
        day = today + timedelta(days=offset)
        if day.weekday() in weekdays and open_windows(store_settings, workspace, day, now=now):
            days.append(day)
            if len(days) >= wanted:
                break
    return days


def is_bookable_day(store_settings, workspace, day: date, *, now=None) -> bool:
    return day in bookable_days(store_settings, workspace, now=now)


def day_arg(day: date) -> str:
    return day.strftime(DAY_ARG_FORMAT)


def parse_day_arg(value: str) -> date | None:
    if not re.fullmatch(r"\d{8}", value or ""):
        return None
    try:
        return datetime.strptime(value, DAY_ARG_FORMAT).date()
    except ValueError:
        return None


def format_day(day: date) -> str:
    """``Mon 20 Oct``."""
    return f"{day:%a} {day.day} {day:%b}"


def day_title(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return format_day(day)


def window_text(window: dict | None) -> str:
    """``Morning (09:00-12:00)``."""
    if not isinstance(window, dict):
        return ""
    return f"{window.get('label', '')} ({window.get('start', '')}-{window.get('end', '')})"


def requested_text(order) -> str:
    """The day and window the buyer asked for, e.g. ``Mon 20 Oct, Morning (09:00-12:00)``."""
    parts = []
    if order.requested_date:
        parts.append(format_day(order.requested_date))
    if order.requested_window:
        parts.append(window_text(order.requested_window))
    return ", ".join(parts)


def format_moment(moment: datetime, workspace) -> str:
    """``Mon 20 Oct, 10:30 AM`` in the workspace time zone."""
    local = moment.astimezone(workspace_zone(workspace))
    clock = local.strftime("%I:%M %p").lstrip("0")
    return f"{format_day(local.date())}, {clock}"


def appointment_text(order) -> str:
    if order.appointment_at is None:
        return requested_text(order)
    return format_moment(order.appointment_at, order.workspace)


def requested_start(order) -> datetime | None:
    """The start of the requested window on the requested day (seller alerts' *Accept*)."""
    window = order.requested_window if isinstance(order.requested_window, dict) else None
    if order.requested_date is None or window is None or parse_time(window.get("start")) is None:
        return None
    return window_start(order.requested_date, window, workspace_zone(order.workspace))


def service_names(order) -> str:
    names = [item.name for item in order.items.all()]
    text = ", ".join(names) or "your booking"
    return text if len(text) <= MAX_SERVICE_NAMES else text[: MAX_SERVICE_NAMES - 1] + "…"
