"""The draw.io file as a drawing an architect edits rather than redraws (initiative 22, WP3).

Every test parses the XML and reads it the way draw.io would: a readable font on every
shape, a port and a label background on every edge, the ArchiMate arrowhead per kind of
relationship, a part inside its whole, bands that are backgrounds and not swimlanes, a title,
a legend and a page that fits. The golden files under `tests/golden/drawio/` pin the whole
file for the sample model, byte for byte (decision 0024).
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ea.models import ARCHIMATE_RELATIONSHIPS, Viewpoint
from ea.services.target import TARGET_STYLE
from ea.views import drawio
from ea.views.drawio import BAND_STYLE, EDGE_STYLE, LAYER_FILL, TITLE_H, to_drawio
from ea.views.layout import Band, Box, Layout, Route
from ea.views.layout import node_size as layout_node_size
from ea.views.model import (
    LAYER_TITLES,
    View,
    ViewEdge,
    ViewNode,
    apply_viewpoint,
    view_from_impact,
    view_from_neighbourhood,
)

STAMP = "2026-01-01T00:00:00Z"
BASE_URL = "http://localhost:8050"
GOLDEN = Path(__file__).parent / "golden" / "drawio"


# ------------------------------------------------------------------------ reading the file


def _root(xml: str) -> ET.Element:
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<mxfile ')
    return ET.fromstring(xml)


def _cells(root: ET.Element) -> dict[str, ET.Element]:
    """Every mxCell by id; a shape's cell takes the id of the object that wraps it."""
    out: dict[str, ET.Element] = {}
    for obj in root.iter("object"):
        cell = obj.find("mxCell")
        assert cell is not None
        out[obj.get("id")] = cell
    for cell in root.iter("mxCell"):
        if cell.get("id"):
            out[cell.get("id")] = cell
    return out


def _shapes(root: ET.Element) -> list[ET.Element]:
    """The objects drawn as a shape: an object whose cell is a band is the band, not a shape."""
    return [
        o for o in root.iter("object") if not (o.find("mxCell").get("style") or "").startswith(BAND_STYLE)
    ]


def _bands(root: ET.Element) -> dict[str, ET.Element]:
    """The band cells by id; a band that stands for an element takes the id of the object that wraps it."""
    out: dict[str, ET.Element] = {}
    for obj in root.iter("object"):
        cell = obj.find("mxCell")
        if (cell.get("style") or "").startswith(BAND_STYLE):
            out[obj.get("id")] = cell
    for cell in root.iter("mxCell"):
        if cell.get("id") and (cell.get("style") or "").startswith(BAND_STYLE):
            out[cell.get("id")] = cell
    return out


def _edges(root: ET.Element) -> list[ET.Element]:
    """The view's edges: the legend's sample lines are `legend_*`, not `edge_*`."""
    return [
        c for c in root.iter("mxCell") if c.get("edge") == "1" and (c.get("id") or "").startswith("edge_")
    ]


def _geo(cell: ET.Element) -> Box:
    g = cell.find("mxGeometry")
    assert g is not None
    return Box(
        float(g.get("x") or 0),
        float(g.get("y") or 0),
        float(g.get("width") or 0),
        float(g.get("height") or 0),
    )


def _order(root: ET.Element) -> list[str]:
    """Every cell's id in the order the file writes them, which is the order draw.io stacks them."""
    return [el.get("id") for el in root.iter() if (el.tag == "object" or el.tag == "mxCell") and el.get("id")]


