"""A layered layout for an exported drawing, in the application's own code (decision 0024).

The bands come from the viewpoint (decision 0023): by architecture layer, by element type, or
by a related element of a named type. Within a band the order is chosen so that the lines to
the neighbouring bands cross as little as possible; a shape is sized to its name; a nested
shape sits inside the whole that holds it; a spanning shape is a bar across the shapes it
relates to; and every edge is given the side it leaves and enters. Everything here is
deterministic: the same view and the same viewpoint give the same drawing, which the golden
files under `tests/golden/drawio/` hold it to. No step draws a random number, reads a clock or
walks a set: every tie is broken on a name and an identifier.

The screens keep the browser's layout; this is for the file, which the command line and the
agent export without a browser.
"""

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass, field

import networkx as nx

from ea.models import Viewpoint
from ea.views.model import DEFAULT_VIEWPOINT, LAYER_TITLES, View, ViewNode, layer_rank

# Shape sizing, in draw.io units (pixels at 100%). A 14-point name reads on a printed page.
FONT_SIZE = 14
NODE_W, NODE_H = 180, 70
NODE_W_MAX, WRAP_CHARS, CHAR_W, LINE_H = 300, 22, 8.0, 19
GAP_X, GAP_Y = 40, 60  # between shapes in a band, and between bands (and between rows of one band)
BAND_PAD, BAND_HEADER = 24, 32  # inside a band: padding, and the room its title takes
NEST_PAD, NEST_HEADER = 16, 34  # inside a nesting shape
MARGIN = 40
MAX_ROW_W = 1600  # a band whose shapes would run wider than this wraps them onto a new row
SWEEPS = 4  # barycentre passes down and back up; the order settles in a handful
PORT_MIN, PORT_MAX = 0.2, 0.8  # where along a side the ports of one shape are spread


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Band:
    key: str  # the layer, the type id, or the band element's id; `other` for the rest
    title: str
    box: Box
    nodes: list[str] = field(default_factory=list)  # the top-level shapes in it, in drawing order
    element_id: str = ""  # bands=related: the element the band stands for (drawn as the band, not as a shape)


@dataclass
class Route:
    """Where an edge leaves its source and enters its target, as fractions of each shape's
    width and height (draw.io's exitX/exitY and entryX/entryY), and the bends in between,
    in absolute coordinates."""

    exit: tuple[float, float]
    entry: tuple[float, float]
    points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Layout:
    boxes: dict[str, Box]  # every drawn node, absolute coordinates (a nested child's too)
    bands: list[Band]  # in drawing order, top to bottom
    parents: dict[str, str] = field(default_factory=dict)  # child -> the node it is drawn inside
    spans: set[str] = field(default_factory=set)  # nodes drawn as a bar across what they relate to
    #: Edge indexes the drawing shows some other way than as a line: as nesting, as a span, as
    #: membership of a band, or not at all because an end is a band element (noted in `notes`).
    hidden_edges: set[int] = field(default_factory=set)
    routes: dict[int, Route] = field(default_factory=dict)  # by index in `view.edges`
    band_elements: set[str] = field(default_factory=set)  # nodes drawn as a band rather than a shape
    notes: list[str] = field(default_factory=list)  # what the drawing could not show as asked, in words
    width: float = 0.0  # content bounds, margins included
    height: float = 0.0


def node_size(n: ViewNode) -> tuple[int, int]:
    """A box wide enough for the name in it, at the font the file uses.

    Every shape the same size turns an export into a grid of identical rectangles with the
    names trimmed inside them — a picture of the layout rather than of the model.
    """
    label = f"{n.glyph} {n.name}".strip() or n.id
    lines = textwrap.wrap(label, WRAP_CHARS) or [label]
    widest = max(len(line) for line in lines)
    width = max(NODE_W, min(NODE_W_MAX, int(widest * CHAR_W) + 32))
    height = max(NODE_H, 28 + len(lines) * LINE_H)
    return width, height


