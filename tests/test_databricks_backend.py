"""The Databricks engine: what differs from DuckDB, proved without a warehouse.

The shared behaviour (every read, write, branch, diff and merge) runs through the
Databricks engine in every test of the suite, over a warehouse played by DuckDB
(`conftest.py`). What is tested here is the engine's own part: the dialect it
writes, the limits it keeps, and what it does when the warehouse falls short.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.conftest import SAMPLE
from tests.fake_warehouse import FakeWarehouseConnection, connect_fake_warehouse

from ea.backend.databricks_backend import BATCH_ROWS, DatabricksBackend, spark_literal, to_delta_ddl
from ea.backend.sql import DDL, MIGRATIONS
from ea.config import Settings
from ea.importer import import_directory
from ea.models import Element, Relationship


@pytest.fixture
def warehouse(pack):
    conn = FakeWarehouseConnection()
    b = DatabricksBackend("/sql/1.0/warehouses/fake", "memory", "main", connect=lambda: conn)
    b.save_pack(pack)
    yield b, conn
    b.close()


def test_a_literal_reads_back_unchanged_on_spark():
    """Spark reads a backslash in a literal as an escape, so the engine doubles it and escapes the
    quote with it too: a doubled quote is two literals side by side on Spark, and the quote is lost."""
    assert spark_literal("C:\\new", "VARCHAR") == "'C:\\\\new'"
    assert spark_literal("it's", "VARCHAR") == "'it\\'s'"
    assert spark_literal(None, "VARCHAR") == "CAST(NULL AS STRING)"
    assert spark_literal(None, "INTEGER") == "CAST(NULL AS INT)"
    assert spark_literal(True, "BOOLEAN") == "TRUE"
    assert spark_literal(7, "INTEGER") == "7"
    assert spark_literal(datetime(2026, 9, 9, 10, 0, 0, 123456), "TIMESTAMP") == (
        "TIMESTAMP '2026-09-09 10:00:00.123456'"
    )
    aware = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    assert spark_literal(aware, "TIMESTAMP") == "TIMESTAMP '2026-09-09 12:00:00'"


def test_the_ddl_is_spelt_in_deltas_types():
    ddl = to_delta_ddl(DDL["element"])
    assert "VARCHAR" not in ddl and "INTEGER" not in ddl
    assert "element_id STRING NOT NULL" in ddl and "_version INT NOT NULL" in ddl
    assert "TIMESTAMP" in ddl and "CREATE TABLE IF NOT EXISTS element" in ddl


def test_json_with_escapes_survives_a_bulk_load(warehouse):
    """A newline inside an attribute is a backslash-n in the stored JSON; on Spark that backslash
    must be doubled in the literal or the JSON comes back broken and the attribute is silently lost."""
    b, _ = warehouse
    e = Element(
        "X1",
        "capability",
        "Bachelor's Degree",
        description_md="A student's award; the vendor's 'next' version",
        attrs={"note": "line one\nline two", "path": "C:\\data"},
    )
    b.upsert_elements([e], "import")
    stored = b.get_element("X1")
    assert stored.name == "Bachelor's Degree"
    assert stored.description_md == "A student's award; the vendor's 'next' version"
    assert stored.attrs == {"note": "line one\nline two", "path": "C:\\data"}


def test_bulk_loads_are_merges_in_batches_without_parameter_markers(warehouse, registry):
    b, conn = warehouse
    report = import_directory(b, registry, SAMPLE, "sample")
    assert report.ok, report.summary()
    merges = [s for s in conn.statements if s.startswith("MERGE INTO")]
    assert merges, "a bulk load lands as MERGE INTO"
    assert all("?" not in s for s in merges), "rows are literals, never markers"
    assert any(s.startswith("MERGE INTO element AS t") for s in merges)
    assert any(s.startswith("MERGE INTO relationship AS t") for s in merges)
    assert b.count_elements() == 47


def test_no_statement_carries_more_markers_than_the_connector_allows(warehouse, registry):
    b, conn = warehouse
    import_directory(b, registry, SAMPLE, "sample")
    ids = [f"E{i}" for i in range(700)]
    b.upsert_elements([Element(i, "capability", i) for i in ids], "t")
    b.upsert_elements([Element(i, "capability", i + " again") for i in ids], "t")  # every id exists now
    assert max(s.count("?") for s in conn.statements) <= 255


def test_a_batch_is_capped(warehouse):
    b, conn = warehouse
    b.upsert_elements([Element(f"B{i}", "capability", f"B{i}") for i in range(BATCH_ROWS * 2 + 1)], "t")
    merges = [s for s in conn.statements if s.startswith("MERGE INTO element")]
    assert len(merges) == 3
    assert b.count_elements() == BATCH_ROWS * 2 + 1


def test_an_older_store_gains_the_columns_that_shipped_later(pack):
    """The migrations run as DESCRIBE then ADD COLUMNS, which is what Delta offers instead of IF NOT EXISTS."""
    conn = FakeWarehouseConnection()
    cur = conn.cursor()
    cur.execute(to_delta_ddl(DDL["element"].replace(",\n            target_note VARCHAR", "")))
    b = DatabricksBackend("/sql/1.0/warehouses/fake", "memory", "main", connect=lambda: conn)
    adds = [s for s in conn.statements if s.startswith("ALTER TABLE")]
    assert adds == ["ALTER TABLE element ADD COLUMNS (target_note STRING)"]
    assert any(s.startswith("DESCRIBE ") for s in conn.statements)
    assert len({t for t, _, _ in MIGRATIONS}) == sum(1 for s in conn.statements if s.startswith("DESCRIBE"))
    b.save_pack(pack)
    b.insert_element(Element("X1", "capability", "Cap", target_note="later"), "a")
    assert b.get_element("X1").target_note == "later"


def test_a_session_the_warehouse_dropped_is_reopened_once_and_the_statement_retried(pack):
    """The platform's failure mode: the connection still says open, the statement is refused with
    the session named as gone; the engine opens a new session and the reader never notices."""
    first = FakeWarehouseConnection()
    second = FakeWarehouseConnection()
    for conn in (first, second):  # the same store behind both sessions
        cur = conn.cursor()
        for ddl in DDL.values():
            cur.execute(to_delta_ddl(ddl))
    opened = [first]

    def open_next():
        opened.append(second)
        return second

    b = DatabricksBackend("/sql/1.0/warehouses/fake", "memory", "main", connect=lambda: first)
    b.save_pack(pack)
    b._open = open_next
    first.fail_with = RuntimeError("[INVALID_HANDLE.SESSION_NOT_FOUND] Invalid SessionHandle: expired")
    assert b.list_packs() == []  # answered by the second session, which holds the tables and no pack
    assert opened == [first, second] and b._conn is second
    assert "SET TIME ZONE 'UTC'" in second.statements, "the new session is prepared like the first"
    b.count_elements()  # no further reconnect
    assert len(opened) == 2


def test_an_error_that_is_not_a_lost_session_is_raised_as_it_is(warehouse):
    b, _ = warehouse
    opened = []
    b._open = lambda: opened.append(1)
    with pytest.raises(Exception, match="no_such_table"):
        b._fetch_all("SELECT * FROM no_such_table")
    assert opened == [], "no reconnect for an ordinary error"


def test_a_warehouse_without_recursive_queries_traces_in_process(warehouse):
    b, conn = warehouse
    for i in ("A", "B", "C", "D"):
        b.insert_element(Element(i, "capability", i), "t")
    r = "capability__contains__capability"
    for rid, s, d in (
        ("r1", "A", "B"),
        ("r2", "B", "C"),
        ("r3", "A", "C"),
        ("r4", "C", "D"),
        ("r5", "D", "A"),
    ):
        b.insert_relationship(Relationship(rid, r, s, d), "t")
    by_sql = b.trace("A", "out", 5)
    assert b._recursive_sql is True

    cursor_class = conn.cursor().__class__
    real_execute = cursor_class.execute
    refused = []

    def refuse_recursion(self, sql, parameters=None):
        if "WITH RECURSIVE" in sql:
            refused.append(sql)
            raise RuntimeError("[PARSE_SYNTAX_ERROR] Syntax error at or near 'RECURSIVE'")
        return real_execute(self, sql, parameters)

    def other_fault(self, sql, parameters=None):
        if "WITH RECURSIVE" in sql:
            raise RuntimeError("[UNSUPPORTED_SUBQUERY_EXPRESSION_CATEGORY] not this")
        return real_execute(self, sql, parameters)

    b._recursive_sql = None
    cursor_class.execute = refuse_recursion
    try:
        by_python = b.trace("A", "out", 5)
        assert b._recursive_sql is False and len(refused) == 1
        assert b.trace("D", "in", 5)
        assert len(refused) == 1, "the engine remembers the refusal and does not try the query again"
        b._recursive_sql = None
        cursor_class.execute = other_fault
        with pytest.raises(RuntimeError, match="UNSUPPORTED_SUBQUERY"):
            b.trace("A", "out", 5)  # another fault is raised, never taken for a missing feature
        assert b._recursive_sql is None
    finally:
        cursor_class.execute = real_execute
    strip = lambda rows: [(x["element_id"], x["depth"], x["path"], x["rel_path"]) for x in rows]  # noqa: E731
    assert strip(by_python) == strip(by_sql)
    assert [x["element_id"] for x in by_python] == ["B", "C", "D"]
    assert by_python[2]["path"] == ["A", "C", "D"]


def test_the_session_enters_the_schema_after_creating_it_and_sets_utc(warehouse):
    b, conn = warehouse
    first = conn.statements[:3]
    assert first == ["CREATE SCHEMA IF NOT EXISTS memory.main", "USE memory.main", "SET TIME ZONE 'UTC'"]
    assert conn.timezone == "UTC"


def test_timestamps_come_back_naive_in_utc(warehouse):
    """The connector hands back zone-aware timestamps once the session has a zone; the store's
    contract is naive UTC, as DuckDB gives it, so the health figures compare like with like."""
    b, conn = warehouse
    assert conn.timezone == "UTC"
    b.insert_element(Element("X1", "capability", "Cap"), "a")
    e = b.get_element("X1")
    assert e.created_at.tzinfo is None
    assert abs((datetime.now(UTC).replace(tzinfo=None) - e.created_at).total_seconds()) < 60
    assert b.history("X1")[0]["changed_at"].tzinfo is None


def test_a_readers_words_and_types_never_spend_the_marker_budget(warehouse):
    b, conn = warehouse
    b.upsert_elements([Element(f"E{i}", "capability", f"Element {i}") for i in range(5)], "t")
    words = " ".join(f"word{i}" for i in range(80))
    types = [f"type_{i}" for i in range(300)] + ["capability"]
    assert len(b.find_elements(text="Element 3", type_id=types)) == 1
    assert b.count_elements(text=words, type_id=types) == 0
    assert max(s.count("?") for s in conn.statements[-2:]) == 0
    assert b.find_elements(text="it's") == [] and "ILIKE '%it\\'s%'" in conn.statements[-1]


def test_settings_name_what_the_engine_needs():
    with pytest.raises(ValueError, match="DATABRICKS_WAREHOUSE_ID"):
        DatabricksBackend.from_settings(Settings(backend="databricks", databricks_catalog="c"))
    with pytest.raises(ValueError, match="EA_CATALOG"):
        DatabricksBackend.from_settings(Settings(backend="databricks", databricks_warehouse_id="abc"))


def test_the_fake_warehouse_reads_literals_as_spark_does():
    conn = connect_fake_warehouse()
    cur = conn.cursor()
    cur.execute("SELECT 'a\\\\b', 'it''s', 'x\\ny'")
    assert cur.fetchall() == [("a\\b", "it's", "x\ny")]
