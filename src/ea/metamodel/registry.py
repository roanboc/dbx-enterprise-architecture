"""The metamodel registry: lookups, inheritance and validation rules derived from a pack.

Everything the engine knows about a framework it learns from here; nothing is
hard-coded to any particular pack, ArchiMate or otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from typing import Any

from ea.models import (
    ANY,
    LINK_SCHEMES,
    AttributeDef,
    AttributeGroup,
    ElementType,
    Issue,
    Pack,
    RelationshipType,
    split_multi,
)


class Registry:
    def __init__(self, pack: Pack):
        self.pack = pack
        self.types: dict[str, ElementType] = {t.id: t for t in pack.element_types}
        self.rel_types: dict[str, RelationshipType] = {r.id: r for r in pack.relationship_types}
        self.domains = {d.id: d for d in pack.domains}
        self.attribute_groups = {g.id: g for g in pack.attribute_groups}
        self._by_name: dict[str, ElementType] = {}
        for t in pack.element_types:
            self._by_name[t.name.strip().lower()] = t
            self._by_name.setdefault(t.plural.strip().lower(), t)
            self._by_name.setdefault(t.id.replace("_", " "), t)
        self._validate_pack()

    # ---------------------------------------------------------------- pack
    def _validate_pack(self) -> None:
        problems: list[str] = []
        for what, items in (
            ("domain", [d.id for d in self.pack.domains]),
            ("element type", [t.id for t in self.pack.element_types]),
            ("relationship type", [r.id for r in self.pack.relationship_types]),
        ):
            seen_ids: set[str] = set()
            for i in items:
                if i in seen_ids:
                    problems.append(f"{what} {i}: defined twice")
                seen_ids.add(i)
        for a in self._all_attributes():
            if a.group and a.group not in self.attribute_groups:
                problems.append(f"attribute {a.name}: unknown attribute group {a.group}")
        for t in self.pack.element_types:
            if t.supertype and t.supertype not in self.types:
                problems.append(f"element type {t.id}: unknown supertype {t.supertype}")
            if t.domain and t.domain not in self.domains:
                problems.append(f"element type {t.id}: unknown domain {t.domain}")
        for r in self.pack.relationship_types:
            for end in (r.source, r.target):
                if end != ANY and end not in self.types:
                    problems.append(f"relationship type {r.id}: unknown end type {end}")
        for t in self.pack.element_types:
            seen: set[str] = set()
            cur: str | None = t.id
            while cur:
                if cur in seen:
                    problems.append(f"element type {t.id}: supertype cycle")
                    break
                seen.add(cur)
                cur = self.types[cur].supertype if cur in self.types else None
        if problems:
            raise ValueError("invalid pack: " + "; ".join(problems))

    def _all_attributes(self) -> list[AttributeDef]:
        out = list(self.pack.common_attributes)
        for t in self.pack.element_types:
            out.extend(t.attributes)
        for r in self.pack.relationship_types:
            out.extend(r.attributes)
        return out

    # -------------------------------------------------------- attribute groups
    def group_name(self, group_id: str) -> str:
        """What the element page heads the section with; the identifier itself if nothing declares it."""
        g = self.attribute_groups.get(group_id or "")
        return g.name if g else (group_id or "")

    def groups_in_order(self) -> list[AttributeGroup]:
        """The groups a version declares, in the order it declares them."""
        return sorted(self.pack.attribute_groups, key=lambda g: (g.sort_order, g.id))

    # ------------------------------------------------------------- lookups
    def get_type(self, type_id: str) -> ElementType | None:
        return self.types.get(type_id)

    def notation(self, type_id: str) -> dict[str, str]:
        """How a type is drawn: its own `notation`, then its supertypes', then its domain's, then the engine defaults."""
        out: dict[str, str] = {
            "layer": "other",
            "glyph": "",
            "stereotype": "",
            "archimate": "",
            "shape": "rect",
        }
        t = self.types.get(type_id)
        if t is None:
            return out
        domain = next((d for d in self.pack.domains if d.id == t.domain), None)
        if domain is not None:
            out.update(domain.notation)
        chain = [self.types[a] for a in reversed(self.ancestors(type_id)) if a in self.types] + [t]
        for et in chain:
            out.update(et.notation)
        if not out.get("stereotype"):
            out["stereotype"] = t.name
        return out

    def resolve_type(self, label: str) -> ElementType | None:
        """By id, name, plural or a loose label ('Logical Data Component', 'logical_data_component')."""
        if not label:
            return None
        key = label.strip()
        if key in self.types:
            return self.types[key]
        low = key.lower()
        if low in self._by_name:
            return self._by_name[low]
        return self._by_name.get(low.replace("_", " ").replace("-", " "))

    def ancestors(self, type_id: str) -> list[str]:
        """The type itself, then its supertypes, root last."""
        out: list[str] = []
        cur: str | None = type_id
        while cur and cur in self.types and cur not in out:
            out.append(cur)
            cur = self.types[cur].supertype
        return out

    def is_a(self, type_id: str, other: str) -> bool:
        return other == ANY or other in self.ancestors(type_id)

    def subtypes(self, type_id: str) -> list[str]:
        return [t.id for t in self.pack.element_types if type_id in self.ancestors(t.id)]

    def attributes_for(self, type_id: str) -> list[AttributeDef]:
        """Common attributes, then inherited (root first), then the type's own."""
        out: list[AttributeDef] = list(self.pack.common_attributes)
        for tid in reversed(self.ancestors(type_id)):
            out.extend(self.types[tid].attributes)
        seen: dict[str, AttributeDef] = {}
        for a in out:
            seen[a.name] = a
        return list(seen.values())

    def attributes_for_relationship(self, rel_type_id: str) -> list[AttributeDef]:
        """What a relationship of this type may carry: the type's own attributes, none inherited."""
        r = self.rel_types.get(rel_type_id)
        return list(r.attributes) if r else []

    def defaults_for(self, type_id: str) -> dict[str, Any]:
        """The attribute values a new element of the type starts with."""
        return {a.name: a.default for a in self.attributes_for(type_id) if a.default is not None}

    def active_types(self) -> list[ElementType]:
        return [t for t in self.pack.element_types if t.active]

    def concrete_types(self) -> list[ElementType]:
        """The types an element may be: active and not abstract."""
        return [t for t in self.pack.element_types if t.active and not t.abstract]

    def types_in_domain(self, domain_id: str) -> list[ElementType]:
        return [t for t in self.pack.element_types if t.domain == domain_id]

    # ------------------------------------------------------- relationships
    def allowed_rel_types(self, src_type: str, dst_type: str) -> list[RelationshipType]:
        return [
            r
            for r in self.pack.relationship_types
            if self.is_a(src_type, r.source) and self.is_a(dst_type, r.target)
        ]

    def rel_types_for_type(self, type_id: str) -> tuple[list[RelationshipType], list[RelationshipType]]:
        """(outgoing, incoming) relationship types a type may take part in."""
        out = [r for r in self.pack.relationship_types if self.is_a(type_id, r.source)]
        inc = [r for r in self.pack.relationship_types if self.is_a(type_id, r.target)]
        return out, inc

    def resolve_rel_type(self, label: str, src_type: str, dst_type: str) -> RelationshipType | None:
        """By id, or by name among the types allowed between src and dst (most specific end types win)."""
        if not label:
            return None
        key = label.strip()
        if key in self.rel_types:
            return self.rel_types[key]
        low = key.lower()
        candidates = [r for r in self.allowed_rel_types(src_type, dst_type) if r.name.lower() == low]
        if not candidates:
            candidates = [r for r in self.allowed_rel_types(src_type, dst_type) if r.inverse.lower() == low]
        if not candidates:
            return None

        def specificity(r: RelationshipType) -> int:
            s = (
                0
                if r.source == ANY
                else len(self.ancestors(src_type)) - self.ancestors(src_type).index(r.source)
            )
            t = (
                0
                if r.target == ANY
                else len(self.ancestors(dst_type)) - self.ancestors(dst_type).index(r.target)
            )
            return s + t

        candidates.sort(key=specificity, reverse=True)
        return candidates[0]

    # ---------------------------------------------------------- validation
    @staticmethod
    def _is_number(v: Any) -> bool:
        if isinstance(v, bool):
            return False
        try:
            float(v)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _is_date(v: Any) -> bool:
        try:
            date.fromisoformat(str(v)[:10])
        except (TypeError, ValueError):
            return False
        return True

    def _value_issues(self, a: AttributeDef, value: Any, entity: str | None) -> list[Issue]:
        """What one value says against one declaration: the rules a pack states on an attribute."""
        issues: list[Issue] = []

        def add(level: str, code: str, message: str) -> None:
            issues.append(Issue(level, code, message, entity=entity))

        for v in split_multi(value) if a.multiple else [value]:
            if v in (None, ""):
                continue
            if a.enum and str(v) not in a.enum:
                add("warning", "enum_value", f"attribute {a.name!r} value {v!r} not in {a.enum}")
            if a.type in ("integer", "number"):
                if not self._is_number(v):
                    add("warning", "wrong_type", f"attribute {a.name!r} expects a number; got {v!r}")
                else:
                    if a.min is not None and self._is_number(a.min) and float(v) < float(a.min):
                        add("error", "out_of_range", f"attribute {a.name!r} value {v!r} is under {a.min}")
                    if a.max is not None and self._is_number(a.max) and float(v) > float(a.max):
                        add("error", "out_of_range", f"attribute {a.name!r} value {v!r} is over {a.max}")
            elif a.type == "date":
                if not self._is_date(v):
                    add(
                        "warning",
                        "wrong_type",
                        f"attribute {a.name!r} expects a date as YYYY-MM-DD; got {v!r}",
                    )
                else:
                    if a.min not in (None, "") and str(v)[:10] < str(a.min)[:10]:
                        add("error", "out_of_range", f"attribute {a.name!r} value {v!r} is before {a.min}")
                    if a.max not in (None, "") and str(v)[:10] > str(a.max)[:10]:
                        add("error", "out_of_range", f"attribute {a.name!r} value {v!r} is after {a.max}")
            elif a.type == "boolean":
                if not isinstance(v, bool) and str(v).strip().lower() not in (
                    "true",
                    "false",
                    "yes",
                    "no",
                    "1",
                    "0",
                ):
                    add("warning", "wrong_type", f"attribute {a.name!r} expects yes or no; got {v!r}")
            elif a.type == "url":
                if not str(v).lower().startswith(LINK_SCHEMES):
                    add("error", "invalid_url", f"attribute {a.name!r} expects a web address; got {v!r}")
            if a.pattern and a.type in ("string", "text", "url") and not re.fullmatch(a.pattern, str(v)):
                add(
                    "error",
                    "pattern_mismatch",
                    f"attribute {a.name!r} value {v!r} does not match {a.pattern!r}",
                )
        return issues

    def _attribute_issues(
        self, defs: list[AttributeDef], attrs: dict[str, Any], owner: str, entity: str | None
    ) -> list[Issue]:
        issues: list[Issue] = []
        for a in defs:
            v = attrs.get(a.name)
            if a.required and (v is None or v == "" or (a.multiple and not split_multi(v))):
                issues.append(
                    Issue(
                        "error", "missing_attribute", f"required attribute {a.name!r} is empty", entity=entity
                    )
                )
                continue
            issues.extend(self._value_issues(a, v, entity))
        known = {a.name for a in defs}
        for k in attrs:
            if k not in known:
                issues.append(
                    Issue(
                        "info",
                        "extra_attribute",
                        f"attribute {k!r} is not declared for {owner!r}",
                        entity=entity,
                    )
                )
        return issues

    def validate_element(
        self, type_id: str, attrs: dict[str, Any] | None, entity: str | None = None
    ) -> list[Issue]:
        issues: list[Issue] = []
        t = self.types.get(type_id)
        if t is None:
            return [Issue("error", "unknown_type", f"unknown element type {type_id!r}", entity=entity)]
        if t.abstract:
            issues.append(
                Issue(
                    "error",
                    "abstract_type",
                    f"element type {t.name!r} is abstract: an element is one of its sub-types",
                    entity=entity,
                )
            )
        if not t.active:
            issues.append(
                Issue(
                    "warning",
                    "inactive_type",
                    f"element type {t.name!r} is inactive: {t.deactivation_reason}",
                    entity=entity,
                )
            )
        issues.extend(self._attribute_issues(self.attributes_for(type_id), attrs or {}, t.name, entity))
        return issues

    def validate_relationship(
        self,
        rel_type_id: str,
        src_type: str,
        dst_type: str,
        qualifier: str = "",
        entity: str | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> list[Issue]:
        r = self.rel_types.get(rel_type_id)
        if r is None:
            return [
                Issue(
                    "error",
                    "unknown_relationship_type",
                    f"unknown relationship type {rel_type_id!r}",
                    entity=entity,
                )
            ]
        issues: list[Issue] = []
        if not self.is_a(src_type, r.source):
            issues.append(
                Issue(
                    "error",
                    "disallowed_source",
                    f"{r.name!r} cannot start from {src_type!r} (expects {r.source})",
                    entity=entity,
                )
            )
        if not self.is_a(dst_type, r.target):
            issues.append(
                Issue(
                    "error",
                    "disallowed_target",
                    f"{r.name!r} cannot end at {dst_type!r} (expects {r.target})",
                    entity=entity,
                )
            )
        if r.qualifiers:
            if not qualifier:
                issues.append(
                    Issue(
                        "warning",
                        "missing_qualifier",
                        f"{r.name!r} expects a qualifier {r.qualifiers}",
                        entity=entity,
                    )
                )
            elif qualifier not in r.qualifiers:
                issues.append(
                    Issue(
                        "warning",
                        "unknown_qualifier",
                        f"qualifier {qualifier!r} not in {r.qualifiers}",
                        entity=entity,
                    )
                )
        elif qualifier:
            issues.append(
                Issue(
                    "info",
                    "unexpected_qualifier",
                    f"{r.name!r} takes no qualifier; got {qualifier!r}",
                    entity=entity,
                )
            )
        if attrs is not None and (r.attributes or attrs):
            # A relationship type that declares no attributes takes whatever an import put on
            # the edge (the validation code, say) without a word about it.
            defs = r.attributes
            if defs:
                issues.extend(self._attribute_issues(defs, attrs, r.name, entity))
        return issues

    # ------------------------------------------------------------- summary
    def summary_markdown(self, type_ids: Iterable[str] | None = None) -> str:
        """A compact description of the metamodel for people and agents."""
        lines = [
            # The name, not the identifier: this is read by people and by the agent, and an
            # identifier is opaque now (decision 0021) — neither can do anything with one.
            f"# {self.pack.name} (version {self.pack.version}, {self.pack.status})",
            "",
        ]
        wanted = set(type_ids) if type_ids else None
        for d in self.pack.domains:
            ts = [t for t in self.types_in_domain(d.id) if t.active and (wanted is None or t.id in wanted)]
            if not ts:
                continue
            lines.append(f"## {d.name}")
            for t in ts:
                sup = f" (sub-type of {t.supertype})" if t.supertype else ""
                abstract = " (abstract)" if t.abstract else ""
                attrs = ", ".join(a.name for a in t.attributes)
                lines.append(
                    f"- `{t.id}` **{t.name}**{sup}{abstract}: {t.description}"
                    + (f" Attributes: {attrs}." if attrs else "")
                )
            lines.append("")
        lines.append("## Relationship types (source -> target)")
        for r in self.pack.relationship_types:
            if (
                wanted is not None
                and r.source != ANY
                and r.target != ANY
                and not (r.source in wanted or r.target in wanted)
            ):
                continue
            q = f" qualifiers {r.qualifiers}" if r.qualifiers else ""
            a = f" attributes {[x.name for x in r.attributes]}" if r.attributes else ""
            lines.append(f"- `{r.id}`: {r.source} *{r.name}* {r.target} [{r.provenance}]{q}{a}")
        return "\n".join(lines)
