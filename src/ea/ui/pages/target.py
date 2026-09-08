"""Target state: current versus intended state of every artefact, per work package, with a marked view."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.models import CURRENT_STATES, TARGET_STATES
from ea.services.target import CURRENT_STYLE, TARGET_STYLE, state_label
from ea.ui import ids
from ea.ui.components import (
    element_anchor,
    icon,
    mermaid_block,
    page_title,
    simple_table,
    type_badge,
    view_toolbar,
)
from ea.ui.context import AppContext, get_context
from ea.views import view_from_ids
from ea.views.drawio import to_drawio
from ea.views.mermaid import state_legend, to_markdown, to_mermaid


def current_badge(state: str, size: str = "sm") -> dmc.Badge:
    return dmc.Badge(
        state_label(state, CURRENT_STYLE),
        color=CURRENT_STYLE.get(state, {}).get("colour", "gray"),
        variant="outline",
        size=size,
    )


def target_badge(state: str, size: str = "sm") -> dmc.Badge:
    st = TARGET_STYLE.get(state, TARGET_STYLE["undecided"])
    return dmc.Badge(
        f"{st['glyph']} {st['label']}",
        color=st["colour"],
        variant="light" if state in ("undecided", "keep") else "filled",
        size=size,
    )


def _view(ctx: AppContext, work_package: str | None):
    title = "Target state of the model"
    if work_package:
        wp = ctx.backend.get_element(work_package)
        title = f"Target state of {wp.name if wp else work_package}"
    return view_from_ids(
        ctx.registry,
        ctx.graph,
        ctx.target.scope_ids(work_package),
        title,
        [work_package] if work_package else [],
    )


def _matrix(summary: dict) -> dmc.Table:
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh("current ↓ / target →")]
            + [dmc.TableTh(target_badge(t, "xs")) for t in TARGET_STATES]
        )
    )
    body = []
    for c in CURRENT_STATES:
        row = summary["matrix"][c]
        if not any(row.values()):
            continue
        body.append(
            dmc.TableTr(
                [dmc.TableTd(current_badge(c, "xs"))]
                + [
                    dmc.TableTd(
                        dmc.Text(str(row[t]), size="sm", fw=600)
                        if row[t]
                        else dmc.Text("·", size="sm", c="dimmed")
                    )
                    for t in TARGET_STATES
                ]
            )
        )
    return dmc.TableScrollContainer(
        dmc.Table(
            [head, dmc.TableTbody(body)],
            withTableBorder=True,
            verticalSpacing="xs",
            fz="sm",
            className="ea-state-matrix",
        ),
        minWidth=560,
    )


def _body(ctx: AppContext, work_package: str | None, only_changes: bool):
    summary = ctx.target.summary(work_package)
    els = ctx.target.elements(work_package, only_changes)
    rels = ctx.target.relationships(work_package, only_changes)
    view = _view(ctx, work_package)
    counts = dmc.Group(
        [
            dmc.Badge(
                f"{v} {state_label(k, TARGET_STYLE).lower()}",
                color=TARGET_STYLE[k]["colour"],
                variant="light",
                size="lg",
            )
            for k, v in summary["by_target"].items()
            if v
        ]
        + [
            dmc.Text(
                f"{summary['elements']} elements · {summary['relationships']} relationships · {summary['changes']} elements change",
                size="sm",
                c="dimmed",
            )
        ],
        gap="xs",
        mb="md",
    )
    el_rows = [
        [
            element_anchor(e),
            type_badge(ctx.registry, e.type_id, "xs"),
            current_badge(e.current_state, "xs"),
            target_badge(e.target_state, "xs"),
            dmc.Anchor(e.target_work_package, href=f"/target?wp={e.target_work_package}", size="xs")
            if e.target_work_package and not work_package
            else "",
            dmc.Text(e.target_note, size="xs"),
        ]
        for e in els
    ]
    rel_rows = []
    for r in rels:
        src, dst = ctx.backend.get_element(r.src_id), ctx.backend.get_element(r.dst_id)
        rt = ctx.registry.rel_types.get(r.rel_type_id)
        rel_rows.append(
            [
                element_anchor(src) if src else r.src_id,
                dmc.Text(
                    (rt.name if rt else r.rel_type_id) + (f" ({r.qualifier})" if r.qualifier else ""),
                    size="sm",
                ),
                element_anchor(dst) if dst else r.dst_id,
                current_badge(r.current_state, "xs"),
                target_badge(r.target_state, "xs"),
                dmc.Text(r.target_note, size="xs"),
            ]
        )
    legend = state_legend(view)
    return html.Div(
        [
            counts,
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        [
                            dmc.Text("Current state by target state", className="ea-section-title"),
                            dmc.Text(
                                "How many elements sit in each cell: what is true today against what is intended.",
                                size="xs",
                                c="dimmed",
                                mb="xs",
                            ),
                            _matrix(summary),
                        ],
                        p="md",
                        withBorder=True,
                        className="ea-card",
                    ),
                    dmc.Paper(
                        [
                            dmc.Text("Architecture view, marked", className="ea-section-title"),
                            dmc.Text(
                                legend or "Nothing changes in this scope.", size="xs", c="dimmed", mb="xs"
                            ),
                            mermaid_block("tg-view", to_mermaid(view, marked=True)),
                            view_toolbar(
                                ids.TG_VIEW_MD,
                                ids.TG_VIEW_DRAWIO,
                                "New shapes are dashed green, changed amber, decommissioned red and struck through in draw.io.",
                            ),
                        ],
                        p="md",
                        withBorder=True,
                        className="ea-card",
                    ),
                ],
                cols={"base": 1, "lg": 2},
                spacing="md",
                mb="md",
            ),
            dmc.Paper(
                [
                    dmc.Text(f"Elements ({len(el_rows)})", className="ea-section-title"),
                    simple_table(["element", "type", "current", "target", "work package", "note"], el_rows)
                    if el_rows
                    else dmc.Text("No elements in this scope.", c="dimmed", size="sm"),
                    dmc.Text(f"Relationships ({len(rel_rows)})", className="ea-section-title", mt="md"),
                    simple_table(["from", "relationship", "to", "current", "target", "note"], rel_rows)
                    if rel_rows
                    else dmc.Text(
                        "No relationships carry a target state in this scope.", c="dimmed", size="sm"
                    ),
                ],
                p="md",
                withBorder=True,
                className="ea-card",
            ),
        ]
    )


def render(ctx: AppContext, search: str | None = None) -> html.Div:
    preset = (parse_qs((search or "").lstrip("?")).get("wp") or [""])[0]
    wps = ctx.work_package_options()
    if preset and preset not in {w["value"] for w in wps}:
        preset = ""
    return html.Div(
        [
            page_title(
                "Target state",
                "What is true of each artefact today (current state) against what the organisation intends for it (target state), analysed per work package. Edit the states on an element's page.",
                dmc.Anchor(
                    dmc.Button("Branches", variant="subtle", leftSection=icon("tabler:git-branch")),
                    href="/branches",
                    underline="never",
                ),
            ),
            dmc.Group(
                [
                    dmc.Select(
                        id=ids.TG_WP,
                        **{"aria-label": "Work package"},
                        data=[{"value": "", "label": "All work packages"}] + wps,
                        value=preset,
                        w=420,
                        searchable=True,
                        allowDeselect=False,
                        leftSection=icon("tabler:target-arrow", 14),
                    ),
                    dmc.Switch(
                        id=ids.TG_ONLY_CHANGES, label="Only what changes", checked=not preset, size="sm"
                    ),
                ],
                gap="md",
                align="center",
                mb="md",
            ),
            html.Div(_body(ctx, preset or None, not preset), id=ids.TG_BODY),
        ]
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.TG_BODY, "children"),
        Output(ids.TG_ONLY_CHANGES, "checked"),
        Input(ids.TG_WP, "value"),
        Input(ids.TG_ONLY_CHANGES, "checked"),
        prevent_initial_call=True,
    )
    def refresh(wp, only_changes):
        ctx = get_context()
        if dash_ctx.triggered_id == ids.TG_WP:
            only_changes = not wp  # a work package shows everything it touches; "all" shows what changes
            return _body(ctx, wp or None, only_changes), only_changes
        return _body(ctx, wp or None, bool(only_changes)), no_update

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.TG_VIEW_MD, "n_clicks"),
        Input(ids.TG_VIEW_DRAWIO, "n_clicks"),
        State(ids.TG_WP, "value"),
        State({"type": ids.MERMAID_POS, "id": "tg-view"}, "data"),
        prevent_initial_call=True,
    )
    def download(n_md, n_drawio, wp, positions):
        if not (n_md or n_drawio):
            return no_update
        ctx = get_context()
        view = _view(ctx, wp or None)
        name = f"target-state-{wp or 'all'}"
        if dash_ctx.triggered_id == ids.TG_VIEW_DRAWIO:
            return dcc.send_string(
                to_drawio(view, ctx.base_url(), positions or None, marked=True), f"{name}.drawio"
            )
        return dcc.send_string(to_markdown(view, marked=True), f"{name}.md")
