"""One graph panel for every network view in the app.

Nodes are elements (or element types, on the Metamodel page); a "group by" choice nests
them in labelled boxes (domain, layer, type, status, source system) and a compound-aware
layout keeps the boxes apart and the nodes inside them. Colours and stereotypes come
from the pack's notation, never from code (principle `P5`).

The panel keeps its raw graph in a store; the callbacks registered here turn it into
Cytoscape elements whenever the grouping or the layout changes, so a page only has to
write the store.
"""

from __future__ import annotations

import math
from typing import Any

import dash
import dash_cytoscape as cyto
import dash_mantine_components as dmc
from dash import MATCH, Input, Output, State, dcc, html

from ea.metamodel.registry import Registry
from ea.ui.components import darken, domain_hex, icon
from ea.views.mermaid import LAYER_STYLE
from ea.views.model import LAYER_TITLES

GROUP_OPTIONS = [
    {"value": "", "label": "No grouping"},
    {"value": "domain", "label": "Group by domain"},
    {"value": "layer", "label": "Group by layer"},
    {"value": "type", "label": "Group by element type"},
    {"value": "status", "label": "Group by status"},
    {"value": "source", "label": "Group by source system"},
    {"value": "target", "label": "Group by target state"},
]
LAYOUT_OPTIONS = [
    {"value": "grouped", "label": "Grouped grid"},
    {"value": "organic", "label": "Organic"},
    {"value": "concentric", "label": "Concentric"},
    {"value": "breadthfirst", "label": "Breadth-first"},
    {"value": "circle", "label": "Circle"},
]
STATUS_HEX = {"approved": "#69db7c", "draft": "#ffa94d", "retired": "#ff8787"}
SOURCE_PALETTE = ["#74c0fc", "#b197fc", "#63e6be", "#ffd43b", "#ffa8a8", "#a5d8ff", "#e599f7"]
NODE_W, NODE_H, NODE_GAP, GROUP_PAD, GROUP_GAP = 170, 48, 26, 40, 70

EMPTY: dict[str, Any] = {"nodes": [], "edges": [], "centre": None}

# Pattern-matching ids: one panel per page, several panels never collide.
CY, STORE, GROUP, LAYOUT, FIT, LEGEND = "gp-cy", "gp-store", "gp-group", "gp-layout", "gp-fit", "gp-legend"
ZOOM_IN, ZOOM_OUT, FULL = "gp-zoom-in", "gp-zoom-out", "gp-full"


def is_element_node(data: dict[str, Any] | None) -> bool:
    """True for a node that stands for an element or a type (not a group box, not the ANY diamond)."""
    return bool((data or {}).get("element_id"))


def element_id_of(data: dict[str, Any] | None) -> str:
    return (data or {}).get("element_id") or ""


def cy_id(panel_id: str) -> dict[str, str]:
    return {"type": CY, "id": panel_id}


def store_id(panel_id: str) -> dict[str, str]:
    return {"type": STORE, "id": panel_id}


# ------------------------------------------------------------------ raw graph
def raw_from_subgraph(registry: Registry, sub: dict[str, Any]) -> dict[str, Any]:
    """The neighbourhood/impact shape of GraphService as the panel's raw graph."""
    nodes = []
    for n in sub["nodes"]:
        t = registry.get_type(n.get("type_id", ""))
        notation = registry.notation(n.get("type_id", ""))
        nodes.append(
            {
                "id": n["element_id"],
                "name": n.get("name") or n["element_id"],
                "kind": "element",
                "type_id": n.get("type_id", ""),
                "type_name": n.get("type_name") or n.get("type_id", ""),
                "domain": t.domain if t else "",
                "layer": notation.get("layer", "other"),
                "stereotype": notation.get("stereotype", ""),
                "status": n.get("status", "") or "",
                "source": n.get("source", "") or "",
                "depth": n.get("depth", 0),
                "current_state": n.get("current_state", "") or "",
                "target_state": n.get("target_state", "") or "",
            }
        )
    edges = [
        {
            "id": e.get("relationship_id") or f"{e['src_id']}->{e['dst_id']}",
            "src": e["src_id"],
            "dst": e["dst_id"],
            "label": e.get("label", ""),
            "kind": "rel",
        }
        for e in sub["edges"]
    ]
    return {"nodes": nodes, "edges": edges, "centre": sub.get("centre")}


