"""The metamodels the repository ships, and starting an organisation on one.

`packs/` is data, so the catalogue is whatever that directory holds: nothing here and nothing
in `src/` names a framework (principle `P5`). It is also not part of the installed wheel, so
finding nothing has to be an ordinary answer rather than a failure — that is what most of
these cover.
"""

from __future__ import annotations

import pytest
from tests.conftest import ARCHIMATE, HIGHER_ED

from ea.config import ROOT
from ea.metamodel.catalogue import starters
from ea.models import ConflictError, Forbidden, NotFoundError
from ea.services import OrganisationService
from ea.services.roles import use_role

SHIPPED = ROOT / "packs"


@pytest.fixture
def orgs(loaded):
    return OrganisationService(loaded)


# ------------------------------------------------------------------------- the catalogue
def test_the_shipped_packs_are_found_and_read_from_their_own_headers():
    found = starters(SHIPPED)
    assert {s.pack_id for s in found} == {HIGHER_ED, ARCHIMATE}
    for s in found:
        assert s.name and s.version and s.status
        assert s.element_types > 0 and s.relationship_types > 0
        assert s.path.name == "metamodel.yaml"
        assert s.ref == f"{s.pack_id}@{s.version}"


def test_the_catalogue_is_ordered_by_name_so_the_list_does_not_move():
    names = [s.name for s in starters(SHIPPED)]
    assert names == sorted(names, key=str.lower)


def test_a_starter_is_keyed_the_way_it_will_be_stored():
    """So the page can tell whether the store already holds one without loading the file."""
    from ea.metamodel import load_pack

    for s in starters(SHIPPED):
        assert load_pack(s.path).id == s.pack_id


def test_a_directory_that_is_not_there_is_an_empty_catalogue_not_an_error(tmp_path):
    """A wheel install carries no `packs/`, and a page that raised would be unusable there."""
    assert starters(tmp_path / "nothing" / "here") == []
    assert starters(tmp_path) == []


def test_a_file_that_is_not_a_pack_is_skipped_and_the_rest_survive(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    (good / "metamodel.yaml").write_text("pack:\n  name: A Good One\n  version: '1'\n")
    for name, text in (
        ("broken", "pack: [this is not a mapping\n"),
        ("empty", ""),
        ("nameless", "pack: {}\n"),
    ):
        d = tmp_path / name
        d.mkdir()
        (d / "metamodel.yaml").write_text(text)
    found = starters(tmp_path)
    assert [s.name for s in found] == ["A Good One"]


def test_a_pack_with_no_identifier_still_offers_a_stable_one(tmp_path):
    d = tmp_path / "mine"
    d.mkdir()
    (d / "metamodel.yaml").write_text("pack:\n  name: My Own Framework\n  version: '1'\n")
    once = starters(tmp_path)[0].pack_id
    assert once == starters(tmp_path)[0].pack_id


# --------------------------------------------------------------------- starting from one
def test_starting_from_a_starter_makes_a_new_empty_organisation(orgs, loaded):
    before = {o.org_id for o in orgs.list()}
    with use_role("admin"):
        org = orgs.start_from(ARCHIMATE, "ArchiMate trial", "ada")
    assert org.org_id not in before
    assert org.pack_id == ARCHIMATE, "it applies the starter"
    assert org.elements == 0 and org.relationships == 0, "and it starts with nothing in it"


def test_the_organisation_the_caller_is_in_is_untouched(orgs):
    """Content typed against one framework does not fit another, so a starter never re-points."""
    here = orgs.current()
    with use_role("admin"):
        orgs.start_from(ARCHIMATE, "ArchiMate trial", "ada")
    after = orgs.current()
    assert (after.org_id, after.pack_id, after.pack_version) == (
        here.org_id,
        here.pack_id,
        here.pack_version,
    )


def test_the_starter_is_stored_so_other_organisations_can_apply_it(orgs, loaded):
    assert loaded.load_pack(ARCHIMATE) is None, "the store has not met it yet"
    with use_role("admin"):
        orgs.start_from(ARCHIMATE, "ArchiMate trial", "ada")
    stored = loaded.load_pack(ARCHIMATE)
    assert stored is not None and stored.element_types


def test_starting_twice_makes_two_organisations_and_one_metamodel(orgs, loaded):
    with use_role("admin"):
        orgs.start_from(ARCHIMATE, "ArchiMate one", "ada")
        orgs.start_from(ARCHIMATE, "ArchiMate two", "ada")
    assert len({r[0] for r in loaded._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")}) == 2
    assert len([v for v in loaded.list_pack_versions(ARCHIMATE)]) == 1


def test_a_starter_nothing_ships_is_refused(orgs):
    with use_role("admin"), pytest.raises(NotFoundError):
        orgs.start_from("mm_nosuchstarter0", "Nowhere", "ada")


def test_a_name_already_taken_is_refused_before_anything_is_stored(orgs):
    with use_role("admin"):
        orgs.start_from(ARCHIMATE, "ArchiMate trial", "ada")
        with pytest.raises(ConflictError, match="already exists"):
            orgs.start_from(ARCHIMATE, "ArchiMate trial", "ada")


def test_only_a_role_that_manages_organisations_may_start_one(orgs):
    for role in ("reader", "reviewer", "architect"):
        with use_role(role), pytest.raises(Forbidden):
            orgs.start_from(ARCHIMATE, f"Trial by {role}", "ada")
