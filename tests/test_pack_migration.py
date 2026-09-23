"""A store keyed on readable pack identifiers, brought onto opaque ones.

The suite builds every store fresh, so a migration is the one thing no other test can reach:
`init_schema` runs against a store this code made, which never holds an old key. These build
one deliberately — the store as it was before decision 0021 — and run the migration over it.
"""

from __future__ import annotations

import logging

import pytest
from tests.conftest import HIGHER_ED

from ea.backend.sql import META_TABLES, table_columns
from ea.models import ConflictError, pack_id_from_legacy

LEGACY = "higher_education"


def _push_back_to_a_slug(backend, pack_id: str, slug: str = LEGACY) -> None:
    """Make the store look the way it looked before the identifier changed."""
    for table in META_TABLES:
        backend._execute(f"UPDATE {table} SET pack_id = ? WHERE pack_id = ?", [slug, pack_id])
    backend._execute("UPDATE organisation SET pack_id = ? WHERE pack_id = ?", [slug, pack_id])


def test_every_table_that_holds_the_key_follows_it(loaded, pack):
    _push_back_to_a_slug(loaded, pack.id)
    loaded._execute("UPDATE meta_pack SET derived_from = ? WHERE pack_id = ?", [f"{LEGACY}@older", LEGACY])
    assert [r[0] for r in loaded._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")] == [LEGACY]

    loaded._migrate_pack_identifiers()

    for table in META_TABLES:
        held = {r[0] for r in loaded._fetch_all(f"SELECT DISTINCT pack_id FROM {table}")}
        assert held == {HIGHER_ED}, f"{table} still holds {held}"
    assert {r[0] for r in loaded._fetch_all("SELECT DISTINCT pack_id FROM organisation")} == {HIGHER_ED}
    derived = loaded._fetch_all("SELECT derived_from FROM meta_pack")[0][0]
    assert derived == f"{HIGHER_ED}@older", "a reference inside a text column moves with the key"


def test_the_migrated_key_is_the_one_the_shipped_file_carries(loaded, pack):
    """The whole point: a store carried forward and one seeded fresh must agree without asking."""
    _push_back_to_a_slug(loaded, pack.id)
    loaded._migrate_pack_identifiers()
    assert loaded._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")[0][0] == pack_id_from_legacy(LEGACY)
    assert pack.id == pack_id_from_legacy(LEGACY)


def test_the_whole_definition_still_loads_afterwards(loaded, pack):
    _push_back_to_a_slug(loaded, pack.id)
    loaded._migrate_pack_identifiers()
    again = loaded.load_pack(HIGHER_ED, pack.version)
    assert again is not None
    assert len(again.element_types) == len(pack.element_types)
    assert len(again.relationship_types) == len(pack.relationship_types)
    assert len(again.domains) == len(pack.domains)
    assert again.name == pack.name


def test_running_it_twice_changes_nothing(loaded, pack):
    _push_back_to_a_slug(loaded, pack.id)
    loaded._migrate_pack_identifiers()
    once = loaded._fetch_all("SELECT pack_id, version, name FROM meta_pack")
    loaded._migrate_pack_identifiers()
    assert loaded._fetch_all("SELECT pack_id, version, name FROM meta_pack") == once


def test_a_store_that_is_already_opaque_is_left_alone(loaded, pack):
    before = loaded._fetch_all("SELECT pack_id, version FROM meta_pack")
    loaded._migrate_pack_identifiers()
    assert loaded._fetch_all("SELECT pack_id, version FROM meta_pack") == before


def test_a_collision_is_reported_rather_than_crashing(loaded, pack, caplog):
    """Both keys for one framework at one version: rewriting would break the unique index.

    A store that will not open is worse than a store holding a row somebody has to look at,
    so the migration says so and carries on.
    """
    # From the DDL, not from `DESCRIBE`: that is DuckDB's, and this test runs on both engines.
    columns = table_columns("meta_pack")
    rest = ",".join(columns[1:])
    loaded._execute(
        f"INSERT INTO meta_pack ({','.join(columns)}) "
        f"SELECT '{LEGACY}', {rest} FROM meta_pack WHERE pack_id = ?",
        [pack.id],
    )
    with caplog.at_level(logging.WARNING):
        loaded._migrate_pack_identifiers()
    assert LEGACY in caplog.text and "already holds" in caplog.text
    held = {r[0] for r in loaded._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")}
    assert held == {LEGACY, HIGHER_ED}, "the old rows are left where somebody can see them"
    assert loaded.load_pack(HIGHER_ED, pack.version) is not None, "and the store still answers"


@pytest.mark.parametrize("slug", ["higher_education", "my_own_framework", "x"])
def test_any_readable_identifier_is_folded_not_only_the_shipped_ones(loaded, pack, slug):
    """Uniformly, which is what keeps a framework's name out of `src/` (principle P5)."""
    _push_back_to_a_slug(loaded, pack.id, slug)
    loaded._migrate_pack_identifiers()
    assert loaded._fetch_all("SELECT DISTINCT pack_id FROM meta_pack")[0][0] == pack_id_from_legacy(slug)


# --------------------------------------------------- a store from before drawing rules existed
# Initiative 22 gave a version viewpoints and a notation on its relationship types (decision
# 0023). A store seeded before that holds the published version without either, and `ea init`
# re-loads the shipped file routinely: the version gains its drawing rules once, and what it
# defines for validation stays frozen.


def _strip_drawing_rules(backend, pack) -> None:
    backend._execute(
        "UPDATE meta_pack SET viewpoints = NULL WHERE pack_id = ? AND version = ?", [pack.id, pack.version]
    )
    backend._execute(
        "UPDATE meta_relationship_type SET notation = NULL WHERE pack_id = ? AND pack_version = ?",
        [pack.id, pack.version],
    )


def test_a_published_version_stored_without_drawing_rules_gains_them_on_the_next_load(loaded, pack):
    from dataclasses import replace

    assert pack.status == "published" and pack.viewpoints and any(r.notation for r in pack.relationship_types)
    _strip_drawing_rules(loaded, pack)
    before = loaded.load_pack(pack.id, pack.version)
    assert before.viewpoints == [] and not any(r.notation for r in before.relationship_types)

    loaded.save_pack(pack, actor="init")  # the routine re-load of the shipped file: accepted, not refused
    after = loaded.load_pack(pack.id, pack.version)
    assert [v.id for v in after.viewpoints] == [v.id for v in pack.viewpoints]
    assert [r.notation for r in after.relationship_types] == [r.notation for r in pack.relationship_types]
    assert after.status == "published"
    loaded.save_pack(pack, actor="init")  # and again is the no-op it always was

    # What the version defines is still frozen: a changed type is refused as before.
    changed = replace(
        pack, element_types=[replace(pack.element_types[0], name="Renamed type")] + pack.element_types[1:]
    )
    with pytest.raises(ConflictError):
        loaded.save_pack(changed, actor="init")


def test_drawing_rules_are_not_a_back_door_for_a_changed_definition(loaded, pack):
    """A file that adds the drawing rules AND changes a type is refused whole."""
    from dataclasses import replace

    _strip_drawing_rules(loaded, pack)
    changed = replace(
        pack, element_types=[replace(pack.element_types[0], name="Renamed type")] + pack.element_types[1:]
    )
    with pytest.raises(ConflictError):
        loaded.save_pack(changed, actor="init")
    still = loaded.load_pack(pack.id, pack.version)
    assert still.viewpoints == [] and still.element_types[0].name == pack.element_types[0].name
