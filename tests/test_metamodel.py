from __future__ import annotations

import pytest

from ea.metamodel import Registry, dump_pack, load_pack, pack_to_dict
from ea.metamodel.loader import pack_from_dict
from ea.models import ANY


def test_pack_loads_everything(pack):
    active = [t for t in pack.element_types if t.active]
    inactive = [t for t in pack.element_types if not t.active]
    assert len(active) == 27
    assert len(inactive) == 32
    assert len(pack.relationship_types) == 54
    assert {d.id for d in pack.domains} == {"information", "process", "integration", "enterprise"}
    assert all(t.deactivation_reason for t in inactive)


def test_supertypes_and_inheritance(registry: Registry):
    assert registry.ancestors("position") == ["position", "role"]
    assert registry.is_a("data_product", "product")
    assert registry.is_a("information_asset", ANY)
    # a relationship declared on the supertype applies to the sub-type
    ids = {r.id for r in registry.allowed_rel_types("organization_unit", "data_product")}
    assert "organization_unit__produces__product" in ids
    # ANY-targeted edges reach every type
    assert "business_definition__relates_to__any" in {
        r.id for r in registry.allowed_rel_types("business_definition", "process")
    }


def test_attributes_include_common_and_inherited(registry: Registry):
    names = [a.name for a in registry.attributes_for("information_asset")]
    assert "alias" in names  # common
    assert "confidentiality_risk_rating" in names  # own
    assert names.count("source") == 1


def test_resolve_type_by_name_plural_and_id(registry: Registry):
    assert registry.resolve_type("Logical Data Component").id == "logical_data_component"
    assert registry.resolve_type("logical data components").id == "logical_data_component"
    assert registry.resolve_type("logical_data_component").id == "logical_data_component"
    assert registry.resolve_type("Nope") is None


def test_resolve_relationship_by_name_and_inverse(registry: Registry):
    rt = registry.resolve_rel_type("owns", "position", "physical_application_component")
    assert rt.id == "position__owns__physical_application_component"
    rt = registry.resolve_rel_type("is encapsulated by", "logical_data_component", "data_entity")
    assert rt.id == "logical_data_component__encapsulates__data_entity"
    assert registry.resolve_rel_type("owns", "data_entity", "capability") is None


def test_validation_rules(registry: Registry):
    issues = registry.validate_element("attribute", {})
    assert any(i.code == "inactive_type" for i in issues)
    assert registry.validate_element("nope", {})[0].code == "unknown_type"
    issues = registry.validate_relationship(
        "position__is_steward_of__information_asset", "position", "information_asset", ""
    )
    assert any(i.code == "missing_qualifier" for i in issues)
    issues = registry.validate_relationship(
        "position__is_steward_of__information_asset", "position", "information_asset", "Chef"
    )
    assert any(i.code == "unknown_qualifier" for i in issues)
    issues = registry.validate_relationship(
        "logical_data_component__encapsulates__data_entity", "capability", "data_entity"
    )
    assert any(i.code == "disallowed_source" for i in issues)


def test_pack_round_trips_through_yaml(pack, tmp_path):
    out = tmp_path / "pack.yaml"
    dump_pack(pack, out)
    again = load_pack(out)
    assert pack_to_dict(again) == pack_to_dict(pack)


def test_pack_rejects_unknown_references():
    bad = {"pack": {"id": "x"}, "element_types": [{"id": "a", "supertype": "missing"}]}
    with pytest.raises(ValueError):
        Registry(pack_from_dict(bad))


# ------------------------------------------------- the richer definitions (initiative 15)
RICH = {
    "pack": {
        "id": "rich",
        "name": "Rich",
        "version": "1",
        "status": "draft",
        "properties": {"owner": "the team"},
    },
    "domains": [{"id": "core", "name": "Core", "properties": {"colour_name": "sea"}, "extra_key": 7}],
    "common_attributes": [
        {"name": "tags", "type": "string", "multiple": True, "group": "Classification", "help": "Any number"},
        {"name": "site", "type": "url", "properties": {"shown_on": "cards"}},
    ],
    "element_types": [
        {"id": "thing", "name": "Thing", "abstract": True, "domain": "core", "properties": {"icon": "box"}},
        {
            "id": "gadget",
            "name": "Gadget",
            "supertype": "thing",
            "domain": "core",
            "attributes": [
                {
                    "name": "tier",
                    "type": "string",
                    "enum": ["gold", "silver"],
                    "default": "silver",
                    "required": True,
                },
                {"name": "colours", "type": "string", "enum": ["red", "blue"], "multiple": True},
                {"name": "cost", "type": "number", "unit": "AUD", "min": 0, "max": 100},
                {"name": "code", "type": "string", "pattern": "[A-Z]{3}-[0-9]+"},
                {"name": "since", "type": "date", "min": "2020-01-01"},
                {"name": "count", "type": "integer", "default": 1},
                {"name": "wanted", "type": "boolean", "default": True},
            ],
        },
    ],
    "relationship_types": [
        {
            "id": "gadget__uses__gadget",
            "name": "uses",
            "source": "gadget",
            "target": "gadget",
            "attributes": [
                {"name": "since", "type": "date", "required": True},
                {"name": "weight", "type": "number"},
            ],
            "properties": {"style": "dashed"},
        }
    ],
}


