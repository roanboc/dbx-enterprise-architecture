"""Propose: hand in a design (text, files, links); settle it in conversation with the assistant;
review the derived change set as an editable merge log; apply it to a branch.

The assistant asks what the draft leaves unclear, a few questions at a time and the context
first (initiative 24); the architect answers with a choice, in words, or by editing the rows.
The draft and its conversation are kept between sittings, per architect."""

from __future__ import annotations

import base64
from typing import Any

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import ALL, MATCH, Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.agent.document import slug
from ea.agent.drawing import MAX_DRAWING_CHARS
from ea.agent.proposal import ProposalResult, fetch_link, result_from_payload
from ea.agent.questions import MAX_SHOWN, shown
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
WORDS = "__words__"  # the choice that answers a question in the architect's own words
#: What the page keeps of a draft beside its rows: the rows live in the grids, the rest here.
STORED = (
    "title",
    "summary",
    "work_package",
    "missing",
    "template_id",
    "template_name",
    "sources",
    "answers",
    "asked",
    "reason",
    "technical",
    "provider",
    "model",
    "drawing",
)

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
            "issues": "; ".join(e.issues)
            or (f"linked from its system: {e.reference_url}" if e.referenced_from else ""),
            # what the conversation settled about the row, carried with it and not shown
            "confirmed_new": e.confirmed_new,
            "referenced_from": e.referenced_from,
            "reference_url": e.reference_url,
            "drawn": e.drawn,
            "drawn_label": e.drawn_label,
            "rename_to": e.rename_to,
            "type_candidates": list(e.type_candidates),
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
            "drawn": x.drawn,
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
        "answers": dict(stored.get("answers") or {}),
        "asked": list(stored.get("asked") or []),
        "reason": stored.get("reason", ""),
        "technical": bool(stored.get("technical", False)),
        "drawing": dict(stored.get("drawing") or {}),
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
                "confirmed_new": bool(r.get("confirmed_new")),
                "referenced_from": r.get("referenced_from") or "",
                "reference_url": r.get("reference_url") or "",
                "drawn": r.get("drawn") or "",
                "drawn_label": r.get("drawn_label") or "",
                "rename_to": r.get("rename_to") or "",
                "type_candidates": list(r.get("type_candidates") or []),
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
                "drawn": bool(r.get("drawn")),
            }
            for i, r in enumerate(rel_rows or [])
            if (r.get("source") or r.get("target"))
        ],
    }


def _stored(r: ProposalResult) -> dict[str, Any]:
    """What the page keeps of a draft beside its rows."""
    d = r.to_dict()
    return {k: d.get(k) for k in STORED}


def _result_from_page(ctx: AppContext, el_rows, el_sel, rel_rows, rel_sel, stored, wp, wp_new, branch):
    """The draft as the page holds it now: the rows as edited and ticked, and the rest as kept."""
    stored = stored or {}
    work_package = stored.get("work_package") or _wp_choice(wp, wp_new)
    payload = _payload_from_rows(el_rows, el_sel, rel_rows, rel_sel, stored, work_package)
    result = result_from_payload(payload, stored.get("provider") or "manual", stored.get("model") or "")
    return ctx.proposals.resolve(result, _matched_on(branch))


def _turn_bubble(turn: dict[str, Any]):
    mine = turn.get("role") == "architect"
    head = "You" if mine else "Assistant"
    if turn.get("kind") == "answer" and turn.get("question"):
        head += " — answered: " + turn["question"][:90] + ("…" if len(turn["question"]) > 90 else "")
    return html.Div(
        [
            dmc.Text(head, size="xs", c="dimmed", fw=500),
            # an identifier in brackets is text, not a Markdown link reference
            dcc.Markdown(
                (turn.get("text") or "").replace("[", "\\[").replace("]", "\\]"), className="ea-turn-text"
            ),
        ],
        className="ea-turn " + ("ea-turn-mine" if mine else "ea-turn-assistant"),
    )


