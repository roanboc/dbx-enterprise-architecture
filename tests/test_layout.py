"""The layered layout (decision 0024): bands, order, placement, nesting, spans and routes, on
hand-built views and on the sample model under the shipped viewpoints."""

from __future__ import annotations

from ea.models import Viewpoint
from ea.views import view_from_impact, view_from_neighbourhood
from ea.views.layout import (
    BAND_HEADER,
    BAND_PAD,
    MARGIN,
    MAX_ROW_W,
    NEST_PAD,
    NODE_H,
    NODE_W,
    Box,
    band_members,
    layout,
    node_size,
    routes_for,
)
from ea.views.model import DEFAULT_VIEWPOINT, View, ViewEdge, ViewNode, apply_viewpoint

# ----------------------------------------------------------------- hand-built views


def node(nid: str, layer: str = "business", type_id: str = "thing", **kw) -> ViewNode:
    return ViewNode(
        id=nid,
        name=kw.pop("name", nid),
        type_id=type_id,
        type_name=type_id.replace("_", " ").capitalize(),
        layer=layer,
        **kw,
    )


def edge(src: str, dst: str, rel: str = "relates", **kw) -> ViewEdge:
    return ViewEdge(src=src, dst=dst, label=rel, rel_type_id=rel, **kw)


def overlaps(a: Box, b: Box) -> bool:
    return a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom


def inside(inner: Box, outer: Box) -> bool:
    return (
        inner.x >= outer.x
        and inner.right <= outer.right
        and inner.y >= outer.y
        and inner.bottom <= outer.bottom
    )


def assert_well_formed(view: View, lay) -> None:
    """What every layout promises, whatever the view: a box per drawn node inside its band and
    inside the page, bands stacked in order across the full width, no two top-level shapes
    overlapping, every child inside its whole, and every edge either hidden or routed."""
    drawn = sorted(n.id for n in view.nodes if n.id not in lay.band_elements)
    assert sorted(lay.boxes) == drawn
    tops = [n for n in lay.boxes if n not in lay.parents]
    for i, a in enumerate(tops):
        for b in tops[i + 1 :]:
            assert not overlaps(lay.boxes[a], lay.boxes[b]), (a, b)
    placed = [n for band in lay.bands for n in band.nodes]
    assert sorted(placed) == sorted(tops)
    for band in lay.bands:
        assert band.box.x == MARGIN and band.box.right == lay.width - MARGIN
        for n in band.nodes:
            assert inside(lay.boxes[n], band.box), (n, band.title)
    for above, below in zip(lay.bands, lay.bands[1:], strict=False):
        assert below.box.y > above.box.bottom
    for child, whole in lay.parents.items():
        assert inside(lay.boxes[child], lay.boxes[whole]), (child, whole)
    for i in range(len(view.edges)):
        assert (i in lay.hidden_edges) != (i in lay.routes), i
    for box in lay.boxes.values():
        assert box.x >= MARGIN and box.y >= MARGIN
        assert box.right <= lay.width - MARGIN and box.bottom <= lay.height - MARGIN
    for r in lay.routes.values():
        assert all(0.0 <= f <= 1.0 for f in (*r.exit, *r.entry))


def port_point(box: Box, port: tuple[float, float]) -> tuple[float, float]:
    return box.x + port[0] * box.w, box.y + port[1] * box.h


# ------------------------------------------------------------------- the sample model


