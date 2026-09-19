"""Organisations: a partition of one store, one of them the default, each applying one version.

Every read and write of the store honours the current organisation (decision 0014), so
two organisations may hold the same identifiers and never see each other's rows; a
sandbox is a copy of the default's main; applying a version is preceded by the
compatibility check; the roles guard the lot.
"""

from __future__ import annotations

import pytest

from ea.backend.branching import use_branch
from ea.backend.organisations import DEFAULT_ORG, current_org, org_id_from_name, use_org
from ea.metamodel import Registry
from ea.metamodel.loader import pack_to_dict
from ea.models import ConflictError, Element, Forbidden, NotFoundError, Relationship
from ea.services import (
    BranchService,
    MetamodelService,
    OrganisationService,
    RepositoryService,
    ReviewService,
    use_role,
)

PUBLISHED = "higher_education@2026-08-11"


@pytest.fixture
def orgs(loaded):
    return OrganisationService(loaded)


def test_ids_come_from_names():
    assert org_id_from_name("Trial: Lean information / 2026") == "trial-lean-information-2026"
    with pytest.raises(ValueError):
        org_id_from_name("!!!")


def test_the_default_organisation_applies_the_pack(loaded, pack, orgs):
    default = orgs.default()
    assert default is not None and default.org_id == DEFAULT_ORG and default.is_default
    assert default.pack_ref == pack.ref == PUBLISHED
    assert current_org() == DEFAULT_ORG
    assert [o.org_id for o in orgs.list()] == [DEFAULT_ORG]
    assert orgs.get(DEFAULT_ORG).elements == 47
    assert orgs.applied_pack().ref == PUBLISHED


def test_content_is_scoped_by_organisation(loaded, registry, orgs):
    trial = orgs.create("Trial", "ada", description="an empty one")
    assert trial.org_id == "trial" and not trial.is_default and trial.elements == 0
    repo = RepositoryService(loaded, registry)
    with use_org("trial"):
        assert loaded.count_elements() == 0 and loaded.count_relationships() == 0
        assert loaded.get_element("LDC-CURR") is None
        # the same identifier as the default organisation's, held apart from it
        loaded.insert_element(Element("LDC-CURR", "logical_data_component", "Curriculum, tried"), "ada")
        loaded.insert_element(Element("DE-X", "data_entity", "X"), "ada")
        loaded.insert_relationship(
            Relationship("r-x", "logical_data_component__encapsulates__data_entity", "LDC-CURR", "DE-X"),
            "ada",
        )
        assert loaded.get_element("LDC-CURR").name == "Curriculum, tried"
        assert loaded.count_elements() == 2 and len(loaded.relationships_of("LDC-CURR")) == 1
        assert {r["element_id"] for r in loaded.trace("LDC-CURR", "out", 3)} == {"DE-X"}
        assert [h["entity_id"] for h in loaded.history()][:1] == ["r-x"]
        assert loaded.linked_element_ids() == []
    # nothing moved in the default organisation
    assert loaded.get_element("LDC-CURR").name == "Curriculum"
    assert loaded.count_elements() == 47 and loaded.get_element("DE-X") is None
    assert loaded.get_relationship("r-x") is None
    assert all(h["entity_id"] != "r-x" for h in loaded.history(limit=1000))
    assert repo.stats()["elements"] == 47


def test_branches_reviews_and_reviewers_belong_to_their_organisation(loaded, registry, orgs):
    orgs.create("Trial", "ada")
    branches = BranchService(loaded, registry)
    reviews = ReviewService(loaded, registry, branches)
    branches.create("shared name", "ada")
    reviews.set_assignment("data_entity", ["ana"], "ada")
    with use_org("trial"):
        assert branches.list() == [] and reviews.assignments() == {}
        b = branches.create("shared name", "ada")  # the same id, in another organisation
        assert b.branch_id == "shared-name"
        with use_branch(b.branch_id):
            loaded.insert_element(Element("DE-T", "data_entity", "T"), "ada")
        assert branches.get(b.branch_id).changes == 1
        reviews.set_assignment("data_entity", ["trial-steward"], "ada")
        assert reviews.assignments() == {"data_entity": ["trial-steward"]}
    assert branches.get("shared-name").changes == 0
    assert reviews.assignments() == {"data_entity": ["ana"]}
    with use_branch("shared-name"):
        assert loaded.get_element("DE-T") is None


