"""A feed reads the landing schema — the one boundary a source writes to (decision 0020).

Every test here runs on both engines, which is the point of putting the boundary in a table
rather than behind a platform API: what a feed does on Lakebase, it does on DuckDB.
"""

from __future__ import annotations

import pytest

from ea.backend.branching import use_branch
from ea.backend.sql import landing_schema
from ea.importer import Feed, Mapping, run_feed
from ea.importer.feeds import frames_from_landing


def _land(backend, table: str, columns: str, *rows: str) -> None:
    """Put rows where a platform job or a replicated catalogue table would put them.

    The schema is named from the store's own prefix, because a Lakebase test run gets a schema
    of its own — which is exactly the thing a hardcoded name would have hidden."""
    where = f"{landing_schema(backend.schema_prefix)}.{table}"
    backend._execute(f"CREATE TABLE {where} ({columns})")
    for row in rows:
        backend._execute(f"INSERT INTO {where} VALUES ({row})")


def test_a_feed_loads_what_a_source_left_and_then_clears_it(backend, registry):
    _land(
        backend,
        "cmdb_elements",
        "id VARCHAR, type VARCHAR, name VARCHAR",
        "'1001','logical_data_component','From the CMDB'",
        "'1002','data_entity','Another'",
    )
    _land(
        backend,
        "cmdb_relationships",
        "src_id VARCHAR, rel_type VARCHAR, dst_id VARCHAR",
        "'1001','encapsulates','1002'",
    )
    feed = Feed(
        "cmdb",
        tables={"elements": "cmdb_elements", "relationships": "cmdb_relationships"},
        mapping=Mapping(id_prefix="CMDB-"),
    )
    report = run_feed(backend, registry, feed, actor="t")

    assert report.ok and report.elements_loaded == 2 and report.relationships_loaded == 1
    # the mapping applies to a table exactly as it applies to a file
    assert sorted(e.element_id for e in backend.find_elements(limit=10)) == ["CMDB-1001", "CMDB-1002"]
    edge = backend.find_relationships(limit=5)[0]
    assert (edge.src_id, edge.dst_id) == ("CMDB-1001", "CMDB-1002")
    # what was loaded no longer waits
    assert backend.read_landing("cmdb_elements", 10, 0).empty


def test_clearing_happens_after_loading_so_a_stopped_run_loses_nothing(backend, registry):
    """The rows stay until the load has succeeded. A run that stops before clearing repeats
    itself next time, and repeating an idempotent load changes nothing."""
    _land(backend, "src_elements", "id VARCHAR, type VARCHAR, name VARCHAR", "'E1','data_entity','One'")
    feed = Feed("src", tables={"elements": "src_elements"})

    first = run_feed(backend, registry, feed, actor="t")
    assert first.elements_created == 1

    # what a repeat would do, had the clear not happened: nothing new
    _land(backend, "again_elements", "id VARCHAR, type VARCHAR, name VARCHAR", "'E1','data_entity','One'")
    repeat = run_feed(backend, registry, Feed("src", tables={"elements": "again_elements"}), actor="t")
    assert (repeat.elements_created, repeat.elements_unchanged) == (0, 1)
    assert backend.count_elements() == 1


def test_a_failed_load_leaves_the_rows_where_they_are(backend, registry):
    """Clearing is for rows that landed. A load with an error keeps them for the next attempt."""
    _land(
        backend,
        "bad_elements",
        "id VARCHAR, type VARCHAR, name VARCHAR",
        "'E1','no_such_type','One'",
    )
    feed = Feed("src", tables={"elements": "bad_elements"})
    report = run_feed(backend, registry, feed, actor="t")
    assert not report.ok
    assert backend.read_landing("bad_elements", 10, 0).shape[0] == 1  # still waiting


