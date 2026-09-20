"""An attribute's group is a declared vocabulary, not free text.

The group was a string on the attribute, so a typo made a section of its own on the element
page that nobody could see was a mistake. A version declares its groups; an attribute names
one; and a group nothing declares is added to the pack rather than dropped, so a mistake is
a visible row instead of an invisible section.
"""

from __future__ import annotations

import pytest

from ea.metamodel import Registry
from ea.metamodel.diff import diff_packs
from ea.metamodel.loader import pack_from_dict, pack_to_dict, resolve_attribute_groups
from ea.models import AttributeDef, AttributeGroup, Pack
from ea.ui.pages.element import _by_group


def test_the_shipped_pack_declares_its_groups(pack):
    assert [g.id for g in pack.attribute_groups] == [
        "identification",
        "governance",
        "classification",
        "standard_dates",
        "data_platform",
        "risk_ratings",
    ]
    assert all(a.group in {g.id for g in pack.attribute_groups} for a in pack.common_attributes if a.group)


def test_an_attribute_names_a_group_by_its_identifier(registry):
    by_name = {a.name: a.group for a in registry.attributes_for("information_asset")}
    assert by_name["owner"] == "governance"
    assert registry.group_name("governance") == "Governance"
    assert registry.group_name("") == "" and registry.group_name("nope") == "nope"


def test_a_label_written_where_an_identifier_belongs_still_resolves():
    """How the format read before groups were declared: `group: Governance`, a label."""
    pack = pack_from_dict(
        {
            "pack": {"id": "p", "name": "P"},
            "attribute_groups": [{"id": "governance", "name": "Governance"}],
            "common_attributes": [{"name": "owner", "group": "Governance"}],
        }
    )
    assert pack.common_attributes[0].group == "governance"
    assert len(pack.attribute_groups) == 1


def test_a_group_nothing_declares_is_added_rather_than_dropped():
    """A typo becomes a visible row in the groups list, not an invisible section."""
    pack = pack_from_dict(
        {
            "pack": {"id": "p", "name": "P"},
            "attribute_groups": [{"id": "governance", "name": "Governance"}],
            "common_attributes": [
                {"name": "owner", "group": "Governance"},
                {"name": "steward", "group": "Govrenance"},  # the typo
            ],
        }
    )
    assert [g.id for g in pack.attribute_groups] == ["governance", "govrenance"]
    assert pack.common_attributes[1].group == "govrenance"
    assert Registry(pack).group_name("govrenance") == "Govrenance"


def test_a_group_that_cannot_be_an_identifier_is_dropped_rather_than_breaking_the_pack():
    pack = resolve_attribute_groups(
        Pack(id="p", name="P", common_attributes=[AttributeDef(name="owner", group="   !!!   ")])
    )
    assert pack.common_attributes[0].group == "" and pack.attribute_groups == []


def test_the_registry_refuses_a_group_no_version_declares():
    """Nothing reaches the registry ungrouped by accident: the loader declares what it finds."""
    pack = Pack(id="p", name="P", common_attributes=[AttributeDef(name="owner", group="ghost")])
    with pytest.raises(ValueError, match="unknown attribute group ghost"):
        Registry(pack)


def test_groups_survive_a_round_trip_through_the_pack_file(pack):
    again = pack_from_dict(pack_to_dict(pack))
    assert [(g.id, g.name, g.description) for g in again.attribute_groups] == [
        (g.id, g.name, g.description) for g in pack.attribute_groups
    ]


def test_groups_survive_a_round_trip_through_the_store(backend, pack):
    stored = backend.load_pack(pack.id, pack.version)
    assert [(g.id, g.name) for g in stored.attribute_groups] == [
        (g.id, g.name) for g in pack.attribute_groups
    ]
    assert stored.attribute_groups[0].description


def test_the_element_page_reads_the_groups_in_the_order_the_version_declares(registry):
    """Not the order the attributes happen to be written in — the order the pack lists."""
    headings = [h for h in _by_group(registry.attributes_for("information_asset"), registry) if h]
    declared = [g.name for g in registry.groups_in_order()]
    assert headings == [n for n in declared if n in headings]


def test_the_difference_between_two_versions_covers_the_groups(pack):
    after = pack_from_dict(pack_to_dict(pack))
    after.attribute_groups.append(AttributeGroup(id="new_section", name="New section"))
    after.attribute_groups[0].name = "Renamed"
    entries = {(e.kind, e.id, e.change) for e in diff_packs(pack, after).entries}
    assert ("attribute_group", "new_section", "added") in entries
    assert ("attribute_group", "identification", "changed") in entries


def test_deleting_a_group_leaves_its_attributes_ungrouped(registry):
    from ea.ui.pages.metamodel import _attr_rows, _group_rows, remove_rows

    rows = {
        "types": [],
        "rels": [],
        "attrs": _attr_rows(registry),
        "domains": [],
        "groups": _group_rows(registry),
        "notation_types": [],
        "notation_domains": [],
    }
    picked = [r for r in rows["groups"] if r["id"] == "governance"]
    left, said = remove_rows("groups", picked, rows)
    assert "governance" not in {r["id"] for r in left["groups"]}
    assert all(r["group"] != "governance" for r in left["attrs"])
    assert any("cleared rather than deleted" in s for s in said)