def layout(
    view: View, viewpoint: Viewpoint | None = None, sizes: dict[str, tuple[int, int]] | None = None
) -> Layout:
    """The drawing of a view under a viewpoint: bands, shapes, nesting, spans and routes.

    The bands come from `band_members`. A relationship the viewpoint nests puts the part inside the
    whole, which grows to hold its children in a small grid; one it spans turns the bar end
    into a bar across the shapes related to it, in a row of its own at the bottom of its band.
    What is left is ordered within each band by a barycentre sweep over the edges to the
    neighbouring bands, so the lines cross as little as possible, placed left to right, and
    pulled under the mean of its neighbours in the band above where there is room. A band
    wider than `MAX_ROW_W` wraps onto more rows. `sizes` overrides the measured size of a
    shape (the browser's, when the export follows an arrangement).
    """
    vp = viewpoint or DEFAULT_VIEWPOINT
    by_id = {n.id: n for n in view.nodes}
    own = {k: (int(w), int(h)) for k, (w, h) in (sizes or {}).items()}
    for n in view.nodes:
        own.setdefault(n.id, node_size(n))
    bands = band_members(view, vp)
    out = Layout(boxes={}, bands=bands, band_elements={b.element_id for b in bands if b.element_id})
    drawn = {n.id for n in view.nodes if n.id not in out.band_elements}
    hide_band_edges(view, bands, out, by_id)
    sources = _spans(view, vp, drawn, out)
    _nest(view, vp, drawn, out, by_id)
    sizes_grown, offsets, children = _grow(own, out.parents, by_id)
    order_key = _order_key(by_id)

    # A nested part leaves its band; a band left with nothing is not drawn, unless it stands
    # for an element (a role with no process is still a swimlane of its own).
    for band in bands:
        band.nodes = [nid for nid in band.nodes if nid not in out.parents]
    bands = [b for b in bands if b.nodes or b.element_id]
    out.bands = bands
    orders = [sorted((n for n in b.nodes if n not in out.spans), key=order_key) for b in bands]
    adj = _adjacency(view, out, orders)
    orders = _sweep(orders, adj, order_key)

    # Rows and the bands' heights, then every shape at its compact place.
    rows_of: list[list[list[str]]] = []
    bars_of: list[list[str]] = []  # per band, its spanning nodes
    y = float(MARGIN)
    for bi, band in enumerate(bands):
        rows = _wrap(orders[bi], sizes_grown)
        rows_of.append(rows)
        row_h = [max(sizes_grown[n][1] for n in row) for row in rows]
        bars_of.append([n for n in band.nodes if n in out.spans])
        body = sum(row_h) + GAP_Y * max(0, len(rows) - 1)
        band.box = Box(MARGIN, y, 0, BAND_HEADER + 2 * BAND_PAD + body)
        ry = y + BAND_HEADER + BAND_PAD
        for row, h in zip(rows, row_h, strict=True):
            x = float(MARGIN + BAND_PAD)
            for n in row:
                out.boxes[n] = Box(x, ry, *sizes_grown[n])
                x += sizes_grown[n][0] + GAP_X
            ry += h + GAP_Y
        y = band.box.bottom + GAP_Y

    # Pull each shape under the mean of its neighbours in the band above. The top band has
    # none, so it is pulled towards the band below it first, while that band is still compact.
    if len(bands) > 1:
        for row in rows_of[0]:
            _align_row(row, out.boxes, adj, set(orders[1]))
    for bi in range(1, len(bands)):
        for row in rows_of[bi]:
            _align_row(row, out.boxes, adj, set(orders[bi - 1]))

    for bi, band in enumerate(bands):
        band.nodes = [n for row in rows_of[bi] for n in row]
        for n in band.nodes:
            _place_children(n, out.boxes, sizes_grown, offsets, children)
    # The bars' rows are known only now, once every source (a nested one included) has its
    # final x: a band grows by the rows its bars take, and every band under it moves down by
    # the same amount, its nested children with it.
    _place_bars(bands, bars_of, rows_of, sources, own, out, by_id)

    content_right = max((b.right for b in out.boxes.values()), default=MARGIN + NODE_W + BAND_PAD)
    width = content_right + BAND_PAD - MARGIN
    for band in bands:
        band.box.w = width
    out.width = MARGIN + width + MARGIN if bands else 2 * MARGIN
    out.height = bands[-1].box.bottom + MARGIN if bands else 2 * MARGIN
    out.routes = routes_for(view, out.boxes, out.parents, hidden=out.hidden_edges)
    return out


