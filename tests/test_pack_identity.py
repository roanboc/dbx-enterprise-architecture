"""The pack identifier, and the name that is free to change because of it.

A framework's identifier used to be a readable slug, which meant it read like a name while
being the key of `meta_pack`, of the five tables under it and of every organisation applying
a version. Rename the framework and the key described something that no longer existed, and
nothing would ever notice. These cover what decisions 0021 and 0022 put in its place: an
identifier nobody can read, minted once, and a name that is a label and nothing more.
"""

from __future__ import annotations

import pytest
from tests.conftest import ARCHIMATE, HIGHER_ED, a_pack_id

from ea.metamodel import load_pack
from ea.metamodel.loader import pack_from_dict, pack_to_dict
from ea.models import (
    IDENT_RE,
    ConflictError,
    Pack,
    is_pack_id,
    new_pack_id,
    pack_id_from_legacy,
    short_pack_id,
    validate_pack_id,
)
from ea.services import MetamodelService, OrganisationService


@pytest.fixture
def metamodels(loaded):
    return MetamodelService(loaded)


@pytest.fixture
def orgs(loaded):
    return OrganisationService(loaded)


# ----------------------------------------------------------------- what an identifier is
def test_a_minted_identifier_is_opaque_unique_and_fits_the_column():
    minted = [new_pack_id() for _ in range(200)]
    assert len(set(minted)) == 200, "eighty bits should not collide in two hundred draws"
    for value in minted:
        assert is_pack_id(value) and validate_pack_id(value) == value
        assert IDENT_RE.match(value), "it must still satisfy the column the store already has"
        assert not {"i", "l", "o", "u"} & set(value[3:]), "the letters that are misread are not used"


def test_an_identifier_a_person_could_read_is_refused():
    """The point of the change: a name-shaped key cannot be written down again by hand."""
    for bad in ("higher_education", "p", "", "MM_ABCDEFGHJKMNPQR", "mm_short", "mm_" + "z" * 17):
        assert not is_pack_id(bad)
        with pytest.raises(ValueError, match="minted, never written by hand"):
            validate_pack_id(bad)
    with pytest.raises(ValueError):
        Pack(id="higher_education", name="Anything")


def test_a_legacy_identifier_folds_to_the_same_key_everywhere():
    """A store migrated in place and one seeded from the shipped file must agree without asking.

    This is what lets the two exchange a pack afterwards, and what makes loading the same file
    twice a no-op rather than a second framework.
    """
    for slug in ("higher_education", "archimate_core", "anything_at_all"):
        first = pack_id_from_legacy(slug)
        assert first == pack_id_from_legacy(slug), "the fold is deterministic"
        assert is_pack_id(first)
    assert pack_id_from_legacy("a") != pack_id_from_legacy("b")


def test_the_short_form_is_what_a_person_copies():
    value = pack_id_from_legacy("higher_education")
    assert short_pack_id(value) == value[:9] and value.startswith(short_pack_id(value))


def test_a_pack_without_a_name_is_refused():
    """The name carries every reference a person reads now, so it cannot be blank."""
    with pytest.raises(ValueError, match="a name is required"):
        Pack(id=new_pack_id(), name="   ")


# ------------------------------------------------------------------- the shipped packs
def test_both_shipped_packs_carry_their_identifier_in_the_file():
    """Carried, not minted on load: minted per load, every `ea init` would fork the framework."""
    higher = load_pack("packs/higher_education/metamodel.yaml")
    archimate = load_pack("packs/archimate_core/metamodel.yaml")
    assert higher.id == HIGHER_ED and archimate.id == ARCHIMATE
    assert higher.id != archimate.id
    assert load_pack("packs/higher_education/metamodel.yaml").id == higher.id


def test_a_file_written_before_the_change_still_loads_onto_the_right_key(pack):
    """An exported YAML from before decision 0021 names its pack by a slug. It is folded, not refused."""
    old = pack_to_dict(pack)
    old["pack"]["id"] = "higher_education"
    assert pack_from_dict(old).id == HIGHER_ED


def test_a_file_with_no_identifier_is_folded_from_its_name(pack):
    """So somebody who hand-writes a pack gets one framework, however many times they load it."""
    data = pack_to_dict(pack)
    data["pack"].pop("id")
    data["pack"]["name"] = "A Framework Of My Own"
    once, twice = pack_from_dict(data).id, pack_from_dict(data).id
    assert is_pack_id(once) and once == twice


def test_a_file_that_names_nothing_at_all_is_refused(pack):
    data = pack_to_dict(pack)
    data["pack"].pop("id")
    data["pack"].pop("name", None)
    with pytest.raises(ValueError, match="an `id` or a `name`"):
        pack_from_dict(data)


