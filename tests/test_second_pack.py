"""A second worked pack, in a different framework, on the same engine.

Principle `P5` says nothing framework-specific lives in `src/`, and goal `G5` says the
engine is reusable by any enterprise. One worked pack cannot show either: whatever the
engine happens to assume about the higher-education metamodel would simply look like the
engine working. This loads ArchiMate's own core — different layers, different types,
relationships declared against ANY rather than per pair — and asks the same code for the
same answers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import ARCHIMATE as ARCHIMATE_ID

from ea.backend.organisations import use_org
from ea.metamodel import Registry, load_pack
from ea.metamodel.loader import pack_from_dict, pack_to_dict
from ea.services import MetamodelService, OrganisationService, RepositoryService
from ea.views.mermaid import LAYER_STYLE

ROOT = Path(__file__).resolve().parents[1]
ARCHIMATE = ROOT / "packs" / "archimate_core" / "metamodel.yaml"


@pytest.fixture(scope="session")
def archimate():
    return load_pack(ARCHIMATE)


def test_it_loads_and_is_a_valid_pack(archimate):
    reg = Registry(archimate)
    assert archimate.id == ARCHIMATE_ID and archimate.version == "3.2"
    assert len(archimate.element_types) >= 25
    assert len(archimate.relationship_types) >= 10
    assert {d.id for d in archimate.domains} == {
        "motivation",
        "strategy",
        "business",
        "application",
        "technology",
        "implementation",
    }
    assert reg.get_type("capability") and reg.get_type("plateau")


def test_every_type_is_drawn_in_a_layer_the_view_generator_knows(archimate):
    """A pack that named a layer nothing renders would draw every shape in the fallback colour."""
    for t in archimate.element_types:
        layer = t.notation.get("layer") or ""
        assert layer in LAYER_STYLE, f"{t.id} names layer {layer!r}, which nothing renders"


def test_every_type_carries_what_the_engine_mints_identifiers_from(archimate):
    for t in archimate.element_types:
        assert t.prefix, f"{t.id} has no prefix"
        assert t.domain in {d.id for d in archimate.domains}
    assert len({t.prefix for t in archimate.element_types}) == len(archimate.element_types)


def test_its_relationships_are_declared_against_any(archimate):
    """ArchiMate allows most relationships between most elements; the pack says so once."""
    reg = Registry(archimate)
    allowed = {r.id for r in reg.allowed_rel_types("application_component", "business_process")}
    assert {"serving", "realization", "association"} <= allowed
    assert reg.resolve_rel_type("serves", "node", "application_component") is not None


def test_it_round_trips_through_the_pack_file(archimate):
    again = pack_from_dict(pack_to_dict(archimate))
    assert [t.id for t in again.element_types] == [t.id for t in archimate.element_types]
    assert [r.id for r in again.relationship_types] == [r.id for r in archimate.relationship_types]
    assert [g.id for g in again.attribute_groups] == [g.id for g in archimate.attribute_groups]


def test_both_frameworks_live_in_one_store_each_in_its_own_organisation(backend, pack, archimate):
    """The shape initiative 15 built for: a framework is tried beside the default, not instead of it."""
    backend.save_pack(archimate, "tester")
    orgs = OrganisationService(backend, MetamodelService(backend))
    trial = orgs.create("ArchiMate trial", "tester", org_id="archimate")
    assert trial  # created applying the default organisation's version
    orgs.apply("archimate", f"{ARCHIMATE_ID}@3.2", "tester")

    assert orgs.applied_pack("default").id == pack.id
    assert orgs.applied_pack("archimate").id == ARCHIMATE_ID
    assert {v.ref for v in MetamodelService(backend).versions()} == {
        f"{pack.id}@{pack.version}",
        f"{ARCHIMATE_ID}@3.2",
    }


def test_content_in_the_second_framework_is_written_and_read_by_the_same_code(backend, archimate):
    """No code knows either framework: the same repository service stores ArchiMate elements."""
    backend.save_pack(archimate, "tester")
    orgs = OrganisationService(backend, MetamodelService(backend))
    orgs.create("ArchiMate trial", "tester", org_id="archimate")
    orgs.apply("archimate", f"{ARCHIMATE_ID}@3.2", "tester")
    repo = RepositoryService(backend, Registry(archimate))
    with use_org("archimate"):
        goal = repo.create_element("goal", "One record per customer", "tester")
        cap = repo.create_element("capability", "Customer management", "tester")
        assert goal.element_id.startswith("GOAL") and cap.element_id.startswith("CAP")
        rel = repo.add_relationship("realization", cap.element_id, goal.element_id, "tester")
        assert rel.rel_type_id == "realization"
        assert backend.count_elements() == 2
    assert backend.count_elements() == 0  # the default organisation never saw any of it


def test_no_pack_ships_a_description_yaml_quietly_split_into_keys(pack, archimate):
    """A description with a comma inside a `{...}` flow mapping ends the value at the comma.

    The rest becomes a key of its own, and the engine's "keep what you do not understand"
    rule then carries it silently in `properties`. Both shipped packs had one. A property
    whose key reads like prose and whose value is empty is what that looks like.
    """
    for shipped in (pack, archimate):
        everything = [
            *shipped.domains,
            *shipped.attribute_groups,
            *shipped.element_types,
            *shipped.relationship_types,
            *shipped.common_attributes,
            *[a for t in shipped.element_types for a in t.attributes],
            *[a for r in shipped.relationship_types for a in r.attributes],
        ]
        stray = [
            (getattr(o, "id", None) or getattr(o, "name", "?"), k)
            for o in everything
            for k, v in (o.properties or {}).items()
            if v is None and " " in str(k)
        ]
        assert not stray, f"{shipped.id}: a description was split at a comma: {stray}"


def test_a_split_description_is_reported_rather_than_swallowed():
    """The warning an adopter gets when their own pack does what both shipped packs did."""
    from ea.metamodel.loader import suspect_split_descriptions

    pack = pack_from_dict(
        {
            "pack": {"id": "p", "name": "P"},
            "element_types": [
                {
                    "id": "thing",
                    "name": "Thing",
                    "description": "A thing",
                    # what YAML makes of `description: A thing, and more` in a flow mapping
                    "and more": None,
                }
            ],
        }
    )
    (line,) = suspect_split_descriptions(pack)
    assert "element type thing" in line and "'and more'" in line
    assert "split at a comma" in line


def test_a_property_the_engine_simply_does_not_know_is_not_reported():
    """The engine keeps what it does not understand; only a key that reads like prose is suspect."""
    from ea.metamodel.loader import suspect_split_descriptions

    pack = pack_from_dict(
        {
            "pack": {"id": "p", "name": "P"},
            "element_types": [{"id": "thing", "name": "Thing", "owner_team": "platform", "retired_on": None}],
        }
    )
    assert suspect_split_descriptions(pack) == []


def test_loading_a_file_logs_what_looks_mis_typed(tmp_path, caplog):
    import logging

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "pack: {id: p, name: P}\n"
        "element_types:\n"
        "  - {id: thing, name: Thing, description: A thing, and more}\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="ea.metamodel.loader"):
        load_pack(bad)
    assert any("split at a comma" in r.getMessage() for r in caplog.records)


def test_the_shipped_packs_load_without_a_warning(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="ea.metamodel.loader"):
        load_pack(ARCHIMATE)
        load_pack(ROOT / "packs" / "higher_education" / "metamodel.yaml")
    assert [r for r in caplog.records] == []