def test_a_sandbox_is_a_copy_of_the_main_content(loaded, registry, orgs):
    ReviewService(loaded, registry, BranchService(loaded, registry)).set_assignment(
        "data_entity", ["ana"], "ada"
    )
    sandbox = orgs.create("Sandbox", "ada", copy_from=DEFAULT_ORG)
    assert (sandbox.elements, sandbox.relationships, sandbox.copied_from) == (47, 99, DEFAULT_ORG)
    assert sandbox.pack_ref == PUBLISHED
    repo = RepositoryService(loaded, registry)
    with use_org("sandbox"):
        cms = loaded.get_element("PAC-CMS")
        assert [ln.url for ln in cms.links] == ["https://example.edu/cmdb/cms"]
        repo.update_element("PAC-CMS", "ada", cms.version, name="CMS, tried")
        assert loaded.list_reviewer_assignments() == {"data_entity": ["ana"]}
        assert loaded.count_elements() == 47
    assert loaded.get_element("PAC-CMS").name == "Curriculum Management System"
    # a copy needs an empty destination
    with pytest.raises(ConflictError):
        loaded.copy_organisation_content(DEFAULT_ORG, "sandbox", "ada")
    with pytest.raises(NotFoundError):
        loaded.copy_organisation_content(DEFAULT_ORG, "nowhere", "ada")


def test_the_default_moves_and_a_deleted_organisation_leaves_nothing(loaded, registry, orgs):
    sandbox = orgs.create("Sandbox", "ada", copy_from=DEFAULT_ORG)
    with pytest.raises(ConflictError):
        orgs.create("Sandbox", "ada")  # the id is taken
    with pytest.raises(ConflictError):
        orgs.delete(DEFAULT_ORG, "ada")  # the default stays
    orgs.set_default("sandbox", "ada")
    assert orgs.default().org_id == "sandbox" and not orgs.get(DEFAULT_ORG).is_default
    orgs.set_default(DEFAULT_ORG, "ada")
    with use_org("sandbox"), use_branch("main"):
        BranchService(loaded, registry).create("wp", "ada")
    orgs.delete(sandbox.org_id, "ada")
    with pytest.raises(NotFoundError):
        orgs.get("sandbox")
    with use_org("sandbox"):
        assert loaded.count_elements() == 0 and loaded.list_branches() == []
    assert loaded.count_elements() == 47
    renamed = orgs.update(DEFAULT_ORG, "ada", name="Sample University", description="the demo")
    assert (renamed.name, renamed.description) == ("Sample University", "the demo")


def test_applying_a_version_checks_the_content_first(loaded, registry, orgs):
    metamodels = MetamodelService(loaded)
    draft = metamodels.draft(PUBLISHED, "ada", version="lean")
    # the draft drops a type the content uses, and makes an attribute the content lacks required
    draft.element_types = [t for t in draft.element_types if t.id != "measure"]
    draft.relationship_types = [r for r in draft.relationship_types if "measure" not in (r.source, r.target)]
    entity = next(t for t in draft.element_types if t.id == "data_entity")
    entity.attributes.append(type(entity.attributes[0])(name="steward", required=True))
    metamodels.save(draft, "ada")
    report = orgs.check(DEFAULT_ORG, draft.ref)
    assert report.elements == 47 and report.relationships == 99
    codes = report.by_code()
    assert codes["unknown_type"] == 2  # the two measures
    assert codes["missing_attribute"] == 7  # every data entity lacks a steward
    assert codes["unknown_relationship_type"] >= 1  # the edges the measures carried
    assert not report.ok
    with pytest.raises(ConflictError, match="error"):
        orgs.apply(DEFAULT_ORG, draft.ref, "ada")
    assert orgs.get(DEFAULT_ORG).pack_ref == PUBLISHED  # refused: nothing applied
    forced = orgs.apply(DEFAULT_ORG, draft.ref, "ada", force=True)
    assert forced.errors and orgs.get(DEFAULT_ORG).pack_ref == draft.ref
    assert orgs.applied_pack().ref == draft.ref
    assert [v.applied_by for v in metamodels.versions("higher_education") if v.version == "lean"] == [
        [DEFAULT_ORG]
    ]
    # the version that fits applies without a word
    clean = orgs.apply(DEFAULT_ORG, PUBLISHED, "ada")
    assert clean.ok and not clean.issues


