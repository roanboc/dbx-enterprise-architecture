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

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "proposal-template.md").read_text(encoding="utf-8")

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
    assert len(r.elements) == 5 and len(r.relationships) == 5
    assert r.elements[0].name == "Curriculum Approval Workflow" and r.elements[0].target_state == "new"
    assert r.elements[2].existing_id == "PAC-CMS"
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
    # the architect unticks one relationship and adds a manual element row before applying
    r.relationships[3].include = False
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
    edited = result_from_payload(payload)
    out = svc.apply(edited, "approval-workflow", "ana")
    assert out["work_package_id"] == "WP-CMS-UPGRADE"
    assert len(out["created"]) == 3 and out["linked"] == ["PAC-CMS", "POS-CURR-MGR"]
    assert len(out["relationships"]) == 3 and not out["skipped"]
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
    assert cs.counts()["added"] == 6 and cs.counts()["changed"] == 1
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


def test_fetch_link_refuses_non_http():
    with pytest.raises(ValueError):
        fetch_link("file:///etc/hosts")
