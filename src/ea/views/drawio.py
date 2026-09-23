"""Render a view as a draw.io (mxGraph) file with ArchiMate 3 stencils: a drawing an architect edits.

The file is a one-way export. Every shape carries the element identifier (`ea_id`) and a
link to the element's page, which is the linking contract; nothing imports it back.

What is written into the file is what a person would otherwise set by hand (initiative 22):
a readable font, a box sized to its name, a port at each end of an edge and the bends between
them, a label with a background, an arrowhead for the kind of relationship, a shape nested in
the shape that holds it, a bar across the shapes it spans, a title, a legend and a page sized
to the drawing. The placement itself comes from `ea.views.layout` (decision 0024) or, when the
reader arranged the shapes in the browser, from where they left them; both are written by the
one writer, so the two files have one shape.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html import escape

from ea.models import ARCHIMATE_RELATIONSHIPS, Viewpoint
from ea.services.target import NOT_REAL, TARGET_STYLE
from ea.views.layout import (
    FONT_SIZE,
    Band,
    Box,
    Layout,
    band_members,
    hide_band_edges,
    layout,
    node_size,
    routes_for,
)
from ea.views.model import DEFAULT_VIEWPOINT, LAYER_TITLES, View, ViewNode, layer_rank

# draw.io ArchiMate 3 fill colours per layer (from the ArchiMate 3 sidebar).
LAYER_FILL = {
    "motivation": "#CCCCFF",
    "strategy": "#F5DEAA",
    "business": "#ffff99",
    "application": "#99ffff",
    "technology": "#AFFFAF",
    "physical": "#AFFFAF",
    "implementation": "#FFE0E0",
    "other": "#EBEBEB",
}
_AM = "html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3."
# ArchiMate element -> stencil fragment appended to _AM.
STENCIL = {
    "BusinessActor": "application;appType=actor;archiType=square;",
    "BusinessRole": "application;appType=role;archiType=square;",
    "BusinessCollaboration": "application;appType=collab;archiType=square;",
    "BusinessInterface": "application;appType=interface;archiType=square;",
    "BusinessProcess": "application;appType=proc;archiType=rounded;",
    "BusinessFunction": "application;appType=func;archiType=rounded;",
    "BusinessInteraction": "application;appType=interaction;archiType=rounded;",
    "BusinessEvent": "application;appType=event;archiType=rounded;",
    "BusinessService": "application;appType=serv;archiType=rounded;",
    "BusinessObject": "businessObject;overflow=fill;",
    "Contract": "application;appType=contract;archiType=square;",
    "Product": "application;appType=product;archiType=square;",
    "ApplicationComponent": "application;appType=comp;archiType=square;",
    "ApplicationInterface": "application;appType=interface;archiType=square;",
    "ApplicationFunction": "application;appType=func;archiType=rounded;",
    "ApplicationInteraction": "application;appType=interaction;archiType=rounded;",
    "ApplicationProcess": "application;appType=proc;archiType=rounded;",
    "ApplicationEvent": "application;appType=event;archiType=rounded;",
    "ApplicationService": "application;appType=serv;archiType=rounded;",
    "DataObject": "businessObject;overflow=fill;",
    "Node": "application;appType=node;archiType=square;",
    "Device": "application;appType=device;archiType=square;",
    "SystemSoftware": "application;appType=sysSw;archiType=square;",
    "TechnologyService": "application;appType=serv;archiType=rounded;",
    "TechnologyInterface": "application;appType=interface;archiType=square;",
    "Artifact": "application;appType=artifact;archiType=square;",
    "Stakeholder": "application;appType=role;archiType=oct;",
    "Driver": "application;appType=driver;archiType=oct;",
    "Assessment": "application;appType=assess;archiType=oct;",
    "Goal": "application;appType=goal;archiType=oct;",
    "Outcome": "application;appType=outcome;archiType=oct;",
    "Principle": "application;appType=principle;archiType=oct;",
    "Requirement": "application;appType=requirement;archiType=oct;",
    "Constraint": "application;appType=constraint;archiType=oct;",
    "Meaning": "application;appType=meaning;archiType=oct;",
    "Capability": "application;appType=capability;archiType=rounded;",
    "Resource": "application;appType=resource;archiType=square;",
    "ValueStream": "application;appType=valueStream;archiType=rounded;",
    "CourseOfAction": "application;appType=course;archiType=rounded;",
    "WorkPackage": "application;appType=workPackage;archiType=rounded;",
    "Plateau": "application;appType=plateau;archiType=square;",
    "Gap": "application;appType=gap;archiType=square;",
    "Location": "application;appType=location;archiType=square;",
}
SPECIAL_FILL = {"Location": "#efd1e4", "Plateau": "#E0FFE0", "Gap": "#E0FFE0"}

# The ArchiMate 3 line decoration per relationship kind, written the way the draw.io sidebar
# writes it. `start*` sits at the edge's source, so a composition's diamond is at the whole;
# when a relationship type's notation runs in reverse the two ends are swapped (`_decoration`).
EDGE_STYLE = {
    "composition": "startArrow=diamondThin;startFill=1;endArrow=none;",
    "aggregation": "startArrow=diamondThin;startFill=0;endArrow=none;",
    "assignment": "startArrow=oval;startFill=1;endArrow=block;endFill=1;",
    "realization": "dashed=1;endArrow=block;endFill=0;endSize=12;",
    "serving": "endArrow=open;endFill=0;",
    "access": "dashed=1;dashPattern=1 4;endArrow=open;endFill=0;endSize=6;",
    "influence": "dashed=1;dashPattern=6 3;endArrow=open;endFill=0;",
    "triggering": "endArrow=block;endFill=1;",
    "flow": "dashed=1;dashPattern=6 3;endArrow=block;endFill=1;",
    "specialization": "endArrow=block;endFill=0;endSize=12;",
    "association": "endArrow=none;",
    "": "endArrow=open;endFill=0;",  # a type that names no notation: the plain directed line it always was
}
EDGE_BASE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
    "fontSize=11;labelBackgroundColor=#ffffff;strokeColor=#555555;"
)
# A band is a background behind its shapes, never a swimlane: a swimlane owns the shapes in
# it, so a shape dragged out of one in the tool is reparented and re-measured, which is not
# what a reader arranging a drawing wants. A band that is a plain rectangle lets every shape
# move freely, and `connectable=0` keeps an edge from snapping to it.
BAND_STYLE = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#fafafa;strokeColor=#999999;dashed=1;"
    "verticalAlign=top;align=left;spacingLeft=8;fontSize=16;fontStyle=1;fontColor=#3e4c59;connectable=0;"
)
_TEXT = "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;overflow=hidden;"
_INVISIBLE = "shape=ellipse;fillColor=none;strokeColor=none;"

# The page, in draw.io units. A4 landscape is the least a page is; the drawing grows it.
PAGE_W, PAGE_H = 1169, 827
PAGE_MARGIN = 40
TITLE_H = 56  # the room the title block takes above the drawing; a note adds its own lines
NOTE_LINE_H, NOTE_CHAR_W = 14, 6  # a line of the note at 11 points, and about a character of it
LEGEND_GAP, LEGEND_ROW, LEGEND_COL = 30, 22, 240
# Around the shapes the reader placed in the browser: what a band adds beyond its members.
BAND_PAD, BAND_HEADER = 24, 32
LOOSE_GAP = 60  # under the placed shapes, the row for the ones the browser never placed


def state_style(n: ViewNode) -> str:
    """The style fragment a target state adds to a shape: coloured stroke, dashed when not (yet) real."""
    out = ""
    st = TARGET_STYLE.get(n.target_state)
    if st and n.target_state not in ("undecided", "keep"):
        out += f"strokeColor={st['hex']};strokeWidth=2;"
        if n.target_state == "decommission":
            out += "fontColor=#c92a2a;"
    if n.current_state in NOT_REAL or n.target_state in ("new", "merge"):
        out += "dashed=1;dashPattern=6 3;"
    return out


def node_style(n: ViewNode, marked: bool = False) -> str:
    fill = SPECIAL_FILL.get(n.archimate) or LAYER_FILL.get(n.layer, LAYER_FILL["other"])
    if n.archimate == "Value":
        return f"ellipse;html=1;whiteSpace=wrap;fillColor={fill};" + (state_style(n) if marked else "")
    frag = STENCIL.get(n.archimate)
    if frag is None:
        style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};"
    else:
        style = f"{_AM}{frag}fillColor={fill};"
    if n.focus:
        style += "strokeWidth=3;"
    if marked:
        style += state_style(n)
    return style


def _label(n: ViewNode, marked: bool) -> str:
    if not marked:
        return n.name
    st = TARGET_STYLE.get(n.target_state)
    if n.target_state == "decommission":
        return f"<s>{n.name}</s>"
    if st and n.target_state not in ("undecided", "keep"):
        return f"{st['glyph']} {n.name}"
    return n.name


def _cell(container: ET.Element, cid: str, **attrs: str) -> ET.Element:
    return ET.SubElement(container, "mxCell", id=cid, **attrs)


def to_drawio(
    view: View,
    base_url: str = "",
    positions: dict[str, dict[str, float]] | None = None,
    marked: bool = False,
    viewpoint: Viewpoint | None = None,
    modified: str | None = None,
) -> str:
    """The view as an uncompressed `.drawio` file.

    Without positions: the layered layout of `ea.views.layout` under `viewpoint` (the default
    viewpoint when none is given). With positions (from the browser, where the reader may have
    moved shapes): every shape exactly where it was, and the bands as dashed background
    groupings sized to their shapes. With `marked`, shapes carry their target state the way the
    Mermaid rendering does. `modified` is the file's timestamp; the export stamps now when
    none is given, and a test passes one so the same view gives the same bytes.
    """
    vp = viewpoint or DEFAULT_VIEWPOINT
    stamp = modified or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if positions and sum(1 for n in view.nodes if n.id in positions) >= max(1, len(view.nodes) // 2):
        lay = _placed(view, vp, positions)
    else:
        lay = layout(view, vp)
    return _write(view, lay, vp, base_url, marked, stamp)


# ------------------------------------------------------------------ the browser's arrangement


def _placed(view: View, vp: Viewpoint, positions: dict[str, dict[str, float]]) -> Layout:
    """The reader's arrangement as a layout: each shape where the browser reports its centre, at
    the size it was drawn (or the measured size when the browser reported none, as it does for a
    view first drawn on a hidden tab), the bands drawn around what they hold, and nothing nested
    or spanned, because the reader placed every shape and a nest or a bar would move it.
    """
    sizes = {n.id: node_size(n) for n in view.nodes}
    boxes: dict[str, Box] = {}
    loose: list[str] = []
    for n in view.nodes:
        p = positions.get(n.id)
        if p is None:
            loose.append(n.id)
            continue
        w = float(p.get("w") or sizes[n.id][0])
        h = float(p.get("h") or sizes[n.id][1])
        boxes[n.id] = Box(float(p["x"]) - w / 2, float(p["y"]) - h / 2, w, h)
    # A shape the browser never placed goes in a row under everything it did, rather than on
    # top of the others at one corner.
    x = min((b.x for b in boxes.values()), default=0.0)
    y = max((b.bottom for b in boxes.values()), default=0.0) + LOOSE_GAP
    for nid in loose:
        w, h = sizes[nid]
        boxes[nid] = Box(x, y, w, h)
        x += w + PAGE_MARGIN

    bands: list[Band] = []
    for band in band_members(view, vp):
        around = [boxes[i] for i in band.nodes if i in boxes]
        if band.element_id in boxes:  # the band stands where the reader put the element it is
            around.append(boxes[band.element_id])
        if not around:
            continue
        x0, y0 = min(b.x for b in around) - BAND_PAD, min(b.y for b in around) - BAND_PAD - BAND_HEADER
        x1, y1 = max(b.right for b in around) + BAND_PAD, max(b.bottom for b in around) + BAND_PAD
        band.box = Box(x0, y0, x1 - x0, y1 - y0)
        bands.append(band)
    band_elements = {b.element_id for b in bands if b.element_id}
    for nid in band_elements:
        boxes.pop(nid, None)  # drawn as the band, not as a shape

    # Everything shifted so the drawing starts at the margin, whatever the browser's origin was.
    everything = list(boxes.values()) + [b.box for b in bands]
    dx = PAGE_MARGIN - min((b.x for b in everything), default=PAGE_MARGIN)
    dy = PAGE_MARGIN - min((b.y for b in everything), default=PAGE_MARGIN)
    for b in everything:
        b.x += dx
        b.y += dy
    lay = Layout(
        boxes=boxes,
        bands=bands,
        band_elements=band_elements,
        width=max((b.right for b in everything), default=0.0) + PAGE_MARGIN,
        height=max((b.bottom for b in everything), default=0.0) + PAGE_MARGIN,
    )
    # An edge to a band element is the membership the band shows, here as on the laid-out
    # path: a line from a band background to a shape is not a relationship anybody drew.
    hide_band_edges(view, bands, lay, {n.id: n for n in view.nodes})
    lay.routes = routes_for(view, boxes, hidden=lay.hidden_edges)
    return lay


# ------------------------------------------------------------------------------ the writer


def _write(view: View, lay: Layout, vp: Viewpoint, base_url: str, marked: bool, stamp: str) -> str:
    """One writer for both placements, so the two files have one shape: title, note, bands,
    shapes (a whole before the parts inside it), edges, legend — in that order, which is the
    z-order draw.io draws them in."""
    mxfile, model, root = _document(view, vp, stamp)
    note = _note(view, lay)
    text_w = max(
        400,
        round(max([b.box.right for b in lay.bands] + [b.right for b in lay.boxes.values()], default=0))
        - PAGE_MARGIN,
    )
    note_h = _note_height(note, text_w) if note else 0
    top = TITLE_H + (note_h + 8 if note else 0)  # the drawing sits under the title block

    # Everything the layout placed, moved under the title and rounded to whole units, which is
    # what a person drawing on the grid would have used.
    at = {nid: _rounded(b, top) for nid, b in lay.boxes.items()}
    band_boxes = [_rounded(b.box, top) for b in lay.bands]
    content_right = max([b.right for b in band_boxes] + [b.right for b in at.values()], default=PAGE_MARGIN)
    content_bottom = max([b.bottom for b in band_boxes] + [b.bottom for b in at.values()], default=top)

    _title(root, view, vp, stamp, text_w, note, note_h)

    by_id = {n.id: n for n in view.nodes}
    cells: set[str] = set()  # every cell an edge may join: the shapes and the bands that are elements
    for band, box in zip(lay.bands, band_boxes, strict=True):
        if band.element_id and band.element_id in by_id:
            obj = _object(root, by_id[band.element_id], base_url, marked, label=band.title, band="")
            cell = ET.SubElement(obj, "mxCell", style=BAND_STYLE, vertex="1", parent="1")
            cells.add(band.element_id)
        else:
            cell = _cell(root, f"lane_{band.key}", value=band.title, style=BAND_STYLE, vertex="1", parent="1")
        _geometry(cell, box)

    band_of = {nid: band.key for band in lay.bands for nid in band.nodes}
    wholes = set(lay.parents.values())
    for nid in _shape_order(view, lay):
        n = by_id.get(nid)
        if n is None or nid in lay.band_elements:
            continue
        parent = lay.parents.get(nid, "")
        if parent not in at:  # a part whose whole was not drawn stands on its own
            parent = ""
        style = node_style(n, marked) + f"fontSize={FONT_SIZE};"
        if nid in wholes:
            style += "container=1;verticalAlign=top;spacingTop=4;"  # the name above what it holds
        if nid in lay.spans:
            style += "align=left;spacingLeft=8;"  # a bar reads from its left end
        obj = _object(root, n, base_url, marked, band="" if parent else band_of.get(nid, ""))
        cell = ET.SubElement(obj, "mxCell", style=style, vertex="1", parent=parent or "1")
        box = at[nid]
        if parent:
            whole = at[parent]
            box = Box(box.x - whole.x, box.y - whole.y, box.w, box.h)  # relative to the whole
        _geometry(cell, box)
        cells.add(nid)

    hidden = set(lay.hidden_edges) | _membership(view, vp, lay.bands)
    drawn_kinds: list[str] = []
    drawn_states: list[str] = []
    for i, e in enumerate(view.edges):
        if i in hidden or e.src not in cells or e.dst not in cells:
            continue
        style = EDGE_BASE + _decoration(e.archimate, e.reversed)
        route = lay.routes.get(i)
        if route is not None:
            style += (
                f"exitX={_num(route.exit[0])};exitY={_num(route.exit[1])};exitDx=0;exitDy=0;"
                f"entryX={_num(route.entry[0])};entryY={_num(route.entry[1])};entryDx=0;entryDy=0;"
            )
        st = TARGET_STYLE.get(e.target_state)
        if marked and st and e.target_state not in ("undecided", "keep"):
            style += f"strokeColor={st['hex']};strokeWidth=2;"
            if e.target_state in ("new", "merge"):
                style += "dashed=1;"
            drawn_states.append(e.target_state)
        cell = _cell(
            root, f"edge_{i}", value=e.label, style=style, edge="1", parent="1", source=e.src, target=e.dst
        )
        geo = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        if route is not None and route.points:
            points = ET.SubElement(geo, "Array", **{"as": "points"})
            for x, y in route.points:
                ET.SubElement(points, "mxPoint", x=_int(x), y=_int(y + top))
        drawn_kinds.append(e.archimate)

    shown = [by_id[nid] for nid in cells if nid in by_id and nid not in lay.band_elements]
    layers = sorted({n.layer for n in shown}, key=layer_rank)
    kinds = [k for k in list(ARCHIMATE_RELATIONSHIPS) + [""] if k in set(drawn_kinds)]
    states: list[str] = []
    if marked:
        for s in [n.target_state for n in shown] + drawn_states:
            if s in TARGET_STYLE and s not in ("undecided", "keep") and s not in states:
                states.append(s)
        states.sort(key=list(TARGET_STYLE).index)
    right, bottom = _legend(
        root, content_bottom + LEGEND_GAP, layers, kinds if len(kinds) > 1 else [], states
    )

    width = max(content_right, right) + PAGE_MARGIN
    height = max(content_bottom, bottom) + PAGE_MARGIN
    model.set("pageWidth", str(max(PAGE_W, math.ceil(width))))
    model.set("pageHeight", str(max(PAGE_H, math.ceil(height))))
    ET.indent(mxfile, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode") + "\n"


def _shape_order(view: View, lay: Layout) -> list[str]:
    """Band by band, each top-level shape followed by what is nested in it, so a whole is in
    the file before its parts; then whatever the bands did not place, in the view's order."""
    children: dict[str, list[str]] = {}
    for n in view.nodes:
        if n.id in lay.parents:
            children.setdefault(lay.parents[n.id], []).append(n.id)
    out: list[str] = []
    seen: set[str] = set()

    def take(nid: str) -> None:
        if nid in seen or nid not in lay.boxes:
            return
        seen.add(nid)
        out.append(nid)
        for c in children.get(nid, []):
            take(c)

    for band in lay.bands:
        for nid in band.nodes:
            take(nid)
    for n in view.nodes:
        if n.id not in lay.parents:
            take(n.id)
    for n in view.nodes:  # a part whose whole was never drawn is drawn on its own
        take(n.id)
    return out