def _question_options(q: dict[str, Any], converses: bool) -> list[dict[str, Any]]:
    """A question's choices, and — when the assistant has a model — an answer in words."""
    options = [dict(o) for o in q.get("options") or []]
    if converses and not any(o.get("needs") == "text" and not o.get("choices") for o in options):
        options.append({"key": WORDS, "label": "In my own words", "needs": "text", "choices": [], "hint": ""})
    for o in options:
        o["key"] = o.get("key") or WORDS
    return options


def _question_card(q: dict[str, Any], converses: bool):
    options = _question_options(q, converses)
    tags = [
        dmc.Badge("stops Apply", color="orange", variant="light", size="xs") if q.get("blocking") else None,
        dmc.Badge("asked by the assistant", color="indigo", variant="light", size="xs")
        if q.get("asked_by") == "assistant"
        else None,
    ]
    qid = q["qid"]
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group([t for t in tags if t is not None], gap=4) if any(tags) else None,
                dmc.Text(q.get("text", ""), size="sm", fw=500),
                dcc.Store(id={"type": ids.PR_Q_DATA, "qid": qid}, data=options),
                dmc.RadioGroup(
                    dmc.Stack([dmc.Radio(label=o["label"], value=o["key"]) for o in options], gap=6),
                    id={"type": ids.PR_Q_OPT, "qid": qid},
                    value=options[0]["key"] if len(options) == 1 else None,
                    size="sm",
                    **{"aria-label": q.get("text", "")},
                ),
                dmc.Select(
                    id={"type": ids.PR_Q_CHOICE, "qid": qid},
                    data=[],
                    searchable=True,
                    style={"display": "none"},
                    comboboxProps={"withinPortal": True},
                ),
                dmc.TextInput(id={"type": ids.PR_Q_TEXT, "qid": qid}, style={"display": "none"}),
                dmc.Group(
                    dmc.Button("Answer", id={"type": ids.PR_Q_SEND, "qid": qid}, size="compact-sm"),
                    justify="flex-end",
                ),
            ],
            gap=6,
        ),
        p="sm",
        withBorder=True,
        className="ea-question",
    )


def _conversation_panel(ctx: AppContext, r: ProposalResult, conversation: list[dict[str, Any]]):
    """The conversation beside the draft: what was said, and the questions open now."""
    converses = ctx.proposals.converses
    open_now = shown(r.questions, MAX_SHOWN)
    waiting = len(r.questions) - len(open_now)
    held = sum(1 for q in r.questions if q.get("held"))
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(
                    [
                        dmc.Text("Conversation", fw=700, size="sm"),
                        dmc.Anchor("What belongs here? The guide", href="/guide#the-boundary", size="xs"),
                    ],
                    justify="space-between",
                ),
                dmc.Text(
                    "The assistant asks what the draft leaves unclear, the context first. You decide "
                    "every answer; nothing is written until you apply.",
                    size="xs",
                    c="dimmed",
                ),
                html.Div(
                    [_turn_bubble(t) for t in conversation[-24:]],
                    className="ea-turns",
                ),
                dmc.Stack([_question_card(q, converses) for q in open_now], gap="xs")
                if open_now
                else dmc.Text("No question is open.", size="sm", c="dimmed"),
                dmc.Text(
                    f"{waiting} more question{'s' if waiting != 1 else ''} waiting"
                    + (
                        f"; {held} about the application and technology rows wait until the context is settled."
                        if held
                        else "."
                    ),
                    size="xs",
                    c="dimmed",
                )
                if waiting
                else None,
                dmc.Textarea(
                    id=ids.PR_MESSAGE,
                    label="Tell the assistant",
                    placeholder="What the change is for, what a row means, what to add…"
                    if converses
                    else "No model is configured: pick a choice above, or edit the rows",
                    autosize=True,
                    minRows=2,
                    disabled=not converses,
                ),
                dmc.Group(
                    dmc.Button(
                        "Send",
                        id=ids.PR_SEND,
                        size="compact-sm",
                        variant="light",
                        leftSection=icon("tabler:send", 14),
                        disabled=not converses,
                    ),
                    justify="flex-end",
                ),
                html.Div(id=ids.PR_TURN_FEEDBACK),
            ],
            gap="xs",
        ),
        p="sm",
        withBorder=True,
        className="ea-card",
        id=ids.PR_CONV,
    )


