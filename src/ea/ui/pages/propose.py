"""Propose: hand in a design (text, files, links); review the derived change set as an editable merge log; apply it to a branch."""

from __future__ import annotations

import base64
from typing import Any

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.agent.proposal import ProposalResult, fetch_link, result_from_payload
from ea.backend.branching import MAIN
from ea.config import ROOT
from ea.models import CURRENT_STATES, TARGET_STATES, ConflictError, Forbidden, NotFoundError, ValidationError
from ea.ui import ids
from ea.ui.components import alert, icon, markdown_editor, page_title
from ea.ui.context import AppContext, get_context

TEMPLATE_PATH = ROOT / "templates" / "proposal-template.md"
NEW_OPTION = "__new__"

_GRID = dict(
    className="ag-theme-alpine",
    defaultColDef={
        "sortable": False,
        "filter": False,
        "resizable": True,
        "editable": True,
        "wrapText": True,
        "autoHeight": True,
    },
    dashGridOptions={
        "rowSelection": "multiple",
        "suppressRowClickSelection": True,
        "singleClickEdit": True,
        "stopEditingWhenCellsLoseFocus": True,
        "animateRows": False,
        "domLayout": "autoHeight",
    },
    style={"width": "100%"},
)
_TICK = {
    "field": "include",
    "headerName": "",
    "checkboxSelection": True,
    "headerCheckboxSelection": True,
    "width": 46,
    "pinned": "left",
    "editable": False,
    "resizable": False,
    "valueFormatter": {"function": "''"},
}


def _type_names(ctx: AppContext) -> list[str]:
    return [t.name for t in ctx.registry.active_types()]


def element_columns(ctx: AppContext) -> list[dict[str, Any]]:
    return [
        _TICK,
        {
            "field": "action",
            "width": 96,
            "editable": False,
            "cellClassRules": {"ea-added": "params.value == 'new'", "ea-link": "params.value == 'link'"},
        },
        {
            "field": "type",
            "width": 210,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": _type_names(ctx)},
        },
        {"field": "name", "flex": 1.4, "minWidth": 200},
        {"field": "existing_id", "headerName": "existing id", "width": 150},
        {
            "field": "description",
            "flex": 2,
            "minWidth": 240,
            "cellEditor": "agLargeTextCellEditor",
            "cellEditorPopup": True,
        },
        {
            "field": "current_state",
            "headerName": "current",
            "width": 130,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": list(CURRENT_STATES)},
        },
        {
            "field": "target_state",
            "headerName": "target",
            "width": 130,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": list(TARGET_STATES)},
        },
        {"field": "note", "flex": 1, "minWidth": 140},
        {
            "field": "issues",
            "flex": 1.5,
            "minWidth": 220,
            "editable": False,
            "cellClassRules": {"ea-conflict": "params.value"},
        },
    ]


REL_COLUMNS = [
    _TICK,
    {"field": "source", "flex": 1.2, "minWidth": 180},
    {"field": "relationship", "flex": 1, "minWidth": 150},
    {"field": "target", "flex": 1.2, "minWidth": 180},
    {"field": "qualifier", "width": 130},
    {"field": "note", "flex": 1, "minWidth": 140},
    {"field": "resolved", "flex": 1, "minWidth": 160, "editable": False},
    {
        "field": "issues",
        "flex": 1.5,
        "minWidth": 220,
        "editable": False,
        "cellClassRules": {"ea-conflict": "params.value"},
    },
]


def _el_rows(r: ProposalResult) -> list[dict[str, Any]]:
    return [
        {
            "key": f"e{i}",
            "include": e.include,
            "action": e.action,
            "type": e.type_label,
            "name": e.name,
            "existing_id": e.element_id or e.existing_id,
            "description": e.description,
            "current_state": e.current_state,
            "target_state": e.target_state,
            "note": e.note,
            "issues": "; ".join(e.issues),
        }
        for i, e in enumerate(r.elements)
    ]


