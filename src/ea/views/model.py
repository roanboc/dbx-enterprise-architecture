"""The view model: what a diagram shows, independent of how it is drawn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ea.metamodel.registry import Registry
from ea.models import Viewpoint
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
    #: Set by `apply_viewpoint` under a viewpoint that bands by a related element: `band` is the
    #: identifier of the element whose band this node sits in (`""`: the viewpoint's other band),
    #: and `is_band` marks the band elements themselves, which are drawn as bands, not as shapes.
    band: str = ""
    is_band: bool = False

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
    #: The ArchiMate relationship the edge is drawn as, from the relationship type's notation
    #: (`""` when the type names none: a plain directed line), and whether the standard's
    #: direction runs from `dst` to `src` — the whole, the assigner, the realiser at the target.
    archimate: str = ""
    reversed: bool = False

    @property
    def whole(self) -> str:
        """The end that contains, assigns or is realised: `src` unless the notation runs in reverse."""
        return self.dst if self.reversed else self.src

    @property
    def part(self) -> str:
        return self.src if self.reversed else self.dst


@dataclass
class View:
    title: str
    focus_ids: list[str] = field(default_factory=list)
    nodes: list[ViewNode] = field(default_factory=list)
    edges: list[ViewEdge] = field(default_factory=list)
    note: str = ""
    omitted: int = 0  # nodes left out by the cap
    viewpoint: str = ""  # the viewpoint the view was filtered through, when one was (decision 0023)
    detail: str = "full"  # one of DETAIL_LEVELS: "overview" once `overview()` has thinned the view

    def layers(self) -> list[str]:
        present = {n.layer for n in self.nodes}
        return [layer for layer in LAYER_ORDER if layer in present]

    def nodes_in(self, layer: str) -> list[ViewNode]:
        return [n for n in self.nodes if n.layer == layer]

    def ids(self) -> list[str]:
        return [n.id for n in self.nodes]


def layer_rank(layer: str) -> int:
    return LAYER_ORDER.index(layer) if layer in LAYER_ORDER else len(LAYER_ORDER)


#: The two levels of detail a view is exported at. An overview is the reader's default: the
#: focus, its direct neighbours and the band elements, every relationship touching the focus
#: and only the structural kinds among the rest, parallel lines merged into one, and at most
#: OVERVIEW_MAX_NODES elements — the practitioner's ceiling for one drawing. Full is everything.
DETAIL_LEVELS = ("overview", "full")
OVERVIEW_MAX_NODES = 30
#: The ArchiMate relationships an overview keeps between elements other than the focus, when
#: the viewpoint names none of its own: the ones that say what is made of, realised by, assigned
#: to, served by or followed by what. Access, association and influence go — they are the lines
#: that turn a drawing into a net.
OVERVIEW_KINDS = frozenset(
    {"composition", "aggregation", "realization", "assignment", "serving", "triggering", "flow"}
)

#: The drawing every pack gets without a viewpoint of its own: one band per architecture
#: layer, every element and every relationship, nothing nested and nothing spanned.
DEFAULT_VIEWPOINT = Viewpoint(
    id="layered", name="Layered", description="Every element, in a band per architecture layer."
)


def _edge(registry: Registry, e: dict[str, Any]) -> ViewEdge:
    notation = registry.rel_notation(e.get("rel_type_id", "") or "")
    return ViewEdge(
        src=e["src_id"],
        dst=e["dst_id"],
        label=e["label"],
        rel_type_id=e.get("rel_type_id", "") or "",
        qualifier=e.get("qualifier", "") or "",
        target_state=e.get("target_state") or "undecided",
        archimate=notation.get("archimate", ""),
        reversed=notation.get("direction") == "reverse",
    )


def overview(view: View, viewpoint: Viewpoint | None = None, max_nodes: int = OVERVIEW_MAX_NODES) -> View:
    """The view thinned to its key elements and lines (`DETAIL_LEVELS`), by a rule a reader can
    predict rather than a judgement:

    - a relationship touching the focus is kept; between the others only a structural kind is —
      the viewpoint's `overview_relationships` when it names any, else `OVERVIEW_KINDS` by the
      type's notation — and so is any relationship the viewpoint nests, spans or bands by;
    - the elements kept are the focus, the band elements, and whatever the focus still reaches
      through the lines kept, as far as the view goes: the depth the reader chose still counts,
      along structural lines. A view with no focus (the whole target state, the metamodel)
      keeps every element;
    - several relationships between one pair of elements become one line labelled with every
      verb, drawn as their common kind or as a plain line when the kinds differ;
    - above `max_nodes` elements the least connected go, the focus and the bands never.

    The note says what was left out, in numbers. Nothing here reads the store.
    """
    vp = viewpoint or DEFAULT_VIEWPOINT
    ids = {n.id for n in view.nodes}
    focus = set(view.focus_ids) & ids
    structural = set(vp.overview_relationships)
    always = set(vp.nest) | set(vp.span) | set(vp.band_relationships)

    def kept_edge(e: ViewEdge) -> bool:
        if e.src not in ids or e.dst not in ids:
            return False
        if e.src in focus or e.dst in focus or e.rel_type_id in always:
            return True
        return e.rel_type_id in structural if structural else e.archimate in OVERVIEW_KINDS

    edges = [e for e in view.edges if kept_edge(e)]
    if focus:
        reached, frontier = set(focus), list(focus)
        while frontier:
            here = frontier.pop()
            for e in edges:
                other = e.dst if e.src == here else e.src if e.dst == here else None
                if other is not None and other not in reached:
                    reached.add(other)
                    frontier.append(other)
        kept_ids = reached | {n.id for n in view.nodes if n.is_band}
        edges = [e for e in edges if e.src in kept_ids and e.dst in kept_ids]
    else:
        kept_ids = set(ids)
    dropped_over = 0
    if len(kept_ids) > max_nodes:
        degree: dict[str, int] = {}
        for e in edges:
            degree[e.src] = degree.get(e.src, 0) + 1
            degree[e.dst] = degree.get(e.dst, 0) + 1
        by_id = {n.id: n for n in view.nodes}
        pinned = {i for i in kept_ids if i in focus or by_id[i].is_band}
        loose = sorted(
            (i for i in kept_ids if i not in pinned),
            key=lambda i: (-degree.get(i, 0), by_id[i].name.lower(), i),
        )
        room = max(0, max_nodes - len(pinned))
        dropped_over = len(loose) - room
        kept_ids = pinned | set(loose[:room])
        edges = [e for e in edges if e.src in kept_ids and e.dst in kept_ids]
    nodes = [n for n in view.nodes if n.id in kept_ids]
    merged: dict[tuple[str, str], ViewEdge] = {}
    for e in edges:
        key = (e.src, e.dst)
        if key not in merged:
            merged[key] = ViewEdge(**dict(e.__dict__))
            continue
        m = merged[key]
        if e.label not in m.label.split(", "):
            m.label = f"{m.label}, {e.label}"
        if (e.archimate, e.reversed) != (m.archimate, m.reversed):
            m.archimate, m.reversed = "", False  # the kinds differ: a plain line carries the verbs
    out = View(
        title=view.title,
        focus_ids=[i for i in view.focus_ids if i in kept_ids],
        nodes=nodes,
        edges=list(merged.values()),
        note=view.note,
        omitted=view.omitted,
        viewpoint=view.viewpoint,
        detail="overview",
    )
    left_nodes = len(view.nodes) - len(nodes)
    left_edges = len(view.edges) - len(out.edges)
    said: list[str] = []
    if left_nodes or left_edges:
        parts = ([f"{left_nodes} element(s)"] if left_nodes else []) + (
            [f"{left_edges} relationship(s)"] if left_edges else []
        )
        said.append(f"Overview: {' and '.join(parts)} not drawn.")
    if dropped_over:
        said.append(f"{dropped_over} of them the least connected, above the {max_nodes} an overview holds.")
    if said:
        out.note = f"{view.note} {' '.join(said)}".strip()
    return out


def _assign_bands(nodes: list[ViewNode], edges: list[ViewEdge], vp: Viewpoint, registry: Registry) -> None:
    """Under bands by a related element: mark the band elements, and give every other node the
    band of the first band element (by name, then identifier) a band relationship joins it to."""
    is_band = {n.id for n in nodes if n.type_id == vp.band_type or registry.is_a(n.type_id, vp.band_type)}
    by_id = {n.id: n for n in nodes}
    wanted = set(vp.band_relationships)
    for n in nodes:
        n.is_band = n.id in is_band
        n.band = ""
    candidates: dict[str, list[str]] = {}
    for e in edges:
        if wanted and e.rel_type_id not in wanted:
            continue
        for me, other in ((e.src, e.dst), (e.dst, e.src)):
            if other in is_band and me not in is_band:
                candidates.setdefault(me, []).append(other)
    for nid, bands in candidates.items():
        by_id[nid].band = sorted(bands, key=lambda b: (by_id[b].name.lower(), b))[0]


def apply_viewpoint(
    view: View, viewpoint: Viewpoint | None, registry: Registry, layers: list[str] | None = None
) -> View:
    """The view narrowed to what a viewpoint admits: its element types (a sub-type counts as its
    supertype), its relationship types, and the architecture layers the reader kept. An edge
    goes with either end it loses. The focus stays whatever the filter says, because a reader
    who asked about an element is told when the viewpoint has nothing to show for it, in `note`.
    """
    vp = viewpoint or DEFAULT_VIEWPOINT
    keep_layers = set(layers) if layers else None

    def admitted(n: ViewNode) -> bool:
        if keep_layers is not None and n.layer not in keep_layers:
            return False
        if not vp.element_types:
            return True
        return any(n.type_id == t or registry.is_a(n.type_id, t) for t in vp.element_types)

    nodes = [n for n in view.nodes if admitted(n)]
    ids = {n.id for n in nodes}
    rels = set(vp.relationship_types)
    edges = [
        e
        for e in view.edges
        if e.src in ids and e.dst in ids and (not rels or e.rel_type_id in rels or not e.rel_type_id)
    ]
    if vp.bands == "related":
        _assign_bands(nodes, edges, vp, registry)
    dropped = len(view.nodes) - len(nodes)
    out = View(
        title=view.title,
        focus_ids=[i for i in view.focus_ids if i in ids],
        nodes=nodes,
        edges=edges,
        note=view.note,
        omitted=view.omitted,
        viewpoint=vp.id,
    )
    if dropped:
        said = f"{dropped} element(s) outside the {vp.name} viewpoint not shown."
        out.note = f"{view.note} {said}".strip()
    lost_focus = [i for i in view.focus_ids if i not in ids]
    if lost_focus:
        out.note = f"{out.note} The focus ({', '.join(lost_focus)}) is outside this viewpoint.".strip()
    return out


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
        view.edges.append(_edge(registry, e))
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
        view.edges.append(_edge(registry, e))
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
        view.edges.append(
            ViewEdge(
                src=src, dst=dst, label=r.name, rel_type_id=r.id, archimate=r.archimate, reversed=r.reversed
            )
        )
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
        viewpoint=d.get("viewpoint", "") or "",
        detail=d.get("detail", "") or "full",
    )