def _style(cell: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for piece in (cell.get("style") or "").split(";"):
        key, _, value = piece.partition("=")
        if key:
            out[key] = value
    return out


# ------------------------------------------------------------------------ hand-built views


def _node(nid: str, name: str, type_id: str = "t", layer: str = "application", **kw) -> ViewNode:
    kw.setdefault("archimate", "ApplicationComponent")
    return ViewNode(nid, name, type_id, type_id.replace("_", " ").title(), layer=layer, **kw)


def _one_edge_per_kind() -> View:
    """A source and a target per ArchiMate relationship kind, plus one plain edge and one
    composition whose notation runs in reverse."""
    nodes, edges = [], []
    for kind in list(ARCHIMATE_RELATIONSHIPS) + [""]:
        key = kind or "plain"
        nodes += [_node(f"S-{key}", f"Source {key}"), _node(f"T-{key}", f"Target {key}", layer="technology")]
        edges.append(ViewEdge(f"S-{key}", f"T-{key}", key, f"r_{key}", archimate=kind))
    nodes += [_node("S-rev", "Part"), _node("T-rev", "Whole", layer="technology")]
    edges.append(ViewEdge("S-rev", "T-rev", "belongs to", "r_rev", archimate="composition", reversed=True))
    return View("Every kind", nodes=nodes, edges=edges)


def _nested_view() -> View:
    nodes = [
        _node("W", "Whole"),
        _node("P", "Part"),
        _node("Q", "Second part"),
        _node("O", "Outsider", layer="business", archimate="BusinessProcess"),
        _node("B", "Bar", layer="business", archimate="BusinessObject"),
    ]
    edges = [
        ViewEdge("W", "P", "contains", "t__contains__t", archimate="composition"),
        ViewEdge("W", "Q", "contains", "t__contains__t", archimate="composition"),
        ViewEdge("O", "W", "uses", "t__uses__t", archimate="serving"),
        ViewEdge("P", "O", "serves", "t__serves__t", archimate="serving"),
        ViewEdge("B", "O", "spans", "t__spans__t", archimate="access"),
    ]
    return View("Nested", nodes=nodes, edges=edges)


def _nested_layout() -> Layout:
    """What the layout module promises for `_nested_view`: W holds P and Q, B is a bar, the
    two composition edges and the span edge are shown some other way, and the serving edges
    are routed with a bend each."""
    boxes = {
        "W": Box(64, 96, 420, 190),
        "P": Box(80, 140, 180, 70),
        "Q": Box(280, 140, 180, 70),
        "O": Box(64, 380, 180, 70),
        "B": Box(64, 470, 300, 40),
    }
    bands = [
        Band("application", "Application", Box(40, 40, 480, 280), ["W"]),
        Band("business", "Business", Box(40, 340, 480, 200), ["O", "B"]),
    ]
    return Layout(
        boxes=boxes,
        bands=bands,
        parents={"P": "W", "Q": "W"},
        spans={"B"},
        hidden_edges={0, 1, 4},
        routes={
            2: Route(exit=(0.5, 0.0), entry=(0.25, 1.0), points=[(154, 330)]),
            3: Route(exit=(0.75, 1.0), entry=(0.75, 0.0), points=[(215, 330), (199, 330)]),
        },
        notes=["One relationship is shown as a bar."],
        width=560,
        height=580,
    )


def _process_view() -> View:
    """Two roles, three processes, two of them performed by a role: what the sample model has
    none of, so the test brings its own."""
    nodes = [
        _node("R-A", "Assessor", "role", "business", archimate="BusinessRole"),
        _node("R-B", "Bursar", "role", "business", archimate="BusinessRole"),
        _node("P-1", "Assess", "process", "business", archimate="BusinessProcess"),
        _node("P-2", "Bill", "process", "business", archimate="BusinessProcess"),
        _node("P-3", "Audit", "process", "business", archimate="BusinessProcess"),
    ]
    edges = [
        ViewEdge("R-A", "P-1", "performs", "role__performs__process", archimate="assignment"),
        ViewEdge("R-B", "P-2", "performs", "role__performs__process", archimate="assignment"),
        ViewEdge("P-1", "P-2", "triggers", "process__triggers__process", archimate="triggering"),
    ]
    return View("Processes", nodes=nodes, edges=edges)


def _positions(view: View, step: int = 260) -> dict[str, dict[str, float]]:
    """A browser arrangement: shapes on a diagonal, so every pair differs in both x and y."""
    return {
        n.id: {"x": 100.0 + step * i, "y": 80.0 + 90.0 * i, "w": 200, "h": 80}
        for i, n in enumerate(view.nodes)
    }


# --------------------------------------------------------------------------- the mechanics


def test_node_size_is_the_layout_module_s():
    """An older import of `node_size` from the exporter still works, and measures the same."""
    assert drawio.node_size is layout_node_size


def test_every_shape_reads_at_fourteen_points(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    for xml in (to_drawio(view, BASE_URL), to_drawio(view, BASE_URL, _positions(view))):
        shapes = _shapes(_root(xml))
        assert len(shapes) == len(view.nodes)
        assert all(_style(o.find("mxCell")).get("fontSize") == "14" for o in shapes)
        assert all("swimlane" not in (c.get("style") or "") for c in _root(xml).iter("mxCell"))


def test_every_edge_has_ports_and_a_label_background(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    for xml in (to_drawio(view, BASE_URL), to_drawio(view, BASE_URL, _positions(view))):
        edges = _edges(_root(xml))
        assert edges
        for e in edges:
            st = _style(e)
            assert {"exitX", "exitY", "entryX", "entryY"} <= set(st), e.get("id")
            assert st["labelBackgroundColor"] == "#ffffff" and st["fontSize"] == "11"
            assert st["edgeStyle"] == "orthogonalEdgeStyle" and st["rounded"] == "1"
            assert e.get("value") and e.get("source") and e.get("target")


def test_the_arrowhead_follows_the_kind_of_relationship():
    view = _one_edge_per_kind()
    root = _root(to_drawio(view, modified=STAMP))
    edges = {e.get("id"): e for e in _edges(root)}
    assert len(edges) == len(view.edges)
    for i, e in enumerate(view.edges[:-1]):
        style = edges[f"edge_{i}"].get("style")
        assert EDGE_STYLE[e.archimate] in style, e.archimate
    assert "startArrow=diamondThin;startFill=1;endArrow=none;" in edges["edge_0"].get("style")
    # A composition whose notation runs in reverse: the diamond sits at the target, the whole.
    rev = edges[f"edge_{len(view.edges) - 1}"].get("style")
    assert "endArrow=diamondThin;endFill=1;startArrow=none;" in rev
    assert "startArrow=diamondThin" not in rev
    # A type with no notation is the plain directed line it always was.
    plain = edges[f"edge_{len(view.edges) - 2}"].get("style")
    assert "endArrow=open;endFill=0;" in plain and "startArrow" not in plain
    # Every kind is drawn, so the legend names every kind.
    names = {c.get("value") for c in root.iter("mxCell") if (c.get("id") or "").startswith("legend_")}
    assert {k.capitalize() for k in ARCHIMATE_RELATIONSHIPS} <= names and "Relationship" in names


def test_a_nested_part_is_a_child_of_its_whole(monkeypatch):
    view, lay = _nested_view(), _nested_layout()
    monkeypatch.setattr(drawio, "layout", lambda *a, **k: lay)
    root = _root(to_drawio(view, BASE_URL, modified=STAMP))
    cells = _cells(root)
    whole, part, second = cells["W"], cells["P"], cells["Q"]
    assert "container=1" in whole.get("style") and "verticalAlign=top;spacingTop=4;" in whole.get("style")
    assert whole.get("parent") == "1"
    for child, box in ((part, lay.boxes["P"]), (second, lay.boxes["Q"])):
        assert child.get("parent") == "W"
        g = _geo(child)
        assert (g.x, g.y) == (box.x - lay.boxes["W"].x, box.y - lay.boxes["W"].y)  # relative to the whole
        assert g.right <= _geo(whole).w and g.bottom <= _geo(whole).h  # and inside it
    # The whole is written before its parts, and every shape still carries the contract.
    order = [o.get("id") for o in root.iter("object")]
    assert order.index("W") < order.index("P") < order.index("Q")
    assert {o.get("ea_band") for o in root.iter("object") if o.get("id") in ("P", "Q")} == {""}
    assert next(o for o in root.iter("object") if o.get("id") == "W").get("ea_band") == "application"
    assert next(o for o in root.iter("object") if o.get("id") == "P").get("link") == f"{BASE_URL}/element/P"
    # A spanning shape is drawn as its bar, read from the left.
    bar = cells["B"]
    assert "align=left;spacingLeft=8;" in bar.get("style") and _geo(bar).w == 300
    # The note the layout added is written under the title.
    assert "shown as a bar" in cells["note"].get("value")


def test_hidden_edges_are_not_written_and_routes_are(monkeypatch):
    view, lay = _nested_view(), _nested_layout()
    monkeypatch.setattr(drawio, "layout", lambda *a, **k: lay)
    root = _root(to_drawio(view, modified=STAMP))
    edges = {e.get("id"): e for e in _edges(root)}
    assert set(edges) == {"edge_2", "edge_3"}  # 0, 1 are nesting; 4 is the span
    st = _style(edges["edge_2"])
    assert (st["exitX"], st["exitY"], st["entryX"], st["entryY"]) == ("0.5", "0", "0.25", "1")
    assert st["exitDx"] == "0" and st["entryDy"] == "0"
    # The bends sit in the same frame as the shapes: under the title block and the note.
    down = _geo(_cells(root)["O"]).y - lay.boxes["O"].y
    assert down > TITLE_H and _geo(_cells(root)["note"]).bottom <= lay.bands[0].box.y + down
    points = edges["edge_3"].findall("mxGeometry/Array[@as='points']/mxPoint")
    bent = str(330 + int(down))
    assert [(p.get("x"), p.get("y")) for p in points] == [("215", bent), ("199", bent)]
    # An edge to a child still names the child's own cell, which keeps its element identifier.
    assert edges["edge_3"].get("source") == "P" and edges["edge_3"].get("target") == "O"


def test_bands_are_backgrounds_not_swimlanes(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    root = _root(to_drawio(view, BASE_URL))
    bands = _bands(root)
    assert [b.get("value") for b in bands.values()] == ["Business", "Application"]
    assert list(bands) == ["lane_business", "lane_application"]
    band_ids = set(bands)
    for b in bands.values():
        st = _style(b)
        assert st["connectable"] == "0" and st["dashed"] == "1" and st["fontSize"] == "16"
        assert b.get("parent") == "1" and b.get("vertex") == "1"
    assert all(o.find("mxCell").get("parent") not in band_ids for o in _shapes(root))
    # Every shape lies inside the band it says it sits in.
    boxes = {b.get("value"): _geo(b) for b in bands.values()}
    for o in _shapes(root):
        g, band = _geo(o.find("mxCell")), boxes[LAYER_TITLES[o.get("ea_band")]]
        assert band.x <= g.x and g.right <= band.right and band.y <= g.y and g.bottom <= band.bottom, o.get(
            "ea_id"
        )
    # And the bands are written before the shapes, so they lie behind them.
    ids = _order(root)
    assert max(ids.index(b) for b in band_ids) < min(ids.index(o.get("id")) for o in _shapes(root))


def test_the_title_names_the_view_and_the_viewpoint(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    vp = registry.viewpoint("application_cooperation")
    narrowed = apply_viewpoint(view, vp, registry)
    root = _root(to_drawio(narrowed, BASE_URL, viewpoint=vp, modified=STAMP))
    title = _cells(root)["title"]
    st = _style(title)
    assert st["fontSize"] == "20" and st["fontStyle"] == "1"
    assert title.get("value").startswith(view.title + "<br>")
    assert "Application cooperation · exported 2026-01-01T00:00:00Z" in title.get("value")
    assert root.get("modified") == STAMP
    assert root.find("diagram").get("name") == f"{view.title} — Application cooperation"
    # What the viewpoint left out is said under the title, in grey.
    note = _cells(root)["note"]
    assert "outside the Application cooperation viewpoint" in note.get("value")
    assert _style(note)["fontSize"] == "11" and _style(note)["fontColor"] == "#6b7280"
    # A view with nothing to note has no note cell.
    assert "note" not in _cells(_root(to_drawio(view, BASE_URL, modified=STAMP)))
    # A long note on a narrow drawing gets the lines it needs, and the drawing starts under it.
    small = View(
        "small", nodes=[_node("A", "A"), _node("B", "B")], note="The drawing could not show this. " * 12
    )
    root = _root(to_drawio(small, BASE_URL, modified=STAMP))
    cells = _cells(root)
    assert _geo(cells["note"]).h > 3 * 14
    assert _geo(cells["note"]).bottom < min(_geo(b).y for b in _bands(root).values())
    assert cells["note"].get("value").endswith("show this.")


def test_the_legend_names_every_layer_present(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
    root = _root(to_drawio(view, BASE_URL, modified=STAMP))
    cells = _cells(root)
    assert _style(cells["legend"])["fontSize"] == "12" and cells["legend"].get("value") == "Legend"
    for layer in view.layers():
        swatch, name = cells[f"legend_layer_{layer}"], cells[f"legend_layer_{layer}_name"]
        assert _style(swatch)["fillColor"] == LAYER_FILL[layer] and _style(swatch)["strokeColor"] == "#999999"
        assert (_geo(swatch).w, _geo(swatch).h) == (24, 16)
        assert name.get("value") == LAYER_TITLES[layer]
    assert not any(
        k.startswith("legend_layer_")
        for k in cells
        if k[len("legend_layer_") :].split("_")[0] not in view.layers()
    )
    # More than one kind of relationship is drawn, so each gets a sample line with its name.
    kinds = {e.archimate for e in view.edges}
    assert len(kinds) > 1
    for kind in kinds:
        line = cells[f"legend_{kind or 'relationship'}"]
        assert line.get("edge") == "1" and EDGE_STYLE[kind] in line.get("style")
        assert line.get("value") == (kind or "relationship").capitalize()
        for end in ("a", "b"):
            dot = cells[f"legend_{kind or 'relationship'}_{end}"]
            assert dot.get("style") == "shape=ellipse;fillColor=none;strokeColor=none;"
            assert (_geo(dot).w, _geo(dot).h) == (1, 1)
    # The legend sits under the last band.
    lowest = max(_geo(b).bottom for b in _bands(root).values())
    assert _geo(cells["legend"]).y > lowest
    # One kind alone needs no sample line.
    one = View(
        "one kind",
        nodes=[_node("A", "A"), _node("B", "B")],
        edges=[ViewEdge("A", "B", "x", "r", archimate="serving")],
    )
    assert not [k for k in _cells(_root(to_drawio(one, modified=STAMP))) if k == "legend_serving"]


def test_a_marked_export_carries_the_target_states_and_their_legend(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
    root = _root(to_drawio(view, BASE_URL, marked=True, modified=STAMP))
    cells = _cells(root)
    states = {n.target_state for n in view.nodes} - {"undecided", "keep"}
    assert states
    for state in states:
        swatch = cells[f"legend_state_{state}"]
        assert _style(swatch)["strokeColor"] == TARGET_STYLE[state]["hex"]
        assert cells[f"legend_state_{state}_name"].get("value") == TARGET_STYLE[state]["label"]
    struck = [o for o in _shapes(root) if o.get("ea_target_state") == "decommission"]
    assert struck and all(o.get("label").startswith("<s>") for o in struck)
    assert all("strokeColor=#c92a2a" in o.find("mxCell").get("style") for o in struck)
    assert not [
        k for k in _cells(_root(to_drawio(view, BASE_URL, modified=STAMP))) if k.startswith("legend_state_")
    ]


def test_the_page_fits_the_content(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
    for xml in (to_drawio(view, BASE_URL), to_drawio(view, BASE_URL, _positions(view, 120))):
        root = _root(xml)
        model = root.find(".//mxGraphModel")
        w, h = int(model.get("pageWidth")), int(model.get("pageHeight"))
        assert w >= 1169 and h >= 827 and model.get("dx") == "0" and model.get("grid") == "1"
        top_level = [c for c in root.iter("mxCell") if c.get("vertex") == "1" and c.get("parent") == "1"]
        assert top_level and all(_geo(c).right <= w and _geo(c).bottom <= h for c in top_level)
        assert all(_geo(c).x >= 0 and _geo(c).y >= 0 for c in top_level)
    # A view of two shapes still gets the A4 page, not a page the size of two shapes.
    small = View("small", nodes=[_node("A", "A"), _node("B", "B")])
    model = _root(to_drawio(small, modified=STAMP)).find(".//mxGraphModel")
    assert (model.get("pageWidth"), model.get("pageHeight")) == ("1169", "827")


def test_the_positioned_path_honours_every_position_and_draws_bands_around_them(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    positions = _positions(view)
    positions["LDC-CURR"] = {"x": 1800.0, "y": 900.0, "w": 240, "h": 90}
    root = _root(to_drawio(view, BASE_URL, positions, modified=STAMP))
    boxes = {o.get("ea_id"): _geo(o.find("mxCell")) for o in _shapes(root)}
    assert set(boxes) == set(view.ids())
    # Every shape keeps its size, and every pair keeps its distance: the file is the screen shifted once.
    for nid, p in positions.items():
        assert (boxes[nid].w, boxes[nid].h) == (p["w"], p["h"])
    shifts = {
        (boxes[n].x - (p["x"] - p["w"] / 2), boxes[n].y - (p["y"] - p["h"] / 2)) for n, p in positions.items()
    }
    assert len(shifts) == 1
    assert min(b.x for b in boxes.values()) >= 0 and min(b.y for b in boxes.values()) >= 0
    # Nothing is nested or spanned, and every shape is on the page's own layer.
    assert all(o.find("mxCell").get("parent") == "1" for o in _shapes(root))
    assert not any("container=1" in o.find("mxCell").get("style") for o in _shapes(root))
    # The bands are drawn around their members, wherever the reader left them.
    bands = {b.get("value"): _geo(b) for b in _bands(root).values()}
    assert set(bands) == {"Business", "Application"}
    for n in view.nodes:
        band, g = bands[LAYER_TITLES[n.layer]], boxes[n.id]
        assert band.x < g.x and g.right < band.right and band.y < g.y and g.bottom < band.bottom, n.id
    # The edges are routed between the placed shapes, with a port at each end.
    assert _edges(root) and all(
        "exitX=" in e.get("style") and "entryX=" in e.get("style") for e in _edges(root)
    )
    # A size the browser could not measure falls back to the measured one, not to nothing.
    unmeasured = {n.id: {"x": 100.0 + 300 * i, "y": 100.0, "w": 0, "h": 0} for i, n in enumerate(view.nodes)}
    sizes = {
        o.get("ea_id"): _geo(o.find("mxCell")) for o in _shapes(_root(to_drawio(view, BASE_URL, unmeasured)))
    }
    assert all((s.w, s.h) == layout_node_size(n) for n in view.nodes for s in [sizes[n.id]])
    # A shape the browser never placed is still drawn, under the ones it did.
    partial = {k: v for k, v in positions.items() if k != "LDC-CURR"}
    boxes = {
        o.get("ea_id"): _geo(o.find("mxCell")) for o in _shapes(_root(to_drawio(view, BASE_URL, partial)))
    }
    assert boxes["LDC-CURR"].y > max(b.bottom for k, b in boxes.items() if k != "LDC-CURR")


def test_the_linking_contract_holds_on_both_paths(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    for xml in (to_drawio(view, BASE_URL), to_drawio(view, BASE_URL, _positions(view))):
        shapes = _shapes(_root(xml))
        assert {o.get("ea_id") for o in shapes} == set(view.ids())
        for o in shapes:
            n = next(n for n in view.nodes if n.id == o.get("ea_id"))
            assert o.get("id") == n.id and o.get("label") == n.name
            assert o.get("link") == f"{BASE_URL}/element/{n.id}"
            assert (o.get("ea_type"), o.get("ea_type_name"), o.get("ea_stereotype")) == (
                n.type_id,
                n.type_name,
                n.stereotype,
            )
            assert (o.get("ea_current_state"), o.get("ea_target_state")) == (n.current_state, n.target_state)
            assert o.get("ea_band") == n.layer
    assert "link=" not in to_drawio(view)  # no base URL, no link


def test_a_band_element_is_drawn_as_a_band_not_a_shape(registry):
    vp = registry.viewpoint("process_cooperation")
    assert vp is not None and vp.bands == "related"
    view = apply_viewpoint(_process_view(), vp, registry)
    assert {n.id for n in view.nodes if n.is_band} == {"R-A", "R-B"}
    for xml in (
        to_drawio(view, BASE_URL, viewpoint=vp, modified=STAMP),
        to_drawio(view, BASE_URL, _positions(view), viewpoint=vp),
    ):
        root = _root(xml)
        assert {o.get("ea_id") for o in _shapes(root)} == {"P-1", "P-2", "P-3"}
        bands = _bands(root)
        assert set(bands) == {"R-A", "R-B", "lane_other"}
        # The band that stands for an element carries the element's contract, and its name.
        roles = {o.get("ea_id"): o for o in root.iter("object") if o.get("ea_id") in ("R-A", "R-B")}
        assert (
            roles["R-A"].get("label") == "Assessor" and roles["R-A"].get("link") == f"{BASE_URL}/element/R-A"
        )
        assert roles["R-A"].get("ea_type") == "role"
        assert bands["lane_other"].get("value") == vp.other_band
        by_id = {o.get("ea_id"): o for o in _shapes(root)}
        assert (by_id["P-1"].get("ea_band"), by_id["P-2"].get("ea_band"), by_id["P-3"].get("ea_band")) == (
            "R-A",
            "R-B",
            "other",
        )
        # The band is the "performs" relationship drawn, so no line says it again; the trigger is drawn.
        edges = _edges(root)
        assert [e.get("value") for e in edges] == ["triggers"]
        assert "endArrow=block;endFill=1;" in edges[0].get("style")


def test_the_same_view_gives_the_same_bytes(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
    assert to_drawio(view, BASE_URL, modified=STAMP) == to_drawio(view, BASE_URL, modified=STAMP)
    positions = _positions(view)
    assert to_drawio(view, BASE_URL, positions, modified=STAMP) == to_drawio(
        view, BASE_URL, positions, modified=STAMP
    )
    # Without a stamp the file is stamped now, which is the one thing that may differ.
    assert 'modified="' in to_drawio(view, BASE_URL)


def test_an_unknown_viewpoint_falls_back_to_the_layered_drawing(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    plain = to_drawio(view, BASE_URL, modified=STAMP)
    assert plain == to_drawio(
        view, BASE_URL, viewpoint=Viewpoint(id="layered", name="Layered"), modified=STAMP
    )
    assert "— Layered" in plain


# ------------------------------------------------------------------------ the golden files

GOLDEN_CASES = [
    "layered",
    "application_cooperation",
    "process_cooperation",
    "staged_delivery",
    "impact-layered",
    "layered-marked",
]


def _golden_export(registry, graph, name: str) -> str:
    """The export each golden file holds; `tests/golden/README.md` lists them."""
    if name == "impact-layered":
        vp = registry.viewpoint("layered")
        view = view_from_impact(registry, graph, graph.impact("DE-SRS-COURSE", 3))
        marked = False
    else:
        vp = registry.viewpoint("layered" if name == "layered-marked" else name)
        view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
        marked = name == "layered-marked"
    assert vp is not None, name
    return to_drawio(
        apply_viewpoint(view, vp, registry), BASE_URL, marked=marked, viewpoint=vp, modified=STAMP
    )


@pytest.mark.parametrize("name", GOLDEN_CASES)
def test_golden_file(registry, graph, name):
    """Byte for byte against `tests/golden/drawio/<name>.drawio`; `EA_UPDATE_GOLDEN=1` rewrites
    the file instead, for a change to the layout or the exporter made on purpose."""
    path = GOLDEN / f"{name}.drawio"
    text = _golden_export(registry, graph, name)
    if os.environ.get("EA_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    assert path.exists(), f"{path} is missing: run with EA_UPDATE_GOLDEN=1 to write it"
    golden = path.read_bytes().decode("utf-8")
    assert text == golden, (
        f"{path.name} differs from the export; EA_UPDATE_GOLDEN=1 rewrites it when the change is meant"
    )