def test_the_shipped_viewpoints_lay_out_the_sample_views(registry, graph):
    """Every viewpoint the higher-education pack declares draws a neighbourhood and an impact
    from the sample without error, every drawn node boxed, and the same input twice gives
    the same drawing."""
    views = [
        view_from_neighbourhood(registry, graph, "LDC-CURR", 2),
        view_from_impact(registry, graph, graph.impact("DE-SRS-COURSE", 3)),
    ]
    viewpoints = registry.viewpoints()
    assert [v.id for v in viewpoints] == [
        "layered",
        "application_cooperation",
        "process_cooperation",
        "staged_delivery",
    ]
    for vp in viewpoints:
        for view in views:
            narrowed = apply_viewpoint(view, vp, registry)
            lay = layout(narrowed, vp)
            assert_well_formed(narrowed, lay)
            assert lay == layout(narrowed, vp)
            assert lay.bands, vp.id
    # The layered viewpoint nests the data entities in the logical data component that
    # encapsulates them, and the staged delivery viewpoint draws a data entity as a bar.
    layered = apply_viewpoint(views[0], viewpoints[0], registry)
    lay = layout(layered, viewpoints[0])
    assert lay.parents and all(layered.edges[i].rel_type_id in viewpoints[0].nest for i in lay.hidden_edges)
    assert "DE-SRS-COURSE" in lay.parents and lay.parents["DE-SRS-COURSE"] == "LDC-CURR"
    staged = apply_viewpoint(views[0], viewpoints[3], registry)
    lay = layout(staged, viewpoints[3])
    # A bar needs two shapes to span: the unit outline is processed by two applications and is
    # drawn as a bar across them; a course is processed by one and stays a shape under it.
    assert "DE-CMS-UNIT-OUTLINE" in lay.spans and "DE-SRS-COURSE" not in lay.spans and not lay.parents


def test_apply_viewpoint_marks_a_subtype_of_the_band_type_as_a_band_element(registry, graph):
    """A position is a role, so under bands by role a position is a band, not a shape."""
    vp = Viewpoint(
        id="by_role",
        name="By role",
        bands="related",
        band_type="role",
        band_relationships=["role__performs__process"],
    )
    view = apply_viewpoint(view_from_neighbourhood(registry, graph, "LDC-CURR", 2), vp, registry)
    positions = [n for n in view.nodes if n.type_id == "position"]
    assert positions and all(n.is_band for n in positions)
    assert all(not n.is_band for n in view.nodes if n.type_id != "position")
    lay = layout(view, vp)
    assert lay.band_elements == {n.id for n in positions}
    assert all(n.id not in lay.boxes for n in positions)
    titles = [b.title for b in lay.bands]
    assert titles[:-1] == sorted(n.name for n in positions) and titles[-1] == "Other"
    # Nothing in the sample is performed by a role, so every relationship to a position is
    # said in a note rather than drawn, and nothing is lost silently.
    assert lay.notes and all("also relates to" in note for note in lay.notes)
    assert_well_formed(view, lay)


# -------------------------------------------------------------------------- the bands


def test_bands_by_layer_follow_the_viewpoint_order_then_the_layers_own():
    view = View("v", nodes=[node("b1"), node("a1", "application"), node("t1", "technology")])
    vp = Viewpoint(id="v", name="v", band_order=["technology"])
    assert [b.key for b in band_members(view, vp)] == ["technology", "business", "application"]
    assert [b.key for b in band_members(view, DEFAULT_VIEWPOINT)] == ["business", "application", "technology"]
    assert [b.title for b in band_members(view, DEFAULT_VIEWPOINT)] == [
        "Business",
        "Application",
        "Technology",
    ]
    lay = layout(view, vp)
    assert [b.key for b in lay.bands] == ["technology", "business", "application"]
    assert_well_formed(view, lay)


def test_bands_by_type_follow_the_viewpoint_order_then_the_view():
    view = View(
        "v",
        nodes=[node("x", type_id="widget"), node("y", type_id="gadget"), node("z", type_id="sprocket")],
    )
    vp = Viewpoint(id="v", name="v", bands="type", band_order=["sprocket", "missing_type"])
    bands = band_members(view, vp)
    assert [b.key for b in bands] == ["sprocket", "widget", "gadget"]
    assert [b.title for b in bands] == ["Sprocket", "Widget", "Gadget"]
    assert_well_formed(view, layout(view, vp))


