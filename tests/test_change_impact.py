"""The change impact (DOBJ3.10): what a change set touches beyond itself, read from main."""

from __future__ import annotations

from ea.backend.branching import use_branch
from ea.services import BranchService, ChangeImpactService, ChangeInput, RepositoryService


def test_what_a_decommission_reaches_and_leaves_dangling(loaded, registry):
    impact = ChangeImpactService(loaded, registry).assess(
        ChangeInput(
            changed={"PAC-CMS": "decommission"},
            named={"PAC-CMS"},
            touched_types=["physical_application_component"],
        )
    )
    assert [c["element_id"] for c in impact.changed] == ["PAC-CMS"]
    reached = {r["element_id"]: r for r in impact.reached}
    # one step away upstream and downstream, and two steps along one direction
    assert reached["INT-CMS-SRS"]["depth"] == 1 and reached["PTC-RDBMS"]["direction"] == "in"
    assert reached["DE-SRS-COURSE"]["depth"] == 2 and reached["DE-SRS-COURSE"]["path"] == [
        "processes",
        "encapsulates",
    ]
    # a path keeps to one direction: a sibling realised by the same platform is not reached
    assert "PAC-SRS" not in reached
    assert all(r["via"] == "PAC-CMS" and r["path"] for r in impact.reached)
    # every relationship of PAC-CMS on main is left pointing at an element that is going
    held = {r.relationship_id for r in loaded.relationships_of("PAC-CMS", "both")}
    assert {d["relationship_id"] for d in impact.dangling} == held
    assert impact.reviewers == [
        {
            "type_id": "physical_application_component",
            "type": "Physical Application Component",
            "reviewers": [],
        }
    ]
    assert not impact.quiet


def test_a_relationship_the_change_retires_is_not_dangling_and_a_named_element_is_not_reached(
    loaded, registry
):
    rels = loaded.relationships_of("PAC-CMS", "both")
    keep_out = rels[0]
    other = keep_out.dst_id if keep_out.src_id == "PAC-CMS" else keep_out.src_id
    impact = ChangeImpactService(loaded, registry).assess(
        ChangeInput(
            changed={"PAC-CMS": "decommission"},
            retired_relationships={keep_out.relationship_id},
            named={"PAC-CMS", other},
        )
    )
    assert keep_out.relationship_id not in {d["relationship_id"] for d in impact.dangling}
    assert other not in {r["element_id"] for r in impact.reached}


def test_a_new_element_connected_to_nothing_that_exists_is_named(loaded, registry):
    change = ChangeInput(
        new=[
            {"ref": "new:a", "name": "A", "type_id": "data_entity"},
            {"ref": "new:b", "name": "B", "type_id": "data_entity"},
            {"ref": "new:c", "name": "C", "type_id": "data_entity"},
        ],
        # a and b only know each other; c reaches something that exists
        links=[("new:a", "new:b"), ("new:c", "PAC-CMS")],
    )
    impact = ChangeImpactService(loaded, registry).assess(change)
    assert [i["name"] for i in impact.isolated] == ["A", "B"]


def test_a_branch_is_assessed_from_its_change_set(loaded, registry):
    BranchService(loaded, registry).create("retire-cms", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("retire-cms"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, target_state="decommission")
        repo.create_element("data_entity", "Orphan record", "ana", description_md="Nothing points here yet.")
    impact = ChangeImpactService(loaded, registry).of_branch("retire-cms")
    assert [c["element_id"] for c in impact.changed] == ["PAC-CMS"]
    assert impact.dangling and [i["name"] for i in impact.isolated] == ["Orphan record"]
    assert {r["type_id"] for r in impact.reviewers} == {"physical_application_component", "data_entity"}


def test_the_assessment_is_bounded(loaded, registry, monkeypatch):
    monkeypatch.setattr(ChangeImpactService, "MAX_REACHED", 3)
    impact = ChangeImpactService(loaded, registry).assess(ChangeInput(changed={"PAC-CMS": "change"}))
    assert len(impact.reached) == 3 and impact.truncated
