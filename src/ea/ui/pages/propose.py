"""Propose: hand in a design (text, files, links); review the derived change set as an editable merge log; apply it to a branch."""

from __future__ import annotations

import base64
from typing import Any

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.agent.document import slug
from ea.agent.proposal import ProposalResult, fetch_link, result_from_payload
from ea.backend.branching import MAIN
from ea.models import CURRENT_STATES, TARGET_STATES, ConflictError, Forbidden, NotFoundError, ValidationError
from ea.services.roles import a_role
from ea.ui import ids
from ea.ui.components import (
    alert,
    empty,
    icon,
    impact_panel,
    layer_chips,
    markdown_editor,
    mermaid_block,
    page_title,
)
from ea.ui.context import AppContext, get_context
from ea.views.mermaid import to_mermaid

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
    return [t.name for t in ctx.registry.concrete_types()]


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
        # What the page's attribute columns gave, by the metamodel's names. Read here and
        # written on Apply; corrected in the page, since each type declares its own.
        {"field": "attributes", "flex": 1, "minWidth": 160, "editable": False},
        {
            "field": "issues",
            "flex": 1.5,
            "minWidth": 220,
            "editable": False,
            # Pinned right: it is the column that says why a row cannot be applied, and ten
            # columns put it off the edge of a wide window, where the architect correcting
            # the row cannot see it.
            "pinned": "right",
            "cellClassRules": {"ea-conflict": "params.value"},
        },
    ]


REL_COLUMNS = [
    _TICK,
    {"field": "source", "flex": 1.2, "minWidth": 180},
    {"field": "relationship", "flex": 1, "minWidth": 150},
    {"field": "target", "flex": 1.2, "minWidth": 180},
    {"field": "qualifier", "width": 130},
    {
        "field": "target_state",
        "headerName": "target",
        "width": 130,
        "cellEditor": "agSelectCellEditor",
        "cellEditorParams": {"values": ["", *TARGET_STATES]},
    },
    {"field": "note", "flex": 1, "minWidth": 140},
    {"field": "resolved", "flex": 1, "minWidth": 160, "editable": False},
    {
        "field": "issues",
        "flex": 1.5,
        "minWidth": 220,
        "editable": False,
        "pinned": "right",
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
            "attrs": dict(e.attrs),
            "attributes": "; ".join(f"{k} = {v}" for k, v in e.attrs.items()),
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
            "target_state": x.target_state,
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
    stored = stored or {}
    return {
        "title": stored.get("title", ""),
        "summary": stored.get("summary", ""),
        "missing": list(stored.get("missing") or []),
        "template_id": stored.get("template_id", ""),
        "template_name": stored.get("template_name", ""),
        "sources": list(stored.get("sources") or []),
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
                "attrs": dict(r.get("attrs") or {}),
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
                "target_state": r.get("target_state") or "",
                "note": r.get("note") or "",
                "include": r.get("key") in rel_keys,
            }
            for i, r in enumerate(rel_rows or [])
            if (r.get("source") or r.get("target"))
        ],
    }


def _revision_note(r: ProposalResult):
    """That the page revises the last pass on the branch, and what that pass wrote which the page
    no longer carries — listed, never deleted: the architect unticks it off the branch."""
    if not r.revises:
        return None
    lines = [
        dmc.Text(
            "This page revises the proposal of the same title already on the branch: what that pass "
            "created is updated rather than written twice.",
            size="sm",
            fw=500,
        )
    ]
    if r.no_longer:
        lines += [
            dmc.Text(
                "The earlier pass wrote these, and this page no longer carries them. They stay on the "
                "branch until you remove them there:",
                size="sm",
            ),
            html.Ul(
                [html.Li(f"{d['name']} [{d['id']}]", style={"fontSize": "0.85rem"}) for d in r.no_longer],
                style={"margin": "0.3rem 0 0", "paddingLeft": "1.2rem"},
            ),
        ]
    return html.Div(alert(html.Div(lines), "blue"), style={"marginBottom": "0.5rem"})