def related_view() -> tuple[View, Viewpoint]:
    """Two roles with processes, a third role with none, a process two roles perform, and an
    actor joined to a role through a relationship that is not a band relationship."""
    vp = Viewpoint(
        id="swim",
        name="Swimlanes",
        bands="related",
        band_type="role",
        band_relationships=["performs"],
        other_band="Unassigned",
    )
    nodes = [
        node("R1", name="Registrar", type_id="role", is_band=True),
        node("R2", name="Advisor", type_id="role", is_band=True),
        node("R3", name="Dean", type_id="role", is_band=True),
        node("P1", type_id="process", band="R1"),
        node("P2", type_id="process", band="R1"),
        node("P3", type_id="process", band="R2"),  # performed by R2 and R1: R2 (Advisor) comes first by name
        node("P4", type_id="process"),
        node("A1", type_id="actor"),
    ]
    edges = [
        edge("R1", "P1", "performs"),
        edge("R1", "P2", "performs"),
        edge("R2", "P3", "performs"),
        edge("R1", "P3", "performs"),
        edge("A1", "R2", "acts_as"),
        edge("R1", "R2", "reports_to"),
        edge("P1", "P2", "triggers"),
        edge("P3", "P4", "triggers"),
        edge("A1", "P4", "participates"),
    ]
    return View("v", nodes=nodes, edges=edges), vp


def test_bands_by_a_related_element_are_swimlanes():
    view, vp = related_view()
    bands = band_members(view, vp)
    assert [(b.title, b.element_id, b.nodes) for b in bands] == [
        ("Advisor", "R2", ["P3"]),
        ("Dean", "R3", []),  # a role with nothing to perform is still a lane
        ("Registrar", "R1", ["P1", "P2"]),
        ("Unassigned", "", ["P4", "A1"]),
    ]
    lay = layout(view, vp)
    assert_well_formed(view, lay)
    assert lay.band_elements == {"R1", "R2", "R3"}
    assert [b.title for b in lay.bands] == ["Advisor", "Dean", "Registrar", "Unassigned"]
    dean = lay.bands[1]
    assert dean.nodes == [] and dean.box.h == BAND_HEADER + 2 * BAND_PAD
    # Membership is the band, so its edges are not lines; a relationship to another band is
    # said once per node; an edge between two bands has nothing to be drawn between.
    assert lay.hidden_edges == {0, 1, 2, 3, 4, 5}
    assert lay.notes == ["A1 also relates to Advisor", "P3 also relates to Registrar"]
    assert set(lay.routes) == {6, 7, 8}


def test_bands_by_a_related_element_fall_back_to_the_type_when_nothing_is_marked():
    view = View("v", nodes=[node("R", type_id="role"), node("P", type_id="process")])
    vp = Viewpoint(id="v", name="v", bands="related", band_type="role")
    assert [(b.title, b.nodes) for b in band_members(view, vp)] == [("R", []), ("Other", ["P"])]


# ------------------------------------------------------------------------------ nesting


def test_nesting_puts_the_part_inside_the_whole_and_out_of_its_own_band():
    view = View(
        "v",
        nodes=[node("W", name="Whole"), node("P", "application", name="Part"), node("O", "application")],
        edges=[edge("W", "P", "contains"), edge("O", "P", "uses")],
    )
    vp = Viewpoint(id="v", name="v", nest=["contains"])
    lay = layout(view, vp)
    assert_well_formed(view, lay)
    assert lay.parents == {"P": "W"} and lay.hidden_edges == {0}
    whole, part = lay.boxes["W"], lay.boxes["P"]
    assert inside(part, whole) and whole.w >= part.w + 2 * NEST_PAD
    assert part.y > whole.y + NEST_PAD  # under the whole's own name
    assert [b.nodes for b in lay.bands] == [["W"], ["O"]]
    assert set(lay.routes) == {1}  # the line to the part reaches the part's own box
    assert (
        lay.routes[1].exit[1] == 0.0 and lay.routes[1].entry[1] == 1.0
    )  # O sits below W's part: top to bottom


def test_a_reversed_notation_nests_the_source_inside_the_target():
    view = View("v", nodes=[node("P"), node("W")], edges=[edge("P", "W", "constitutes", reversed=True)])
    lay = layout(view, Viewpoint(id="v", name="v", nest=["constitutes"]))
    assert lay.parents == {"P": "W"}
    assert_well_formed(view, lay)


