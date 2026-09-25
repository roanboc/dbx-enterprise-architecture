"""The Metamodel page's lists: what deleting a row takes with it, and that what is left still validates.

The page rebuilds a whole pack from its grids, so a row taken out of a grid is a row taken
out of the version when it is saved. `remove_rows` decides what a deletion drags with it —
and the point of these tests is that whatever it leaves behind is a pack the metamodel
accepts, not one that has to be repaired by hand afterwards.
"""

from __future__ import annotations

import pytest

from ea.metamodel import Registry
from ea.metamodel.loader import pack_from_dict
from ea.ui.pages.metamodel import (
    _attr_rows,
    _domain_notation_rows,
    _domain_rows,
    _pack_from_grids,
    _rel_rows,
    _type_notation_rows,
    _type_rows,
    remove_rows,
)

TYPE = "data_entity"
SUB = "business_definition"  # a sub-type of business_information
REL = "logical_data_component__encapsulates__data_entity"


@pytest.fixture
def rows(registry):
    return {
        "types": _type_rows(registry),
        "rels": _rel_rows(registry),
        "attrs": _attr_rows(registry),
        "domains": _domain_rows(registry),
        "notation_types": _type_notation_rows(registry),
        "notation_domains": _domain_notation_rows(registry),
    }


def _pack(registry, rows: dict) -> Registry:
    """The grids as the page saves them: a pack rebuilt, parsed and validated."""
    return Registry(
        pack_from_dict(
            _pack_from_grids(
                registry.pack,
                rows["types"],
                rows["rels"],
                rows["attrs"],
                rows["domains"],
                rows["notation_domains"],
                rows["notation_types"],
            )
        )
    )


def _ids(rows: list[dict]) -> set[str]:
    return {r["id"] for r in rows}


def test_deleting_an_element_type_takes_its_relationships_and_attributes_with_it(registry, rows):
    picked = [r for r in rows["types"] if r["id"] == TYPE]
    ends = {r["id"] for r in rows["rels"] if TYPE in (r["source"], r["target"])}
    assert len(ends) > 1  # the type is at one end of several relationship types
    left, said = remove_rows("types", picked, rows)
    assert TYPE not in _ids(left["types"]) and TYPE not in _ids(left["notation_types"])
    assert not ends & _ids(left["rels"])
    assert not [a for a in left["attrs"] if a["type_id"] in ({TYPE} | ends)]
    assert said[0] == "1 element type(s)" and "relationship type(s) that named one of them" in said[1]
    # and what is left is a pack the metamodel accepts, with the type gone from it
    reg = _pack(registry, left)
    assert reg.get_type(TYPE) is None
    assert len(reg.pack.element_types) == len(registry.pack.element_types) - 1
    assert len(reg.pack.relationship_types) == len(registry.pack.relationship_types) - len(ends)


def test_deleting_a_supertype_keeps_its_sub_types_and_clears_the_reference(registry, rows):
    parent = next(r for r in rows["types"] if r["id"] == "business_information")
    children = {r["id"] for r in rows["types"] if r["supertype"] == parent["id"]}
    assert SUB in children
    left, said = remove_rows("types", [parent], rows)
    assert children <= _ids(left["types"])  # nobody's sub-type is deleted behind their back
    assert all(r["supertype"] == "" for r in left["types"] if r["id"] in children)
    assert any("cleared rather than deleted" in x for x in said)
    reg = _pack(registry, left)
    assert reg.get_type(SUB) is not None and reg.get_type(SUB).supertype is None


def test_deleting_a_domain_keeps_its_types_and_clears_the_domain(registry, rows):
    domain = next(r for r in rows["domains"] if r["id"] == "information")
    inside = {r["id"] for r in rows["types"] if r["domain"] == "information"}
    assert TYPE in inside
    left, said = remove_rows("domains", [domain], rows)
    assert "information" not in _ids(left["domains"])
    assert "information" not in _ids(left["notation_domains"])
    assert inside <= _ids(left["types"]) and all(
        r["domain"] == "" for r in left["types"] if r["id"] in inside
    )
    assert any("the domain of" in x for x in said)
    reg = _pack(registry, left)  # an unknown domain would be refused; a blank one is not
    assert reg.get_type(TYPE).domain == ""
    assert "information" not in reg.domains


def test_deleting_a_relationship_type_takes_only_its_own_attributes(registry, rows):
    rows["attrs"].append({"type_id": REL, "name": "since", "type": "date", "label": "Since"})
    left, said = remove_rows("rels", [r for r in rows["rels"] if r["id"] == REL], rows)
    assert REL not in _ids(left["rels"])
    assert not [a for a in left["attrs"] if a["type_id"] == REL]
    assert len(left["types"]) == len(rows["types"])
    assert said == ["1 relationship type(s)", "1 attribute(s) of what went with them"]
    reg = _pack(registry, left)
    assert REL not in reg.rel_types


def test_deleting_attributes_takes_the_ticked_ones_and_nothing_else(registry, rows):
    common = next(r for r in rows["attrs"] if r["type_id"] == "" and r["name"] == "alias")
    own = next(r for r in rows["attrs"] if r["type_id"] == TYPE and r["name"] == "includes_pii")
    left, said = remove_rows("attrs", [common, own], rows)
    assert len(left["attrs"]) == len(rows["attrs"]) - 2
    assert said == ["2 attribute(s)"]
    reg = _pack(registry, left)
    names = {a.name for a in reg.attributes_for(TYPE)}
    assert "alias" not in names and "includes_pii" not in names
    assert "available_in_analytics_platform" in names  # the type's other attribute stayed


def test_nothing_ticked_changes_nothing(registry, rows):
    left, said = remove_rows("types", [], rows)
    assert said == [] and {k: len(v) for k, v in left.items()} == {k: len(v) for k, v in rows.items()}


def test_the_attributes_a_type_declares_carry_their_group(registry):
    """An attribute names a declared group by its identifier; the name is the section heading."""
    groups = {a.name: a.group for a in registry.attributes_for("information_asset")}
    assert groups["alias"] == "identification" and groups["owner"] == "governance"
    assert groups["confidentiality_risk_rating"] == "risk_ratings"
    assert groups["information_category_description"] == ""
    assert registry.group_name("risk_ratings") == "Risk ratings"
    rows = _attr_rows(registry)
    assert next(r for r in rows if r["name"] == "alias")["group"] == "identification"


def test_a_type_placed_below_the_enterprise_level_is_saved_so(registry, rows):
    """Principle P9's line is the organisation's to draw: the level is edited in the types grid
    and a wrong one is refused, like any value the pack cannot hold (initiative 24)."""
    assert {r["level"] for r in rows["types"]} == {"enterprise"}  # both shipped packs, every type
    row = next(r for r in rows["types"] if r["id"] == TYPE)
    row["level"] = "solution"
    saved = _pack(registry, rows)
    assert saved.types[TYPE].level == "solution" and saved.types[SUB].level == "enterprise"
    row["level"] = "component"
    with pytest.raises(ValueError, match="level 'component' is not one of enterprise, solution"):
        _pack(registry, rows)
