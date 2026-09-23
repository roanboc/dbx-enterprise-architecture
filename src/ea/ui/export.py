"""The export dialogue: what a reader names before a view leaves as a draw.io file.

One dialogue serves the five pages that export a view (decision 0023): the viewpoint the
metamodel declares, the focus, the depth where the view grows from an element, the layers,
and whether the file keeps the arrangement on screen rather than the layout the viewpoint
gives. The page's draw.io button opens it; its own Download button writes the file through
the one shared `dcc.Download`. The Markdown download beside the button is untouched: a
Markdown document has no bands to choose.

The parts a callback computes — the options, the summary line, the view that goes to the
file — are plain functions, so they are provable without a browser.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, no_update
from dash import ctx as dash_ctx

from ea.metamodel.registry import Registry
from ea.models import Viewpoint
from ea.ui import ids
from ea.ui.components import icon, modal_title
from ea.ui.context import AppContext, get_context
from ea.views.drawio import to_drawio
from ea.views.model import DEFAULT_VIEWPOINT, LAYER_TITLES, View, apply_viewpoint

TITLE = "Export as a draw.io diagram"
KEEP_ARRANGEMENT = "Keep the arrangement on screen"

_SUFFIXES = {
    "modal": ids.EXPORT_MODAL,
    "about": ids.EXPORT_ABOUT,
    "viewpoint": ids.EXPORT_VIEWPOINT,
    "focus": ids.EXPORT_FOCUS,
    "depth": ids.EXPORT_DEPTH,
    "layers": ids.EXPORT_LAYERS,
    "arranged": ids.EXPORT_ARRANGED,
    "summary": ids.EXPORT_SUMMARY,
    "go": ids.EXPORT_GO,
}


def export_ids(prefix: str) -> dict[str, str]:
    """The ids of one page's dialogue, as <prefix>-<suffix>, so five pages never collide."""
    return {key: f"{prefix}-{suffix}" for key, suffix in _SUFFIXES.items()}


# ------------------------------------------------------------------ the pure parts


def viewpoint_options(registry: Registry) -> list[dict[str, str]]:
    """The viewpoints the version declares, by id and name, in its order; a pack that declares
    none is offered the layered drawing, which is what every pack exported before."""
    declared = registry.viewpoints() or [DEFAULT_VIEWPOINT]
    return [{"value": v.id, "label": v.name} for v in declared]


def resolve_viewpoint(registry: Registry, viewpoint_id: str | None) -> Viewpoint:
    """The viewpoint an id names; the layered default for a pack without any, or an id it lost."""
    return registry.viewpoint(viewpoint_id or "") or DEFAULT_VIEWPOINT


def suggested_viewpoint(view: View, options: list[dict[str, str]]) -> str:
    """The viewpoint the dialogue opens on: the one the view already carries when it is offered
    (an answer document may name one), else the first the version declares."""
    if any(o["value"] == view.viewpoint for o in options):
        return view.viewpoint
    return options[0]["value"]


def layer_options(view: View) -> list[dict[str, str]]:
    """The architecture layers present in the view, titled the way the legend titles them."""
    return [{"value": layer, "label": LAYER_TITLES.get(layer, layer)} for layer in view.layers()]


def focus_options(view: View) -> list[dict[str, str]]:
    """Every element the view holds, as `name (id)`, in the view's own order."""
    return [{"value": n.id, "label": f"{n.name} ({n.id})"} for n in view.nodes]


def about_text(view: View) -> str:
    """What the diagram is about: the focus elements by name, or the view's title when the view
    has no focus (the whole target state, the metamodel)."""
    by_id = {n.id: n.name for n in view.nodes}
    names = [by_id.get(i, i) for i in view.focus_ids]
    return "About " + (", ".join(names) if names else view.title)


def narrowed_view(
    view: View, viewpoint: Viewpoint, layers: list[str] | None, registry: Registry, narrow: bool = True
) -> View:
    """What the file will hold under the reader's choices.

    A content view is narrowed to what the viewpoint admits; the metamodel view is not
    (`narrow=False`: every type is drawn and the viewpoint governs the bands only), but the
    layers the reader unticked are left out either way. No layer ticked draws them all, and
    the dialogue says so beside the control.
    """
    out = apply_viewpoint(view, viewpoint if narrow else DEFAULT_VIEWPOINT, registry, layers or None)
    out.viewpoint = viewpoint.id
    return out


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def summary_text(
    view: View, viewpoint: Viewpoint, layers: list[str] | None, registry: Registry, narrow: bool = True
) -> str:
    """'12 elements and 15 relationships; 3 outside this viewpoint not shown' — what the file
    will hold under the current choices, and what it leaves out and why."""
    by_viewpoint = narrowed_view(view, viewpoint, None, registry, narrow)
    kept = narrowed_view(view, viewpoint, layers, registry, narrow)
    said = f"{_plural(len(kept.nodes), 'element')} and {_plural(len(kept.edges), 'relationship')}"
    left: list[str] = []
    outside = len(view.nodes) - len(by_viewpoint.nodes)
    if outside:
        left.append(f"{outside} outside this viewpoint")
    unticked = len(by_viewpoint.nodes) - len(kept.nodes)
    if unticked:
        left.append(f"{unticked} in an unticked layer")
    if left:
        said += "; " + " and ".join(left) + " not shown"
    return said