def _membership(view: View, vp: Viewpoint, bands: list[Band]) -> set[int]:
    """The edges that only say which band a shape sits in: under bands by a related element,
    the band relationship between a member and the element its band stands for. The band is
    that edge drawn, so a line to it would say the same thing twice, to a rectangle."""
    if vp.bands != "related":
        return set()
    member_of = {nid: band.element_id for band in bands if band.element_id for nid in band.nodes}
    wanted = set(vp.band_relationships)
    return {
        i
        for i, e in enumerate(view.edges)
        if (not wanted or e.rel_type_id in wanted)
        and (member_of.get(e.src) == e.dst or member_of.get(e.dst) == e.src)
    }


def _decoration(kind: str, reversed_: bool) -> str:
    """The line decoration of a relationship kind, its two ends swapped when the type's
    notation runs from target to source, so the diamond, the dot or the arrowhead sits at
    the element the standard puts it at."""
    style = EDGE_STYLE.get(kind, EDGE_STYLE[""])
    if not reversed_:
        return style
    out = []
    for piece in style.rstrip(";").split(";"):
        key, _, value = piece.partition("=")
        if key.startswith("start"):
            key = "end" + key[len("start") :]
        elif key.startswith("end"):
            key = "start" + key[len("end") :]
        out.append(f"{key}={value}")
    # A style that names no endArrow gets draw.io's default, a classic arrowhead at the
    # target; the swapped decoration must say "none" where the standard draws nothing.
    if not any(piece.startswith("endArrow=") for piece in out):
        out.append("endArrow=none")
    return ";".join(out) + ";"


