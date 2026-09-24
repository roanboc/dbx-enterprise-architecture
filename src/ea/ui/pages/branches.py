"""Branches: the list, a branch's change set as a merge log, merge item by item, abandon."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx
from flask import session

from ea.backend.branching import MAIN, set_branch, use_branch
from ea.models import ChangeItem, ChangeSet, ConflictError, Forbidden, NotFoundError
from ea.ui import ids, layout
from ea.ui.components import (
    alert,
    element_href,
    empty,
    icon,
    impact_panel,
    layer_chips,
    mermaid_block,
    page_title,
    simple_table,
)
from ea.ui.context import AppContext, get_context
from ea.views import view_from_ids
from ea.views.mermaid import to_mermaid

STATUS_COLOURS = {
    "open": "green",
    "in_review": "yellow",
    "approved": "teal",
    "merged": "indigo",
    "abandoned": "gray",
}
CHANGE_COLOURS = {"added": "green", "changed": "orange", "deleted": "red"}

#: The merge log's columns. Every width here is spent against about 1265px of card at the
#: viewport the round is taken at, and `tests/test_ui_grids.py` holds the sum to it: the
#: 'take' cell is the one control that settles a conflict, and a column added without the
#: arithmetic pushed it to the card's edge and the two version columns past it.
GRID_COLUMNS = [
    {
        "field": "include",
        "headerName": "",
        "checkboxSelection": True,
        "headerCheckboxSelection": True,
        "width": 46,
        "pinned": "left",
        "sortable": False,
        "filter": False,
        "resizable": False,
        "valueFormatter": {"function": "''"},
    },
    {
        "field": "change",
        "width": 100,
        "cellClassRules": {
            "ea-added": "params.value == 'added'",
            "ea-changed": "params.value == 'changed'",
            "ea-deleted": "params.value == 'deleted'",
        },
    },
    {"field": "kind", "width": 100},
    {"field": "entity_id", "headerName": "id", "width": 170},
    {"field": "label", "headerName": "what", "flex": 2, "minWidth": 210},
    {"field": "fields", "headerName": "fields changed", "flex": 1, "minWidth": 130},
    {
        "field": "conflict",
        "width": 100,
        "cellDataType": "text",
        # Only a real conflict is red. 'stale' means main moved under the row without
        # disagreeing with it, which merges as it is and is worth knowing, not worth alarm.
        "cellClassRules": {"ea-conflict": "params.value == 'conflict'"},
    },
    {
        "field": "disputed",
        "headerName": "both changed",
        "flex": 1,
        "minWidth": 120,
        "tooltipField": "disputed",
    },
    {
        "field": "resolution",
        "headerName": "take",
        "width": 110,
        "editable": {"function": "params.data.conflict == 'conflict'"},
        "cellEditor": "agSelectCellEditor",
        "cellEditorParams": {"values": ["", "branch", "main"]},
        "cellClassRules": {"ea-editable": "params.data.conflict == 'conflict'"},
    },
    {"field": "base_version", "headerName": "base", "width": 70},
    {"field": "main_version", "headerName": "main", "width": 70},
]


def _branch_table(ctx: AppContext, status: str | None, selected: str | None):
    rows = ctx.branches.list(status or None)
    if not rows:
        text = (
            f"No {status.replace('_', ' ')} branches. Pick another status above."
            if status and ctx.branches.list()
            else "No branches yet. Create one with the + button in the header."
        )
        return dmc.Text(text, c="dimmed", size="sm")
    out = []
    for b in rows:
        wp = ctx.backend.get_element(b.work_package) if b.work_package else None
        out.append(
            [
                dmc.Anchor(
                    b.name,
                    href=f"/branches?branch={b.branch_id}",
                    size="sm",
                    fw=700 if b.branch_id == selected else 500,
                ),
                dmc.Badge(
                    b.status.replace("_", " "),
                    color=STATUS_COLOURS.get(b.status, "gray"),
                    size="xs",
                    variant="light",
                ),
                b.changes,
                dmc.Anchor(wp.name, href=element_href(wp.element_id), size="sm") if wp else "",
                b.created_by,
                str(b.created_at)[:16] if b.created_at else "",
                dmc.Button(
                    "Open",
                    id={"type": ids.BR_OPEN, "id": b.branch_id},
                    size="compact-xs",
                    variant="subtle",
                ),
            ]
        )
    return simple_table(["branch", "status", "rows", "work package", "by", "created", ""], out)


def _before_after(svc, it: ChangeItem, editable: bool = False):
    """Every field in play, who moved it, and — where both did — which value main keeps.

    A merge is per field, so this is where a conflict is actually settled. A field only one
    side moved needs no decision and says so; a field both moved carries a choice, and until
    it is made the merge holds the row back rather than guessing.
    """
    rows = svc.field_rows(it)
    if not rows:
        return dmc.Text("No field differs.", c="dimmed", size="xs")
    body = []
    for r in rows:
        if r["disputed"] and editable:
            decision = dmc.SegmentedControl(
                id={"type": ids.BR_FIELD_TAKE, "key": it.key, "field": r["field"]},
                data=[{"value": "main", "label": "main"}, {"value": "branch", "label": "branch"}],
                value="",
                size="xs",
                color="orange",
            )
        elif r["disputed"]:
            decision = dmc.Badge("both changed it", color="red", variant="light", size="xs", tt="none")
        elif r["changed_by_main"]:
            decision = dmc.Badge("main moved it", color="blue", variant="light", size="xs", tt="none")
        elif r["changed_by_branch"]:
            decision = dmc.Badge("the branch", color="green", variant="light", size="xs", tt="none")
        else:
            decision = dmc.Text("—", size="xs", c="dimmed")
        body.append([r["field"], _fmt(r["base"]), _fmt(r["main"]), _fmt(r["branch"]), decision])
    return html.Div(
        [
            simple_table(["field", "was", "main now", "branch", "takes"], body, striped=False),
            dmc.Text(
                "Only a field both sides changed needs a decision. The rest merge as they are: "
                "the branch's changes land on main's current row, and what main moved and the "
                "branch did not is kept.",
                size="xs",
                c="dimmed",
                mt=4,
            ),
        ]
    )


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return str(v)


def _may_abandon(ctx: AppContext, b) -> bool:
    return ctx.can("abandon_branch") and (ctx.role() == "admin" or b.created_by == ctx.actor)


def _review_panel(ctx: AppContext, b, has_rows: bool, message: Any = None):
    """Where the branch stands in its review, who must approve what, and the controls the role has.

    `message` is the outcome of the last review decision, and it is rendered here rather than
    under the merge log: a refusal belongs beside the button that raised it.
    """
    reqs = ctx.reviews.requirements(b.branch_id) if b.status not in ("merged", "abandoned") else []
    reviews = ctx.reviews.reviews(b.branch_id)
    me = ctx.current_user()
    is_author = b.created_by == me.username
    can_request = (
        b.status == "open" and has_rows and ctx.can("request_review") and (is_author or ctx.role() == "admin")
    )
    can_review = b.status == "in_review" and ctx.can("review") and not is_author
    my_types = [
        r["type_id"]
        for r in reqs
        if not r["approved"]
        and (ctx.role() == "admin" or ctx.reviews.covers(r["type_id"], me.username, me.groups))
    ]
    req_rows = [
        [
            dmc.Text(r["type"], size="sm", fw=500),
            dmc.Text(", ".join(r["reviewers"]) if r["reviewers"] else "any reviewer", size="sm", c="dimmed"),
            dmc.Badge("approved by " + ", ".join(r["approved_by"]), color="teal", variant="light", size="xs")
            if r["approved"]
            else dmc.Badge("pending", color="yellow", variant="light", size="xs"),
        ]
        for r in reqs
    ]
    history = [
        dmc.Text(
            f"{str(rv.decided_at)[:16]} · {rv.reviewer} {'approved' if rv.decision == 'approve' else 'sent back'}"
            + (
                f" ({', '.join(ctx.registry.types[t].name if t in ctx.registry.types else t for t in rv.type_ids)})"
                if rv.decision == "approve"
                else ""
            )
            + (f": {rv.comment}" if rv.comment else ""),
            size="xs",
            c="dimmed",
        )
        for rv in reviews
    ]
    if b.status == "open":
        headline = "Not yet in review. " + (
            "Request a review when the branch is complete: it freezes until the reviewers decide."
            if has_rows
            else "Nothing to review yet."
        )
    elif b.status == "in_review":
        headline = "In review: frozen until every touched type is approved, or a reviewer sends it back."
    elif b.status == "approved":
        headline = "Approved by its reviewers: the author or an admin may merge it."
    else:
        headline = f"This branch is {b.status}."
    controls = []
    if can_request:
        controls.append(
            dmc.Button(
                "Request review", id=ids.RV_REQUEST, leftSection=icon("tabler:checklist"), variant="light"
            )
        )
    if can_review:
        controls += [
            dmc.MultiSelect(
                id=ids.RV_TYPES,
                data=[{"value": r["type_id"], "label": r["type"]} for r in reqs if not r["approved"]],
                value=my_types,
                placeholder="Types to approve",
                w=320,
                size="sm",
            ),
            dmc.TextInput(id=ids.RV_COMMENT, placeholder="Comment (required to send back)", w=320, size="sm"),
            dmc.Button(
                "Approve",
                id=ids.RV_APPROVE,
                color="teal",
                leftSection=icon("tabler:checklist"),
                disabled=not my_types,
            ),
            dmc.Button(
                "Send back",
                id=ids.RV_SEND_BACK,
                color="orange",
                variant="light",
                leftSection=icon("tabler:refresh"),
            ),
        ]
    elif b.status == "in_review" and is_author:
        controls.append(dmc.Text("You wrote this branch; somebody else approves it.", size="xs", c="dimmed"))
    # every control the callbacks expect must exist, hidden when the role has no use for it
    hidden = html.Div(
        [
            html.Div(id=ids.RV_REQUEST) if not can_request else None,
            html.Div(id=ids.RV_APPROVE) if not can_review else None,
            html.Div(id=ids.RV_SEND_BACK) if not can_review else None,
            dcc.Store(id=ids.RV_TYPES, data=[]) if not can_review else None,
            dcc.Store(id=ids.RV_COMMENT, data="") if not can_review else None,
        ],
        hidden=True,
    )
    return dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Stack(
                        [
                            dmc.Title("Review", order=2, className="ea-section-title"),
                            dmc.Text(headline, size="xs", c="dimmed"),
                        ],
                        gap=2,
                    ),
                    dmc.Group(controls, gap="xs", align="flex-end"),
                ],
                justify="space-between",
                align="flex-start",
            ),
            simple_table(["type touched", "reviewers", "decision"], req_rows) if req_rows else None,
            dmc.Stack(history, gap=2, mt="xs") if history else None,
            html.Div(message, id=ids.RV_FEEDBACK, style={"marginTop": "0.4rem"}),
            hidden,
        ],
        p="md",
        withBorder=True,
        className="ea-card",
        mb="md",
    )


def _detail(ctx: AppContext, branch_id: str, message: Any = None, review_message: Any = None):
    """The branch's head, counts and merge log.

    `message` is the outcome of the last merge or abandon, printed under the log it acted on;
    `review_message` is the outcome of the last review decision, printed in the review panel
    beside the button that made it.
    """
    try:
        cs: ChangeSet = ctx.branches.diff(branch_id)
    except NotFoundError:
        return alert(f"No branch {branch_id}.", "red")
    b = cs.branch
    counts = cs.counts()
    rows = ctx.branches.item_rows(cs)
    wp = ctx.backend.get_element(b.work_package) if b.work_package else None
    head = dmc.Group(
        [
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Title(b.name, order=2, size="h3"),
                            dmc.Badge(
                                b.status.replace("_", " "),
                                color=STATUS_COLOURS.get(b.status, "gray"),
                                variant="light",
                            ),
                            dmc.Code(b.branch_id),
                        ],
                        gap="sm",
                    ),
                    dmc.Text(b.description or "No description.", size="sm", c="dimmed"),
                    dmc.Group(
                        [
                            dmc.Text(
                                f"created by {b.created_by} on {str(b.created_at)[:16]}",
                                size="xs",
                                c="dimmed",
                            ),
                            dmc.Anchor(f"work package {wp.name}", href=element_href(wp.element_id), size="xs")
                            if wp
                            else None,
                            dmc.Text(
                                f"closed by {b.closed_by} on {str(b.closed_at)[:16]}", size="xs", c="dimmed"
                            )
                            if b.closed_at
                            else None,
                        ],
                        gap="md",
                    ),
                ],
                gap=4,
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Switch to this branch" if ctx.branch() != branch_id else "You are on this branch",
                        id=ids.BR_SWITCH,
                        variant="light",
                        leftSection=icon("tabler:git-branch"),
                        disabled=ctx.branch() == branch_id or b.status in ("merged", "abandoned"),
                    ),
                    dmc.Button(
                        "Abandon",
                        id=ids.BR_ABANDON,
                        variant="subtle",
                        color="red",
                        leftSection=icon("tabler:trash"),
                        disabled=b.status in ("merged", "abandoned") or not _may_abandon(ctx, b),
                    ),
                ],
                gap="xs",
            ),
        ],
        justify="space-between",
        align="flex-start",
    )
    count_badges = dmc.Group(
        [
            dmc.Badge(f"{counts['added']} added", color="green", variant="light"),
            dmc.Badge(f"{counts['changed']} changed", color="orange", variant="light"),
            dmc.Badge(f"{counts['deleted']} deleted", color="red", variant="light"),
            dmc.Badge(
                f"{counts['conflicts']} conflicts",
                color="red",
                variant="filled" if counts["conflicts"] else "light",
            ),
        ],
        gap="xs",
        my="sm",
    )
    # Nothing told an author their branch had gone stale until the merge screen showed a
    # column of conflicts. A conflict is main moving under a row this branch holds, so the
    # count of them is the age of the branch measured in the only way that matters.
    behind = sum(1 for i in cs.items if i.stale)
    disputed = counts["conflicts"]
    stale_note = (
        dmc.Alert(
            dmc.Text(
                f"Main has moved under {behind} of this branch's {len(cs.items)} rows since it "
                + (
                    f"started, and on {disputed} of them the two changed the same field. Those are "
                    "marked 'conflict' below: open the row, decide each disputed field, then tick it. "
                    "Everything else merges as it is — the branch's changes land on main's current "
                    "row, and what main moved and the branch did not is kept."
                    if disputed
                    else "started, but never the same field the branch changed. They merge as they "
                    "are: the branch's changes land on main's current row, and what main moved is kept."
                ),
                size="sm",
            ),
            title="This branch is behind main",
            color="orange" if disputed else "blue",
            variant="light",
            withCloseButton=False,
            mb="sm",
        )
        if behind
        else None
    )
    merge_ok, merge_why = ctx.reviews.can_merge(branch_id, ctx.actor)
    details = []
    for it in cs.items:
        details.append(
            dmc.AccordionItem(
                [
                    dmc.AccordionControl(
                        dmc.Group(
                            [
                                dmc.Badge(it.change, color=CHANGE_COLOURS.get(it.change, "gray"), size="xs"),
                                dmc.Text(it.kind, size="xs", c="dimmed"),
                                dmc.Code(it.entity_id),
                                dmc.Text(
                                    next(r["label"] for r in rows if r["key"] == it.key), size="sm", fw=500
                                ),
                                dmc.Badge("conflict", color="red", size="xs") if it.conflict else None,
                            ],
                            gap="sm",
                        )
                    ),
                    dmc.AccordionPanel(
                        [
                            dmc.Text(
                                f"Main moved from version {it.base_version} to {it.main_version} since this "
                                f"branch took its copy, and both sides changed "
                                f"{', '.join(it.overlapping) or 'this row'}. Decide each one below, then tick "
                                "the row in the merge log.",
                                size="xs",
                                c="red",
                                mb="xs",
                            )
                            if it.conflict
                            else None,
                            _before_after(ctx.branches, it, editable=it.conflict and merge_ok),
                            dmc.Anchor("open on this branch", href=element_href(it.entity_id), size="xs")
                            if it.kind == "element" and it.change != "deleted"
                            else None,
                        ]
                    ),
                ],
                value=it.key,
            )
        )
    empty_note = (
        dmc.Text(
            "Nothing on this branch yet: edits, imports and applied proposals made on it will appear here."
            if b.status == "open"
            else "This branch is closed; what it held was merged or discarded.",
            c="dimmed",
            size="sm",
        )
        if not rows
        else None
    )
    grid = dag.AgGrid(
        id=ids.BR_GRID,
        columnDefs=GRID_COLUMNS,
        rowData=rows,
        getRowId="params.data.key",
        # Everything clean is ticked, because merging the branch is what the button is for.
        # A conflict is not: main moved under that row, and a row that overwrites somebody
        # else's work should be ticked by a person rather than by the page.
        selectedRows=[r for r in rows if r["conflict"] != "conflict"],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={
            "rowSelection": "multiple",
            # The header tick used to select rows the column filter was hiding, so a reader
            # who filtered to three rows and pressed it merged the whole branch.
            "headerCheckboxSelectionFilteredOnly": True,
            "suppressRowClickSelection": True,
            "animateRows": False,
            "singleClickEdit": True,
            "stopEditingWhenCellsLoseFocus": True,
            "domLayout": "autoHeight",
        },
        className="ag-theme-alpine",
        style={"width": "100%"},
    )
    changes = html.Div(
        [
            dmc.Paper(
                [
                    dmc.Group(
                        [
                            dmc.Stack(
                                [
                                    dmc.Title("Merge log", order=2, className="ea-section-title"),
                                    dmc.Text(
                                        "Every row is one element or relationship this branch would write to main. Tick what goes "
                                        "to main now; what is not ticked remains on the branch. An applied row is main's "
                                        "current row with the branch's changes laid over it. A conflict means both sides "
                                        "changed the same field — the 'both changed' column names which — so it arrives "
                                        "neither ticked nor decided: settle each field under 'What each row changes', "
                                        "then tick it.",
                                        size="xs",
                                        c="dimmed",
                                    ),
                                ],
                                gap=2,
                            ),
                            dmc.Stack(
                                [
                                    dmc.Button(
                                        "Merge ticked rows to main",
                                        id=ids.BR_MERGE,
                                        leftSection=icon("tabler:git-merge"),
                                        disabled=not rows or not merge_ok,
                                    ),
                                    dmc.Text(merge_why, size="xs", c="dimmed", ta="right")
                                    if merge_why
                                    else None,
                                ],
                                gap=2,
                                align="flex-end",
                            ),
                        ],
                        justify="space-between",
                        align="flex-start",
                        mb="sm",
                    ),
                    empty_note,
                    html.Div(grid, hidden=not rows),
                    html.Div(message, id=ids.BR_FEEDBACK, style={"marginTop": "0.5rem"}),
                ],
                p="md",
                withBorder=True,
                className="ea-card",
            ),
            dmc.Paper(
                [
                    dmc.Title("What each row changes", order=2, className="ea-section-title"),
                    dmc.Text(
                        "What the branch started from, what main holds now, and what the branch would "
                        "write — with who moved each field, and a choice where both did.",
                        size="xs",
                        c="dimmed",
                        mb="xs",
                    ),
                    dmc.Accordion(details, variant="separated", multiple=True),
                ],
                p="md",
                withBorder=True,
                mt="md",
                className="ea-card",
            )
            if rows
            else None,
        ]
    )
    proposals = ctx.backend.list_proposals(branch_id)  # newest first
    if not rows and not proposals:
        tabs = changes
    else:
        impact = ctx.impact.of_branch(branch_id).to_dict()
        dangling = len(impact.get("dangling") or [])
        tabs = dmc.Tabs(
            [
                dmc.TabsList(
                    [
                        dmc.TabsTab(
                            f"Changes ({len(rows)})", value="changes", leftSection=icon("tabler:git-merge")
                        ),
                        dmc.TabsTab(
                            f"Proposals ({len(proposals)})",
                            value="proposals",
                            leftSection=icon("tabler:file-text"),
                        ),
                        dmc.TabsTab(
                            f"What it touches ({dangling} left dangling)" if dangling else "What it touches",
                            value="impact",
                            leftSection=icon("tabler:target-arrow"),
                        ),
                        dmc.TabsTab("Drawn", value="drawn", leftSection=icon("tabler:topology-star")),
                    ]
                ),
                dmc.TabsPanel(changes, value="changes", pt="md"),
                dmc.TabsPanel(_proposals_panel(proposals), value="proposals", pt="md"),
                dmc.TabsPanel(
                    html.Div(
                        [
                            dmc.Text(
                                "What the branch touches on main beyond its own rows. None of it stops a review or a merge.",
                                size="xs",
                                c="dimmed",
                                mb="xs",
                            ),
                            impact_panel(impact, ids.BR_IMPACT),
                        ]
                    ),
                    value="impact",
                    pt="md",
                ),
                dmc.TabsPanel(_branch_view(ctx, cs), value="drawn", pt="md"),
            ],
            id=ids.BR_TABS,
            value="changes",
        )
    return html.Div(
        [
            head,
            count_badges,
            stale_note,
            html.Div(_review_panel(ctx, b, bool(rows), review_message), id=ids.RV_PANEL),
            tabs,
        ]
    )


def _proposals_panel(proposals: list) -> Any:
    """The proposals the branch was written from, pass by pass, with the page as handed in."""
    if not proposals:
        return empty("No proposal was applied to this branch: its rows were edited or imported.")
    passes = {p.proposal_id: n for n, p in enumerate(reversed(proposals), start=1)}
    items = []
    for p in proposals:
        result = p.result or {}
        pages = [src for src in p.sources if (src.get("text") or "").strip()]
        applied = result.get("applied") or {}
        items.append(
            dmc.AccordionItem(
                [
                    dmc.AccordionControl(
                        dmc.Group(
                            [
                                dmc.Text(p.title, fw=600, size="sm"),
                                dmc.Badge(f"pass {passes[p.proposal_id]}", variant="light", size="sm"),
                                dmc.Text(
                                    f"by {p.created_by or '?'}"
                                    + (f", {p.created_at:%Y-%m-%d %H:%M}" if p.created_at else "")
                                    + (
                                        f" · template {result.get('template_name')}"
                                        if result.get("template_name")
                                        else ""
                                    )
                                    + (" · revises the pass before" if p.revises else ""),
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                            gap="sm",
                        )
                    ),
                    dmc.AccordionPanel(
                        dmc.Stack(
                            [
                                dmc.Text(
                                    f"{len(applied.get('created') or [])} created, {len(applied.get('linked') or [])} linked, "
                                    f"{len(applied.get('relationships') or [])} relationship(s) written"
                                    + (
                                        f", {len(applied.get('retired'))} marked for decommissioning"
                                        if applied.get("retired")
                                        else ""
                                    ),
                                    size="sm",
                                ),
                                alert(
                                    html.Ul([html.Li(m) for m in result.get("missing") or []]),
                                    "blue",
                                    dismissible=False,
                                )
                                if result.get("missing")
                                else None,
                                *[
                                    html.Details(
                                        [
                                            html.Summary(
                                                f"The page as handed in: {src.get('name') or src.get('kind')}"
                                            ),
                                            dmc.Code(
                                                src.get("text") or "",
                                                block=True,
                                                style={"maxHeight": "24rem", "overflow": "auto"},
                                            ),
                                        ]
                                    )
                                    for src in pages
                                ],
                            ],
                            gap="xs",
                        )
                    ),
                ],
                value=p.proposal_id,
            )
        )
    return dmc.Accordion(items, variant="separated", id=ids.BR_PROPOSALS)


def _branch_view(ctx: AppContext, cs: ChangeSet) -> Any:
    """The branch's change drawn: the elements it touches, with their states marked."""
    with use_branch(cs.branch.branch_id):
        element_ids = [it.entity_id for it in cs.items if it.kind == "element" and it.change != "deleted"]
        changed = [
            it.entity_id
            for it in cs.items
            if it.kind == "element"
            and (it.after or {}).get("target_state") not in (None, "", "keep", "undecided")
        ]
        for it in cs.items:
            row = it.after or it.before or {}
            if it.kind == "relationship":
                element_ids += [x for x in (row.get("src_id"), row.get("dst_id")) if x]
        view = view_from_ids(
            ctx.registry, ctx.graph, element_ids, f"{cs.branch.name}, drawn", focus_ids=changed
        )
    if not view.nodes:
        return empty("Nothing to draw.")
    return mermaid_block("br-view", to_mermaid(view, marked=True), legend=layer_chips(view))


