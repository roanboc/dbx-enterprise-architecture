"""Branches as overlays: invisible on main, diffed with base versions, merged item by item."""

from __future__ import annotations

import pytest

from ea.backend.branching import MAIN, branch_id_from_name, current_branch, use_branch
from ea.models import ConflictError, Element, NotFoundError, Relationship, ValidationError
from ea.services import BranchService, GraphService, RepositoryService, TargetStateService


@pytest.fixture
def branches(loaded, registry):
    return BranchService(loaded, registry)


def test_branch_ids_come_from_names():
    assert branch_id_from_name("CMS upgrade / phase 2") == "cms-upgrade-/-phase-2"
    with pytest.raises(ValueError):
        branch_id_from_name("main")
    with pytest.raises(ValueError):
        branch_id_from_name("   ")


def test_writes_on_a_branch_are_invisible_on_main(loaded, branches, registry):
    branches.create("Curriculum approval", "ana", work_package="WP-CMS-UPGRADE")
    repo = RepositoryService(loaded, registry)
    with use_branch("curriculum-approval"):
        assert current_branch() == "curriculum-approval"
        e = repo.create_element(
            "physical_application_component",
            "Curriculum Review Board Portal",
            "ana",
            element_id="PAC-CRB",
            description_md="Drafting and approval of units.",
            current_state="proposed",
            target_state="new",
            target_work_package="WP-CMS-UPGRADE",
        )
        assert loaded.get_element("PAC-CRB") is not None
        assert loaded.count_elements() == 48
        # an existing element updated on the branch
        cms = loaded.get_element("PAC-CMS")
        repo.update_element(
            "PAC-CMS", "ana", cms.version, description_md="Upgraded in phase 2.", target_state="change"
        )
        assert loaded.get_element("PAC-CMS").description_md == "Upgraded in phase 2."
        assert [ln.url for ln in loaded.get_links("PAC-CMS")] == [
            "https://example.edu/cmdb/cms"
        ]  # links carried over
        # a relationship added on the branch, and one removed
        rel = repo.add_relationship("processes", "PAC-CRB", "DE-CMS-UNIT-OUTLINE", "ana")
        gone = loaded.relationships_of("PAC-CMS", "out")[0]
        repo.remove_relationship(gone.relationship_id, "ana")
        assert loaded.get_relationship(gone.relationship_id) is None
        assert loaded.get_relationship(rel.relationship_id) is not None
    # back on main nothing moved
    assert current_branch() == MAIN
    assert loaded.get_element("PAC-CRB") is None
    assert loaded.count_elements() == 47
    assert loaded.get_element("PAC-CMS").description_md != "Upgraded in phase 2."
    assert loaded.get_relationship(gone.relationship_id) is not None
    assert loaded.get_relationship(rel.relationship_id) is None
    assert e.element_id == "PAC-CRB"
    b = branches.get("curriculum-approval")
    assert b.changes == 4 and b.status == "open" and b.work_package == "WP-CMS-UPGRADE"