def test_nesting_is_several_levels_deep_and_a_whole_grows_to_hold_it_all():
    view = View(
        "v",
        nodes=[node("A"), node("B"), node("C"), node("D")],
        edges=[edge("A", "B", "contains"), edge("B", "C", "contains"), edge("B", "D", "contains")],
    )
    lay = layout(view, Viewpoint(id="v", name="v", nest=["contains"]))
    assert_well_formed(view, lay)
    assert lay.parents == {"B": "A", "C": "B", "D": "B"}
    assert inside(lay.boxes["C"], lay.boxes["B"]) and inside(lay.boxes["B"], lay.boxes["A"])
    assert not overlaps(lay.boxes["C"], lay.boxes["D"])
    assert lay.boxes["A"].w > lay.boxes["B"].w > lay.boxes["C"].w
    assert [b.nodes for b in lay.bands] == [["A"]]


def test_a_part_with_two_wholes_takes_the_first_by_name_and_a_cycle_is_broken():
    view = View(
        "v",
        nodes=[node("Z", name="Zed"), node("A", name="Alpha"), node("P", name="Part")],
        edges=[edge("Z", "P", "contains"), edge("A", "P", "contains")],
    )
    lay = layout(view, Viewpoint(id="v", name="v", nest=["contains"]))
    assert_well_formed(view, lay)
    assert lay.parents == {"P": "A"} and lay.hidden_edges == {1} and set(lay.routes) == {0}

    cycle = View(
        "v", nodes=[node("X"), node("Y")], edges=[edge("X", "Y", "contains"), edge("Y", "X", "contains")]
    )
    lay = layout(cycle, Viewpoint(id="v", name="v", nest=["contains"]))
    assert_well_formed(cycle, lay)
    assert lay.parents == {"X": "Y"} and lay.hidden_edges == {1}  # the first part by name, X, takes its whole
    assert lay.routes[0].exit == (0.5, 0.0) and lay.routes[0].entry == (0.5, 0.0)  # from Y's name down to X


# -------------------------------------------------------------------------------- spans


def test_a_spanning_node_is_a_bar_across_the_shapes_it_relates_to():
    view = View(
        "v",
        nodes=[node("S1"), node("S2"), node("S3"), node("T", "application"), node("O", "application")],
        edges=[edge("S1", "T", "processes"), edge("S3", "T", "processes"), edge("S2", "O", "uses")],
    )
    vp = Viewpoint(id="v", name="v", span=["processes"])
    lay = layout(view, vp)
    assert_well_formed(view, lay)
    assert lay.spans == {"T"} and lay.hidden_edges == {0, 1} and set(lay.routes) == {2}
    bar, s1, s3 = lay.boxes["T"], lay.boxes["S1"], lay.boxes["S3"]
    assert bar.x <= min(s1.x, s3.x) and bar.right >= max(s1.right, s3.right)
    assert bar.h == NODE_H and bar.w > lay.boxes["S2"].w  # across S2, which sits between S1 and S3
    band = lay.bands[1]
    assert band.nodes == ["O", "T"] and bar.y >= lay.boxes["O"].bottom  # a row of its own, at the bottom


def test_a_bar_is_at_least_as_wide_as_its_name_and_a_bar_may_span_bars():
    view = View(
        "v",
        nodes=[
            node("S1"),
            node("S2"),
            node("T", "application", name="A bar with a very long name indeed"),
            node("V", "application"),
            node("U", "technology"),
        ],
        edges=[
            edge("S1", "T", "processes"),
            edge("S2", "T", "processes"),
            edge("T", "U", "processes"),
            edge("V", "U", "processes"),
        ],
    )
    lay = layout(view, Viewpoint(id="v", name="v", span=["processes"]))
    assert_well_formed(view, lay)
    assert lay.spans == {"T", "U"}
    assert lay.boxes["T"].w >= node_size(view.nodes[2])[0] > lay.boxes["S1"].w
    assert lay.boxes["T"].x <= lay.boxes["S1"].x and lay.boxes["T"].right >= lay.boxes["S2"].right
    assert lay.boxes["U"].x <= lay.boxes["T"].x and lay.boxes["U"].right >= lay.boxes["V"].right