def render(ctx: AppContext, search: str | None = None) -> html.Div:
    q = parse_qs((search or "").lstrip("?"))
    selected = (q.get("branch") or [None])[0]
    if not selected and ctx.branch() != MAIN:
        selected = ctx.branch()
    if not selected:
        open_ = ctx.branches.open()
        selected = open_[0].branch_id if open_ else None
    return html.Div(
        [
            page_title(
                "Branches",
                "A branch is a draft of the model laid over main: every architect works on their own, merges item by item, and main moves only when someone merges.",
                dmc.Button(
                    "New branch",
                    id=ids.BRANCH_NEW_OPEN + "-page",
                    leftSection=icon("tabler:plus"),
                    variant="light",
                    disabled=not ctx.can("create_branch"),
                ),
            ),
            dmc.Group(
                [
                    dmc.SegmentedControl(
                        id=ids.BR_STATUS,
                        data=[
                            {"value": "open", "label": "Open"},
                            {"value": "in_review", "label": "In review"},
                            {"value": "approved", "label": "Approved"},
                            {"value": "merged", "label": "Merged"},
                            {"value": "abandoned", "label": "Abandoned"},
                            {"value": "", "label": "All"},
                        ],
                        value="open",
                        size="xs",
                    ),
                    dmc.Text(_where(ctx), id=ids.BR_WHERE, size="sm", c="dimmed"),
                ],
                gap="md",
                mb="sm",
            ),
            dcc.Store(id=ids.BR_SELECTED, data=selected),
            html.Div(_branch_table(ctx, "open", selected), id=ids.BR_LIST),
            dmc.Divider(my="md"),
            html.Div(
                _detail(ctx, selected)
                if selected
                else dmc.Text("Pick a branch above.", c="dimmed", size="sm"),
                id=ids.BR_DETAIL,
            ),
        ]
    )