def test_a_sandbox_applies_the_version_it_is_created_with(loaded, orgs):
    metamodels = MetamodelService(loaded)
    draft = metamodels.draft(PUBLISHED, "ada", version="trial-1", notes="try things")
    trial = orgs.create("Trial", "ada", pack_ref=draft.ref, copy_from=DEFAULT_ORG)
    assert trial.pack_ref == draft.ref
    with use_org("trial"):
        assert orgs.applied_pack().notes == "try things"
        assert Registry(orgs.applied_pack()).pack.status == "draft"
    with pytest.raises(NotFoundError):
        orgs.create("Nowhere", "ada", pack_ref="higher_education@nope")


def test_the_roles_guard_organisations_and_versions(loaded, orgs):
    metamodels = MetamodelService(loaded)
    with use_role("architect"):
        with pytest.raises(Forbidden):
            orgs.create("No", "arjun")
        with pytest.raises(Forbidden):
            orgs.apply(DEFAULT_ORG, PUBLISHED, "arjun")
        with pytest.raises(Forbidden):
            metamodels.draft(PUBLISHED, "arjun")
        with pytest.raises(Forbidden):
            metamodels.publish(PUBLISHED, "arjun")
        assert orgs.check(DEFAULT_ORG, PUBLISHED).ok  # checking is reading
    with use_role("reader"):
        with pytest.raises(Forbidden):
            orgs.set_default(DEFAULT_ORG, "ren")


def test_a_readers_sql_answers_for_the_organisation_and_its_version(loaded, orgs):
    orgs.create("Trial", "ada")
    with use_org("trial"):
        loaded.insert_element(Element("E1", "capability", "One"), "ada")
        assert int(loaded.query("select count(*) as n from element")["n"][0]) == 1
    assert int(loaded.query("select count(*) as n from element")["n"][0]) == 47
    assert int(loaded.query("with c as (select * from element) select count(*) as n from c")["n"][0]) == 47
    assert int(loaded.query("select count(*) as n from meta_element_type")["n"][0]) == 59
    assert int(loaded.query("select count(*) as n from element", scoped=False)["n"][0]) == 48


def test_an_older_store_is_given_its_organisation(backend, pack):
    """Rows from before organisations and versions belong to the default organisation, and the
    default organisation applies the pack most recently loaded."""
    backend.insert_element(Element("OLD-1", "capability", "From before"), "ada")
    backend._execute("UPDATE element SET org_id = NULL")
    backend._execute("UPDATE meta_element_type SET pack_version = NULL")
    backend._execute("UPDATE meta_pack SET status = NULL")
    backend._execute("DELETE FROM organisation")
    backend.init_schema()
    assert backend.get_element("OLD-1") is not None
    default = backend.default_organisation()
    assert default is not None and default.pack_ref == pack.ref
    stored = backend.load_pack(pack.id, pack.version)
    assert stored is not None and len(stored.element_types) == len(pack.element_types)
    assert pack_to_dict(stored)["element_types"] == pack_to_dict(pack)["element_types"]
    assert stored.status == "draft"  # a migrated store's pack was edited in place: it stays editable
