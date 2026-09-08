"""Metamodel manager: the type graph, editable type/relationship/attribute grids, YAML export and reload."""

from __future__ import annotations

from typing import Any

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import yaml
from dash import Input, Output, State, dcc, html, no_update

from ea.metamodel import Registry, load_pack, pack_to_dict
from ea.metamodel.loader import pack_from_dict
from ea.models import ANY, Forbidden
from ea.ui import graph as gp
from ea.ui import ids
from ea.ui.components import alert, icon, mermaid_block, page_title
from ea.ui.context import AppContext, get_context
from ea.views.drawio import STENCIL
from ea.views.mermaid import SHAPES, to_mermaid
from ea.views.model import LAYER_ORDER, View, ViewNode, layer_rank

TYPE_COLS = [
    {"field": "id", "editable": False, "pinned": "left", "width": 240},
    {"field": "name", "editable": True, "width": 220},
    {"field": "plural", "editable": True, "width": 200},
    {"field": "supertype", "editable": True, "width": 180},
    {"field": "domain", "editable": True, "width": 130},
    {"field": "provenance", "editable": True, "width": 120},
    {"field": "prefix", "editable": True, "width": 90},
    {"field": "active", "editable": True, "width": 90, "cellDataType": "boolean"},
    {"field": "source_of_record", "editable": True, "width": 240},
    {"field": "type_owner", "editable": True, "width": 200},
    {"field": "instance_owner", "editable": True, "width": 200},
    {
        "field": "description",
        "editable": True,
        "flex": 1,
        "minWidth": 300,
        "cellEditor": "agLargeTextCellEditor",
        "cellEditorPopup": True,
    },
    {"field": "deactivation_reason", "editable": True, "width": 260},
]
NOTATION_KEYS = ("layer", "glyph", "stereotype", "archimate", "shape")
PALETTE = [
    "gray",
    "red",
    "pink",
    "grape",
    "violet",
    "indigo",
    "blue",
    "cyan",
    "teal",
    "green",
    "lime",
    "yellow",
    "orange",
]
_SELECT = "agSelectCellEditor"
_NOTATION_EDIT_COLS = [
    {
        "field": "layer",
        "editable": True,
        "width": 130,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": [""] + LAYER_ORDER},
    },
    {"field": "glyph", "editable": True, "width": 80},
    {"field": "stereotype", "editable": True, "width": 190},
    {
        "field": "archimate",
        "editable": True,
        "width": 200,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": [""] + sorted(STENCIL) + ["Value"]},
    },
    {
        "field": "shape",
        "editable": True,
        "width": 110,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": [""] + list(SHAPES)},
    },
]
DOMAIN_NOTATION_COLS = [
    {"field": "id", "editable": False, "pinned": "left", "width": 150},
    {"field": "name", "editable": False, "width": 220},
    {
        "field": "colour",
        "editable": True,
        "width": 110,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": PALETTE},
    },
    {"field": "hex", "editable": True, "width": 100},
    *_NOTATION_EDIT_COLS,
]
TYPE_NOTATION_COLS = [
    {"field": "id", "editable": False, "pinned": "left", "width": 240},
    {"field": "name", "editable": False, "width": 220},
    {"field": "domain", "editable": False, "width": 120},
    {"field": "inherited", "editable": False, "width": 260, "headerName": "inherited (domain and supertype)"},
    *_NOTATION_EDIT_COLS,
]
REL_COLS = [
    {"field": "id", "editable": True, "pinned": "left", "width": 300},
    {"field": "name", "editable": True, "width": 200},
    {"field": "inverse", "editable": True, "width": 200},
    {"field": "source", "editable": True, "width": 220},
    {"field": "target", "editable": True, "width": 220},
    {"field": "provenance", "editable": True, "width": 110},
    {"field": "qualifiers", "editable": True, "width": 220, "headerName": "qualifiers (comma-separated)"},
    {"field": "diagrams", "editable": True, "width": 180},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 260},
]
ATTR_COLS = [
    {
        "field": "type_id",
        "editable": True,
        "pinned": "left",
        "width": 240,
        "headerName": "type (blank = common)",
    },
    {"field": "name", "editable": True, "width": 220},
    {"field": "label", "editable": True, "width": 220},
    {"field": "type", "editable": True, "width": 110},
    {"field": "required", "editable": True, "width": 100, "cellDataType": "boolean"},
    {"field": "enum", "editable": True, "width": 220, "headerName": "enum (comma-separated)"},
    {"field": "sensitivity", "editable": True, "width": 120},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 240},
]


