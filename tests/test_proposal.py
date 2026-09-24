"""Propose: the template's tables become a resolved change set, pushback names what is missing, apply writes to a branch."""

from __future__ import annotations

from pathlib import Path

import pytest

from ea.agent.proposal import (
    ProposalService,
    fetch_link,
    markdown_tables,
    parse_csv,
    parse_markdown,
    result_from_payload,
)
from ea.backend.branching import use_branch
from ea.config import Settings
from ea.models import ElementFilter, ValidationError
from ea.services import BranchService, RepositoryService, TargetStateService
from ea.views.mermaid import to_mermaid

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "packs" / "higher_education" / "proposal-template.md").read_text(encoding="utf-8")

DOC = """# Proposal: Curriculum approval workflow

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |
| **Proposed by** | An architect |

## Summary

Academic staff draft and approve units in a workflow application that feeds the curriculum system.

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Physical Application Component | Curriculum Review Portal | | A portal in which review boards read and approve unit proposals before publication. | proposed | new |
| Data Entity | CAW_Unit_Proposal | | The record of a proposed unit as it moves through approval, with its outline and outcomes. | proposed | new |
| Physical Application Component | Curriculum Management System | PAC-CMS | | live | change |
| Position | Manager, Curriculum Systems | | | live | keep |
| Capability | Curriculum Development | CAP-CURR-DEV | | | |

## Relationships

| Source | Relationship | Target | Note |
| ------ | ------------ | ------ | ---- |
| Curriculum Review Portal | processes | CAW_Unit_Proposal | |
| Curriculum Review Portal | is source for | CMS to SRS curriculum sync | approved units flow into the sync |
| Manager, Curriculum Systems | owns | Curriculum Review Portal | |
| Lakehouse Platform | stores | CAW_Unit_Proposal | reporting copy |
"""


@pytest.fixture
def svc(loaded, registry):
    return ProposalService(
        loaded,
        registry,
        RepositoryService(loaded, registry),
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
    )


def test_template_tables_parse():
    tables = markdown_tables(TEMPLATE)
    assert [t["heading"] for t in tables][:3] == [
        "Proposal: <title of the change>",
        "Elements",
        "Relationships",
    ]
    r = parse_markdown(TEMPLATE)
    assert len(r.elements) == 6 and len(r.relationships) == 6
    assert r.elements[0].existing_id == "CAP-CURR-DEV"  # the context first: what the change serves
    assert r.elements[1].name == "Curriculum Approval Workflow" and r.elements[1].target_state == "new"
    assert r.elements[3].existing_id == "PAC-CMS"
    assert r.relationships[1].note == "approved units flow into the existing sync"
    assert r.work_package == ""  # the placeholder is not a work package


def test_csv_source_parses_like_a_table():
    r = parse_csv(
        "type,name,existing id,description,current state,target state\nData Entity,X,,A record of X.,proposed,new\n"
    )
    assert (
        len(r.elements) == 1
        and r.elements[0].type_label == "Data Entity"
        and r.elements[0].target_state == "new"
    )


def test_analysis_links_existing_and_adopts_new(svc):
    r = svc.analyse([{"kind": "text", "name": "page", "text": DOC}])
    assert r.provider == "stub" and r.title == "Curriculum approval workflow"
    assert r.work_package == "WP-CMS-UPGRADE" and r.work_package_id == "WP-CMS-UPGRADE"
    by_name = {e.name: e for e in r.elements}
    portal, prop, cms, mgr = (
        by_name["Curriculum Review Portal"],
        by_name["CAW_Unit_Proposal"],
        by_name["Curriculum Management System"],
        by_name["Manager, Curriculum Systems"],
    )
    assert portal.action == "new" and portal.type_id == "physical_application_component" and not portal.issues
    assert prop.action == "new" and prop.type_id == "data_entity"
    assert (
        cms.action == "link"
        and cms.match == "id"
        and cms.element_id == "PAC-CMS"
        and cms.target_state == "change"
    )
    assert mgr.action == "link" and mgr.match == "exact" and mgr.element_id == "POS-CURR-MGR"
    rels = {(x.source, x.target): x for x in r.relationships}
    assert (
        rels[("Curriculum Review Portal", "CAW_Unit_Proposal")].rel_type_id
        == "physical_application_component__processes__data_entity"
    )
    assert rels[("Lakehouse Platform", "CAW_Unit_Proposal")].src_ref == "PTC-LAKEHOUSE"
    assert (
        rels[("Manager, Curriculum Systems", "Curriculum Review Portal")].dst_ref
        == "new:curriculum review portal"
    )
    assert all(not x.issues for x in r.relationships), [x.issues for x in r.relationships]
    assert r.pushback == [] and r.complete


