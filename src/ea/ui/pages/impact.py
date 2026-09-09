"""Impact: blast radius of an element with a completeness footer."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.models import NotFoundError
from ea.ui import graph as gp
from ea.ui import ids
from ea.ui.components import (
    alert,
    element_anchor,
    icon,
    keep_selected_option,
    mermaid_block,
    page_title,
    simple_table,
    type_badge,
    view_toolbar,
)
from ea.ui.context import AppContext, get_context
from ea.views import view_from_impact
from ea.views.drawio import to_drawio
from ea.views.mermaid import to_markdown, to_mermaid


def _option(ctx: AppContext, e) -> dict[str, str]:
    t = ctx.registry.types.get(e.type_id)
    return {"value": e.element_id, "label": f"{e.name} [{e.element_id}] \u00b7 {t.name if t else e.type_id}"}


NOTHING_TO_EXPORT = "Choose an element and press Run: there is no view to export yet."
NOTHING_CHOSEN = "Choose an element above, then press Run."
GRAPH_HOPS = 2  # the picture stays readable at two hops however far the tables answer


def render(ctx: AppContext, search: str | None = None) -> html.Div:
    preset = (parse_qs((search or "").lstrip("?")).get("element") or [None])[0]
    data = [_option(ctx, e) for e in ctx.repo.search(limit=50)]
    result, elements, mermaid = None, gp.EMPTY, ""
    if preset:
        e = ctx.backend.get_element(preset)
        if e:
            if not any(o["value"] == preset for o in data):
                data = [_option(ctx, e), *data]
            result, elements, mermaid = _result(ctx, preset, 3)
        else:
            # An address naming an element that is not here is refused rather than answered
            # with an empty page, and the selector is left empty because there is nothing
            # to select.
            result = _unknown(preset)
            preset = None
    nothing_yet = "" if mermaid else NOTHING_TO_EXPORT
    return html.Div(
        [
            page_title(
                "Impact",
                "What depends on an element (upstream, following relationships into it) and what it depends on (downstream), to a chosen depth.",
            ),
            dmc.Group(
                [
                    dmc.Select(
                        id=ids.IMP_ELEMENT,
                        **{"aria-label": "The element to trace"},
                        placeholder="Search an element…",
                        searchable=True,
                        data=data,
                        value=preset,
                        w=460,
                        nothingFoundMessage="Type to search",
                    ),
                    dmc.NumberInput(
                        id=ids.IMP_DEPTH,
                        **{"aria-label": "How many hops to follow"},
                        label=None,
                        value=3,
                        min=1,
                        max=6,
                        w=90,
                    ),
                    dmc.Button("Run", id=ids.IMP_RUN, leftSection=icon("tabler:radar")),
                ],
                align="flex-end",
                gap="sm",
                mb="md",
            ),
            html.Div(result, id=ids.IMP_RESULT),
            dmc.Paper(
                [
                    dmc.Text(
                        _graph_note(3) if elements is not gp.EMPTY else "",
                        id=ids.IMP_GRAPH_NOTE,
                        size="xs",
                        c="dimmed",
                    ),
                    gp.graph_panel("imp", ctx.registry, elements, height="70vh", group_by="layer"),
                ],
                p="sm",
                withBorder=True,
                mt="md",
            ),
            dmc.Paper(
                [
                    dmc.Title("Architecture view", order=2, size="h5", mb="xs"),
                    dmc.Text(
                        "The impact as an architecture diagram, generated from the model: layers top to bottom, every shape an element.",
                        size="sm",
                        c="dimmed",
                        mb="xs",
                    ),
                    mermaid_block("imp-view", mermaid),
                    view_toolbar(
                        ids.IMP_VIEW_MD,
                        ids.IMP_VIEW_DRAWIO,
                        md_reason=nothing_yet,
                        drawio_reason=nothing_yet,
                        note=nothing_yet,
                        note_id=ids.IMP_VIEW_NOTE,
                    ),
                ],
                p="md",
                withBorder=True,
                mt="md",
            ),
        ]
    )


def _rows(ctx: AppContext, rows):
    return [
        [
            r["depth"],
            element_anchor(r),
            type_badge(ctx.registry, r["type_id"], "xs"),
            " › ".join(r["rel_labels"]),
        ]
        for r in rows
    ]


def _unknown(element_id: str) -> dmc.Alert:
    """A refusal that names what was refused and offers somewhere to go.

    'Unknown element.' on its own says neither which identifier the address carried nor what
    to do about it; the element page's own Not found screen does both.
    """
    return dmc.Alert(
        dmc.Group(
            [
                dmc.Text(
                    f"Unknown element. Nothing in the model carries the id '{element_id}'; "
                    "it may have been renamed, merged or never imported.",
                    size="sm",
                ),
                dmc.Anchor("Search the model", href="/browse", size="sm", fw=600),
            ],
            gap="sm",
        ),
        color="red",
        variant="light",
        withCloseButton=False,
    )


def _result(ctx: AppContext, element_id: str, depth: int):
    """(summary and tables, cytoscape elements, mermaid code) for one impact run."""
    try:
        res = ctx.graph.impact(element_id, depth)
    except NotFoundError:
        return _unknown(element_id), gp.EMPTY, ""
    e, c = res["element"], res["completeness"]
    summary = dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(
                    [
                        dmc.Title(e["name"], order=2, size="h3"),
                        type_badge(ctx.registry, e["type_id"]),
                        dmc.Anchor("open", href=f"/element/{e['element_id']}", size="sm"),
                    ],
                    gap="sm",
                ),
                dmc.Text(
                    f"{len(res['upstream'])} elements depend on it within {depth} hops; it depends on {len(res['downstream'])}. By type: "
                    + ", ".join(f"{k} {v}" for k, v in res["by_type"].items()),
                    size="sm",
                ),
                dmc.Alert(
                    f"Completeness: {c['populated']} of {c['declared']} relationship types declared for {e['type_name']} have any instances in the repository."
                    + (
                        f" No instances yet for: {'; '.join(c['empty'])}."
                        if c["empty"]
                        else " Every declared relationship type has content."
                    ),
                    color="yellow" if c["empty"] else "green",
                    variant="light",
                    title="How complete is this answer?",
                ),
            ]
        ),
        p="md",
        withBorder=True,
        mb="md",
    )
    tables = dmc.SimpleGrid(
        [
            dmc.Paper(
                [
                    dmc.Title("Depends on this (upstream)", order=2, size="h5", mb="xs"),
                    simple_table(["hops", "element", "type", "via"], _rows(ctx, res["upstream"]))
                    if res["upstream"]
                    else dmc.Text("Nothing.", c="dimmed", size="sm"),
                ],
                p="md",
                withBorder=True,
            ),
            dmc.Paper(
                [
                    dmc.Title("This depends on (downstream)", order=2, size="h5", mb="xs"),
                    simple_table(["hops", "element", "type", "via"], _rows(ctx, res["downstream"]))
                    if res["downstream"]
                    else dmc.Text("Nothing.", c="dimmed", size="sm"),
                ],
                p="md",
                withBorder=True,
            ),
        ],
        cols={"base": 1, "lg": 2},
        spacing="md",
    )
    elements = gp.raw_from_subgraph(
        ctx.registry, ctx.graph.neighbours(element_id, min(int(depth or 3), GRAPH_HOPS))
    )
    return (
        html.Div([summary, tables]),
        elements,
        to_mermaid(view_from_impact(ctx.registry, ctx.graph, res)),
    )


def _graph_note(depth: int) -> str:
    """What the picture shows against what the tables answered.

    The graph is drawn from two hops however far the answer reaches, so it stays readable;
    unsaid, a work package the table names three hops out looks missing from the picture.
    """
    return (
        f"The picture shows the two hops nearest the element; the tables above answer to {depth}."
        if int(depth or 3) > GRAPH_HOPS
        else ""
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.IMP_ELEMENT, "data"),
        Output(ids.IMP_ELEMENT, "nothingFoundMessage"),
        Input(ids.IMP_ELEMENT, "searchValue"),
        State(ids.IMP_ELEMENT, "value"),
        State(ids.IMP_ELEMENT, "data"),
        prevent_initial_call=True,
    )
    def search(text, value, data):
        if not text or len(text) < 2:
            return no_update, "Type at least two letters to search"
        ctx = get_context()
        options = [_option(ctx, e) for e in ctx.repo.search(text, limit=25)]
        # Picking an option makes the label the next search term, which matches nothing:
        # keep the list as it is rather than dropping the option the value refers to.
        if not options:
            # 'Type to search' is the right instruction before anything is typed and reads,
            # afterwards, as though the search had never run.
            return no_update, f"No element matches '{text}'."
        return keep_selected_option(options, value, data), "Type to search"

    @app.callback(
        Output(ids.IMP_RESULT, "children"),
        Output(ids.IMP_VIEW_MD, "disabled"),
        Output(ids.IMP_VIEW_DRAWIO, "disabled"),
        Output(ids.IMP_VIEW_NOTE, "children"),
        Output(gp.store_id("imp"), "data"),
        Output({"type": ids.MERMAID_SRC, "id": "imp-view"}, "children"),
        Output(ids.IMP_GRAPH_NOTE, "children"),
        Input(ids.IMP_RUN, "n_clicks"),
        Input(ids.IMP_ELEMENT, "value"),
        State(ids.IMP_DEPTH, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.IMP_RUN, "loading"), True, False)],
    )
    def run(n, element_id, depth):
        if not element_id:
            # A button that reports as loading and then leaves the page exactly as it was
            # reads as broken; say what is missing instead.
            if dash.ctx.triggered_id == ids.IMP_RUN:
                blocked = dmc.Text(NOTHING_TO_EXPORT, size="xs", c="dimmed")
                return alert(NOTHING_CHOSEN, "yellow"), True, True, blocked, gp.EMPTY, "", ""
            return (no_update,) * 7
        result, nodes, mermaid = _result(get_context(), element_id, int(depth or 3))
        blocked = "" if mermaid else NOTHING_TO_EXPORT
        note = dmc.Text(blocked, size="xs", c="dimmed") if blocked else None
        return result, bool(blocked), bool(blocked), note, nodes, mermaid, _graph_note(int(depth or 3))

    @app.callback(
        Output(ids.IMP_DEPTH, "value"),
        Input(ids.IMP_DEPTH, "value"),
        prevent_initial_call=True,
    )
    def keep_a_depth(depth):
        """An emptied box would answer at three while showing nothing: put the three back."""
        return no_update if depth not in (None, "") else 3

    @app.callback(
        Output(ids.URL, "pathname", allow_duplicate=True),
        Output(ids.URL, "search", allow_duplicate=True),
        Input(gp.cy_id("imp"), "tapNodeData"),
        prevent_initial_call=True,
    )
    def tap_node(data):
        if not data or not gp.is_element_node(data):
            return no_update, no_update
        return f"/element/{gp.element_id_of(data)}", ""

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.IMP_VIEW_MD, "n_clicks"),
        Input(ids.IMP_VIEW_DRAWIO, "n_clicks"),
        State(ids.IMP_ELEMENT, "value"),
        State(ids.IMP_DEPTH, "value"),
        State({"type": ids.MERMAID_POS, "id": "imp-view"}, "data"),
        prevent_initial_call=True,
    )
    def download_view(n_md, n_drawio, element_id, depth, positions):
        if not element_id or not (n_md or n_drawio):
            return no_update
        ctx = get_context()
        try:
            view = view_from_impact(ctx.registry, ctx.graph, ctx.graph.impact(element_id, int(depth or 3)))
        except NotFoundError:
            return no_update
        if dash.ctx.triggered_id == ids.IMP_VIEW_DRAWIO:
            return dcc.send_string(
                to_drawio(view, ctx.base_url(), positions or None), f"{element_id}-impact.drawio"
            )
        return dcc.send_string(to_markdown(view), f"{element_id}-impact.md")
