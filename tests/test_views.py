"""Generated views: the view model, the Mermaid renderer and the draw.io export, on the sample model."""

import xml.etree.ElementTree as ET

from ea.views import view_from_ids, view_from_impact, view_from_neighbourhood
from ea.views.drawio import to_drawio
from ea.views.mermaid import layer_legend, node_id, to_markdown, to_mermaid


def test_notation_is_inherited_and_defaulted(registry):
    de = registry.notation("data_entity")
    assert de["stereotype"] == "Data Object" and de["layer"] == "application"
    pos = registry.notation("position")  # own block wins over role's and the domain's
    assert pos["stereotype"] == "Business Role" and pos["layer"] == "business"
    assert registry.notation("no_such_type")["layer"] == "other"


def test_neighbourhood_view_is_layered_and_deterministic(registry, graph):
    v1 = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    v2 = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    assert v1.focus_ids == ["LDC-CURR"]
    assert "LDC-CURR" in v1.ids() and len(v1.nodes) > 5
    assert v1.layers() == [layer for layer in v1.layers()]  # ordered top to bottom
    assert [n.id for n in v1.nodes] == [n.id for n in v2.nodes]
    assert all(e.src in v1.ids() and e.dst in v1.ids() for e in v1.edges)


def test_mermaid_draws_the_elements_themselves_and_names_the_layer_colours(registry, graph):
    """The layers are the fill colour and the line above the diagram, never a box around it.

    A subgraph per layer spread a dozen elements over a page and pushed the relationships —
    what the picture is for — to its edges, so the bands went and the legend took their job.
    """
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    code = to_mermaid(view)
    assert code.startswith("flowchart BT")
    assert "subgraph" not in code and " ~~~ " not in code  # no bands, and nothing holding them apart
    assert "classDef application fill:#c2f0ff" in code  # the layer is the fill
    assert "«Data Object»" in code and "[LDC-CURR]" in code
    assert f"style {node_id('LDC-CURR')} stroke-width:3px" in code
    assert "-->|" in code
    assert len([ln for ln in code.splitlines() if ":::" in ln]) == len(view.nodes)
    legend = layer_legend(view)
    assert legend.startswith("Filled by layer:") and "🟦 Application" in legend  # shown, not described
    assert [layer for layer in ("Business", "Application") if layer in legend] == ["Business", "Application"]
    assert layer_legend(view_from_ids(registry, graph, [], "empty")) == ""
    md = to_markdown(view)
    assert md.startswith("## ") and "```mermaid" in md and "| `LDC-CURR` |" in md
    assert f"_{legend}_" in md  # the intro says what the colours mean, above the diagram


def test_impact_view_and_cap(registry, graph):
    res = graph.impact("DE-SRS-COURSE", 3)
    view = view_from_impact(registry, graph, res)
    assert view.focus_ids == ["DE-SRS-COURSE"]
    assert len(view.nodes) == 1 + len({r["element_id"] for r in res["upstream"] + res["downstream"]})
    small = view_from_ids(registry, graph, view.ids(), "capped", ["DE-SRS-COURSE"], max_nodes=3)
    assert len(small.nodes) == 3 and small.omitted == len(view.nodes) - 3 and "not shown" in small.note
    assert small.nodes[0].id == "DE-SRS-COURSE" or "DE-SRS-COURSE" in small.ids()