def _rel_rows(r: ProposalResult) -> list[dict[str, Any]]:
    return [
        {
            "key": f"r{i}",
            "include": x.include,
            "source": x.source,
            "relationship": x.relationship,
            "target": x.target,
            "qualifier": x.qualifier,
            "note": x.note,
            "resolved": x.rel_type_id or "",
            "issues": "; ".join(x.issues),
        }
        for i, x in enumerate(r.relationships)
    ]


def _payload_from_rows(
    el_rows: list[dict[str, Any]],
    el_selected: list[dict[str, Any]],
    rel_rows: list[dict[str, Any]],
    rel_selected: list[dict[str, Any]],
    stored: dict[str, Any] | None,
    work_package: str,
) -> dict[str, Any]:
    """The grids (as edited and ticked) back into a proposal payload."""
    el_keys = {r["key"] for r in (el_selected or [])}
    rel_keys = {r["key"] for r in (rel_selected or [])}
    return {
        "title": (stored or {}).get("title", ""),
        "summary": (stored or {}).get("summary", ""),
        "work_package": work_package,
        "elements": [
            {
                "row": i + 1,
                "type": r.get("type") or "",
                "name": r.get("name") or "",
                "existing_id": r.get("existing_id") or "",
                "description": r.get("description") or "",
                "current_state": r.get("current_state") or "",
                "target_state": r.get("target_state") or "",
                "note": r.get("note") or "",
                "include": r.get("key") in el_keys,
            }
            for i, r in enumerate(el_rows or [])
            if (r.get("name") or r.get("type"))
        ],
        "relationships": [
            {
                "row": i + 1,
                "source": r.get("source") or "",
                "relationship": r.get("relationship") or "",
                "target": r.get("target") or "",
                "qualifier": r.get("qualifier") or "",
                "note": r.get("note") or "",
                "include": r.get("key") in rel_keys,
            }
            for i, r in enumerate(rel_rows or [])
            if (r.get("source") or r.get("target"))
        ],
    }


def _preview(ctx: AppContext, r: ProposalResult):
    """The change-set preview: pushback, then the two editable grids with include ticks."""
    el_rows, rel_rows = _el_rows(r), _rel_rows(r)
    n_new = sum(1 for e in r.elements if e.action == "new")
    n_link = sum(1 for e in r.elements if e.action == "link")
    who = r.provider + (f" · {r.model}" if r.model else "")
    wp_note = (
        f"Work package: {r.work_package} (existing)"
        if r.work_package_id
        else (
            f"Work package: {r.work_package} (will be created)"
            if r.work_package
            else "Work package: not named"
        )
    )
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Badge(f"{n_new} new", color="green", variant="light", size="lg"),
                    dmc.Badge(f"{n_link} linked", color="blue", variant="light", size="lg"),
                    dmc.Badge(
                        f"{len(r.relationships)} relationships", color="gray", variant="light", size="lg"
                    ),
                    dmc.Text(wp_note, size="sm", c="dimmed"),
                    dmc.Text(f"read by {who}", size="xs", c="dimmed") if r.provider else None,
                ],
                gap="sm",
                mb="sm",
            ),
            html.Div(
                alert(
                    html.Div(
                        [
                            dmc.Text(
                                "Not enough to apply. Add the following, then analyse again or correct the rows below:",
                                fw=600,
                                size="sm",
                            ),
                            html.Ul(
                                [html.Li(p, style={"fontSize": "0.85rem"}) for p in r.pushback],
                                style={"margin": "0.3rem 0 0", "paddingLeft": "1.2rem"},
                            ),
                        ]
                    ),
                    "yellow",
                )
                if r.pushback
                else alert(
                    "Every element and relationship is identified and described; apply it to a branch when the rows read right.",
                    "green",
                ),
                id=ids.PR_PUSHBACK,
            ),
            dmc.Title("Elements", order=2, className="ea-section-title"),
            dmc.Text(
                "new = will be created as proposed on the branch; link = an element that exists, updated only in its states. Edit any cell in place; untick a row to leave it out.",
                size="xs",
                c="dimmed",
                mb=4,
            ),
            dag.AgGrid(
                id=ids.PR_EL_GRID,
                columnDefs=element_columns(ctx),
                rowData=el_rows,
                getRowId="params.data.key",
                selectedRows=[x for x in el_rows if x["include"]],
                **_GRID,
            ),
            dmc.Button(
                "Add element row",
                id=ids.PR_ADD_EL,
                size="xs",
                variant="subtle",
                leftSection=icon("tabler:plus", 12),
                mt=4,
            ),
            dmc.Title("Relationships", order=2, className="ea-section-title", mt="md"),
            dmc.Text(
                "Refer to the elements by the names above or by repository id; the relationship is a name of the metamodel.",
                size="xs",
                c="dimmed",
                mb=4,
            ),
            dag.AgGrid(
                id=ids.PR_REL_GRID,
                columnDefs=REL_COLUMNS,
                rowData=rel_rows,
                getRowId="params.data.key",
                selectedRows=[x for x in rel_rows if x["include"]],
                **_GRID,
            ),
            dmc.Button(
                "Add relationship row",
                id=ids.PR_ADD_REL,
                size="xs",
                variant="subtle",
                leftSection=icon("tabler:plus", 12),
                mt=4,
            ),
            dmc.Divider(my="md"),
            dmc.Group(
                [
                    dmc.Button(
                        "Re-check rows",
                        id=ids.PR_ANALYSE + "-again",
                        variant="light",
                        leftSection=icon("tabler:checklist"),
                    ),
                    dmc.Button(
                        "Apply to branch",
                        id=ids.PR_APPLY,
                        leftSection=icon("tabler:git-branch"),
                        disabled=not ctx.can("propose"),
                    ),
                ],
                gap="sm",
            ),
            html.Div(id=ids.PR_APPLY_FEEDBACK, style={"marginTop": "0.5rem"}),
        ]
    )