def _type_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "plural": t.plural,
            "supertype": t.supertype or "",
            "domain": t.domain,
            "provenance": t.provenance,
            "prefix": t.prefix,
            "active": t.active,
            "source_of_record": t.source_of_record,
            "type_owner": t.type_owner,
            "instance_owner": t.instance_owner,
            "description": t.description,
            "deactivation_reason": t.deactivation_reason,
            "examples": ", ".join(t.examples),
        }
        for t in reg.pack.element_types
    ]


def _domain_notation_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "name": d.name,
            "colour": d.notation.get("colour", ""),
            "hex": d.notation.get("hex", ""),
            **{k: d.notation.get(k, "") for k in NOTATION_KEYS},
        }
        for d in reg.pack.domains
    ]


def _type_notation_rows(reg: Registry) -> list[dict[str, Any]]:
    rows = []
    for t in reg.pack.element_types:
        own = t.notation
        eff = reg.notation(t.id)
        inherited = f"{eff.get('layer', '')} · {eff.get('glyph', '')} «{eff.get('stereotype', '')}» · {eff.get('shape', '')}"
        rows.append(
            {
                "id": t.id,
                "name": t.name,
                "domain": t.domain,
                "inherited": inherited,
                **{k: own.get(k, "") for k in NOTATION_KEYS},
            }
        )
    return rows


def notation_preview(reg: Registry) -> str:
    """One sample node per active type, in its layer, drawn with the notation as it stands."""
    view = View(title="Notation preview")
    for t in reg.active_types():
        n = reg.notation(t.id)
        view.nodes.append(
            ViewNode(
                id=t.id,
                name=t.name,
                type_id=t.id,
                type_name=t.name,
                layer=n.get("layer", "other"),
                glyph=n.get("glyph", ""),
                stereotype=n.get("stereotype", ""),
                shape=n.get("shape", "rect"),
                archimate=n.get("archimate", ""),
            )
        )
    view.nodes.sort(key=lambda x: (layer_rank(x.layer), x.name))
    return to_mermaid(view, direction="LR")


def _rel_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "name": r.name,
            "inverse": r.inverse,
            "source": r.source,
            "target": r.target,
            "provenance": r.provenance,
            "qualifiers": ", ".join(r.qualifiers),
            "diagrams": ", ".join(r.diagrams),
            "description": r.description,
        }
        for r in reg.pack.relationship_types
    ]


def _attr_rows(reg: Registry) -> list[dict[str, Any]]:
    rows = [
        {
            "type_id": "",
            "name": a.name,
            "label": a.label,
            "type": a.type,
            "required": a.required,
            "enum": ", ".join(a.enum or []),
            "sensitivity": a.sensitivity,
            "description": a.description,
        }
        for a in reg.pack.common_attributes
    ]
    for t in reg.pack.element_types:
        for a in t.attributes:
            rows.append(
                {
                    "type_id": t.id,
                    "name": a.name,
                    "label": a.label,
                    "type": a.type,
                    "required": a.required,
                    "enum": ", ".join(a.enum or []),
                    "sensitivity": a.sensitivity,
                    "description": a.description,
                }
            )
    return rows


def _detail(reg: Registry, node_id: str | None):
    if not node_id or node_id == "ANY":
        return dmc.Text(
            "Tap a type to see its definition, attributes and relationships.", c="dimmed", size="sm"
        )
    t = reg.get_type(node_id)
    if t is None:
        return dmc.Text("Unknown type.", c="dimmed", size="sm")
    out_rels, in_rels = reg.rel_types_for_type(t.id)
    return dmc.Stack(
        [
            dmc.Group(
                [
                    dmc.Title(t.name, order=2, size="h4"),
                    dmc.Badge(t.domain, color="gray", variant="light", size="xs"),
                    dmc.Badge(t.provenance, variant="outline", size="xs"),
                    dmc.Badge("inactive", color="red", size="xs") if not t.active else None,
                ],
                gap="xs",
            ),
            dmc.Text(t.description, size="sm"),
            dmc.Text(f"Examples: {', '.join(t.examples)}", size="xs", c="dimmed") if t.examples else None,
            dmc.Text(f"Source of record: {t.source_of_record}", size="xs", c="dimmed")
            if t.source_of_record
            else None,
            dmc.Text(
                f"Owners: type {t.type_owner or '—'}; instances {t.instance_owner or '—'}",
                size="xs",
                c="dimmed",
            ),
            dmc.Text(
                "Attributes: "
                + (", ".join(a.name for a in reg.attributes_for(t.id) if a.type_id) or "none of its own"),
                size="xs",
            ),
            dmc.Text(
                "Outgoing: " + ("; ".join(f"{r.name} → {r.target}" for r in out_rels) or "none"), size="xs"
            ),
            dmc.Text(
                "Incoming: " + ("; ".join(f"{r.source} {r.name}" for r in in_rels) or "none"), size="xs"
            ),
        ],
        gap=4,
    )