def raw_from_types(
    registry: Registry, domain: str | None = None, include_inactive: bool = False
) -> dict[str, Any]:
    """The metamodel's type graph as the panel's raw graph (ANY as a diamond, sub-type edges dashed)."""
    from ea.models import ANY

    types = [
        t
        for t in registry.pack.element_types
        if (t.active or include_inactive) and (not domain or t.domain == domain)
    ]
    ids_ = {t.id for t in types}
    nodes = []
    for t in types:
        notation = registry.notation(t.id)
        nodes.append(
            {
                "id": t.id,
                "name": t.name,
                "kind": "type",
                "type_id": t.id,
                "type_name": t.name,
                "domain": t.domain,
                "layer": notation.get("layer", "other"),
                "stereotype": notation.get("stereotype", ""),
                "status": "active" if t.active else "inactive",
                "source": t.source_of_record.split(";")[0][:40] if t.source_of_record else "",
                "inactive": not t.active,
            }
        )
    edges = []
    need_any = False
    for r in registry.pack.relationship_types:
        s, d = r.source, r.target
        if (s != ANY and s not in ids_) or (d != ANY and d not in ids_):
            continue
        need_any = need_any or s == ANY or d == ANY
        edges.append(
            {
                "id": r.id,
                "src": s if s != ANY else "ANY",
                "dst": d if d != ANY else "ANY",
                "label": r.name,
                "kind": "rel",
            }
        )
    for t in types:
        if t.supertype and t.supertype in ids_:
            edges.append(
                {"id": f"sub:{t.id}", "src": t.id, "dst": t.supertype, "label": "is a", "kind": "sub"}
            )
    if need_any:
        nodes.append(
            {
                "id": "ANY",
                "name": "Any element",
                "kind": "any",
                "type_id": "",
                "type_name": "",
                "domain": "",
                "layer": "other",
                "stereotype": "",
                "status": "",
                "source": "",
            }
        )
    return {"nodes": nodes, "edges": edges, "centre": None}


# --------------------------------------------------------------- elements
def _group_key(n: dict[str, Any], group_by: str, registry: Registry) -> tuple[str, str, str]:
    """(group id, group label, group hex) for a node under a grouping, or ('', '', '') for none."""
    if not group_by or n.get("kind") == "any":
        return "", "", ""
    if group_by == "domain":
        d = next((d for d in registry.pack.domains if d.id == n.get("domain")), None)
        return (
            f"g:domain:{n.get('domain') or 'none'}",
            d.name if d else "No domain",
            domain_hex(registry, n.get("domain", "")),
        )
    if group_by == "layer":
        layer = n.get("layer") or "other"
        return (
            f"g:layer:{layer}",
            LAYER_TITLES.get(layer, layer),
            LAYER_STYLE.get(layer, LAYER_STYLE["other"])[0],
        )
    if group_by == "type":
        return (
            f"g:type:{n.get('type_id') or 'none'}",
            n.get("type_name") or "No type",
            domain_hex(registry, n.get("domain", "")),
        )
    if group_by == "status":
        st = n.get("status") or "unknown"
        return f"g:status:{st}", st, STATUS_HEX.get(st, "#ced4da")
    if group_by == "source":
        src = n.get("source") or "no source"
        idx = sum(ord(c) for c in src) % len(SOURCE_PALETTE)
        return f"g:source:{src}", src, SOURCE_PALETTE[idx]
    if group_by == "target":
        from ea.services.target import TARGET_STYLE, state_label

        st = n.get("target_state") or "undecided"
        return (
            f"g:target:{st}",
            state_label(st, TARGET_STYLE),
            TARGET_STYLE.get(st, TARGET_STYLE["undecided"])["hex"] + "55",
        )
    return "", "", ""


def _node_fill(n: dict[str, Any], registry: Registry) -> str:
    if n.get("kind") == "any":
        return "#dee2e6"
    return (
        domain_hex(registry, n.get("domain", ""))
        if n.get("domain")
        else LAYER_STYLE.get(n.get("layer", "other"), LAYER_STYLE["other"])[0]
    )