def render(ctx: AppContext) -> html.Div:
    provider = ctx.proposals.provider
    badge = dmc.Badge(
        f"reader: {provider.name}" + (f" · {provider.model}" if getattr(provider, "model", "") else ""),
        variant="light",
        color="indigo" if provider.name == "anthropic" else "gray",
        id=ids.PR_PROVIDER,
    )
    wps = ctx.work_package_options()
    open_branches = [{"value": b.branch_id, "label": f"{b.name} ({b.changes})"} for b in ctx.branches.open()]
    branch_options = open_branches + [{"value": NEW_OPTION, "label": "➕ New branch…"}]
    wp_options = wps + [{"value": NEW_OPTION, "label": "➕ New work package…"}]
    return html.Div(
        [
            page_title(
                "Propose a change",
                "Hand in a design page, a document or links. The reader identifies the elements it names, links the ones that exist, adopts the new ones as proposed, and pushes back on what is missing. You review every row, add what it missed, and apply the result to a branch.",
                badge,
            ),
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dmc.Text("1 · Where it lands", fw=700, size="sm"),
                                dmc.Select(
                                    id=ids.PR_BRANCH,
                                    label="Branch",
                                    description="An open branch to write to; New creates one from main, named after the proposal when no name is given.",
                                    data=branch_options,
                                    value=ctx.branch() if ctx.branch() != MAIN else None,
                                    searchable=True,
                                    clearable=True,
                                    placeholder="New branch (created from main)",
                                    comboboxProps={"withinPortal": True},
                                ),
                                dmc.TextInput(
                                    id=ids.PR_BRANCH_NEW,
                                    label="New branch name",
                                    placeholder="Named after the proposal when left empty",
                                    style={"display": "none"},
                                ),
                                dmc.Select(
                                    id=ids.PR_WP,
                                    label="Work package",
                                    description="The initiative the change belongs to; the document's own says wins when it names one.",
                                    data=wp_options,
                                    searchable=True,
                                    clearable=True,
                                    placeholder="Existing work package…",
                                    comboboxProps={"withinPortal": True},
                                ),
                                dmc.TextInput(
                                    id=ids.PR_WP_NEW,
                                    label="New work package name",
                                    placeholder="Name of a new initiative",
                                    style={"display": "none"},
                                ),
                                dmc.Divider(),
                                dmc.Button(
                                    "Download Proposal Template",
                                    id=ids.PR_TEMPLATE,
                                    variant="light",
                                    leftSection=icon("tabler:download"),
                                ),
                                dmc.Text(
                                    "Start from the template: its tables work without a model key.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                            gap="sm",
                        ),
                        p="md",
                        withBorder=True,
                        className="ea-card",
                    ),
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dmc.Text("2 · The proposal", fw=700, size="sm"),
                                markdown_editor(
                                    ids.PR_TEXT,
                                    "Paste the proposal",
                                    placeholder="Paste the design page here (Markdown with the template's tables works without a model key; free text needs the hosted reader)…",
                                    min_rows=8,
                                ),
                                dcc.Upload(
                                    id=ids.PR_UPLOAD,
                                    multiple=True,
                                    children=dmc.Group(
                                        [
                                            icon("tabler:cloud-upload", 20),
                                            dmc.Text(
                                                "Drop Markdown, text or CSV files here, or click to choose",
                                                size="sm",
                                            ),
                                        ],
                                        gap="sm",
                                        justify="center",
                                        py="sm",
                                    ),
                                    style={
                                        "border": "1px dashed #adb5bd",
                                        "borderRadius": 8,
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Div(id=ids.PR_FILES),
                                dcc.Store(id=ids.PR_STORE, data={}),
                                dmc.Textarea(
                                    id=ids.PR_LINKS,
                                    label="Links (one per line)",
                                    placeholder="https://…",
                                    autosize=True,
                                    minRows=1,
                                ),
                                dmc.Group(
                                    [
                                        dmc.Text(
                                            "No document yet? Analyse with nothing pasted and add the rows by hand.",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                        dmc.Button(
                                            "Analyse", id=ids.PR_ANALYSE, leftSection=icon("tabler:send")
                                        ),
                                    ],
                                    justify="space-between",
                                    align="center",
                                ),
                            ],
                            gap="sm",
                        ),
                        p="md",
                        withBorder=True,
                        className="ea-card",
                    ),
                ],
                cols={"base": 1, "md": 2},
                spacing="md",
                mb="md",
            ),
            dcc.Store(id=ids.PR_RESULT_STORE, data=None),
            html.Div(id=ids.PR_RESULT),
        ]
    )