def test_the_richer_definitions_round_trip(tmp_path):
    pack = pack_from_dict(RICH)
    tier = next(a for a in pack.element_types[1].attributes if a.name == "tier")
    assert (tier.default, tier.required, tier.enum) == ("silver", True, ["gold", "silver"])
    assert pack.element_types[0].abstract and pack.element_types[0].properties == {"icon": "box"}
    assert pack.domains[0].properties == {"colour_name": "sea", "extra_key": 7}  # an unknown key is kept
    assert pack.relationship_types[0].attributes[0].rel_type_id == "gadget__uses__gadget"
    assert pack.properties == {"owner": "the team"} and pack.status == "draft"
    out = tmp_path / "rich.yaml"
    dump_pack(pack, out)
    assert pack_to_dict(load_pack(out)) == pack_to_dict(pack)
    assert "abstract: true" in out.read_text() and "multiple: true" in out.read_text()
    d = pack_to_dict(pack)
    assert (
        "abstract" not in d["element_types"][1] and "multiple" not in d["element_types"][1]["attributes"][0]
    )


def test_the_richer_definitions_round_trip_through_the_store(backend):
    pack = pack_from_dict(RICH)
    backend.save_pack(pack, "ada")
    stored = backend.load_pack("rich", "1")
    assert pack_to_dict(stored) == pack_to_dict(pack)
    assert stored.relationship_types[0].attributes[1].type == "number"
    assert [v.ref for v in backend.list_pack_versions("rich")] == ["rich@1"]


def test_the_richer_rules_are_validated():
    reg = Registry(pack_from_dict(RICH))
    codes = lambda issues: sorted(i.code for i in issues)  # noqa: E731
    assert reg.validate_element("thing", {})[0].code == "abstract_type"
    assert [t.id for t in reg.concrete_types()] == ["gadget"]
    assert reg.defaults_for("gadget") == {"tier": "silver", "count": 1, "wanted": True}
    ok = {
        "tier": "gold",
        "colours": ["red"],
        "cost": 50,
        "code": "ABC-1",
        "since": "2021-06-01",
        "site": "https://x",
    }
    assert reg.validate_element("gadget", ok) == []
    assert codes(reg.validate_element("gadget", {})) == ["missing_attribute"]
    bad = {
        "tier": "gold",
        "colours": ["red", "green"],
        "cost": 500,
        "code": "abc",
        "since": "2019-12-31",
        "site": "ftp://x",
        "count": "many",
        "wanted": "maybe",
    }
    assert codes(reg.validate_element("gadget", bad)) == [
        "enum_value",
        "invalid_url",
        "out_of_range",
        "out_of_range",
        "pattern_mismatch",
        "wrong_type",
        "wrong_type",
    ]
    assert codes(reg.validate_element("gadget", {"tier": "gold", "colours": "red|blue"})) == []
    assert codes(reg.validate_element("gadget", {"tier": "gold", "tags": "a; b"})) == []
    rel = reg.validate_relationship("gadget__uses__gadget", "gadget", "gadget", attrs={})
    assert codes(rel) == ["missing_attribute"]
    rel = reg.validate_relationship(
        "gadget__uses__gadget", "gadget", "gadget", attrs={"since": "2024-01-01", "weight": "x"}
    )
    assert codes(rel) == ["wrong_type"]
    assert (
        reg.validate_relationship(
            "gadget__uses__gadget", "gadget", "gadget", attrs={"since": "2024-01-01", "odd": 1}
        )[0].code
        == "extra_attribute"
    )
    assert reg.attributes_for_relationship("gadget__uses__gadget")[0].name == "since"
    assert (
        "(abstract)" in reg.summary_markdown() and "attributes ['since', 'weight']" in reg.summary_markdown()
    )
    with pytest.raises(ValueError, match="regular expression"):
        pack_from_dict({"pack": {"id": "x"}, "common_attributes": [{"name": "a", "pattern": "("}]})
    with pytest.raises(ValueError, match="above max"):
        pack_from_dict(
            {"pack": {"id": "x"}, "common_attributes": [{"name": "a", "type": "number", "min": 2, "max": 1}]}
        )
    with pytest.raises(ValueError, match="defined twice"):
        Registry(pack_from_dict({"pack": {"id": "x"}, "element_types": [{"id": "a"}, {"id": "a"}]}))


def test_diff_reads_what_changed():
    from ea.metamodel import diff_packs

    before = pack_from_dict(RICH)
    after = pack_from_dict(RICH)
    after.element_types[1].attributes[0].default = "gold"
    after.element_types.append(type(after.element_types[0])(id="widget", name="Widget", domain="core"))
    after.relationship_types = []
    diff = diff_packs(before, after)
    assert diff.counts() == {
        "element_type": {"added": 1, "removed": 0, "changed": 0},
        "relationship_type": {"added": 0, "removed": 1, "changed": 0},
        "attribute": {"added": 0, "removed": 2, "changed": 1},
    }
    changed = next(e for e in diff.entries if e.change == "changed")
    assert changed.id == "gadget.tier" and changed.fields == [("default", "silver", "gold")]
    assert "rich@1 -> rich@1" in diff.summary()
