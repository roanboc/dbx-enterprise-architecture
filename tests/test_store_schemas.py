"""The store's tables are grouped into schemas, one per group of the logical data model.

A database somebody opens with a SQL client should show the model rather than seventeen
tables in a heap, and a grant should be possible per group. The grouping is also the one
thing in the schema that cannot be added later without moving data, so a store made before
it is moved on its next start — with its rows.
"""

from __future__ import annotations

import duckdb
import pytest

from ea.backend.duckdb_backend import DuckDBBackend
from ea.backend.sql import DDL, SCHEMA_GROUPS, TABLE_GROUP, qualified, schema_of, schemas

ONE_ROW = (
    "(element_id, type_id, name, status, _version, org_id) "
    "VALUES ('OLD1', 'capability', 'From before', 'approved', 1, 'default')"
)


def test_every_table_is_in_exactly_one_group():
    grouped = [table for tables in SCHEMA_GROUPS.values() for table in tables]
    assert sorted(grouped) == sorted(DDL), "a table in the DDL and not in a group has no schema"
    assert len(grouped) == len(set(grouped)), "a table in two groups would be made twice"
    assert set(TABLE_GROUP) == set(DDL)


def test_the_schemas_are_named_from_the_prefix():
    assert schemas("ea") == [
        "ea_metamodel",
        "ea_content",
        "ea_branch",
        "ea_governance",
        "ea_audit",
        "ea_staging",
    ]
    assert qualified("element", "ea") == "ea_content.element"
    assert qualified("change_log", "demo") == "demo_audit.change_log"


def test_the_staging_schema_is_the_one_the_store_does_not_fill():
    """Every other group names the tables the store makes. Staging names none: what goes there
    is put there from outside, and the contract with a source is the shape of the table
    (decision 0020)."""
    assert SCHEMA_GROUPS["staging"] == []
    assert all(SCHEMA_GROUPS[group] for group in SCHEMA_GROUPS if group != "staging")


def test_each_table_is_made_in_the_schema_of_its_group(backend):
    for table in DDL:
        where = schema_of(table, backend.schema_prefix)
        assert backend._table_exists(where, table), f"{table} is not in {where}"
    assert backend.count_elements() == 0  # and the store reads them without naming a schema


def test_a_store_made_before_the_split_is_grouped_on_its_next_start(tmp_path):
    """The one migration this change needs: the tables move, and the rows come with them."""
    path = tmp_path / "before.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(DDL["element"])  # the old home, every table in `main`
    conn.execute(f"INSERT INTO element {ONE_ROW}")
    conn.close()

    store = DuckDBBackend(path)
    assert store._table_exists("ea_content", "element")
    assert not store._table_exists("main", "element"), "the old home is left empty"
    assert store.get_element("OLD1").name == "From before"
    store.close()


def test_a_prefix_of_its_own_keeps_two_stores_apart(tmp_path):
    one = DuckDBBackend(tmp_path / "shared.duckdb", schema_prefix="left")
    one._execute(f"INSERT INTO {qualified('element', 'left')} {ONE_ROW}")
    other = DuckDBBackend(tmp_path / "shared.duckdb", schema_prefix="right")
    assert other.count_elements() == 0, "the second store reads its own schemas"
    assert one.count_elements() == 1
    one.close()
    other.close()


@pytest.mark.parametrize("table", ["element", "meta_pack", "change_log", "branch_review"])
def test_the_group_of_a_table_is_the_section_it_is_documented_under(table):
    expected = {
        "element": "content",
        "meta_pack": "metamodel",
        "change_log": "audit",
        "branch_review": "governance",
    }
    assert TABLE_GROUP[table] == expected[table]