def _touches_label(r: ProposalResult) -> str:
    """The Impact tab's name, with the one count a reader should not miss: what is left dangling."""
    impact = r.impact or {}
    dangling = len(impact.get("dangling") or [])
    reached = len(impact.get("reached") or [])
    if dangling:
        return f"What it touches ({dangling} left dangling)"
    return f"What it touches ({reached})" if reached else "What it touches"


def _change_view(ctx: AppContext, r: ProposalResult):
    view = ctx.proposals.view(r)
    if not view.nodes:
        return empty("Nothing to draw yet: no row names a type.")
    return mermaid_block(ids.PR_VIEW, to_mermaid(view, marked=True), legend=layer_chips(view))


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
                    dmc.Text(
                        # 'manual' is not a third provider beside the model ones: those rows
                        # came from the architect, and the line has to read that way.
                        "typed here, not read from a document"
                        if r.provider == "manual"
                        else f"read by {who}",
                        size="xs",
                        c="dimmed",
                    )
                    if r.provider
                    else None,
                    dmc.Text(f"template: {r.template_name}", size="xs", c="dimmed")
                    if r.template_name
                    else None,
                ],
                gap="sm",
                mb="sm",
            ),
            _revision_note(r),
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
            alert(
                html.Div(
                    [
                        dmc.Text(
                            "The reader also found the sources silent on the following. It does not stop Apply; answer it in the document or in the rows:",
                            fw=600,
                            size="sm",
                        ),
                        html.Ul(
                            [html.Li(m, style={"fontSize": "0.85rem"}) for m in r.missing],
                            style={"margin": "0.3rem 0 0", "paddingLeft": "1.2rem"},
                        ),
                    ]
                ),
                "blue",
            )
            if r.missing
            else None,
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            dmc.TabsTab(
                                f"Rows ({len(r.elements)} + {len(r.relationships)})",
                                value="rows",
                                leftSection=icon("tabler:table"),
                            ),
                            dmc.TabsTab(
                                _touches_label(r),
                                value="impact",
                                leftSection=icon("tabler:target-arrow"),
                            ),
                            dmc.TabsTab("Drawn", value="drawn", leftSection=icon("tabler:topology-star")),
                        ]
                    ),
                    dmc.TabsPanel(
                        html.Div(
                            [
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
                            ]
                        ),
                        value="rows",
                        pt="md",
                    ),
                    dmc.TabsPanel(
                        html.Div(
                            [
                                dmc.Text(
                                    "Read from main, before anything is written: what depends on what the change alters or retires, "
                                    "what it leaves pointing at nothing, and who must review it. It informs; it does not stop Apply.",
                                    size="xs",
                                    c="dimmed",
                                    mb=4,
                                ),
                                impact_panel(r.impact, ids.PR_IMPACT),
                            ]
                        ),
                        value="impact",
                        pt="md",
                    ),
                    dmc.TabsPanel(_change_view(ctx, r), value="drawn", pt="md"),
                ],
                id=ids.PR_TABS,
                value="rows",
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
                    # A disabled button raises no tooltip, so the reason stands beside it.
                    dmc.Text(
                        f"{a_role(ctx.role_label())} may not apply a proposal; an architect or an "
                        "admin can. Everything above is still yours to read and export."
                        if not ctx.can("propose")
                        else "",
                        id=ids.PR_APPLY_WHY,
                        size="xs",
                        c="dimmed",
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
    template_options = [{"value": key, "label": label} for key, label, _ in ctx.templates.offered()]
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
                                dmc.Select(
                                    id=ids.PR_TPL_PICK,
                                    label="Template",
                                    description="The shape the page is written in. A page that names its own template in its front matter is read with that one.",
                                    data=template_options,
                                    value=template_options[0]["value"] if template_options else None,
                                    placeholder="The metamodel's own names",
                                    clearable=True,
                                    comboboxProps={"withinPortal": True},
                                ),
                                dmc.Group(
                                    [
                                        dmc.Button(
                                            "Download template",
                                            id=ids.PR_TEMPLATE,
                                            variant="light",
                                            leftSection=icon("tabler:download"),
                                            disabled=not template_options,
                                        ),
                                        dmc.Button(
                                            "Load example",
                                            id=ids.PR_EXAMPLE,
                                            variant="subtle",
                                            color="gray",
                                            leftSection=icon("tabler:wand"),
                                            disabled=not template_options,
                                        ),
                                    ],
                                    gap="xs",
                                ),
                                dmc.Text(
                                    "Start from a template: its tables work without a model key. Load example "
                                    "puts its worked example straight into the editor on the right."
                                    if template_options
                                    else "No template is offered for this organisation's metamodel. A page whose "
                                    "table headings name element types is read all the same.",
                                    size="xs",
                                    c="dimmed",
                                ),
                                _template_admin(ctx) if ctx.can("manage_templates") else None,
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


def _kept_rows(ctx: AppContext):
    kept = ctx.templates.list()
    if not kept:
        return dmc.Text("None kept yet: the starters above are offered instead.", size="xs", c="dimmed")
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Text(t.name, size="sm", fw=500),
                    dmc.Text(
                        "this metamodel" if t.pack_id == ctx.registry.pack.id else f"typed in {t.pack_id}",
                        size="xs",
                        c="dimmed",
                    ),
                    dmc.Button(
                        "Delete",
                        id={"type": ids.PR_TPL_DELETE, "id": t.template_id},
                        size="compact-xs",
                        variant="subtle",
                        color="red",
                        **{"aria-label": f"Delete the template {t.name}"},
                    ),
                ],
                gap="xs",
            )
            for t in kept
        ],
        gap=4,
    )


