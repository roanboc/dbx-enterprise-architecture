from __future__ import annotations

import pytest

from ea.models import Link, ValidationError


def test_element_detail_labels_both_directions(repo):
    d = repo.element_detail("LDC-CURR")
    out = {(r["label"], r["other"].element_id) for r in d["outgoing"]}
    inc = {(r["label"], r["other"].element_id) for r in d["incoming"]}
    assert ("encapsulates", "DE-SRS-COURSE") in out
    assert ("is processed by", "PAC-SRS") in inc


def test_create_update_and_relate(repo):
    e = repo.create_element(
        "Information Asset",
        "Timetables",
        "tester",
        description_md="# Timetables",
        attrs={"confidentiality_risk_rating": "Low"},
    )
    assert e.element_id.startswith("IA-") and e.version == 1
    e = repo.update_element(
        e.element_id,
        "tester",
        e.version,
        description_md="edited",
        links=[Link(e.element_id, "https://x", "x")],
    )
    assert e.version == 2 and e.links[0].url == "https://x"
    rel = repo.add_relationship("categorises", "LDC-CURR", e.element_id, "tester")
    assert rel.rel_type_id == "logical_data_component__categorises__information_asset"
    with pytest.raises(ValidationError):
        repo.add_relationship("owns", "DE-SRS-COURSE", e.element_id, "tester")
    with pytest.raises(ValidationError):
        repo.create_element("nope", "x", "tester")


def test_impact_and_completeness(graph):
    res = graph.impact("DE-SRS-COURSE-OFFERING", 3)
    up = {r["element_id"] for r in res["upstream"]}
    assert {"LDC-CURR", "PAC-SRS", "PTC-RDBMS", "WP-CMS-UPGRADE"} <= up
    assert {r["element_id"] for r in res["downstream"]} >= {"DP-CURR-HEALTH", "MSR-OUTLINE-COMPLETENESS"}
    assert res["completeness"]["declared"] >= 5
    assert res["completeness"]["populated"] == res["completeness"]["declared"]


def test_neighbours_and_cytoscape(graph):
    sub = graph.neighbours("POS-DATA-GOV", 1)
    ids = {n["element_id"] for n in sub["nodes"]}
    assert {"POS-DATA-GOV", "ORG-DAU", "IA-COURSE-CAT", "IA-STUDENT-ENROL"} <= ids
    els = graph.cytoscape_elements(sub)
    assert any("source" in el["data"] for el in els) and any(el["data"].get("centre") for el in els)


def test_the_same_edge_is_never_written_twice(repo, loaded):
    """An edge added by hand after it arrived from a tool is the edge the model already holds."""
    existing = loaded.relationships_of("PAC-CMS", "out")[0]
    before = loaded.count_relationships()
    again = repo.add_relationship(
        existing.rel_type_id,
        existing.src_id,
        existing.dst_id,
        "ana",
        qualifier=existing.qualifier,
        origin="user",
    )
    assert again.relationship_id == existing.relationship_id
    assert loaded.count_relationships() == before


def test_not_found_reads_as_a_sentence():
    """The message is shown to people — on the command line and beside a refused row."""
    from ea.models import NotFoundError

    assert str(NotFoundError("DE-NOPE")) == "no element with id DE-NOPE"
    assert str(NotFoundError("wp9", "branch")) == "no branch with id wp9"
