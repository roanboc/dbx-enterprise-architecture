"""The Feeds page: what it says about where a feed writes, and when it is meant to run.

Two things this page must not get wrong. A feed that writes to main skips the review every
other change goes through, so the page has to show that rather than leave it in a field
nobody opened. And a schedule shown without its zone is a time in somebody else's day.
"""

from __future__ import annotations

from datetime import datetime

from ea.models import SourceFeed
from ea.ui.pages.feeds import feed_row


def _texts(component) -> str:
    """Every string anywhere in a rendered component, flattened."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)
        for attribute in ("label", "description", "title"):
            value = getattr(node, attribute, None)
            if isinstance(value, str):
                out.append(value)

    walk(component)
    return " | ".join(out)


def test_a_feed_that_writes_to_main_says_so_on_the_row():
    """It is the one that lands without anybody reviewing it, so it is the one to show."""
    to_main = feed_row(SourceFeed(name="Reference model", elements_table="ref_elements"), "UTC", True, True)
    assert "→ main" in _texts(to_main)

    to_branch = feed_row(
        SourceFeed(name="CMDB", elements_table="cmdb_elements", target_branch="wip"),
        "UTC",
        True,
        True,
    )
    assert "→ wip" in _texts(to_branch)


def test_a_schedule_is_shown_with_the_zone_it_means():
    feed = SourceFeed(
        name="CMDB",
        elements_table="cmdb_elements",
        schedule="30 2 * * *",
        schedule_timezone="Australia/Brisbane",
    )
    shown = _texts(feed_row(feed, "UTC", True, True))
    assert "02:30 daily Australia/Brisbane" in shown


def test_the_last_run_is_read_where_the_reader_is():
    feed = SourceFeed(
        name="CMDB",
        elements_table="cmdb_elements",
        last_run_at=datetime(2026, 9, 20, 16, 30),
        last_run_status="ok",
    )
    assert "2026-09-21 02:30 Australia/Brisbane" in _texts(feed_row(feed, "Australia/Brisbane", True, True))
    assert "Never run" in _texts(feed_row(SourceFeed(name="n", elements_table="t"), "UTC", True, True))


def test_a_feed_that_keeps_its_landing_tables_is_marked():
    """Because it is the exception: a feed normally empties what it loaded."""
    kept = feed_row(SourceFeed(name="Synced", elements_table="t", clear_after=False), "UTC", True, True)
    assert "keeps its landing tables" in _texts(kept)
    normal = feed_row(SourceFeed(name="Normal", elements_table="t"), "UTC", True, True)
    assert "keeps its landing tables" not in _texts(normal)


def test_a_disabled_feed_is_marked():
    off = feed_row(SourceFeed(name="Paused", elements_table="t", enabled=False), "UTC", True, True)
    assert "disabled" in _texts(off)


def test_the_buttons_are_off_for_a_role_that_may_not_use_them():
    """A reader sees what is configured and can press nothing."""
    row = feed_row(SourceFeed(name="n", elements_table="t"), "UTC", can_run=False, can_configure=False)

    def buttons(node, found=None):
        found = [] if found is None else found
        if isinstance(node, list):
            for item in node:
                buttons(item, found)
            return found
        if type(node).__name__ == "Button":
            found.append(node)
        children = getattr(node, "children", None)
        if children is not None:
            buttons(children, found)
        return found

    every = buttons(row)
    assert every and all(b.disabled for b in every)


def test_the_page_says_which_zone_it_shows_and_that_it_fires_nothing():
    """Saving a cron here makes nothing happen; a page that showed one without saying so would
    imply that it does. And a time without its zone is a time in somebody else's day."""
    from ea.ui.pages.feeds import schedule_notice

    notice = schedule_notice("Australia/Brisbane")
    assert "Australia/Brisbane" in notice
    assert "does not fire one" in notice
    assert "runs a feed on demand" in notice