def _template_admin(ctx: AppContext):
    """Where an admin keeps the organisation's own templates: uploaded, or copied from a starter."""
    return dmc.Accordion(
        dmc.AccordionItem(
            [
                dmc.AccordionControl("Templates this organisation keeps", icon=icon("tabler:template")),
                dmc.AccordionPanel(
                    dmc.Stack(
                        [
                            html.Div(_kept_rows(ctx), id=ids.PR_TPL_LIST),
                            dcc.Upload(
                                id=ids.PR_TPL_UPLOAD,
                                children=dmc.Text(
                                    "Drop a template (Markdown with `proposal_template:` front matter) to keep it",
                                    size="xs",
                                ),
                                style={
                                    "border": "1px dashed #adb5bd",
                                    "borderRadius": 8,
                                    "padding": "0.4rem",
                                    "cursor": "pointer",
                                },
                            ),
                            dmc.Button(
                                "Keep the picked starter as our own",
                                id=ids.PR_TPL_KEEP,
                                size="xs",
                                variant="light",
                            ),
                            html.Div(id=ids.PR_TPL_FEEDBACK),
                        ],
                        gap="xs",
                    )
                ),
            ],
            value="templates",
        ),
        variant="contained",
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
            # `fetch_link` raises with the URL already in its message, so prefixing it again
            # names the same link twice in one sentence.
            reason = str(exc)
            problems.append(reason if url in reason else f"{url}: {reason}")
    return sources, problems


def _matched_on(branch: str | None) -> str:
    """The branch a proposal is matched against: the open branch it will be applied to, or
    `main` when a new branch will be created from it."""
    return branch if branch and branch != NEW_OPTION else MAIN


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

    def picked(key: str | None) -> tuple[str, str] | None:
        """(name, document) of the picked template, or of the first offered when none is picked."""
        templates = get_context().templates
        offered = templates.offered()
        key = key or (offered[0][0] if offered else None)
        return templates.document(key) if key else None

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.PR_TEMPLATE, "n_clicks"),
        State(ids.PR_TPL_PICK, "value"),
        prevent_initial_call=True,
    )
    def template(n, key):
        if not n:
            return no_update
        found = picked(key)
        if found is None:
            return no_update
        name, document = found
        return dcc.send_string(document, f"{slug(name) or 'proposal-template'}.md")

    @app.callback(
        Output({"type": ids.MD_TEXT, "id": ids.PR_TEXT}, "value", allow_duplicate=True),
        Input(ids.PR_EXAMPLE, "n_clicks"),
        State(ids.PR_TPL_PICK, "value"),
        prevent_initial_call=True,
    )
    def example(n, key):
        if not n:
            return no_update
        found = picked(key)
        return found[1] if found else no_update

    @app.callback(
        Output(ids.PR_TPL_FEEDBACK, "children"),
        Output(ids.PR_TPL_LIST, "children"),
        Output(ids.PR_TPL_PICK, "data"),
        Input(ids.PR_TPL_UPLOAD, "contents"),
        Input(ids.PR_TPL_KEEP, "n_clicks"),
        Input({"type": ids.PR_TPL_DELETE, "id": dash.ALL}, "n_clicks"),
        State(ids.PR_TPL_UPLOAD, "filename"),
        State(ids.PR_TPL_PICK, "value"),
        prevent_initial_call=True,
    )
    def keep_templates(contents, keep, deletes, filename, key):
        trig = dash_ctx.triggered_id
        ctx = get_context()
        templates = ctx.templates
        said: list = []
        try:
            if trig == ids.PR_TPL_UPLOAD and contents:
                _, b64 = contents.split(",", 1)
                document = base64.b64decode(b64).decode("utf-8-sig", errors="replace")
                kept = templates.save(document, ctx.actor)
                notes = templates.check(document)
                said = [alert(f"Kept {kept.name!r} from {filename}.", "green")] + (
                    [alert(html.Ul([html.Li(n) for n in notes]), "yellow")] if notes else []
                )
            elif trig == ids.PR_TPL_KEEP and keep:
                if not key or not key.startswith("starter:"):
                    return (
                        alert("Pick a starter first: it is the one marked (starter).", "yellow"),
                        no_update,
                        no_update,
                    )
                kept = templates.add_starter(key.split(":", 1)[1], ctx.actor)
                said = [alert(f"Kept {kept.name!r} as this organisation's own.", "green")]
            elif isinstance(trig, dict) and trig.get("type") == ids.PR_TPL_DELETE and any(deletes or []):
                gone = templates.get(trig["id"])
                templates.delete(gone.template_id, ctx.actor)
                said = [alert(f"Deleted {gone.name!r}.", "green")]
            else:
                return no_update, no_update, no_update
        except (ValidationError, NotFoundError, Forbidden) as exc:
            msg = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
            return alert(msg, "red"), no_update, no_update
        options = [{"value": k, "label": label} for k, label, _ in templates.offered()]
        return html.Div(said), _kept_rows(ctx), options

    @app.callback(
        Output(ids.PR_RESULT, "children"),
        Output(ids.PR_RESULT_STORE, "data"),
        Input(ids.PR_ANALYSE, "n_clicks"),
        State({"type": ids.MD_TEXT, "id": ids.PR_TEXT}, "value"),
        State(ids.PR_STORE, "data"),
        State(ids.PR_LINKS, "value"),
        State(ids.PR_WP, "value"),
        State(ids.PR_WP_NEW, "value"),
        State(ids.PR_BRANCH, "value"),
        State(ids.PR_TPL_PICK, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.PR_ANALYSE, "loading"), True, False)],
    )
    def analyse(n, text, files, links, wp, wp_new, branch, template_key):
        if not n:
            return no_update, no_update
        ctx = get_context()
        on = _matched_on(branch)
        sources, problems = _sources(text, files, links)
        if sources:
            result = ctx.proposals.analyse(sources, on, template_key)
        else:
            result = ctx.proposals.resolve(ProposalResult(provider="manual"), on)
        if not result.work_package:
            result.work_package = _wp_choice(wp, wp_new)
            result = ctx.proposals.resolve(result, on)
        head = alert("Some links could not be read: " + "; ".join(problems), "red") if problems else None
        stored = {
            "title": result.title,
            "summary": result.summary,
            "work_package": result.work_package,
            "missing": result.missing,
            "template_id": result.template_id,
            "template_name": result.template_name,
            "sources": result.sources,
        }
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
        result = ctx.proposals.resolve(result_from_payload(payload, "manual"), _matched_on(branch))
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
                    + (f", {len(out['retired'])} marked for decommissioning" if out.get("retired") else "")
                    + (f", {len(out['skipped'])} row(s) skipped" if out["skipped"] else "")
                    + (" — a revision of the proposal already there" if out.get("revises") else "")
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