def test_the_identifier_round_trips_through_a_pack_file(pack):
    assert pack_from_dict(pack_to_dict(pack)).id == pack.id


# ----------------------------------------------------------- a name is not a definition
def test_a_published_version_is_renamed_in_place(metamodels, loaded, pack):
    """The freeze is on what a version DEFINES; a label defines nothing (decision 0022)."""
    ref = f"{HIGHER_ED}@{pack.version}"
    before = metamodels.version(ref)
    assert before.status == "published"

    after = metamodels.rename(ref, "Curriculum Metamodel", "ada")
    assert after.name == "Curriculum Metamodel" and after.status == "published"
    assert after.pack_id == before.pack_id, "renaming moves no key"

    stored = metamodels.get(ref)
    assert stored.name == "Curriculum Metamodel"
    assert len(stored.element_types) == len(pack.element_types), "the definition is untouched"
    assert len(stored.domains) == len(pack.domains)


def test_renaming_leaves_the_organisation_where_it_was(metamodels, orgs, pack):
    """Nothing keys off the name, which is the whole reason renaming is allowed at all."""
    ref = f"{HIGHER_ED}@{pack.version}"
    before = orgs.current()
    metamodels.rename(ref, "Something Else Entirely", "ada")
    after = orgs.current()
    assert (after.pack_id, after.pack_version) == (before.pack_id, before.pack_version)


def test_a_rename_is_recorded_with_the_name_it_had(metamodels, loaded, pack):
    """The row keeps no history, so a correction nobody can trace is not one anybody can argue with."""
    ref = f"{HIGHER_ED}@{pack.version}"
    metamodels.rename(ref, "Renamed Once", "ada")
    entries = [h for h in loaded.history(limit=50) if h.get("op") == "rename"]
    assert entries, "a rename is logged"
    assert pack.name in str(entries[0]) and "Renamed Once" in str(entries[0])


def test_renaming_to_the_same_name_changes_nothing(metamodels, loaded, pack):
    ref = f"{HIGHER_ED}@{pack.version}"
    metamodels.rename(ref, pack.name, "ada")
    assert not [h for h in loaded.history(limit=50) if h.get("op") == "rename"]


def test_a_blank_name_is_refused(metamodels, pack):
    with pytest.raises(ValueError, match="needs a name"):
        metamodels.rename(f"{HIGHER_ED}@{pack.version}", "   ", "ada")


def test_a_published_definition_is_still_frozen_after_the_name_left_it(metamodels, pack):
    """The narrowing is exactly one field wide: everything else a version defines still refuses."""
    changed = metamodels.get(f"{HIGHER_ED}@{pack.version}")
    changed.name = "A New Name As Well"
    changed.element_types[0].description = "edited"
    with pytest.raises(ConflictError, match="frozen"):
        metamodels.save(changed, "ada")
    assert metamodels.get(f"{HIGHER_ED}@{pack.version}").name == pack.name, "and nothing was renamed"


# --------------------------------------------------------------------- naming a version
def test_a_version_is_reached_by_name_however_it_is_spelled(metamodels, pack):
    for spelling in (pack.name, pack.name.lower(), pack.name.replace(" ", "_").lower()):
        assert metamodels.resolve(spelling) == (HIGHER_ED, pack.version)


def test_a_version_is_reached_by_a_prefix_of_its_identifier(metamodels, pack):
    assert metamodels.resolve(short_pack_id(HIGHER_ED)) == (HIGHER_ED, pack.version)
    assert metamodels.resolve(HIGHER_ED) == (HIGHER_ED, pack.version)


def test_a_prefix_too_short_to_be_sure_is_refused_rather_than_guessed(metamodels):
    with pytest.raises(Exception, match="too short"):
        metamodels.resolve_pack(HIGHER_ED[:5])


def test_a_name_nothing_matches_says_what_is_held(metamodels, pack):
    """Somebody with a note from before the change lands here, and needs what to type instead."""
    with pytest.raises(Exception, match="this store holds") as exc:
        metamodels.resolve_pack("higher_education")
    assert pack.name in str(exc.value)


def test_a_name_two_metamodels_share_is_refused_rather_than_picked(metamodels, loaded, pack):
    """Choosing one for somebody who was ambiguous is how the wrong metamodel gets applied."""
    from dataclasses import replace

    twin = replace(pack, id=a_pack_id("twin"), version="twin", status="draft")
    loaded.save_pack(twin, "ada")
    with pytest.raises(ConflictError, match="more than one"):
        metamodels.resolve_pack(pack.name)