def test_a_feed_reading_a_table_it_does_not_own_leaves_it_alone(backend, registry):
    """A replicated catalogue table is maintained by whatever replicates it: emptying it would
    fight the thing that fills it."""
    _land(backend, "synced_elements", "id VARCHAR, type VARCHAR, name VARCHAR", "'E1','data_entity','One'")
    feed = Feed("synced", tables={"elements": "synced_elements"}, clear_after=False)
    report = run_feed(backend, registry, feed, actor="t")
    assert report.ok and backend.read_landing("synced_elements", 10, 0).shape[0] == 1


def test_a_feed_naming_a_table_that_is_not_there_says_so(backend, registry):
    feed = Feed("src", tables={"elements": "never_created"})
    report = run_feed(backend, registry, feed, actor="t")
    assert [i.code for i in report.issues] == ["no_landing_table"]
    assert report.elements_loaded == 0


def test_a_landing_table_is_read_in_pages(backend, registry, monkeypatch):
    """No single statement asks the store for a whole table (decision 0019)."""
    from ea import capacity

    monkeypatch.setattr(capacity, "READ_CHUNK", 2)
    rows = [f"'E{i}','data_entity','Name {i}'" for i in range(5)]
    _land(backend, "many_elements", "id VARCHAR, type VARCHAR, name VARCHAR", *rows)

    seen: list[int] = []
    original = backend.read_landing

    def counted(table, limit, offset):
        seen.append(offset)
        return original(table, limit, offset)

    monkeypatch.setattr(backend, "read_landing", counted)
    frames = frames_from_landing(backend, Feed("src", tables={"elements": "many_elements"}))
    assert len(frames["elements"][0][1]) == 5  # every row arrives
    assert seen[:3] == [0, 2, 4]  # and it took more than one read to get them


def test_a_landing_table_name_that_is_not_an_identifier_is_refused(backend):
    """A landing table is named by configuration and goes into a statement as a name."""
    with pytest.raises(ValueError, match="not a landing table name"):
        backend.read_landing("elements; DROP TABLE element", 10, 0)
    with pytest.raises(ValueError, match="not a landing table name"):
        backend.clear_landing("x'; DELETE FROM element; --")


def test_the_landing_schema_exists_and_the_store_puts_nothing_in_it(backend):
    """The store creates the schema and never a table in it: what lands there comes from
    outside the application entirely."""
    assert backend.landing_tables() == []


# --------------------------------------------------------- configured feeds


def test_a_feed_configuration_is_stored_and_read_back(backend):
    from ea.models import SourceFeed

    saved = backend.save_feed(
        SourceFeed(
            name="CMDB nightly",
            source_system="cmdb",
            elements_table="cmdb_elements",
            schedule="30 2 * * *",
            schedule_timezone="Australia/Brisbane",
        ),
        "me",
    )
    assert saved.feed_id and saved.created_by == "me"
    read = backend.get_feed(saved.feed_id)
    assert read.name == "CMDB nightly" and read.schedule_timezone == "Australia/Brisbane"
    assert read.writes_to_main  # no branch named

    read.name = "renamed"
    backend.save_feed(read, "someone else")
    again = backend.get_feed(saved.feed_id)
    assert again.name == "renamed"
    assert again.created_by == "me" and again.updated_by == "someone else"

    backend.delete_feed(saved.feed_id, "me")
    assert backend.list_feeds() == []


def test_running_a_configured_feed_writes_to_the_branch_it_names(backend, registry):
    """The branch is the feed's own, not the caller's: a feed configured onto a branch is
    reviewed before it reaches main, whoever presses the button."""
    from ea.backend.branching import MAIN, current_branch
    from ea.importer.feeds import run_configured_feed
    from ea.models import Branch, SourceFeed

    backend.create_branch(Branch(branch_id="wip", name="Work in progress"), "t")
    _land(backend, "src_elements", "id VARCHAR, type VARCHAR, name VARCHAR", "'E1','data_entity','One'")
    feed = backend.save_feed(
        SourceFeed(name="src", source_system="src", elements_table="src_elements", target_branch="wip"),
        "t",
    )

    assert current_branch() == MAIN
    report = run_configured_feed(backend, registry, feed.feed_id, actor="t")
    assert report.ok and report.elements_loaded == 1
    assert current_branch() == MAIN  # the caller is left where they were

    assert backend.get_element("E1") is None  # main did not gain it
    with use_branch("wip"):
        assert backend.get_element("E1").name == "One"


