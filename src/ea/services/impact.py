"""The impact of a change set (DOBJ3.10): what it touches beyond itself.

For every element a change changes, decommissions or merges: the elements connected to it on
`main` within two steps, upstream and downstream along every relationship, that are not
themselves in the change. A path keeps to one direction, so what shares a platform with the
element is not reached through the platform. For every element it decommissions or merges: the relationships on
`main` it leaves pointing at that element, unless the change retires them too. For every new
element: whether the change's own relationships connect it to anything that exists. And for
every type it touches: who must review it.

Everything is read on `main`, the model as it stands, and read by the store's walk (decisions
0016 to 0018) rather than the in-process graph. It is bounded — at most `MAX_CHANGED` walks
and `MAX_REACHED` rows, with `truncated` saying when it was cut (decision 0019). Two steps
along every relationship is a blunt measure: a pack declares no direction of dependency per
relationship type yet, so what reaches an element and what it reaches count alike.

It informs and never stops an Apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, use_branch
from ea.metamodel.registry import Registry
from ea.models import ChangeImpact

#: Target states that change an element that exists.
CHANGING = ("change", "decommission", "merge")
#: Target states after which an element is no longer there to point at.
RETIRING = ("decommission", "merge")


@dataclass
class ChangeInput:
    """A change set in the terms an assessment needs, whether it came from a proposal or a branch.

    Element references are identifiers for what exists, and any other string (a proposal's
    `new:<name>`, or a branch's new identifier) for what the change creates.
    """

    changed: dict[str, str] = field(default_factory=dict)  # existing element id → target state
    new: list[dict[str, str]] = field(default_factory=list)  # {ref, name, type_id}
    links: list[tuple[str, str]] = field(default_factory=list)  # ends of the relationships it adds
    retired_relationships: set[str] = field(default_factory=set)
    named: set[str] = field(default_factory=set)  # existing elements the change names at all
    touched_types: list[str] = field(default_factory=list)


class ChangeImpactService:
    DEPTH = 2
    MAX_CHANGED = 100
    MAX_REACHED = 200

    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend, self.registry = backend, registry

    # ------------------------------------------------------------ assess
    def assess(self, change: ChangeInput) -> ChangeImpact:
        with use_branch(MAIN):
            impact = ChangeImpact(depth=self.DEPTH)
            in_change = set(change.changed) | set(change.named)
            walked = list(change.changed.items())
            impact.truncated = len(walked) > self.MAX_CHANGED
            walked = walked[: self.MAX_CHANGED]
            held = {e.element_id: e for e in self.backend.elements_by_ids([eid for eid, _ in walked])}
            impact.changed = [
                {
                    "element_id": eid,
                    "name": held[eid].name,
                    "type": self._type_name(held[eid].type_id),
                    "target_state": state,
                }
                for eid, state in walked
                if eid in held
            ]
            impact.reached = self._reached([eid for eid, _ in walked if eid in held], in_change, held)
            if len(impact.reached) >= self.MAX_REACHED:
                impact.truncated = True
            retiring = {eid for eid, state in walked if state in RETIRING and eid in held}
            impact.dangling = self._dangling(retiring, change.retired_relationships, held)
            impact.isolated = self._isolated(change)
            impact.reviewers = self._reviewers(change.touched_types)
            return impact

    def of_branch(self, branch_id: str) -> ChangeImpact:
        """The impact of everything a branch changes against `main`."""
        return self.assess(self.branch_change(branch_id))

    def branch_change(self, branch_id: str) -> ChangeInput:
        change = ChangeInput()
        for it in self.backend.diff_branch(branch_id).items:
            row = it.after or it.before or {}
            if it.kind == "element":
                t = row.get("type_id") or ""
                if t and t not in change.touched_types:
                    change.touched_types.append(t)
                if it.change == "added":
                    change.new.append(
                        {"ref": it.entity_id, "name": row.get("name") or it.entity_id, "type_id": t}
                    )
                    continue
                change.named.add(it.entity_id)
                if it.change == "deleted":
                    change.changed[it.entity_id] = "decommission"
                elif (it.after or {}).get("target_state") in CHANGING:
                    change.changed[it.entity_id] = it.after["target_state"]
            else:
                if it.change == "deleted" or (it.after or {}).get("target_state") == "decommission":
                    change.retired_relationships.add(it.entity_id)
                elif row.get("src_id") and row.get("dst_id"):
                    change.links.append((row["src_id"], row["dst_id"]))
        return change

    # ------------------------------------------------------------- parts
    def _type_name(self, type_id: str) -> str:
        t = self.registry.get_type(type_id)
        return t.name if t else type_id

    def _rel_name(self, rel_type_id: str) -> str:
        r = self.registry.rel_types.get(rel_type_id)
        return r.name if r else rel_type_id

    def _reached(self, walked: list[str], in_change: set[str], held: dict) -> list[dict]:
        best: dict[str, dict] = {}
        for eid in walked:
            for direction in ("in", "out"):
                for r in self.backend.trace(eid, direction, self.DEPTH):
                    nid = r["element_id"]
                    if nid in in_change or nid == eid:
                        continue
                    if nid not in best or r["depth"] < best[nid]["depth"]:
                        best[nid] = {
                            "element_id": nid,
                            "depth": int(r["depth"]),
                            "via": eid,
                            "via_name": held[eid].name,
                            "direction": direction,
                            "path": [self._rel_name(x) for x in r["rel_path"]],
                        }
        ordered = sorted(best.values(), key=lambda d: (d["depth"], d["via"], d["element_id"]))[
            : self.MAX_REACHED
        ]
        named = {e.element_id: e for e in self.backend.elements_by_ids([d["element_id"] for d in ordered])}
        out = []
        for d in ordered:
            e = named.get(d["element_id"])
            if e is not None:
                out.append(dict(d, name=e.name, type=self._type_name(e.type_id)))
        return out

    def _dangling(self, retiring: set[str], retired: set[str], held: dict) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        ends: dict[str, str] = {}
        for eid in sorted(retiring):
            for rel in self.backend.relationships_of(eid, "both"):
                if rel.relationship_id in retired or rel.relationship_id in seen:
                    continue
                other = rel.dst_id if rel.src_id == eid else rel.src_id
                if other in retiring:
                    continue  # both ends leave together
                seen.add(rel.relationship_id)
                ends.setdefault(other, "")
                out.append(
                    {
                        "relationship_id": rel.relationship_id,
                        "relationship": self._rel_name(rel.rel_type_id),
                        "src_id": rel.src_id,
                        "dst_id": rel.dst_id,
                        "retiring": eid,
                        "retiring_name": held[eid].name,
                        "other": other,
                    }
                )
        named = {e.element_id: e.name for e in self.backend.elements_by_ids(list(ends))}
        for d in out:
            d["other_name"] = named.get(d["other"], d["other"])
        return out

    @staticmethod
    def _isolated(change: ChangeInput) -> list[dict]:
        """New elements whose component, over the change's own relationships, holds nothing that exists."""
        new_refs = {n["ref"] for n in change.new}
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in change.links:
            parent[find(a)] = find(b)
        anchored = {find(x) for x in list(parent) if x not in new_refs}
        return [
            {"ref": n["ref"], "name": n["name"], "type_id": n.get("type_id", "")}
            for n in change.new
            if find(n["ref"]) not in anchored
        ]

    def _reviewers(self, types: list[str]) -> list[dict]:
        assigned = self.backend.list_reviewer_assignments()
        return [
            {"type_id": t, "type": self._type_name(t), "reviewers": list(assigned.get(t, []))}
            for t in dict.fromkeys(types)
            if t
        ]