def test_pushback_names_the_minimum(svc):
    doc = DOC.replace(
        "| Data Entity | CAW_Unit_Proposal | | The record of a proposed unit as it moves through approval, with its outline and outcomes. | proposed | new |",
        "| Data Entity | CAW_Unit_Proposal | | | proposed | new |\n| Spaceship | Rocket | | A rocket to the moon, obviously. | live | keep |",
    ).replace("| **Work package** | WP-CMS-UPGRADE |", "| **Work package** | |")
    doc = doc.replace(
        "| Curriculum Review Portal | processes | CAW_Unit_Proposal | |",
        "| Curriculum Review Portal | flies | CAW_Unit_Proposal | |",
    )
    r = svc.analyse([{"kind": "text", "name": "page", "text": doc}])
    text = "\n".join(r.pushback)
    assert "description is missing" in text
    assert "type 'Spaceship' is not in the metamodel" in text
    assert "no relationship 'flies'" in text and "allowed:" in text
    assert "Name the work package" in text
    with pytest.raises(ValidationError):
        svc.apply(r, "any", "ana")


def test_similar_names_are_flagged_not_linked(svc):
    doc = DOC.replace(
        "| Position | Manager, Curriculum Systems | | | live | keep |",
        "| Position | Manager Curriculum System | | The manager. | live | keep |",
    )
    r = svc.analyse([{"kind": "text", "name": "page", "text": doc}])
    mgr = next(e for e in r.elements if e.name.startswith("Manager"))
    assert mgr.action == "new" and mgr.candidates and mgr.candidates[0]["element_id"] == "POS-CURR-MGR"
    assert any("similar element exists" in i for i in mgr.issues)


def test_stub_pushes_back_on_free_text(svc):
    r = svc.analyse(
        [{"kind": "text", "name": "notes", "text": "We want a new approval workflow app that feeds the CMS."}]
    )
    assert r.error and "template" in r.error.lower()
    assert r.pushback


def test_apply_writes_to_the_branch_and_keeps_the_proposal(svc, loaded, registry):
    branches = BranchService(loaded, registry)
    branches.create("Approval workflow", "ana", work_package="WP-CMS-UPGRADE")
    r = svc.analyse([{"kind": "text", "name": "page", "text": DOC}])
    # the architect unticks one relationship and adds a manual element row, with what it joins
    r.relationships[1].include = False
    payload = r.to_dict()
    payload["elements"].append(
        {
            "type": "Interface",
            "name": "Review portal API",
            "description": "The interface the portal exposes to the curriculum system.",
            "current_state": "proposed",
            "target_state": "new",
        }
    )
    for end in ("Curriculum Review Portal", "Curriculum Management System"):
        payload["relationships"].append(
            {"source": end, "relationship": "provides to / uses", "target": "Review portal API"}
        )
    edited = result_from_payload(payload)
    out = svc.apply(edited, "approval-workflow", "ana")
    assert out["work_package_id"] == "WP-CMS-UPGRADE"
    assert len(out["created"]) == 3 and out["linked"] == ["PAC-CMS", "POS-CURR-MGR", "CAP-CURR-DEV"]
    assert len(out["relationships"]) == 5 and not out["skipped"]
    # on the branch: new elements exist with their states; main is untouched
    with use_branch("approval-workflow"):
        portal = next(e for e in loaded.find_elements(ElementFilter(text="Curriculum Review Portal")))
        assert (portal.current_state, portal.target_state, portal.target_work_package) == (
            "proposed",
            "new",
            "WP-CMS-UPGRADE",
        )
        assert portal.origin == "proposal"
        assert loaded.get_element("PAC-CMS").target_state == "change"
        api = next(e for e in loaded.find_elements(ElementFilter(text="Review portal API")))
        assert api.type_id == "interface"
        rel = loaded.relationships_of(portal.element_id, "out")
        assert {x.target_state for x in rel} == {"new"}
    assert not loaded.find_elements(ElementFilter(text="Curriculum Review Portal"))
    cs = branches.diff("approval-workflow")
    # PAC-CMS already carried target 'change' on main, so only the manager's new 'keep' is a changed row
    assert cs.counts()["added"] == 8 and cs.counts()["changed"] == 1
    changed = [i for i in cs.items if i.change == "changed"]
    assert changed[0].entity_id == "POS-CURR-MGR" and changed[0].fields_changed == ["target_state"]
    props = loaded.list_proposals("approval-workflow")
    assert (
        len(props) == 1 and props[0].status == "applied" and props[0].title == "Curriculum approval workflow"
    )
    assert props[0].result["applied"]["created"] == out["created"]