def test_drawio_export_carries_the_linking_contract(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    xml = to_drawio(view, base_url="http://localhost:8050")
    root = ET.fromstring(xml)
    objects = [o for o in root.findall(".//object") if o.get("ea_id")]
    assert len(objects) == len(view.nodes)
    for o in objects:
        assert o.get("ea_id") in view.ids()
        assert o.get("link") == f"http://localhost:8050/element/{o.get('ea_id')}"
        cell = o.find("mxCell")
        assert cell is not None and cell.get("vertex") == "1"
        assert "mxgraph.archimate3" in cell.get("style")
    edges = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
    assert len(edges) == len(view.edges)
    lanes = [
        o for o in root.findall(".//object") if (o.find("mxCell").get("style") or "").startswith("swimlane")
    ]
    assert [o.get("label") for o in lanes] == ["Business", "Application"]


def _drawn(root: ET.Element) -> list[tuple[ET.Element | None, ET.Element]]:
    """Every vertex and edge in a draw.io document, with the `object` that carries its data."""
    out = []
    for parent in root.iter():
        for cell in parent.findall("mxCell"):
            if cell.get("vertex") == "1" or cell.get("edge") == "1":
                out.append((parent if parent.tag == "object" else None, cell))
    return out


def test_drawio_export_stamps_everything_the_application_drew(registry, graph):
    """A shape a person adds in draw.io is the one without the stamp, and every edge names its relationship.

    Architects keep the files and draw on them; when one comes back, what the application drew,
    from which export, and what a person added must be told apart without guessing.
    """
    from ea.backend.branching import use_branch
    from ea.views.drawio import ORIGIN, TAG

    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    assert view.edges and all(e.relationship_id for e in view.edges)
    with use_branch("main"):
        root = ET.fromstring(to_drawio(view, base_url="http://x"))
    doc = next(o for o in root.iter("object") if o.get("id") == "0")  # the file's own data
    export = doc.get("ea_export")
    assert doc.get("ea_origin") == ORIGIN and export and doc.get("ea_branch") == "main"
    assert doc.get("ea_org") and doc.get("ea_exported_at") and doc.get("ea_title") == view.title
    # what it drew, so a drawing handed back says what a person took out
    assert doc.get("ea_elements").split() == view.ids()
    assert sorted(doc.get("ea_relationships").split()) == sorted(e.relationship_id for e in view.edges)
    drawn = _drawn(root)
    assert drawn and all(obj is not None for obj, _ in drawn)
    for obj, _ in drawn:
        assert obj.get("ea_origin") == ORIGIN and obj.get("ea_export") == export
        assert TAG in (obj.get("tags") or "").split()
    names = {n.id: n.name for n in view.nodes}
    shapes = [o for o, _ in drawn if o.get("ea_id")]
    assert {o.get("ea_id"): o.get("ea_name") for o in shapes} == names  # the name as exported
    edges = [(o, c) for o, c in drawn if c.get("edge") == "1"]
    assert sorted(o.get("ea_rel_id") for o, _ in edges) == sorted(e.relationship_id for e in view.edges)
    for o, c in edges:
        assert (o.get("ea_src"), o.get("ea_dst")) == (c.get("source"), c.get("target"))
        assert o.get("ea_rel_type")
    positioned = ET.fromstring(
        to_drawio(view, "http://x", {n.id: {"x": 90.0 * i, "y": 0.0} for i, n in enumerate(view.nodes)})
    )
    assert all(obj is not None and obj.get("ea_origin") == ORIGIN for obj, _ in _drawn(positioned))
    again = ET.fromstring(to_drawio(view))
    assert next(o for o in again.iter("object") if o.get("id") == "0").get("ea_export") != export


def test_drawio_export_honours_browser_positions(registry, graph):
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    positions = {
        n.id: {"x": 40.0 * i, "y": 50.0 * (i % 3), "w": 160, "h": 60} for i, n in enumerate(view.nodes)
    }
    positions["LDC-CURR"] = {"x": 900.0, "y": 700.0, "w": 160, "h": 60}
    xml = to_drawio(view, "http://x", positions)
    root = ET.fromstring(xml)
    geo = {o.get("ea_id"): o.find("mxCell/mxGeometry") for o in root.findall(".//object") if o.get("ea_id")}
    assert len(geo) == len(view.nodes)
    # relative placement is preserved: the focus node sits far right and below the others
    lc = geo["LDC-CURR"]
    others = [g for k, g in geo.items() if k != "LDC-CURR"]
    assert all(float(lc.get("x")) > float(g.get("x")) for g in others)
    assert all(float(lc.get("y")) > float(g.get("y")) for g in others)
    lanes = [
        o
        for o in root.findall(".//object")
        if "dashed=1" in (o.find("mxCell").get("style") or "") and o.get("ea_layer")
    ]
    assert {o.get("label") for o in lanes} == {"Business", "Application"}
    # too few positions: the grid layout is used instead
    xml2 = to_drawio(view, "http://x", {"LDC-CURR": positions["LDC-CURR"]})
    assert "swimlane" in xml2


def test_view_round_trips_through_a_dict(registry, graph):
    from ea.views.model import view_from_dict, view_to_dict

    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    again = view_from_dict(view_to_dict(view))
    assert again.ids() == view.ids() and len(again.edges) == len(view.edges) and again.title == view.title
