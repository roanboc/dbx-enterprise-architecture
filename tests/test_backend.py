from __future__ import annotations

import pytest

from ea.models import ConflictError, Element, Relationship


def test_pack_round_trips_through_store(backend, pack):
    stored = backend.load_pack("higher_education")
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
    ins, upd = backend.upsert_elements(
        [Element("A", "capability", "A"), Element("B", "capability", "B")], "import"
    )
    assert (ins, upd) == (2, 0)
    ins, upd = backend.upsert_elements([Element("A", "capability", "A renamed")], "import")
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
