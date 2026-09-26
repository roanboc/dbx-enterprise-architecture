"""The layout a deep dive's diagrams are drawn from: one set of boxes and lines per figure.

The PDF and the draw.io files are both written from it (decision 0025), so what is printed is
what opens in draw.io. Two styles, as the deep dive reads top-down (initiative 25):

- **presentation**, for the context and the overview — a context map, layer bands, a heat
  map and charts, in colour and with icons, for a reader who is not an architect;
- **architecture**, for the architecture and the detail — the metamodel's notation, drawn as
  the application draws a view: the layer is the fill colour, rows run top-down by layer.

Every shape that stands for an element carries its identifier beneath its name (principle P8);
a chart draws figures and carries no element. Everything is read from what the deep dive kept,
so a pack is drawn the same way however long after it was written.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ea.services.target import NOT_REAL, TARGET_STYLE
from ea.views.drawio import LAYER_FILL, SPECIAL_FILL
from ea.views.icons import icon_for
from ea.views.model import LAYER_ORDER, LAYER_TITLES, layer_rank, view_from_dict

INK, MUTED, RULE, PAPER = "#1f2933", "#52606d", "#cbd2d9", "#ffffff"
#: The presentation palette: one colour per layer, brighter than the notation's fills.
PRESENT = {
    "motivation": "#7c6fd6",
    "strategy": "#d9822b",
    "business": "#e6b422",
    "application": "#2d8fd5",
    "technology": "#3a9d5d",
    "physical": "#3a9d5d",
    "implementation": "#e05d44",
    "other": "#7b8794",
}
MATURITY_FILL = {1: "#c92a2a", 2: "#e8590c", 3: "#f2c94c", 4: "#94c973", 5: "#2f9e44"}
SEVERITY_FILL = {"high": "#c92a2a", "medium": "#f08c00", "low": "#1c7ed6"}
GROUP_COLOUR = {
    "serves": "#d9822b",
    "business": "#e6b422",
    "who": "#0ca678",
    "around": "#2d8fd5",
    "work": "#e05d44",
}
#: What joins the subject to each group on the context map.
GROUP_VERB = {
    "serves": "serves",
    "business": "supports",
    "who": "concerns",
    "around": "beside",
    "work": "changes",
}
#: The groups whose line runs to the subject rather than from it.
TOWARDS = ("who", "work")


@dataclass
class Shape:
    """A box. `element_id` is set on every shape that stands for an element, and only on those."""

    sid: str
    x: float
    y: float
    w: float
    h: float
    kind: str  # element | panel | band | tile | bar | rule | text | swatch | badge
    text: str = ""
    sub: str = ""  # the small line beneath: an element's identifier
    fill: str = "none"
    stroke: str = "none"
    font: str = INK
    font_size: float = 10
    bold: bool = False
    align: str = "center"  # center | left
    valign: str = "middle"  # middle | top
    rounded: float = 0
    dashed: bool = False
    stroke_width: float = 1
    icon: str = ""
    icon_colour: str = PAPER
    element_id: str = ""
    style: str = "presentation"  # presentation | architecture
    node: dict[str, Any] | None = None  # the view node an architecture shape draws
    marked: bool = False
    strike: bool = False
    parent: str = ""  # drawn inside another shape, and moved with it in draw.io


@dataclass
class Line:
    lid: str
    src: str
    dst: str
    label: str = ""
    colour: str = MUTED
    width: float = 1
    dashed: bool = False
    arrow: bool = True
    relationship_id: str = ""  # set where the line draws a stored relationship


@dataclass
class Layout:
    title: str
    style: str
    width: float
    height: float
    shapes: list[Shape] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)

    def elements(self) -> list[Shape]:
        return [s for s in self.shapes if s.element_id]

    def shape(self, sid: str) -> Shape | None:
        return next((s for s in self.shapes if s.sid == sid), None)


def ink_on(fill: str) -> str:
    """Dark or light text, whichever reads on this fill."""
    h = fill.lstrip("#")
    if len(h) != 6:
        return INK
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return INK if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else PAPER


def tint(colour: str, amount: float = 0.85) -> str:
    """A pale version of a colour, for a panel behind shapes of that colour."""
    h = colour.lstrip("#")
    if len(h) != 6:
        return "#f5f7fa"
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    mix = [round(c + (255 - c) * amount) for c in (r, g, b)]
    return "#" + "".join(f"{c:02x}" for c in mix)


# ------------------------------------------------------------------ presentation
CHIP_W, CHIP_H, CHIP_GAP = 196, 50, 12
#: How wide a presentation diagram is drawn: about a page's width at two thirds, so its type
#: prints at a size a reader can read.
PRESENT_W = 860.0


def _chip(row: dict[str, Any], x: float, y: float, w: float = CHIP_W, h: float = CHIP_H) -> Shape:
    colour = PRESENT.get(row.get("layer", "other"), PRESENT["other"])
    return Shape(
        sid=row["element_id"],
        x=x,
        y=y,
        w=w,
        h=h,
        kind="element",
        text=row.get("name") or row["element_id"],
        sub=row["element_id"],
        fill=colour,
        stroke=colour,
        font=ink_on(colour),
        font_size=11,
        bold=True,
        align="left",
        rounded=8,
        icon=icon_for(row.get("archimate", ""), row.get("layer", "other")),
        icon_colour=ink_on(colour),
        element_id=row["element_id"],
    )


def _grid(ids: list[str], rows: dict[str, dict[str, Any]], x: float, y: float, cols: int) -> list[Shape]:
    return [
        _chip(rows[i], x + (n % cols) * (CHIP_W + CHIP_GAP), y + (n // cols) * (CHIP_H + CHIP_GAP))
        for n, i in enumerate([i for i in ids if i in rows])
    ]


def _centred(width: float, cols: int) -> float:
    return (width - (cols * CHIP_W + (cols - 1) * CHIP_GAP)) / 2


def _legend(lay: Layout, items: list[tuple[str, str, dict[str, Any]]], y: float, width: float) -> float:
    """A row of keys — a swatch and its label each — wrapped to the width. The y below it."""
    x = 20.0
    for sid, label, swatch in items:
        text_w = 5.6 * len(label) + 24  # the text is drawn 8 in from either side
        if x > 20 and x + 18 + text_w > width - 10:
            x, y = 20.0, y + 24
        kind = swatch.pop("kind", "swatch")
        lay.shapes.append(Shape(sid, x, y + 4, 14, 14, kind, **swatch))
        lay.shapes.append(
            Shape(
                f"{sid}_t", x + 18, y, text_w, 22, "text", text=label, font=MUTED, font_size=9, align="left"
            )
        )
        x += 18 + text_w + 14
    return y + 30


def _grid_height(count: int, cols: int) -> float:
    lines = max(1, (count + cols - 1) // cols)
    return lines * CHIP_H + (lines - 1) * CHIP_GAP


def context_map(fig: dict[str, Any], rows: dict[str, dict[str, Any]]) -> Layout:
    """The subject at the centre, what it serves above, who is concerned and the business beside
    it, and what sits next to it below."""
    width = PRESENT_W
    lay = Layout(fig["title"], "presentation", width, 0)
    groups = {g["key"]: [i for i in g["ids"] if i in rows] for g in fig.get("groups") or []}
    centre = [i for i in fig.get("centre") or [] if i in rows]
    pad, head = 14, 30
    y = 20.0

    def panel(key: str, title: str, x: float, top: float, w: float, h: float) -> Shape:
        colour = GROUP_COLOUR.get(key, MUTED)
        s = Shape(
            sid=f"_panel_{key}",
            x=x,
            y=top,
            w=w,
            h=h,
            kind="panel",
            text=title,
            fill=tint(colour),
            stroke=colour,
            font=INK,
            font_size=11,
            bold=True,
            align="left",
            valign="top",
            rounded=10,
        )
        lay.shapes.append(s)
        return s

    titles = {g["key"]: g["title"] for g in fig.get("groups") or []}
    panels: dict[str, Shape] = {}
    # what it serves, across the top
    if groups.get("serves"):
        cols = 3
        h = head + _grid_height(len(groups["serves"]), cols) + pad
        panels["serves"] = panel("serves", titles["serves"], 20, y, width - 40, h)
        lay.shapes += _grid(groups["serves"], rows, _centred(width, cols), y + head, cols)
        y += h + 60
    # who is concerned, the subject, the business it supports
    side_w = CHIP_W + 2 * pad
    middle_top = y
    heights = []
    for key, x in (("who", 20), ("business", width - 20 - side_w)):
        ids = groups.get(key) or []
        if ids:
            h = head + _grid_height(len(ids), 1) + pad
            panels[key] = panel(key, titles[key], x, middle_top, side_w, h)
            lay.shapes += _grid(ids, rows, x + pad, middle_top + head, 1)
            heights.append(h)
    centre_w = 300.0
    centre_h = head + _grid_height(len(centre), 1) + pad if centre else 80
    cx = (width - centre_w) / 2
    cy = middle_top + max(0.0, (max(heights, default=centre_h) - centre_h) / 2)
    core = Shape(
        sid="_panel_centre",
        x=cx,
        y=cy,
        w=centre_w,
        h=centre_h,
        kind="panel",
        text="The subject",
        fill="#f0f4f8",
        stroke=INK,
        stroke_width=2,
        font=INK,
        font_size=11,
        bold=True,
        align="left",
        valign="top",
        rounded=14,
    )
    lay.shapes.append(core)
    lay.shapes += [
        _chip(rows[c], cx + pad + (centre_w - 2 * pad - 260) / 2, cy + head + n * (CHIP_H + CHIP_GAP), 260)
        for n, c in enumerate(centre)
    ]
    y = middle_top + max([*heights, centre_h]) + 60
    # what sits beside it, and the work in flight that changes it, across the bottom
    bottom = [k for k in ("around", "work") if groups.get(k)]
    if bottom:
        if len(bottom) == 2:
            work_w = CHIP_W + 2 * pad
            spans = {"around": (20.0, width - 60 - work_w), "work": (width - 20 - work_w, work_w)}
        else:
            spans = {bottom[0]: (20.0, width - 40)}
        cols = {
            k: max(1, min(3, int((w - 2 * pad + CHIP_GAP) // (CHIP_W + CHIP_GAP))))
            for k, (_, w) in spans.items()
        }
        h = max(head + _grid_height(len(groups[k]), cols[k]) + pad for k in bottom)
        for k in bottom:
            x, w = spans[k]
            panels[k] = panel(k, titles[k], x, y, w, h)
            grid_w = cols[k] * CHIP_W + (cols[k] - 1) * CHIP_GAP
            lay.shapes += _grid(groups[k], rows, x + (w - grid_w) / 2, y + head, cols[k])
        y += h + 20
    if not panels:
        lay.shapes.append(
            Shape(
                sid="_note",
                x=20,
                y=y,
                w=width - 40,
                h=30,
                kind="text",
                text="Nothing around it reaches the business, the strategy or the motivation.",
                font=MUTED,
                font_size=11,
            )
        )
        y += 50
    for key, p in panels.items():
        src, dst = (p.sid, "_panel_centre") if key in TOWARDS else ("_panel_centre", p.sid)
        lay.lines.append(
            Line(
                f"_to_{key}",
                src,
                dst,
                GROUP_VERB.get(key, ""),
                GROUP_COLOUR.get(key, MUTED),
                2.5,
                key in ("around", "work"),
            )
        )
    lay.height = y
    return lay


def layer_bands(fig: dict[str, Any], rows: dict[str, dict[str, Any]]) -> Layout:
    """One band per layer, top-down, each with its elements as coloured, iconed chips."""
    width, head_w, cols = PRESENT_W, 150.0, 3
    lay = Layout(fig["title"], "presentation", width, 0)
    y = 20.0
    for band in fig.get("bands") or []:
        ids = [i for i in band["ids"] if i in rows]
        if not ids:
            continue
        colour = PRESENT.get(band["layer"], PRESENT["other"])
        h = _grid_height(len(ids), cols) + 28
        lay.shapes.append(
            Shape(
                sid=f"_band_{band['layer']}",
                x=20,
                y=y,
                w=width - 40,
                h=h,
                kind="band",
                fill=tint(colour, 0.82),
                stroke=colour,
                rounded=6,
            )
        )
        lay.shapes.append(
            Shape(
                sid=f"_band_{band['layer']}_title",
                x=28,
                y=y,
                w=head_w - 16,
                h=h,
                kind="text",
                text=f"{band['title']} ({len(ids)})",
                font=INK,
                font_size=12,
                bold=True,
                align="left",
                icon=icon_for("", band["layer"]),
                icon_colour=colour,
            )
        )
        lay.shapes += _grid(ids, rows, 20 + head_w, y + 14, cols)
        y += h + 10
    lay.height = y + 10
    return lay


TILE_W, TILE_H, TILE_GAP = 160, 48, 8
_MATURITY_KEY = {1: "1 Named", 2: "2 Described", 3: "3 Related", 4: "4 Approved", 5: "5 Current"}


def heat_map(fig: dict[str, Any], rows: dict[str, dict[str, Any]]) -> Layout:
    """Every element as a tile coloured by its maturity, a row per layer, its findings counted."""
    width, head_w, cols = PRESENT_W, 120.0, 4
    lay = Layout(fig["title"], "presentation", width, 0)
    keys = [
        (f"_key_{level}", _MATURITY_KEY[level], {"fill": colour, "stroke": colour, "rounded": 3})
        for level, colour in MATURITY_FILL.items()
    ]
    keys.append(
        ("_key_f", "findings that cite it", {"kind": "badge", "fill": SEVERITY_FILL["high"], "stroke": PAPER})
    )
    y = _legend(lay, keys, 10, width) + 6
    cells = [c for c in fig.get("cells") or [] if c["id"] in rows]
    for layer in LAYER_ORDER:
        here = [c for c in cells if c.get("layer") == layer]
        if not here:
            continue
        lines = (len(here) + cols - 1) // cols
        h = lines * TILE_H + (lines - 1) * TILE_GAP
        lay.shapes.append(
            Shape(
                f"_row_{layer}",
                20,
                y,
                head_w - 10,
                h,
                "text",
                text=LAYER_TITLES.get(layer, layer),
                font=INK,
                font_size=11,
                bold=True,
                align="left",
                valign="top",
                icon=icon_for("", layer),
                icon_colour=PRESENT.get(layer, MUTED),
            )
        )
        for n, c in enumerate(here):
            row = rows[c["id"]]
            fill = MATURITY_FILL.get(int(c.get("maturity") or 1), MATURITY_FILL[1])
            tx = 20 + head_w + (n % cols) * (TILE_W + TILE_GAP)
            ty = y + (n // cols) * (TILE_H + TILE_GAP)
            lay.shapes.append(
                Shape(
                    c["id"],
                    tx,
                    ty,
                    TILE_W,
                    TILE_H,
                    "tile",
                    text=row.get("name") or c["id"],
                    sub=c["id"],
                    fill=fill,
                    stroke=PAPER,
                    font=ink_on(fill),
                    font_size=9,
                    bold=True,
                    rounded=4,
                    element_id=c["id"],
                )
            )
            if c.get("findings"):
                lay.shapes.append(
                    Shape(
                        f"_badge_{c['id']}",
                        tx + TILE_W - 18,
                        ty - 6,
                        20,
                        20,
                        "badge",
                        text=str(c["findings"]),
                        fill=SEVERITY_FILL["high"],
                        stroke=PAPER,
                        font=PAPER,
                        font_size=8,
                        bold=True,
                        parent=c["id"],
                    )
                )
        y += h + 16
    lay.height = y + 4
    return lay


def bar_chart(fig: dict[str, Any], colours: list[str]) -> Layout:
    """Bars for a series of figures. A chart stands for no element, so it carries none."""
    series = list(fig.get("series") or [])
    width, height = 640.0, 330.0
    lay = Layout(fig["title"], "presentation", width, height)
    left, top, plot_w, plot_h = 60.0, 30.0, 540.0, 220.0
    top_value = max([s["value"] for s in series] + [1])
    slot = plot_w / max(1, len(series))
    bar_w = min(80.0, slot * 0.6)
    lay.shapes.append(Shape("_axis_x", left, top + plot_h, plot_w, 1.5, "rule", fill=MUTED))
    lay.shapes.append(Shape("_axis_y", left, top, 1.5, plot_h, "rule", fill=MUTED))
    for n, s in enumerate(series):
        h = plot_h * s["value"] / top_value
        x = left + n * slot + (slot - bar_w) / 2
        colour = colours[n % len(colours)]
        if s["value"]:
            lay.shapes.append(
                Shape(f"_bar_{n}", x, top + plot_h - h, bar_w, h, "bar", fill=colour, rounded=3)
            )
        lay.shapes.append(
            Shape(
                f"_value_{n}",
                x - 10,
                top + plot_h - h - 22,
                bar_w + 20,
                20,
                "text",
                text=str(s["value"]),
                font=INK,
                font_size=12,
                bold=True,
            )
        )
        lay.shapes.append(
            Shape(
                f"_label_{n}",
                left + n * slot,
                top + plot_h + 8,
                slot,
                40,
                "text",
                text=s["label"],
                font=MUTED,
                font_size=10,
                valign="top",
            )
        )
    return lay


# ------------------------------------------------------------------ architecture
NODE_W, NODE_H, COLS, GAP_X, GAP_Y, LAYER_GAP = 150, 58, 4, 34, 40, 56


def view_layout(fig: dict[str, Any]) -> Layout:
    """A view in the metamodel's notation: a row per layer, top-down; the layer is the fill."""
    view = view_from_dict(fig["view"])
    marked = bool(fig.get("marked"))
    flagged = set(fig.get("flagged") or [])
    layers = sorted(view.layers(), key=layer_rank)
    widest = max((min(len(view.nodes_in(lv)), COLS) for lv in layers), default=1)
    width = max(560.0, 40 + widest * NODE_W + (widest - 1) * GAP_X)
    lay = Layout(fig["title"], "architecture", width, 0)
    # the key: the layers by their fill, and the target states when they are drawn
    keys = [
        (
            f"_key_{lv}",
            LAYER_TITLES.get(lv, lv),
            {"fill": LAYER_FILL.get(lv, LAYER_FILL["other"]), "stroke": "#555555"},
        )
        for lv in layers
    ]
    if marked:
        keys += [
            (
                f"_key_{state}",
                TARGET_STYLE[state]["label"],
                {
                    "fill": PAPER,
                    "stroke": TARGET_STYLE[state]["hex"],
                    "stroke_width": 2,
                    "dashed": state in ("new", "merge"),
                },
            )
            for state in ("new", "change", "decommission", "merge")
        ]
    y = _legend(lay, keys, 10, width)
    y += 6
    for lv in layers:
        nodes = view.nodes_in(lv)
        for start in range(0, len(nodes), COLS):
            chunk = nodes[start : start + COLS]
            row_w = len(chunk) * NODE_W + (len(chunk) - 1) * GAP_X
            x0 = (width - row_w) / 2
            for n, node in enumerate(chunk):
                fill = SPECIAL_FILL.get(node.archimate) or LAYER_FILL.get(node.layer, LAYER_FILL["other"])
                stroke, sw, dashed = "#555555", 1.0, False
                if node.focus:
                    stroke, sw = INK, 2.5
                st = TARGET_STYLE.get(node.target_state)
                if marked and st and node.target_state not in ("undecided", "keep"):
                    stroke, sw = st["hex"], 2.5
                if marked and (node.current_state in NOT_REAL or node.target_state in ("new", "merge")):
                    dashed = True
                shape = Shape(
                    node.id,
                    x0 + n * (NODE_W + GAP_X),
                    y,
                    NODE_W,
                    NODE_H,
                    "element",
                    text=node.name,
                    sub=node.id,
                    fill=fill,
                    stroke=stroke,
                    stroke_width=sw,
                    dashed=dashed,
                    font="#c92a2a" if marked and node.target_state == "decommission" else INK,
                    font_size=10,
                    rounded=8 if node.archimate.endswith(("Process", "Function", "Service", "Event")) else 0,
                    icon=icon_for(node.archimate, node.layer),
                    icon_colour=INK,
                    element_id=node.id,
                    style="architecture",
                    node=_node_dict(node),
                    marked=marked,
                    strike=marked and node.target_state == "decommission",
                )
                lay.shapes.append(shape)
                if node.id in flagged:
                    lay.shapes.append(
                        Shape(
                            f"_flag_{node.id}",
                            shape.x - 8,
                            shape.y - 8,
                            18,
                            18,
                            "badge",
                            text="!",
                            fill=SEVERITY_FILL["high"],
                            stroke=PAPER,
                            font=PAPER,
                            font_size=9,
                            bold=True,
                            parent=node.id,
                        )
                    )
            y += NODE_H + GAP_Y
        y += LAYER_GAP - GAP_Y
    present = {n.id for n in view.nodes}
    for n, e in enumerate(view.edges):
        if e.src not in present or e.dst not in present:
            continue
        colour, width_, dashed = MUTED, 1.0, False
        st = TARGET_STYLE.get(e.target_state)
        if marked and st and e.target_state not in ("undecided", "keep"):
            colour, width_, dashed = st["hex"], 2.0, e.target_state in ("new", "merge")
        lay.lines.append(
            Line(
                f"_edge_{n}", e.src, e.dst, e.label, colour, width_, dashed, relationship_id=e.relationship_id
            )
        )
    if view.note:
        lay.shapes.append(
            Shape("_note", 20, y, width - 40, 20, "text", text=view.note, font=MUTED, font_size=9)
        )
        y += 24
    lay.height = y + 10
    return lay