def test_apply_creates_a_new_work_package_when_named(svc, loaded, registry):
    BranchService(loaded, registry).create("wp-new", "ana")
    doc = DOC.replace(
        "| **Work package** | WP-CMS-UPGRADE |", "| **Work package** | Curriculum approval uplift |"
    )
    r = svc.analyse([{"kind": "text", "name": "page", "text": doc}])
    assert r.work_package == "Curriculum approval uplift" and r.work_package_id == ""
    out = svc.apply(r, "wp-new", "ana")
    with use_branch("wp-new"):
        wp = loaded.get_element(out["work_package_id"])
        assert (
            wp.type_id == "work_package"
            and wp.name == "Curriculum approval uplift"
            and wp.current_state == "proposed"
        )
        portal = next(e for e in loaded.find_elements(ElementFilter(text="Curriculum Review Portal")))
        assert portal.target_work_package == wp.element_id


def test_what_the_reader_found_missing_survives_the_resolution(svc):
    """A hosted reader's list of what the sources do not say reaches the architect.

    It used to be written into the pushback and then cleared by the resolution that
    recomputes the pushback, so the architect never read it. It is the reader's own
    finding, not the rule's, so it is kept beside the pushback and does not stop Apply.
    """
    payload = {
        "title": "Curriculum approval workflow",
        "work_package": "WP-CMS-UPGRADE",
        "elements": [
            {
                "type": "Data Entity",
                "name": "CAW_Unit_Proposal",
                "description": "The record of a proposed unit as it moves through approval.",
            }
        ],
        "missing": ["Who is the data steward of CAW_Unit_Proposal?"],
    }
    r = svc.resolve(result_from_payload(payload, "hosted"))
    assert r.missing == ["Who is the data steward of CAW_Unit_Proposal?"]
    assert all("data steward" not in p for p in r.pushback)
    # a re-check from the edited rows carries it, and it is kept with the applied proposal
    again = svc.resolve(result_from_payload(r.to_dict(), "manual"))
    assert again.missing == r.missing


def test_a_revised_proposal_applied_again_updates_rather_than_duplicates(svc, loaded, registry):
    """The second apply of the same page to the same branch finds what the first one created.

    Matching ran against the branch the reader happened to stand on (here `main`), not the
    branch being written to, so every new element of the first apply was new again.
    """
    BranchService(loaded, registry).create("revise", "ana")
    first = svc.apply(svc.analyse([{"kind": "text", "name": "page", "text": DOC}]), "revise", "ana")
    revised = DOC.replace("before publication", "before publication, with a comment trail")
    again = svc.analyse([{"kind": "text", "name": "page", "text": revised}], branch_id="revise")
    portal = next(e for e in again.elements if e.name == "Curriculum Review Portal")
    assert portal.action == "link" and portal.element_id in first["created"]
    second = svc.apply(again, "revise", "ana")
    assert second["created"] == [] and portal.element_id in second["linked"]
    # applied again from a result resolved elsewhere, it still writes nothing twice
    third = svc.apply(svc.analyse([{"kind": "text", "name": "page", "text": DOC}]), "revise", "ana")
    assert third["created"] == []
    with use_branch("revise"):
        found = loaded.find_elements(ElementFilter(text="Curriculum Review Portal"), limit=50)
        assert [e.name for e in found].count("Curriculum Review Portal") == 1


