"""Read and write metamodel packs (YAML). The pack file format is documented in packs/README.md."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from ea.models import (
    ANY,
    AttributeDef,
    AttributeGroup,
    Domain,
    ElementType,
    Pack,
    RelationshipType,
    Viewpoint,
    is_pack_id,
    pack_id_from_legacy,
    slugify,
)

log = logging.getLogger(__name__)

# Keys of an attribute a pack may set and the engine reads; anything else under an attribute
# is unknown to the engine and travels in `properties`, so a framework loses nothing by
# writing what the engine does not yet understand.
ATTRIBUTE_KEYS = {
    "name",
    "label",
    "type",
    "required",
    "enum",
    "description",
    "sensitivity",
    "default",
    "multiple",
    "unit",
    "pattern",
    "min",
    "max",
    "group",
    "help",
    "properties",
}


def _properties(d: dict[str, Any], known: set[str]) -> dict[str, Any]:
    """The `properties` block, plus any key the engine does not know, so a pack can say more than the engine reads."""
    out = dict(d.get("properties") or {}) if isinstance(d.get("properties"), dict) else {}
    for k, v in d.items():
        if k not in known and k != "properties":
            out[str(k)] = v
    return out


def _attr(d: dict[str, Any], type_id: str | None = None, rel_type_id: str | None = None) -> AttributeDef:
    return AttributeDef(
        name=d["name"],
        label=d.get("label", ""),
        type=d.get("type", "string"),
        required=bool(d.get("required", False)),
        enum=[str(x) for x in d["enum"]] if d.get("enum") else None,
        description=d.get("description", ""),
        sensitivity=d.get("sensitivity", ""),
        type_id=type_id,
        rel_type_id=rel_type_id,
        default=d.get("default"),
        multiple=bool(d.get("multiple", False)),
        unit=str(d.get("unit") or ""),
        pattern=str(d.get("pattern") or ""),
        min=d.get("min"),
        max=d.get("max"),
        group=str(d.get("group") or ""),
        help=str(d.get("help") or ""),
        properties=_properties(d, ATTRIBUTE_KEYS),
    )


def _notation(d: Any) -> dict[str, str]:
    """A notation block is a flat map of strings; anything else is ignored rather than trusted."""
    if not isinstance(d, dict):
        return {}
    return {str(k): str(v) for k, v in d.items() if v not in (None, "")}


DOMAIN_KEYS = {"id", "name", "description", "notation", "properties"}
GROUP_KEYS = {"id", "name", "description", "properties"}
TYPE_KEYS = {
    "id",
    "name",
    "plural",
    "supertype",
    "active",
    "deactivation_reason",
    "domain",
    "provenance",
    "prefix",
    "description",
    "examples",
    "source_of_record",
    "type_owner",
    "instance_owner",
    "attributes",
    "notation",
    "abstract",
    "properties",
}
REL_KEYS = {
    "id",
    "name",
    "inverse",
    "source",
    "target",
    "provenance",
    "qualifiers",
    "diagrams",
    "description",
    "src_max",
    "dst_max",
    "attributes",
    "properties",
    "notation",
}
VIEWPOINT_KEYS = {
    "id",
    "name",
    "description",
    "element_types",
    "relationship_types",
    "bands",
    "band_order",
    "band_type",
    "band_relationships",
    "other_band",
    "nest",
    "span",
    "overview_relationships",
    "properties",
}
PACK_KEYS = {
    "id",
    "name",
    "version",
    "description",
    "source",
    "provenance_values",
    "status",
    "derived_from",
    "notes",
    "properties",
}


def _pack_id_of(meta: dict[str, Any]) -> str:
    """The identifier a pack file is stored under.

    A file written since decision 0021 carries an opaque one and is taken at its word. Anything
    else is folded into one deterministically rather than minted: a file exported before the
    identifier changed, and a file somebody wrote by hand with a readable `id:` or none at all,
    each land on the same key however many times they are loaded and on whatever machine — so
    loading one twice is the no-op it looks like, not a second framework.
    """
    given = str(meta.get("id") or "").strip()
    if is_pack_id(given):
        return given
    # No identifier at all is a framework the store has not met; its name is the only stable
    # thing about it, so that is what the key is folded from.
    legacy = given or slugify(str(meta.get("name") or ""))
    derived = pack_id_from_legacy(legacy)
    log.info("pack %r carries no opaque identifier; reading it as %s", legacy, derived)
    return derived


def pack_from_dict(data: dict[str, Any]) -> Pack:
    meta = data.get("pack") or {}
    if not (meta.get("id") or meta.get("name")):
        raise ValueError("pack file needs a `pack:` block with an `id` or a `name`")
    domains = [
        Domain(
            id=d["id"],
            name=d.get("name", d["id"]),
            description=d.get("description", ""),
            notation=_notation(d.get("notation")),
            sort_order=i,
            properties=_properties(d, DOMAIN_KEYS),
        )
        for i, d in enumerate(data.get("domains") or [])
    ]
    groups = [
        AttributeGroup(
            id=g["id"] if isinstance(g, dict) else slugify(str(g)),
            name=(g.get("name") or "") if isinstance(g, dict) else str(g),
            description=g.get("description", "") if isinstance(g, dict) else "",
            sort_order=i,
            properties=_properties(g, GROUP_KEYS) if isinstance(g, dict) else {},
        )
        for i, g in enumerate(data.get("attribute_groups") or [])
    ]
    common = [_attr(a) for a in data.get("common_attributes") or []]
    element_types: list[ElementType] = []
    for i, e in enumerate(data.get("element_types") or []):
        element_types.append(
            ElementType(
                id=e["id"],
                name=e.get("name", e["id"]),
                plural=e.get("plural", ""),
                supertype=e.get("supertype") or None,
                active=bool(e.get("active", True)),
                deactivation_reason=e.get("deactivation_reason", ""),
                domain=e.get("domain", ""),
                provenance=e.get("provenance", ""),
                prefix=e.get("prefix", ""),
                description=e.get("description", ""),
                examples=list(e.get("examples") or []),
                source_of_record=e.get("source_of_record", ""),
                type_owner=e.get("type_owner", ""),
                instance_owner=e.get("instance_owner", ""),
                attributes=[_attr(a, e["id"]) for a in e.get("attributes") or []],
                notation=_notation(e.get("notation")),
                sort_order=i,
                abstract=bool(e.get("abstract", False)),
                properties=_properties(e, TYPE_KEYS),
            )
        )
    relationship_types: list[RelationshipType] = []
    for i, r in enumerate(data.get("relationship_types") or []):
        relationship_types.append(
            RelationshipType(
                id=r["id"],
                name=r.get("name", r["id"]),
                inverse=r.get("inverse", ""),
                source=r.get("source", ANY) or ANY,
                target=r.get("target", ANY) or ANY,
                provenance=r.get("provenance", ""),
                qualifiers=list(r.get("qualifiers") or []),
                diagrams=list(r.get("diagrams") or []),
                description=r.get("description", ""),
                src_max=r.get("src_max"),
                dst_max=r.get("dst_max"),
                sort_order=i,
                attributes=[_attr(a, None, r["id"]) for a in r.get("attributes") or []],
                properties=_properties(r, REL_KEYS),
                notation=_notation(r.get("notation")),
            )
        )
    viewpoints = [
        Viewpoint(
            id=v["id"],
            name=v.get("name") or v["id"],
            description=v.get("description", "") or "",
            element_types=[str(x) for x in v.get("element_types") or []],
            relationship_types=[str(x) for x in v.get("relationship_types") or []],
            bands=str(v.get("bands") or "layer"),
            band_order=[str(x) for x in v.get("band_order") or []],
            band_type=str(v.get("band_type") or ""),
            band_relationships=[str(x) for x in v.get("band_relationships") or []],
            other_band=str(v.get("other_band") or "Other"),
            nest=[str(x) for x in v.get("nest") or []],
            span=[str(x) for x in v.get("span") or []],
            overview_relationships=[str(x) for x in v.get("overview_relationships") or []],
            sort_order=i,
            properties=_properties(v, VIEWPOINT_KEYS),
        )
        for i, v in enumerate(data.get("viewpoints") or [])
    ]
    return resolve_attribute_groups(
        Pack(
            id=_pack_id_of(meta),
            name=meta.get("name") or str(meta.get("id") or ""),
            version=str(meta.get("version") or "1"),
            description=meta.get("description", ""),
            source=meta.get("source", ""),
            provenance_values=list(meta.get("provenance_values") or []),
            domains=domains,
            attribute_groups=groups,
            common_attributes=common,
            element_types=element_types,
            relationship_types=relationship_types,
            status=str(meta.get("status") or "draft"),
            derived_from=str(meta.get("derived_from") or ""),
            notes=str(meta.get("notes") or ""),
            properties=_properties(meta, PACK_KEYS),
            viewpoints=viewpoints,
        )
    )


def resolve_attribute_groups(pack: Pack) -> Pack:
    """Every attribute's `group` made to name a declared group, declaring the missing ones.

    A group written as a label rather than an identifier (`group: Governance`, which is how
    the format read before groups were declared) matches a declared group by its name; one
    nothing declares is **added** to the pack rather than dropped. So a vocabulary always
    exists, and a typo shows up as an extra row in the groups list — visible, and deletable —
    instead of an invisible section on the element page.
    """
    by_id = {g.id: g for g in pack.attribute_groups}
    by_name = {g.name.strip().lower(): g for g in pack.attribute_groups}
    for a in _every_attribute(pack):
        raw = (a.group or "").strip()
        if not raw:
            a.group = ""
            continue
        if raw in by_id:
            continue
        found = by_name.get(raw.lower())
        if found is None:
            try:
                slug = slugify(raw)
            except ValueError:
                a.group = ""
                continue
            found = by_id.get(slug)
        if found is None:
            found = AttributeGroup(id=slug, name=raw, sort_order=len(pack.attribute_groups))
            pack.attribute_groups.append(found)
            by_id[found.id] = found
            by_name[found.name.strip().lower()] = found
        a.group = found.id
    for i, g in enumerate(pack.attribute_groups):
        g.sort_order = i
    return pack


def _every_attribute(pack: Pack) -> list[AttributeDef]:
    out = list(pack.common_attributes)
    for e in pack.element_types:
        out.extend(e.attributes)
    for r in pack.relationship_types:
        out.extend(r.attributes)
    return out


def suspect_split_descriptions(pack: Pack) -> list[str]:
    """Properties that look like a description YAML split at a comma, one sentence each.

    Inside a `{...}` flow mapping, `description: A, B` ends the value at the comma and makes
    `B` a key of its own. The engine's rule that what it does not understand is kept in
    `properties` then carries the rest of the sentence silently, so a pack loses half a
    description and says nothing. Both shipped packs had one.

    A property whose key reads like prose — it has a space in it — and whose value is empty
    is what that looks like. Nothing else legitimately writes one, so it is worth a warning;
    it stays a warning rather than an error because only the author can say whether the key
    was meant.
    """
    out: list[str] = []
    for what, name, props in _properties_by_owner(pack):
        for key, value in (props or {}).items():
            if value is None and " " in str(key):
                out.append(
                    f"{what} {name}: the property {key!r} has no value and reads like prose — "
                    f"a description was probably split at a comma. Quote it: description: '…, …'"
                )
    return out


def _properties_by_owner(pack: Pack) -> list[tuple[str, str, dict[str, Any]]]:
    out: list[tuple[str, str, dict[str, Any]]] = [("pack", pack.id, pack.properties)]
    out += [("domain", d.id, d.properties) for d in pack.domains]
    out += [("attribute group", g.id, g.properties) for g in pack.attribute_groups]
    out += [("element type", t.id, t.properties) for t in pack.element_types]
    out += [("relationship type", r.id, r.properties) for r in pack.relationship_types]
    out += [("viewpoint", v.id, v.properties) for v in pack.viewpoints]
    out += [("attribute", a.name, a.properties) for a in _every_attribute(pack)]
    return out


def load_pack(path: str | Path) -> Pack:
    """A pack read from a file, with anything that looks mis-typed logged rather than swallowed."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    pack = pack_from_dict(data)
    for line in suspect_split_descriptions(pack):
        log.warning("%s: %s", path, line)
    return pack