def _node_dict(node: Any) -> dict[str, Any]:
    return asdict(node)


def layout_figure(fig: dict[str, Any], rows: dict[str, dict[str, Any]]) -> Layout:
    """The layout of one figure a deep dive kept."""
    kind = fig.get("kind")
    if kind == "context_map":
        return context_map(fig, rows)
    if kind == "layer_bands":
        return layer_bands(fig, rows)
    if kind == "heat_map":
        return heat_map(fig, rows)
    if kind == "chart_maturity":
        return bar_chart(fig, [MATURITY_FILL[n] for n in sorted(MATURITY_FILL)])
    if kind == "chart_findings":
        return bar_chart(fig, [SEVERITY_FILL[s] for s in ("high", "medium", "low")])
    if kind == "view":
        return view_layout(fig)
    raise ValueError(f"no layout for a figure of kind {kind!r}")


def slug(text: str, limit: int = 48) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (out[:limit].rstrip("-")) or "figure"


def figure_filename(number: int, fig: dict[str, Any]) -> str:
    """`NN-level-L-title.drawio`: numbered in reading order, level first, as the PDF names it."""
    return f"{number:02d}-level-{fig.get('level', 0)}-{slug(fig.get('title', ''))}.drawio"


def pack_filename(d: Any) -> str:
    return f"deep-dive-{slug(d.title, 40)}-{d.deep_dive_id or 'draft'}.zip"


def figures(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Every figure, in the order the deep dive reads: level first."""
    return [f for lv in content.get("levels") or [] for f in lv.get("figures") or []]