def test_fetch_link_refuses_non_http():
    with pytest.raises(ValueError):
        fetch_link("file:///etc/hosts")


def test_a_revision_names_the_pass_it_revises_and_what_it_no_longer_carries(svc, loaded, registry):
    """Handed to the same branch, a page of the same title is a revision of the last one: it is
    recorded as such, and what the last pass wrote that the page has dropped is listed — never
    deleted, because the architect decides that by unticking it off the branch."""
    BranchService(loaded, registry).create("revise", "ana")
    first = svc.apply(svc.analyse([{"kind": "text", "name": "page", "text": DOC}], "revise"), "revise", "ana")
    dropped = (
        DOC.replace(
            "| Data Entity | CAW_Unit_Proposal | | The record of a proposed unit as it moves through approval, with its outline and outcomes. | proposed | new |\n",
            "",
        )
        .replace("| Curriculum Review Portal | processes | CAW_Unit_Proposal | |\n", "")
        .replace("| Lakehouse Platform | stores | CAW_Unit_Proposal | reporting copy |\n", "")
    )
    again = svc.analyse([{"kind": "text", "name": "page", "text": dropped}], "revise")
    assert again.revises == first["proposal_id"]
    gone = {d["name"] for d in again.no_longer}
    assert "CAW_Unit_Proposal" in gone
    assert any(d["kind"] == "relationship" and "CAW_Unit_Proposal" in d["name"] for d in again.no_longer)
    out = svc.apply(again, "revise", "ana")
    assert out["revises"] == first["proposal_id"] and out["created"] == []
    records = loaded.list_proposals("revise")
    assert [p.revises for p in records] == [first["proposal_id"], ""]  # newest first
    with use_branch("revise"):
        assert loaded.find_elements(ElementFilter(text="CAW_Unit_Proposal"))  # listed, not deleted
    # on main, or under another title, a page revises nothing
    other = svc.analyse(
        [
            {
                "kind": "text",
                "name": "page",
                "text": DOC.replace("Curriculum approval workflow", "Another thing"),
            }
        ],
        "revise",
    )
    assert other.revises == "" and other.no_longer == []


def test_a_revision_updates_what_the_branch_created_and_never_empties_a_field(svc, loaded, registry):
    BranchService(loaded, registry).create("revise", "ana")
    svc.apply(svc.analyse([{"kind": "text", "name": "page", "text": DOC}], "revise"), "revise", "ana")
    main_cms = loaded.get_element("PAC-CMS").description_md
    main_mgr = dict(loaded.get_element("POS-CURR-MGR").attrs)
    revised = DOC.replace(
        "| Type | Name | Existing id | Description | Current state | Target state |",
        "| Type | Name | Existing id | Description | Current state | Target state | Owner |",
    ).replace(
        "| ---- | ---- | ----------- | ----------- | ------------- | ------------ |",
        "| ---- | ---- | ----------- | ----------- | ------------- | ------------ | ----- |",
    )
    revised = (
        revised.replace(
            "before publication. | proposed | new |",
            "before publication, with a comment trail kept on each unit. | proposed | new | Registrar |",
        )
        .replace(
            "| Physical Application Component | Curriculum Management System | PAC-CMS | | live | change |",
            "| Physical Application Component | Curriculum Management System | PAC-CMS | Short. | live | change | Head of Curriculum |",
        )
        .replace(
            "| Position | Manager, Curriculum Systems | | | live | keep |",
            "| Position | Manager, Curriculum Systems | | | live | keep | |",
        )
    )
    svc.apply(svc.analyse([{"kind": "text", "name": "page", "text": revised}], "revise"), "revise", "ana")
    with use_branch("revise"):
        portal = next(e for e in loaded.find_elements(ElementFilter(text="Curriculum Review Portal")))
        assert portal.description_md.endswith("comment trail kept on each unit.")  # created here: revised
        assert portal.attrs.get("owner") == "Registrar"
        cms = loaded.get_element("PAC-CMS")
        assert cms.description_md == main_cms  # main's own text is not replaced by the page's short one
        assert cms.attrs.get("owner") == "Head of Curriculum"
        assert loaded.get_element("POS-CURR-MGR").attrs == main_mgr  # a blank Owner cell set nothing