def _reviewer_rows(ctx: AppContext) -> list[dict[str, str]]:
    assigned = ctx.reviews.assignments()
    return [
        {"type_id": t.id, "type": t.name, "reviewers": ", ".join(assigned.get(t.id, []))}
        for t in ctx.registry.pack.element_types
        if t.active
    ]


def render(ctx: AppContext) -> html.Div:
    reg = ctx.registry
    grid_kw = dict(
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "editable": True},
        className="ag-theme-alpine",
        dashGridOptions={
            "singleClickEdit": False,
            "stopEditingWhenCellsLoseFocus": True,
            "animateRows": False,
        },
        style={"height": "55vh", "width": "100%"},
    )
    return html.Div(
        [
            page_title(
                "Metamodel",
                _counts(reg),
                dmc.Group(
                    [
                        dmc.Button(
                            "Save changes",
                            id=ids.MM_SAVE,
                            leftSection=icon("tabler:device-floppy"),
                            disabled=not ctx.can("edit_metamodel"),
                        ),
                        dmc.Button(
                            "Export YAML",
                            id=ids.MM_EXPORT,
                            variant="light",
                            leftSection=icon("tabler:download"),
                        ),
                        dmc.Button(
                            "Reload from file",
                            id=ids.MM_RELOAD,
                            variant="subtle",
                            color="gray",
                            leftSection=icon("tabler:refresh"),
                        ),
                    ],
                    gap="xs",
                ),
                subtitle_id=ids.MM_SUBTITLE,
            ),
            html.Div(id=ids.MM_FEEDBACK),
            dmc.Paper(
                [
                    dmc.SimpleGrid(
                        [
                            gp.graph_panel(
                                "mm",
                                reg,
                                gp.raw_from_types(reg),
                                height="70vh",
                                group_by="domain",
                                extra_controls=[
                                    dmc.Select(
                                        id=ids.MM_DOMAIN_FILTER,
                                        **{"aria-label": "Domain"},
                                        data=[{"value": "", "label": "All domains"}]
                                        + [{"value": d.id, "label": d.name} for d in reg.pack.domains],
                                        value="",
                                        w=200,
                                        size="xs",
                                    )
                                ],
                                hint="Tap a type to see its definition, attributes and relationships. Dashed edge = sub-type; diamond = any element.",
                            ),
                            dmc.Paper(
                                html.Div(_detail(reg, None), id=ids.MM_DETAIL),
                                p="sm",
                                withBorder=True,
                                style={"height": "660px", "overflow": "auto"},
                            ),
                        ],
                        cols={"base": 1, "lg": 2},
                        spacing="sm",
                        style={"gridTemplateColumns": "2fr 1fr"},
                    ),
                ],
                p="md",
                withBorder=True,
                mb="md",
            ),
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            dmc.TabsTab("Element types", value="types"),
                            dmc.TabsTab("Relationship types", value="rels"),
                            dmc.TabsTab("Attributes", value="attrs"),
                            dmc.TabsTab("Notation", value="notation"),
                            dmc.TabsTab("Reviewers", value="reviewers"),
                        ]
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Text(
                                "Who reviews a branch that touches each element type: users or groups, comma-separated. A type with nobody assigned may be approved by any Reviewer. Only an admin saves this table.",
                                size="sm",
                                c="dimmed",
                                my="xs",
                            ),
                            dag.AgGrid(
                                id=ids.MM_REVIEWERS_GRID,
                                columnDefs=[
                                    {
                                        "field": "type_id",
                                        "headerName": "type id",
                                        "width": 260,
                                        "editable": False,
                                    },
                                    {"field": "type", "width": 240, "editable": False},
                                    {"field": "reviewers", "flex": 1, "editable": True},
                                ],
                                rowData=_reviewer_rows(ctx),
                                getRowId="params.data.type_id",
                                **grid_kw,
                            ),
                            dmc.Group(
                                [
                                    dmc.Button(
                                        "Save reviewers",
                                        id=ids.MM_REVIEWERS_SAVE,
                                        size="xs",
                                        leftSection=icon("tabler:device-floppy"),
                                        disabled=not ctx.can("assign_reviewers"),
                                    ),
                                    html.Div(id=ids.MM_REVIEWERS_FEEDBACK),
                                ],
                                my="xs",
                            ),
                        ],
                        value="reviewers",
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Text(
                                "How each domain and type is drawn in generated views and graphs. A blank cell inherits from the supertype, then the domain. The preview follows every edit; Save changes writes the pack.",
                                size="sm",
                                c="dimmed",
                                my="xs",
                            ),
                            dmc.Title("Domains", order=2, className="ea-section-title"),
                            dag.AgGrid(
                                id=ids.MM_NOTATION_DOMAINS_GRID,
                                columnDefs=DOMAIN_NOTATION_COLS,
                                rowData=_domain_notation_rows(reg),
                                getRowId="params.data.id",
                                **dict(grid_kw, style={"height": "24vh", "width": "100%"}),
                            ),
                            dmc.Title(
                                "Element types (overrides)", order=2, className="ea-section-title", mt="md"
                            ),
                            dag.AgGrid(
                                id=ids.MM_NOTATION_TYPES_GRID,
                                columnDefs=TYPE_NOTATION_COLS,
                                rowData=_type_notation_rows(reg),
                                getRowId="params.data.id",
                                **dict(grid_kw, style={"height": "40vh", "width": "100%"}),
                            ),
                            dmc.Title("Preview", order=2, className="ea-section-title", mt="md"),
                            mermaid_block(ids.MM_NOTATION_PREVIEW, notation_preview(reg)),
                        ],
                        value="notation",
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Group(
                                [
                                    dmc.Button(
                                        "Add type",
                                        id=ids.MM_ADD_TYPE,
                                        size="xs",
                                        variant="light",
                                        leftSection=icon("tabler:plus"),
                                    )
                                ],
                                my="xs",
                            ),
                            dag.AgGrid(
                                id=ids.MM_TYPES_GRID,
                                columnDefs=TYPE_COLS,
                                rowData=_type_rows(reg),
                                getRowId="params.data.id",
                                **grid_kw,
                            ),
                        ],
                        value="types",
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Group(
                                [
                                    dmc.Button(
                                        "Add relationship type",
                                        id=ids.MM_ADD_REL,
                                        size="xs",
                                        variant="light",
                                        leftSection=icon("tabler:plus"),
                                    )
                                ],
                                my="xs",
                            ),
                            dag.AgGrid(
                                id=ids.MM_RELS_GRID,
                                columnDefs=REL_COLS,
                                rowData=_rel_rows(reg),
                                getRowId="params.data.id",
                                **grid_kw,
                            ),
                        ],
                        value="rels",
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Group(
                                [
                                    dmc.Button(
                                        "Add attribute",
                                        id=ids.MM_ADD_ATTR,
                                        size="xs",
                                        variant="light",
                                        leftSection=icon("tabler:plus"),
                                    )
                                ],
                                my="xs",
                            ),
                            dag.AgGrid(
                                id=ids.MM_ATTRS_GRID, columnDefs=ATTR_COLS, rowData=_attr_rows(reg), **grid_kw
                            ),
                        ],
                        value="attrs",
                    ),
                ],
                value="types",
            ),
            dmc.Text(
                "Rows are matched by id. To retire a type, set active to false rather than deleting it, so existing content still resolves.",
                size="xs",
                c="dimmed",
                mt="xs",
            ),
        ]
    )