def band_members(view: View, vp: Viewpoint) -> list[Band]:
    """The bands a viewpoint gives a view and which node sits in which, in drawing order, before
    anything is placed (every box is empty). By layer: the viewpoint's order first, then the
    layers' own, only the bands that hold something. By type: the viewpoint's order first, then
    the remaining types in view order, titled with the type's name. By a related element: a band
    per band element, ordered by name, drawn even when empty, and a last band the viewpoint names
    for what no band element claims. Under bands by a related element the membership is what
    `apply_viewpoint` marked on the nodes (`ViewNode.band`, `ViewNode.is_band`); a view that was
    never filtered falls back to an exact match on the band type. The export from a browser
    arrangement uses this to draw the bands around the shapes where the reader left them.
    """
    if vp.bands == "type":
        order = list(vp.band_order)
        for n in view.nodes:
            if n.type_id not in order:
                order.append(n.type_id)
        titles = {n.type_id: n.type_name for n in view.nodes}
        groups = {t: [n.id for n in view.nodes if n.type_id == t] for t in order}
        return [Band(t, titles.get(t, t), Box(0, 0, 0, 0), ids) for t, ids in groups.items() if ids]
    if vp.bands == "related":
        by_id = {n.id: n for n in view.nodes}
        band_ids = [
            n.id
            for n in view.nodes
            if n.is_band or (not any(m.is_band for m in view.nodes) and n.type_id == vp.band_type)
        ]
        bands = [
            Band(
                b,
                by_id[b].name,
                Box(0, 0, 0, 0),
                [n.id for n in view.nodes if n.band == b and n.id != b],
                element_id=b,
            )
            for b in sorted(band_ids, key=lambda b: (by_id[b].name.lower(), b))
        ]
        rest = [n.id for n in view.nodes if n.id not in band_ids and n.band not in band_ids]
        if rest:
            bands.append(Band("other", vp.other_band, Box(0, 0, 0, 0), rest))
        return bands
    order = [layer for layer in vp.band_order if layer] or []
    layers = sorted(view.layers(), key=layer_rank)
    for layer in layers:
        if layer not in order:
            order.append(layer)
    return [
        Band(layer, LAYER_TITLES.get(layer, layer), Box(0, 0, 0, 0), [n.id for n in view.nodes_in(layer)])
        for layer in order
        if view.nodes_in(layer)
    ]


