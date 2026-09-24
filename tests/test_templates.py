"""Proposal templates (initiative 22): read from the metamodel's own names, declared only where
they differ, kept per organisation, and the ArchiMate reference read completely without a model."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import ARCHIMATE as ARCHIMATE_ID

from ea.agent.proposal import ProposalService, parse_markdown
from ea.backend.branching import use_branch
from ea.backend.organisations import use_org
from ea.config import Settings
from ea.metamodel import Registry, load_pack
from ea.models import ElementFilter, Forbidden, ValidationError
from ea.services import (
    BranchService,
    MetamodelService,
    OrganisationService,
    RepositoryService,
    TargetStateService,
    TemplateService,
    use_role,
)
from ea.services.templates import Reading, check, split_front_matter, starter_templates

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "packs" / "archimate_core" / "proposal-template.md"
HIGHER_ED = ROOT / "packs" / "higher_education" / "proposal-template.md"


def _service(backend, registry) -> ProposalService:
    return ProposalService(
        backend,
        registry,
        RepositoryService(backend, registry),
        BranchService(backend, registry),
        TargetStateService(backend, registry),
        Settings(agent_provider="stub"),
    )


# ------------------------------------------------------------------ reading


def test_front_matter_declares_the_template_and_leaves_the_page():
    decl, body = split_front_matter(REFERENCE.read_text(encoding="utf-8"))
    assert decl is not None and decl.name == "ArchiMate change proposal"
    assert decl.metamodel == ARCHIMATE_ID
    assert body.lstrip().startswith("# Proposal:")
    assert split_front_matter("# A page\n") == (None, "# A page\n")


def test_a_heading_that_names_a_type_types_its_table(registry):
    page = """# Proposal: x

## Physical application components

| Name | Description | Owner |
| ---- | ----------- | ----- |
| Review portal | A portal in which review boards approve unit proposals. | Registrar |
"""
    r = parse_markdown(page, Reading(registry))
    assert [(e.type_label, e.name) for e in r.elements] == [
        ("Physical Application Component", "Review portal")
    ]
    assert r.elements[0].attrs == {"owner": "Registrar"}
    # without the metamodel, the same table has no Type column and nothing types it
    assert parse_markdown(page).elements == []


def test_the_front_matter_declares_only_what_the_template_names_differently(registry):
    page = """---
proposal_template:
  name: Our solution design
  sections:
    Systems: Physical Application Component
  columns:
    System: name
    Summary: description
    Business owner: owner
---
# Proposal: x

## 3.1 Systems

| System | Summary | Business owner |
| ------ | ------- | -------------- |
| Review portal | A portal in which review boards approve unit proposals. | Registrar |
"""
    decl, _ = split_front_matter(page)
    r = parse_markdown(page, Reading(registry, decl))
    assert r.template_name == "Our solution design"
    el = r.elements[0]
    assert (el.type_label, el.name, el.attrs) == (
        "Physical Application Component",
        "Review portal",
        {"owner": "Registrar"},
    )
    assert el.description.startswith("A portal")


def test_check_says_what_it_cannot_place_and_refuses_nothing(registry):
    page = """---
proposal_template:
  name: Rough
  sections:
    Widgets: Spaceship
---
## Things

| Name | Colour |
| ---- | ------ |
| A | red |

## Physical application components

