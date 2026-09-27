"""The layered layout: rows by layer, few crossings, lines of right angles that never cross a box."""

from __future__ import annotations

import itertools
import xml.etree.ElementTree as ET

from ea.views.drawio import to_drawio
from ea.views.layered import Box, Link, arrange, aspect_tier, fit_box, route
from ea.views.model import View, ViewEdge, ViewNode


def _boxes() -> tuple[list[Box], list[Link]]:
    """A business actor, three applications, two data objects and a platform, related across rows."""
    boxes = [
        Box("ACT", 160, 60, band=0, tier=1),
        Box("APP-A", 160, 60, band=1, tier=1),
        Box("APP-B", 160, 60, band=1, tier=1),
        Box("APP-C", 160, 60, band=1, tier=1),
        Box("DATA-1", 160, 60, band=1, tier=2),
        Box("DATA-2", 160, 60, band=1, tier=2),
        Box("PLAT", 160, 60, band=2, tier=1),
    ]
    links = [
        Link("e0", "ACT", "APP-C", "uses"),
        Link("e1", "APP-A", "DATA-2", "writes"),
        Link("e2", "APP-C", "DATA-1", "reads"),
        Link("e3", "PLAT", "APP-A", "realises"),
        Link("e4", "PLAT", "APP-C", "realises"),
        Link("e5", "ACT", "PLAT", "owns"),  # two bands apart: past the application rows
        Link("e6", "APP-A", "APP-B", "flows to"),
    ]
    return boxes, links


def _inside(p: tuple[float, float], b: Box, clear: float = 0.5) -> bool:
    return b.x + clear < p[0] < b.right - clear and b.y + clear < p[1] < b.bottom - clear


def _crosses(a: tuple[float, float], c: tuple[float, float], b: Box) -> bool:
    """Whether an upright or level segment runs through a box's inside."""
    if abs(a[1] - c[1]) < 0.01:
        return (
            b.y + 0.5 < a[1] < b.bottom - 0.5
            and min(a[0], c[0]) < b.right - 0.5
            and max(a[0], c[0]) > b.x + 0.5
        )
    return (
        b.x + 0.5 < a[0] < b.right - 0.5 and min(a[1], c[1]) < b.bottom - 0.5 and max(a[1], c[1]) > b.y + 0.5
    )


def test_bands_run_top_down_and_boxes_never_overlap():
    boxes, links = _boxes()
    plan = arrange(boxes, links)
    by_band = {}
    for b in plan.boxes.values():
        by_band.setdefault(b.band, []).append(b)
    assert max(b.bottom for b in by_band[0]) < min(b.y for b in by_band[1])
    assert max(b.bottom for b in by_band[1]) < min(b.y for b in by_band[2])
    for a, b in itertools.combinations(plan.boxes.values(), 2):
        assert a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y, (a.id, b.id)


def test_inside_a_related_band_what_is_worked_on_stands_below_what_works():
    boxes, links = _boxes()
    plan = arrange(boxes, links)
    apps = [plan.boxes[i] for i in ("APP-A", "APP-B", "APP-C")]
    data = [plan.boxes[i] for i in ("DATA-1", "DATA-2")]
    assert max(b.bottom for b in apps) < min(b.y for b in data)


def test_every_line_is_right_angled_runs_border_to_border_and_crosses_no_box():
    boxes, links = _boxes()
    plan = arrange(boxes, links)
    assert set(plan.routes) == {lk.key for lk in links}
    for lk in links:
        r = plan.routes[lk.key]
        src, dst = plan.boxes[lk.src], plan.boxes[lk.dst]
        assert len(r.points) >= 2
        for a, c in itertools.pairwise(r.points):
            assert abs(a[0] - c[0]) < 0.01 or abs(a[1] - c[1]) < 0.01, (lk.key, r.points)
            for b in plan.boxes.values():
                assert not _crosses(a, c, b), (lk.key, b.id, r.points)
        assert not _inside(r.points[0], src) and not _inside(r.points[-1], dst)
        assert (0 <= r.exit[0] <= 1 and 0 <= r.exit[1] <= 1) and (
            0 <= r.entry[0] <= 1 and 0 <= r.entry[1] <= 1
        )


