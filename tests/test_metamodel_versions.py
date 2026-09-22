"""The metamodel in versions: a draft is edited in place, a published version is frozen, a
retired one is kept; the difference between two versions is read, not eyeballed (decision 0015)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.conftest import HIGHER_ED

from ea.backend.organisations import DEFAULT_ORG
from ea.metamodel.loader import pack_to_dict
from ea.models import ConflictError, NotFoundError
from ea.services import MetamodelService, OrganisationService

PUBLISHED = f"{HIGHER_ED}@2026-08-11"


@pytest.fixture
def metamodels(loaded):
    return MetamodelService(loaded)


def test_versions_are_listed_with_their_state_and_who_applies_them(loaded, metamodels):
    (v,) = metamodels.versions()
    assert (v.ref, v.status, v.applied_by) == (PUBLISHED, "published", [DEFAULT_ORG])
    assert v.published_at is not None and v.name == "Higher Education EA Metamodel"
    assert metamodels.resolve(HIGHER_ED) == (HIGHER_ED, "2026-08-11")
    assert metamodels.get(HIGHER_ED).version == "2026-08-11"
    for ref in (f"{HIGHER_ED}@nope", "nope", "nope@1", ""):
        with pytest.raises(NotFoundError):
            metamodels.resolve(ref)


def test_a_published_version_is_frozen(loaded, pack, metamodels):
    loaded.save_pack(pack, "ada")  # the same definition again: nothing happens
    assert len(metamodels.versions()) == 1
    changed = metamodels.get(PUBLISHED)
    changed.element_types[0].description = "edited"
    with pytest.raises(ConflictError, match="frozen"):
        metamodels.save(changed, "ada")
    with pytest.raises(ConflictError):
        loaded.save_pack(changed, "ada")
    assert metamodels.get(PUBLISHED).element_types[0].description != "edited"
    assert metamodels.publish(PUBLISHED, "ada").status == "published"  # publishing again is a no-op
    with pytest.raises(ConflictError, match="retired, not deleted"):
        metamodels.delete(PUBLISHED, "ada")


def test_a_draft_is_edited_in_place_then_published(loaded, metamodels):
    draft = metamodels.draft(PUBLISHED, "ada", notes="a trial")
    today = datetime.now(UTC).date().isoformat()
    assert draft.version == today and draft.status == "draft" and draft.derived_from == PUBLISHED
    assert metamodels.suggest_version(HIGHER_ED) == f"{today}-1"
    with pytest.raises(ConflictError, match="already exists"):
        metamodels.draft(PUBLISHED, "ada", version=today)
    draft.element_types[0].description = "edited on the draft"
    metamodels.save(draft, "ada")
    again = metamodels.get(draft.ref)
    assert again.element_types[0].description == "edited on the draft" and again.notes == "a trial"
    assert pack_to_dict(metamodels.get(PUBLISHED))["element_types"][0]["description"] != "edited on the draft"
    published = metamodels.publish(draft.ref, "ada")
    assert published.status == "published" and published.published_by == "ada"
    metamodels.save(again, "ada")  # the same content as published: nothing to store, nothing refused
    again.element_types[0].description = "edited after publishing"
    with pytest.raises(ConflictError, match="frozen"):
        metamodels.save(again, "ada")
    with pytest.raises(ValueError):
        metamodels.draft(PUBLISHED, "ada", version="not a version!")


def test_retire_and_delete_respect_who_applies_a_version(loaded, metamodels):
    orgs = OrganisationService(loaded, metamodels)
    with pytest.raises(ConflictError, match="applied by default"):
        metamodels.retire(PUBLISHED, "ada")
    draft = metamodels.draft(PUBLISHED, "ada", version="next")
    orgs.apply(DEFAULT_ORG, draft.ref, "ada")
    with pytest.raises(ConflictError, match="applied by default"):
        metamodels.delete(draft.ref, "ada")
    retired = metamodels.retire(PUBLISHED, "ada")
    assert retired.status == "retired"
    with pytest.raises(ConflictError, match="retired"):
        orgs.apply(DEFAULT_ORG, PUBLISHED, "ada")
    with pytest.raises(ConflictError, match="retired"):
        metamodels.publish(PUBLISHED, "ada")
    orgs.create("Other", "ada", pack_ref=draft.ref)
    metamodels.publish(draft.ref, "ada")
    spare = metamodels.draft(draft.ref, "ada", version="spare")
    metamodels.delete(spare.ref, "ada")
    assert {v.version for v in metamodels.versions(HIGHER_ED)} == {"2026-08-11", "next"}
    with pytest.raises(NotFoundError):
        metamodels.get(spare.ref)


def test_the_difference_between_two_versions(loaded, metamodels):
    draft = metamodels.draft(PUBLISHED, "ada", version="diffed")
    draft.element_types = [t for t in draft.element_types if t.id != "location"]
    draft.relationship_types = [r for r in draft.relationship_types if r.target != "location"]
    entity = next(t for t in draft.element_types if t.id == "data_entity")
    entity.description = "changed"
    entity.attributes.append(type(entity.attributes[0])(name="steward"))
    rel = next(
        r for r in draft.relationship_types if r.id == "logical_data_component__encapsulates__data_entity"
    )
    rel.name = "holds"
    draft.common_attributes = [a for a in draft.common_attributes if a.name != "alias"]
    metamodels.save(draft, "ada")
    diff = metamodels.diff(PUBLISHED, draft.ref)
    assert not diff.empty and diff.a == PUBLISHED and diff.b == draft.ref
    by_key = {(e.kind, e.id): e for e in diff.entries}
    assert by_key[("element_type", "location")].change == "removed"
    assert by_key[("element_type", "data_entity")].summary == "description"
    assert by_key[("attribute", "data_entity.steward")].change == "added"
    assert by_key[("attribute", "common.alias")].change == "removed"
    assert [f for f, _, _ in by_key[("relationship_type", rel.id)].fields] == ["name"]
    assert ("pack", HIGHER_ED) not in by_key  # the header did not change
    counts = diff.counts()
    assert counts["element_type"] == {"added": 0, "removed": 1, "changed": 1}
    assert "element types" in diff.summary()
    assert metamodels.diff(PUBLISHED, PUBLISHED).empty


def test_a_loaded_file_with_a_new_version_sits_beside_the_old_one(loaded, pack, metamodels):
    other = metamodels.get(PUBLISHED)
    other.version = "2027-01-01"
    other.status = "draft"
    other.name = "The next edition"
    metamodels.save(other, "ada")
    assert [v.version for v in loaded.list_pack_versions(HIGHER_ED)] == ["2027-01-01", "2026-08-11"]
    assert loaded.load_pack(HIGHER_ED).name == "The next edition"  # the most recently loaded
    assert loaded.load_pack(HIGHER_ED, "2026-08-11").name == pack.name
    assert loaded.load_pack(HIGHER_ED, "nope") is None