def _split(v: Any) -> list[str]:
    return [x.strip() for x in str(v or "").replace(";", ",").split(",") if x.strip()]


def _all_rows(virtual: list[dict] | None, rows: list[dict] | None, *key: str) -> list[dict]:
    """Every row of a grid, carrying whatever was edited in the rows on screen.

    `virtualRowData` is what the grid is showing — filtered and sorted — and it is the only
    place a cell edit appears. `rowData` is everything the grid was given. Saving from the
    first alone means a column filter decides what is written, and everything it hid is
    dropped; saving from the second alone throws away the edit that prompted the save.
    So: everything, with the rows on screen laid over it.
    """
    rows = list(rows or [])
    virtual = list(virtual or [])
    if not rows:
        return virtual
    if not virtual:
        return rows

    def identity(row: dict) -> tuple:
        return tuple(str(row.get(k, "")) for k in key)

    edited = {identity(r): r for r in virtual}
    out = [edited.pop(identity(r), r) for r in rows]
    out.extend(edited.values())  # a row added on screen is not in rowData yet
    return out


def _counts(reg: Registry) -> str:
    """What the page says it holds. A save changes it, so it is written in one place."""
    inactive = len(reg.pack.element_types) - len(reg.active_types())
    return (
        f"{reg.pack.name} — {len(reg.active_types())} active types, {inactive} inactive, "
        f"{len(reg.pack.relationship_types)} relationship types. Edit the grids and save; "
        "export the result as a pack."
    )


