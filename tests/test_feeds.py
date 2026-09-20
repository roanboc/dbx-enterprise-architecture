"""A feed reads the landing schema — the one boundary a source writes to (decision 0020).

Every test here runs on both engines, which is the point of putting the boundary in a table
rather than behind a platform API: what a feed does on Lakebase, it does on DuckDB.
"""

from __future__ import annotations

import pytest

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
