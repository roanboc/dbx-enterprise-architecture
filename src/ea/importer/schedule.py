"""A schedule people can read, kept as the cron expression a trigger takes.

Cron is exact and unreadable. Both matter, and they are not in tension: the picker writes the
expression, the words read it back, and what is stored is still cron — so whatever fires a feed
outside the application (decision 0020) takes it unchanged, and nobody has to reach for a
translator to know when a feed runs.

The picker holds the shapes people actually ask for — every hour, every day, every week on a
day, every month on a date. Anything else is kept exactly as written and shown exactly as
written: **a wrong rendering of a schedule is worse than none**, because it says the wrong time
with the same confidence as a right one.

A zone belongs with an expression rather than being converted away from it. Half past two means
half past two where the person saying it is, which is why a platform scheduler takes a zone
beside its expression and why this does too.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

#: The recurrences the picker offers, coarsest last, as a person reads them.
EVERY = ("hour", "day", "week", "month")

_SUFFIX = {1: "st", 2: "nd", 3: "rd"}

#: Cron numbers the days from Sunday, which is the convention every common scheduler shares.
WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def to_cron(every: str, hour: int = 0, minute: int = 0, weekday: int = 0, day_of_month: int = 1) -> str:
    """The cron expression a picker's choices mean.

    `hour` is ignored for an hourly schedule, which has no hour to keep, and `weekday` and
    `day_of_month` are read only by the recurrence that uses them.
    """
    if every not in EVERY:
        raise ValueError(f"every must be one of {EVERY}, not {every!r}")
    hour, minute = int(hour), int(minute)
    if not (0 <= hour < 24):
        raise ValueError(f"an hour is 0 to 23, not {hour}")
    if not (0 <= minute < 60):
        raise ValueError(f"a minute is 0 to 59, not {minute}")
    if every == "hour":
        return f"{minute} * * * *"
    if every == "day":
        return f"{minute} {hour} * * *"
    if every == "week":
        weekday = int(weekday)
        if not (0 <= weekday < 7):
            raise ValueError(f"a weekday is 0 (Sunday) to 6, not {weekday}")
        return f"{minute} {hour} * * {weekday}"
    day_of_month = int(day_of_month)
    if not (1 <= day_of_month <= 31):
        raise ValueError(f"a day of the month is 1 to 31, not {day_of_month}")
    return f"{minute} {hour} {day_of_month} * *"


def from_cron(cron: str) -> dict[str, Any] | None:
    """The picker's choices an expression means, or None when the picker cannot hold it.

    None is the important answer: it is what tells a screen to show the expression itself
    rather than a picker that would quietly say something else.
    """
    parts = (cron or "").split()
    if len(parts) != 5:
        return None
    minute, hour, day, month, weekday = parts
    if month != "*":
        return None
    out = {"every": "", "hour": 0, "minute": 0, "weekday": 0, "day_of_month": 1}
    if not minute.isdigit() or not 0 <= int(minute) < 60:
        return None
    out["minute"] = int(minute)
    if hour == "*":
        if (day, weekday) != ("*", "*"):
            return None
        out["every"] = "hour"
        return out
    if not hour.isdigit() or not 0 <= int(hour) < 24:
        return None
    out["hour"] = int(hour)
    if day == "*" and weekday == "*":
        out["every"] = "day"
        return out
    if day == "*" and weekday.isdigit() and 0 <= int(weekday) < 7:
        out["every"], out["weekday"] = "week", int(weekday)
        return out
    if weekday == "*" and day.isdigit() and 1 <= int(day) <= 31:
        out["every"], out["day_of_month"] = "month", int(day)
        return out
    return None


def ordinal(n: int) -> str:
    """`1st`, `2nd`, `3rd`, `11th` — the day of the month as a person writes it."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{_SUFFIX.get(n % 10, 'th')}"


def in_words(cron: str) -> str:
    """What an expression says, in a sentence — or the expression itself when it says too much.

    Falling back to the expression is deliberate. Somebody reading `0 */4 * * 1-5` as "every
    four hours on weekdays" would be right; somebody reading it as "every day at 4" would be
    wrong at exactly the moment it mattered, and this cannot tell which reading a sentence
    would produce, so it offers none.
    """
    picked = from_cron(cron)
    if picked is None:
        return cron or ""
    at = f"{picked['hour']:02d}:{picked['minute']:02d}"
    if picked["every"] == "hour":
        if picked["minute"] == 0:
            return "Every hour, on the hour"
        return f"Every hour at {picked['minute']} minutes past"
    if picked["every"] == "day":
        return f"Every day at {at}"
    if picked["every"] == "week":
        return f"Every week on {WEEKDAYS[picked['weekday']]} at {at}"
    return f"Every month on the {ordinal(picked['day_of_month'])} at {at}"


def offset_label(zone: str, at: datetime | None = None) -> str:
    """`(UTC+10:00)` — what a zone is worth right now, so it can be chosen without looking it up.

    It is the current offset, not a fixed one: a zone that keeps daylight saving is worth
    different things in different months, and the label says what it is worth today rather than
    pretending otherwise.
    """
    try:
        here = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return ""
    moment = (at or datetime.now(UTC)).astimezone(here)
    seconds = int((moment.utcoffset() or timedelta()).total_seconds())
    sign = "-" if seconds < 0 else "+"
    hours, minutes = divmod(abs(seconds) // 60, 60)
    return f"(UTC{sign}{hours:02d}:{minutes:02d})"


def zone_label(zone: str, at: datetime | None = None) -> str:
    """A zone as a person picks it: its offset, then its name."""
    prefix = offset_label(zone, at)
    return f"{prefix} {zone}" if prefix else zone


def zone_options(at: datetime | None = None) -> list[dict[str, str]]:
    """Every zone this system knows, offset first, ordered west to east.

    Ordered by offset rather than alphabetically because that is how somebody looks for their
    own: they know roughly where they are before they know how the zone is spelled.
    """
    moment = at or datetime.now(UTC)
    out: list[tuple[str, dict[str, str]]] = []
    for zone in available_timezones():
        prefix = offset_label(zone, moment)
        if not prefix:
            continue
        out.append((prefix + zone, {"value": zone, "label": f"{prefix} {zone}"}))
    return [option for _key, option in sorted(out)]