def elements(
    registry: Registry, raw: dict[str, Any], group_by: str = "", layout: str = "grouped"
) -> list[dict[str, Any]]:
    """Cytoscape elements for a raw graph: group parents, nodes with fills and labels, edges; positions for the grouped grid."""
    nodes = raw.get("nodes") or []
    centre = raw.get("centre")
    groups: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    node_els: dict[str, dict[str, Any]] = {}
    for n in nodes:
        gid, glabel, ghex = _group_key(n, group_by, registry)
        if gid and gid not in groups:
            groups[gid] = {"id": gid, "label": glabel, "hex": ghex, "members": []}
        if gid:
            groups[gid]["members"].append(n["id"])
        fill = _node_fill(n, registry)
        label = n["name"] if n.get("kind") != "element" else f"{n['name']}\n{n.get('type_name', '')}"
        classes = [n.get("kind", "element")]
        if centre and n["id"] == centre:
            classes.append("centre")
        if n.get("inactive"):
            classes.append("inactive")
        el = {
            "data": {
                "id": f"{group_by or 'n'}:{n['id']}",
                "element_id": "" if n.get("kind") == "any" else n["id"],
                "label": label,
                "name": n["name"],
                "type_id": n.get("type_id", ""),
                "type_name": n.get("type_name", ""),
                "stereotype": n.get("stereotype", ""),
                "layer": n.get("layer", ""),
                "domain": n.get("domain", ""),
                "status": n.get("status", ""),
                "fill": fill,
                "stroke": darken(fill, 0.35),
                "centre": bool(centre and n["id"] == centre),
            },
            "classes": " ".join(classes),
        }
        if gid:
            el["data"]["parent"] = gid
        node_els[n["id"]] = el
    for g in groups.values():
        out.append(
            {
                "data": {
                    "id": g["id"],
                    "label": g["label"],
                    "fill": g["hex"],
                    "stroke": darken(g["hex"], 0.3),
                },
                "classes": "group",
            }
        )
    if layout == "grouped":
        for nid, pos in grouped_grid_positions(nodes, groups).items():
            node_els[nid]["position"] = pos
    prefix = f"{group_by or 'n'}:"
    out.extend(node_els.values())
    ids_ = set(node_els)
    for e in raw.get("edges") or []:
        if e["src"] not in ids_ or e["dst"] not in ids_:
            continue
        out.append(
            {
                "data": {
                    "id": f"{prefix}{e['id']}",
                    "source": f"{prefix}{e['src']}",
                    "target": f"{prefix}{e['dst']}",
                    "label": e.get("label", ""),
                },
                "classes": e.get("kind", "rel"),
            }
        )
    return out


