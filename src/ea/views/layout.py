"""A layered layout for an exported drawing, in the application's own code (decision 0024).

The bands come from the viewpoint (decision 0023): by architecture layer, by element type, or
by a related element of a named type. Within a band the order is chosen so that the lines to
the neighbouring bands cross as little as possible; a shape is sized to its name; a nested
shape sits inside the whole that holds it; a spanning shape is a bar across the shapes it
relates to; and every edge is given the side it leaves and enters. Everything here is
deterministic: the same view and the same viewpoint give the same drawing, which the golden
files under `tests/golden/drawio/` hold it to.

The screens keep the browser's layout; this is for the file, which the command line and the
agent export without a browser.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from ea.models import Viewpoint
from ea.views.model import DEFAULT_VIEWPOINT, LAYER_TITLES, View, ViewNode, layer_rank

# Shape sizing, in draw.io units (pixels at 100%). A 14-point name reads on a printed page.
FONT_SIZE = 14
NODE_W, NODE_H = 180, 70
NODE_W_MAX, WRAP_CHARS, CHAR_W, LINE_H = 300, 22, 8.0, 19
GAP_X, GAP_Y = 40, 60  # between shapes in a band, and between bands
BAND_PAD, BAND_HEADER = 24, 32  # inside a band: padding, and the room its title takes
NEST_PAD, NEST_HEADER = 16, 34  # inside a nesting shape
MARGIN = 40


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
    boxes: dict[str, Box]  # every drawn node, absolute coordinates
    bands: list[Band]  # in drawing order, top to bottom
    parents: dict[str, str] = field(default_factory=dict)  # child -> the node it is drawn inside
    spans: set[str] = field(default_factory=set)  # nodes drawn as a bar across what they relate to
    hidden_edges: set[int] = field(
        default_factory=set
    )  # edge indexes drawn as nesting, a span, or a band membership
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

    `sizes` overrides the measured size of a shape (the browser's, when the export follows an
    arrangement). The baseline here places every band's shapes in reading order on one row;
    the ordering, compaction, nesting and spanning are the work of initiative 22's WP2.
    """
    vp = viewpoint or DEFAULT_VIEWPOINT
    sizes = dict(sizes or {})
    for n in view.nodes:
        sizes.setdefault(n.id, node_size(n))
    bands = band_members(view, vp)
    boxes: dict[str, Box] = {}
    y = MARGIN
    width = 0.0
    for band in bands:
        x = MARGIN + BAND_PAD
        tallest = 0
        for nid in band.nodes:
            w, h = sizes[nid]
            boxes[nid] = Box(x, y + BAND_HEADER + BAND_PAD, w, h)
            x += w + GAP_X
            tallest = max(tallest, h)
        band.box = Box(
            MARGIN, y, max(x - GAP_X + BAND_PAD - MARGIN, NODE_W), BAND_HEADER + 2 * BAND_PAD + tallest
        )
        width = max(width, band.box.right)
        y += band.box.h + GAP_Y
    for band in bands:
        band.box.w = width - MARGIN
    out = Layout(
        boxes=boxes,
        bands=bands,
        band_elements={b.element_id for b in bands if b.element_id},
        width=width + MARGIN,
        height=y - GAP_Y + MARGIN,
    )
    out.routes = routes_for(view, out.boxes, out.parents)
    return out


def band_members(view: View, vp: Viewpoint) -> list[Band]:
    """The bands a viewpoint gives a view and which node sits in which, in drawing order, before
    anything is placed (every box is empty). Under bands by a related element the membership is
    what `apply_viewpoint` marked on the nodes (`ViewNode.band`, `ViewNode.is_band`); a view
    that was never filtered falls back to an exact match on the band type. The export from a
    browser arrangement uses this to draw the bands around the shapes where the reader left them.
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


def routes_for(view: View, boxes: dict[str, Box], parents: dict[str, str] | None = None) -> dict[int, Route]:
    """A port at each end of every edge whose ends are drawn: below-to-above when the target sits
    under the source, side to side when they share a row, so no two edges leave one shape from
    the same point when they head the same way.

    The baseline picks the side from the relative position of the two boxes; WP2 spreads the
    ports along a side and adds the bends.
    """
    routes: dict[int, Route] = {}
    for i, e in enumerate(view.edges):
        a, b = boxes.get(e.src), boxes.get(e.dst)
        if a is None or b is None:
            continue
        if b.y >= a.bottom:
            routes[i] = Route(exit=(0.5, 1.0), entry=(0.5, 0.0))
        elif b.bottom <= a.y:
            routes[i] = Route(exit=(0.5, 0.0), entry=(0.5, 1.0))
        elif b.x >= a.right:
            routes[i] = Route(exit=(1.0, 0.5), entry=(0.0, 0.5))
        elif b.right <= a.x:
            routes[i] = Route(exit=(0.0, 0.5), entry=(1.0, 0.5))
        else:
            routes[i] = Route(exit=(0.5, 1.0), entry=(0.5, 0.0))
    return routes