def export_view(
    view: View,
    viewpoint: Viewpoint,
    layers: list[str] | None,
    focus: list[str] | None,
    registry: Registry,
    narrow: bool = True,
) -> View:
    """The view that goes to the file: narrowed, with the focus the reader marked and nothing
    else marked. The nodes are copied, so the view the page holds is not marked with them."""
    out = narrowed_view(view, viewpoint, layers, registry, narrow)
    chosen = list(focus or [])
    wanted = set(chosen)
    out.nodes = [replace(n, focus=n.id in wanted) for n in out.nodes]
    present = {n.id for n in out.nodes}
    out.focus_ids = [i for i in chosen if i in present]
    return out


# ------------------------------------------------------------------ the dialogue


def export_modal(prefix: str, with_depth: bool = False, depth_max: int = 3) -> dmc.Modal:
    """The dialogue for one page. `with_depth` adds the Depth control, for a page whose view
    grows from an element, up to `depth_max` hops."""
    eid = export_ids(prefix)
    depth = (
        [
            dmc.NumberInput(
                id=eid["depth"],
                label="Depth",
                description="How many hops from the element the diagram reaches",
                min=1,
                max=depth_max,
                value=1,
                allowNegative=False,
                w=160,
            )
        ]
        if with_depth
        else []
    )
    return dmc.Modal(
        id=eid["modal"],
        title=modal_title(TITLE, eid["modal"]),
        closeButtonProps={"aria-label": "Close this dialog"},
        size="lg",
        children=dmc.Stack(
            [
                dmc.Text(id=eid["about"], size="sm", fw=500),
                dmc.Select(
                    id=eid["viewpoint"],
                    label="Viewpoint",
                    description=(
                        "What the diagram is for: which elements it admits and how it is banded, "
                        "as the metamodel declares it"
                    ),
                    data=[],
                    allowDeselect=False,
                ),
                dmc.MultiSelect(
                    id=eid["focus"],
                    label="Focus",
                    description="The elements the diagram is about; they are marked in the file",
                    data=[],
                    value=[],
                    searchable=True,
                    nothingFoundMessage="No element of that name in this view",
                ),
                *depth,
                dmc.MultiSelect(
                    id=eid["layers"],
                    label="Layers",
                    description="Untick a layer to leave it out; none ticked draws them all",
                    data=[],
                    value=[],
                ),
                dmc.Switch(
                    id=eid["arranged"],
                    label=KEEP_ARRANGEMENT,
                    description=(
                        "Every shape where you left it on screen, instead of the layout the viewpoint gives"
                    ),
                    checked=False,
                    disabled=True,
                    size="sm",
                ),
                dmc.Text(id=eid["summary"], size="sm", c="dimmed"),
                dmc.Group(
                    [dmc.Button("Download", id=eid["go"], leftSection=icon("tabler:download", 14))],
                    justify="flex-end",
                ),
            ],
            gap="sm",
        ),
    )


def _first_positions(raw: Any) -> dict[str, dict[str, float]] | None:
    """The browser's positions: one store's data, or under a wildcard (the Ask page, whose
    answer may hold no diagram) the first store that reports any."""
    if isinstance(raw, list):
        raw = next((p for p in raw if p), None)
    return raw or None