def grouped_grid_positions(
    nodes: list[dict[str, Any]], groups: dict[str, dict[str, Any]]
) -> dict[str, dict[str, float]]:
    """Each group on its own grid, groups packed into rows and columns (the Databricks model viewer's arrangement)."""
    buckets: list[list[str]] = [g["members"] for g in groups.values()]
    grouped_ids = {i for b in buckets for i in b}
    loose = [n["id"] for n in nodes if n["id"] not in grouped_ids]
    if loose:
        buckets.append(loose)
    if not buckets:
        return {}
    sizes = []
    for members in buckets:
        cols = max(1, math.ceil(math.sqrt(len(members) * 1.4)))
        rows = math.ceil(len(members) / cols)
        sizes.append(
            (
                cols,
                rows,
                cols * (NODE_W + NODE_GAP) + 2 * GROUP_PAD,
                rows * (NODE_H + NODE_GAP) + 2 * GROUP_PAD,
            )
        )
    g_cols = max(1, math.ceil(math.sqrt(len(buckets))))
    g_rows = math.ceil(len(buckets) / g_cols)
    col_w = [0.0] * g_cols
    row_h = [0.0] * g_rows
    for i, (_, _, w, h) in enumerate(sizes):
        col_w[i % g_cols] = max(col_w[i % g_cols], w)
        row_h[i // g_cols] = max(row_h[i // g_cols], h)
    col_x = []
    x = 0.0
    for w in col_w:
        col_x.append(x + w / 2)
        x += w + GROUP_GAP
    row_y = []
    y = 0.0
    for h in row_h:
        row_y.append(y + h / 2)
        y += h + GROUP_GAP
    positions: dict[str, dict[str, float]] = {}
    for i, members in enumerate(buckets):
        cols, rows, _, _ = sizes[i]
        cx, cy = col_x[i % g_cols], row_y[i // g_cols]
        for j, nid in enumerate(members):
            r, c = j // cols, j % cols
            positions[nid] = {
                "x": cx + (c - (cols - 1) / 2) * (NODE_W + NODE_GAP),
                "y": cy + (r - (rows - 1) / 2) * (NODE_H + NODE_GAP),
            }
    return positions


def layout_spec(name: str) -> dict[str, Any]:
    if name == "organic":
        return {
            "name": "cose-bilkent",
            "animate": False,
            "fit": True,
            "padding": 30,
            "nodeDimensionsIncludeLabels": True,
            "idealEdgeLength": 140,
            "nodeRepulsion": 8000,
            "gravity": 0.2,
            "gravityRange": 3.0,
            "tile": True,
            "randomize": True,
        }
    if name == "concentric":
        return {
            "name": "concentric",
            "animate": False,
            "fit": True,
            "padding": 30,
            "minNodeSpacing": 50,
            "concentric": None,
        }
    if name == "breadthfirst":
        return {
            "name": "breadthfirst",
            "animate": False,
            "fit": True,
            "padding": 30,
            "directed": True,
            "spacingFactor": 1.3,
        }
    if name == "circle":
        return {
            "name": "circle",
            "animate": False,
            "fit": True,
            "padding": 30,
            "avoidOverlap": True,
            "spacingFactor": 1.1,
        }
    return {"name": "preset", "animate": False, "fit": True, "padding": 30}


def stylesheet() -> list[dict[str, Any]]:
    return [
        {
            "selector": "node",
            "style": {
                "shape": "round-rectangle",
                "width": NODE_W,
                "height": NODE_H,
                "background-color": "data(fill)",
                "border-color": "data(stroke)",
                "border-width": 1.5,
                "label": "data(label)",
                "font-size": "10px",
                "font-family": "Inter, -apple-system, Segoe UI, sans-serif",
                "color": "#1f2933",
                "text-wrap": "wrap",
                "text-max-width": f"{NODE_W - 14}px",
                "text-valign": "center",
                "text-halign": "center",
                "line-height": 1.15,
            },
        },
        {"selector": "node.type", "style": {"font-size": "11px", "font-weight": 600}},
        {
            "selector": "node.centre",
            "style": {"border-width": 3.5, "font-weight": 700, "border-color": "#1f2933"},
        },
        {
            "selector": "node.any",
            "style": {"shape": "diamond", "width": 110, "height": 60, "font-size": "10px"},
        },
        {"selector": "node.inactive", "style": {"opacity": 0.5, "border-style": "dashed"}},
        {
            "selector": "node.group",
            "style": {
                "shape": "round-rectangle",
                "background-color": "data(fill)",
                "background-opacity": 0.18,
                "border-color": "data(stroke)",
                "border-width": 1,
                "border-opacity": 0.6,
                "label": "data(label)",
                "font-size": "12px",
                "font-weight": 700,
                "color": "#3e4c59",
                "text-valign": "top",
                "text-halign": "center",
                "text-margin-y": -6,
                "padding": "26px",
            },
        },
        {
            "selector": "edge",
            "style": {
                "curve-style": "bezier",
                "control-point-step-size": 40,
                "width": 1.2,
                "line-color": "#8d99a6",
                "target-arrow-shape": "triangle",
                "target-arrow-color": "#8d99a6",
                "arrow-scale": 0.9,
                "label": "data(label)",
                "font-size": "8px",
                "color": "#52606d",
                "text-rotation": "autorotate",
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.9,
                "text-background-padding": "2px",
                "text-background-shape": "roundrectangle",
                "min-zoomed-font-size": 7,
            },
        },
        {
            "selector": "edge.sub",
            "style": {"line-style": "dashed", "target-arrow-shape": "triangle-tee", "line-color": "#adb5bd"},
        },
        {
            "selector": "edge:selected, node:selected",
            "style": {"line-color": "#364fc7", "target-arrow-color": "#364fc7", "border-color": "#364fc7"},
        },
    ]


# ------------------------------------------------------------------ panel
def graph_panel(
    panel_id: str,
    registry: Registry,
    raw: dict[str, Any],
    height: str = "70vh",
    group_by: str = "domain",
    layout: str = "grouped",
    extra_controls: list[Any] | None = None,
    hint: str = "Tap a node to open it; drag to pan, scroll to zoom, Ctrl-drag to move a node.",
) -> html.Div:
    return html.Div(
        [
            dcc.Store(id=store_id(panel_id), data=raw),
            dmc.Group(
                [
                    *(extra_controls or []),
                    dmc.Select(
                        id={"type": GROUP, "id": panel_id},
                        data=GROUP_OPTIONS,
                        value=group_by,
                        w=200,
                        size="xs",
                        **{"aria-label": "Group the graph by"},
                    ),
                    dmc.Select(
                        id={"type": LAYOUT, "id": panel_id},
                        data=LAYOUT_OPTIONS,
                        value=layout,
                        w=150,
                        size="xs",
                        **{"aria-label": "Lay the graph out as"},
                    ),
                    dmc.Button(
                        "Fit",
                        id={"type": FIT, "id": panel_id},
                        size="xs",
                        variant="light",
                        leftSection=icon("tabler:arrows-maximize", 14),
                    ),
                    _panel_control(ZOOM_OUT, panel_id, "tabler:minus", "Zoom out"),
                    _panel_control(ZOOM_IN, panel_id, "tabler:plus", "Zoom in"),
                    _panel_control(FULL, panel_id, "tabler:maximize", "Full screen (Escape leaves it)"),
                    html.Div(legend(registry), id={"type": LEGEND, "id": panel_id}),
                ],
                gap="sm",
                mb="xs",
                align="center",
            ),
            cyto.Cytoscape(
                id=cy_id(panel_id),
                className="ea-graph-canvas",
                elements=elements(registry, raw, group_by, layout),
                stylesheet=stylesheet(),
                layout=layout_spec(layout),
                style={"width": "100%", "height": height, "background": "#fbfcfd", "borderRadius": "8px"},
                minZoom=0.05,
                maxZoom=3,
                wheelSensitivity=0.2,
                boxSelectionEnabled=False,
                autoungrabify=True,  # a plain drag pans; ea-graph.js frees the nodes while Ctrl is held
            ),
            dmc.Text(hint, size="xs", c="dimmed", mt=4),
        ],
        className="ea-graph-frame",
    )


def _panel_control(kind: str, panel_id: str, icon_name: str, label: str) -> dmc.Tooltip:
    return dmc.Tooltip(
        dmc.ActionIcon(
            icon(icon_name, 14),
            id={"type": kind, "id": panel_id},
            variant="default",
            size="sm",
            **{"aria-label": label},
        ),
        label=label,
    )


def legend(registry: Registry) -> dmc.Group:
    from ea.ui.components import domain_colour

    return dmc.Group(
        [
            dmc.Badge(d.name, color=domain_colour(registry, d.id), variant="filled", size="xs")
            for d in registry.pack.domains
        ],
        gap="xs",
    )


def register(app: dash.Dash) -> None:
    """Grouping and layout changes rebuild the elements from the store; Fit runs client-side."""
    from ea.ui.context import get_context

    @app.callback(
        Output({"type": CY, "id": MATCH}, "elements"),
        Output({"type": CY, "id": MATCH}, "layout"),
        Input({"type": STORE, "id": MATCH}, "data"),
        Input({"type": GROUP, "id": MATCH}, "value"),
        Input({"type": LAYOUT, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def rebuild(raw, group_by, layout):
        if not raw:
            return [], layout_spec(layout or "grouped")
        reg = get_context().registry
        spec = layout_spec(layout or "grouped")
        spec["_tick"] = (
            dash.ctx.timestamp if hasattr(dash.ctx, "timestamp") else None
        )  # a changed dict re-runs the layout
        return elements(reg, raw, group_by or "", layout or "grouped"), spec

    app.clientside_callback(
        """
        function(n, layout) {
          if (!n) { return window.dash_clientside.no_update; }
          const out = window.dash_clientside.callback_context.outputs_list;
          const cy = window.eaGraph && window.eaGraph.instance(out.id.id);
          if (cy) { cy.fit(undefined, 30); }
          return window.dash_clientside.no_update;
        }
        """,
        Output({"type": CY, "id": MATCH}, "pan"),
        Input({"type": FIT, "id": MATCH}, "n_clicks"),
        State({"type": CY, "id": MATCH}, "layout"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(zoomOut, zoomIn, full) {
          const trigger = window.dash_clientside.callback_context.triggered_id;
          if (!trigger || !window.eaGraph) { return window.dash_clientside.no_update; }
          if (trigger.type === 'gp-full') { window.eaGraph.fullscreen(trigger.id); }
          else { window.eaGraph.zoom(trigger.id, trigger.type === 'gp-zoom-in' ? 1.3 : 1 / 1.3); }
          return window.dash_clientside.no_update;
        }
        """,
        Output({"type": CY, "id": MATCH}, "zoom"),
        Input({"type": ZOOM_OUT, "id": MATCH}, "n_clicks"),
        Input({"type": ZOOM_IN, "id": MATCH}, "n_clicks"),
        Input({"type": FULL, "id": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
