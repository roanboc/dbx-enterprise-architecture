from __future__ import annotations

import pytest
from tests.conftest import HIGHER_ED

from ea.backend.organisations import DEFAULT_ORG
from ea.backend.sql import column_types, qualified
from ea.models import ConflictError, Element, Relationship


def test_pack_round_trips_through_store(backend, pack):
    stored = backend.load_pack(HIGHER_ED)
    assert len(stored.element_types) == len(pack.element_types)
    assert len(stored.relationship_types) == len(pack.relationship_types)
    assert [a.name for a in stored.common_attributes] == [a.name for a in pack.common_attributes]


def test_optimistic_concurrency(backend):
    e = backend.insert_element(Element("X1", "capability", "Cap"), "a")
    e.name = "Cap 2"
    backend.update_element(e, "a")
    stale = backend.get_element("X1")
    stale.version = 1
    with pytest.raises(ConflictError):
        backend.update_element(stale, "b")
    assert backend.get_element("X1").version == 2
    assert len(backend.history("X1")) == 2


def test_upsert_is_idempotent_and_bumps_version(backend):
    ins, upd, _ = backend.upsert_elements(
        [Element("A", "capability", "A"), Element("B", "capability", "B")], "import"
    )
    assert (ins, upd) == (2, 0)
    ins, upd, _ = backend.upsert_elements([Element("A", "capability", "A renamed")], "import")
    assert (ins, upd) == (0, 1)
    assert backend.get_element("A").version == 2
    assert backend.count_elements() == 2


def test_trace_returns_shortest_path(backend):
    for i in ("A", "B", "C", "D"):
        backend.insert_element(Element(i, "capability", i), "t")
    r = "capability__contains__capability"
    backend.insert_relationship(Relationship("r1", r, "A", "B"), "t")
    backend.insert_relationship(Relationship("r2", r, "B", "C"), "t")
    backend.insert_relationship(Relationship("r3", r, "A", "C"), "t")
    backend.insert_relationship(Relationship("r4", r, "C", "D"), "t")
    rows = {row["element_id"]: row for row in backend.trace("A", "out", 5)}
    assert rows["C"]["depth"] == 1 and rows["C"]["path"] == ["A", "C"]
    assert rows["D"]["depth"] == 2 and rows["D"]["rel_path"] == [r, r]
    assert {row["element_id"] for row in backend.trace("D", "in", 5)} == {"A", "B", "C"}


def test_a_walk_visits_a_node_once_however_many_paths_reach_it(backend):
    """A cycle and a hub: the two shapes that make a path enumeration explode.

    Every element of a real estate points at a few shared platforms, and dependencies
    come back on themselves. The walk has to answer with the set of elements reached and
    one shortest path to each, whatever number of paths there are."""
    for i in ("A", "B", "C", "H"):
        backend.insert_element(Element(i, "capability", i), "t")
    r = "capability__contains__capability"
    for n, (src, dst) in enumerate([("A", "B"), ("B", "C"), ("C", "A"), ("A", "H"), ("B", "H"), ("C", "H")]):
        backend.insert_relationship(Relationship(f"r{n}", r, src, dst), "t")

    rows = backend.trace("A", "out", 5)
    by_id = {row["element_id"]: row for row in rows}
    assert len(rows) == len(by_id) == 3  # B, C and the hub, once each — not once per path
    assert set(by_id) == {"B", "C", "H"}
    assert "A" not in by_id  # the cycle does not put the start into its own answer
    assert by_id["H"]["depth"] == 1 and by_id["H"]["path"] == ["A", "H"]
    assert by_id["C"]["depth"] == 2 and by_id["C"]["path"] == ["A", "B", "C"]
    for row in rows:
        assert row["path"][0] == "A" and row["path"][-1] == row["element_id"]
        assert len(row["path"]) == row["depth"] + 1
        assert len(row["rel_path"]) == row["depth"]

    inward = {row["element_id"]: row for row in backend.trace("H", "in", 5)}
    assert set(inward) == {"A", "B", "C"} and all(r["depth"] == 1 for r in inward.values())


def test_the_logical_keys_are_indexed_so_the_database_refuses_a_duplicate(backend):
    """The store has always enforced its keys in Python; now the database holds them too."""
    backend.insert_element(Element("X1", "capability", "Cap"), "a")
    same = backend._element_values(Element("X1", "capability", "Cap again")) + [DEFAULT_ORG]
    with pytest.raises(Exception, match="(?i)unique|duplicate|constraint"):
        backend._insert_rows("element", [same])
    assert backend.count_elements() == 1


def test_a_write_names_its_columns_rather_than_counting_on_their_order(backend):
    """A column a store gained by migration sits physically last, wherever the DDL declares it.

    The change log is rebuilt here in the opposite order to prove the point: a write that
    counted on position would land the actor in the operation's column and say nothing."""
    types = column_types("change_log")
    reordered = ", ".join(f"{name} {types[name]}" for name in reversed(list(types)))
    where = qualified("change_log", backend.schema_prefix)  # an unqualified CREATE would land elsewhere
    backend._execute(f"DROP TABLE {where}")
    backend._execute(f"CREATE TABLE {where} ({reordered})")

    backend.insert_element(Element("X1", "capability", "Cap"), "ada")
    (entry,) = backend.history("X1")
    assert entry["entity_kind"] == "element"
    assert entry["op"] == "insert"
    assert entry["actor"] == "ada"
    assert entry["entity_id"] == "X1"


def test_query_is_read_only(backend):
    backend.insert_element(Element("X1", "capability", "Cap", target_state="merge"), "a")
    assert len(backend.query("select * from element")) == 1
    for bad in (
        "delete from element",
        "select 1; drop table element",
        "update element set name='x'",
        "merge into element using element on 1=1 when matched then delete",
    ):
        with pytest.raises(ValueError):
            backend.query(bad)
    # a word inside a literal is a value: 'merge' is a target state, 'delete' a change-log op
    assert len(backend.query("select element_id from element where target_state = 'merge'")) == 1
    assert len(backend.query("select * from change_log where op = 'delete; drop'")) == 0
