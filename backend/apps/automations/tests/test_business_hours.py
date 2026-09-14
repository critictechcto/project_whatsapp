"""Pure business-hours logic: same-day and overnight slots, day wrap and time zones."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from apps.automations.business_hours import (
    Slot,
    is_open,
    is_outside,
    parse_schedule,
    parse_time,
    resolve_time_zone,
    slot_error,
)

IST = ZoneInfo("Asia/Kolkata")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def ist(weekday: int, hour: int, minute: int = 0) -> datetime:
    """A moment in the week of Monday 14 September 2026, India time."""
    moment = datetime(2026, 9, 14 + weekday, hour, minute, tzinfo=IST)
    assert moment.weekday() == weekday
    return moment


def slots(*raw: tuple[int, str, str]) -> list[Slot]:
    return parse_schedule([{"day": day, "start": start, "end": end} for day, start, end in raw])


def test_parse_time():
    assert parse_time("00:00") == time(0, 0)
    assert parse_time("23:59") == time(23, 59)
    for bad in ("24:00", "9:00", "09:60", "0900", "", None, 900):
        with pytest.raises(ValueError):
            parse_time(bad)


@pytest.mark.parametrize(
    ("raw", "valid"),
    [
        ({"day": 0, "start": "09:00", "end": "18:00"}, True),
        ({"day": 6, "start": "22:00", "end": "02:00"}, True),
        ({"day": 7, "start": "09:00", "end": "18:00"}, False),
        ({"day": -1, "start": "09:00", "end": "18:00"}, False),
        ({"day": True, "start": "09:00", "end": "18:00"}, False),
        ({"day": "1", "start": "09:00", "end": "18:00"}, False),
        ({"day": 1, "start": "09:00", "end": "09:00"}, False),
        ({"day": 1, "start": "9:00", "end": "18:00"}, False),
        ({"day": 1, "start": "09:00"}, False),
    ],
)
def test_slot_error(raw, valid):
    assert (slot_error(raw) is None) is valid


def test_parse_schedule_ignores_malformed_entries():
    parsed = parse_schedule(
        [
            {"day": 0, "start": "10:00", "end": "19:00"},
            {"day": 9, "start": "10:00", "end": "19:00"},
            "garbage",
            {"day": 1, "start": "10:00", "end": "10:00"},
        ]
    )

    assert parsed == [Slot(0, time(10), time(19))]


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (ist(MON, 9, 59), False),
        (ist(MON, 10, 0), True),  # start is inclusive
        (ist(MON, 18, 59), True),
        (ist(MON, 19, 0), False),  # end is exclusive
        (ist(TUE, 12, 0), False),  # other day
    ],
)
def test_same_day_slot(moment, expected):
    assert is_open(slots((MON, "10:00", "19:00")), moment, "Asia/Kolkata") is expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (ist(FRI, 21, 59), False),
        (ist(FRI, 22, 0), True),
        (ist(FRI, 23, 59), True),
        (ist(SAT, 0, 0), True),  # past midnight, next day
        (ist(SAT, 1, 59), True),
        (ist(SAT, 2, 0), False),
        (ist(SAT, 23, 0), False),  # the evening part belongs to Friday only
        (ist(THU, 23, 0), False),
        (ist(FRI, 1, 0), False),  # the morning part follows Friday, not Thursday
    ],
)
def test_overnight_slot(moment, expected):
    assert is_open(slots((FRI, "22:00", "02:00")), moment, "Asia/Kolkata") is expected


def test_overnight_slot_wraps_from_sunday_to_monday():
    schedule = slots((SUN, "22:00", "02:00"))

    assert is_open(schedule, ist(SUN, 23, 0), "Asia/Kolkata")
    assert is_open(schedule, ist(MON, 1, 30), "Asia/Kolkata")
    assert not is_open(schedule, ist(MON, 2, 0), "Asia/Kolkata")
    assert not is_open(schedule, ist(SAT, 23, 0), "Asia/Kolkata")


def test_slot_ending_at_midnight_runs_to_the_end_of_the_day():
    schedule = slots((MON, "18:00", "00:00"))

    assert is_open(schedule, ist(MON, 23, 59), "Asia/Kolkata")
    assert not is_open(schedule, ist(TUE, 0, 0), "Asia/Kolkata")
    assert not is_open(schedule, ist(MON, 17, 59), "Asia/Kolkata")


def test_multiple_slots_on_one_day():
    schedule = slots((MON, "09:00", "13:00"), (MON, "14:00", "18:00"))

    assert is_open(schedule, ist(MON, 12, 0), "Asia/Kolkata")
    assert not is_open(schedule, ist(MON, 13, 30), "Asia/Kolkata")
    assert is_open(schedule, ist(MON, 14, 0), "Asia/Kolkata")


def test_moment_is_converted_to_the_workspace_time_zone():
    schedule = slots((MON, "10:00", "19:00"))
    moment = datetime(2026, 9, 14, 4, 30, tzinfo=UTC)  # 10:00 in India

    assert is_open(schedule, moment, "Asia/Kolkata")
    assert not is_open(schedule, moment, "UTC")
    assert not is_open(schedule, moment, "America/New_York")  # 00:30 Monday in New York


def test_time_zone_conversion_crosses_day_boundaries():
    schedule = slots((MON, "00:00", "06:00"))
    sunday_evening_utc = datetime(2026, 9, 13, 20, 0, tzinfo=UTC)  # Monday 01:30 in India

    assert is_open(schedule, sunday_evening_utc, "Asia/Kolkata")
    assert not is_open(schedule, sunday_evening_utc, "UTC")


def test_unknown_or_blank_time_zone_falls_back_to_india():
    assert resolve_time_zone("Mars/Olympus_Mons") == IST
    assert resolve_time_zone("") == IST
    assert resolve_time_zone(None) == IST


def test_is_outside():
    schedule = [{"day": MON, "start": "10:00", "end": "19:00"}]

    assert is_outside(
        enabled=True, schedule=schedule, moment=ist(MON, 20), time_zone="Asia/Kolkata"
    )
    assert not is_outside(
        enabled=True, schedule=schedule, moment=ist(MON, 11), time_zone="Asia/Kolkata"
    )
    # Disabled hours never count as outside, whatever the time.
    assert not is_outside(
        enabled=False, schedule=schedule, moment=ist(MON, 20), time_zone="Asia/Kolkata"
    )
    # Enabled with no slots means always closed.
    assert is_outside(enabled=True, schedule=[], moment=ist(MON, 11), time_zone="Asia/Kolkata")
