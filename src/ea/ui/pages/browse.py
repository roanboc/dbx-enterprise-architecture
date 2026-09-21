"""Browse: narrow the model down to the rows you meant, open one, create one, or bulk-edit many.

Three things the page has to get right once the model is larger than a screen. The
**criteria** have to be enough to reach one row — a type and a word are not, which is why
every field an element carries is a filter here. The **count** has to be the whole result
set rather than the page, and the page has to be reachable: the store ranks and pages, so
page two is the rows after page one. And the **address** has to carry the filters, because
a search nobody can send to a colleague is a search they have to describe over the phone.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlencode

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.models import (
    CURRENT_STATES,
    ELEMENT_STATUSES,
    SORT_ORDERS,
    TARGET_STATES,
    AttributeFilter,
    ElementFilter,
    Forbidden,
    ValidationError,
)
from ea.services.health import COMPLETENESS_FACETS
from ea.ui import ids
from ea.ui.components import SELECT_COLUMN, alert, icon, markdown_editor, modal_title, page_title
from ea.ui.context import AppContext, get_context

#: What the grid can show. The first eight are on by default; the rest are there for a
#: reader who is working on states, provenance or freshness and needs them beside the name.
ALL_COLUMNS = [
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
    {"field": "key", "width": 140},
    {"field": "target_work_package", "headerName": "work package", "width": 160},
    {"field": "lifecycle_status", "headerName": "lifecycle", "width": 130},
    {"field": "updated_at", "headerName": "updated", "width": 140},
    {"field": "updated_by", "headerName": "by", "width": 120},
    {"field": "matched_in", "headerName": "matched field", "width": 140},
]
DEFAULT_COLUMNS = [
    "element_id",
    "name",
    "type",
    "status",
    "current_state",
    "target_state",
    "source_system",
    "snippet",
]
COLUMN_LABELS = {c["field"]: c.get("headerName", c["field"]) for c in ALL_COLUMNS}

#: One screenful. The store pages, so this is a page rather than a ceiling on the answer.
PAGE_SIZE = 100

GRID_OPTIONS = {
    "rowSelection": "multiple",
    "suppressRowClickSelection": True,
    "animateRows": False,
    # The store pages now, so the grid must not also page: two pagers over one page of rows
    # would disagree about which page a reader is on.
    "pagination": False,
    "tooltipShowDelay": 300,
}

SORT_LABELS = {
    "relevance": "Best match",
    "name": "Name",
    "type": "Type",
    "status": "Status",
    "updated": "Last updated",
    "created": "Created",
}

FACET_LABELS = {
    "description": "without a description",
    "links": "without a link",
    "relationships": "without a relationship",
    "attributes": "with a required attribute empty",
    "target": "with an undecided target state",
    "stale": "not updated for a while",
    "never_updated": "never updated since the import",
}


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" and {parts[-1]}"


# ----------------------------------------------------------------- the address
#: Each filter as it is written in the address, so a search can be sent to somebody. The
#: name on the left is what the address says; the attribute on the right is what it sets.
QUERY_KEYS = {
    "q": "text",
    "type": "type_ids",
    "status": "statuses",
    "current": "current_states",
    "target": "target_states",
    "wp": "work_packages",
    "source": "sources",
    "lifecycle": "lifecycle_statuses",
    "sort": "sort",
    "desc": "descending",
}
LIST_FIELDS = {
    "type_ids",
    "statuses",
    "current_states",
    "target_states",
    "work_packages",
    "sources",
    "lifecycle_statuses",
}


def _days(q: dict, default: int = 90) -> int:
    """The days= an address carries. An address is typed and pasted, so it is never trusted."""
    try:
        return max(1, int((q.get("days") or [default])[0]))
    except (TypeError, ValueError):
        return default


def _since(raw: str) -> datetime | None:
    """An ISO date in the address, or nothing. A date nobody can parse narrows nothing."""
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def filter_from_query(search: str | None) -> tuple[ElementFilter, dict]:
    """The filter an address describes, and the raw query beside it for the notes below."""
    q = parse_qs((search or "").lstrip("?"))
    kwargs: dict = {}
    for key, field in QUERY_KEYS.items():
        values = [v for v in q.get(key, []) if v != ""]
        if not values:
            continue
        if field in LIST_FIELDS:
            kwargs[field] = values
        elif field == "descending":
            kwargs[field] = values[0] in ("1", "true", "yes")
        else:
            kwargs[field] = values[0]
    if kwargs.get("sort") not in SORT_ORDERS:
        kwargs.pop("sort", None)
    name = (q.get("attr") or [""])[0]
    if name:
        kwargs["attributes"] = [AttributeFilter(name, (q.get("attrvalue") or [""])[0])]
    since = _since((q.get("since") or [""])[0])
    if since:
        kwargs["updated_since"] = since
    return ElementFilter(**kwargs), q


def query_from_filter(filt: ElementFilter, extra: dict | None = None) -> str:
    """The address a filter describes, so the controls put back what they read."""
    pairs: list[tuple[str, str]] = []
    for key, field in QUERY_KEYS.items():
        value = getattr(filt, field)
        if field in LIST_FIELDS:
            pairs += [(key, v) for v in value if v]
        elif field == "descending":
            if value:
                pairs.append((key, "1"))
        elif field == "sort":
            if value != "relevance":
                pairs.append((key, value))
        elif value:
            pairs.append((key, str(value)))
    for a in filt.attributes:
        pairs.append(("attr", a.name))
        if a.value:
            pairs.append(("attrvalue", a.value))
    if filt.updated_since:
        pairs.append(("since", filt.updated_since.date().isoformat()))
    for key, value in (extra or {}).items():
        if value:
            pairs.append((key, str(value)))
    return ("?" + urlencode(pairs)) if pairs else ""


# ----------------------------------------------------------------- what narrows
def describing(ctx: AppContext, filt: ElementFilter, facet: str = "") -> list[tuple[str, str]]:
    """Every criterion in force, as (address key, words), for the chips and the empty state."""
    out: list[tuple[str, str]] = []
    if filt.text:
        out.append(("q", f"words '{filt.text}'"))
    for key, field, label in (
        ("type", "type_ids", "type"),
        ("status", "statuses", "status"),
        ("current", "current_states", "current state"),
        ("target", "target_states", "target state"),
        ("wp", "work_packages", "work package"),
        ("source", "sources", "source"),
        ("lifecycle", "lifecycle_statuses", "lifecycle"),
    ):
        values = getattr(filt, field)
        if not values:
            continue
        if field == "type_ids":
            shown = [(ctx.registry.get_type(v).name if ctx.registry.get_type(v) else v) for v in values]
        else:
            shown = [v or "not set" for v in values]
        out.append((key, f"{label} {' or '.join(shown)}"))
    for a in filt.attributes:
        out.append(("attr", f"{a.name} {('is ' + a.value) if a.value else 'is set'}"))
    if filt.updated_since:
        out.append(("since", f"updated since {filt.updated_since.date().isoformat()}"))
    if facet:
        out.append(("missing", f"the Health filter {FACET_LABELS.get(facet, facet)}"))
    return out


def _no_rows(ctx: AppContext, filt: ElementFilter, facet: str = ""):
    """What the screen says when nothing matched, or None when something did.

    The grid's own overlay reads 'No Rows To Show', which is true of a search that missed,
    of a filter left on from an earlier one and of a repository with nothing in it alike.
    This says what was asked for, what is still narrowing the list, and the way back.
    """
    narrowing = [words for _, words in describing(ctx, filt, facet)]
    if not narrowing:
        return dmc.Alert(
            "There is nothing here yet. Import a directory of CSV files, or add one with New element.",
            color="gray",
            variant="light",
            withCloseButton=False,
        )
    body = f"Nothing matches {_and(narrowing)}."
    if filt.text:
        body += " Every word has to match, and the controls above narrow the list together."
    elif len(narrowing) > 1:
        body += " The controls above narrow the list together."
    return dmc.Alert(
        dmc.Group(
            [
                dmc.Text(body, size="sm"),
                dmc.Anchor("Clear the filters", href="/browse", size="sm", fw=600),
            ],
            gap="sm",
        ),
        color="gray",
        variant="light",
        withCloseButton=False,
    )


def _columns(can_write: bool, shown: list[str] | None) -> list[dict]:
    """The tick column is offered only to a role that can do something with a tick: a
    Reader who ticks a row — or the header box, and the whole model — has nothing to apply."""
    keep = set(shown or DEFAULT_COLUMNS)
    cols = [c for c in ALL_COLUMNS if c["field"] in keep]
    return ([SELECT_COLUMN] if can_write else []) + cols


def _type_options(ctx: AppContext) -> list[dict[str, str]]:
    counts = ctx.backend.count_by_type()
    opts = []
    for t in ctx.registry.pack.element_types:
        n = counts.get(t.id, 0)
        if t.active or n:
            opts.append({"value": t.id, "label": f"{t.name} ({n})"})
    return opts


def _value_options(ctx: AppContext, column: str) -> list[dict[str, str]]:
    """The values the rows actually hold, so a filter never offers one that matches nothing."""
    return [{"value": v, "label": v} for v in ctx.search.values(column)]


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


def _unknown_type(ctx: AppContext, filt: ElementFilter) -> str:
    """An element type the address names that this metamodel does not hold, if any."""
    for t in filt.type_ids:
        if not ctx.registry.get_type(t):
            return t
    return ""


def _filter_note(ctx: AppContext, filt: ElementFilter, q: dict) -> str:
    facet = (q.get("missing") or q.get("facet") or [""])[0]
    unknown_type = _unknown_type(ctx, filt)
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


def _chips(ctx: AppContext, filt: ElementFilter, facet: str):
    """What is narrowing the list, each one removable, so the state is never invisible."""
    parts = describing(ctx, filt, facet)
    if not parts:
        return None
    return dmc.Group(
        [dmc.Text("Narrowed by", size="xs", c="dimmed")]
        + [
            dmc.Badge(words, variant="light", color="blue", size="sm", radius="sm", tt="none")
            for _, words in parts
        ]
        + [
            dmc.Anchor(
                "clear all",
                href="/browse",
                id=ids.BROWSE_CLEAR,
                size="xs",
                fw=600,
            )
        ],
        gap="xs",
        mb="xs",
        wrap="wrap",
    )


# ----------------------------------------------------------------------- render
def render(ctx: AppContext, search: str | None = None) -> html.Div:
    filt, q = filter_from_query(search)
    facet = (q.get("missing") or q.get("facet") or [""])[0]
    health_filter = (
        {"facet": facet, "source": (q.get("source") or [""])[0], "days": _days(q)} if facet else None
    )
    frozen = ctx.frozen_reason()
    can_write = ctx.can("edit_content") and (ctx.on_branch() or ctx.can("edit_main")) and not frozen
    address_note = _filter_note(ctx, filt, q)
    attr = filt.attributes[0] if filt.attributes else AttributeFilter("")
    return html.Div(
        [
            page_title(
                "Browse",
                "Search word by word across names, identifiers, descriptions and attributes, and "
                "narrow by any field an element carries. Click a row to open the element, tick rows "
                "to edit many at once.",
                dmc.Group(
                    [
                        dmc.Button(
                            "Export CSV",
                            id=ids.BROWSE_EXPORT,
                            leftSection=icon("tabler:download"),
                            variant="subtle",
                        ),
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
            # The three criteria most searches use, on the screen; the rest a click away, so
            # the common case stays one line and the uncommon one is still reachable.
            dmc.Group(
                [
                    dmc.MultiSelect(
                        id=ids.BROWSE_TYPE,
                        **{"aria-label": "Element types"},
                        placeholder="" if filt.type_ids else "All types",
                        data=_type_options(ctx),
                        value=filt.type_ids,
                        w=250,
                        searchable=True,
                        clearable=True,
                        maxValues=20,
                    ),
                    dmc.TextInput(
                        id=ids.BROWSE_TEXT,
                        **{"aria-label": "Search the model"},
                        placeholder="Search words…",
                        leftSection=icon("tabler:search"),
                        debounce=400,
                        w=260,
                        value=filt.text,
                    ),
                    dmc.MultiSelect(
                        id=ids.BROWSE_STATUS,
                        **{"aria-label": "Status"},
                        placeholder="" if filt.statuses else "Any status",
                        data=list(ELEMENT_STATUSES),
                        value=filt.statuses,
                        w=160,
                        clearable=True,
                    ),
                    dmc.Button(
                        "More filters",
                        id=ids.BROWSE_MORE_OPEN,
                        leftSection=icon("tabler:list-search"),
                        variant="subtle",
                        size="sm",
                    ),
                    dmc.Select(
                        id=ids.BROWSE_SORT,
                        **{"aria-label": "Sort by"},
                        data=[{"value": s, "label": SORT_LABELS[s]} for s in SORT_ORDERS],
                        value=filt.sort,
                        w=140,
                    ),
                    dmc.Switch(
                        id=ids.BROWSE_DESC,
                        label="Reverse",
                        checked=filt.descending,
                        size="sm",
                    ),
                    dmc.Text(id=ids.BROWSE_COUNT, size="sm", c="dimmed"),
                ],
                gap="sm",
                mb="xs",
                align="center",
            ),
            html.Div(_chips(ctx, filt, facet), id=ids.BROWSE_CHIPS),
            dmc.Drawer(
                id=ids.BROWSE_MORE,
                title="Narrow the list",
                position="right",
                size="md",
                padding="md",
                children=dmc.Stack(
                    [
                        dmc.Text(
                            "Every control here narrows the list together with the ones above. "
                            "The address bar carries all of them, so a search can be shared.",
                            size="sm",
                            c="dimmed",
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_CURRENT,
                            label="Current state",
                            data=list(CURRENT_STATES),
                            value=filt.current_states,
                            clearable=True,
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_TARGET,
                            label="Target state",
                            data=list(TARGET_STATES),
                            value=filt.target_states,
                            clearable=True,
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_WP,
                            label="Work package",
                            data=ctx.work_package_options(),
                            value=filt.work_packages,
                            searchable=True,
                            clearable=True,
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_SOURCE,
                            label="Source system",
                            data=_value_options(ctx, "source_system"),
                            value=filt.sources,
                            searchable=True,
                            clearable=True,
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_LIFECYCLE,
                            label="Lifecycle status",
                            data=_value_options(ctx, "lifecycle_status"),
                            value=filt.lifecycle_statuses,
                            searchable=True,
                            clearable=True,
                        ),
                        dmc.Group(
                            [
                                dmc.TextInput(
                                    id=ids.BROWSE_ATTR_NAME,
                                    label="Attribute",
                                    placeholder="owner",
                                    value=attr.name,
                                    w=160,
                                ),
                                dmc.TextInput(
                                    id=ids.BROWSE_ATTR_VALUE,
                                    label="is",
                                    placeholder="anything",
                                    value=attr.value,
                                    w=180,
                                ),
                            ],
                            gap="xs",
                            align="flex-end",
                        ),
                        dmc.TextInput(
                            id=ids.BROWSE_UPDATED_SINCE,
                            label="Updated since",
                            placeholder="2026-01-31",
                            value=filt.updated_since.date().isoformat() if filt.updated_since else "",
                        ),
                        dmc.MultiSelect(
                            id=ids.BROWSE_COLUMNS,
                            label="Columns",
                            data=[{"value": f, "label": COLUMN_LABELS[f]} for f in COLUMN_LABELS],
                            value=DEFAULT_COLUMNS,
                            clearable=False,
                        ),
                    ],
                    gap="sm",
                ),
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
            dcc.Store(id=ids.BROWSE_PAGE, data=0),
            html.Div(id=ids.BROWSE_EMPTY),
            dag.AgGrid(
                id=ids.BROWSE_GRID,
                columnDefs=_columns(can_write, DEFAULT_COLUMNS),
                rowData=[],
                getRowId="params.data.element_id",
                defaultColDef={"sortable": False, "filter": True, "resizable": True},
                dashGridOptions=GRID_OPTIONS,
                className="ag-theme-alpine",
                style={"height": "64vh", "width": "100%"},
            ),
            html.Div(id=ids.BROWSE_PAGER),
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
                            data=[{"value": t.id, "label": t.name} for t in ctx.registry.concrete_types()],
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
                                    data=list(ELEMENT_STATUSES),
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
                        dmc.Checkbox(
                            id=ids.BULK_ATTR_CLEAR,
                            label="Remove that attribute instead of setting it",
                            checked=False,
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


# ------------------------------------------------------------------- the rows
def _filter_of(
    text, types, statuses, current, target, wp, source, lifecycle, attr_name, attr_value, since, sort, desc
) -> ElementFilter:
    """One filter from the controls, whichever of them a reader has touched."""
    attributes = (
        [AttributeFilter(attr_name.strip(), (attr_value or "").strip())] if (attr_name or "").strip() else []
    )
    return ElementFilter(
        text=text or "",
        type_ids=list(types or []),
        statuses=list(statuses or []),
        current_states=list(current or []),
        target_states=list(target or []),
        work_packages=list(wp or []),
        sources=list(source or []),
        lifecycle_statuses=list(lifecycle or []),
        attributes=attributes,
        updated_since=_since((since or "").strip()),
        sort=sort if sort in SORT_ORDERS else "relevance",
        descending=bool(desc),
    )


def _load(ctx: AppContext, filt: ElementFilter, health_filter, page: int = 0):
    """One page of rows, and the honest total behind it.

    The Health drill-down is a set of ids rather than a predicate the store knows, so it is
    pushed into the filter as `only_ids` — which is what makes the count right. It used to
    be applied in Python *after* the row limit, and the total then rewritten to the length
    of what survived, so the screen read 'N of N' while rows past the limit were dropped.
    """
    if health_filter and health_filter.get("facet"):
        f = health_filter
        keep = ctx.health.ids_for(
            f["facet"],
            filt.type_ids[0] if len(filt.type_ids) == 1 else None,
            f.get("source") or None,
            int(f.get("days") or 90),
        )
        filt = replace_only_ids(filt, sorted(keep))
    total = ctx.search.count(filt)
    hits = ctx.search.search(filt, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    return ctx.search.rows(hits, ctx.registry), total, filt


def replace_only_ids(filt: ElementFilter, ids_: list[str]) -> ElementFilter:
    """The same filter, narrowed to a set of ids (the filter is not mutated in place)."""
    out = ElementFilter(**{**filt.__dict__, "only_ids": ids_})
    return out


def _pager(page: int, shown: int, total: int):
    """Where the reader is in the result set, and the way to the rest of it."""
    if not total:
        return None
    first = page * PAGE_SIZE + 1
    last = page * PAGE_SIZE + shown
    pages = max(1, -(-total // PAGE_SIZE))
    return dmc.Group(
        [
            dmc.Text(f"{first}–{last} of {total}", size="sm", c="dimmed"),
            dmc.Pagination(
                id=ids.BROWSE_PAGER,
                total=pages,
                value=page + 1,
                siblings=1,
                size="sm",
            )
            if pages > 1
            else None,
        ],
        gap="md",
        mt="xs",
        justify="space-between",
    )


def register(app: dash.Dash) -> None:
    filter_states = [
        Input(ids.BROWSE_TEXT, "value"),
        Input(ids.BROWSE_TYPE, "value"),
        Input(ids.BROWSE_STATUS, "value"),
        Input(ids.BROWSE_CURRENT, "value"),
        Input(ids.BROWSE_TARGET, "value"),
        Input(ids.BROWSE_WP, "value"),
        Input(ids.BROWSE_SOURCE, "value"),
        Input(ids.BROWSE_LIFECYCLE, "value"),
        Input(ids.BROWSE_ATTR_NAME, "value"),
        Input(ids.BROWSE_ATTR_VALUE, "value"),
        Input(ids.BROWSE_UPDATED_SINCE, "value"),
        Input(ids.BROWSE_SORT, "value"),
        Input(ids.BROWSE_DESC, "checked"),
    ]

    @app.callback(
        Output(ids.BROWSE_GRID, "rowData"),
        Output(ids.BROWSE_COUNT, "children"),
        Output(ids.BROWSE_EMPTY, "children"),
        Output(ids.BROWSE_PAGER, "children"),
        Output(ids.BROWSE_CHIPS, "children"),
        *filter_states,
        Input(ids.BROWSE_PAGE, "data"),
        State(ids.BROWSE_SELECTED, "data"),
    )
    def load_rows(*values):
        ctx = get_context()
        *controls, page, health_filter = values
        filt = _filter_of(*controls)
        rows, total, _applied = _load(ctx, filt, health_filter, int(page or 0))
        facet = (health_filter or {}).get("facet", "")
        empty = None if rows else _no_rows(ctx, filt, facet)
        return (
            rows,
            f"{len(rows)} of {total}",
            empty,
            _pager(int(page or 0), len(rows), total),
            _chips(ctx, filt, facet),
        )

    @app.callback(
        Output(ids.URL, "search", allow_duplicate=True),
        *filter_states,
        State(ids.BROWSE_SELECTED, "data"),
        prevent_initial_call=True,
    )
    def keep_the_address(*values):
        """The controls write what they are showing back into the address.

        The page has always *read* the address; it never wrote to it, so a reader who
        narrowed the list by hand had nothing to send a colleague and nothing for the back
        button to return to. The Health drill-down's own keys are carried through, because
        the note above the grid is written from them.
        """
        *controls, health_filter = values
        facet = (health_filter or {}).get("facet", "")
        extra = (
            {
                "missing": facet,
                "source": (health_filter or {}).get("source"),
                "days": (health_filter or {}).get("days"),
            }
            if facet
            else {}
        )
        return query_from_filter(_filter_of(*controls), extra)

    @app.callback(
        Output(ids.BROWSE_PAGE, "data"),
        Input(ids.BROWSE_PAGER, "value"),
        *filter_states,
        prevent_initial_call=True,
    )
    def turn_the_page(page, *controls):
        # Any change to a filter puts the reader back on the first page: page four of the
        # old result set is not page four of the new one.
        from dash import ctx as dash_ctx

        if dash_ctx.triggered_id != ids.BROWSE_PAGER:
            return 0
        return max(0, int(page or 1) - 1)

    @app.callback(
        Output(ids.BROWSE_MORE, "opened"),
        Input(ids.BROWSE_MORE_OPEN, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_more(n):
        return bool(n)

    @app.callback(
        Output(ids.BROWSE_GRID, "columnDefs"),
        Input(ids.BROWSE_COLUMNS, "value"),
        prevent_initial_call=True,
    )
    def choose_columns(shown):
        ctx = get_context()
        can_write = (
            ctx.can("edit_content") and (ctx.on_branch() or ctx.can("edit_main")) and not ctx.frozen_reason()
        )
        return _columns(can_write, shown or DEFAULT_COLUMNS)

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.BROWSE_EXPORT, "n_clicks"),
        *[State(i.component_id, i.component_property) for i in filter_states],
        State(ids.BROWSE_SELECTED, "data"),
        prevent_initial_call=True,
    )
    def export_rows(n, *values):
        """The result set as CSV — the whole of it, not the page on screen.

        An architect asked for a list of applications in a work package wants the list, and
        the only export the app had was the whole model.
        """
        if not n:
            return no_update
        import csv
        import io

        ctx = get_context()
        *controls, health_filter = values
        filt = _filter_of(*controls)
        rows, total, applied = _load(ctx, filt, health_filter, 0)
        # Beyond one page, page through the rest rather than holding the model in a request.
        page = 1
        while len(rows) < total and page * PAGE_SIZE < ctx.settings.max_rows:
            more, _, _ = _load(ctx, filt, health_filter, page)
            if not more:
                break
            rows += more
            page += 1
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["element_id"])
        writer.writeheader()
        writer.writerows(rows)
        return dcc.send_string(out.getvalue(), "browse.csv")

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
        Output(ids.BROWSE_COUNT, "children", allow_duplicate=True),
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
        State(ids.BULK_ATTR_CLEAR, "checked"),
        *[State(i.component_id, i.component_property) for i in filter_states],
        State(ids.BROWSE_PAGE, "data"),
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
        attr_clear,
        *rest,
    ):
        if not n:
            return no_update, no_update, no_update
        ctx = get_context()
        *controls, page, hf = rest
        ids_ = [r["element_id"] for r in _on_screen(selected, visible)]
        if not ids_:
            return alert("Tick at least one row first.", "yellow"), no_update, no_update
        fields = {
            "status": status,
            "current_state": current,
            "target_state": target,
            "target_work_package": wp,
            "target_note": note,
        }
        attribute = (attr_name.strip(), attr_value) if (attr_name or "").strip() else None
        if not any(fields.values()) and not attribute:
            return alert("Fill in at least one field.", "yellow"), no_update, no_update
        try:
            out = ctx.repo.bulk_update(ids_, ctx.actor, fields, attribute, clear_attribute=bool(attr_clear))
        except (Forbidden, ValidationError) as exc:
            msg = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
            return alert(f"Not applied: {msg}", "red"), no_update, no_update
        ctx.graph.invalidate()
        rows, total, _ = _load(ctx, _filter_of(*controls), hf, int(page or 0))
        msg = f"Updated {len(out['updated'])} element(s)"
        if out["refused"]:
            msg += "; refused: " + "; ".join(
                f"{r['element_id']} ({r['reason'][:80]})" for r in out["refused"][:5]
            )
        # The count went stale after a bulk edit: an edit that retires rows out of the
        # current filter left the old number on the screen.
        return (
            alert(msg + ".", "green" if not out["refused"] else "yellow"),
            rows,
            f"{len(rows)} of {total}",
        )

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
