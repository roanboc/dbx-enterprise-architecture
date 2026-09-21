"""Branches as overlays: invisible on main, diffed with base versions, merged item by item."""

from __future__ import annotations

import pytest

from ea.backend.branching import MAIN, branch_id_from_name, current_branch, use_branch
from ea.models import ConflictError, Element, Link, NotFoundError, Relationship, ValidationError
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
    # The branch changed the name, main changed the description: main has moved under the row,
    # but the two have not disagreed about anything, so it is stale rather than conflicting.
    cms_item = by_key["element:PAC-CMS"]
    assert cms_item.stale and not cms_item.conflict
    assert cms_item.branch_fields == ["name"] and cms_item.main_fields == ["description_md"]
    assert cms_item.overlapping == []
    assert cs.counts() == {"added": 1, "changed": 2, "deleted": 0, "conflicts": 0}
    assert cms_item.fields_changed == ["description_md", "name"]
    assert cms_item.base_version == 1 and cms_item.main_version == 2
    assert not by_key["element:PAC-SRS"].conflict and by_key["element:PAC-SRS"].fields_changed == [
        "target_state"
    ]
    assert by_key["element:DE-CAW-PROP"].change == "added" and by_key["element:DE-CAW-PROP"].before is None
    rows = branches.item_rows(cs)
    assert {r["key"] for r in rows} == set(by_key)
    assert all(r["include"] for r in rows)
    # Nothing here is a conflict any more, so no row asks for a resolution — but the row
    # main moved under says 'stale', because a reader seeing main's fields in the diff
    # should know why they are there.
    assert [r["resolution"] for r in rows if r["conflict"] == "conflict"] == []
    assert {r["key"]: r["conflict"] for r in rows}["element:PAC-CMS"] == "stale"
    assert {r["key"]: r["disputed"] for r in rows}["element:PAC-CMS"] == ""


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
    # second round: everything left. The branch renamed PAC-CMS while main edited its
    # description — different fields, so both survive and nothing needs resolving.
    res = branches.merge("wp3", "ana")
    assert sorted(res.applied) == ["element:PAC-CMS", "element:PAC-SRS"]
    assert res.remaining == 0 and res.closed
    assert loaded.get_element("PAC-SRS").target_state == "change"
    cms_after = loaded.get_element("PAC-CMS")
    assert cms_after.name == "CMS v2", "the branch's change landed"
    assert cms_after.description_md == "edited on main", "and main's was not reverted"
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


