"""What changed between two versions of a pack, element by element and field by field.

A version is compared before it is published or applied: the diff says which types,
relationship types, attributes and domains a version adds, removes or changes against
the one it came from, so the decision to promote it is read from the difference rather
than from two grids side by side.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ea.models import AttributeDef, Pack

KINDS = ("pack", "domain", "element_type", "relationship_type", "attribute")
_SKIP = {"sort_order", "attributes", "type_id", "rel_type_id"}


@dataclass
class DiffEntry:
    kind: str  # pack | domain | element_type | relationship_type | attribute
    id: str
    label: str
    change: str  # added | removed | changed
    fields: list[tuple[str, Any, Any]] = field(default_factory=list)  # (field, before, after)

    @property
    def summary(self) -> str:
        if self.change != "changed":
            return self.change
        return ", ".join(f for f, _, _ in self.fields)


@dataclass
class PackDiff:
    a: str  # `<pack id>@<version>` compared from
    b: str  # compared to
    entries: list[DiffEntry] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.entries

    def counts(self) -> dict[str, dict[str, int]]:
        """{kind: {added, removed, changed}} for the kinds that differ."""
        out: dict[str, dict[str, int]] = {}
        for e in self.entries:
            out.setdefault(e.kind, {"added": 0, "removed": 0, "changed": 0})[e.change] += 1
        return out

    def summary(self) -> str:
        if self.empty:
            return f"{self.a} and {self.b} define the same metamodel"
        parts = []
        for kind, c in self.counts().items():
            what = kind.replace("_", " ") + ("s" if sum(c.values()) != 1 else "")
            parts.append(f"{what}: " + ", ".join(f"{n} {change}" for change, n in c.items() if n))
        return f"{self.a} -> {self.b}: " + "; ".join(parts)


def _record(obj: Any) -> dict[str, Any]:
    d = asdict(obj)
    return {k: v for k, v in d.items() if k not in _SKIP}


def _attributes(pack: Pack) -> dict[str, tuple[str, AttributeDef]]:
    """Every attribute of the pack under one key: `common.<name>`, `<type>.<name>`, `<rel type>.<name>`."""
    out: dict[str, tuple[str, AttributeDef]] = {}
    for a in pack.common_attributes:
        out[f"common.{a.name}"] = ("common", a)
    for t in pack.element_types:
        for a in t.attributes:
            out[f"{t.id}.{a.name}"] = (t.name, a)
    for r in pack.relationship_types:
        for a in r.attributes:
            out[f"{r.id}.{a.name}"] = (r.name, a)
    return out


def _compare(
    kind: str, before: dict[str, tuple[str, Any]], after: dict[str, tuple[str, Any]]
) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            entries.append(DiffEntry(kind, key, after[key][0], "added"))
        elif key not in after:
            entries.append(DiffEntry(kind, key, before[key][0], "removed"))
        else:
            b, a = _record(before[key][1]), _record(after[key][1])
            changed = [(f, b.get(f), a.get(f)) for f in sorted(set(b) | set(a)) if b.get(f) != a.get(f)]
            if changed:
                entries.append(DiffEntry(kind, key, after[key][0], "changed", changed))
    return entries


def diff_packs(before: Pack, after: Pack) -> PackDiff:
    """The difference from `before` to `after`, in the order a reader looks: the header, domains, types, relationship types, attributes."""
    out = PackDiff(a=before.ref, b=after.ref)
    header_fields = ("name", "description", "source", "provenance_values", "notes", "properties")
    changed = [
        (f, getattr(before, f), getattr(after, f))
        for f in header_fields
        if getattr(before, f) != getattr(after, f)
    ]
    if changed:
        out.entries.append(DiffEntry("pack", after.id, after.name, "changed", changed))
    out.entries += _compare(
        "domain",
        {d.id: (d.name, d) for d in before.domains},
        {d.id: (d.name, d) for d in after.domains},
    )
    out.entries += _compare(
        "element_type",
        {t.id: (t.name, t) for t in before.element_types},
        {t.id: (t.name, t) for t in after.element_types},
    )
    out.entries += _compare(
        "relationship_type",
        {r.id: (r.name, r) for r in before.relationship_types},
        {r.id: (r.name, r) for r in after.relationship_types},
    )
    out.entries += _compare("attribute", _attributes(before), _attributes(after))
    return out