def _pack_from_grids(
    reg: Registry,
    types: list[dict],
    rels: list[dict],
    attrs: list[dict],
    domain_notation: list[dict] | None = None,
    type_notation: list[dict] | None = None,
) -> dict[str, Any]:
    d = pack_to_dict(reg.pack)
    if domain_notation is not None:
        by_id = {r["id"]: r for r in domain_notation if r.get("id")}
        for dom in d["domains"]:
            r = by_id.get(dom["id"])
            if r is None:
                continue
            notation = {k: str(r.get(k) or "").strip() for k in ("colour", "hex", *NOTATION_KEYS)}
            dom["notation"] = {k: v for k, v in notation.items() if v}
    notation_by_type = {
        r["id"]: {k: str(r.get(k) or "").strip() for k in NOTATION_KEYS if str(r.get(k) or "").strip()}
        for r in (type_notation or [])
        if r.get("id")
    }
    keep_notation = {t.id: dict(t.notation) for t in reg.pack.element_types}
    attr_by_type: dict[str, list[dict]] = {}
    for a in attrs:
        if not a.get("name"):
            continue
        item = {
            "name": a["name"],
            "label": a.get("label", ""),
            "type": a.get("type") or "string",
            "required": bool(a.get("required")),
            "description": a.get("description", ""),
            "sensitivity": a.get("sensitivity", ""),
        }
        if _split(a.get("enum")):
            item["enum"] = _split(a.get("enum"))
        attr_by_type.setdefault(a.get("type_id") or "", []).append(item)
    d["common_attributes"] = attr_by_type.get("", [])
    d["element_types"] = []
    for t in types:
        if not t.get("id"):
            continue
        et = {
            "id": t["id"],
            "name": t.get("name") or t["id"],
            "plural": t.get("plural", ""),
            "supertype": t.get("supertype") or None,
            "active": bool(t.get("active", True)),
            "deactivation_reason": t.get("deactivation_reason", ""),
            "domain": t.get("domain", ""),
            "provenance": t.get("provenance", ""),
            "prefix": t.get("prefix", ""),
            "description": t.get("description", ""),
            "examples": _split(t.get("examples")),
            "notation": (
                notation_by_type.get(t["id"], keep_notation.get(t["id"], {}))
                if type_notation is not None
                else keep_notation.get(t["id"], {})
            ),
            "source_of_record": t.get("source_of_record", ""),
            "type_owner": t.get("type_owner", ""),
            "instance_owner": t.get("instance_owner", ""),
            "attributes": attr_by_type.get(t["id"], []),
        }
        d["element_types"].append(et)
    d["relationship_types"] = [
        {
            "id": r["id"],
            "name": r.get("name") or r["id"],
            "inverse": r.get("inverse", ""),
            "source": r.get("source") or ANY,
            "target": r.get("target") or ANY,
            "provenance": r.get("provenance", ""),
            "qualifiers": _split(r.get("qualifiers")),
            "diagrams": _split(r.get("diagrams")),
            "description": r.get("description", ""),
        }
        for r in rels
        if r.get("id")
    ]
    return d


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.MM_REVIEWERS_FEEDBACK, "children"),
        Input(ids.MM_REVIEWERS_SAVE, "n_clicks"),
        State(ids.MM_REVIEWERS_GRID, "virtualRowData"),
        State(ids.MM_REVIEWERS_GRID, "rowData"),
        prevent_initial_call=True,
    )
    def save_reviewers(n, virtual_rows, rows):
        if not n:
            return no_update
        ctx = get_context()
        try:
            for r in _all_rows(virtual_rows, rows, "type_id"):
                ctx.reviews.set_assignment(r["type_id"], (r.get("reviewers") or "").split(","), ctx.actor)
        except Forbidden as exc:
            return alert(str(exc), "red")
        return alert("Reviewer assignments saved.", "green")

    @app.callback(
        Output(gp.store_id("mm"), "data"), Input(ids.MM_DOMAIN_FILTER, "value"), prevent_initial_call=True
    )
    def filter_graph(domain):
        return gp.raw_from_types(get_context().registry, domain or None)

    @app.callback(
        Output(ids.MM_DETAIL, "children"), Input(gp.cy_id("mm"), "tapNodeData"), prevent_initial_call=True
    )
    def detail(data):
        if not data or not gp.is_element_node(data):
            return no_update
        return _detail(get_context().registry, gp.element_id_of(data))

    @app.callback(
        Output(ids.MM_TYPES_GRID, "rowTransaction"),
        Input(ids.MM_ADD_TYPE, "n_clicks"),
        prevent_initial_call=True,
    )
    def add_type(n):
        return (
            {
                "add": [
                    {
                        "id": f"new_type_{n}",
                        "name": "New type",
                        "plural": "",
                        "supertype": "",
                        "domain": "",
                        "provenance": "",
                        "prefix": "",
                        "active": True,
                        "description": "",
                    }
                ]
            }
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_RELS_GRID, "rowTransaction"),
        Input(ids.MM_ADD_REL, "n_clicks"),
        prevent_initial_call=True,
    )
    def add_rel(n):
        return (
            {
                "add": [
                    {
                        "id": f"new_relationship_{n}",
                        "name": "relates to",
                        "inverse": "",
                        "source": "ANY",
                        "target": "ANY",
                        "provenance": "",
                        "qualifiers": "",
                        "diagrams": "",
                        "description": "",
                    }
                ]
            }
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_ATTRS_GRID, "rowTransaction"),
        Input(ids.MM_ADD_ATTR, "n_clicks"),
        prevent_initial_call=True,
    )
    def add_attr(n):
        return (
            {
                "add": [
                    {
                        "type_id": "",
                        "name": f"new_attribute_{n}",
                        "label": "",
                        "type": "string",
                        "required": False,
                        "enum": "",
                        "sensitivity": "",
                        "description": "",
                    }
                ]
            }
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_FEEDBACK, "children"),
        Output(gp.store_id("mm"), "data", allow_duplicate=True),
        Output(ids.MM_SUBTITLE, "children"),
        Input(ids.MM_SAVE, "n_clicks"),
        State(ids.MM_TYPES_GRID, "virtualRowData"),
        State(ids.MM_TYPES_GRID, "rowData"),
        State(ids.MM_RELS_GRID, "virtualRowData"),
        State(ids.MM_RELS_GRID, "rowData"),
        State(ids.MM_ATTRS_GRID, "virtualRowData"),
        State(ids.MM_ATTRS_GRID, "rowData"),
        State(ids.MM_NOTATION_DOMAINS_GRID, "virtualRowData"),
        State(ids.MM_NOTATION_DOMAINS_GRID, "rowData"),
        State(ids.MM_NOTATION_TYPES_GRID, "virtualRowData"),
        State(ids.MM_NOTATION_TYPES_GRID, "rowData"),
        prevent_initial_call=True,
        running=[(Output(ids.MM_SAVE, "loading"), True, False)],
    )
    def save(
        n, t_virtual, t_rows, r_virtual, r_rows, a_virtual, a_rows, dn_virtual, dn_rows, tn_virtual, tn_rows
    ):
        if not n:
            return no_update, no_update, no_update
        ctx = get_context()
        if not ctx.can("edit_metamodel"):
            return alert(f"A {ctx.role_label()} may not edit the metamodel.", "red"), no_update, no_update
        try:
            d = _pack_from_grids(
                ctx.registry,
                _all_rows(t_virtual, t_rows, "id"),
                _all_rows(r_virtual, r_rows, "id"),
                _all_rows(a_virtual, a_rows, "type_id", "name"),
                _all_rows(dn_virtual, dn_rows, "id"),
                _all_rows(tn_virtual, tn_rows, "id"),
            )
            pack = pack_from_dict(d)
            Registry(pack)  # validates references and cycles before anything is stored
            ctx.backend.save_pack(pack)
            reg = ctx.reload_registry()
        except (ValueError, KeyError) as exc:
            return alert(f"Not saved: {exc}", "red"), no_update, no_update
        return (
            alert(
                f"Metamodel saved: {len(reg.pack.element_types)} types, "
                f"{len(reg.pack.relationship_types)} relationship types.",
                "green",
            ),
            gp.raw_from_types(reg),
            _counts(reg),
        )

    @app.callback(Output(ids.DOWNLOAD, "data"), Input(ids.MM_EXPORT, "n_clicks"), prevent_initial_call=True)
    def export(n):
        if not n:
            return no_update
        reg = get_context().registry
        text = yaml.safe_dump(pack_to_dict(reg.pack), sort_keys=False, allow_unicode=True, width=110)
        return dcc.send_string(text, f"{reg.pack.id}-metamodel.yaml")

    @app.callback(
        Output(ids.MM_FEEDBACK, "children", allow_duplicate=True),
        Output(ids.MM_TYPES_GRID, "rowData"),
        Output(ids.MM_RELS_GRID, "rowData"),
        Output(ids.MM_ATTRS_GRID, "rowData"),
        Output(gp.store_id("mm"), "data", allow_duplicate=True),
        Output(ids.MM_NOTATION_DOMAINS_GRID, "rowData"),
        Output(ids.MM_NOTATION_TYPES_GRID, "rowData"),
        Output({"type": ids.MERMAID_SRC, "id": ids.MM_NOTATION_PREVIEW}, "children", allow_duplicate=True),
        Output(ids.MM_SUBTITLE, "children", allow_duplicate=True),
        Input(ids.MM_RELOAD, "n_clicks"),
        prevent_initial_call=True,
    )
    def reload(n):
        if not n:
            return (no_update,) * 9
        ctx = get_context()
        try:
            pack = load_pack(ctx.settings.pack_path)
            ctx.backend.save_pack(pack)
            reg = ctx.reload_registry()
        except (OSError, ValueError) as exc:
            return (alert(f"Reload failed: {exc}", "red"),) + (no_update,) * 8
        return (
            alert(f"Reloaded {reg.pack.id} from {ctx.settings.pack_path}.", "green"),
            _type_rows(reg),
            _rel_rows(reg),
            _attr_rows(reg),
            gp.raw_from_types(reg),
            _domain_notation_rows(reg),
            _type_notation_rows(reg),
            notation_preview(reg),
            _counts(reg),
        )

    @app.callback(
        Output({"type": ids.MERMAID_SRC, "id": ids.MM_NOTATION_PREVIEW}, "children"),
        Input(ids.MM_NOTATION_DOMAINS_GRID, "cellValueChanged"),
        Input(ids.MM_NOTATION_TYPES_GRID, "cellValueChanged"),
        State(ids.MM_NOTATION_DOMAINS_GRID, "virtualRowData"),
        State(ids.MM_NOTATION_DOMAINS_GRID, "rowData"),
        State(ids.MM_NOTATION_TYPES_GRID, "virtualRowData"),
        State(ids.MM_NOTATION_TYPES_GRID, "rowData"),
        State(ids.MM_TYPES_GRID, "virtualRowData"),
        State(ids.MM_TYPES_GRID, "rowData"),
        State(ids.MM_RELS_GRID, "virtualRowData"),
        State(ids.MM_RELS_GRID, "rowData"),
        State(ids.MM_ATTRS_GRID, "virtualRowData"),
        State(ids.MM_ATTRS_GRID, "rowData"),
        prevent_initial_call=True,
    )
    def preview(
        _d,
        _t,
        dn_virtual,
        dn_rows,
        tn_virtual,
        tn_rows,
        t_virtual,
        t_rows,
        r_virtual,
        r_rows,
        a_virtual,
        a_rows,
    ):
        """The preview follows every edit before anything is saved."""
        ctx = get_context()
        try:
            d = _pack_from_grids(
                ctx.registry,
                _all_rows(t_virtual, t_rows, "id"),
                _all_rows(r_virtual, r_rows, "id"),
                _all_rows(a_virtual, a_rows, "type_id", "name"),
                _all_rows(dn_virtual, dn_rows, "id"),
                _all_rows(tn_virtual, tn_rows, "id"),
            )
            reg = Registry(pack_from_dict(d))
        except (ValueError, KeyError):
            return no_update
        return notation_preview(reg)