def test_a_spanning_node_needs_two_sources_and_never_nests():
    """A bar needs two shapes to span: one source, or none, leaves the node an ordinary shape
    joined to it by a line; and a bar holds nothing, whatever the viewpoint nests by."""
    view = View(
        "v",
        nodes=[node("S1"), node("S2"), node("T", "application"), node("X", "application")],
        edges=[
            edge("S1", "T", "processes"),
            edge("S2", "T", "processes"),
            edge("T", "X", "contains"),
            edge("T", "S1", "processes", reversed=True),
        ],
    )
    vp = Viewpoint(id="v", name="v", span=["processes"], nest=["contains"])
    lay = layout(view, vp)
    assert_well_formed(view, lay)
    assert lay.spans == {"T"} and lay.hidden_edges == {0, 1, 3} and not lay.parents  # a bar holds nothing
    alone = View("v", nodes=[node("T")], edges=[])
    assert layout(alone, vp).spans == set()
    unsourced = View("v", nodes=[node("S1"), node("T")], edges=[edge("S1", "T", "other")])
    assert layout(unsourced, vp).spans == set()
    one = View("v", nodes=[node("S1"), node("T", "application")], edges=[edge("S1", "T", "processes")])
    lay = layout(one, vp)
    assert lay.spans == set() and lay.hidden_edges == set() and 0 in lay.routes  # drawn as a line


# ----------------------------------------------------------------- order and placement


def test_the_order_within_a_band_uncrosses_the_lines_to_the_band_above():
    view = View(
        "v",
        nodes=[node("A"), node("B"), node("C", "application"), node("D", "application")],
        edges=[edge("A", "D"), edge("B", "C")],
    )
    lay = layout(view)
    assert_well_formed(view, lay)
    a, b, c, d = (lay.boxes[k] for k in "ABCD")
    assert (a.cx < b.cx) == (d.cx < c.cx)  # whichever band was reordered, the two lines do not cross


def test_a_shape_is_pulled_under_the_mean_of_its_neighbours_above():
    view = View(
        "v",
        nodes=[node("A"), node("B"), node("C"), node("X", "application")],
        edges=[edge("B", "X"), edge("C", "X")],
    )
    lay = layout(view)
    assert_well_formed(view, lay)
    b, c, x = lay.boxes["B"], lay.boxes["C"], lay.boxes["X"]
    assert abs(x.cx - (b.cx + c.cx) / 2) <= 1
    assert lay.boxes["A"].x == MARGIN + BAND_PAD  # the band above stays where it is


def test_the_focus_comes_first_among_ties_and_the_rest_follow_the_name():
    view = View(
        "v", nodes=[node("b", name="beta"), node("a", name="alpha"), node("f", name="zulu", focus=True)]
    )
    lay = layout(view)
    assert lay.bands[0].nodes == ["f", "a", "b"]
    assert lay.boxes["f"].x < lay.boxes["a"].x < lay.boxes["b"].x


def test_a_wide_band_wraps_onto_more_rows():
    view = View("v", nodes=[node(f"n{i:02d}") for i in range(20)])
    lay = layout(view)
    assert_well_formed(view, lay)
    rows = sorted({b.y for b in lay.boxes.values()})
    assert len(rows) == 3  # 20 shapes of 180 plus the gaps: 7 to a row
    assert all(b.right - (MARGIN + BAND_PAD) <= MAX_ROW_W for b in lay.boxes.values())
    assert len(lay.bands) == 1 and lay.bands[0].box.h > 3 * NODE_H


def test_sizes_from_the_browser_override_the_measured_ones():
    view = View("v", nodes=[node("A"), node("B")])
    lay = layout(view, sizes={"A": (300, 90)})
    assert (lay.boxes["A"].w, lay.boxes["A"].h) == (300, 90)
    assert (lay.boxes["B"].w, lay.boxes["B"].h) == node_size(view.nodes[1])


def test_the_empty_view_is_an_empty_page():
    lay = layout(View("nothing"))
    assert lay.bands == [] and lay.boxes == {} and lay.routes == {}
    assert lay.width == lay.height == 2 * MARGIN


