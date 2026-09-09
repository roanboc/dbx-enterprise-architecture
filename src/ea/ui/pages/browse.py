"""Browse: search elements word by word, open one, create one, or bulk-edit many."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.models import CURRENT_STATES, TARGET_STATES, Forbidden, ValidationError
from ea.services.health import COMPLETENESS_FACETS
from ea.ui import ids
from ea.ui.components import alert, icon, markdown_editor, modal_title, page_title
from ea.ui.context import AppContext, get_context

SELECT_COLUMN = {
    "field": "sel",
    "headerName": "",
    "checkboxSelection": True,
    "headerCheckboxSelection": True,
    "width": 46,
    "pinned": "left",
    "sortable": False,
    "filter": False,
    "resizable": False,
    "valueFormatter": {"function": "''"},
}

COLUMNS = [
    {"field": "element_id", "headerName": "id", "width": 190},
    {"field": "name", "flex": 2, "minWidth": 200},
    {"field": "type", "flex": 1, "minWidth": 150},
    {"field": "status", "width": 100},
    {"field": "current_state", "headerName": "current", "width": 110},
    {"field": "target_state", "headerName": "target", "width": 110},
    {"field": "source_system", "headerName": "source", "width": 100},
    {
        "field": "snippet",
        "headerName": "matched in",
        "flex": 2,
        "minWidth": 220,
        "tooltipField": "snippet",
        "cellClassRules": {"ea-snippet": "params.value"},
    },
]


GRID_OPTIONS = {
    "rowSelection": "multiple",
    "suppressRowClickSelection": True,
    "animateRows": False,
    "pagination": True,
    "paginationPageSize": 50,
    "tooltipShowDelay": 300,
}


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" and {parts[-1]}"


def _no_rows(ctx: AppContext, type_id, text, status, health_filter):
    """What the screen says when nothing matched, or None when something did.

    The grid's own overlay reads 'No Rows To Show', which is true of a search that missed,
    of a filter left on from an earlier one and of a repository with nothing in it alike.
    This says what was asked for, what is still narrowing the list, and the way back.
    """
    narrowing = []
    if text:
        narrowing.append(f"the words '{text}'")
    if type_id:
        t = ctx.registry.get_type(type_id)
        narrowing.append(f"the type {t.name if t else type_id}")
    if status:
        narrowing.append(f"status {status}")
    if health_filter and health_filter.get("facet"):
        narrowing.append(f"the Health filter {health_filter['facet']}")
    if not narrowing:
        return dmc.Alert(
            "There is nothing here yet. Import a directory of CSV files, or add one with New element.",
            color="gray",
            variant="light",
            withCloseButton=False,
        )
    body = f"Nothing matches {_and(narrowing)}."
    if text:
        body += " Every word has to match, and the controls above narrow the list together."
    elif len(narrowing) > 1:
        body += " The controls above narrow the list together."
    return dmc.Alert(
        dmc.Group(
            [
                dmc.Text(body, size="sm"),
                dmc.Anchor("Show all elements", href="/browse", size="sm", fw=600),
            ],
            gap="sm",
        ),
        color="gray",
        variant="light",
        withCloseButton=False,
    )


def _columns(can_write: bool) -> list[dict]:
    """The tick column is offered only to a role that can do something with a tick: a
    Reader who ticks a row — or the header box, and the whole model — has nothing to apply."""
    return ([SELECT_COLUMN] if can_write else []) + COLUMNS


FACET_LABELS = {
    "description": "without a description",
    "links": "without a link",
    "relationships": "without a relationship",
    "attributes": "with a required attribute empty",
    "target": "with an undecided target state",
    "stale": "not updated for a while",
    "never_updated": "never updated since the import",
}


def _type_options(ctx: AppContext) -> list[dict[str, str]]:
    counts = ctx.backend.count_by_type()
    opts = [{"value": "", "label": "All types"}]
    for t in ctx.registry.pack.element_types:
        n = counts.get(t.id, 0)
        if t.active or n:
            opts.append({"value": t.id, "label": f"{t.name} ({n})"})
    return opts


def _on_screen(selected: list[dict] | None, visible: list[dict] | None) -> list[dict]:
    """The ticked rows that are still in the grid.

    A tick survives the filter that takes its row away, so a reader who ticks a row, narrows
    the search past it and presses Bulk edit would change a row they can no longer see.
    """
    rows = list(selected or [])
    if visible is None:
        return rows
    on_screen = {r.get("element_id") for r in visible}
    return [r for r in rows if r.get("element_id") in on_screen]


def _days(q: dict, default: int = 90) -> int:
    """The days= an address carries. An address is typed and pasted, so it is never trusted."""
    try:
        return max(1, int((q.get("days") or [default])[0]))
    except (TypeError, ValueError):
        return default


def _unknown_type(ctx: AppContext, q: dict) -> str:
    """The element type an address names that this metamodel does not hold, if any."""
    type_id = (q.get("type") or [""])[0]
    return "" if not type_id or ctx.registry.get_type(type_id) else type_id


def _filter_note(ctx: AppContext, q: dict) -> str:
    facet = (q.get("missing") or q.get("facet") or [""])[0]
    unknown_type = _unknown_type(ctx, q)
    if not facet:
        # An address that narrows the grid to nothing has to say so, or an empty grid reads
        # as a model with nothing in it.
        return (
            f"The address asks for the element type '{unknown_type}', which this metamodel "
            "does not hold, so nothing is shown."
            if unknown_type
            else ""
        )
    label = FACET_LABELS.get(facet)
    if label is None:
        return (
            f"'{facet}' is not a filter this page knows, so nothing is shown. The link came "
            "from the Health page and may name a filter that has since been renamed."
        )
    where = ""
    if q.get("source"):
        where = f" from source {q['source'][0]}"
    if facet == "stale":
        label = f"not updated for {_days(q)} days or more"
    return f"Showing only the elements {label}{where} (from the Health page)."


def render(ctx: AppContext, search: str | None = None) -> html.Div:
    q = parse_qs((search or "").lstrip("?"))
    preset_type = (q.get("type") or [""])[0]
    preset_text = (q.get("q") or [""])[0]
    facet = (q.get("missing") or q.get("facet") or [""])[0]
    health_filter = (
        {"facet": facet, "source": (q.get("source") or [""])[0], "days": _days(q)} if facet else None
    )
    frozen = ctx.frozen_reason()
    can_write = ctx.can("edit_content") and (ctx.on_branch() or ctx.can("edit_main")) and not frozen
    address_note = _filter_note(ctx, q)
    return html.Div(
        [
            page_title(
                "Browse",
                "Search word by word across names, identifiers, descriptions and attributes; every word must match. Click a row to open the element, tick rows to edit many at once.",
                dmc.Group(
                    [
                        dmc.Button(
                            "Bulk edit",
                            id=ids.BULK_OPEN,
                            leftSection=icon("tabler:pencil"),
                            variant="light",
                            disabled=not can_write,
                        ),
                        dmc.Button(
                            "New element",
                            id=ids.NEW_OPEN,
                            leftSection=icon("tabler:plus"),
                            variant="light",
                            disabled=not can_write,
                        ),
                    ],
                    gap="xs",
                ),
            ),
            alert(
                # The role first: it is why the buttons are off wherever the reader stands.
                # The freeze is what stops a role that could otherwise write.
                f"You are a {ctx.role_label()} on this page: browse and open, but nothing here "
                "changes the model."
                if not ctx.can("edit_content")
                else frozen
                if frozen
                else "You are on main: switch to a branch in the header to edit or bulk-edit."
                if not can_write
                else "",
                "blue",
                # It is the only thing on the screen saying why New element and Bulk edit are
                # greyed out, so closing it would leave the refusal unexplained.
                dismissible=False,
            )
            if not can_write
            else None,
            dmc.Group(
                [
                    dmc.Select(
                        id=ids.BROWSE_TYPE,
                        **{"aria-label": "Element type"},
                        data=_type_options(ctx),
                        value=preset_type,
                        w=300,
                        searchable=True,
                        clearable=False,
                    ),
                    dmc.TextInput(
                        id=ids.BROWSE_TEXT,
                        **{"aria-label": "Search the model"},
                        placeholder="Search words…",
                        leftSection=icon("tabler:search"),
                        debounce=400,
                        w=340,
                        value=preset_text,
                    ),
                    dmc.Select(
                        id=ids.BROWSE_STATUS,
                        **{"aria-label": "Status"},
                        data=[{"value": "", "label": "Any status"}, "draft", "approved", "retired"],
                        value="",
                        w=140,
                    ),
                    dmc.Text(id=ids.BROWSE_COUNT, size="sm", c="dimmed"),
                ],
                gap="sm",
                mb="xs",
            ),
            html.Div(
                dmc.Alert(
                    dmc.Group(
                        [
                            dmc.Text(address_note, size="sm"),
                            dmc.Anchor("Show all elements", href="/browse", size="sm", fw=600),
                        ],
                        gap="sm",
                    ),
                    color="yellow",
                    variant="light",
                    # Not dismissible: it is the only thing on the page saying the grid is
                    # filtered, and the filter came from an address rather than from the
                    # controls above. Closing it would leave a partial list looking whole.
                    withCloseButton=False,
                )
                if address_note
                else None,
                id=ids.BROWSE_FILTER_NOTE,
            ),
            dcc.Store(id=ids.BROWSE_SELECTED, data=health_filter),
            html.Div(id=ids.BROWSE_EMPTY),
            dag.AgGrid(
                id=ids.BROWSE_GRID,
                columnDefs=_columns(can_write),
                rowData=[],
                getRowId="params.data.element_id",
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                dashGridOptions=GRID_OPTIONS,
                className="ag-theme-alpine",
                style={"height": "68vh", "width": "100%"},
            ),
            dmc.Modal(
                id=ids.NEW_MODAL,
                title=modal_title("New element", ids.NEW_MODAL),
                # The dialog's own close button is an icon with no wording: named here, or it
                # is nothing at all to a reader who is not looking at it.
                closeButtonProps={"aria-label": "Close this dialog"},
                children=dmc.Stack(
                    [
                        dmc.Select(
                            id=ids.NEW_TYPE,
                            label="Type",
                            data=[{"value": t.id, "label": t.name} for t in ctx.registry.active_types()],
                            searchable=True,
                            required=True,
                        ),
                        dmc.TextInput(id=ids.NEW_NAME, label="Name", required=True),
                        markdown_editor(ids.NEW_DESC, "Description (Markdown)", min_rows=5),
                        html.Div(id=ids.NEW_FEEDBACK),
                        dmc.Group([dmc.Button("Create", id=ids.NEW_SAVE)], justify="flex-end"),
                    ]
                ),
            ),
            dmc.Modal(
                id=ids.BULK_MODAL,
                title=modal_title("Bulk edit the ticked elements", ids.BULK_MODAL),
                # The dialog's own close button is an icon with no wording: named here, or it
                # is nothing at all to a reader who is not looking at it.
                closeButtonProps={"aria-label": "Close this dialog"},
                size="lg",
                children=dmc.Stack(
                    [
                        dmc.Text(
                            "A field left empty is not touched. Every element is updated on its own and audited; "
                            "one that refuses the change does not stop the others.",
                            size="sm",
                            c="dimmed",
                        ),
                        dmc.SimpleGrid(
                            [
                                dmc.Select(
                                    id=ids.BULK_STATUS,
                                    label="Status",
                                    data=["draft", "approved", "retired"],
                                    clearable=True,
                                ),
                                dmc.Select(
                                    id=ids.BULK_CURRENT,
                                    label="Current state",
                                    data=list(CURRENT_STATES),
                                    clearable=True,
                                ),
                                dmc.Select(
                                    id=ids.BULK_TARGET,
                                    label="Target state",
                                    data=list(TARGET_STATES),
                                    clearable=True,
                                ),
                                dmc.Select(
                                    id=ids.BULK_WP,
                                    label="Work package",
                                    data=ctx.work_package_options(),
                                    searchable=True,
                                    clearable=True,
                                ),
                                dmc.TextInput(id=ids.BULK_NOTE, label="Target note"),
                                dmc.TextInput(id=ids.BULK_ATTR_NAME, label="Attribute", placeholder="name"),
                                dmc.TextInput(id=ids.BULK_ATTR_VALUE, label="Attribute value"),
                            ],
                            cols={"base": 1, "md": 2},
                        ),
                        html.Div(id=ids.BULK_FEEDBACK),
                        dmc.Group(
                            [
                                dmc.Button(
                                    "Apply to the ticked rows",
                                    id=ids.BULK_SAVE,
                                    leftSection=icon("tabler:pencil"),
                                )
                            ],
                            justify="flex-end",
                        ),
                    ]
                ),
            ),
        ]
    )


def _load(ctx: AppContext, type_id, text, status, health_filter):
    hits = ctx.search.search(text or None, type_id or None, status or None, limit=ctx.settings.max_rows)
    total = ctx.search.count(text or None, type_id or None, status or None)
    rows = ctx.search.rows(hits, ctx.registry)
    if health_filter and health_filter.get("facet"):
        f = health_filter
        keep = ctx.health.ids_for(
            f["facet"], type_id or None, f.get("source") or None, int(f.get("days") or 90)
        )
        rows = [r for r in rows if r["element_id"] in keep]
        total = len(rows)
    return rows, total


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.BROWSE_GRID, "rowData"),
        Output(ids.BROWSE_COUNT, "children"),
        Output(ids.BROWSE_EMPTY, "children"),
        Input(ids.BROWSE_TYPE, "value"),
        Input(ids.BROWSE_TEXT, "value"),
        Input(ids.BROWSE_STATUS, "value"),
        State(ids.BROWSE_SELECTED, "data"),
    )
    def load_rows(type_id, text, status, health_filter):
        ctx = get_context()
        rows, total = _load(ctx, type_id, text, status, health_filter)
        empty = None if rows else _no_rows(ctx, type_id, text, status, health_filter)
        return rows, f"{len(rows)} of {total}", empty

    @app.callback(
        Output(ids.URL, "pathname", allow_duplicate=True),
        Output(ids.URL, "search", allow_duplicate=True),
        Input(ids.BROWSE_GRID, "cellClicked"),
        prevent_initial_call=True,
    )
    def open_clicked(cell):
        if not cell or cell.get("colId") == "sel" or not cell.get("rowId"):
            return no_update, no_update
        return f"/element/{cell['rowId']}", ""

    @app.callback(Output(ids.NEW_MODAL, "opened"), Input(ids.NEW_OPEN, "n_clicks"), prevent_initial_call=True)
    def open_modal(n):
        return bool(n)

    @app.callback(
        Output(ids.BULK_MODAL, "opened"),
        Output(ids.BULK_FEEDBACK, "children", allow_duplicate=True),
        Input(ids.BULK_OPEN, "n_clicks"),
        State(ids.BROWSE_GRID, "selectedRows"),
        State(ids.BROWSE_GRID, "virtualRowData"),
        prevent_initial_call=True,
    )
    def open_bulk(n, selected, visible):
        if not n:
            return no_update, no_update
        selected = _on_screen(selected, visible)
        if not selected:
            # A button that does nothing when pressed reads as broken. Open it and say why
            # there is nothing to do; Save refuses for the same reason.
            return True, alert(
                "Nothing is ticked. Close this, tick the rows you want to change in the "
                "left-hand column, and open it again.",
                "yellow",
            )
        return True, dmc.Text(f"{len(selected)} element(s) ticked.", size="sm", c="dimmed")

    @app.callback(
        Output(ids.BULK_FEEDBACK, "children"),
        Output(ids.BROWSE_GRID, "rowData", allow_duplicate=True),
        Input(ids.BULK_SAVE, "n_clicks"),
        State(ids.BROWSE_GRID, "selectedRows"),
        State(ids.BROWSE_GRID, "virtualRowData"),
        State(ids.BULK_STATUS, "value"),
        State(ids.BULK_CURRENT, "value"),
        State(ids.BULK_TARGET, "value"),
        State(ids.BULK_WP, "value"),
        State(ids.BULK_NOTE, "value"),
        State(ids.BULK_ATTR_NAME, "value"),
        State(ids.BULK_ATTR_VALUE, "value"),
        State(ids.BROWSE_TYPE, "value"),
        State(ids.BROWSE_TEXT, "value"),
        State(ids.BROWSE_STATUS, "value"),
        State(ids.BROWSE_SELECTED, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.BULK_SAVE, "loading"), True, False)],
    )
    def bulk_save(
        n,
        selected,
        visible,
        status,
        current,
        target,
        wp,
        note,
        attr_name,
        attr_value,
        type_id,
        text,
        st,
        hf,
    ):
        if not n:
            return no_update, no_update
        ctx = get_context()
        ids_ = [r["element_id"] for r in _on_screen(selected, visible)]
        if not ids_:
            return alert("Tick at least one row first.", "yellow"), no_update
        fields = {
            "status": status,
            "current_state": current,
            "target_state": target,
            "target_work_package": wp,
            "target_note": note,
        }
        attribute = (attr_name.strip(), attr_value) if (attr_name or "").strip() else None
        if not any(fields.values()) and not attribute:
            return alert("Fill in at least one field.", "yellow"), no_update
        try:
            out = ctx.repo.bulk_update(ids_, ctx.actor, fields, attribute)
        except (Forbidden, ValidationError) as exc:
            msg = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
            return alert(f"Not applied: {msg}", "red"), no_update
        ctx.graph.invalidate()
        rows, _ = _load(ctx, type_id, text, st, hf)
        msg = f"Updated {len(out['updated'])} element(s)"
        if out["refused"]:
            msg += "; refused: " + "; ".join(
                f"{r['element_id']} ({r['reason'][:80]})" for r in out["refused"][:5]
            )
        return alert(msg + ".", "green" if not out["refused"] else "yellow"), rows

    @app.callback(
        Output(ids.NEW_FEEDBACK, "children"),
        Output(ids.URL, "pathname", allow_duplicate=True),
        Output(ids.URL, "search", allow_duplicate=True),
        Input(ids.NEW_SAVE, "n_clicks"),
        State(ids.NEW_TYPE, "value"),
        State(ids.NEW_NAME, "value"),
        State({"type": ids.MD_TEXT, "id": ids.NEW_DESC}, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.NEW_SAVE, "loading"), True, False)],
    )
    def create(n, type_id, name, desc):
        if not n:
            return no_update, no_update, no_update
        if not type_id or not (name or "").strip():
            return alert("Type and name are required.", "yellow"), no_update, no_update
        ctx = get_context()
        try:
            e = ctx.repo.create_element(type_id, name, ctx.actor, description_md=desc or "")
        except ValidationError as exc:
            return alert("; ".join(str(i) for i in exc.issues), "red"), no_update, no_update
        except Forbidden as exc:
            return alert(str(exc), "red"), no_update, no_update
        ctx.graph.invalidate()
        return no_update, f"/element/{e.element_id}", ""


_ = COMPLETENESS_FACETS