def routes_for(
    view: View,
    boxes: dict[str, Box],
    parents: dict[str, str] | None = None,
    hidden: set[int] | None = None,
) -> dict[int, Route]:
    """A port at each end of every edge whose ends are drawn: bottom to top when the target sits
    under the source, top to bottom when above, side to side when they share a row. The ports
    of one shape are spread along each side in the order of the other ends, so no two edges
    leaving (or entering) a shape the same way share a point. Two shapes side by side with a
    third between them are joined over the top of the row, with a bend at each end, so the line
    does not run through the shape between. An edge to or from a nested child uses the child's
    own box; one in `hidden` is left out because the drawing shows it some other way. A line
    that is left between a whole and a shape inside it (a second relationship between them,
    or the edge a cycle could not nest) runs from the whole's own name down to the child.
    """
    parents = parents or {}
    hidden = hidden or set()
    sides: dict[int, tuple[str, str]] = {}
    detour: set[int] = set()
    for i, e in enumerate(view.edges):
        a, b = boxes.get(e.src), boxes.get(e.dst)
        if i in hidden or a is None or b is None:
            continue
        if e.src == e.dst:
            sides[i] = ("right", "top")
        elif _holds(parents, e.src, e.dst) or _holds(parents, e.dst, e.src):
            sides[i] = ("top", "top")
        elif b.y >= a.bottom:
            sides[i] = ("bottom", "top")
        elif b.bottom <= a.y:
            sides[i] = ("top", "bottom")
        elif b.x >= a.right or b.right <= a.x:
            if _something_between(boxes, a, b, (e.src, e.dst)):
                sides[i] = ("top", "top")
                detour.add(i)
            else:
                sides[i] = ("right", "left") if b.x >= a.right else ("left", "right")
        else:  # the boxes overlap: one holds the other but not as its own part
            sides[i] = ("bottom", "top") if b.cy >= a.cy else ("top", "bottom")

    # Spread the ports: everything that touches one side of one shape, exits and entries alike,
    # ordered by where the other end is, so the lines fan out without crossing at the shape.
    groups: dict[tuple[str, str], list[tuple[float, int, bool]]] = {}
    for i, (exit_side, entry_side) in sides.items():
        e = view.edges[i]
        a, b = boxes[e.src], boxes[e.dst]
        groups.setdefault((e.src, exit_side), []).append((_along(b, exit_side), i, True))
        groups.setdefault((e.dst, entry_side), []).append((_along(a, entry_side), i, False))
    ports: dict[tuple[int, bool], tuple[float, float]] = {}
    for (_, side), items in groups.items():
        items.sort()
        for j, (_, i, is_exit) in enumerate(items):
            t = 0.5 if len(items) == 1 else round(PORT_MIN + (PORT_MAX - PORT_MIN) * j / (len(items) - 1), 3)
            ports[(i, is_exit)] = {"top": (t, 0.0), "bottom": (t, 1.0), "left": (0.0, t), "right": (1.0, t)}[
                side
            ]

    routes: dict[int, Route] = {}
    for i in sides:
        e = view.edges[i]
        exit_port, entry_port = ports[(i, True)], ports[(i, False)]
        points: list[tuple[float, float]] = []
        if i in detour:
            a, b = boxes[e.src], boxes[e.dst]
            wy = min(a.y, b.y) - BAND_PAD / 2  # between the band's title and its shapes
            points = [(round(a.x + exit_port[0] * a.w), wy), (round(b.x + entry_port[0] * b.w), wy)]
        routes[i] = Route(exit=exit_port, entry=entry_port, points=points)
    return routes


# ------------------------------------------------------------------ the steps of `layout`


def _order_key(by_id: dict[str, ViewNode]):
    """The tie-break everywhere: the focus first, then the name, then the identifier."""
    return lambda nid: (not by_id[nid].focus, by_id[nid].name.lower(), nid)


def hide_band_edges(view: View, bands: list[Band], out: Layout, by_id: dict[str, ViewNode]) -> None:
    """Under bands by a related element, an edge to a band element cannot be a line: the
    element is a band, not a shape. To the node's own band it is the membership the band already
    shows; to another band it is said in a note, once per node."""
    if not out.band_elements:
        return
    title = {b.element_id: b.title for b in bands if b.element_id}
    elsewhere: dict[str, list[str]] = {}
    for i, e in enumerate(view.edges):
        ends = [x for x in (e.src, e.dst) if x in out.band_elements]
        if not ends:
            continue
        out.hidden_edges.add(i)
        if len(ends) == 2:
            continue
        band_el = ends[0]
        node = e.dst if e.src == band_el else e.src
        if node not in by_id or by_id[node].band == band_el:
            continue
        names = elsewhere.setdefault(node, [])
        if title[band_el] not in names:
            names.append(title[band_el])
    for node in sorted(elsewhere, key=lambda n: (by_id[n].name.lower(), n)):
        out.notes.append(f"{by_id[node].name} also relates to {'; '.join(sorted(elsewhere[node]))}")


def _spans(view: View, vp: Viewpoint, drawn: set[str], out: Layout) -> dict[str, list[str]]:
    """The nodes drawn as a bar, and for each the shapes it spans (the other ends of its span
    edges, when drawn). A bar needs two shapes to span: a spanning node with one drawn source,
    or none, stays an ordinary shape joined to it by a line, because four entities stacked one
    under the other beneath the one application that holds them is a column, not a picture of
    what spans what."""
    wanted = set(vp.span)
    sources: dict[str, list[str]] = {}
    if not wanted:
        return sources
    edges_of: dict[str, list[int]] = {}
    for i, e in enumerate(view.edges):
        if e.rel_type_id not in wanted or i in out.hidden_edges:
            continue
        bar, src = (e.src, e.dst) if e.reversed else (e.dst, e.src)
        if bar == src or bar not in drawn or src not in drawn:
            continue
        sources.setdefault(bar, []).append(src)
        edges_of.setdefault(bar, []).append(i)
    for bar in list(sources):
        if len(set(sources[bar])) < 2:
            del sources[bar]
            continue
        out.hidden_edges.update(edges_of[bar])
        out.spans.add(bar)
    return sources