def _sources(text: str, files: dict[str, str], links_text: str) -> tuple[list[dict[str, str]], list[str]]:
    sources: list[dict[str, str]] = []
    problems: list[str] = []
    if (text or "").strip():
        sources.append({"kind": "text", "name": "pasted text", "text": text})
    for name, content in (files or {}).items():
        sources.append({"kind": "file", "name": name, "text": content})
    for url in (links_text or "").splitlines():
        url = url.strip()
        if not url:
            continue
        try:
            sources.append({"kind": "link", "name": url, "text": fetch_link(url)})
        except Exception as exc:  # noqa: BLE001 — the reason goes to the architect
            problems.append(f"{url}: {exc}")
    return sources, problems


def _wp_choice(wp: str | None, wp_new: str | None) -> str:
    if wp == NEW_OPTION:
        return (wp_new or "").strip()
    return wp or ""


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.PR_BRANCH_NEW, "style"),
        Input(ids.PR_BRANCH, "value"),
        prevent_initial_call=True,
    )
    def show_new_branch_name(branch):
        return {} if branch == NEW_OPTION else {"display": "none"}

    @app.callback(
        Output(ids.PR_WP_NEW, "style"),
        Input(ids.PR_WP, "value"),
        prevent_initial_call=True,
    )
    def show_new_wp_name(wp):
        return {} if wp == NEW_OPTION else {"display": "none"}

    @app.callback(
        Output(ids.PR_STORE, "data"),
        Output(ids.PR_FILES, "children"),
        Input(ids.PR_UPLOAD, "contents"),
        State(ids.PR_UPLOAD, "filename"),
        State(ids.PR_STORE, "data"),
        prevent_initial_call=True,
    )
    def upload(contents, names, store):
        if not contents:
            return no_update, no_update
        store = dict(store or {})
        for content, name in zip(contents, names, strict=True):
            _, b64 = content.split(",", 1)
            store[name] = base64.b64decode(b64).decode("utf-8-sig", errors="replace")[:400_000]
        rows = [
            dmc.Group(
                [
                    icon("tabler:file-text"),
                    dmc.Text(n, size="sm"),
                    dmc.Text(f"{len(t)} chars", size="xs", c="dimmed"),
                ],
                gap="xs",
            )
            for n, t in store.items()
        ]
        return store, dmc.Stack(rows, gap=4)

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.PR_TEMPLATE, "n_clicks"),
        prevent_initial_call=True,
    )
    def template(n):
        if not n:
            return no_update
        return dcc.send_string(TEMPLATE_PATH.read_text(encoding="utf-8"), "proposal-template.md")

    @app.callback(
        Output(ids.PR_RESULT, "children"),
        Output(ids.PR_RESULT_STORE, "data"),
        Input(ids.PR_ANALYSE, "n_clicks"),
        State({"type": ids.MD_TEXT, "id": ids.PR_TEXT}, "value"),
        State(ids.PR_STORE, "data"),
        State(ids.PR_LINKS, "value"),
        State(ids.PR_WP, "value"),
        State(ids.PR_WP_NEW, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.PR_ANALYSE, "loading"), True, False)],
    )
    def analyse(n, text, files, links, wp, wp_new):
        if not n:
            return no_update, no_update
        ctx = get_context()
        sources, problems = _sources(text, files, links)
        if sources:
            result = ctx.proposals.analyse(sources)
        else:
            result = ctx.proposals.resolve(ProposalResult(provider="manual"))
        if not result.work_package:
            result.work_package = _wp_choice(wp, wp_new)
            result = ctx.proposals.resolve(result)
        head = alert("Some links could not be read: " + "; ".join(problems), "red") if problems else None
        stored = {"title": result.title, "summary": result.summary, "work_package": result.work_package}
        return html.Div([head, _preview(ctx, result)]), stored

    @app.callback(
        Output(ids.PR_EL_GRID, "rowData"),
        Output(ids.PR_EL_GRID, "selectedRows"),
        Input(ids.PR_ADD_EL, "n_clicks"),
        State(ids.PR_EL_GRID, "virtualRowData"),
        State(ids.PR_EL_GRID, "rowData"),
        State(ids.PR_EL_GRID, "selectedRows"),
        prevent_initial_call=True,
    )
    def add_element_row(n, virtual_rows, rows, selected):
        if not n:
            return no_update, no_update
        current = list(virtual_rows or rows or [])
        key = f"m{n}-{len(current)}"
        current.append(
            {
                "key": key,
                "include": True,
                "action": "new",
                "type": "",
                "name": "",
                "existing_id": "",
                "description": "",
                "current_state": "proposed",
                "target_state": "new",
                "note": "",
                "issues": "",
            }
        )
        return current, list(selected or []) + [current[-1]]

    @app.callback(
        Output(ids.PR_REL_GRID, "rowData"),
        Output(ids.PR_REL_GRID, "selectedRows"),
        Input(ids.PR_ADD_REL, "n_clicks"),
        State(ids.PR_REL_GRID, "virtualRowData"),
        State(ids.PR_REL_GRID, "rowData"),
        State(ids.PR_REL_GRID, "selectedRows"),
        prevent_initial_call=True,
    )
    def add_relationship_row(n, virtual_rows, rows, selected):
        if not n:
            return no_update, no_update
        current = list(virtual_rows or rows or [])
        key = f"m{n}-{len(current)}"
        current.append(
            {
                "key": key,
                "include": True,
                "source": "",
                "relationship": "",
                "target": "",
                "qualifier": "",
                "note": "",
                "resolved": "",
                "issues": "",
            }
        )
        return current, list(selected or []) + [current[-1]]

    @app.callback(
        Output(ids.PR_RESULT, "children", allow_duplicate=True),
        Output(ids.PR_APPLY_FEEDBACK, "children"),
        Output(ids.BRANCH_SELECT, "data", allow_duplicate=True),
        Input(ids.PR_ANALYSE + "-again", "n_clicks"),
        Input(ids.PR_APPLY, "n_clicks"),
        State(ids.PR_EL_GRID, "virtualRowData"),
        State(ids.PR_EL_GRID, "rowData"),
        State(ids.PR_EL_GRID, "selectedRows"),
        State(ids.PR_REL_GRID, "virtualRowData"),
        State(ids.PR_REL_GRID, "rowData"),
        State(ids.PR_REL_GRID, "selectedRows"),
        State(ids.PR_RESULT_STORE, "data"),
        State(ids.PR_BRANCH, "value"),
        State(ids.PR_BRANCH_NEW, "value"),
        State(ids.PR_WP, "value"),
        State(ids.PR_WP_NEW, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.PR_APPLY, "loading"), True, False)],
    )
    def recheck_or_apply(
        n_check,
        n_apply,
        el_v,
        el_rows,
        el_sel,
        rel_v,
        rel_rows,
        rel_sel,
        stored,
        branch,
        branch_new,
        wp,
        wp_new,
    ):
        trig = dash_ctx.triggered_id
        ctx = get_context()
        work_package = (stored or {}).get("work_package") or _wp_choice(wp, wp_new)
        payload = _payload_from_rows(
            el_v or el_rows, el_sel, rel_v or rel_rows, rel_sel, stored, work_package
        )
        result = ctx.proposals.resolve(result_from_payload(payload, "manual"))
        if trig == ids.PR_ANALYSE + "-again":
            if not n_check:
                return no_update, no_update, no_update
            return _preview(ctx, result), no_update, no_update
        if not n_apply:
            return no_update, no_update, no_update
        if result.pushback:
            return (
                _preview(ctx, result),
                alert("Not applied: see what is missing above.", "yellow"),
                no_update,
            )
        new_name = (branch_new or "").strip()
        try:
            if branch == NEW_OPTION or (not branch and new_name):
                title = new_name or result.title or f"proposal {len(ctx.branches.list()) + 1}"
                b = ctx.branches.create(
                    title, ctx.actor, f"Proposal: {result.title or title}", result.work_package_id or ""
                )
            elif branch:
                b = ctx.branches.get(branch)
            else:
                title = result.title or f"proposal {len(ctx.branches.list()) + 1}"
                b = ctx.branches.create(title, ctx.actor, f"Proposal: {title}", result.work_package_id or "")
            out = ctx.proposals.apply(result, b.branch_id, ctx.actor)
        except (ValidationError, ConflictError, NotFoundError, ValueError, Forbidden) as exc:
            msg = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
            return no_update, alert(f"Not applied: {msg}", "red"), no_update
        ctx.graph.invalidate()
        summary = html.Div(
            [
                dmc.Text(
                    f"Applied to branch {b.name}: {len(out['created'])} element(s) created as proposed, {len(out['linked'])} linked, "
                    f"{len(out['relationships'])} relationship(s) written"
                    + (f", {len(out['skipped'])} row(s) skipped" if out["skipped"] else "")
                    + ".",
                    size="sm",
                    fw=500,
                ),
                dmc.Group(
                    [
                        dmc.Anchor(
                            "Review and merge on the Branches page",
                            href=f"/branches?branch={b.branch_id}",
                            size="sm",
                        ),
                        dmc.Anchor(
                            "Target state of the work package",
                            href=f"/target?wp={out['work_package_id']}",
                            size="sm",
                        )
                        if out.get("work_package_id")
                        else None,
                    ],
                    gap="md",
                ),
                dmc.Text("Skipped: " + "; ".join(out["skipped"]), size="xs", c="dimmed")
                if out["skipped"]
                else None,
            ]
        )
        return no_update, alert(summary, "green"), ctx.branch_options()