def _depth(value: Any) -> int:
    """A depth the reader emptied is the first hop, never nothing."""
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def register_export(
    app: dash.Dash,
    prefix: str,
    opener_id: str,
    build_view: Callable[..., View | None],
    file_stem: Callable[..., str],
    states: list[State],
    positions_id: Any = None,
    marked: bool = False,
    with_depth: bool = False,
    depth_id: str | None = None,
    registry_for: Callable[..., Registry] | None = None,
    narrow: bool = True,
    linked: bool = True,
) -> None:
    """Wire one page's dialogue: open it from the page's draw.io button, keep its summary
    true as the reader changes their mind, and write the file from the Download button.

    `build_view(ctx, depth, *values)` rebuilds the page's view from the values of `states`
    (the page's own controls or stores, read when the dialogue opens and again when it
    downloads, so the file is drawn from what the page shows now) and returns None when
    there is nothing to export yet; `file_stem(ctx, *values)` names the file without its
    suffix. `positions_id` is the page's position store, whose data lets the reader keep the
    arrangement on screen. `with_depth` adds the Depth control, seeded from the page's own
    depth control `depth_id`. `registry_for(ctx, *values)` names the version whose viewpoints
    are offered when it is not the applied one (the Metamodel page shows any version);
    `narrow=False` keeps every element whatever the viewpoint admits (the metamodel view,
    where the viewpoint governs the bands only), and `linked=False` writes no link back to an
    element page (a type has none).
    """
    eid = export_ids(prefix)
    positions = [State(positions_id, "data")] if positions_id is not None else []
    seed = [State(depth_id, "value")] if with_depth and depth_id else []
    depth_out = [Output(eid["depth"], "value")] if with_depth else []
    depth_in = [Input(eid["depth"], "value")] if with_depth else []
    depth_state = [State(eid["depth"], "value")] if with_depth else []

    def registry_of(ctx: AppContext, values: list[Any]) -> Registry:
        return registry_for(ctx, *values) if registry_for else ctx.registry

    @app.callback(
        Output(eid["modal"], "opened"),
        Output(eid["about"], "children"),
        Output(eid["viewpoint"], "data"),
        Output(eid["viewpoint"], "value"),
        Output(eid["focus"], "data"),
        Output(eid["focus"], "value"),
        Output(eid["layers"], "data"),
        Output(eid["layers"], "value"),
        Output(eid["arranged"], "checked"),
        Output(eid["arranged"], "disabled"),
        Output(eid["summary"], "children"),
        *depth_out,
        Input(opener_id, "n_clicks"),
        *positions,
        *seed,
        *states,
        prevent_initial_call=True,
    )
    def open_dialogue(n, *raw):
        quiet = (no_update,) * (11 + len(depth_out))
        if not n:
            return quiet
        values = list(raw)
        placed = _first_positions(values.pop(0)) if positions else None
        depth = _depth(values.pop(0)) if seed else 1
        ctx = get_context()
        view = build_view(ctx, depth if with_depth else None, *values)
        if view is None:
            return quiet
        registry = registry_of(ctx, values)
        options = viewpoint_options(registry)
        chosen = suggested_viewpoint(view, options)
        layers = layer_options(view)
        all_layers = [o["value"] for o in layers]
        out = (
            True,
            about_text(view),
            options,
            chosen,
            focus_options(view),
            list(view.focus_ids),
            layers,
            all_layers,
            False,
            # The switch can only keep an arrangement the browser has reported.
            placed is None,
            summary_text(view, resolve_viewpoint(registry, chosen), all_layers, registry, narrow),
        )
        return out + ((depth,) if with_depth else ())

    @app.callback(
        Output(eid["summary"], "children", allow_duplicate=True),
        Output(eid["focus"], "data", allow_duplicate=True),
        Output(eid["focus"], "value", allow_duplicate=True),
        Output(eid["layers"], "data", allow_duplicate=True),
        Output(eid["layers"], "value", allow_duplicate=True),
        Input(eid["viewpoint"], "value"),
        Input(eid["layers"], "value"),
        *depth_in,
        State(eid["focus"], "value"),
        State(eid["modal"], "opened"),
        *states,
        prevent_initial_call=True,
    )
    def refresh(viewpoint_id, layers, *raw):
        """The summary follows every choice; a new depth regrows the view, so the focus and
        the layers on offer follow it too, and the layers go back to all of them."""
        quiet = (no_update,) * 5
        values = list(raw)
        depth = _depth(values.pop(0)) if with_depth else None
        focus = list(values.pop(0) or [])
        opened = values.pop(0)
        if not opened:
            return quiet
        ctx = get_context()
        view = build_view(ctx, depth, *values)
        if view is None:
            return quiet
        registry = registry_of(ctx, values)
        vp = resolve_viewpoint(registry, viewpoint_id)
        regrown = with_depth and eid["depth"] in dash_ctx.triggered_prop_ids.values()
        if not regrown:
            return summary_text(view, vp, list(layers or []), registry, narrow), *quiet[1:]
        options = layer_options(view)
        all_layers = [o["value"] for o in options]
        present = {n.id for n in view.nodes}
        return (
            summary_text(view, vp, all_layers, registry, narrow),
            focus_options(view),
            [i for i in focus if i in present],
            options,
            all_layers,
        )

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Output(eid["modal"], "opened", allow_duplicate=True),
        Input(eid["go"], "n_clicks"),
        State(eid["viewpoint"], "value"),
        State(eid["focus"], "value"),
        State(eid["layers"], "value"),
        State(eid["arranged"], "checked"),
        *depth_state,
        *positions,
        *states,
        prevent_initial_call=True,
    )
    def download(n, viewpoint_id, focus, layers, arranged, *raw):
        if not n:
            return no_update, no_update
        values = list(raw)
        depth = _depth(values.pop(0)) if with_depth else None
        placed = _first_positions(values.pop(0)) if positions else None
        ctx = get_context()
        view = build_view(ctx, depth, *values)
        if view is None:
            return no_update, no_update
        registry = registry_of(ctx, values)
        vp = resolve_viewpoint(registry, viewpoint_id)
        drawn = export_view(view, vp, list(layers or []), list(focus or []), registry, narrow)
        text = to_drawio(
            drawn,
            ctx.base_url() if linked else "",
            placed if arranged else None,
            marked=marked,
            viewpoint=vp,
        )
        return dcc.send_string(text, f"{file_stem(ctx, *values)}.drawio"), False
