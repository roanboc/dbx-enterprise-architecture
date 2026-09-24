"""Metamodel manager: one version at a time.

Six tabs over the version shown: **Manage** (the five lists: domains, element types,
relationship types, attributes, attribute groups — edited in grids and saved), **Graph** (the type graph, grouped and
laid out like every other network graph), **Architecture view** (the metamodel drawn in the
notation it declares, downloadable), **Notation** (how each domain and type is drawn),
**Versions** (every stored version, its state, who applies it, drafts, publishing and the
difference between two) and **Reviewers** (who approves a branch per element type).

A published version is frozen: saving edits made on one creates a draft, to be tried in an
organisation of its own and published when it is right (decision 0015).
"""

from __future__ import annotations

import base64
import json
from typing import Any

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
import yaml
from dash import ALL, Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.metamodel import Registry, pack_to_dict, pack_yaml
from ea.metamodel.diff import PackDiff
from ea.metamodel.loader import pack_from_dict, suspect_split_descriptions
from ea.models import (
    ANY,
    ATTRIBUTE_TYPES,
    LEVELS,
    ConflictError,
    Forbidden,
    NotFoundError,
    Pack,
    PackVersion,
    slugify,
)
from ea.services.roles import a_role
from ea.ui import graph as gp
from ea.ui import ids, layout
from ea.ui.components import (
    FALLBACK_HEX,
    SELECT_COLUMN,
    alert,
    icon,
    layer_chips,
    mermaid_block,
    modal_title,
    page_title,
    simple_table,
    view_toolbar,
)
from ea.ui.context import AppContext, get_context
from ea.views import view_from_metamodel
from ea.views.drawio import STENCIL, to_drawio
from ea.views.mermaid import SHAPES, to_markdown, to_mermaid
from ea.views.model import LAYER_ORDER, View, ViewNode, layer_rank

_SELECT = "agSelectCellEditor"
_LARGE = {"cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True}
STATUS_COLOUR = {"draft": "orange", "published": "green", "retired": "gray"}
TABS = [
    ("manage", "Manage", "tabler:table"),
    ("graph", "Graph", "tabler:topology-star"),
    ("view", "Architecture view", "tabler:vector-triangle"),
    ("notation", "Notation", "tabler:palette"),
    ("versions", "Versions", "tabler:versions"),
    ("reviewers", "Reviewers", "tabler:user"),
]

#: The list the Manage tab opens on. It is the first pill, so a reader is never dropped on
#: the second one; `_manage_panel` draws the pills in this order.
FIRST_LIST = "domains"

TYPE_COLS = [
    # An id is fixed once saved (rows are matched by it, and content is typed by it); a row the
    # reader just added carries `added` and may be given an id of its own before it is saved.
    {"field": "id", "editable": {"function": "params.data.added"}, "pinned": "left", "width": 240},
    {"field": "name", "editable": True, "width": 220},
    {"field": "plural", "editable": True, "width": 200},
    {"field": "supertype", "editable": True, "width": 180},
    {"field": "domain", "editable": True, "width": 130},
    {"field": "provenance", "editable": True, "width": 120},
    {"field": "prefix", "editable": True, "width": 90},
    {"field": "active", "editable": True, "width": 90, "cellDataType": "boolean"},
    {"field": "abstract", "editable": True, "width": 100, "cellDataType": "boolean"},
    # where the type sits against principle P9's line: at the enterprise level, or a system's
    # inside that is linked from the system rather than modelled (initiative 24)
    {
        "field": "level",
        "editable": True,
        "width": 120,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": LEVELS},
        "headerTooltip": "enterprise: it belongs in the repository; solution: a system's inside, linked from the system",
    },
    {"field": "source_of_record", "editable": True, "width": 240},
    {"field": "type_owner", "editable": True, "width": 200},
    {"field": "instance_owner", "editable": True, "width": 200},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 300, **_LARGE},
    {"field": "examples", "editable": True, "width": 240, "headerName": "examples (comma-separated)"},
    {"field": "deactivation_reason", "editable": True, "width": 260},
    {"field": "properties", "editable": True, "width": 220, "headerName": "properties (JSON)", **_LARGE},
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
    {"field": "src_max", "editable": True, "width": 100, "headerName": "source max"},
    {"field": "dst_max", "editable": True, "width": 100, "headerName": "target max"},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 260, **_LARGE},
    {"field": "properties", "editable": True, "width": 220, "headerName": "properties (JSON)", **_LARGE},
]
ATTR_COLS = [
    {
        "field": "type_id",
        "editable": True,
        "pinned": "left",
        "width": 240,
        "headerName": "belongs to (element type, relationship type, blank = common)",
    },
    {"field": "name", "editable": True, "width": 200},
    {"field": "label", "editable": True, "width": 200},
    {
        "field": "type",
        "editable": True,
        "width": 110,
        "cellEditor": _SELECT,
        "cellEditorParams": {"values": list(ATTRIBUTE_TYPES)},
    },
    {"field": "required", "editable": True, "width": 100, "cellDataType": "boolean"},
    {"field": "enum", "editable": True, "width": 220, "headerName": "enum (comma-separated)"},
    {"field": "default", "editable": True, "width": 120},
    {"field": "multiple", "editable": True, "width": 100, "cellDataType": "boolean"},
    # Picked from the groups the version declares, never typed: a typo used to make a section
    # of its own on the element page, which nobody could see was a mistake.
    {"field": "group", "editable": True, "width": 160, "cellEditor": _SELECT},
    {"field": "help", "editable": True, "width": 220},
    {"field": "unit", "editable": True, "width": 90},
    {"field": "pattern", "editable": True, "width": 160},
    {"field": "min", "editable": True, "width": 90},
    {"field": "max", "editable": True, "width": 90},
    {"field": "sensitivity", "editable": True, "width": 120},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 240},
    {"field": "properties", "editable": True, "width": 200, "headerName": "properties (JSON)", **_LARGE},
]
GROUP_COLS = [
    {"field": "id", "editable": True, "pinned": "left", "width": 180},
    {"field": "name", "editable": True, "width": 260, "headerName": "name (the section heading)"},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 320, **_LARGE},
    {"field": "properties", "editable": True, "width": 220, "headerName": "properties (JSON)", **_LARGE},
]
DOMAIN_COLS = [
    {"field": "id", "editable": True, "pinned": "left", "width": 180},
    {"field": "name", "editable": True, "width": 260},
    {"field": "description", "editable": True, "flex": 1, "minWidth": 320, **_LARGE},
    {"field": "properties", "editable": True, "width": 220, "headerName": "properties (JSON)", **_LARGE},
]
GRID_KW = dict(
    defaultColDef={"sortable": True, "filter": True, "resizable": True, "editable": True},
    className="ag-theme-alpine",
    dashGridOptions={
        "singleClickEdit": False,
        "stopEditingWhenCellsLoseFocus": True,
        "animateRows": False,
    },
    style={"height": "55vh", "width": "100%"},
)


def _grid_kw(can_edit: bool, **over: Any) -> dict[str, Any]:
    """The grid options, with every cell read-only for a role that may not save the metamodel.

    A cell that takes an edit nobody may store is a dead end: the reader types, presses Save,
    and is refused for something they were invited to do. The role decides the whole tab.
    """
    kw = dict(GRID_KW, **over)
    kw["defaultColDef"] = dict(GRID_KW["defaultColDef"], editable=can_edit)
    kw["dashGridOptions"] = dict(
        GRID_KW["dashGridOptions"], rowSelection="multiple", suppressRowClickSelection=True
    )
    return kw


# ------------------------------------------------------------------ rows
def _props(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True) if d else ""


def _type_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "added": False,
            "name": t.name,
            "plural": t.plural,
            "supertype": t.supertype or "",
            "domain": t.domain,
            "provenance": t.provenance,
            "prefix": t.prefix,
            "active": t.active,
            "abstract": t.abstract,
            "level": t.level,
            "source_of_record": t.source_of_record,
            "type_owner": t.type_owner,
            "instance_owner": t.instance_owner,
            "description": t.description,
            "deactivation_reason": t.deactivation_reason,
            "examples": ", ".join(t.examples),
            "properties": _props(t.properties),
        }
        for t in reg.pack.element_types
    ]


def _domain_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {"id": d.id, "name": d.name, "description": d.description, "properties": _props(d.properties)}
        for d in reg.pack.domains
    ]


def _attr_cols(reg: Registry) -> list[dict[str, Any]]:
    """The attribute columns, with the group cell offering the groups this version declares.

    A blank is offered too: an attribute outside every group is read on its own, above the
    sections, and that is a choice rather than an omission.
    """
    values = [""] + [g.id for g in reg.pack.attribute_groups]
    return [{**c, "cellEditorParams": {"values": values}} if c["field"] == "group" else c for c in ATTR_COLS]


def _group_rows(reg: Registry) -> list[dict[str, Any]]:
    return [
        {"id": g.id, "name": g.name, "description": g.description, "properties": _props(g.properties)}
        for g in reg.pack.attribute_groups
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
            "src_max": "" if r.src_max is None else r.src_max,
            "dst_max": "" if r.dst_max is None else r.dst_max,
            "description": r.description,
            "properties": _props(r.properties),
        }
        for r in reg.pack.relationship_types
    ]