def _drafts_panel(ctx: AppContext):
    """The architect's drafts, to pick up where they were left."""
    drafts = ctx.proposals.drafts(ctx.actor) if ctx.can("propose") else []
    if not drafts:
        return html.Div(id=ids.PR_DRAFTS, style={"marginBottom": "0.75rem"})
    rows = []
    for d in drafts[:10]:
        questions = len((d.result or {}).get("questions") or [])
        when = d.updated_at.strftime("%Y-%m-%d %H:%M") if d.updated_at else ""
        rows.append(
            dmc.Group(
                [
                    dmc.Text(d.title, size="sm", fw=500),
                    dmc.Text(
                        f"{questions} question{'s' if questions != 1 else ''} open · {when}",
                        size="xs",
                        c="dimmed",
                    ),
                    dmc.Button(
                        "Resume",
                        id={"type": ids.PR_DRAFT_RESUME, "id": d.proposal_id},
                        size="compact-xs",
                        variant="light",
                        **{"aria-label": f"Resume the draft {d.title}"},
                    ),
                    dmc.Button(
                        "Discard",
                        id={"type": ids.PR_DRAFT_DISCARD, "id": d.proposal_id},
                        size="compact-xs",
                        variant="subtle",
                        color="red",
                        **{"aria-label": f"Discard the draft {d.title}"},
                    ),
                ],
                gap="xs",
            )
        )
    return html.Div(
        alert(
            dmc.Stack([dmc.Text("Your drafts, kept between sittings", size="sm", fw=600)] + rows, gap=4),
            "blue",
            dismissible=False,
        ),
        id=ids.PR_DRAFTS,
        style={"marginBottom": "0.75rem"},
    )


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


