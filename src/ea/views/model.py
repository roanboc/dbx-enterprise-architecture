"""The view model: what a diagram shows, independent of how it is drawn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ea.metamodel.registry import Registry
from ea.services.graph import GraphService

# ArchiMate layers top to bottom, which is also the drawing order.
LAYER_ORDER = [
    "motivation",
    "strategy",
    "business",
    "application",
    "technology",
    "physical",
    "implementation",
    "other",
]
LAYER_TITLES = {
    "motivation": "Motivation",
    "strategy": "Strategy",
    "business": "Business",
    "application": "Application",
    "technology": "Technology",
    "physical": "Physical",
    "implementation": "Implementation & migration",
    "other": "Other",
}
DEFAULT_MAX_NODES = 60


@dataclass
class ViewNode:
    id: str
    name: str
    type_id: str
    type_name: str
    layer: str = "other"
    glyph: str = ""
    stereotype: str = ""
    shape: str = "rect"
    archimate: str = ""
    focus: bool = False
    status: str = ""
    depth: int = 0
    current_state: str = "live"
    target_state: str = "undecided"

    @property
    def label(self) -> str:
        """`glyph «Stereotype» Name`, the way the architecture documents write a node."""
        parts = [self.glyph] if self.glyph else []
        if self.stereotype:
            parts.append(f"«{self.stereotype}»")
        parts.append(self.name)
        return " ".join(parts)


@dataclass
class ViewEdge:
    src: str
    dst: str
    label: str
    rel_type_id: str = ""
    qualifier: str = ""
    target_state: str = "undecided"


@dataclass
class View:
    title: str
    focus_ids: list[str] = field(default_factory=list)
    nodes: list[ViewNode] = field(default_factory=list)
    edges: list[ViewEdge] = field(default_factory=list)
    note: str = ""
    omitted: int = 0  # nodes left out by the cap

    def layers(self) -> list[str]:
        present = {n.layer for n in self.nodes}
        return [layer for layer in LAYER_ORDER if layer in present]

    def nodes_in(self, layer: str) -> list[ViewNode]:
        return [n for n in self.nodes if n.layer == layer]

    def ids(self) -> list[str]:
        return [n.id for n in self.nodes]


def layer_rank(layer: str) -> int:
    return LAYER_ORDER.index(layer) if layer in LAYER_ORDER else len(LAYER_ORDER)


def _node(registry: Registry, d: dict[str, Any], focus: bool) -> ViewNode:
    notation = registry.notation(d.get("type_id", ""))
    return ViewNode(
        id=d["element_id"],
        name=d.get("name") or d["element_id"],
        type_id=d.get("type_id", ""),
        type_name=d.get("type_name") or d.get("type_id", ""),
        layer=notation.get("layer", "other"),
        glyph=notation.get("glyph", ""),
        stereotype=notation.get("stereotype", ""),
        shape=notation.get("shape", "rect"),
        archimate=notation.get("archimate", ""),
        focus=focus,
        status=d.get("status", "") or "",
        depth=int(d.get("depth", 0) or 0),
        current_state=d.get("current_state") or "live",
        target_state=d.get("target_state") or "undecided",
    )


def _finish(view: View) -> View:
    """Deterministic order: layer, then type, then name; edges by ends and label."""
    view.nodes.sort(key=lambda n: (layer_rank(n.layer), n.type_name, n.name.lower(), n.id))
    view.edges.sort(key=lambda e: (e.src, e.dst, e.label))
    return view


def has_state_markers(view: View) -> bool:
    """Whether anything in the view has a target state worth marking."""
    return any(
        n.target_state not in ("undecided", "keep") or n.current_state != "live" for n in view.nodes
    ) or any(e.target_state not in ("undecided", "keep") for e in view.edges)


def view_from_ids(
    registry: Registry,
    graph: GraphService,
    ids: list[str],
    title: str,
    focus_ids: list[str] | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> View:
    """The elements named plus every relationship among them, from the store."""
    focus = set(focus_ids or [])
    wanted: list[str] = []
    for i in ids:
        if i not in wanted:
            wanted.append(i)
    keep = [i for i in wanted if i in focus] + [i for i in wanted if i not in focus]
    omitted = max(0, len(keep) - max_nodes)
    keep = keep[:max_nodes]
    view = View(title=title, focus_ids=[i for i in keep if i in focus], omitted=omitted)
    known = set()
    for i in keep:
        try:
            d = graph.node(i)
        except Exception:  # noqa: BLE001 — an id the store does not know is simply not drawn
            continue
        known.add(i)
        view.nodes.append(_node(registry, d, i in focus))
    for e in graph.edges_among(list(known)):
        view.edges.append(
            ViewEdge(
                src=e["src_id"],
                dst=e["dst_id"],
                label=e["label"],
                rel_type_id=e.get("rel_type_id", "") or "",
                qualifier=e.get("qualifier", "") or "",
                target_state=e.get("target_state") or "undecided",
            )
        )
    if omitted:
        view.note = f"{omitted} more element(s) not shown."
    return _finish(view)


def view_of_change(
    registry: Registry,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    title: str,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> View:
    """A change set drawn before it exists: nodes and edges given as rows rather than read.

    A proposal's new elements have no identifier until it is applied, so they cannot be read
    from the store; each row says what to draw — `element_id` (any string that names the node
    within the view), `name`, `type_id`, `current_state`, `target_state` and `focus` for a
    node; `src`, `dst`, `label` and `target_state` for an edge. The shapes are the pack's
    notation, as every generated view's are (principle `P8`).
    """
    focus = [n for n in nodes if n.get("focus")]
    rest = [n for n in nodes if not n.get("focus")]
    keep = (focus + rest)[:max_nodes]
    omitted = max(0, len(nodes) - len(keep))
    view = View(title=title, focus_ids=[n["element_id"] for n in keep if n.get("focus")], omitted=omitted)
    for d in keep:
        t = registry.get_type(d.get("type_id", ""))
        view.nodes.append(
            _node(
                registry,
                dict(d, type_name=d.get("type_name") or (t.name if t else d.get("type_id", ""))),
                bool(d.get("focus")),
            )
        )
    present = {n.id for n in view.nodes}
    for e in edges:
        if e.get("src") in present and e.get("dst") in present:
            view.edges.append(
                ViewEdge(
                    src=e["src"],
                    dst=e["dst"],
                    label=e.get("label", ""),
                    rel_type_id=e.get("rel_type_id", "") or "",
                    qualifier=e.get("qualifier", "") or "",
                    target_state=e.get("target_state") or "undecided",
                )
            )
    if omitted:
        view.note = f"{omitted} more element(s) not shown."
    return _finish(view)


def view_from_neighbourhood(
    registry: Registry,
    graph: GraphService,
    element_id: str,
    depth: int = 1,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> View:
    sub = graph.neighbours(element_id, depth, max_nodes=max_nodes)
    centre = sub["centre"]
    name = next((n["name"] for n in sub["nodes"] if n["element_id"] == centre), centre)
    view = View(title=f"{name} and its neighbourhood (depth {depth})", focus_ids=[centre])
    for n in sub["nodes"]:
        view.nodes.append(_node(registry, n, n["element_id"] == centre))
    for e in sub["edges"]:
        view.edges.append(
            ViewEdge(
                e["src_id"],
                e["dst_id"],
                e["label"],
                e.get("rel_type_id") or "",
                e.get("qualifier") or "",
                e.get("target_state") or "undecided",
            )
        )
    if sub.get("truncated"):
        view.note = f"Neighbourhood capped at {max_nodes} elements."
    return _finish(view)


def view_from_impact(
    registry: Registry, graph: GraphService, result: dict[str, Any], max_nodes: int = DEFAULT_MAX_NODES
) -> View:
    """The impact result of :meth:`GraphService.impact` as a view: centre, upstream and downstream, and the edges among them."""
    centre = result["element"]
    ids = [centre["element_id"]]
    for row in sorted(result["upstream"] + result["downstream"], key=lambda r: (r["depth"], r["element_id"])):
        if row["element_id"] not in ids:
            ids.append(row["element_id"])
    view = view_from_ids(
        registry,
        graph,
        ids,
        title=f"Impact of {centre['name']}",
        focus_ids=[centre["element_id"]],
        max_nodes=max_nodes,
    )
    depths = {r["element_id"]: r["depth"] for r in result["upstream"] + result["downstream"]}
    for n in view.nodes:
        n.depth = depths.get(n.id, 0)
    return view


def view_from_metamodel(
    registry: Registry, domain: str | None = None, include_inactive: bool = False
) -> View:
    """The metamodel itself as a view: one node per element type in the type's own notation,
    one edge per relationship type, sub-types joined to their supertype; a diamond stands for
    `ANY`. What the architecture documents call a notation diagram, drawn from the pack."""
    from ea.models import ANY

    types = [
        t
        for t in registry.pack.element_types
        if (t.active or include_inactive) and (not domain or t.domain == domain)
    ]
    ids = {t.id for t in types}
    title = registry.pack.name + (f" — {registry.domains[domain].name}" if domain in registry.domains else "")
    view = View(title=f"{title} (version {registry.pack.version})")
    for t in types:
        n = registry.notation(t.id)
        view.nodes.append(
            ViewNode(
                id=t.id,
                name=t.name,
                type_id=t.id,
                type_name=t.name,
                layer=n.get("layer", "other"),
                glyph=n.get("glyph", ""),
                stereotype=n.get("stereotype", ""),
                shape=n.get("shape", "rect"),
                archimate=n.get("archimate", ""),
                status="active" if t.active else "inactive",
            )
        )
    need_any = False
    for r in registry.pack.relationship_types:
        src, dst = r.source, r.target
        if (src != ANY and src not in ids) or (dst != ANY and dst not in ids):
            continue
        need_any = need_any or src == ANY or dst == ANY
        view.edges.append(ViewEdge(src=src, dst=dst, label=r.name, rel_type_id=r.id))
    for t in types:
        if t.supertype and t.supertype in ids:
            view.edges.append(ViewEdge(src=t.id, dst=t.supertype, label="is a", rel_type_id=f"sub:{t.id}"))
    if need_any:
        view.nodes.append(
            ViewNode(
                id=ANY,
                name="Any element",
                type_id="",
                type_name="",
                layer="other",
                glyph="◇",
                shape="diamond",
            )
        )
    return _finish(view)


def view_to_dict(view: View) -> dict[str, Any]:
    return asdict(view)


def view_from_dict(d: dict[str, Any]) -> View:
    return View(
        title=d.get("title", ""),
        focus_ids=list(d.get("focus_ids") or []),
        nodes=[ViewNode(**n) for n in d.get("nodes") or []],
        edges=[ViewEdge(**e) for e in d.get("edges") or []],
        note=d.get("note", ""),
        omitted=int(d.get("omitted", 0) or 0),
    )