def test_a_label_sits_on_its_line_and_on_no_box():
    boxes, links = _boxes()
    plan = arrange(boxes, links)
    for lk in links:
        r = plan.routes[lk.key]
        assert r.label_at is not None
        assert any(
            min(a[0], c[0]) - 0.5 <= r.label_at[0] <= max(a[0], c[0]) + 0.5
            and min(a[1], c[1]) - 0.5 <= r.label_at[1] <= max(a[1], c[1]) + 0.5
            for a, c in itertools.pairwise(r.points)
        ), lk.key
        assert not any(_inside(r.label_at, b) for b in plan.boxes.values()), lk.key
        assert 0.0 <= r.fraction(r.label_at) <= 1.0


def test_the_order_in_a_row_uncrosses_lines():
    # drawn in the order that crosses: A over Y, B over X
    boxes = [
        Box("A", 120, 50, band=0),
        Box("B", 120, 50, band=0),
        Box("X", 120, 50, band=1),
        Box("Y", 120, 50, band=1),
    ]
    plan = arrange(boxes, [Link("1", "A", "Y"), Link("2", "B", "X")])
    b = plan.boxes
    assert (b["A"].x < b["B"].x) == (b["Y"].x < b["X"].x)


def test_a_line_between_two_boxes_one_above_the_other_runs_straight():
    plan = arrange([Box("A", 160, 60, band=0), Box("B", 160, 60, band=1)], [Link("1", "A", "B")])
    assert len(plan.routes["1"].points) == 2


def test_a_layout_is_the_same_every_time():
    first = arrange(*_boxes())
    second = arrange(*_boxes())
    assert {k: (b.x, b.y) for k, b in first.boxes.items()} == {k: (b.x, b.y) for k, b in second.boxes.items()}
    assert {k: r.points for k, r in first.routes.items()} == {k: r.points for k, r in second.routes.items()}


def test_boxes_placed_by_hand_are_routed_where_they_stand():
    boxes = [Box("A", 120, 50, x=0, y=0), Box("B", 120, 50, x=300, y=200), Box("C", 120, 50, x=150, y=100)]
    routes = route(boxes, [Link("1", "A", "B")])
    assert [(b.x, b.y) for b in boxes] == [(0, 0), (300, 200), (150, 100)]
    pts = routes["1"].points
    for a, c in itertools.pairwise(pts):
        assert not _crosses(a, c, boxes[2])


def test_a_box_fits_its_name_and_the_aspects_order_a_layer():
    short, long = fit_box("SRS", "PAC-SRS"), fit_box("Curriculum to Student Administration interface", "IF-X")
    assert long[0] > short[0] and long[1] >= short[1]
    assert aspect_tier("ApplicationService") < aspect_tier("ApplicationComponent") < aspect_tier("DataObject")


def test_an_unarranged_draw_io_export_carries_the_routes():
    nodes = [
        ViewNode("A", "Alpha", "t", "T", layer="business", archimate="BusinessActor"),
        ViewNode("B", "Beta", "t", "T", layer="application", archimate="ApplicationComponent"),
        ViewNode("C", "Gamma", "t", "T", layer="technology", archimate="Node"),
    ]
    view = View("v", nodes=nodes, edges=[ViewEdge("A", "B", "uses"), ViewEdge("C", "A", "serves")])
    root = ET.fromstring(to_drawio(view))
    edges = [c for c in root.iter("mxCell") if c.get("edge") == "1"]
    assert len(edges) == 2
    for e in edges:
        assert "exitPerimeter=0" in e.get("style") and "entryPerimeter=0" in e.get("style")
    # the line from the platform to the actor passes the application row by a gutter: it bends
    passing = next(e for e in edges if e.get("source") == "C")
    assert passing.find("mxGeometry/Array") is not None