def _nest(view: View, vp: Viewpoint, drawn: set[str], out: Layout, by_id: dict[str, ViewNode]) -> None:
    """The part of every nested relationship goes inside its whole. A part with two wholes takes
    the first by name and identifier; a whole that already sits inside the part (a cycle) is
    passed over; the edges not taken stay lines. A spanning node neither nests nor holds."""
    wanted = set(vp.nest)
    if not wanted:
        return
    candidates: dict[str, list[tuple[str, str, int]]] = {}
    for i, e in enumerate(view.edges):
        if e.rel_type_id not in wanted or i in out.hidden_edges:
            continue
        whole, part = e.whole, e.part
        if (
            whole == part
            or whole not in drawn
            or part not in drawn
            or whole in out.spans
            or part in out.spans
        ):
            continue
        candidates.setdefault(part, []).append((by_id[whole].name.lower(), whole, i))
    forest = nx.DiGraph()
    for part in sorted(candidates, key=lambda p: (by_id[p].name.lower(), p)):
        for _, whole, i in sorted(candidates[part]):
            if forest.has_node(part) and forest.has_node(whole) and nx.has_path(forest, part, whole):
                continue
            out.parents[part] = whole
            out.hidden_edges.add(i)
            forest.add_edge(whole, part)
            break


def _grow(
    own: dict[str, tuple[int, int]], parents: dict[str, str], by_id: dict[str, ViewNode]
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Every whole grown to hold its children in a small grid under its own name: the sizes,
    each child's offset inside its whole, and the children of each whole in drawing order."""
    children: dict[str, list[str]] = {}
    for part in sorted(parents, key=_order_key(by_id)):
        children.setdefault(parents[part], []).append(part)
    sizes = dict(own)
    offsets: dict[str, tuple[int, int]] = {}
    done: set[str] = set()

    def size(n: str) -> tuple[int, int]:
        if n in done:
            return sizes[n]
        kids = children.get(n, [])
        if kids:
            cols = math.ceil(math.sqrt(len(kids)))
            x = y = row_h = grid_w = 0
            for j, k in enumerate(kids):
                kw, kh = size(k)
                if j and j % cols == 0:
                    y, x, row_h = y + row_h + NEST_PAD, 0, 0
                offsets[k] = (NEST_PAD + x, NEST_HEADER + y)
                x += kw + NEST_PAD
                row_h = max(row_h, kh)
                grid_w = max(grid_w, x - NEST_PAD)
            w0, _ = own[n]
            sizes[n] = (max(w0, grid_w + 2 * NEST_PAD), NEST_HEADER + y + row_h + NEST_PAD)
        done.add(n)
        return sizes[n]

    for n in own:
        size(n)
    return sizes, offsets, children


def _outermost(parents: dict[str, str], nid: str) -> str:
    while nid in parents:
        nid = parents[nid]
    return nid


def _holds(parents: dict[str, str], whole: str, nid: str) -> bool:
    """Whether `nid` is drawn inside `whole`, at any depth."""
    while nid in parents:
        nid = parents[nid]
        if nid == whole:
            return True
    return False


def _adjacency(view: View, out: Layout, orders: list[list[str]]) -> dict[str, list[str]]:
    """Who is joined to whom among the shapes that are ordered: a drawn edge counts for the
    outermost wholes of its ends, in both directions, once per edge."""
    ordered = {nid for order in orders for nid in order}
    adj: dict[str, list[str]] = {nid: [] for nid in ordered}
    for i, e in enumerate(view.edges):
        if i in out.hidden_edges:
            continue
        a, b = _outermost(out.parents, e.src), _outermost(out.parents, e.dst)
        if a == b or a not in ordered or b not in ordered:
            continue
        adj[a].append(b)
        adj[b].append(a)
    return adj


def _sweep(orders: list[list[str]], adj: dict[str, list[str]], key) -> list[list[str]]:
    """The order within every band after `SWEEPS` barycentre passes down the bands and back up,
    keeping the best order seen: a pass can undo the gain of the one before it, and the count
    of crossings between neighbouring bands says which order to keep."""
    best, fewest = [list(o) for o in orders], _crossings(orders, adj)
    for _ in range(SWEEPS):
        for bi in range(1, len(orders)):
            orders[bi] = _by_barycentre(orders[bi], orders[bi - 1], adj, key)
        for bi in range(len(orders) - 2, -1, -1):
            orders[bi] = _by_barycentre(orders[bi], orders[bi + 1], adj, key)
        crossings = _crossings(orders, adj)
        if crossings < fewest:
            best, fewest = [list(o) for o in orders], crossings
        if fewest == 0:
            break
    return best


def _crossings(orders: list[list[str]], adj: dict[str, list[str]]) -> int:
    """How many pairs of lines between neighbouring bands cross, by the order within each band."""
    pos = {nid: i for order in orders for i, nid in enumerate(order)}
    total = 0
    for upper, lower in zip(orders, orders[1:], strict=False):
        below = set(lower)
        segments = sorted((pos[u], pos[v]) for u in upper for v in adj.get(u, []) if v in below)
        for i, (u1, v1) in enumerate(segments):
            for u2, v2 in segments[i + 1 :]:
                if u2 > u1 and v2 < v1:
                    total += 1
    return total


def _by_barycentre(order: list[str], other: list[str], adj: dict[str, list[str]], key) -> list[str]:
    """The band reordered by the mean position of each node's neighbours in the other band; a
    node with none there keeps its place."""
    pos = {nid: i for i, nid in enumerate(other)}
    here = {nid: i for i, nid in enumerate(order)}

    def bary(nid: str) -> float:
        ps = sorted(pos[m] for m in adj.get(nid, []) if m in pos)
        return sum(ps) / len(ps) if ps else float(here[nid])

    return sorted(order, key=lambda nid: (bary(nid), *key(nid)))


def _wrap(order: list[str], sizes: dict[str, tuple[int, int]]) -> list[list[str]]:
    rows: list[list[str]] = [[]]
    width = 0
    for n in order:
        w = sizes[n][0]
        if rows[-1] and width + GAP_X + w > MAX_ROW_W:
            rows.append([])
            width = 0
        width += w + (GAP_X if rows[-1] else 0)
        rows[-1].append(n)
    return rows if rows[0] else []


def _align_row(row: list[str], boxes: dict[str, Box], adj: dict[str, list[str]], other: set[str]) -> None:
    """Sugiyama's priority placement: the shapes with the most neighbours in the other band are
    put under the mean of those neighbours first, and each later shape moves as close as the
    ones already fixed allow, with the room the shapes between them need kept free."""
    w = {n: boxes[n].w for n in row}
    index = {n: i for i, n in enumerate(row)}

    def targets(n: str) -> list[float]:
        return sorted(boxes[m].cx for m in adj.get(n, []) if m in other)

    fixed: dict[str, float] = {}
    for n in sorted(row, key=lambda n: (-len(targets(n)), index[n])):
        i = index[n]
        lo, between = float(MARGIN + BAND_PAD), 0.0
        for m in reversed(row[:i]):
            if m in fixed:
                lo = fixed[m] + w[m] + GAP_X
                break
            between += w[m] + GAP_X
        lo += between
        hi, between = math.inf, 0.0
        for m in row[i + 1 :]:
            if m in fixed:
                hi = fixed[m] - GAP_X
                break
            between += w[m] + GAP_X
        hi -= between + w[n]
        ts = targets(n)
        want = sum(ts) / len(ts) - w[n] / 2 if ts else boxes[n].x
        fixed[n] = float(round(min(max(want, lo), hi)))
    for n, x in fixed.items():
        boxes[n].x = x


def _place_children(
    n: str,
    boxes: dict[str, Box],
    sizes: dict[str, tuple[int, int]],
    offsets: dict[str, tuple[int, int]],
    children: dict[str, list[str]],
) -> None:
    """A whole's children at their offsets inside it, in absolute coordinates, all the way down."""
    for k in children.get(n, []):
        dx, dy = offsets[k]
        boxes[k] = Box(boxes[n].x + dx, boxes[n].y + dy, *sizes[k])
        _place_children(k, boxes, sizes, offsets, children)


def _place_bars(
    bands: list[Band],
    bars_of: list[list[str]],
    rows_of: list[list[list[str]]],
    sources: dict[str, list[str]],
    own: dict[str, tuple[int, int]],
    out: Layout,
    by_id: dict[str, ViewNode],
) -> None:
    """Every spanning node as a bar from the leftmost to the rightmost of the shapes it spans, at
    least as wide as its own name, in rows under the shapes at the bottom of its band. Bars
    whose ranges do not overlap share a row (first fit, left to right), so four entities under
    one application stack and three under three applications sit side by side. A bar may span
    other bars, so they are placed as their sources become known; one whose sources never do
    (bars spanning each other) takes what is known. The band grows by the rows its bars take,
    and every band below it moves down by the same amount."""
    key = _order_key(by_id)
    pending = sorted(out.spans, key=key)
    bar_x: dict[str, tuple[float, float]] = {}

    def place(bar: str, force: bool) -> bool:
        known = [out.boxes[s] for s in sources[bar] if s in out.boxes]
        if not force and len(known) < len(sources[bar]):
            return False
        w0 = own[bar][0]
        if known:
            x0, x1 = min(b.x for b in known), max(b.right for b in known)
            w = max(x1 - x0, w0)
            x = max(float(MARGIN + BAND_PAD), round(x0 - (w - (x1 - x0)) / 2))
        else:
            x, w = float(MARGIN + BAND_PAD), w0
        bar_x[bar] = (x, w)
        out.boxes[bar] = Box(x, 0, w, NODE_H)  # its row comes once every bar of the band has an x
        return True

    while pending:
        placed = [bar for bar in pending if place(bar, force=False)]
        if not placed:
            place(pending[0], force=True)
            placed = [pending[0]]
        pending = [bar for bar in pending if bar not in placed]

    def outermost(nid: str) -> str:
        while nid in out.parents:
            nid = out.parents[nid]
        return nid

    shift = 0.0
    for bi, band in enumerate(bands):
        band.box.y += shift
        top_level = {n for row in rows_of[bi] for n in row}
        for n, box in out.boxes.items():
            if n not in out.spans and outermost(n) in top_level:
                box.y += shift
        bars = sorted(bars_of[bi], key=lambda n: (bar_x[n][0], *key(n)))
        rows: list[list[str]] = []
        for bar in bars:
            b = out.boxes[bar]
            for row in rows:
                if all(b.x >= out.boxes[o].right + GAP_X or b.right + GAP_X <= out.boxes[o].x for o in row):
                    row.append(bar)
                    break
            else:
                rows.append([bar])
        if not rows:
            continue
        top = band.box.bottom - BAND_PAD + (BAND_PAD if rows_of[bi] else 0)
        for ri, row in enumerate(rows):
            for bar in row:
                out.boxes[bar].y = top + ri * (NODE_H + BAND_PAD)
        extra = (BAND_PAD if rows_of[bi] else 0) + len(rows) * NODE_H + BAND_PAD * (len(rows) - 1)
        band.box.h += extra
        shift += extra
        band.nodes.extend(bar for row in rows for bar in row)


def _something_between(boxes: dict[str, Box], a: Box, b: Box, ends: tuple[str, str]) -> bool:
    """Whether a third shape sits between two that share a row, in the way of a straight line."""
    left, right = (a, b) if a.x <= b.x else (b, a)
    top, bottom = min(a.y, b.y), max(a.bottom, b.bottom)
    return any(
        m.x >= left.right and m.right <= right.x and m.y < bottom and m.bottom > top
        for nid, m in boxes.items()
        if nid not in ends
    )


def _along(other: Box, side: str) -> float:
    """Where the other end lies along a side: its x for the top and bottom, its y for the sides."""
    return other.cx if side in ("top", "bottom") else other.cy
