"""Graph questions: neighbourhoods, traces, impact — with names attached and a completeness footer.

**Every answer here comes from the store.** The in-process graph below is a convenience for
the callers that genuinely want the whole thing at once (the agent's overview, the view
model's whole-model pass); it is built only while the model is under the size the
application is assessed to hold in a request, and no traversal waits on it (decision 0019).
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.backend.branching import current_branch
from ea.backend.organisations import current_org
from ea.metamodel.registry import Registry
from ea.models import Element, NotFoundError


class TooLargeToHold(RuntimeError):
    """The model is past the size a request may hold in memory (`ea.capacity`)."""

    def __init__(self, elements: int, limit: int) -> None:
        super().__init__(
            f"the model holds {elements:,} elements, past the {limit:,} this application is "
            f"assessed to hold in one request; ask the store for the part you need"
        )
        self.elements, self.limit = elements, limit


class GraphService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend = backend
        self.registry = registry
        # One cached graph per organisation and branch: both decide what the graph holds, and a
        # copied organisation has the same counts as the one it was copied from, so the counts
        # alone would not tell them apart.
        self._graphs: dict[tuple[str, str], tuple[tuple[int, int], nx.DiGraph]] = {}
        self._nodes_cache: dict[str, dict[str, Any]] = {}

    # --------------------------------------------------------------- cache
    def invalidate(self) -> None:
        self._graphs.clear()
        self._nodes_cache.clear()

    def size(self) -> dict[str, Any]:
        """How large the model is against the capacity the application is assessed for."""
        return capacity.headroom(self.backend.count_elements(), self.backend.count_relationships())

    def graph(self) -> nx.DiGraph:
        """The whole graph in memory, for the current organisation and branch.

        Raises :class:`TooLargeToHold` past `capacity.GRAPH_MAX_ELEMENTS`. Nothing on a
        traversal path calls this; a caller that does is asking for the whole model on
        purpose and has to be ready for the refusal.
        """
        branch, org = current_branch(), current_org()
        elements = self.backend.count_elements()
        if capacity.too_large_to_hold(elements):
            raise TooLargeToHold(elements, capacity.GRAPH_MAX_ELEMENTS)
        key = (elements, self.backend.count_relationships())
        cached = self._graphs.get((org, branch))
        if cached is not None and cached[0] == key:
            return cached[1]
        g = nx.DiGraph()
        for e in self.backend.find_elements(limit=capacity.GRAPH_MAX_ELEMENTS):
            g.add_node(
                e.element_id,
                name=e.name,
                type_id=e.type_id,
                status=e.status,
                key=e.key,
                source=e.source_system or "",
                current_state=e.current_state,
                target_state=e.target_state,
                target_work_package=e.target_work_package or "",
            )
        for row in self.backend.edges_frame().itertuples(index=False):
            g.add_edge(
                row.src_id,
                row.dst_id,
                rel_type_id=row.rel_type_id,
                qualifier=row.qualifier
                if isinstance(row.qualifier, str)
                else "",  # NaN from the frame is not a qualifier
                relationship_id=row.relationship_id,
                target_state=row.target_state if isinstance(row.target_state, str) else "undecided",
            )
        self._graphs[(org, branch)] = (key, g)
        return g

    # ------------------------------------------------------------ helpers
    def _node(self, element_id: str) -> dict[str, Any]:
        """One element, read from the store.

        This used to build the whole in-process graph and look the element up in it — once
        for the centre of a traversal and once per row of its answer, so the walk the store
        answers in milliseconds (decision 0016) was wrapped by the enumeration it replaced.
        """
        e = self.backend.get_element(element_id)
        if e is None:
            raise NotFoundError(element_id)
        return self._element_dict(e)

    def _nodes(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """The same, for many elements, in one read per chunk."""
        return {e.element_id: self._element_dict(e) for e in self.backend.elements_by_ids(ids)}

    def _element_dict(self, e: Element) -> dict[str, Any]:
        t = self.registry.get_type(e.type_id)
        return {
            "element_id": e.element_id,
            "name": e.name,
            "type_id": e.type_id,
            "type_name": t.name if t else e.type_id,
            "status": e.status,
            "key": e.key,
            "source": e.source_system or "",
            "current_state": e.current_state,
            "target_state": e.target_state,
            "target_work_package": e.target_work_package or "",
        }

    def _edge_dict(self, u: str, v: str, data: dict[str, Any]) -> dict[str, Any]:
        rt = self.registry.rel_types.get(data.get("rel_type_id", ""))
        label = rt.name if rt else data.get("rel_type_id")
        if data.get("qualifier"):
            label = f"{label} ({data['qualifier']})"
        return {
            "relationship_id": data.get("relationship_id"),
            "src_id": u,
            "dst_id": v,
            "rel_type_id": data.get("rel_type_id"),
            "label": label,
            "qualifier": data.get("qualifier", ""),
            "target_state": data.get("target_state", "undecided") or "undecided",
        }

    def _rel_dict(self, r: Any) -> dict[str, Any]:
        """A stored relationship as the same labelled edge a graph edge produces."""
        return self._edge_dict(
            r.src_id,
            r.dst_id,
            {
                "rel_type_id": r.rel_type_id,
                "qualifier": r.qualifier or "",
                "relationship_id": r.relationship_id,
                "target_state": r.target_state or "undecided",
            },
        )

    def node(self, element_id: str) -> dict[str, Any]:
        """One element as the graph knows it (raises NotFoundError)."""
        return self._node(element_id)

    def edges_among(self, ids: list[str]) -> list[dict[str, Any]]:
        """Every relationship whose both ends are in `ids`, as labelled edge dicts, from the store."""
        return [self._rel_dict(r) for r in self.backend.edges_among(list(ids))]

    # ----------------------------------------------------------- queries
    def neighbours(
        self, element_id: str, depth: int = 1, direction: str = "both", max_nodes: int = 300
    ) -> dict[str, Any]:
        """What sits around an element, answered by the store's walk rather than in memory.

        `max_nodes` is applied to the walk's own order — nearest first, then by identifier —
        so a hub gives its closest neighbours and says it was cut, instead of an arbitrary
        slice of everything it reaches.
        """
        centre = self._node(element_id)  # raises NotFoundError
        reach = {r["element_id"]: int(r["depth"]) for r in self.backend.trace(element_id, direction, depth)}
        reach.pop(element_id, None)
        ordered = sorted(reach, key=lambda n: (reach[n], n))
        truncated = len(ordered) > max_nodes
        keep = ordered[:max_nodes]
        reach[element_id] = 0
        by_id = self._nodes([element_id, *keep])
        nodes = [dict(by_id[n], depth=reach[n]) for n in [element_id, *keep] if n in by_id]
        edges = self.edges_among([element_id, *keep])
        return {"centre": centre["element_id"], "nodes": nodes, "edges": edges, "truncated": truncated}

    def trace(
        self, element_id: str, direction: str = "out", max_depth: int = 5, rel_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self._node(element_id)
        rows = self.backend.trace(element_id, direction, max_depth)
        wanted = set(rel_types or [])
        rows = [r for r in rows if not wanted or set(r["rel_path"]) & wanted]
        # One read for every element the walk reached, rather than one per row.
        by_id = self._nodes([r["element_id"] for r in rows])
        out = []
        for r in rows:
            node = by_id.get(r["element_id"])
            if node is None:
                continue
            labels = []
            for rid in r["rel_path"]:
                rt = self.registry.rel_types.get(rid)
                labels.append(rt.name if rt else rid)
            out.append(
                dict(
                    node,
                    depth=r["depth"],
                    path=r["path"],
                    rel_path=r["rel_path"],
                    rel_labels=labels,
                    direction=direction,
                )
            )
        return out

    def impact(self, element_id: str, max_depth: int = 3) -> dict[str, Any]:
        """What depends on this element (incoming, upstream chain) and what it depends on (outgoing), with a completeness footer."""
        centre = self._node(element_id)
        upstream = self.trace(element_id, "in", max_depth)
        downstream = self.trace(element_id, "out", max_depth)
        by_type: dict[str, int] = {}
        for r in upstream + downstream:
            by_type[r["type_name"]] = by_type.get(r["type_name"], 0) + 1
        return {
            "element": centre,
            "upstream": upstream,
            "downstream": downstream,
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "completeness": self.completeness(centre["type_id"]),
        }

    def completeness(self, type_id: str) -> dict[str, Any]:
        """Which relationship types this element type could have, and how many instances exist for each — an honest footer for any impact answer."""
        by_rel = self.backend.count_by_rel_type()
        out_types, in_types = self.registry.rel_types_for_type(type_id)
        rows = []
        for r in sorted({x.id: x for x in out_types + in_types}.values(), key=lambda x: x.id):
            rows.append(
                {
                    "rel_type_id": r.id,
                    "name": r.name,
                    "source": r.source,
                    "target": r.target,
                    "instances": by_rel.get(r.id, 0),
                }
            )
        empty = [r["name"] + f" ({r['source']} -> {r['target']})" for r in rows if r["instances"] == 0]
        return {"declared": len(rows), "populated": len(rows) - len(empty), "empty": empty, "rows": rows}

    def cytoscape_elements(self, sub: dict[str, Any]) -> list[dict[str, Any]]:
        """The neighbourhood as dash-cytoscape elements."""
        out = []
        for n in sub["nodes"]:
            out.append(
                {
                    "data": {
                        "id": n["element_id"],
                        "label": n["name"],
                        "type_id": n["type_id"],
                        "type_name": n["type_name"],
                        "depth": n.get("depth", 0),
                        "centre": n["element_id"] == sub["centre"],
                    },
                    "classes": n["type_id"] + (" centre" if n["element_id"] == sub["centre"] else ""),
                }
            )
        for e in sub["edges"]:
            out.append(
                {
                    "data": {
                        "id": e["relationship_id"] or f"{e['src_id']}->{e['dst_id']}",
                        "source": e["src_id"],
                        "target": e["dst_id"],
                        "label": e["label"],
                        "rel_type_id": e["rel_type_id"],
                    }
                }
            )
        return out
