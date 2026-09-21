"""A schedule people can read without a cron translator.

Cron is exact and unreadable, so the picker writes it and the words read it back. What is
stored stays a cron expression, because that is what a trigger outside the application takes;
what a person sees is a sentence.
"""

from __future__ import annotations

import pytest

from ea.importer.schedule import EVERY, from_cron, in_words, to_cron, zone_label, zone_options


def test_the_picker_writes_a_cron_expression():
    assert to_cron("day", 2, 30) == "30 2 * * *"
    assert to_cron("hour", 0, 15) == "15 * * * *"
    assert to_cron("week", 14, 31, weekday=1) == "31 14 * * 1"
    assert to_cron("month", 6, 0, day_of_month=5) == "0 6 5 * *"


def test_a_cron_expression_reads_back_into_the_picker():
    """Editing a feed has to put the picker where the stored expression left it."""
    assert from_cron("30 2 * * *") == {
        "every": "day",
        "hour": 2,
        "minute": 30,
        "weekday": 0,
        "day_of_month": 1,
    }
    assert from_cron("31 14 * * 1")["every"] == "week"
    assert from_cron("31 14 * * 1")["weekday"] == 1
    assert from_cron("0 6 5 * *") == {
        "every": "month",
        "hour": 6,
        "minute": 0,
        "weekday": 0,
        "day_of_month": 5,
    }
    assert from_cron("15 * * * *")["every"] == "hour"


def test_an_expression_the_picker_cannot_hold_reads_back_as_nothing():
    """So the screen shows the expression itself rather than a picker that would lie about it."""
    for cron in ("0 */4 * * 1-5", "*/5 * * * *", "0 0 1,15 * *", "not a cron", "", "1 2 3"):
        assert from_cron(cron) is None, cron


def test_a_schedule_is_said_in_words():
    assert in_words("30 2 * * *") == "Every day at 02:30"
    assert in_words("31 14 * * 1") == "Every week on Monday at 14:31"
    assert in_words("0 6 5 * *") == "Every month on the 5th at 06:00"
    assert in_words("0 * * * *") == "Every hour, on the hour"
    assert in_words("15 * * * *") == "Every hour at 15 minutes past"


def test_the_day_of_the_month_is_ordinal_the_way_people_write_it():
    for day, said in (
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (21, "21st"),
        (22, "22nd"),
    ):
        assert said in in_words(f"0 6 {day} * *"), day


def test_an_expression_nobody_can_read_is_shown_as_written_rather_than_guessed_at():
    """A wrong rendering of a schedule is worse than none: it would say the wrong time."""
    assert in_words("0 */4 * * 1-5") == "0 */4 * * 1-5"
    assert in_words("") == ""


def test_the_picker_refuses_a_frequency_it_does_not_have():
    with pytest.raises(ValueError, match="every"):
        to_cron("fortnight", 2, 30)
    assert EVERY == ("hour", "day", "week", "month")


def test_an_hour_or_a_minute_outside_the_clock_is_refused():
    """A picker offers only valid values, but the function is also called from a stored row."""
    for hour, minute in ((24, 0), (-1, 0), (0, 60), (0, -1)):
        with pytest.raises(ValueError):
            to_cron("day", hour, minute)


def test_a_zone_is_offered_with_its_offset_so_it_can_be_chosen_without_looking_it_up():
    options = zone_options()
    assert len(options) > 100
    labels = {o["value"]: o["label"] for o in options}
    assert "Australia/Brisbane" in labels
    assert labels["Australia/Brisbane"].startswith("(UTC+10:00)")
    assert labels["UTC"].startswith("(UTC+00:00)")
    # sorted by offset, so the list reads west to east rather than alphabetically
    offsets = [o["label"][:10] for o in options]
    assert offsets == sorted(offsets)


def test_a_zone_this_system_does_not_know_is_labelled_rather_than_crashing():
    assert zone_label("Mars/Olympus") == "Mars/Olympus"