| Name | Colour |
| ---- | ------ |
| B | blue |
"""
    said = "\n".join(check(page, registry))
    assert "'Widgets' is declared as 'Spaceship'" in said
    assert "under 'Things' has no Type column" in said
    assert "column(s) 'Colour'" in said and "ignored" in said


def test_the_starters_are_the_templates_shipped_beside_their_packs(pack):
    found = {s.name: s for s in starter_templates(ROOT / "packs")}
    assert set(found) == {"ArchiMate change proposal", "Higher education change proposal"}
    assert found["ArchiMate change proposal"].pack_id == ARCHIMATE_ID
    assert found["Higher education change proposal"].pack_id == pack.id


# ----------------------------------------------------- kept per organisation


def test_an_organisation_keeps_its_own_templates(loaded, registry):
    templates = TemplateService(loaded, registry)
    # offered before anything is kept: the starter typed in this organisation's metamodel only
    assert [label for _, label, _ in templates.offered()] == ["Higher education change proposal (starter)"]
    doc = HIGHER_ED.read_text(encoding="utf-8").replace(
        "name: Higher education change proposal", "name: Our change proposal"
    )
    with use_role("architect"), pytest.raises(Forbidden):
        templates.save(doc, "arjun")
    with pytest.raises(ValidationError):
        templates.save("# no front matter\n", "ada")
    kept = templates.save(doc, "ada")
    assert kept.name == "Our change proposal" and kept.pack_id == registry.pack.id
    again = templates.save(doc + "\n<!-- revised -->\n", "ada")
    assert again.template_id == kept.template_id and len(templates.list()) == 1  # replaced, not doubled
    copied = templates.add_starter("Higher education change proposal", "ada")
    assert {t.name for t in templates.list()} == {"Our change proposal", "Higher education change proposal"}
    # a kept copy of a starter is offered once, as the organisation's own
    assert [label for _, label, _ in templates.offered()] == [
        "Higher education change proposal",
        "Our change proposal",
    ]
    assert templates.find("our change PROPOSAL").template_id == kept.template_id
    templates.delete(copied.template_id, "ada")
    assert [t.name for t in templates.list()] == ["Our change proposal"]
    assert any(h["entity_id"] == kept.template_id for h in loaded.history(limit=50))


def test_a_proposal_read_with_a_kept_template_names_it(loaded, registry):
    templates = TemplateService(loaded, registry)
    kept = templates.save(HIGHER_ED.read_text(encoding="utf-8"), "ada")
    svc = _service(loaded, registry)
    r = svc.analyse([{"kind": "text", "name": "page", "text": HIGHER_ED.read_text(encoding="utf-8")}])
    assert r.template_id == kept.template_id and r.template_name == "Higher education change proposal"
    # the page's own front matter is enough to find it; naming it on the page is the same
    by_key = svc.analyse(
        [{"kind": "text", "name": "page", "text": "# Proposal: x\n"}], template=kept.template_id
    )
    assert by_key.template_id == kept.template_id


# ------------------------------------------------ the ArchiMate reference

EXISTING = [
    ("driver", "Paper requests are slow", "Service requests arrive on paper forms."),
    ("business_process", "Handle a service request", "Receiving and resolving a customer's request."),
    ("business_process", "Paper intake", "Opening the post and keying in the paper forms."),
    ("application_component", "Case management system", "The system case handlers work in."),
    ("node", "Forms server", "The server that hosts the printable request forms."),
    ("technology_service", "Container hosting", "The managed platform web applications run on."),
]


@pytest.fixture
def archimate_org(backend):
    pack = load_pack(ROOT / "packs" / "archimate_core" / "metamodel.yaml")
    backend.save_pack(pack, "ada")
    orgs = OrganisationService(backend, MetamodelService(backend))
    orgs.create("ArchiMate trial", "ada", org_id="archimate")
    orgs.apply("archimate", f"{ARCHIMATE_ID}@3.2", "ada")
    registry = Registry(pack)
    repo = RepositoryService(backend, registry)
    with use_org("archimate"):
        ids = {
            name: repo.create_element(t, name, "ada", description_md=d).element_id for t, name, d in EXISTING
        }
        repo.add_relationship("serving", ids["Forms server"], ids["Handle a service request"], "ada")
        repo.add_relationship("serving", ids["Forms server"], ids["Paper intake"], "ada")
        repo.add_relationship("serving", ids["Container hosting"], ids["Case management system"], "ada")
    return registry, ids


def test_the_archimate_reference_is_read_completely_without_a_model(backend, archimate_org):
    registry, ids = archimate_org
    page = REFERENCE.read_text(encoding="utf-8").replace(
        "`WP-…` (an existing work package id) or the name of a new one", "Online service requests"
    )
    with use_org("archimate"):
        svc = _service(backend, registry)
        r = svc.analyse([{"kind": "text", "name": "reference", "text": page}])
        assert r.provider == "stub" and r.template_name == "ArchiMate change proposal"
        assert r.pushback == [], r.pushback
        by_name = {e.name: e for e in r.elements}
        assert len(r.elements) == 12 and len(r.relationships) == 11
        portal = by_name["Self-service portal"]
        assert (portal.type_id, portal.action) == ("application_component", "new")
        assert portal.attrs == {"owner": "Digital channels manager", "criticality": "high"}
        assert (
            by_name["Forms server"].action == "link"
            and by_name["Forms server"].element_id == ids["Forms server"]
        )
        assert by_name["Requests are made and tracked online"].type_id == "requirement"
        retire = next(x for x in r.relationships if x.target_state == "decommission")
        assert retire.relationship_id and not retire.issues
        # before Apply the impact says what the page did not: the forms server also serves the
        # paper intake, which the page never mentions and which is left pointing at nothing
        assert [d["other_name"] for d in r.impact["dangling"]] == ["Paper intake"]
        assert "Paper intake" in {x["name"] for x in r.impact["reached"]}
        BranchService(backend, registry).create("Online requests", "ada")
        out = svc.apply(r, "online-requests", "ada")
        assert out["retired"] == [retire.relationship_id] and not out["skipped"]
        with use_branch("online-requests"):
            rel = backend.get_relationship(retire.relationship_id)
            assert rel.target_state == "decommission"
            made = backend.find_elements(ElementFilter(text="Self-service portal"))
            assert made[0].attrs == {"owner": "Digital channels manager", "criticality": "high"}
        stored = backend.list_proposals("online-requests")[0]
        assert stored.result["impact"]["dangling"][0]["other_name"] == "Paper intake"
        assert stored.sources[0]["text"].startswith("---")  # the page as handed in, for the reviewer


def test_a_template_deleted_since_it_was_offered_reads_as_no_template(loaded, registry):
    templates = TemplateService(loaded, registry)
    kept = templates.save(HIGHER_ED.read_text(encoding="utf-8"), "ada")
    templates.delete(kept.template_id, "ada")
    reading, template_id, name = templates.reading(kept.template_id, "# Proposal: x\n")
    assert (template_id, name) == ("", "") and reading.registry is registry