def _note(view: View, lay: Layout) -> str:
    """What the drawing could not show as asked, as one grey paragraph: the view's own note
    and the layout's, each a sentence of its own."""
    pieces = [s.strip() for s in [view.note, *lay.notes] if s and s.strip()]
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in pieces)


def _note_height(note: str, width: float) -> int:
    """Room for the note at 11 points, wrapped to the title's width, so a long one is read
    rather than clipped. An estimate from the character count is enough for a text cell."""
    per_line = max(20, int(width / NOTE_CHAR_W))
    return 8 + math.ceil(len(note) / per_line) * NOTE_LINE_H


def _title(
    root: ET.Element, view: View, vp: Viewpoint, stamp: str, width: float, note: str, note_h: int
) -> None:
    """The title block: the view's title, under it the viewpoint and the export stamp, and the
    note (what the drawing could not show as asked) when there is one."""
    level = " · Overview" if view.detail == "overview" else ""
    subtitle = f"{escape(vp.name)}{level} · exported {escape(stamp)}"
    cell = _cell(
        root,
        "title",
        value=(
            f'{escape(view.title)}<br><font style="font-size: 11px; font-weight: normal;">{subtitle}</font>'
        ),
        style=f"{_TEXT}align=left;verticalAlign=top;fontSize=20;fontStyle=1;",
        vertex="1",
        parent="1",
    )
    _geometry(cell, Box(PAGE_MARGIN, 8, width, TITLE_H - 12))
    if note:
        cell = _cell(
            root,
            "note",
            value=escape(note),
            style=f"{_TEXT}align=left;verticalAlign=top;fontSize=11;fontColor=#6b7280;",
            vertex="1",
            parent="1",
        )
        _geometry(cell, Box(PAGE_MARGIN, TITLE_H - 4, width, note_h))