def test_node_size_grows_with_the_name_and_wraps_a_long_one():
    short, long = node("s", name="Short"), node("l", name="A name that runs on for rather longer than a box")
    assert node_size(short) == (NODE_W, NODE_H)
    w, h = node_size(long)
    assert w > NODE_W and h > NODE_H


# ------------------------------------------------------------------------------- routes


def test_ports_are_spread_along_a_side_in_the_order_of_the_other_end():
    view = View(
        "v",
        nodes=[node("A"), node("B", "application"), node("C", "application"), node("D", "application")],
        edges=[edge("A", "D"), edge("A", "B"), edge("A", "C"), edge("B", "A")],
    )
    lay = layout(view)
    assert_well_formed(view, lay)
    exits = {i: lay.routes[i].exit for i in (0, 1, 2)}
    assert all(fy == 1.0 for _, fy in exits.values())  # all leave A at the bottom
    assert len({fx for fx, _ in exits.values()}) == 3
    by_target_x = sorted((lay.boxes[view.edges[i].dst].cx, i) for i in (0, 1, 2))
    assert [exits[i][0] for _, i in by_target_x] == sorted(fx for fx, _ in exits.values())
    # The edge coming back up from B leaves B's top and enters A's bottom, and each side it
    # shares with another edge gives it a point of its own.
    back = lay.routes[3]
    assert back.exit[1] == 0.0 and back.entry[1] == 1.0
    assert back.entry[0] not in {fx for fx, _ in exits.values()}
    assert back.exit != lay.routes[1].entry


def test_side_by_side_shapes_join_sideways_or_over_a_neighbour():
    view = View("v", nodes=[node("A"), node("B"), node("C")], edges=[edge("A", "B"), edge("A", "C")])
    lay = layout(view)
    assert_well_formed(view, lay)
    assert lay.bands[0].nodes == ["A", "B", "C"]
    assert lay.routes[0].exit == (1.0, 0.5) and lay.routes[0].entry == (0.0, 0.5) and not lay.routes[0].points
    detour = lay.routes[1]
    assert detour.exit[1] == 0.0 and detour.entry[1] == 0.0 and len(detour.points) == 2
    band = lay.bands[0]
    assert all(y == band.box.y + BAND_HEADER / 2 for _, y in detour.points)
    (x0, _), (x1, _) = detour.points
    assert (
        x0 == port_point(lay.boxes["A"], detour.exit)[0] and x1 == port_point(lay.boxes["C"], detour.entry)[0]
    )
    assert lay.boxes["B"].right < x1 and x0 < lay.boxes["B"].x  # the bends bracket the shape between


def test_shapes_one_above_the_other_in_wrapped_rows_join_top_to_bottom():
    view = View("v", nodes=[node(f"n{i:02d}") for i in range(10)], edges=[edge("n00", "n07")])
    lay = layout(view)
    a, b = lay.boxes["n00"], lay.boxes["n07"]
    assert b.y >= a.bottom  # wrapped under it
    assert lay.routes[0].exit[1] == 1.0 and lay.routes[0].entry[1] == 0.0


def test_routes_for_leaves_out_hidden_edges_and_uses_the_child_box():
    view = View(
        "v", nodes=[node("W"), node("P"), node("O", "application")], edges=[edge("W", "P"), edge("O", "P")]
    )
    boxes = {"W": Box(0, 0, 300, 200), "P": Box(20, 50, 100, 60), "O": Box(20, 400, 100, 60)}
    routes = routes_for(view, boxes, parents={"P": "W"})
    assert set(routes) == {0, 1}
    assert routes[0].exit == (0.5, 0.0) and routes[0].entry == (0.5, 0.0)  # a whole to the shape inside it
    assert routes[1].exit == (0.5, 0.0) and routes[1].entry == (
        0.5,
        1.0,
    )  # up from O into the child's own box
    assert set(routes_for(view, boxes, hidden={0})) == {1}
    assert routes_for(view, boxes, hidden={0, 1}) == {}