def _attr_row(a, owner: str, added: bool = False) -> dict[str, Any]:
    return {
        # The grid matches a row by `row_key` and an element type by `id`, so a row keeps its
        # identity while its name is being typed; `added` is what makes an id editable, and
        # both are read by the grid rather than shown in a column.
        "row_key": f"{owner}|{a.name}",
        "added": added,
        "type_id": owner,
        "name": a.name,
        "label": a.label,
        "type": a.type,
        "required": a.required,
        "enum": ", ".join(a.enum or []),
        "default": ""
        if a.default is None
        else (str(a.default).lower() if isinstance(a.default, bool) else a.default),
        "multiple": a.multiple,
        "group": a.group,
        "help": a.help,
        "unit": a.unit,
        "pattern": a.pattern,
        "min": "" if a.min is None else a.min,
        "max": "" if a.max is None else a.max,
        "sensitivity": a.sensitivity,
        "description": a.description,
        "properties": _props(a.properties),
    }


def _attr_rows(reg: Registry) -> list[dict[str, Any]]:
    rows = [_attr_row(a, "") for a in reg.pack.common_attributes]
    for t in reg.pack.element_types:
        rows += [_attr_row(a, t.id) for a in t.attributes]
    for r in reg.pack.relationship_types:
        rows += [_attr_row(a, r.id) for a in r.attributes]
    return rows


def _reviewer_rows(ctx: AppContext) -> list[dict[str, str]]:
    assigned = ctx.reviews.assignments()
    return [
        {"type_id": t.id, "type": t.name, "reviewers": ", ".join(assigned.get(t.id, []))}
        for t in ctx.registry.pack.element_types
        if t.active
    ]


# --------------------------------------------------------------- notation
def notation_swatches(reg: Registry) -> Any:
    """One chip per domain in the colour that domain declares.

    A generated view is filled by ArchiMate layer, so the domain's colour never shows there;
    it is what the network graph fills a node with and what every badge in the application
    takes its colour from. Without this the colour column reads as a control that does
    nothing, which is worse than a control that does something elsewhere.
    """
    return dmc.Group(
        [
            dmc.Group(
                [
                    html.Div(
                        style={
                            "width": "14px",
                            "height": "14px",
                            "borderRadius": "3px",
                            "background": d.notation.get("hex") or FALLBACK_HEX,
                            "border": "1px solid rgba(0,0,0,.2)",
                        }
                    ),
                    dmc.Text(d.name, size="xs"),
                    dmc.Badge(
                        d.notation.get("colour") or "gray",
                        color=d.notation.get("colour") or "gray",
                        variant="light",
                        size="xs",
                    ),
                ],
                gap=6,
            )
            for d in reg.pack.domains
        ],
        gap="md",
        mb="xs",
    )


def notation_view(reg: Registry) -> View:
    """One sample node per active type, in layer order, drawn with the notation as it stands."""
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
    return view


def notation_preview(reg: Registry) -> str:
    return to_mermaid(notation_view(reg), direction="LR")


def metamodel_view_code(reg: Registry, domain: str | None, include_inactive: bool) -> str:
    return to_mermaid(view_from_metamodel(reg, domain or None, include_inactive), direction="BT", legend=True)


# ----------------------------------------------------------------- detail
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
                    dmc.Badge("abstract", color="grape", size="xs") if t.abstract else None,
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
            dmc.Text("Properties: " + _props(t.properties), size="xs", c="dimmed") if t.properties else None,
        ],
        gap=4,
    )


# ------------------------------------------------------------------ page
def _status_badge(status: str, size: str = "sm") -> dmc.Badge:
    return dmc.Badge(status, color=STATUS_COLOUR.get(status, "gray"), variant="light", size=size)


def _version_options(ctx: AppContext) -> list[dict[str, str]]:
    """Every stored version; the metamodel is named only when the store holds more than one.

    Named, not keyed: the identifier is opaque (decision 0021), so it would tell a reader
    choosing between two versions nothing at all. The value stays the canonical reference.
    """
    org = ctx.organisation()
    versions = ctx.metamodels.versions()
    several = len({v.pack_id for v in versions}) > 1
    return [
        {
            "value": v.ref,
            "label": (f"{v.name} · " if several else "")
            + f"{v.version} · {v.status}"
            + (" · applied here" if v.ref == org.pack_ref else ""),
        }
        for v in versions
    ]


def _counts(reg: Registry, ctx: AppContext) -> str:
    """What the page says it holds. A save changes it, so it is written in one place."""
    pack = reg.pack
    org = ctx.organisation()
    where = (
        f"applied to {org.name}"
        if org.pack_ref == pack.ref
        else f"not the version {org.name} applies ({org.pack_ref})"
    )
    inactive = len(pack.element_types) - len(reg.active_types())
    attrs = len(pack.common_attributes) + sum(len(t.attributes) for t in pack.element_types)
    attrs += sum(len(r.attributes) for r in pack.relationship_types)
    return (
        f"{pack.name}, version {pack.version} ({pack.status}), {where}. "
        f"{len(reg.active_types())} active types, {inactive} inactive, "
        f"{len(pack.relationship_types)} relationship types, {attrs} attributes."
    )


def render(ctx: AppContext) -> html.Div:
    reg = ctx.registry
    return html.Div(
        [
            page_title(
                "Metamodel",
                _counts(reg, ctx),
                subtitle_id=ids.MM_SUBTITLE,
                right=dmc.Select(
                    id=ids.MM_VERSION_SELECT,
                    label="Showing version",
                    data=_version_options(ctx),
                    value=reg.pack.ref,
                    w=380,
                    size="sm",
                    allowDeselect=False,
                    leftSection=icon("tabler:versions", 14),
                    comboboxProps={"withinPortal": True},
                ),
            ),
            dcc.Store(id=ids.MM_VERSION, data=reg.pack.ref),
            dcc.Store(id=ids.MM_CONFIRM_STORE, data=None),
            html.Div(id=ids.MM_FEEDBACK),
            html.Div(_body(ctx, reg, "manage", FIRST_LIST), id=ids.MM_BODY),
            _draft_modal(ctx),
            _rename_modal(),
            dcc.Store(id=ids.MM_RENAME_REF, data=""),
            _confirm_modal(),
        ]
    )


def _draft_modal(ctx: AppContext) -> dmc.Modal:
    org = ctx.organisation()
    return dmc.Modal(
        id=ids.MM_DRAFT_MODAL,
        title=modal_title("Save as a new draft", ids.MM_DRAFT_MODAL),
        closeButtonProps={"aria-label": "Close this dialog"},
        children=dmc.Stack(
            [
                dmc.Text(
                    "The version shown is published, so it cannot change. Your edits are saved as a new "
                    "draft copied from it: try the draft in an organisation of its own, then publish it "
                    "and apply it where it belongs.",
                    size="sm",
                    c="dimmed",
                ),
                dmc.TextInput(
                    id=ids.MM_DRAFT_VERSION,
                    label="Version name",
                    required=True,
                    description="Letters, digits, '.', '_' or '-'; a date works well",
                ),
                dmc.Textarea(id=ids.MM_DRAFT_NOTES, label="What this draft tries", autosize=True, minRows=2),
                dmc.Checkbox(
                    id=ids.MM_DRAFT_APPLY,
                    label=f"Apply the draft to {org.name} now",
                    description="Its content is checked against the draft first; findings are reported, not refused"
                    + (" — this is the default organisation, so apply with care" if org.is_default else ""),
                    checked=not org.is_default,
                ),
                html.Div(id=ids.MM_DRAFT_FEEDBACK),
                dmc.Group(
                    [
                        dmc.Button(
                            "Create the draft", id=ids.MM_DRAFT_SAVE, leftSection=icon("tabler:device-floppy")
                        )
                    ],
                    justify="flex-end",
                ),
            ]
        ),
    )


def _rename_modal() -> dmc.Modal:
    """Correct what a version is called — at any status, and it says why that is allowed.

    A reader who has been told a published version is frozen will not believe a field that
    edits one unless the dialog explains the distinction, so it does.
    """
    return dmc.Modal(
        id=ids.MM_RENAME_MODAL,
        title=modal_title("Rename this metamodel", ids.MM_RENAME_MODAL),
        closeButtonProps={"aria-label": "Close this dialog"},
        children=dmc.Stack(
            [
                dmc.Text(
                    "A name is a label: nothing is stored against it and nothing looks anything up by "
                    "it, so correcting one changes no definition and no organisation. That is why a "
                    "published version can be renamed while everything it defines stays frozen.",
                    size="sm",
                    c="dimmed",
                ),
                dmc.TextInput(
                    id=ids.MM_RENAME_NAME,
                    label="Name",
                    required=True,
                    description="What this metamodel is called wherever a reader sees it",
                ),
                html.Div(id=ids.MM_RENAME_FEEDBACK),
                dmc.Group(
                    [dmc.Button("Rename", id=ids.MM_RENAME_SAVE, leftSection=icon("tabler:pencil"))],
                    justify="flex-end",
                ),
            ]
        ),
    )