def test_a_partial_merge_never_leaves_a_relationship_without_its_ends(loaded, branches, registry):
    """Merging a relationship without the element it points at would break main.

    The whole-branch merge orders elements before relationships, so it always finds the
    ends. A merge of some rows cannot assume that: ticking the relationship and leaving
    its new element on the branch used to write a row on main pointing at nothing, and
    nothing on the branch could repair it afterwards.
    """
    branches.create("Portal", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("portal"):
        new = repo.create_element("physical_application_component", "Portal", "ana", element_id="PAC-P")
        repo.add_relationship(
            "physical_application_component__processes__logical_data_component",
            "PAC-P",
            "LDC-CURR",
            "ana",
        )
    rel = next(i for i in branches.diff("portal").items if i.kind == "relationship")

    result = branches.merge("portal", "ana", include={rel.key})
    assert result.applied == [], "the relationship was written without its end"
    assert result.held_back == [{"key": rel.key, "reason": "PAC-P is not on main and is not in this merge"}]
    assert loaded.count_relationships() == 99, "main is unchanged"

    # ticked together, both land
    result = branches.merge("portal", "ana", include={rel.key, f"element:{new.element_id}"})
    assert sorted(result.applied) == sorted([rel.key, f"element:{new.element_id}"])
    assert loaded.get_element("PAC-P") is not None and loaded.count_relationships() == 100


def test_a_row_main_deleted_under_the_branch_is_a_conflict_not_a_resurrection(loaded, branches, registry):
    """A branch holding an edit to a row main has since deleted must not put it back silently."""
    branches.create("Edit", "ana")
    repo = RepositoryService(loaded, registry)
    rel = loaded.relationships_of("PAC-CMS", "out")[0]
    with use_branch("edit"):
        repo.set_relationship_states(rel.relationship_id, "ana", target_state="change")
    loaded.delete_relationship(rel.relationship_id, "ana")  # removed on main meanwhile

    item = next(i for i in branches.diff("edit").items if i.entity_id == rel.relationship_id)
    assert item.conflict, "main deleted the row the branch started from"

    result = branches.merge("edit", "ana")
    assert result.applied == [] and "not resolved" in result.reasons()
    assert loaded.get_relationship(rel.relationship_id) is None, "still deleted on main"

    result = branches.merge("edit", "ana", resolutions={item.key: "branch"})
    assert result.applied == [item.key], "put back only because somebody said so"
    assert loaded.get_relationship(rel.relationship_id) is not None


def test_a_closed_branch_refuses_the_writes_it_could_never_merge(loaded, branches, registry):
    """A row written into a merged branch can reach neither main nor an abandon: it is lost."""
    from ea.models import Forbidden

    branches.create("Done", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("done"):
        repo.create_element("physical_application_component", "Landed", "ana", element_id="PAC-L")
    branches.merge("done", "ana")
    assert branches.get("done").status == "merged"

    with use_branch("done"), pytest.raises(Forbidden, match="closed branch is history"):
        repo.create_element("physical_application_component", "After the merge", "ana")


def test_a_conflict_arrives_unresolved_rather_than_set_to_overwrite_main(loaded, branches, registry):
    """The merge grid defaulted every conflict to 'take the branch'.

    That made overwriting somebody else's work the thing that happens when nobody looks at
    the row. A conflict now arrives with no resolution, and the merge holds it back saying so.
    """
    branches.create("Clash", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("clash"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, description_md="The branch's words.")
    main_cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bo", main_cms.version, description_md="Main's words.")

    rows = branches.item_rows(branches.diff("clash"))
    row = next(r for r in rows if r["entity_id"] == "PAC-CMS")
    assert row["conflict"] == "conflict" and row["resolution"] == "", "no resolution is chosen for anybody"

    result = branches.merge("clash", "ana")
    assert result.applied == [] and "not resolved" in result.reasons()
    assert loaded.get_element("PAC-CMS").description_md == "Main's words.", "main is untouched"


def test_two_branches_editing_different_fields_do_not_conflict(loaded, branches, registry):
    """The case that cost an architect their work: two people, one element, two fields.

    Ana rewrites a description, Bo sets a target state. Whoever merged second used to find
    a conflict — the version had moved — and resolving it for the branch wrote their whole
    row, reverting the first one's edit. Neither of them ever disagreed about anything.
    """
    repo = RepositoryService(loaded, registry)
    branches.create("ana", "ana")
    branches.create("bo", "bo")
    with use_branch("ana"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, description_md="Ana's description.")
    with use_branch("bo"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "bo", cms.version, target_note="Bo's note")
    branches.merge("ana", "ana")

    item = branches.diff("bo").items[0]
    assert item.stale, "main did move under Bo's row"
    assert not item.conflict, "but the two never touched the same field"
    assert item.branch_fields == ["target_note"] and item.main_fields == ["description_md"]

    result = branches.merge("bo", "bo")
    assert result.applied == ["element:PAC-CMS"] and result.closed
    after = loaded.get_element("PAC-CMS")
    assert after.target_note == "Bo's note", "Bo's change landed"
    assert after.description_md == "Ana's description.", "and Ana's was not reverted"


def test_one_field_in_dispute_is_settled_field_by_field(loaded, branches, registry):
    """Where both sides did move the same field, the choice is per field rather than per row."""
    repo = RepositoryService(loaded, registry)
    branches.create("ana", "ana")
    branches.create("bo", "bo")
    with use_branch("ana"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, description_md="Ana's description.")
    with use_branch("bo"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element(
            "PAC-CMS", "bo", cms.version, description_md="Bo's description.", target_note="Bo's note"
        )
    branches.merge("ana", "ana")

    item = branches.diff("bo").items[0]
    assert item.conflict and item.overlapping == ["description_md"]
    assert "target_note" in item.branch_fields, "Bo changed something nobody else did"

    # undecided: the row stays put and says which field is waiting
    result = branches.merge("bo", "bo", resolutions={"element:PAC-CMS": {}})
    assert result.applied == [] and "no decision for description_md" in result.reasons()

    # decided: main keeps its description, Bo's target state still lands
    result = branches.merge("bo", "bo", resolutions={"element:PAC-CMS": {"description_md": "main"}})
    assert result.applied == ["element:PAC-CMS"]
    after = loaded.get_element("PAC-CMS")
    assert after.description_md == "Ana's description." and after.target_note == "Bo's note"


def test_taking_the_branch_for_every_disputed_field_is_still_whole_row_behaviour(loaded, branches, registry):
    """The old two-valued resolution still means what it always meant."""
    repo = RepositoryService(loaded, registry)
    branches.create("ana", "ana")
    branches.create("bo", "bo")
    with use_branch("ana"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="Ana's name")
    with use_branch("bo"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "bo", cms.version, name="Bo's name")
    branches.merge("ana", "ana")
    branches.merge("bo", "bo", resolutions={"element:PAC-CMS": "branch"})
    assert loaded.get_element("PAC-CMS").name == "Bo's name"


def test_a_row_with_no_base_kept_is_still_treated_as_a_whole_row_conflict(loaded, branches, registry):
    """A branch written before the base row was kept must not merge on a guess.

    Without the base, nothing can prove which side moved which field, so the old rule
    stands: a version that moved is a conflict over everything the branch touched.
    """
    repo = RepositoryService(loaded, registry)
    branches.create("old", "ana")
    with use_branch("old"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="Branch name")
    # as an older store would have it: the row is there, the base is not
    loaded._execute(  # noqa: SLF001
        "UPDATE branch_element SET base_row = NULL WHERE branch_id = ? AND element_id = ?",
        ["old", "PAC-CMS"],
    )
    cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bob", cms.version, description_md="Main's description.")

    item = branches.diff("old").items[0]
    assert item.conflict and item.base is None
    assert branches.merge("old", "ana").applied == [], "it will not merge without a decision"


def test_a_branch_delete_notices_that_main_moved(loaded, branches, registry):
    """Deleting a row main has been editing is a disagreement about the whole row.

    The first field-level merge treated a delete as changing no field, so it disagreed with
    nothing and applied without a decision — taking main's edit with it.
    """
    repo = RepositoryService(loaded, registry)
    branches.create("cut", "ana")
    rel = loaded.relationships_of("PAC-CMS", "out")[0]
    with use_branch("cut"):
        repo.remove_relationship(rel.relationship_id, "ana")
    repo.set_relationship_states(rel.relationship_id, "bob", target_note="Main's plan")

    item = branches.diff("cut").items[0]
    assert item.change == "deleted" and item.conflict, "main wrote to the row being deleted"
    assert branches.merge("cut", "ana").applied == []
    assert loaded.get_relationship(rel.relationship_id) is not None, "main's row survives"

    # asked for plainly, the delete goes through
    result = branches.merge("cut", "ana", resolutions={item.key: "branch"})
    assert result.applied == [item.key]
    assert loaded.get_relationship(rel.relationship_id) is None


def test_a_branch_row_that_changed_nothing_does_not_revert_main(loaded, branches, registry):
    """Setting links alone puts a copy of main's row on the branch; it must stay a copy.

    That row changes no field, so it was not a conflict, so it was ticked by default — and
    merging it wrote a stale copy of main over everything main had done since.
    """
    repo = RepositoryService(loaded, registry)
    branches.create("links", "ana")
    with use_branch("links"):
        loaded.set_links("PAC-CMS", [Link("PAC-CMS", "https://example.edu/cmdb/cms")], "ana")
    cms = loaded.get_element("PAC-CMS")
    repo.update_element("PAC-CMS", "bob", cms.version, description_md="Main's words.")

    branches.merge("links", "ana")
    assert loaded.get_element("PAC-CMS").description_md == "Main's words."


def test_main_keeps_the_links_a_branch_never_touched(loaded, branches, registry):
    """A branch carries a copy of main's links from the moment it touches the element."""
    repo = RepositoryService(loaded, registry)
    branches.create("note", "ana")
    with use_branch("note"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, target_note="Branch note")
    loaded.set_links(
        "PAC-CMS",
        [
            Link("PAC-CMS", "https://example.edu/cmdb/cms"),
            Link("PAC-CMS", "https://example.edu/new"),
        ],
        "bob",
    )

    branches.merge("note", "ana")
    assert loaded.get_element("PAC-CMS").target_note == "Branch note", "the branch's field landed"
    assert len(loaded.get_links("PAC-CMS")) == 2, "and main's second link was not reverted"


def test_a_branch_that_did_change_the_links_still_writes_them(loaded, branches):
    branches.create("relink", "ana")
    with use_branch("relink"):
        loaded.set_links("PAC-CMS", [Link("PAC-CMS", "https://example.edu/branch")], "ana")
    branches.merge("relink", "ana")
    assert [ln.url for ln in loaded.get_links("PAC-CMS")] == ["https://example.edu/branch"]


def test_a_mapping_cannot_settle_a_row_that_has_no_disputed_field(loaded, branches, registry):
    """A row main deleted is a whole-row decision; a per-field mapping used to silently drop it."""
    repo = RepositoryService(loaded, registry)
    branches.create("gone", "ana")
    rel = loaded.relationships_of("PAC-CMS", "out")[0]
    with use_branch("gone"):
        repo.set_relationship_states(rel.relationship_id, "ana", target_note="Branch note")
    loaded.delete_relationship(rel.relationship_id, "bob")

    item = branches.diff("gone").items[0]
    assert item.conflict and item.overlapping == []
    result = branches.merge("gone", "ana", resolutions={item.key: {"target_note": "branch"}})
    assert result.applied == [] and result.dropped == []
    assert "whole row" in result.reasons(), "and it says which decision it wants"


def test_an_import_onto_a_branch_keeps_what_the_branch_started_from(loaded, branches, registry):
    """`_replace_rows` names its columns, and one left out comes back empty."""
    repo = RepositoryService(loaded, registry)
    branches.create("fed", "ana")
    with use_branch("fed"):
        cms = loaded.get_element("PAC-CMS")
        repo.update_element("PAC-CMS", "ana", cms.version, name="Branch name")
        loaded.upsert_elements([loaded.get_element("PAC-CMS")], "ana")
    assert branches.diff("fed").items[0].base is not None
