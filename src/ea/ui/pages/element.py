"""Element page: overview, edit, relationships, neighbourhood graph, history."""

from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.models import (
    CURRENT_STATES,
    TARGET_STATES,
    ConflictError,
    Forbidden,
    Link,
    NotFoundError,
    ValidationError,
)
from ea.services.target import CURRENT_STYLE, TARGET_STYLE, state_label
from ea.ui import graph as gp
from ea.ui import ids
from ea.ui.components import (
    alert,
    element_anchor,
    icon,
    keep_selected_option,
    kv_table,
    markdown,
    markdown_editor,
    mermaid_block,
    simple_table,
    status_badge,
    type_badge,
    view_toolbar,
)
from ea.ui.context import AppContext, get_context
from ea.ui.pages.target import current_badge, target_badge
from ea.views import view_from_neighbourhood
from ea.views.drawio import to_drawio
from ea.views.mermaid import to_markdown, to_mermaid

STATUS_OPTIONS = ["draft", "approved", "retired"]
CURRENT_OPTIONS = [{"value": s, "label": state_label(s, CURRENT_STYLE)} for s in CURRENT_STATES]
TARGET_OPTIONS = [
    {"value": s, "label": f"{TARGET_STYLE[s]['glyph']} {TARGET_STYLE[s]['label']}"} for s in TARGET_STATES
]


def _attr_input(a, value: Any):
    aid = {"type": ids.EL_ATTR, "name": a.name}
    label = a.label + (" (restricted)" if a.sensitivity else "")
    if a.type == "boolean":
        v = None if value in (None, "") else ("true" if value else "false")
        return dmc.Select(
            id=aid,
            label=label,
            data=[{"value": "true", "label": "yes"}, {"value": "false", "label": "no"}],
            value=v,
            clearable=True,
        )
    if a.enum:
        return dmc.Select(
            id=aid,
            label=label,
            data=list(a.enum),
            value=value if value in a.enum else None,
            clearable=True,
            searchable=True,
        )
    if a.type in ("integer", "number"):
        return dmc.NumberInput(id=aid, label=label, value=value, allowDecimal=a.type == "number")
    if a.type == "text":
        return dmc.Textarea(id=aid, label=label, value=value or "", autosize=True, minRows=2)
    return dmc.TextInput(
        id=aid, label=label, value="" if value is None else str(value), description=a.description or None
    )


def _rel_tab_label(ctx: AppContext, element_id: str) -> str:
    """What the Relationships tab says, so the label and the tables are written together."""
    d = ctx.repo.element_detail(element_id)
    return f"Relationships ({len(d['outgoing']) + len(d['incoming'])})"


def _rel_tables(ctx: AppContext, element_id: str) -> html.Div:
    d = ctx.repo.element_detail(element_id)

    def rows(items, incoming: bool):
        out = []
        for r in items:
            rel = r["relationship"]
            o = r["other"]
            q = f" ({rel.qualifier})" if rel.qualifier else ""
            out.append(
                [
                    dmc.Text(r["label"] + q, size="sm"),
                    element_anchor(o) if o else dmc.Text(rel.src_id if incoming else rel.dst_id, size="sm"),
                    type_badge(ctx.registry, o.type_id, "xs") if o else "",
                    dmc.Badge(rel.origin or "", size="xs", variant="outline", color="gray"),
                    dmc.ActionIcon(
                        icon("tabler:trash", 14),
                        id={"type": ids.EL_REL_DELETE, "id": rel.relationship_id},
                        variant="subtle",
                        color="red",
                        size="sm",
                    ),
                ]
            )
        return out

    out_rows, in_rows = rows(d["outgoing"], False), rows(d["incoming"], True)
    return html.Div(
        [
            dmc.Title("Outgoing", order=2, size="h5", mt="sm"),
            simple_table(["relationship", "to", "type", "origin", ""], out_rows)
            if out_rows
            else dmc.Text("None.", c="dimmed", size="sm"),
            dmc.Title("Incoming", order=2, size="h5", mt="md"),
            simple_table(["relationship", "from", "type", "origin", ""], in_rows)
            if in_rows
            else dmc.Text("None.", c="dimmed", size="sm"),
        ]
    )