def test_an_attribute_the_type_does_not_declare_is_pushed_back(svc):
    page = (
        DOC.replace(
            "| Type | Name | Existing id | Description | Current state | Target state |",
            "| Type | Name | Existing id | Description | Current state | Target state | Approval Status |",
        )
        .replace(
            "| ---- | ---- | ----------- | ----------- | ------------- | ------------ |",
            "| ---- | ---- | ----------- | ----------- | ------------- | ------------ | --------------- |",
        )
        .replace("before publication. | proposed | new |", "before publication. | proposed | new | Maybe |")
    )
    r = svc.analyse([{"kind": "text", "name": "page", "text": page}])
    portal = next(e for e in r.elements if e.name == "Curriculum Review Portal")
    assert portal.attrs == {"approval_status": "Maybe"}
    assert any("approval_status" in i and "Maybe" in i for i in portal.issues), portal.issues


def test_a_relationship_is_retired_only_when_it_exists(svc, loaded, registry):
    retire = (
        DOC.replace(
            "| Source | Relationship | Target | Note |\n| ------ | ------------ | ------ | ---- |",
            "| Source | Relationship | Target | Target state | Note |\n| ------ | ------------ | ------ | ------------ | ---- |",
        )
        .replace(
            "| Curriculum Review Portal | processes | CAW_Unit_Proposal | |",
            "| Curriculum Review Portal | processes | CAW_Unit_Proposal | new | |",
        )
        .replace(
            "| Curriculum Review Portal | is source for | CMS to SRS curriculum sync | approved units flow into the sync |",
            "| Curriculum Management System | is source for | CMS to SRS curriculum sync | decommission | replaced |",
        )
        .replace(
            "| Manager, Curriculum Systems | owns | Curriculum Review Portal | |",
            "| Manager, Curriculum Systems | owns | Curriculum Review Portal | new | |",
        )
        .replace(
            "| Lakehouse Platform | stores | CAW_Unit_Proposal | reporting copy |",
            "| Lakehouse Platform | stores | CAW_Unit_Proposal | decommission | never held |",
        )
    )
    r = svc.analyse([{"kind": "text", "name": "page", "text": retire}])
    rels = {x.row: x for x in r.relationships}
    assert rels[2].target_state == "decommission" and rels[2].relationship_id and not rels[2].issues
    assert any("no such relationship to decommission" in i for i in rels[4].issues)
    rels[4].include = False
    # without the lakehouse row the record relates only to the portal: kept, and said why (P9)
    r = svc.resolve(r)
    r, _ = svc.answer(r, "boundary:caw unit proposal", "keep", "the lakehouse will hold a reporting copy")
    assert r.pushback == [], r.pushback
    BranchService(loaded, registry).create("retire", "ana")
    out = svc.apply(result_from_payload(r.to_dict()), "retire", "ana")
    assert out["retired"] == [rels[2].relationship_id]
    with use_branch("retire"):
        assert loaded.get_relationship(rels[2].relationship_id).target_state == "decommission"
    assert loaded.get_relationship(rels[2].relationship_id).target_state != "decommission"  # main untouched


def test_the_change_is_drawn_before_it_exists(svc):
    """New elements have no identifier until Apply, so the view is built from the rows."""
    r = svc.analyse([{"kind": "text", "name": "page", "text": DOC}])
    view = svc.view(r)
    names = {n.name: n for n in view.nodes}
    assert {"Curriculum Review Portal", "CAW_Unit_Proposal", "Curriculum Management System"} <= set(names)
    assert names["Curriculum Review Portal"].target_state == "new" and names["Curriculum Review Portal"].focus
    assert names["Curriculum Management System"].target_state == "change"
    assert names["Curriculum Review Portal"].layer != "other"  # drawn in the pack's notation
    labels = {(e.src, e.dst, e.label) for e in view.edges}
    assert ("new:curriculum review portal", "new:caw unit proposal", "processes") in labels
    drawn = to_mermaid(view, marked=True)
    assert "[not yet created]" in drawn and "[new:" not in drawn  # the placeholder is never shown
    assert "[PAC-CMS]" in drawn