def _confirm_modal() -> dmc.Modal:
    return dmc.Modal(
        id=ids.MM_CONFIRM_MODAL,
        title=modal_title("Are you sure?", ids.MM_CONFIRM_MODAL),
        closeButtonProps={"aria-label": "Close this dialog"},
        children=dmc.Stack(
            [
                html.Div(id=ids.MM_CONFIRM_TEXT),
                dmc.Group(
                    [dmc.Button("Yes, go ahead", id=ids.MM_CONFIRM_YES, color="red")], justify="flex-end"
                ),
            ]
        ),
    )


def _body(ctx: AppContext, reg: Registry, tab: str, list_tab: str = FIRST_LIST) -> Any:
    pack = reg.pack
    org = ctx.organisation()
    applied = org.pack_ref == pack.ref
    return dmc.Tabs(
        [
            dmc.TabsList(
                [dmc.TabsTab(label, value=value, leftSection=icon(ic, 14)) for value, label, ic in TABS]
            ),
            dmc.TabsPanel(_manage_panel(ctx, reg, list_tab), value="manage", pt="sm"),
            dmc.TabsPanel(_graph_panel(reg), value="graph", pt="sm"),
            dmc.TabsPanel(_view_panel(reg), value="view", pt="sm"),
            dmc.TabsPanel(_notation_panel(ctx, reg), value="notation", pt="sm"),
            dmc.TabsPanel(_versions_panel(ctx, reg, applied), value="versions", pt="sm"),
            dmc.TabsPanel(_reviewers_panel(ctx), value="reviewers", pt="sm"),
        ],
        id=ids.MM_TABS,
        value=tab if tab in {t[0] for t in TABS} else "manage",
    )


def _cols(cols: list[dict[str, Any]], can_edit: bool) -> list[dict[str, Any]]:
    """The columns, read-only throughout for a role that may not save the metamodel.

    A column says `editable` for itself, which outranks the grid's default, so the role has
    to be applied column by column or a Reader still gets an editor on every cell.
    """
    if can_edit:
        return cols
    return [dict(c, editable=False) for c in cols]


def _grid(
    grid_id: str,
    cols: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    row_id: str | None,
    can_edit: bool = True,
) -> Any:
    kw = _grid_kw(can_edit)
    if row_id:
        kw["getRowId"] = row_id
    return dag.AgGrid(id=grid_id, columnDefs=[SELECT_COLUMN, *_cols(cols, can_edit)], rowData=rows, **kw)


def _row_buttons(what: str, add_id: str, delete_id: str, can_edit: bool) -> dmc.Group:
    """Add one row, or delete the rows ticked. Neither stores anything: the save does."""
    return dmc.Group(
        [
            dmc.Button(
                f"Add {what}",
                id=add_id,
                size="xs",
                variant="light",
                leftSection=icon("tabler:plus"),
                disabled=not can_edit,
            ),
            dmc.Button(
                f"Delete the {what}s ticked",
                id=delete_id,
                size="xs",
                variant="light",
                color="red",
                leftSection=icon("tabler:trash"),
                disabled=not can_edit,
            ),
        ],
        my="xs",
        gap="xs",
    )


def _manage_panel(ctx: AppContext, reg: Registry, list_tab: str) -> Any:
    pack = reg.pack
    can_edit = ctx.can("edit_metamodel")
    draft = pack.status == "draft"
    n_attrs = len(_attr_rows(reg))
    if not can_edit:
        why = f"{a_role(ctx.role_label())} may not change the metamodel; only an admin saves it."
    elif draft:
        why = f"Version {pack.version} is a draft: Save changes writes the grids to it, in place."
    else:
        why = (
            f"Version {pack.version} is {pack.status}, so it cannot change: Save as a new draft copies "
            "your edits into a draft, to try in an organisation of its own and publish when ready."
        )
    return dmc.Stack(
        [
            dmc.Text(
                "The lists a version is made of. Rows are matched by id. Tick rows and delete them to "
                "take them out of this version, and what depended on them goes or is cleared with them; "
                "to keep existing content resolving, set a type's active to false instead. An abstract "
                "type groups its sub-types and is never an element's type. A properties cell holds any "
                "JSON object the framework wants kept with the row.",
                size="sm",
                c="dimmed",
            ),
            dmc.Tabs(
                [
                    dmc.TabsList(
                        [
                            # In the order a metamodel is read rather than the order it was built:
                            # a domain groups element types, a type carries attributes, an
                            # attribute names one of the groups. The panels below are matched to
                            # these by `value`, so their own order is not what a reader sees.
                            dmc.TabsTab(f"Domains ({len(pack.domains)})", value="domains"),
                            dmc.TabsTab(f"Element types ({len(pack.element_types)})", value="types"),
                            dmc.TabsTab(f"Relationship types ({len(pack.relationship_types)})", value="rels"),
                            dmc.TabsTab(f"Attributes ({n_attrs})", value="attrs"),
                            dmc.TabsTab(f"Attribute groups ({len(pack.attribute_groups)})", value="groups"),
                        ]
                    ),
                    dmc.TabsPanel(
                        [
                            _row_buttons("type", ids.MM_ADD_TYPE, ids.MM_DEL_TYPE, can_edit),
                            _grid(ids.MM_TYPES_GRID, TYPE_COLS, _type_rows(reg), "params.data.id", can_edit),
                        ],
                        value="types",
                    ),
                    dmc.TabsPanel(
                        [
                            _row_buttons("relationship type", ids.MM_ADD_REL, ids.MM_DEL_REL, can_edit),
                            _grid(ids.MM_RELS_GRID, REL_COLS, _rel_rows(reg), "params.data.id", can_edit),
                        ],
                        value="rels",
                    ),
                    dmc.TabsPanel(
                        [
                            _row_buttons("attribute", ids.MM_ADD_ATTR, ids.MM_DEL_ATTR, can_edit),
                            _grid(
                                ids.MM_ATTRS_GRID,
                                _attr_cols(reg),
                                _attr_rows(reg),
                                "params.data.row_key",
                                can_edit,
                            ),
                        ],
                        value="attrs",
                    ),
                    dmc.TabsPanel(
                        [
                            _row_buttons("domain", ids.MM_ADD_DOMAIN, ids.MM_DEL_DOMAIN, can_edit),
                            _grid(
                                ids.MM_DOMAINS_GRID,
                                DOMAIN_COLS,
                                _domain_rows(reg),
                                "params.data.id",
                                can_edit,
                            ),
                        ],
                        value="domains",
                    ),
                    dmc.TabsPanel(
                        [
                            dmc.Text(
                                "The sections an element's attributes are read and edited in, in this order. "
                                "An attribute picks one from this list rather than naming it in free text, so a "
                                "typo cannot make a section of its own. Deleting a group leaves its attributes "
                                "ungrouped.",
                                size="xs",
                                c="dimmed",
                                mb="xs",
                            ),
                            _row_buttons("attribute group", ids.MM_ADD_GROUP, ids.MM_DEL_GROUP, can_edit),
                            _grid(
                                ids.MM_GROUPS_GRID,
                                GROUP_COLS,
                                _group_rows(reg),
                                "params.data.id",
                                can_edit,
                            ),
                        ],
                        value="groups",
                    ),
                ],
                id=ids.MM_LISTS,
                value=list_tab,
                variant="pills",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Save changes" if draft else "Save as a new draft…",
                        id=ids.MM_SAVE,
                        leftSection=icon("tabler:device-floppy"),
                        disabled=not can_edit,
                    ),
                    dmc.Button(
                        "Export YAML",
                        id=ids.MM_EXPORT,
                        variant="light",
                        leftSection=icon("tabler:download"),
                    ),
                    dcc.Upload(
                        id=ids.MM_RELOAD,
                        accept=".yaml,.yml",
                        multiple=False,
                        disable_click=not can_edit,
                        children=dmc.Button(
                            "Load YAML file…",
                            variant="subtle",
                            color="gray",
                            leftSection=icon("tabler:upload"),
                            disabled=not can_edit,
                        ),
                    ),
                ],
                gap="xs",
                mt="md",
            ),
            # A disabled button raises no tooltip, so the reason stands under the row it is in.
            dmc.Text(why, id=ids.MM_SAVE_WHY, size="xs", c="dimmed"),
            dmc.Text(
                "Export YAML downloads the version shown as a pack file. Load YAML file stores the file as "
                "the version it names (a draft it holds is replaced, a published one refused when the file "
                "differs) and applies it to this organisation after checking its content against it.",
                size="xs",
                c="dimmed",
            ),
        ],
        gap="xs",
    )


def _graph_panel(reg: Registry) -> Any:
    return dmc.Stack(
        [
            gp.graph_panel(
                "mm",
                reg,
                gp.raw_from_types(reg),
                height="60vh",
                group_by="domain",
                extra_controls=[
                    dmc.Select(
                        id=ids.MM_DOMAIN_FILTER,
                        allowDeselect=False,
                        **{"aria-label": "Domain"},
                        data=[{"value": "", "label": "All domains"}]
                        + [{"value": d.id, "label": d.name} for d in reg.pack.domains],
                        value="",
                        w=200,
                        size="xs",
                        comboboxProps={"withinPortal": False},
                    ),
                    dmc.Switch(
                        id=ids.MM_GRAPH_INACTIVE, label="Inactive types too", size="xs", checked=False
                    ),
                ],
                hint="Tap a type to see its definition, attributes and relationships. Dashed edge = sub-type; diamond = any element.",
            ),
            dmc.Paper(
                html.Div(_detail(reg, None), id=ids.MM_DETAIL),
                p="sm",
                withBorder=True,
                style={"maxHeight": "240px", "overflow": "auto"},
            ),
        ],
        gap="sm",
    )