def _history_table(ctx: AppContext, element_id: str):
    rows = ctx.repo.history(element_id, 50)
    if not rows:
        return dmc.Text("No changes recorded.", c="dimmed", size="sm")
    return simple_table(
        ["when", "who", "op", "version"],
        [[str(r["changed_at"])[:19], r["actor"], r["op"], r["version"]] for r in rows],
    )


def _state_card(ctx: AppContext, e) -> dmc.Paper:
    wp = ctx.backend.get_element(e.target_work_package) if e.target_work_package else None
    return dmc.Paper(
        [
            dmc.Title("State", order=2, size="h5", mb="xs"),
            kv_table(
                [
                    ("Current state", current_badge(e.current_state)),
                    ("Target state", target_badge(e.target_state)),
                    (
                        "Work package",
                        dmc.Anchor(wp.name, href=f"/target?wp={wp.element_id}", size="sm")
                        if wp
                        else dmc.Text(e.target_work_package or "—", size="sm", c="dimmed"),
                    ),
                    ("Note", dmc.Text(e.target_note or "—", size="sm")),
                ]
            ),
            dmc.Text(
                "What is true today against what the organisation intends; edit both on the Edit tab, analyse per work package on the Target state page.",
                size="xs",
                c="dimmed",
                mt="xs",
            ),
        ],
        p="md",
        withBorder=True,
    )