def _clean(d: dict[str, Any], drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """Drop empty values and bookkeeping fields so the YAML stays readable."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k in drop or v in (None, "", [], {}):
            continue
        out[k] = v
    return out


def attr_to_dict(a: AttributeDef) -> dict[str, Any]:
    d = _clean(asdict(a), drop=("type_id", "rel_type_id"))
    if not a.multiple:
        d.pop("multiple", None)
    return d


def pack_to_dict(pack: Pack) -> dict[str, Any]:
    element_types = []
    for e in pack.element_types:
        d = _clean(asdict(e), drop=("sort_order", "attributes"))
        if e.active:
            d.pop("active", None)
        else:
            d["active"] = False
        if not e.abstract:
            d.pop("abstract", None)
        if e.attributes:
            d["attributes"] = [attr_to_dict(a) for a in e.attributes]
        element_types.append(d)
    relationship_types = []
    for r in pack.relationship_types:
        d = _clean(asdict(r), drop=("sort_order", "attributes"))
        if r.attributes:
            d["attributes"] = [attr_to_dict(a) for a in r.attributes]
        relationship_types.append(d)
    return {
        "pack": _clean(
            {
                "id": pack.id,
                "name": pack.name,
                "version": pack.version,
                "status": pack.status,
                "derived_from": pack.derived_from,
                "description": pack.description,
                "source": pack.source,
                "notes": pack.notes,
                "provenance_values": pack.provenance_values,
                "properties": pack.properties,
            }
        ),
        "domains": [_clean(asdict(d), drop=("sort_order",)) for d in pack.domains],
        "attribute_groups": [_clean(asdict(g), drop=("sort_order",)) for g in pack.attribute_groups],
        "common_attributes": [attr_to_dict(a) for a in pack.common_attributes],
        "element_types": element_types,
        "relationship_types": relationship_types,
        **({"viewpoints": [_viewpoint_to_dict(v) for v in pack.viewpoints]} if pack.viewpoints else {}),
    }


def _viewpoint_to_dict(v: Viewpoint) -> dict[str, Any]:
    d = _clean(asdict(v), drop=("sort_order",))
    if v.bands == "layer":
        d.pop("bands", None)
    if v.other_band == "Other":
        d.pop("other_band", None)
    return d


def dump_pack(pack: Pack, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(pack_to_dict(pack), fh, sort_keys=False, allow_unicode=True, width=110)


def pack_yaml(pack: Pack) -> str:
    """The pack as the text of its file."""
    return yaml.safe_dump(pack_to_dict(pack), sort_keys=False, allow_unicode=True, width=110)