def _legend(
    root: ET.Element, y: float, layers: list[str], kinds: list[str], states: list[str]
) -> tuple[float, float]:
    """A legend under the drawing: a swatch per layer drawn, a sample line per relationship
    kind when more than one is drawn, and a swatch per target state when the drawing is
    marked. Returns its right and bottom edges, so the page can be sized to it."""
    if not (layers or kinds or states):
        return 0.0, y
    x0 = PAGE_MARGIN
    heading = _cell(
        root,
        "legend",
        value="Legend",
        style=f"{_TEXT}align=left;verticalAlign=middle;fontSize=12;fontStyle=1;",
        vertex="1",
        parent="1",
    )
    _geometry(heading, Box(x0, y, LEGEND_COL, 20))
    rows_y = y + 26
    columns = 0

    def text(cid: str, x: float, ry: float, value: str) -> None:
        cell = _cell(
            root,
            cid,
            value=value,
            style=f"{_TEXT}align=left;verticalAlign=middle;fontSize=11;",
            vertex="1",
            parent="1",
        )
        _geometry(cell, Box(x, ry, LEGEND_COL - 40, LEGEND_ROW))

    def swatch(cid: str, x: float, ry: float, fill: str, stroke: str, width: str = "1") -> None:
        cell = _cell(
            root,
            cid,
            value="",
            style=f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth={width};connectable=0;",
            vertex="1",
            parent="1",
        )
        _geometry(cell, Box(x, ry + 3, 24, 16))

    if layers:
        x = x0 + columns * LEGEND_COL
        for r, layer in enumerate(layers):
            ry = rows_y + r * LEGEND_ROW
            swatch(f"legend_layer_{layer}", x, ry, LAYER_FILL.get(layer, LAYER_FILL["other"]), "#999999")
            text(f"legend_layer_{layer}_name", x + 32, ry, LAYER_TITLES.get(layer, layer))
        columns += 1
    if kinds:
        x = x0 + columns * LEGEND_COL
        for r, kind in enumerate(kinds):
            ry = rows_y + r * LEGEND_ROW
            key = kind or "relationship"
            for end, px in (("a", x), ("b", x + 56)):
                dot = _cell(root, f"legend_{key}_{end}", value="", style=_INVISIBLE, vertex="1", parent="1")
                _geometry(dot, Box(px, ry + LEGEND_ROW / 2, 1, 1))
            line = _cell(
                root,
                f"legend_{key}",
                value=(kind or "relationship").capitalize(),
                style=EDGE_BASE + EDGE_STYLE[kind] + "align=left;verticalAlign=middle;",
                edge="1",
                parent="1",
                source=f"legend_{key}_a",
                target=f"legend_{key}_b",
            )
            # The label at the line's end, its left edge eight units past it, not on the line.
            geo = ET.SubElement(line, "mxGeometry", relative="1", x="1", **{"as": "geometry"})
            ET.SubElement(geo, "mxPoint", x="8", y="0", **{"as": "offset"})
        columns += 1
    if states:
        x = x0 + columns * LEGEND_COL
        for r, state in enumerate(states):
            ry = rows_y + r * LEGEND_ROW
            swatch(f"legend_state_{state}", x, ry, "#ffffff", TARGET_STYLE[state]["hex"], "2")
            text(f"legend_state_{state}_name", x + 32, ry, TARGET_STYLE[state]["label"])
        columns += 1
    rows = max(len(layers), len(kinds), len(states))
    return x0 + columns * LEGEND_COL, rows_y + rows * LEGEND_ROW