def render(ctx: AppContext, element_id: str) -> html.Div:
    try:
        d = ctx.repo.element_detail(element_id)
    except NotFoundError:
        return html.Div(
            [
                dmc.Title("Not found", order=1, size="h2"),
                dmc.Text(f"No element with id {element_id}."),
                dmc.Text(
                    "It may have been renamed or removed, or the identifier may belong to a "
                    "branch you are not on.",
                    c="dimmed",
                    size="sm",
                    mt="xs",
                ),
                dmc.Group(
                    [
                        dmc.Anchor("Search the model", href="/browse", size="sm"),
                        dmc.Anchor("Home", href="/", size="sm"),
                    ],
                    gap="md",
                    mt="sm",
                ),
            ]
        )
    e, t = d["element"], d["type"]
    can_write = ctx.can("edit_content") and (ctx.on_branch() or ctx.can("edit_main"))
    attrs = ctx.registry.attributes_for(e.type_id)
    own = [a for a in attrs if a.type_id == e.type_id or (a.type_id and a.type_id != e.type_id)]
    common = [a for a in attrs if a.type_id is None]
    shown_attrs = [(a.label, e.attrs.get(a.name)) for a in attrs if e.attrs.get(a.name) not in (None, "")]
    extra_attrs = [(k, v) for k, v in e.attrs.items() if k not in {a.name for a in attrs}]
    header = dmc.Group(
        [
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            # The element is what this page is about, so its name is the
                            # document title. Everything below it is a section.
                            dmc.Title(e.name, order=1, size="h2"),
                            type_badge(ctx.registry, e.type_id),
                            status_badge(e.status),
                            current_badge(e.current_state),
                            target_badge(e.target_state) if e.target_state != "undecided" else None,
                        ],
                        gap="sm",
                    ),
                    dmc.Group(
                        [
                            dmc.Code(e.element_id),
                            dmc.Text(f"key {e.key}", size="sm", c="dimmed")
                            if e.key and e.key != e.element_id
                            else None,
                            dmc.Text(f"source {e.source_system}", size="sm", c="dimmed")
                            if e.source_system
                            else None,
                            dmc.Text(f"v{e.version}", size="sm", c="dimmed"),
                        ],
                        gap="sm",
                    ),
                ],
                gap=4,
            ),
            dmc.Anchor(
                dmc.Button("Impact", variant="light", leftSection=icon("tabler:radar")),
                href=f"/impact?element={e.element_id}",
                underline="never",
            ),
        ],
        justify="space-between",
        align="flex-start",
        mb="md",
    )
    overview = dmc.SimpleGrid(
        [
            dmc.Paper(
                [
                    dmc.Title("Description", order=2, size="h5", mb="xs"),
                    markdown(e.description_md, f"el-desc-{e.element_id}"),
                ],
                p="md",
                withBorder=True,
            ),
            dmc.Paper(
                [
                    dmc.Title("Attributes", order=2, size="h5", mb="xs"),
                    kv_table(shown_attrs + extra_attrs)
                    if (shown_attrs or extra_attrs)
                    else dmc.Text("No attributes set.", c="dimmed", size="sm"),
                    dmc.Title("Links", order=2, size="h5", mt="md", mb="xs"),
                    dmc.Stack(
                        [
                            dmc.Anchor(ln.label or ln.url, href=ln.url, target="_blank", size="sm")
                            for ln in e.links
                        ],
                        gap=4,
                    )
                    if e.links
                    else dmc.Text("No links.", c="dimmed", size="sm"),
                    dmc.Title("Type", order=2, size="h5", mt="md", mb="xs"),
                    dmc.Text(t.description if t else "", size="sm", c="dimmed"),
                ],
                p="md",
                withBorder=True,
            ),
            _state_card(ctx, e),
        ],
        cols={"base": 1, "md": 2},
        spacing="md",
    )
    edit = dmc.Paper(
        dmc.Stack(
            [
                dmc.SimpleGrid(
                    [
                        dmc.TextInput(id=ids.EL_NAME, label="Name", value=e.name, required=True),
                        dmc.TextInput(id=ids.EL_KEY, label="Key", value=e.key),
                        dmc.Select(id=ids.EL_STATUS, label="Status", data=STATUS_OPTIONS, value=e.status),
                    ],
                    cols={"base": 1, "md": 3},
                ),
                markdown_editor(ids.EL_DESC, "Description (Markdown)", value=e.description_md, min_rows=6),
                dmc.Textarea(
                    id=ids.EL_LINKS,
                    label="Links (one per line, optionally `url | label`)",
                    value="\n".join(f"{ln.url} | {ln.label}" if ln.label else ln.url for ln in e.links),
                    autosize=True,
                    minRows=2,
                ),
                dmc.Title("State", order=2, size="h5"),
                dmc.SimpleGrid(
                    [
                        dmc.Select(
                            id=ids.EL_CURRENT_STATE,
                            label="Current state",
                            data=CURRENT_OPTIONS,
                            value=e.current_state,
                            allowDeselect=False,
                        ),
                        dmc.Select(
                            id=ids.EL_TARGET_STATE,
                            label="Target state",
                            data=TARGET_OPTIONS,
                            value=e.target_state,
                            allowDeselect=False,
                        ),
                        dmc.Select(
                            id=ids.EL_TARGET_WP,
                            label="Work package",
                            data=ctx.work_package_options(),
                            value=e.target_work_package or None,
                            searchable=True,
                            clearable=True,
                            placeholder="None",
                        ),
                        dmc.TextInput(
                            id=ids.EL_TARGET_NOTE,
                            label="Target note",
                            value=e.target_note,
                            placeholder="Why, and into what for merge",
                        ),
                    ],
                    cols={"base": 1, "md": 4},
                ),
                dmc.Title("Type attributes", order=2, size="h5") if own else None,
                dmc.SimpleGrid([_attr_input(a, e.attrs.get(a.name)) for a in own], cols={"base": 1, "md": 3})
                if own
                else None,
                dmc.Accordion(
                    [
                        dmc.AccordionItem(
                            [
                                dmc.AccordionControl("Common attributes"),
                                dmc.AccordionPanel(
                                    dmc.SimpleGrid(
                                        [_attr_input(a, e.attrs.get(a.name)) for a in common],
                                        cols={"base": 1, "md": 3},
                                    )
                                ),
                            ],
                            value="common",
                        )
                    ],
                    variant="separated",
                ),
                html.Div(id=ids.EL_SAVE_FEEDBACK),
                dmc.Group(
                    [
                        dmc.Text(
                            "Switch to a branch in the header to edit."
                            if ctx.can("edit_content") and not can_write
                            else f"A {ctx.role_label()} may not edit."
                            if not can_write
                            else "",
                            size="xs",
                            c="dimmed",
                        ),
                        dmc.Button(
                            "Save",
                            id=ids.EL_SAVE,
                            leftSection=icon("tabler:device-floppy"),
                            disabled=not can_write,
                        ),
                    ],
                    justify="flex-end",
                ),
            ]
        ),
        p="md",
        withBorder=True,
    )
    relationships = dmc.Stack(
        [
            dmc.Paper(
                dmc.Stack(
                    [
                        dmc.Title("Add a relationship", order=2, size="h5"),
                        dmc.Group(
                            [
                                dmc.SegmentedControl(
                                    id=ids.EL_REL_DIRECTION,
                                    data=[
                                        {"value": "out", "label": "this element →"},
                                        {"value": "in", "label": "→ this element"},
                                    ],
                                    value="out",
                                ),
                                dmc.Select(
                                    id=ids.EL_REL_OTHER,
                                    placeholder="Search the other element…",
                                    searchable=True,
                                    data=[
                                        {
                                            "value": o.element_id,
                                            "label": f"{o.name} [{o.element_id}]",
                                        }
                                        for o in ctx.repo.search(limit=50)
                                        if o.element_id != element_id
                                    ],
                                    w=380,
                                    nothingFoundMessage="Type to search",
                                ),
                                dmc.Select(
                                    id=ids.EL_REL_TYPE,
                                    placeholder="Relationship",
                                    data=[
                                        {
                                            "value": r.id,
                                            "label": f"{r.name}  (→ {ctx.registry.types[r.target].name if r.target in ctx.registry.types else r.target})",
                                        }
                                        for r in ctx.registry.rel_types_for_type(e.type_id)[0]
                                    ],
                                    w=300,
                                    searchable=True,
                                ),
                                dmc.Select(
                                    id=ids.EL_REL_QUALIFIER,
                                    placeholder="Qualifier",
                                    data=[],
                                    w=180,
                                    clearable=True,
                                    disabled=True,
                                ),
                                dmc.Button(
                                    "Add",
                                    id=ids.EL_REL_ADD,
                                    leftSection=icon("tabler:link-plus"),
                                    disabled=not can_write,
                                ),
                            ],
                            gap="sm",
                            align="flex-end",
                        ),
                        html.Div(id=ids.EL_REL_FEEDBACK),
                    ]
                ),
                p="md",
                withBorder=True,
            ),
            html.Div(_rel_tables(ctx, element_id), id=ids.EL_REL_TABLES),
        ]
    )
    graph = dmc.Paper(
        [
            dmc.Group(
                [
                    dmc.Text("Depth", size="sm"),
                    dmc.Slider(
                        id=ids.EL_GRAPH_DEPTH,
                        min=1,
                        max=3,
                        step=1,
                        value=1,
                        w=200,
                        marks=[
                            {"value": 1, "label": "1"},
                            {"value": 2, "label": "2"},
                            {"value": 3, "label": "3"},
                        ],
                    ),
                ],
                gap="md",
                mb="sm",
            ),
            gp.graph_panel(
                "el",
                ctx.registry,
                gp.raw_from_subgraph(ctx.registry, ctx.graph.neighbours(element_id, 1)),
                height="70vh",
            ),
            dmc.Divider(my="md", label="Architecture view (generated from the model)", labelPosition="left"),
            mermaid_block(
                "el-view", to_mermaid(view_from_neighbourhood(ctx.registry, ctx.graph, element_id, 1))
            ),
            view_toolbar(
                ids.EL_VIEW_MD,
                ids.EL_VIEW_DRAWIO,
                "Every shape is an element of the model; the draw.io file is a draft to reuse, not a store.",
            ),
            dmc.Text("Tap a node to open it.", size="xs", c="dimmed"),
        ],
        p="md",
        withBorder=True,
    )
    return html.Div(
        [
            dcc.Store(id=ids.EL_ID, data=element_id),
            dcc.Store(id=ids.EL_VERSION, data=e.version),
            header,
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            dmc.TabsTab("Overview", value="overview", leftSection=icon("tabler:eye")),
                            dmc.TabsTab("Edit", value="edit", leftSection=icon("tabler:pencil")),
                            dmc.TabsTab(
                                html.Span(
                                    f"Relationships ({len(d['outgoing']) + len(d['incoming'])})",
                                    id=ids.EL_REL_COUNT,
                                ),
                                value="rels",
                                leftSection=icon("tabler:arrows-exchange"),
                            ),
                            dmc.TabsTab("Graph", value="graph", leftSection=icon("tabler:topology-star")),
                            dmc.TabsTab("History", value="history", leftSection=icon("tabler:history")),
                        ]
                    ),
                    dmc.TabsPanel(overview, value="overview", pt="md"),
                    dmc.TabsPanel(edit, value="edit", pt="md"),
                    dmc.TabsPanel(relationships, value="rels", pt="md"),
                    dmc.TabsPanel(graph, value="graph", pt="md"),
                    dmc.TabsPanel(
                        html.Div(_history_table(ctx, element_id), id=ids.EL_HISTORY), value="history", pt="md"
                    ),
                ],
                id=ids.EL_TABS,
                value="overview",
            ),
        ]
    )


