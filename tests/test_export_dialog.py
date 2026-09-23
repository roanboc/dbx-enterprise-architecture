"""The export dialogue: what it offers, what it says, and the view it hands to the file.

The dialogue's callbacks are thin over plain functions — the options, the summary line, the
narrowed and focused view — so those are proved here without a browser. The browser round
(group N) proves the dialogue opens from the draw.io button and the file comes down.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ea.metamodel import Registry
from ea.models import Viewpoint
from ea.ui.export import (
    KEEP_ARRANGEMENT,
    TITLE,
    about_text,
    export_ids,
    export_modal,
    export_view,
    focus_options,
    layer_options,
    resolve_viewpoint,
    suggested_viewpoint,
    summary_text,
    viewpoint_options,
)
from ea.views import DEFAULT_VIEWPOINT, apply_viewpoint, view_from_ids, view_from_neighbourhood
from ea.views.model import LAYER_TITLES

APPLICATION = "PAC-CMS"
PREFIXES = {"el": True, "imp": True, "tg": False, "ask": False, "mm": False}  # prefix: has a Depth control


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _ids(component) -> set[str]:
    return {node.id for node in _walk(component) if isinstance(getattr(node, "id", None), str)}


def _texts(component) -> list[str]:
    return [node.children for node in _walk(component) if isinstance(getattr(node, "children", None), str)]


# ------------------------------------------------------------------ the dialogue itself


def test_export_ids_are_distinct_per_prefix():
    el, imp = export_ids("el"), export_ids("imp")
    assert set(el) == {
        "modal",
        "about",
        "viewpoint",
        "focus",
        "depth",
        "layers",
        "arranged",
        "detail",
        "summary",
        "go",
    }
    assert set(el.values()).isdisjoint(imp.values())
    assert el["go"] == "el-export-go" and imp["modal"] == "imp-export-modal"


@pytest.mark.parametrize(("prefix", "with_depth"), PREFIXES.items())
def test_the_modal_builds_for_each_page(prefix, with_depth):
    modal = export_modal(prefix, with_depth=with_depth, depth_max=6 if prefix == "imp" else 3)
    eid = export_ids(prefix)
    found = _ids(modal)
    wanted = {v for k, v in eid.items() if k != "depth"}
    assert wanted <= found, sorted(wanted - found)
    assert (eid["depth"] in found) == with_depth
    assert TITLE in _texts(modal.title)  # the title is a prop of its own, with the full-screen toggle
    said = _texts(modal)
    assert "Download" in said and KEEP_ARRANGEMENT not in said  # the switch carries its label as a prop
    assert getattr(modal, "opened", False) is not True  # closed until the page's draw.io button opens it


def test_the_depth_control_reaches_as_far_as_the_page_allows():
    deep = next(
        n
        for n in _walk(export_modal("imp", with_depth=True, depth_max=6))
        if getattr(n, "id", "") == "imp-export-depth"
    )
    assert (deep.min, deep.max, deep.value) == (1, 6, 1)


# ------------------------------------------------------------------ the options


def test_viewpoint_options_follow_the_version(registry):
    options = viewpoint_options(registry)
    assert [o["value"] for o in options] == [v.id for v in registry.viewpoints()]
    assert [o["label"] for o in options] == [v.name for v in registry.viewpoints()]
    assert options[0]["value"] == "layered"
    bare = Registry(replace(registry.pack, viewpoints=[]))
    assert viewpoint_options(bare) == [{"value": "layered", "label": "Layered"}]
    assert resolve_viewpoint(bare, "layered") is DEFAULT_VIEWPOINT
    assert resolve_viewpoint(registry, "application_cooperation").name == "Application cooperation"
    assert resolve_viewpoint(registry, "no-such") is DEFAULT_VIEWPOINT


def test_the_dialogue_opens_on_the_viewpoint_the_view_carries(registry, graph):
    options = viewpoint_options(registry)
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    assert suggested_viewpoint(view, options) == options[0]["value"]
    narrowed = apply_viewpoint(view, registry.viewpoint("application_cooperation"), registry)
    assert suggested_viewpoint(narrowed, options) == "application_cooperation"
    narrowed.viewpoint = "gone"
    assert suggested_viewpoint(narrowed, options) == options[0]["value"]


def test_layer_and_focus_options_read_the_view(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    layers = layer_options(view)
    assert [o["value"] for o in layers] == view.layers()
    assert all(o["label"] == LAYER_TITLES[o["value"]] for o in layers)
    focus = focus_options(view)
    assert [o["value"] for o in focus] == view.ids()
    assert {"value": APPLICATION, "label": f"Curriculum Management System ({APPLICATION})"} in focus


def test_about_names_the_focus_or_the_whole_view(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    assert about_text(view) == "About Curriculum Management System"
    unfocused = view_from_ids(registry, graph, view.ids(), "Target state of the model")
    assert about_text(unfocused) == "About Target state of the model"


# ------------------------------------------------------------------ the summary and the file's view


def test_the_summary_counts_and_says_what_is_left_out(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    whole = summary_text(view, DEFAULT_VIEWPOINT, None, registry)
    assert whole == f"{len(view.nodes)} elements and {len(view.edges)} relationships"
    vp = registry.viewpoint("application_cooperation")
    narrowed = apply_viewpoint(view, vp, registry)
    outside = len(view.nodes) - len(narrowed.nodes)
    assert outside > 0
    assert summary_text(view, vp, None, registry) == (
        f"{len(narrowed.nodes)} elements and {len(narrowed.edges)} relationships; "
        f"{outside} outside this viewpoint not shown"
    )
    kept = apply_viewpoint(view, vp, registry, ["application"])
    unticked = len(narrowed.nodes) - len(kept.nodes)
    assert unticked > 0
    assert summary_text(view, vp, ["application"], registry).endswith(
        f"; {outside} outside this viewpoint and {unticked} in an unticked layer not shown"
    )
    # No layer ticked draws them all, which the dialogue says beside the control.
    assert summary_text(view, vp, [], registry) == summary_text(view, vp, None, registry)


def test_the_metamodel_view_is_not_narrowed_by_the_viewpoint(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    vp = Viewpoint(id="none", name="Nothing admitted", element_types=["data_product"])
    assert summary_text(view, vp, None, registry, narrow=False) == (
        f"{len(view.nodes)} elements and {len(view.edges)} relationships"
    )
    out = export_view(view, vp, None, [], registry, narrow=False)
    assert out.ids() == view.ids() and out.viewpoint == "none"


def test_export_view_marks_the_chosen_focus_and_nothing_else(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    other = next(n.id for n in view.nodes if n.id != APPLICATION)
    out = export_view(view, DEFAULT_VIEWPOINT, None, [other, "not-in-view"], registry)
    assert out.focus_ids == [other]
    assert {n.id for n in out.nodes if n.focus} == {other}
    # The page's own view keeps its focus: the copy was marked, not the original.
    assert view.focus_ids == [APPLICATION] and next(n for n in view.nodes if n.id == APPLICATION).focus
    assert not next(n for n in view.nodes if n.id == other).focus


def test_export_view_applies_the_layers_and_the_viewpoint(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    vp = registry.viewpoint("application_cooperation")
    out = export_view(view, vp, ["application"], [APPLICATION], registry)
    assert out.nodes and {n.layer for n in out.nodes} == {"application"}
    assert out.viewpoint == "application_cooperation" and out.focus_ids == [APPLICATION]
    assert "outside the Application cooperation viewpoint not shown" in out.note


def test_the_file_speaks_of_the_focus_the_reader_chose(registry, graph):
    """The note about a focus the viewpoint leaves out names the reader's focus, not the page's."""
    from ea.ui.export import export_view
    from ea.views import view_from_neighbourhood

    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    vp = registry.viewpoint("staged_delivery")  # admits no logical data component
    chosen = next(n.id for n in view.nodes if n.type_id == "data_entity")
    out = export_view(view, vp, None, [chosen], registry)
    assert "LDC-CURR" not in out.note and out.focus_ids == [chosen]
    assert [n.id for n in out.nodes if n.focus] == [chosen]


def test_the_summary_and_the_file_follow_the_detail_level(registry, graph):
    """Overview is the dialogue's default and says what it leaves out; Full draws everything."""
    from ea.ui.export import DEFAULT_DETAIL, export_view, summary_text
    from ea.views import view_from_neighbourhood

    assert DEFAULT_DETAIL == "overview"
    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 2)
    vp = registry.viewpoint("layered")
    full = summary_text(view, vp, None, registry, detail="full")
    brief = summary_text(view, vp, None, registry, detail="overview")
    assert "the overview leaves out" in brief and "leaves out" not in full
    drawn = export_view(view, vp, None, ["LDC-CURR"], registry, detail="overview")
    everything = export_view(view, vp, None, ["LDC-CURR"], registry, detail="full")
    assert drawn.detail == "overview" and everything.detail == "full"
    assert len(drawn.edges) < len(everything.edges)
    assert "LDC-CURR" in {n.id for n in drawn.nodes}


def test_keeping_the_arrangement_draws_the_full_view():
    """The arrangement on screen is of the full view, so a file that keeps it is full whatever
    the Detail control says; otherwise the control decides, Overview when it says nothing."""
    from ea.ui.export import level_for

    assert level_for("overview", arranged=True) == "full"
    assert level_for("overview", arranged=False) == "overview"
    assert level_for("full", arranged=False) == "full"
    assert level_for(None, arranged=False) == "overview"