def _where(ctx: AppContext) -> str:
    """Which branch the reader is standing on, as the page says it.

    Written in one place because a callback has to rewrite it: abandoning the branch you are
    on moves the header to main, and a line still naming the branch that was thrown away
    disagrees with the header a few pixels above it.
    """
    return f"You are on {ctx.branch()} as {ctx.role_label()}."


def _type_names(ctx: AppContext, type_ids: list[str]) -> str:
    """Element types by the names the page uses for them everywhere else."""
    return ", ".join(ctx.registry.types[t].name if t in ctx.registry.types else t for t in (type_ids or []))


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.BR_LIST, "children"),
        Input(ids.BR_STATUS, "value"),
        State(ids.BR_SELECTED, "data"),
        prevent_initial_call=True,
    )
    def filter_list(status, selected):
        return _branch_table(get_context(), status or None, selected)

    @app.callback(
        Output(ids.BR_DETAIL, "children"),
        Output(ids.BR_SELECTED, "data"),
        Input({"type": ids.BR_OPEN, "id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_branch(clicks):
        """Open one branch's detail, and remember which one it is.

        The store used to live inside the detail, so it went with it; it belongs to the page,
        which means the page has to keep it up to date.
        """
        trig = dash_ctx.triggered_id
        if not trig or not any(clicks):
            return no_update, no_update
        return _detail(get_context(), trig["id"]), trig["id"]

    @app.callback(
        Output(ids.BRANCH_NEW_MODAL, "opened", allow_duplicate=True),
        Input(ids.BRANCH_NEW_OPEN + "-page", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_modal(n):
        return bool(n)

    @app.callback(
        Output(ids.BR_FEEDBACK, "children"),
        Output(ids.BR_DETAIL, "children", allow_duplicate=True),
        Output(ids.BR_LIST, "children", allow_duplicate=True),
        Output(ids.BRANCH_SELECT, "data", allow_duplicate=True),
        Output(ids.BRANCH_SELECT, "value", allow_duplicate=True),
        Output(ids.BR_WHERE, "children"),
        Input(ids.BR_MERGE, "n_clicks"),
        Input(ids.BR_ABANDON, "n_clicks"),
        State(ids.BR_SELECTED, "data"),
        State(ids.BR_GRID, "selectedRows"),
        State(ids.BR_GRID, "virtualRowData"),
        State(ids.BR_GRID, "rowData"),
        State(ids.BR_STATUS, "value"),
        State({"type": ids.BR_FIELD_TAKE, "key": ALL, "field": ALL}, "value"),
        State({"type": ids.BR_FIELD_TAKE, "key": ALL, "field": ALL}, "id"),
        prevent_initial_call=True,
        running=[(Output(ids.BR_MERGE, "loading"), True, False)],
    )
    def merge_or_abandon(
        n_merge, n_abandon, branch_id, selected, virtual_rows, rows, status, takes, takes_id
    ):
        trig = dash_ctx.triggered_id
        ctx = get_context()
        if trig == ids.BR_ABANDON and n_abandon:
            try:
                ctx.branches.abandon(branch_id, ctx.actor)
            except (NotFoundError, Forbidden) as exc:
                return alert(str(exc), "red"), no_update, no_update, no_update, no_update, no_update
            ctx.graph.invalidate()
            switched = _leave_if_current(ctx, branch_id)
            return (
                no_update,
                _detail(
                    ctx,
                    branch_id,
                    alert(
                        f"Branch {branch_id} abandoned; its rows are discarded and main is untouched.",
                        "green",
                    ),
                ),
                _branch_table(ctx, status or None, branch_id),
                ctx.branch_options(),
                MAIN if switched else no_update,
                _where(ctx),
            )
        if trig != ids.BR_MERGE or not n_merge:
            return (no_update,) * 6
        include = {r["key"] for r in (selected or [])}
        if not include:
            return (
                alert("Tick at least one row to merge.", "yellow"),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        current = {r["key"]: r for r in (virtual_rows or rows or [])}
        resolutions: dict[str, Any] = {
            k: r.get("resolution")
            for k, r in current.items()
            if r.get("conflict") == "conflict" and r.get("resolution") in ("branch", "main")
        }
        # A decision taken field by field, under "What each row changes", is more specific
        # than the whole-row take on the grid, so it wins where both were given.
        for spec, value in zip(takes_id or [], takes or [], strict=False):
            if value not in ("branch", "main"):
                continue
            per_field = resolutions.setdefault(spec["key"], {})
            if isinstance(per_field, dict):
                per_field[spec["field"]] = value
            else:  # a whole-row take was set as well: the field-level one is the finer word
                resolutions[spec["key"]] = {spec["field"]: value}
        try:
            res = ctx.branches.merge(branch_id, ctx.actor, include, resolutions)
        except (ConflictError, NotFoundError, Forbidden) as exc:
            return alert(str(exc), "red"), no_update, no_update, no_update, no_update, no_update
        ctx.graph.invalidate()
        msg = f"Merged {len(res.applied)} row(s) to main"
        if res.dropped:
            msg += f", dropped {len(res.dropped)} conflict(s) in favour of main"
        if res.held_back:
            msg += f", held back {len(res.held_back)} ({res.reasons()})"
        msg += (
            f"; {res.remaining} row(s) remain on the branch."
            if not res.closed
            else "; the branch is now merged and closed."
        )
        switched = res.closed and _leave_if_current(ctx, branch_id)
        return (
            no_update,
            _detail(ctx, branch_id, alert(msg, "green")),
            _branch_table(ctx, status or None, branch_id),
            ctx.branch_options(),
            MAIN if switched else no_update,
            _where(ctx),
        )

    @app.callback(
        Output(ids.BR_DETAIL, "children", allow_duplicate=True),
        Output(ids.BR_LIST, "children", allow_duplicate=True),
        Output(ids.BRANCH_SELECT, "data", allow_duplicate=True),
        Input(ids.RV_REQUEST, "n_clicks"),
        Input(ids.RV_APPROVE, "n_clicks"),
        Input(ids.RV_SEND_BACK, "n_clicks"),
        State(ids.BR_SELECTED, "data"),
        State(ids.RV_TYPES, "value"),
        State(ids.RV_COMMENT, "value"),
        State(ids.BR_STATUS, "value"),
        prevent_initial_call=True,
    )
    def review(n_req, n_ok, n_back, branch_id, types, comment, status):
        trig = dash_ctx.triggered_id
        ctx = get_context()
        me = ctx.current_user()
        try:
            if trig == ids.RV_REQUEST and n_req:
                ctx.reviews.request(branch_id, me.username)
                msg = alert("Review requested: the branch is frozen until its reviewers decide.", "green")
            elif trig == ids.RV_APPROVE and n_ok:
                out = ctx.reviews.approve(branch_id, me.username, types or None, comment or "", me.groups)
                msg = alert(
                    "Approved "
                    + _type_names(ctx, out["approved_types"])
                    + (
                        "; the branch is approved."
                        if out["complete"]
                        # Named the way the panel above names them: a reader should not have
                        # to translate an identifier back into the type they just approved.
                        else "; still pending: " + _type_names(ctx, out["pending"]) + "."
                    ),
                    "green",
                )
            elif trig == ids.RV_SEND_BACK and n_back:
                ctx.reviews.send_back(branch_id, me.username, comment or "")
                msg = alert("Sent back to the author; the branch is open again.", "orange")
            else:
                return no_update, no_update, no_update
        except (ConflictError, NotFoundError, Forbidden) as exc:
            msg = alert(str(exc), "red")
        return (
            _detail(ctx, branch_id, review_message=msg),
            _branch_table(ctx, status or None, branch_id),
            ctx.branch_options(),
        )

    @app.callback(
        Output(ids.BRANCH_SELECT, "value", allow_duplicate=True),
        Input(ids.BR_SWITCH, "n_clicks"),
        State(ids.BR_SELECTED, "data"),
        prevent_initial_call=True,
    )
    def switch(n, branch_id):
        if not n or not branch_id:
            return no_update
        return branch_id


def _leave_if_current(ctx: AppContext, branch_id: str) -> bool:
    """After a branch closes, a reader who was on it goes back to main."""
    if ctx.branch() == branch_id:
        session["branch"] = MAIN
        set_branch(MAIN)
        return True
    return False


_ = layout