def _parse_links(element_id: str, text: str) -> list[Link]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        url, _, label = line.partition("|")
        out.append(Link(element_id, url.strip(), label.strip()))
    return out


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.EL_SAVE_FEEDBACK, "children"),
        Output(ids.EL_VERSION, "data"),
        Output(ids.EL_HISTORY, "children"),
        Input(ids.EL_SAVE, "n_clicks"),
        State(ids.EL_ID, "data"),
        State(ids.EL_VERSION, "data"),
        State(ids.EL_NAME, "value"),
        State(ids.EL_KEY, "value"),
        State(ids.EL_STATUS, "value"),
        State({"type": ids.MD_TEXT, "id": ids.EL_DESC}, "value"),
        State(ids.EL_LINKS, "value"),
        State(ids.EL_CURRENT_STATE, "value"),
        State(ids.EL_TARGET_STATE, "value"),
        State(ids.EL_TARGET_WP, "value"),
        State(ids.EL_TARGET_NOTE, "value"),
        State({"type": ids.EL_ATTR, "name": ALL}, "value"),
        State({"type": ids.EL_ATTR, "name": ALL}, "id"),
        prevent_initial_call=True,
        running=[(Output(ids.EL_SAVE, "loading"), True, False)],
    )
    def save(
        n,
        element_id,
        version,
        name,
        key,
        status,
        desc,
        links_text,
        current_state,
        target_state,
        target_wp,
        target_note,
        attr_values,
        attr_ids,
    ):
        if not n:
            return no_update, no_update, no_update
        ctx = get_context()
        attrs = {}
        for aid, v in zip(attr_ids, attr_values, strict=True):
            if v in (None, ""):
                continue
            attrs[aid["name"]] = {"true": True, "false": False}.get(v, v) if isinstance(v, str) else v
        try:
            e = ctx.repo.update_element(
                element_id,
                ctx.actor,
                int(version),
                name=name,
                key=key or "",
                status=status,
                description_md=desc or "",
                attrs=attrs,
                links=_parse_links(element_id, links_text),
                current_state=current_state or "live",
                target_state=target_state or "undecided",
                target_work_package=target_wp or "",
                target_note=target_note or "",
            )
        except ConflictError as exc:
            return (
                alert(f"Not saved: {exc}. Reload the page to see the latest version.", "red"),
                no_update,
                no_update,
            )
        except ValidationError as exc:
            return alert("; ".join(str(i) for i in exc.issues), "red"), no_update, no_update
        except Forbidden as exc:
            return alert(str(exc), "red"), no_update, no_update
        ctx.graph.invalidate()
        return alert(f"Saved version {e.version}.", "green"), e.version, _history_table(ctx, element_id)

    @app.callback(
        Output(ids.EL_REL_OTHER, "data"),
        Input(ids.EL_REL_OTHER, "searchValue"),
        State(ids.EL_ID, "data"),
        State(ids.EL_REL_OTHER, "value"),
        State(ids.EL_REL_OTHER, "data"),
        prevent_initial_call=True,
    )
    def search_other(text, element_id, value, data):
        if not text or len(text) < 2:
            return no_update
        ctx = get_context()
        rows = ctx.repo.search(text, limit=25)
        options = [
            {
                "value": e.element_id,
                "label": f"{e.name} [{e.element_id}] · {ctx.registry.types[e.type_id].name if e.type_id in ctx.registry.types else e.type_id}",
            }
            for e in rows
            if e.element_id != element_id
        ]
        # Picking an option makes the label the next search term, which matches nothing:
        # keep the list as it is rather than dropping the option the value refers to.
        if not options:
            return no_update
        return keep_selected_option(options, value, data)

    @app.callback(
        Output(ids.EL_REL_TYPE, "data"),
        Output(ids.EL_REL_QUALIFIER, "data"),
        Output(ids.EL_REL_QUALIFIER, "disabled"),
        Input(ids.EL_REL_OTHER, "value"),
        Input(ids.EL_REL_DIRECTION, "value"),
        Input(ids.EL_REL_TYPE, "value"),
        State(ids.EL_ID, "data"),
        prevent_initial_call=True,
    )
    def rel_type_options(other_id, direction, chosen, element_id):
        ctx = get_context()
        me = ctx.backend.get_element(element_id)
        if not me:
            return [], [], True
        if other_id:
            other = ctx.backend.get_element(other_id)
            if not other:
                return [], [], True
            src_t, dst_t = (me.type_id, other.type_id) if direction == "out" else (other.type_id, me.type_id)
            allowed = ctx.registry.allowed_rel_types(src_t, dst_t)
        else:
            # No other end yet: offer every relationship this element's type may take in that direction.
            outgoing, incoming = ctx.registry.rel_types_for_type(me.type_id)
            allowed = outgoing if direction == "out" else incoming
        data = [
            {
                "value": r.id,
                "label": f"{r.name}  ({ctx.registry.types[r.source].name if r.source in ctx.registry.types else r.source} → {ctx.registry.types[r.target].name if r.target in ctx.registry.types else r.target})",
            }
            for r in allowed
        ]
        rt = ctx.registry.rel_types.get(chosen or "")
        quals = list(rt.qualifiers) if rt and rt.qualifiers else []
        return data, quals, not quals

    @app.callback(
        Output(ids.EL_REL_FEEDBACK, "children"),
        Output(ids.EL_REL_TABLES, "children"),
        Output(ids.EL_REL_COUNT, "children"),
        Input(ids.EL_REL_ADD, "n_clicks"),
        Input({"type": ids.EL_REL_DELETE, "id": ALL}, "n_clicks"),
        State(ids.EL_ID, "data"),
        State(ids.EL_REL_DIRECTION, "value"),
        State(ids.EL_REL_OTHER, "value"),
        State(ids.EL_REL_TYPE, "value"),
        State(ids.EL_REL_QUALIFIER, "value"),
        prevent_initial_call=True,
    )
    def add_or_delete(n_add, n_del, element_id, direction, other_id, rel_type_id, qualifier):
        ctx = get_context()
        trig = dash_ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == ids.EL_REL_DELETE:
            if not any(n_del):
                return no_update, no_update, no_update
            try:
                ctx.repo.remove_relationship(trig["id"], ctx.actor)
            except Forbidden as exc:
                return alert(str(exc), "red"), no_update, no_update
            ctx.graph.invalidate()
            return (
                alert("Relationship removed.", "green"),
                _rel_tables(ctx, element_id),
                _rel_tab_label(ctx, element_id),
            )
        if not n_add:
            return no_update, no_update, no_update
        if not other_id or not rel_type_id:
            return alert("Choose the other element and a relationship.", "yellow"), no_update, no_update
        src, dst = (element_id, other_id) if direction == "out" else (other_id, element_id)
        try:
            ctx.repo.add_relationship(rel_type_id, src, dst, ctx.actor, qualifier or "")
        except ValidationError as exc:
            return alert("; ".join(str(i) for i in exc.issues), "red"), no_update, no_update
        except Forbidden as exc:
            return alert(str(exc), "red"), no_update, no_update
        ctx.graph.invalidate()
        return (
            alert("Relationship added.", "green"),
            _rel_tables(ctx, element_id),
            _rel_tab_label(ctx, element_id),
        )

    @app.callback(
        Output(gp.store_id("el"), "data"),
        Output({"type": ids.MERMAID_SRC, "id": "el-view"}, "children"),
        Input(ids.EL_GRAPH_DEPTH, "value"),
        Input(ids.EL_REL_TABLES, "children"),
        State(ids.EL_ID, "data"),
        prevent_initial_call=True,
    )
    def graph_depth(depth, _tables, element_id):
        ctx = get_context()
        d = int(depth or 1)
        return (
            gp.raw_from_subgraph(ctx.registry, ctx.graph.neighbours(element_id, d)),
            to_mermaid(view_from_neighbourhood(ctx.registry, ctx.graph, element_id, d)),
        )

    app.clientside_callback(
        """
        function(tab) {
          if (tab !== 'graph') { return window.dash_clientside.no_update; }
          const id = JSON.stringify({id: 'el', type: 'gp-cy'});
          setTimeout(function() {
            const el = document.getElementById(id);
            const cy = el && el._cyreg ? el._cyreg.cy : null;
            if (cy) { cy.resize(); cy.fit(undefined, 30); }
          }, 150);
          return window.dash_clientside.no_update;
        }
        """,
        Output(gp.cy_id("el"), "pan", allow_duplicate=True),
        Input(ids.EL_TABS, "value"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.EL_VIEW_MD, "n_clicks"),
        Input(ids.EL_VIEW_DRAWIO, "n_clicks"),
        State(ids.EL_ID, "data"),
        State(ids.EL_GRAPH_DEPTH, "value"),
        State({"type": ids.MERMAID_POS, "id": "el-view"}, "data"),
        prevent_initial_call=True,
    )
    def download_view(n_md, n_drawio, element_id, depth, positions):
        if not (n_md or n_drawio):
            return no_update
        ctx = get_context()
        view = view_from_neighbourhood(ctx.registry, ctx.graph, element_id, int(depth or 1))
        if dash_ctx.triggered_id == ids.EL_VIEW_DRAWIO:
            return dcc.send_string(
                to_drawio(view, ctx.base_url(), positions or None), f"{element_id}-view.drawio"
            )
        return dcc.send_string(to_markdown(view), f"{element_id}-view.md")

    @app.callback(
        Output(ids.URL, "pathname", allow_duplicate=True),
        Output(ids.URL, "search", allow_duplicate=True),
        Input(gp.cy_id("el"), "tapNodeData"),
        State(ids.EL_ID, "data"),
        prevent_initial_call=True,
    )
    def tap_node(data, element_id):
        if not data or not gp.is_element_node(data) or gp.element_id_of(data) == element_id:
            return no_update, no_update
        return f"/element/{gp.element_id_of(data)}", ""