def _document(view: View, vp: Viewpoint, stamp: str) -> tuple[ET.Element, ET.Element, ET.Element]:
    mxfile = ET.Element(
        "mxfile", host="ea-repository", modified=stamp, agent="ea-repository view export", version="1"
    )
    diagram = ET.SubElement(mxfile, "diagram", id="view", name=f"{view.title[:80]} — {vp.name}")
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        dx="0",
        dy="0",
        grid="1",
        gridSize="10",
        guides="1",
        tooltips="1",
        connect="1",
        arrows="1",
        fold="1",
        page="1",
        pageScale="1",
        pageWidth=str(PAGE_W),
        pageHeight=str(PAGE_H),
    )
    root = ET.SubElement(model, "root")
    _cell(root, "0")
    _cell(root, "1", parent="0")
    return mxfile, model, root


def _object(
    root: ET.Element,
    n: ViewNode,
    base_url: str,
    marked: bool = False,
    label: str | None = None,
    band: str = "",
) -> ET.Element:
    """The linking contract: every shape carries its element identifier and a link to its page,
    and `ea_band` says which band it sits in (empty for a shape nested in another)."""
    obj = ET.SubElement(
        root,
        "object",
        label=_label(n, marked) if label is None else label,
        ea_id=n.id,
        ea_type=n.type_id,
        ea_type_name=n.type_name,
        ea_stereotype=n.stereotype,
        ea_current_state=n.current_state,
        ea_target_state=n.target_state,
        ea_band=band,
        id=n.id,
    )
    if base_url:
        obj.set("link", f"{base_url}/element/{n.id}")
    return obj


def _rounded(b: Box, dy: float) -> Box:
    return Box(round(b.x), round(b.y + dy), round(b.w), round(b.h))


def _geometry(cell: ET.Element, b: Box) -> None:
    ET.SubElement(
        cell, "mxGeometry", x=_int(b.x), y=_int(b.y), width=_int(b.w), height=_int(b.h), **{"as": "geometry"}
    )


def _int(v: float) -> str:
    return str(int(round(v)))


def _num(v: float) -> str:
    """A port fraction as draw.io writes it: `0.5`, `1`, `0.333`."""
    return f"{round(v, 3):.3f}".rstrip("0").rstrip(".") or "0"