def _view_panel(reg: Registry) -> Any:
    return dmc.Stack(
        [
            dmc.Text(
                "The metamodel drawn the way the architecture documents draw a notation: one shape per "
                "element type in the layer, glyph, stereotype and shape it declares, one edge per "
                "relationship type, an 'is a' edge from a sub-type to its supertype, a diamond for any "
                "element. Download it as Markdown to paste into a document, or as draw.io to arrange.",
                size="sm",
                c="dimmed",
            ),
            dmc.Group(
                [
                    dmc.Select(
                        id=ids.MM_VIEW_DOMAIN,
                        allowDeselect=False,
                        **{"aria-label": "Domain drawn"},
                        data=[{"value": "", "label": "All domains"}]
                        + [{"value": d.id, "label": d.name} for d in reg.pack.domains],
                        value="",
                        w=220,
                        size="xs",
                        comboboxProps={"withinPortal": True},
                    ),
                    dmc.Switch(id=ids.MM_VIEW_INACTIVE, label="Inactive types too", size="xs", checked=False),
                ],
                gap="sm",
            ),
            mermaid_block(
                ids.MM_VIEW,
                metamodel_view_code(reg, None, False),
                legend=layer_chips(view_from_metamodel(reg, None, False)),
            ),
            view_toolbar(
                ids.MM_VIEW_MD,
                ids.MM_VIEW_DRAWIO,
                "Every shape is an element type of the version shown; nothing here is drawn by hand.",
                note_id=ids.MM_VIEW_NOTE,
            ),
        ],
        gap="sm",
    )


def _notation_panel(ctx: AppContext, reg: Registry) -> Any:
    can_edit = ctx.can("edit_metamodel")
    small = _grid_kw(can_edit, style={"height": "24vh", "width": "100%"})
    tall = _grid_kw(can_edit, style={"height": "40vh", "width": "100%"})
    return dmc.Stack(
        [
            dmc.Text(
                "How each domain and type is drawn in generated views and graphs. A blank cell inherits from "
                "the supertype, then the domain. The preview follows every edit; Save changes on the Manage "
                "tab writes the notation with the rest of the version.",
                size="sm",
                c="dimmed",
            ),
            dmc.Title("Domains", order=2, className="ea-section-title"),
            dag.AgGrid(
                id=ids.MM_NOTATION_DOMAINS_GRID,
                columnDefs=_cols(DOMAIN_NOTATION_COLS, can_edit),
                rowData=_domain_notation_rows(reg),
                getRowId="params.data.id",
                **small,
            ),
            dmc.Title("Element types (overrides)", order=2, className="ea-section-title", mt="md"),
            dag.AgGrid(
                id=ids.MM_NOTATION_TYPES_GRID,
                columnDefs=_cols(TYPE_NOTATION_COLS, can_edit),
                rowData=_type_notation_rows(reg),
                getRowId="params.data.id",
                **tall,
            ),
            dmc.Title("Preview", order=2, className="ea-section-title", mt="md"),
            html.Div(id=ids.MM_NOTATION_NOTE),
            dmc.Text(
                "The chips take each domain's colour, which the network graph and every "
                "badge use; the diagram below takes each type's glyph, stereotype and "
                "shape, and is filled by ArchiMate layer rather than by domain.",
                size="xs",
                c="dimmed",
            ),
            html.Div(notation_swatches(reg), id=ids.MM_NOTATION_SWATCHES),
            mermaid_block(
                ids.MM_NOTATION_PREVIEW, notation_preview(reg), legend=layer_chips(notation_view(reg))
            ),
        ],
        gap="xs",
    )


def _action(label: str, action: str, ref: str, enabled: bool, colour: str = "gray", ic: str = "") -> Any:
    return dmc.Button(
        label,
        id={"type": ids.MM_VER_ACTION, "action": action, "ref": ref},
        size="compact-xs",
        variant="light",
        color=colour,
        disabled=not enabled,
        leftSection=icon(ic, 12) if ic else None,
    )


def _versions_table(ctx: AppContext, versions: list[PackVersion], shown: str) -> Any:
    can_edit, can_publish = ctx.can("edit_metamodel"), ctx.can("publish_metamodel")
    names = {o.org_id: o.name for o in ctx.orgs.list()}
    rows = []
    for v in versions:
        applied = v.applied_by
        rows.append(
            [
                # This is the one screen where the identifier earns its space: it is where a
                # person picks up a reference to paste into `ea metamodel …`. So the version
                # reads plainly and the short identifier sits beside it as something to copy,
                # with the whole canonical reference on the cell for anyone who needs it.
                dmc.Group(
                    [
                        dmc.Text(v.version, size="sm", fw=600),
                        dmc.Tooltip(
                            dmc.Code(v.short_id, style={"whiteSpace": "nowrap"}),
                            label=v.ref,
                            withArrow=True,
                        ),
                        dmc.Badge("shown", color="indigo", size="xs", variant="outline")
                        if v.ref == shown
                        else None,
                    ],
                    gap=6,
                ),
                _status_badge(v.status, "xs"),
                v.name,
                dmc.Code(v.derived_from) if v.derived_from else "",
                dmc.Group(
                    [dmc.Badge(names.get(o, o), color="teal", variant="light", size="xs") for o in applied]
                    or [dmc.Text("nobody", size="xs", c="dimmed")],
                    gap=4,
                ),
                f"{v.created_by or ''} {str(v.created_at or v.loaded_at or '')[:16]}".strip(),
                f"{v.published_by or ''} {str(v.published_at or '')[:16]}".strip() if v.published_at else "",
                v.notes,
                dmc.Group(
                    [
                        _action("Show", "show", v.ref, v.ref != shown, "indigo", "tabler:eye"),
                        _action("New draft", "draft", v.ref, can_edit, "indigo", "tabler:copy"),
                        _action(
                            "Publish",
                            "publish",
                            v.ref,
                            can_publish and v.status == "draft",
                            "green",
                            "tabler:check",
                        ),
                        _action(
                            "Retire",
                            "retire",
                            v.ref,
                            can_publish and v.status == "published" and not applied,
                            "orange",
                        ),
                        _action(
                            "Delete",
                            "delete",
                            v.ref,
                            can_edit and v.status != "published" and not applied,
                            "red",
                            "tabler:trash",
                        ),
                        # At any status: a freeze is on what a version defines, and a name
                        # defines nothing (decision 0022).
                        _action("Rename", "rename", v.ref, can_edit, "gray", "tabler:pencil"),
                        _action("Export", "export", v.ref, True, "gray", "tabler:download"),
                    ],
                    gap=4,
                ),
            ]
        )
    return simple_table(
        ["version", "state", "pack", "derived from", "applied by", "created", "published", "notes", ""], rows
    )


def _versions_panel(ctx: AppContext, reg: Registry, applied: bool) -> Any:
    versions = ctx.metamodels.versions()
    options = [{"value": v.ref, "label": f"{v.label} ({v.status})"} for v in versions]
    shown = reg.pack.ref
    derived = reg.pack.derived_from if any(v.ref == reg.pack.derived_from for v in versions) else ""
    # A draft is compared from what it was copied from; anything else from itself to the newest other version.
    other = next((v.ref for v in versions if v.ref != shown), shown)
    cmp_from, cmp_to = (derived, shown) if derived else (shown, other)
    return dmc.Stack(
        [
            dmc.Text(
                "A pack is kept in versions. A draft is edited in place; a published version is frozen, "
                "so what was validated against it stays validated; a retired one is kept for the record. "
                "Each organisation applies one version. To try a change: start a draft from the version "
                "in use, apply it to an organisation copied from the default on the Organisations page, "
                "work there, compare, then publish the draft and apply it to the default organisation.",
                size="sm",
                c="dimmed",
            ),
            html.Div(_versions_table(ctx, versions, shown), id=ids.MM_VERSIONS_TABLE),
            dmc.Group(
                [
                    dmc.Anchor(
                        dmc.Button(
                            "Apply a version to an organisation…",
                            variant="light",
                            size="xs",
                            leftSection=icon("tabler:rocket", 14),
                        ),
                        href=f"/organisations?version={shown}",
                        underline="never",
                    ),
                    dmc.Text(
                        "Applying happens on the Organisations page, where every organisation and the "
                        "version it applies are listed; the version shown here is preselected.",
                        size="xs",
                        c="dimmed",
                    ),
                ],
                gap="sm",
                align="center",
            ),
            dmc.Paper(
                [
                    dmc.Title("Compare two versions", order=2, className="ea-section-title"),
                    dmc.Group(
                        [
                            dmc.Select(
                                id=ids.MM_CMP_A,
                                allowDeselect=False,
                                label="From",
                                data=options,
                                value=cmp_from,
                                w=320,
                                size="xs",
                                comboboxProps={"withinPortal": True},
                            ),
                            dmc.Select(
                                id=ids.MM_CMP_B,
                                allowDeselect=False,
                                label="To",
                                data=options,
                                value=cmp_to,
                                w=320,
                                size="xs",
                                comboboxProps={"withinPortal": True},
                            ),
                            dmc.Button(
                                "Compare",
                                id=ids.MM_CMP_RUN,
                                size="xs",
                                variant="light",
                                leftSection=icon("tabler:git-compare", 14),
                            ),
                        ],
                        gap="sm",
                        align="flex-end",
                    ),
                    html.Div(
                        dmc.Text("Pick two versions and compare them.", size="xs", c="dimmed"),
                        id=ids.MM_CMP_RESULT,
                    ),
                ],
                p="sm",
                withBorder=True,
            ),
        ],
        gap="sm",
    )