def test_a_run_records_how_it_went_on_the_feed(backend, registry):
    from ea.importer.feeds import run_configured_feed
    from ea.models import SourceFeed

    _land(backend, "src_elements", "id VARCHAR, type VARCHAR, name VARCHAR", "'E1','data_entity','One'")
    feed = backend.save_feed(SourceFeed(name="src", source_system="src", elements_table="src_elements"), "t")
    run_configured_feed(backend, registry, feed.feed_id, actor="t")
    after = backend.get_feed(feed.feed_id)
    assert after.last_run_status == "ok"
    assert after.last_run_at is not None and "elements 1/1 loaded" in after.last_run_summary


def test_running_a_feed_that_is_not_configured_says_so(backend, registry):
    from ea.importer.feeds import run_configured_feed
    from ea.models import NotFoundError

    with pytest.raises(NotFoundError):
        run_configured_feed(backend, registry, "feed-nobody-made", actor="t")


# ------------------------------------------------------- times, where you are


def test_a_schedule_is_shown_in_the_zone_it_was_written_in():
    """A person who says half past two means half past two where they are, so the zone is kept
    with the expression rather than converted away from it."""
    from ea.importer.feeds import schedule_in_words
    from ea.models import SourceFeed

    daily = SourceFeed(name="n", schedule="30 2 * * *", schedule_timezone="Australia/Brisbane")
    assert schedule_in_words(daily) == "Every day at 02:30 (Australia/Brisbane)"

    weekly = SourceFeed(name="n", schedule="31 14 * * 1", schedule_timezone="Australia/Brisbane")
    assert schedule_in_words(weekly) == "Every week on Monday at 14:31 (Australia/Brisbane)"

    # an expression the words cannot hold is shown as written, never guessed at
    odd = SourceFeed(name="n", schedule="0 */4 * * 1-5", schedule_timezone="Australia/Brisbane")
    assert schedule_in_words(odd) == "0 */4 * * 1-5 (Australia/Brisbane)"

    assert "runs when somebody runs it" in schedule_in_words(SourceFeed(name="n"))
    assert schedule_in_words(
        SourceFeed(name="n", schedule="30 2 * * *", schedule_timezone="UTC", enabled=False)
    ).endswith("— disabled")


def test_a_stored_instant_is_read_where_the_reader_is():
    from datetime import datetime

    from ea.importer.feeds import in_zone

    # 16:30 UTC is half past two the next morning in Brisbane
    assert (
        in_zone(datetime(2026, 9, 20, 16, 30), "Australia/Brisbane") == "2026-09-21 02:30 Australia/Brisbane"
    )
    assert in_zone(datetime(2026, 9, 20, 16, 30), "UTC") == "2026-09-20 16:30 UTC"
    assert in_zone(None, "Australia/Brisbane") == ""
    # a zone this system does not know is said plainly rather than crashing a page
    assert "not one this system knows" in in_zone(datetime(2026, 9, 20, 16, 30), "Mars/Olympus")


def test_the_timezone_is_a_setting_and_not_a_place_in_the_code():
    """The repository is generic: where its readers are is configuration, not source."""
    import subprocess

    from ea.config import Settings

    assert Settings().timezone == "UTC"
    # A zone may be named in a comment as an example of what the setting takes; what must not
    # happen is one being used as a value, which is what would make the repository local to a
    # place rather than configured for one.
    found = subprocess.run(
        ["grep", "-rn", "Australia/", "--include=*.py", "src/"], capture_output=True, text=True
    )
    in_code = [
        line for line in found.stdout.splitlines() if not line.split(":", 2)[-1].lstrip().startswith("#")
    ]
    assert in_code == [], "a zone is used as a value in the source:\n" + "\n".join(in_code)
