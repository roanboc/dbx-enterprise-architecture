"""Render a view as a draw.io (mxGraph) file with ArchiMate 3 stencils: a draft for an architect to reuse.

The file is a one-way export. Every shape carries the element identifier (`ea_id`) and a
link to the element's page, which is the linking contract; nothing imports it back.
"""

from __future__ import annotations

import textwrap
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from ea.services.target import NOT_REAL, TARGET_STYLE
from ea.views.model import LAYER_TITLES, View, ViewNode, layer_rank

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

NODE_W, NODE_H, GAP_X, GAP_Y, COLS, LANE_HEADER, LANE_GAP = 170, 60, 30, 30, 5, 28, 30
NODE_W_MAX, WRAP_CHARS, CHAR_W, LINE_H = 300, 24, 7.0, 17


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
) -> str:
    """The view as an uncompressed `.drawio` file.

    Without positions: one swimlane per layer, shapes in a grid. With positions (from the
    browser, where the reader may have moved shapes): every shape exactly where it was, and
    the layer boxes as dashed background groupings sized to their shapes. With `marked`,
    shapes carry their target state the way the Mermaid rendering does.
    """
    if positions and sum(1 for n in view.nodes if n.id in positions) >= max(1, len(view.nodes) // 2):
        return _to_drawio_positioned(view, base_url, positions, marked)
    mxfile, root = _document(view)

    layers = sorted(view.layers(), key=layer_rank)
    sizes = {n.id: node_size(n) for n in view.nodes}
    # One column width and one row height for the whole drawing, so the lanes still line up
    # while every shape is big enough for what is written in it.
    cell_w = max((w for w, _ in sizes.values()), default=NODE_W)
    cell_h = max((h for _, h in sizes.values()), default=NODE_H)
    widest = max((min(len(view.nodes_in(layer)), COLS) for layer in layers), default=1)
    lane_w = GAP_X + widest * (cell_w + GAP_X)
    y = 20
    for layer in layers:
        nodes = view.nodes_in(layer)
        rows = (len(nodes) + COLS - 1) // COLS
        lane_h = LANE_HEADER + GAP_Y + rows * (cell_h + GAP_Y)
        lane_id = f"lane_{layer}"
        lane = _cell(
            root,
            lane_id,
            value=LAYER_TITLES.get(layer, layer),
            style=(
                "swimlane;whiteSpace=wrap;html=1;collapsible=0;horizontal=1;"
                f"startSize={LANE_HEADER};fillColor=#fafafa;strokeColor=#999999;fontStyle=1;"
            ),
            vertex="1",
            parent="1",
        )
        ET.SubElement(
            lane, "mxGeometry", x="20", y=str(y), width=str(lane_w), height=str(lane_h), **{"as": "geometry"}
        )
        for i, n in enumerate(nodes):
            col, row = i % COLS, i // COLS
            obj = _object(root, n, base_url, marked)
            cell = ET.SubElement(obj, "mxCell", style=node_style(n, marked), vertex="1", parent=lane_id)
            ET.SubElement(
                cell,
                "mxGeometry",
                x=str(GAP_X + col * (cell_w + GAP_X)),
                y=str(LANE_HEADER + GAP_Y + row * (cell_h + GAP_Y)),
                width=str(sizes[n.id][0]),
                height=str(sizes[n.id][1]),
                **{"as": "geometry"},
            )
        y += lane_h + LANE_GAP

    _edges(root, view, marked)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode")


def node_size(n: ViewNode) -> tuple[int, int]:
    """A box wide enough for the name in it.

    Every shape the same size turns an export into a grid of identical rectangles with the
    names trimmed inside them — a picture of the layout rather than of the model. This is
    only for a view nobody has arranged; once the reader has dragged the shapes, the sizes
    the browser reports are used instead.
    """
    label = f"{n.glyph} {n.name}".strip() or n.id
    lines = textwrap.wrap(label, WRAP_CHARS) or [label]
    widest = max(len(line) for line in lines)
    width = max(NODE_W, min(NODE_W_MAX, int(widest * CHAR_W) + 28))
    height = max(NODE_H, 24 + len(lines) * LINE_H)
    return width, height


def _document(view: View) -> tuple[ET.Element, ET.Element]:
    mxfile = ET.Element(
        "mxfile",
        host="ea-repository",
        modified=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        agent="ea-repository view export",
        version="1",
    )
    diagram = ET.SubElement(mxfile, "diagram", id="view", name=view.title[:80])
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
        pageWidth="1169",
        pageHeight="827",
    )
    root = ET.SubElement(model, "root")
    _cell(root, "0")
    _cell(root, "1", parent="0")
    return mxfile, root