def diff_table(diff: PackDiff) -> Any:
    if diff.empty:
        return alert(diff.summary(), "green", dismissible=False)
    rows = []
    for e in diff.entries:
        detail = [html.Div(f"{f}: {b!r} → {a!r}") for f, b, a in e.fields] if e.change == "changed" else ""
        rows.append(
            [
                dmc.Badge(
                    e.change,
                    color={"added": "green", "removed": "red", "changed": "orange"}[e.change],
                    size="xs",
                    variant="light",
                ),
                e.kind.replace("_", " "),
                dmc.Code(e.id),
                e.label,
                html.Div(detail) if detail else "",
            ]
        )
    return dmc.Stack(
        [
            dmc.Text(diff.summary(), size="sm"),
            simple_table(["change", "kind", "id", "name", "what changed"], rows),
        ],
        gap="xs",
    )


def _reviewers_panel(ctx: AppContext) -> Any:
    return dmc.Stack(
        [
            dmc.Text(
                "Who reviews a branch that touches each element type in this organisation: users or groups, "
                "comma-separated. The types are those of the version this organisation applies, whichever "
                "version the tabs above are showing, because that is what a branch here can hold. A type "
                "with nobody assigned may be approved by any Reviewer. Only an admin saves this table.",
                size="sm",
                c="dimmed",
            ),
            dag.AgGrid(
                id=ids.MM_REVIEWERS_GRID,
                columnDefs=_cols(
                    [
                        {"field": "type_id", "headerName": "type id", "width": 260, "editable": False},
                        {"field": "type", "width": 240, "editable": False},
                        {"field": "reviewers", "flex": 1, "editable": True},
                    ],
                    ctx.can("assign_reviewers"),
                ),
                rowData=_reviewer_rows(ctx),
                getRowId="params.data.type_id",
                **_grid_kw(ctx.can("assign_reviewers")),
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
        gap="xs",
    )


# ---------------------------------------------------------- grids to pack
def _split(v: Any) -> list[str]:
    return [x.strip() for x in str(v or "").replace(";", ",").split(",") if x.strip()]


def _int_or_none(v: Any) -> int | None:
    text = str(v if v is not None else "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        raise ValueError(f"{text!r} is not a whole number") from None


def _json_cell(value: Any, what: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        out = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"the properties of {what} are not valid JSON ({exc})") from None
    if not isinstance(out, dict):
        raise ValueError(f"the properties of {what} must be a JSON object")
    return out


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


def _attr_item(a: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": a["name"],
        "label": a.get("label", ""),
        "type": a.get("type") or "string",
        "required": bool(a.get("required")),
        "description": a.get("description", ""),
        "sensitivity": a.get("sensitivity", ""),
        "multiple": bool(a.get("multiple")),
        "group": a.get("group", "") or "",
        "help": a.get("help", "") or "",
        "unit": a.get("unit", "") or "",
        "pattern": a.get("pattern", "") or "",
        "properties": _json_cell(a.get("properties"), f"attribute {a['name']}"),
    }
    if _split(a.get("enum")):
        item["enum"] = _split(a.get("enum"))
    for k in ("default", "min", "max"):
        v = a.get(k)
        if v not in (None, ""):
            if k == "default" and item["type"] == "boolean" and isinstance(v, str):
                v = v.strip().lower() in ("true", "yes", "1")
            item[k] = v
    return item


def _pack_from_grids(
    pack: Pack,
    types: list[dict],
    rels: list[dict],
    attrs: list[dict],
    domains: list[dict] | None = None,
    domain_notation: list[dict] | None = None,
    type_notation: list[dict] | None = None,
    groups: list[dict] | None = None,
) -> dict[str, Any]:
    d = pack_to_dict(pack)
    if groups is not None:
        d["attribute_groups"] = [
            {
                "id": r["id"],
                "name": r.get("name") or r["id"],
                "description": r.get("description", "") or "",
                "properties": _json_cell(r.get("properties"), f"attribute group {r['id']}"),
            }
            for r in groups
            if r.get("id")
        ]
    keep_domain_notation = {x.id: dict(x.notation) for x in pack.domains}
    if domains is not None:
        d["domains"] = [
            {
                "id": r["id"],
                "name": r.get("name") or r["id"],
                "description": r.get("description", "") or "",
                "notation": keep_domain_notation.get(r["id"], {}),
                "properties": _json_cell(r.get("properties"), f"domain {r['id']}"),
            }
            for r in domains
            if r.get("id")
        ]
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
    keep_notation = {t.id: dict(t.notation) for t in pack.element_types}
    type_ids = {t["id"] for t in types if t.get("id")}
    rel_ids = {r["id"] for r in rels if r.get("id")}
    attr_by_owner: dict[str, list[dict]] = {}
    for a in attrs:
        if not a.get("name"):
            continue
        owner = (a.get("type_id") or "").strip()
        if owner and owner not in type_ids and owner not in rel_ids:
            raise ValueError(
                f"attribute {a['name']} belongs to {owner!r}, which is neither an element type nor a relationship type"
            )
        attr_by_owner.setdefault(owner, []).append(_attr_item(a))
    d["common_attributes"] = attr_by_owner.get("", [])
    d["element_types"] = []
    for t in types:
        if not t.get("id"):
            continue
        d["element_types"].append(
            {
                "id": t["id"],
                "name": t.get("name") or t["id"],
                "plural": t.get("plural", ""),
                "supertype": t.get("supertype") or None,
                "active": bool(t.get("active", True)),
                "abstract": bool(t.get("abstract", False)),
                "level": t.get("level") or "enterprise",
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
                "attributes": attr_by_owner.get(t["id"], []),
                "properties": _json_cell(t.get("properties"), f"element type {t['id']}"),
            }
        )
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
            "src_max": _int_or_none(r.get("src_max")),
            "dst_max": _int_or_none(r.get("dst_max")),
            "attributes": attr_by_owner.get(r["id"], []),
            "properties": _json_cell(r.get("properties"), f"relationship type {r['id']}"),
        }
        for r in rels
        if r.get("id")
    ]
    return d


GRID_STATES = [
    State(ids.MM_TYPES_GRID, "virtualRowData"),
    State(ids.MM_TYPES_GRID, "rowData"),
    State(ids.MM_RELS_GRID, "virtualRowData"),
    State(ids.MM_RELS_GRID, "rowData"),
    State(ids.MM_ATTRS_GRID, "virtualRowData"),
    State(ids.MM_ATTRS_GRID, "rowData"),
    State(ids.MM_DOMAINS_GRID, "virtualRowData"),
    State(ids.MM_DOMAINS_GRID, "rowData"),
    State(ids.MM_GROUPS_GRID, "virtualRowData"),
    State(ids.MM_GROUPS_GRID, "rowData"),
    State(ids.MM_NOTATION_DOMAINS_GRID, "virtualRowData"),
    State(ids.MM_NOTATION_DOMAINS_GRID, "rowData"),
    State(ids.MM_NOTATION_TYPES_GRID, "virtualRowData"),
    State(ids.MM_NOTATION_TYPES_GRID, "rowData"),
]


def _pack_from_states(pack: Pack, grids: tuple) -> dict[str, Any]:
    rows = _rows_from_states(grids)
    return _pack_from_grids(
        pack,
        rows["types"],
        rows["rels"],
        rows["attrs"],
        rows["domains"],
        rows["notation_domains"],
        rows["notation_types"],
        rows["groups"],
    )


DELETABLE = {
    "types": "element type",
    "rels": "relationship type",
    "attrs": "attribute",
    "domains": "domain",
    "groups": "attribute group",
}


def _rows_from_states(grids: tuple) -> dict[str, list[dict]]:
    """Every grid of the Manage and Notation tabs as it now stands, edits and all."""
    t_v, t_r, r_v, r_r, a_v, a_r, d_v, d_r, g_v, g_r, dn_v, dn_r, tn_v, tn_r = grids
    return {
        "types": _all_rows(t_v, t_r, "id"),
        "rels": _all_rows(r_v, r_r, "id"),
        "attrs": _all_rows(a_v, a_r, "type_id", "name"),
        "domains": _all_rows(d_v, d_r, "id"),
        "groups": _all_rows(g_v, g_r, "id"),
        "notation_types": _all_rows(tn_v, tn_r, "id"),
        "notation_domains": _all_rows(dn_v, dn_r, "id"),
    }


def remove_rows(
    which: str, picked: list[dict], rows: dict[str, list[dict]]
) -> tuple[dict[str, list[dict]], list[str]]:
    """The grids with the ticked rows taken out, and a sentence per consequence.

    What the metamodel could not hold without the row goes with it — a relationship type
    whose end type is gone, an attribute whose owner is gone, the notation of a type or a
    domain that is gone. What can stand without it is kept and the reference cleared: a
    sub-type of a deleted supertype, a type whose domain is deleted. So deleting one row
    never quietly deletes a branch of the model nobody asked about, and the version that
    is left is one the metamodel accepts. Nothing here touches the store.
    """
    out = {k: list(v) for k, v in rows.items()}
    said: list[str] = []
    gone_types = {r.get("id") for r in picked} if which == "types" else set()
    gone_rels = {r.get("id") for r in picked} if which == "rels" else set()
    gone_attrs = {(r.get("type_id") or "", r.get("name")) for r in picked} if which == "attrs" else set()
    gone_domains = {r.get("id") for r in picked} if which == "domains" else set()
    gone_groups = {r.get("id") for r in picked} if which == "groups" else set()

    if gone_types:
        out["types"] = [r for r in out["types"] if r.get("id") not in gone_types]
        out["notation_types"] = [r for r in out["notation_types"] if r.get("id") not in gone_types]
        ended = [r for r in out["rels"] if gone_types & {r.get("source"), r.get("target")}]
        gone_rels |= {r.get("id") for r in ended}
        orphans = [r for r in out["types"] if r.get("supertype") in gone_types]
        for r in orphans:
            r["supertype"] = ""
        said.append(f"{len(gone_types)} element type(s)")
        if ended:
            said.append(f"{len(ended)} relationship type(s) that named one of them as an end")
        if orphans:
            said.append(f"the supertype of {len(orphans)} sub-type(s), cleared rather than deleted")
    if gone_rels:
        out["rels"] = [r for r in out["rels"] if r.get("id") not in gone_rels]
        if which == "rels":
            said.append(f"{len(gone_rels)} relationship type(s)")
    if gone_types or gone_rels:
        owned = [r for r in out["attrs"] if (r.get("type_id") or "") in (gone_types | gone_rels)]
        if owned:
            out["attrs"] = [r for r in out["attrs"] if r not in owned]
            said.append(f"{len(owned)} attribute(s) of what went with them")
    if gone_attrs:
        out["attrs"] = [
            r for r in out["attrs"] if ((r.get("type_id") or ""), r.get("name")) not in gone_attrs
        ]
        said.append(f"{len(gone_attrs)} attribute(s)")
    if gone_domains:
        out["domains"] = [r for r in out["domains"] if r.get("id") not in gone_domains]
        out["notation_domains"] = [r for r in out["notation_domains"] if r.get("id") not in gone_domains]
        homeless = [r for r in out["types"] if r.get("domain") in gone_domains]
        for r in homeless:
            r["domain"] = ""
        said.append(f"{len(gone_domains)} domain(s)")
        if homeless:
            said.append(f"the domain of {len(homeless)} element type(s), cleared rather than deleted")
    if gone_groups:
        out["groups"] = [r for r in out.get("groups", []) if r.get("id") not in gone_groups]
        ungrouped = [r for r in out["attrs"] if r.get("group") in gone_groups]
        for r in ungrouped:
            r["group"] = ""
        said.append(f"{len(gone_groups)} attribute group(s)")
        if ungrouped:
            said.append(f"the group of {len(ungrouped)} attribute(s), cleared rather than deleted")
    return out, said


def _in_use(ctx: AppContext, which: str, picked: list[dict]) -> str:
    """What the organisation already holds of the element types being deleted, or nothing.

    The metamodel and the content are separate: a version that drops a type still saves,
    and the elements that carry the type only become invalid when the version is applied
    (the compatibility check reports them then). Saying it here is the difference between
    a deletion the architect meant and one they find out about a screen later.
    """
    if which != "types":
        return ""
    gone = {r.get("id") for r in picked}
    try:
        counts = ctx.backend.count_by_type()
    except Exception:  # noqa: BLE001 — a count is a courtesy; never fail the deletion for it
        return ""
    held = sum(n for type_id, n in counts.items() if type_id in gone)
    if not held:
        return ""
    return (
        f" {held} element(s) in {ctx.organisation().name} are of what you deleted: applying this "
        "version here would leave them invalid, and the check before it will say so."
    )


def _shown(ctx: AppContext, ref: str | None) -> Registry:
    """The registry of the version the page shows; the applied one when the store no longer holds it."""
    try:
        return Registry(ctx.metamodels.get(ref)) if ref else ctx.registry
    except NotFoundError:
        return ctx.registry


# --------------------------------------------------------------- callbacks
def register(app: dash.Dash) -> None:
    body_outputs = [
        Output(ids.MM_FEEDBACK, "children", allow_duplicate=True),
        Output(ids.MM_BODY, "children", allow_duplicate=True),
        Output(ids.MM_SUBTITLE, "children", allow_duplicate=True),
        Output(ids.MM_VERSION, "data", allow_duplicate=True),
        Output(ids.MM_VERSION_SELECT, "data", allow_duplicate=True),
        Output(ids.MM_VERSION_SELECT, "value", allow_duplicate=True),
        # Loading a file and creating a draft can both change what the organisation applies,
        # and the header says which version that is. It is written wherever the page is.
        Output(ids.PACK_BADGE, "children", allow_duplicate=True),
    ]

    def rerender(ctx: AppContext, ref: str, tab: str, list_tab: str, message: Any = None) -> tuple:
        reg = _shown(ctx, ref)
        return (
            message,
            _body(ctx, reg, tab or "manage", list_tab or FIRST_LIST),
            _counts(reg, ctx),
            reg.pack.ref,
            _version_options(ctx),
            reg.pack.ref,
            layout.pack_badge(ctx.pack_label()),
        )

    @app.callback(
        *body_outputs,
        Input(ids.MM_VERSION_SELECT, "value"),
        State(ids.MM_VERSION, "data"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
    )
    def switch_version(value, shown, tab, list_tab):
        if not value or value == shown:
            return (no_update,) * 7
        ctx = get_context()
        try:
            out = rerender(ctx, value, tab, list_tab)
        except NotFoundError as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 6
        return out

    @app.callback(
        Output(gp.store_id("mm"), "data"),
        Input(ids.MM_DOMAIN_FILTER, "value"),
        Input(ids.MM_GRAPH_INACTIVE, "checked"),
        State(ids.MM_VERSION, "data"),
        prevent_initial_call=True,
    )
    def filter_graph(domain, inactive, ref):
        return gp.raw_from_types(_shown(get_context(), ref), domain or None, bool(inactive))

    @app.callback(
        Output(ids.MM_DETAIL, "children"),
        Input(gp.cy_id("mm"), "tapNodeData"),
        State(ids.MM_VERSION, "data"),
        prevent_initial_call=True,
    )
    def detail(data, ref):
        if not data or not gp.is_element_node(data):
            return no_update
        return _detail(_shown(get_context(), ref), gp.element_id_of(data))

    @app.callback(
        Output({"type": ids.MERMAID_SRC, "id": ids.MM_VIEW}, "children"),
        Output({"type": ids.MERMAID_LEGEND, "id": ids.MM_VIEW}, "children"),
        Input(ids.MM_VIEW_DOMAIN, "value"),
        Input(ids.MM_VIEW_INACTIVE, "checked"),
        State(ids.MM_VERSION, "data"),
        prevent_initial_call=True,
    )
    def redraw_view(domain, inactive, ref):
        reg = _shown(get_context(), ref)
        view = view_from_metamodel(reg, domain or None, bool(inactive))
        return to_mermaid(view, direction="BT", legend=True), layer_chips(view)

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.MM_VIEW_MD, "n_clicks"),
        Input(ids.MM_VIEW_DRAWIO, "n_clicks"),
        State(ids.MM_VIEW_DOMAIN, "value"),
        State(ids.MM_VIEW_INACTIVE, "checked"),
        State(ids.MM_VERSION, "data"),
        State({"type": ids.MERMAID_POS, "id": ids.MM_VIEW}, "data"),
        prevent_initial_call=True,
    )
    def download_view(n_md, n_drawio, domain, inactive, ref, positions):
        trigger = dash_ctx.triggered_id
        if (trigger == ids.MM_VIEW_MD and not n_md) or (trigger == ids.MM_VIEW_DRAWIO and not n_drawio):
            return no_update
        reg = _shown(get_context(), ref)
        view = view_from_metamodel(reg, domain or None, bool(inactive))
        # Named for the reader who has to find the file afterwards: an opaque identifier in a
        # file name is a file nobody can pick out of a folder (decision 0021).
        stem = f"{slugify(reg.pack.name) if reg.pack.name else reg.pack.id}-{reg.pack.version}-metamodel"
        if trigger == ids.MM_VIEW_MD:
            return dcc.send_string(to_markdown(view, legend=True), f"{stem}.md")
        return dcc.send_string(to_drawio(view, positions=positions or None), f"{stem}.drawio")

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
                        "added": True,
                        "name": "New type",
                        "plural": "",
                        "supertype": "",
                        "domain": "",
                        "provenance": "",
                        "prefix": "",
                        "active": True,
                        "abstract": False,
                        "level": "enterprise",
                        "description": "",
                        "properties": "",
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
                        "src_max": "",
                        "dst_max": "",
                        "description": "",
                        "properties": "",
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
                    _attr_row(
                        type(
                            "A",
                            (),
                            dict(
                                name=f"new_attribute_{n}",
                                label="",
                                type="string",
                                required=False,
                                enum=None,
                                default=None,
                                multiple=False,
                                group="",
                                help="",
                                unit="",
                                pattern="",
                                min=None,
                                max=None,
                                sensitivity="",
                                description="",
                                properties={},
                            ),
                        )(),
                        "",
                        added=True,
                    )
                ]
            }
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_DOMAINS_GRID, "rowTransaction"),
        Input(ids.MM_ADD_DOMAIN, "n_clicks"),
        prevent_initial_call=True,
    )
    def add_domain(n):
        return (
            {"add": [{"id": f"new_domain_{n}", "name": "New domain", "description": "", "properties": ""}]}
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_GROUPS_GRID, "rowTransaction"),
        Input(ids.MM_ADD_GROUP, "n_clicks"),
        prevent_initial_call=True,
    )
    def add_group(n):
        return (
            {"add": [{"id": f"new_group_{n}", "name": "New group", "description": "", "properties": ""}]}
            if n
            else no_update
        )

    @app.callback(
        Output(ids.MM_FEEDBACK, "children", allow_duplicate=True),
        Output(ids.MM_TYPES_GRID, "rowData"),
        Output(ids.MM_RELS_GRID, "rowData"),
        Output(ids.MM_ATTRS_GRID, "rowData"),
        Output(ids.MM_DOMAINS_GRID, "rowData"),
        Output(ids.MM_GROUPS_GRID, "rowData"),
        Output(ids.MM_NOTATION_TYPES_GRID, "rowData"),
        Output(ids.MM_NOTATION_DOMAINS_GRID, "rowData"),
        Input(ids.MM_DEL_TYPE, "n_clicks"),
        Input(ids.MM_DEL_REL, "n_clicks"),
        Input(ids.MM_DEL_ATTR, "n_clicks"),
        Input(ids.MM_DEL_DOMAIN, "n_clicks"),
        Input(ids.MM_DEL_GROUP, "n_clicks"),
        State(ids.MM_TYPES_GRID, "selectedRows"),
        State(ids.MM_RELS_GRID, "selectedRows"),
        State(ids.MM_ATTRS_GRID, "selectedRows"),
        State(ids.MM_DOMAINS_GRID, "selectedRows"),
        State(ids.MM_GROUPS_GRID, "selectedRows"),
        *GRID_STATES,
        prevent_initial_call=True,
    )
    def delete_rows(*args):
        """Take the ticked rows out of the version being edited, with whatever depended on them.

        Nothing is stored here: the grids are rewritten and the save writes the version, so a
        deletion is undone by leaving the page. `remove_rows` decides what goes with what.
        """
        buttons = (ids.MM_DEL_TYPE, ids.MM_DEL_REL, ids.MM_DEL_ATTR, ids.MM_DEL_DOMAIN, ids.MM_DEL_GROUP)
        clicks, selections, grids = args[:5], args[5:10], args[10:]
        trigger = dash_ctx.triggered_id
        if trigger not in buttons or not clicks[buttons.index(trigger)]:
            return (no_update,) * 8
        ctx = get_context()
        if not ctx.can("edit_metamodel"):
            return (alert(f"{a_role(ctx.role_label())} may not edit the metamodel.", "red"),) + (
                no_update,
            ) * 7
        which = ("types", "rels", "attrs", "domains", "groups")[buttons.index(trigger)]
        picked = list(selections[buttons.index(trigger)] or [])
        if not picked:
            return (
                alert(f"Tick the {DELETABLE[which]}s to delete first: nothing is ticked.", "yellow"),
                *(no_update,) * 7,
            )
        rows, said = remove_rows(which, picked, _rows_from_states(grids))
        return (
            alert(
                "Taken out of the grids: "
                + "; ".join(said)
                + ". Nothing is stored yet — save to write it into the version, or leave the page "
                "without saving to put it all back." + _in_use(ctx, which, picked),
                "yellow",
            ),
            rows["types"],
            rows["rels"],
            rows["attrs"],
            rows["domains"],
            rows["groups"],
            rows["notation_types"],
            rows["notation_domains"],
        )

    @app.callback(
        *body_outputs,
        Output(ids.MM_DRAFT_MODAL, "opened"),
        Output(ids.MM_DRAFT_VERSION, "value"),
        Input(ids.MM_SAVE, "n_clicks"),
        *GRID_STATES,
        State(ids.MM_VERSION, "data"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.MM_SAVE, "loading"), True, False)],
    )
    def save(n, *args):
        if not n:
            return (no_update,) * 9
        *grids, ref, tab, list_tab = args
        ctx = get_context()
        if not ctx.can("edit_metamodel"):
            return (alert(f"{a_role(ctx.role_label())} may not edit the metamodel.", "red"),) + (
                no_update,
            ) * 8
        try:
            shown = ctx.metamodels.get(ref)
        except NotFoundError as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 8
        if shown.status != "draft":
            # Frozen: the edits go into a draft, named in the dialog that opens.
            return (no_update,) * 7 + (True, ctx.metamodels.suggest_version(shown.id))
        try:
            pack = pack_from_dict(_pack_from_states(shown, tuple(grids)))
            pack.version, pack.status, pack.derived_from = shown.version, "draft", shown.derived_from
            ctx.metamodels.save(pack, ctx.actor)
            ctx.reload_registry()
        except (ValueError, KeyError, ConflictError, Forbidden) as exc:
            return (alert(f"Not saved: {exc}", "red"),) + (no_update,) * 8
        return rerender(
            ctx,
            pack.ref,
            tab,
            list_tab,
            alert(
                f"Version {pack.version} saved: {len(pack.element_types)} types, "
                f"{len(pack.relationship_types)} relationship types.",
                "green",
            ),
        ) + (False, no_update)

    @app.callback(
        *body_outputs,
        Output(ids.MM_DRAFT_MODAL, "opened", allow_duplicate=True),
        Output(ids.MM_DRAFT_FEEDBACK, "children"),
        Input(ids.MM_DRAFT_SAVE, "n_clicks"),
        *GRID_STATES,
        State(ids.MM_DRAFT_VERSION, "value"),
        State(ids.MM_DRAFT_NOTES, "value"),
        State(ids.MM_DRAFT_APPLY, "checked"),
        State(ids.MM_VERSION, "data"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.MM_DRAFT_SAVE, "loading"), True, False)],
    )
    def create_draft(n, *args):
        if not n:
            return (no_update,) * 9
        *grids, version, notes, apply_here, ref, tab, list_tab = args
        ctx = get_context()
        try:
            shown = ctx.metamodels.get(ref)
            pack = pack_from_dict(_pack_from_states(shown, tuple(grids)))
            pack.version = (version or "").strip()
            pack.status, pack.derived_from, pack.notes = "draft", shown.ref, notes or ""
            if any(v.version == pack.version for v in ctx.metamodels.versions(pack.id)):
                raise ConflictError(f"version {pack.version} of {pack.id} already exists; pick another name")
            ctx.metamodels.save(pack, ctx.actor)
            message = f"Draft {pack.name} {pack.version} created from {shown.name} {shown.version}."
            if apply_here:
                report = ctx.orgs.apply(ctx.org(), pack.ref, ctx.actor, force=True)
                message += f" Applied to {ctx.organisation().name}: {report.summary()}."
            ctx.reload_registry()
        except (ValueError, KeyError, ConflictError, Forbidden, NotFoundError) as exc:
            return (no_update,) * 7 + (no_update, alert(f"Not created: {exc}", "red"))
        return rerender(ctx, pack.ref, tab, list_tab, alert(message, "green")) + (False, None)

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.MM_EXPORT, "n_clicks"),
        State(ids.MM_VERSION, "data"),
        prevent_initial_call=True,
    )
    def export(n, ref):
        if not n:
            return no_update
        pack = _shown(get_context(), ref).pack
        stem = slugify(pack.name) if pack.name else pack.id
        return dcc.send_string(pack_yaml(pack), f"{stem}-{pack.version}-metamodel.yaml")

    @app.callback(
        *body_outputs,
        Input(ids.MM_RELOAD, "contents"),
        State(ids.MM_RELOAD, "filename"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
    )
    def reload(contents, filename, tab, list_tab):
        if not contents:
            return (no_update,) * 7
        ctx = get_context()
        if not ctx.can("edit_metamodel"):
            # Loading writes a version into the store: it is an edit, and the button being
            # visible is not permission to make one.
            return (alert(f"{a_role(ctx.role_label())} may not edit the metamodel.", "red"),) + (
                no_update,
            ) * 6
        try:
            _, b64 = contents.split(",", 1)
            data = yaml.safe_load(base64.b64decode(b64).decode("utf-8")) or {}
            read = pack_from_dict(data)
            suspect = suspect_split_descriptions(read)
            # What the store called this version before the file arrived, so a file that only
            # renames a frozen version is reported as the rename it is (decision 0022).
            try:
                was = ctx.metamodels.version(read.ref).name
            except NotFoundError:
                was = ""
            pack = ctx.metamodels.save(read, ctx.actor)
        except (OSError, ValueError, KeyError, yaml.YAMLError, ConflictError, Forbidden) as exc:
            return (alert(f"{filename or 'File'} not loaded: {exc}", "red"),) + (no_update,) * 6
        # The status the STORE holds, not the one the file claims: a file that renames a
        # published version may say `draft` in its header, and the version stays published.
        stored = ctx.metamodels.version(pack.ref)
        message = f"Loaded {pack.name} {pack.version} ({stored.status}) from {filename}."
        if was and was != pack.name:
            message += f" Renamed from {was}; what it defines is unchanged."
        colour = "green"
        if suspect:
            # The file loaded; something in it looks mis-typed, and saying nothing would
            # leave half a description in a property nobody reads.
            message += f" {len(suspect)} value(s) look mis-typed: " + " ".join(suspect[:3])
            colour = "yellow"
        org = ctx.organisation()
        if org.pack_ref != pack.ref:
            try:
                report = ctx.orgs.apply(org.org_id, pack.ref, ctx.actor)
                message += f" Applied to {org.name}: {report.summary()}."
            except (ConflictError, Forbidden) as exc:
                message += f" Not applied to {org.name}: {exc}"
                colour = "yellow"
        ctx.reload_registry()
        return rerender(ctx, pack.ref, tab, list_tab, alert(message, colour))

    @app.callback(
        *body_outputs,
        Output(ids.MM_CONFIRM_MODAL, "opened"),
        Output(ids.MM_CONFIRM_TEXT, "children"),
        Output(ids.MM_CONFIRM_STORE, "data"),
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Output(ids.MM_RENAME_MODAL, "opened"),
        Output(ids.MM_RENAME_NAME, "value"),
        Output(ids.MM_RENAME_REF, "data"),
        Input({"type": ids.MM_VER_ACTION, "action": ALL, "ref": ALL}, "n_clicks"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
    )
    def version_action(clicks, tab, list_tab):
        trigger = dash_ctx.triggered_id
        if not isinstance(trigger, dict) or not any(n for n in (clicks or []) if n):
            return (no_update,) * 14
        ctx = get_context()
        action, ref = trigger.get("action"), trigger.get("ref")
        quiet = (no_update,) * 7
        try:
            if action == "show":
                return rerender(ctx, ref, tab, list_tab) + (no_update,) * 7
            if action == "export":
                pack = ctx.metamodels.get(ref)
                # Named for the reader who has to find the file afterwards, not keyed: an
                # opaque identifier in a file name is a file nobody can pick out of a folder.
                stem = slugify(pack.name) if pack.name else pack.id
                return (
                    quiet
                    + (
                        no_update,
                        no_update,
                        no_update,
                        dcc.send_string(pack_yaml(pack), f"{stem}-{pack.version}-metamodel.yaml"),
                    )
                    + (no_update,) * 3
                )
            if action == "draft":
                source = ctx.metamodels.version(ref)
                draft = ctx.metamodels.draft(ref, ctx.actor)
                ctx.reload_registry()
                return (
                    rerender(
                        ctx,
                        draft.ref,
                        "manage",
                        list_tab,
                        # Named for the reader, with the canonical reference beside it for
                        # whoever pastes it into an address or a command — the same rule the
                        # command line follows.
                        alert(
                            f"Draft {draft.name} {draft.version} created from "
                            f"{source.name} {source.version} ({draft.ref}); it is shown now.",
                            "green",
                        ),
                    )
                    + (no_update,) * 7
                )
            if action == "publish":
                v = ctx.metamodels.publish(ref, ctx.actor)
                ctx.reload_registry()
                return (
                    rerender(
                        ctx,
                        ref,
                        tab,
                        list_tab,
                        alert(f"{v.label} is published: what it defines is frozen from now on.", "green"),
                    )
                    + (no_update,) * 7
                )
            if action == "rename":
                v = ctx.metamodels.version(ref)
                return quiet + (no_update,) * 4 + (True, v.name, ref)
            if action in ("retire", "delete"):
                label = ctx.metamodels.version(ref).label
                what = (
                    f"Retire {label}? It stays in the store for the record but can no longer be applied."
                    if action == "retire"
                    else f"Delete {label}? A draft nobody applies is removed for good."
                )
                return (
                    quiet
                    + (True, dmc.Text(what, size="sm"), {"action": action, "ref": ref}, no_update)
                    + (no_update,) * 3
                )
        except (ConflictError, Forbidden, NotFoundError, ValueError) as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 13
        return (no_update,) * 14

    @app.callback(
        *body_outputs,
        Output(ids.MM_RENAME_MODAL, "opened", allow_duplicate=True),
        Output(ids.MM_RENAME_FEEDBACK, "children"),
        Input(ids.MM_RENAME_SAVE, "n_clicks"),
        State(ids.MM_RENAME_NAME, "value"),
        State(ids.MM_RENAME_REF, "data"),
        State(ids.MM_VERSION, "data"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
    )
    def rename_version(n, name, ref, shown, tab, list_tab):
        """Write the new name, and leave the reader on the version they were looking at.

        The dialog keeps its own feedback so a refusal — an empty name, or a role that may
        not edit the metamodel — is answered where the reader is typing rather than behind
        a dialog they then have to close to read.
        """
        if not n or not ref:
            return (no_update,) * 9
        ctx = get_context()
        try:
            v = ctx.metamodels.rename(ref, name or "", ctx.actor)
        except (ConflictError, Forbidden, NotFoundError, ValueError) as exc:
            return (no_update,) * 7 + (no_update, alert(str(exc), "red"))
        # The registry holds the pack's name too, so the header and every subtitle are stale
        # until it is read again — but only when the version renamed is the one being shown.
        if ref == shown:
            ctx.reload_registry()
        return rerender(
            ctx,
            shown,
            tab,
            list_tab,
            alert(f"Renamed to {v.name}. Nothing it defines changed, and no organisation moved.", "green"),
        ) + (False, None)

    @app.callback(
        *body_outputs,
        Output(ids.MM_CONFIRM_MODAL, "opened", allow_duplicate=True),
        Input(ids.MM_CONFIRM_YES, "n_clicks"),
        State(ids.MM_CONFIRM_STORE, "data"),
        State(ids.MM_VERSION, "data"),
        State(ids.MM_TABS, "value"),
        State(ids.MM_LISTS, "value"),
        prevent_initial_call=True,
    )
    def confirmed(n, pending, shown, tab, list_tab):
        if not n or not pending:
            return (no_update,) * 8
        ctx = get_context()
        action, ref = pending.get("action"), pending.get("ref")
        if action not in ("retire", "delete"):
            # Anything else is a dialog nobody wrote: never fall through to deleting a version.
            return (no_update,) * 7 + (False,)
        try:
            # Named before anything happens to it: a deleted version cannot be looked up
            # afterwards, and a key is not a name anyway (decision 0021).
            label = ctx.metamodels.version(ref).label
            if action == "retire":
                ctx.metamodels.retire(ref, ctx.actor)
                message = f"{label} is retired."
            else:
                ctx.metamodels.delete(ref, ctx.actor)
                message = f"{label} deleted."
            ctx.reload_registry()
        except (ConflictError, Forbidden, NotFoundError) as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 6 + (False,)
        show = shown if not (action == "delete" and shown == ref) else ctx.registry.pack.ref
        return rerender(ctx, show, tab, list_tab, alert(message, "green")) + (False,)

    @app.callback(
        Output(ids.MM_CMP_RESULT, "children"),
        Input(ids.MM_CMP_RUN, "n_clicks"),
        State(ids.MM_CMP_A, "value"),
        State(ids.MM_CMP_B, "value"),
        prevent_initial_call=True,
    )
    def compare(n, a, b):
        if not n:
            return no_update
        if not a or not b:
            return alert("Pick two versions to compare.", "yellow")
        try:
            return diff_table(get_context().metamodels.diff(a, b))
        except NotFoundError as exc:
            return alert(str(exc), "red")

    @app.callback(
        Output({"type": ids.MERMAID_SRC, "id": ids.MM_NOTATION_PREVIEW}, "children"),
        Output({"type": ids.MERMAID_LEGEND, "id": ids.MM_NOTATION_PREVIEW}, "children"),
        Output(ids.MM_NOTATION_NOTE, "children"),
        Output(ids.MM_NOTATION_SWATCHES, "children"),
        Input(ids.MM_NOTATION_DOMAINS_GRID, "cellValueChanged"),
        Input(ids.MM_NOTATION_TYPES_GRID, "cellValueChanged"),
        *GRID_STATES,
        State(ids.MM_VERSION, "data"),
        prevent_initial_call=True,
    )
    def preview(_d, _t, *args):
        """The preview follows every edit before anything is saved."""
        *grids, ref = args
        ctx = get_context()
        try:
            reg = Registry(pack_from_dict(_pack_from_states(_shown(ctx, ref).pack, tuple(grids))))
        except (ValueError, KeyError) as exc:
            # Freezing in silence looks like an edit that did not take. Say which grid is
            # holding the preview back, so the reader knows what to fix.
            return (
                no_update,
                no_update,
                alert(
                    f"The preview cannot be drawn from the grids as they stand: {exc}. "
                    "It will follow again once that is fixed.",
                    "yellow",
                ),
                no_update,
            )
        view = notation_view(reg)
        return to_mermaid(view, direction="LR"), layer_chips(view), None, notation_swatches(reg)

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