def _preview(ctx: AppContext, r: ProposalResult, conversation: list[dict[str, Any]] | None = None):
    """The change-set preview: pushback, then the conversation beside the draft's tabs — the two
    editable grids with include ticks, what the change touches, and the change drawn."""
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
                                "Not enough to apply yet. Answer the open questions in the conversation, "
                                "or correct the rows, then re-check:",
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
            dmc.Grid(
                [
                    dmc.GridCol(
                        _conversation_panel(ctx, r, conversation or []),
                        span={"base": 12, "lg": 4},
                    ),
                    dmc.GridCol(
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
                                        dmc.TabsTab(
                                            "Drawn", value="drawn", leftSection=icon("tabler:topology-star")
                                        ),
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
                                            dmc.Title(
                                                "Relationships",
                                                order=2,
                                                className="ea-section-title",
                                                mt="md",
                                            ),
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
                        span={"base": 12, "lg": 8},
                    ),
                ],
                gutter="md",
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
        color="gray" if provider.name == "stub" else "indigo",
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
                "Hand in a design page, a document or links. The assistant identifies the elements it "
                "names, links the ones that exist, adopts the new ones as proposed, and asks about what "
                "it cannot settle — why the change is made and which business it changes first. You "
                "answer, review every row, and apply the result to a branch.",
                badge,
            ),
            _drafts_panel(ctx),
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
                                                "Drop Markdown, text or CSV files, or a draw.io drawing, here — or click to choose",
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
            dcc.Store(id=ids.PR_CONV_STORE, data=[]),
            dcc.Store(id=ids.PR_DRAFT_STORE, data=""),
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
            # a drawing carries its icons inline, so it is taken whole up to a larger size
            cap = MAX_DRAWING_CHARS if name.lower().endswith(".drawio") else 400_000
            store[name] = base64.b64decode(b64).decode("utf-8-sig", errors="replace")[:cap]
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

    def keep(ctx: AppContext, result: ProposalResult, conversation, branch, draft_id) -> str:
        """The draft kept between sittings, when the role may propose; its identifier."""
        if not ctx.can("propose"):
            return draft_id or ""
        on = branch if branch and branch != NEW_OPTION else ""
        try:
            return ctx.proposals.save_draft(result, conversation, ctx.actor, on, draft_id or "").proposal_id
        except PermissionError:  # another architect's: this sitting becomes a draft of its own
            return ctx.proposals.save_draft(result, conversation, ctx.actor, on).proposal_id

    @app.callback(
        Output(ids.PR_RESULT, "children"),
        Output(ids.PR_RESULT_STORE, "data"),
        Output(ids.PR_CONV_STORE, "data"),
        Output(ids.PR_DRAFT_STORE, "data"),
        Output(ids.PR_DRAFTS, "children"),
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
            return (no_update,) * 5
        ctx = get_context()
        on = _matched_on(branch)
        sources, problems = _sources(text, files, links)
        if sources:
            result, conversation = ctx.proposals.start(sources, on, template_key)
        else:
            result, conversation = ctx.proposals.resolve(ProposalResult(provider="manual"), on), []
        if not result.work_package and _wp_choice(wp, wp_new):
            result.work_package = _wp_choice(wp, wp_new)
            result = ctx.proposals.resolve(result, on)
        # what the assistant says reads the draft as it now stands
        conversation = [t for t in conversation if t.get("role") != "assistant"] + [
            {
                "role": "assistant",
                "kind": "reply",
                "text": ctx.proposals.summary(result),
                "questions": [q["qid"] for q in shown(result.questions)],
            }
        ]
        draft_id = keep(ctx, result, conversation, branch, "")
        head = alert("Some links could not be read: " + "; ".join(problems), "red") if problems else None
        return (
            html.Div([head, _preview(ctx, result, conversation)]),
            _stored(result),
            conversation,
            draft_id,
            _drafts_panel(ctx).children,
        )

    @app.callback(
        Output({"type": ids.PR_Q_CHOICE, "qid": MATCH}, "data"),
        Output({"type": ids.PR_Q_CHOICE, "qid": MATCH}, "style"),
        Output({"type": ids.PR_Q_CHOICE, "qid": MATCH}, "label"),
        Output({"type": ids.PR_Q_CHOICE, "qid": MATCH}, "value"),
        Output({"type": ids.PR_Q_TEXT, "qid": MATCH}, "style"),
        Output({"type": ids.PR_Q_TEXT, "qid": MATCH}, "label"),
        Output({"type": ids.PR_Q_TEXT, "qid": MATCH}, "placeholder"),
        Input({"type": ids.PR_Q_OPT, "qid": MATCH}, "value"),
        State({"type": ids.PR_Q_DATA, "qid": MATCH}, "data"),
    )
    def what_a_choice_needs(key, options):
        """The second pick and the words a choice needs, shown only when it needs them."""
        hidden = {"display": "none"}
        o = next((x for x in options or [] if x.get("key") == key), None)
        if o is None:
            return [], hidden, "", None, hidden, "", ""
        choices = [{"value": c["key"], "label": c["label"]} for c in o.get("choices") or []]
        choice_label = "Type" if o["key"] == "new" else "Relationship"
        text_label = {
            "text": "Your answer",
            "name": "Name",
            "url": "The page that describes it",
        }.get(o.get("needs") or "", "")
        return (
            choices,
            {} if choices else hidden,
            choice_label,
            choices[0]["value"] if len(choices) == 1 else None,
            {} if o.get("needs") else hidden,
            text_label,
            o.get("hint") or ("https://…" if o.get("needs") == "url" else ""),
        )

    @app.callback(
        Output(ids.PR_RESULT, "children", allow_duplicate=True),
        Output(ids.PR_RESULT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_CONV_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFTS, "children", allow_duplicate=True),
        Input({"type": ids.PR_Q_SEND, "qid": ALL}, "n_clicks"),
        Input(ids.PR_SEND, "n_clicks"),
        State({"type": ids.PR_Q_OPT, "qid": ALL}, "value"),
        State({"type": ids.PR_Q_CHOICE, "qid": ALL}, "value"),
        State({"type": ids.PR_Q_TEXT, "qid": ALL}, "value"),
        State(ids.PR_MESSAGE, "value"),
        State(ids.PR_EL_GRID, "virtualRowData"),
        State(ids.PR_EL_GRID, "rowData"),
        State(ids.PR_EL_GRID, "selectedRows"),
        State(ids.PR_REL_GRID, "virtualRowData"),
        State(ids.PR_REL_GRID, "rowData"),
        State(ids.PR_REL_GRID, "selectedRows"),
        State(ids.PR_RESULT_STORE, "data"),
        State(ids.PR_CONV_STORE, "data"),
        State(ids.PR_DRAFT_STORE, "data"),
        State(ids.PR_BRANCH, "value"),
        State(ids.PR_WP, "value"),
        State(ids.PR_WP_NEW, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.PR_SEND, "loading"), True, False)],
    )
    def converse(
        sends, send, picked, second, words, message, el_v, el_rows, el_sel, rel_v, rel_rows, rel_sel,
        stored, conversation, draft_id, branch, wp, wp_new,
    ):  # fmt: skip
        trig = dash_ctx.triggered_id
        if not dash_ctx.triggered or not dash_ctx.triggered[0].get("value"):
            return (no_update,) * 5
        ctx = get_context()
        answers: list[dict[str, str]] = []
        text = ""
        if isinstance(trig, dict) and trig.get("type") == ids.PR_Q_SEND:
            qid = trig["qid"]

            def value_of(kind: str):
                for group in dash_ctx.states_list:
                    for item in group if isinstance(group, list) else []:
                        if item["id"].get("type") == kind and item["id"].get("qid") == qid:
                            return item.get("value")
                return None

            key = value_of(ids.PR_Q_OPT)
            if not key:
                return (no_update,) * 5
            answers.append(
                {
                    "qid": qid,
                    "key": "" if key == WORDS else key,
                    "choice": value_of(ids.PR_Q_CHOICE) or "",
                    "text": value_of(ids.PR_Q_TEXT) or "",
                }
            )
        elif trig == ids.PR_SEND:
            text = (message or "").strip()
            if not text:
                return (no_update,) * 5
        result = _result_from_page(
            ctx, el_v or el_rows, el_sel, rel_v or rel_rows, rel_sel, stored, wp, wp_new, branch
        )
        result, conversation = ctx.proposals.turn(
            result, conversation or [], answers, text, ctx.actor, _matched_on(branch)
        )
        draft_id = keep(ctx, result, conversation, branch, draft_id)
        return (
            _preview(ctx, result, conversation),
            _stored(result),
            conversation,
            draft_id,
            _drafts_panel(ctx).children,
        )

    @app.callback(
        Output(ids.PR_RESULT, "children", allow_duplicate=True),
        Output(ids.PR_RESULT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_CONV_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFTS, "children", allow_duplicate=True),
        Output(ids.PR_BRANCH, "value", allow_duplicate=True),
        Input({"type": ids.PR_DRAFT_RESUME, "id": ALL}, "n_clicks"),
        Input({"type": ids.PR_DRAFT_DISCARD, "id": ALL}, "n_clicks"),
        State(ids.PR_DRAFT_STORE, "data"),
        prevent_initial_call=True,
    )
    def drafts(resumes, discards, current):
        trig = dash_ctx.triggered_id
        if not isinstance(trig, dict) or not dash_ctx.triggered[0].get("value"):
            return (no_update,) * 6
        ctx = get_context()
        pid = trig["id"]
        if trig.get("type") == ids.PR_DRAFT_DISCARD:
            try:
                ctx.proposals.discard_draft(pid, ctx.actor)
            except (PermissionError, ValueError, Forbidden):
                return (no_update,) * 6
            cleared = pid == current
            return (
                html.Div() if cleared else no_update,
                None if cleared else no_update,
                [] if cleared else no_update,
                "" if cleared else no_update,
                _drafts_panel(ctx).children,
                no_update,
            )
        d = ctx.proposals.draft(pid)
        if d is None:
            return (no_update,) * 6
        open_ids = {b.branch_id for b in ctx.branches.open()}
        branch = d.branch_id if d.branch_id in open_ids else None
        result = ctx.proposals.resolve(
            result_from_payload(
                d.result, (d.result or {}).get("provider") or "manual", (d.result or {}).get("model") or ""
            ),
            branch or MAIN,
        )
        return (
            _preview(ctx, result, d.conversation),
            _stored(result),
            d.conversation,
            d.proposal_id,
            no_update,
            branch,
        )

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
        Output(ids.PR_RESULT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFT_STORE, "data", allow_duplicate=True),
        Output(ids.PR_DRAFTS, "children", allow_duplicate=True),
        Input(ids.PR_ANALYSE + "-again", "n_clicks"),
        Input(ids.PR_APPLY, "n_clicks"),
        State(ids.PR_EL_GRID, "virtualRowData"),
        State(ids.PR_EL_GRID, "rowData"),
        State(ids.PR_EL_GRID, "selectedRows"),
        State(ids.PR_REL_GRID, "virtualRowData"),
        State(ids.PR_REL_GRID, "rowData"),
        State(ids.PR_REL_GRID, "selectedRows"),
        State(ids.PR_RESULT_STORE, "data"),
        State(ids.PR_CONV_STORE, "data"),
        State(ids.PR_DRAFT_STORE, "data"),
        State(ids.PR_BRANCH, "value"),
        State(ids.PR_BRANCH_NEW, "value"),
        State(ids.PR_WP, "value"),
        State(ids.PR_WP_NEW, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.PR_APPLY, "loading"), True, False)],
    )
    def recheck_or_apply(
        n_check, n_apply, el_v, el_rows, el_sel, rel_v, rel_rows, rel_sel, stored, conversation,
        draft_id, branch, branch_new, wp, wp_new,
    ):  # fmt: skip
        trig = dash_ctx.triggered_id
        ctx = get_context()
        conversation = conversation or []
        result = _result_from_page(
            ctx, el_v or el_rows, el_sel, rel_v or rel_rows, rel_sel, stored, wp, wp_new, branch
        )
        if trig == ids.PR_ANALYSE + "-again":
            if not n_check:
                return (no_update,) * 6
            draft_id = keep(ctx, result, conversation, branch, draft_id)
            return (
                _preview(ctx, result, conversation),
                no_update,
                no_update,
                _stored(result),
                draft_id,
                _drafts_panel(ctx).children,
            )
        if not n_apply:
            return (no_update,) * 6
        if result.pushback:
            return (
                _preview(ctx, result, conversation),
                alert("Not applied: see what is missing above.", "yellow"),
                no_update,
                _stored(result),
                no_update,
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
            # the draft as it stands now, so the applied proposal carries the whole conversation
            draft_id = keep(ctx, result, conversation, b.branch_id, draft_id)
            out = ctx.proposals.apply(result, b.branch_id, ctx.actor, draft_id=draft_id)
        except (ValidationError, ConflictError, NotFoundError, ValueError, Forbidden) as exc:
            msg = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
            return no_update, alert(f"Not applied: {msg}", "red"), no_update, no_update, no_update, no_update
        ctx.graph.invalidate()
        summary = html.Div(
            [
                dmc.Text(
                    f"Applied to branch {b.name}: {len(out['created'])} element(s) created as proposed, {len(out['linked'])} linked, "
                    f"{len(out['relationships'])} relationship(s) written"
                    + (f", {len(out['retired'])} marked for decommissioning" if out.get("retired") else "")
                    + (
                        f", {len(out['referenced'])} part(s) linked from their system"
                        if out.get("referenced")
                        else ""
                    )
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
        return (
            no_update,
            alert(summary, "green"),
            ctx.branch_options(),
            no_update,
            "",
            _drafts_panel(ctx).children,
        )