def test_diff_lists_changes_and_flags_conflicts(loaded, branches, registry):
    branches.create("wp2", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("wp2"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="Curriculum Management System v2")
        srs = loaded.get_element("PAC-SRS")
        repo.update_element("PAC-SRS", "ana", srs.version, target_state="change")
        repo.create_element("data_entity", "CAW_Unit_Proposal", "ana", element_id="DE-CAW-PROP")
    # somebody else changes PAC-CMS on main in the meantime
    cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bob", cms.version, description_md="edited on main")
    cs = branches.diff("wp2")
    by_key = {i.key: i for i in cs.items}
    assert cs.counts() == {"added": 1, "changed": 2, "deleted": 0, "conflicts": 1}
    assert by_key["element:PAC-CMS"].conflict and by_key["element:PAC-CMS"].fields_changed == [
        "description_md",
        "name",
    ]
    assert by_key["element:PAC-CMS"].base_version == 1 and by_key["element:PAC-CMS"].main_version == 2
    assert not by_key["element:PAC-SRS"].conflict and by_key["element:PAC-SRS"].fields_changed == [
        "target_state"
    ]
    assert by_key["element:DE-CAW-PROP"].change == "added" and by_key["element:DE-CAW-PROP"].before is None
    rows = branches.item_rows(cs)
    assert {r["key"] for r in rows} == set(by_key)
    assert all(r["include"] for r in rows)
    assert [r["resolution"] for r in rows if r["conflict"]] == ["branch"]


def test_merge_is_per_item_and_closes_only_when_empty(loaded, branches, registry):
    branches.create("wp3", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("wp3"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="CMS v2")
        repo.create_element("data_entity", "CAW_Unit_Proposal", "ana", element_id="DE-CAW-PROP")
        repo.add_relationship("processes", "PAC-CMS", "DE-CAW-PROP", "ana")
        srs = loaded.get_element("PAC-SRS")
        repo.update_element("PAC-SRS", "ana", srs.version, target_state="change")
    cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bob", cms.version, description_md="edited on main")
    cs = branches.diff("wp3")
    rel_key = next(i.key for i in cs.items if i.kind == "relationship")
    # first round: the new entity and its relationship only
    res = branches.merge("wp3", "ana", include={"element:DE-CAW-PROP", rel_key})
    assert sorted(res.applied) == sorted(["element:DE-CAW-PROP", rel_key])
    assert res.remaining == 2 and not res.closed
    assert loaded.get_element("DE-CAW-PROP") is not None
    assert loaded.get_element("DE-CAW-PROP").version == 1
    assert len(loaded.relationships_of("DE-CAW-PROP")) == 1
    assert loaded.get_element("PAC-CMS").name != "CMS v2"
    # second round: everything left; the conflict stays until resolved
    res = branches.merge("wp3", "ana")
    assert res.applied == ["element:PAC-SRS"] and res.remaining == 1 and not res.closed
    assert loaded.get_element("PAC-SRS").target_state == "change"
    # resolve for main: the branch row is dropped, main keeps its edit, the branch closes
    res = branches.merge("wp3", "ana", resolutions={"element:PAC-CMS": "main"})
    assert res.dropped == ["element:PAC-CMS"] and res.remaining == 0 and res.closed
    assert loaded.get_element("PAC-CMS").description_md == "edited on main"
    assert branches.get("wp3").status == "merged"
    with pytest.raises(ConflictError):
        branches.merge("wp3", "ana")
    ops = [(h["op"], h["branch_id"]) for h in loaded.history("DE-CAW-PROP")]
    assert ("insert", "branch:wp3") in ops and ("insert", "wp3") in ops


def test_conflict_resolved_for_branch_overwrites_main(loaded, branches, registry):
    branches.create("wp4", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("wp4"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="CMS v2")
    cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bob", cms.version, name="CMS renamed on main")
    res = branches.merge("wp4", "ana", resolutions={"element:PAC-CMS": "branch"})
    assert res.applied == ["element:PAC-CMS"] and res.closed
    e = loaded.get_element("PAC-CMS")
    assert e.name == "CMS v2" and e.version == 3


def test_abandon_discards_the_overlay(loaded, branches, registry):
    branches.create("wp5", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("wp5"):
        repo.create_element("data_entity", "Throwaway", "ana", element_id="DE-TMP")
    assert branches.get("wp5").changes == 1
    b = branches.abandon("wp5", "ana")
    assert b.status == "abandoned" and b.changes == 0
    assert loaded.get_element("DE-TMP") is None
    with use_branch("wp5"):
        assert loaded.get_element("DE-TMP") is None
    assert [x.branch_id for x in branches.open()] == []


def test_branch_names_are_unique_and_valid(loaded, branches):
    branches.create("wp6", "ana")
    with pytest.raises(ConflictError):
        branches.create("wp6", "ana")
    with pytest.raises(ConflictError):
        branches.create("main", "ana", branch_id="main")
    with pytest.raises(ValueError):
        branches.create("Bad Id", "ana", branch_id="Bad Id")


def test_graph_is_per_branch(loaded, branches, registry):
    graph = GraphService(loaded, registry)
    n_main = graph.graph().number_of_nodes()
    branches.create("wp7", "ana")
    with use_branch("wp7"):
        loaded.insert_element(
            Element("DE-X", "data_entity", "X", current_state="proposed", target_state="new"), "ana"
        )
        loaded.insert_relationship(
            Relationship("r-x", "physical_application_component__processes__data_entity", "PAC-CMS", "DE-X"),
            "ana",
        )
        assert graph.graph().number_of_nodes() == n_main + 1
        assert graph.node("DE-X")["target_state"] == "new"
        assert graph.neighbours("DE-X")["nodes"][0]["element_id"] in ("DE-X", "PAC-CMS")
    assert graph.graph().number_of_nodes() == n_main
    with pytest.raises(NotFoundError):
        graph.node("DE-X")


def test_states_are_validated(loaded, registry):
    repo = RepositoryService(loaded, registry)
    with pytest.raises(ValueError):
        Element("E", "capability", "E", current_state="alive")
    with pytest.raises(ValidationError):
        repo.create_element("capability", "Bad", "ana", target_state="delete")
    with pytest.raises(ValidationError):
        repo.create_element("capability", "Bad", "ana", target_work_package="WP-NOPE")
    cms = loaded.get_element("PAC-CMS")
    e = repo.set_states(
        "PAC-CMS", "ana", cms.version, target_state="change", target_work_package="WP-CMS-UPGRADE"
    )
    assert e.target_state == "change" and e.target_work_package == "WP-CMS-UPGRADE"
    rel = loaded.relationships_of("PAC-CMS", "out")[0]
    r = repo.set_relationship_states(rel.relationship_id, "ana", target_state="keep")
    assert loaded.get_relationship(r.relationship_id).target_state == "keep"


def test_target_state_summary_and_scope(loaded, registry):
    svc = TargetStateService(loaded, registry)
    assert svc.work_package_type() == "work_package"
    assert [w.element_id for w in svc.work_packages()] == ["WP-CMS-UPGRADE"]
    s = svc.summary("WP-CMS-UPGRADE")
    assert s["elements"] >= 1 and s["changes"] >= 1
    assert sum(s["by_target"].values()) == s["elements"]
    ids = svc.scope_ids("WP-CMS-UPGRADE")
    assert ids[0] == "WP-CMS-UPGRADE" and len(ids) == s["elements"] + 1
    everything = svc.summary()
    assert everything["elements"] == 47


def test_a_branch_name_with_nothing_usable_in_it_is_refused_for_what_it_is():
    """Punctuation only is a different mistake from typing 'main', and gets a different answer."""
    with pytest.raises(ValueError, match="letter or a number"):
        branch_id_from_name("!!!")
    with pytest.raises(ValueError, match="other than 'main'"):
        branch_id_from_name("MAIN")


def test_a_closed_branch_is_not_abandoned(loaded, branches):
    """Abandoning a merged branch used to rewrite its status, so the record denied a merge that happened."""
    b = branches.create("Already merged", "ana")
    loaded.set_branch_status(b.branch_id, "merged", "ana")
    with pytest.raises(ConflictError, match="already merged"):
        branches.abandon(b.branch_id, "ana")
    assert loaded.get_branch(b.branch_id).status == "merged"