def _object(root: ET.Element, n: ViewNode, base_url: str, marked: bool = False) -> ET.Element:
    """The linking contract: every shape carries its element identifier and a link to its page."""
    obj = ET.SubElement(
        root,
        "object",
        label=_label(n, marked),
        ea_id=n.id,
        ea_type=n.type_id,
        ea_type_name=n.type_name,
        ea_stereotype=n.stereotype,
        ea_current_state=n.current_state,
        ea_target_state=n.target_state,
        id=n.id,
    )
    if base_url:
        obj.set("link", f"{base_url}/element/{n.id}")
    return obj


def _edges(root: ET.Element, view: View, marked: bool = False) -> None:
    ids = set(view.ids())
    for i, e in enumerate(view.edges):
        if e.src not in ids or e.dst not in ids:
            continue
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=open;endFill=0;strokeColor=#555555;fontSize=10;"
        st = TARGET_STYLE.get(e.target_state)
        if marked and st and e.target_state not in ("undecided", "keep"):
            style += f"strokeColor={st['hex']};strokeWidth=2;"
            if e.target_state in ("new", "merge"):
                style += "dashed=1;"
        cell = _cell(
            root,
            f"edge_{i}",
            value=e.label,
            style=style,
            edge="1",
            parent="1",
            source=e.src,
            target=e.dst,
        )
        ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})


def _to_drawio_positioned(
    view: View, base_url: str, positions: dict[str, dict[str, float]], marked: bool = False
) -> str:
    mxfile, root = _document(view)
    margin = 40
    xs = [p["x"] - p.get("w", NODE_W) / 2 for p in positions.values()]
    ys = [p["y"] - p.get("h", NODE_H) / 2 for p in positions.values()]
    ox = min(xs) - margin if xs else 0
    oy = min(ys) - margin if ys else 0

    def box(n: ViewNode) -> tuple[float, float, float, float]:
        p = positions.get(n.id)
        if p is None:
            return (margin, margin, NODE_W, NODE_H)
        w, h = p.get("w") or NODE_W, p.get("h") or NODE_H
        return (p["x"] - w / 2 - ox, p["y"] - h / 2 - oy, w, h)

    # layer boxes first, so they sit behind the shapes
    pad = 24
    for layer in sorted(view.layers(), key=layer_rank):
        nodes = [n for n in view.nodes_in(layer) if n.id in positions]
        if not nodes:
            continue
        boxes = [box(n) for n in nodes]
        x0 = min(b[0] for b in boxes) - pad
        y0 = min(b[1] for b in boxes) - pad - 22
        x1 = max(b[0] + b[2] for b in boxes) + pad
        y1 = max(b[1] + b[3] for b in boxes) + pad
        lane = _cell(
            root,
            f"lane_{layer}",
            value=LAYER_TITLES.get(layer, layer),
            style=(
                "rounded=0;whiteSpace=wrap;html=1;fillColor=#fafafa;strokeColor=#999999;dashed=1;"
                "verticalAlign=top;fontStyle=1;align=left;spacingLeft=8;fontSize=12;fontColor=#3e4c59;"
            ),
            vertex="1",
            parent="1",
        )
        ET.SubElement(
            lane,
            "mxGeometry",
            x=str(round(x0)),
            y=str(round(y0)),
            width=str(round(x1 - x0)),
            height=str(round(y1 - y0)),
            **{"as": "geometry"},
        )
    for n in view.nodes:
        x, y, w, h = box(n)
        obj = _object(root, n, base_url, marked)
        cell = ET.SubElement(obj, "mxCell", style=node_style(n, marked), vertex="1", parent="1")
        ET.SubElement(
            cell,
            "mxGeometry",
            x=str(round(x)),
            y=str(round(y)),
            width=str(round(w)),
            height=str(round(h)),
            **{"as": "geometry"},
        )
    _edges(root, view, marked)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode")
