"""Render a view as Mermaid, in the notation the architecture documents of this repository use."""

from __future__ import annotations

import re

from ea.services.target import CURRENT_STYLE, NOT_REAL, TARGET_STYLE, state_label
from ea.views.model import LAYER_TITLES, View, ViewNode

# How a target state marks a shape: stroke colour, and dashed when the artefact is not (yet) real.
TARGET_CLASS = {
    "new": "stroke:#2f9e44,stroke-width:2.5px,stroke-dasharray:6 3",
    "change": "stroke:#e8590c,stroke-width:2.5px",
    "decommission": "stroke:#c92a2a,stroke-width:2.5px,stroke-dasharray:2 3,color:#c92a2a",
    "merge": "stroke:#7048e8,stroke-width:2.5px,stroke-dasharray:6 3",
    "keep": "stroke:#1c7ed6,stroke-width:1.5px",
}
NOT_REAL_CLASS = "stroke-dasharray:6 3"

# archreator's colours per ArchiMate layer (architecture-document-style § ArchiMate on Mermaid).
# The layers are not drawn as boxes (see `to_mermaid`), so each fill is also named in words:
# `layer_legend` says which colour is which layer in the line above the diagram.
LAYER_STYLE = {
    "motivation": ("#e6d6f5", "#7e57c2"),
    "strategy": ("#f5deaa", "#c8a24a"),
    "business": ("#fffbb5", "#b8a200"),
    "application": ("#c2f0ff", "#0288d1"),
    "technology": ("#c9e7b7", "#558b2f"),
    "physical": ("#c9e7b7", "#558b2f"),
    "implementation": ("#f8d7da", "#c0392b"),
    "other": ("#eeeeee", "#888888"),
}
# A swatch per layer for the line that stands in for the layer boxes: in a document, a
# reader matches a colour to a shape at a glance and has to translate the word "blue".
LAYER_SWATCH = {
    "motivation": "🟪",
    "strategy": "🟧",
    "business": "🟨",
    "application": "🟦",
    "technology": "🟩",
    "physical": "🟩",
    "implementation": "🟥",
    "other": "⬜",
}
# Mermaid node shapes by the pack's `shape` key.
SHAPES = {
    "rect": ('["', '"]'),
    "round": ('("', '")'),
    "stadium": ('(["', '"])'),
    "hex": ('{{"', '"}}'),
    "cyl": ('[("', '")]'),
    "subroutine": ('[["', '"]]'),
    "diamond": ('{"', '"}'),
    "asym": ('>"', '"]'),
}
_SAFE = re.compile(r"[^A-Za-z0-9_]")


def node_id(element_id: str) -> str:
    """A Mermaid-safe identifier for an element id (hyphens and dots are not safe everywhere)."""
    return "n_" + _SAFE.sub("_", element_id)


def _quote(text: str) -> str:
    return text.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


def _state_prefix(n: ViewNode, marked: bool) -> str:
    """A glyph in front of the label when the view marks states: + new, Δ change, × decommission, ⇒ merge."""
    if not marked:
        return ""
    st = TARGET_STYLE.get(n.target_state)
    if st and n.target_state not in ("undecided", "keep"):
        return st["glyph"] + " "
    if n.current_state in NOT_REAL:
        return "◌ "
    return ""


def _node_line(n: ViewNode, marked: bool = False) -> str:
    left, right = SHAPES.get(n.shape, SHAPES["rect"])
    text = _quote(f"{_state_prefix(n, marked)}{n.label} [{n.id if n.identified else 'not yet created'}]")
    return f"{node_id(n.id)}{left}{text}{right}:::{n.layer if n.layer in LAYER_STYLE else 'other'}"


def _state_lines(view: View) -> list[str]:
    """classDef and class lines that mark target states (and dashed shapes for what is not yet real)."""
    lines: list[str] = []
    used: set[str] = set()
    for n in view.nodes:
        if n.target_state in TARGET_CLASS:
            lines.append(f"  class {node_id(n.id)} st_{n.target_state}")
            used.add(n.target_state)
        elif n.current_state in NOT_REAL:
            lines.append(f"  class {node_id(n.id)} st_notreal")
            used.add("notreal")
    for state in used:
        style = NOT_REAL_CLASS if state == "notreal" else TARGET_CLASS[state]
        lines.append(f"  classDef st_{state} {style}")
    return lines


def _edge_style_lines(view: View) -> list[str]:
    lines = []
    for i, e in enumerate(view.edges):
        st = TARGET_STYLE.get(e.target_state)
        if st and e.target_state not in ("undecided", "keep"):
            dash = ",stroke-dasharray:6 3" if e.target_state in ("new", "merge") else ""
            lines.append(f"  linkStyle {i} stroke:{st['hex']},stroke-width:2px{dash}")
    return lines


def state_legend(view: View) -> str:
    """One line saying what the markers mean, for the states that occur in the view."""
    parts = []
    seen_t = sorted(
        {n.target_state for n in view.nodes} | {e.target_state for e in view.edges},
        key=list(TARGET_STYLE).index,
    )
    for t in seen_t:
        if t in ("undecided", "keep"):
            continue
        parts.append(f"{TARGET_STYLE[t]['glyph']} {state_label(t, TARGET_STYLE).lower()}")
    if any(n.current_state in NOT_REAL and n.target_state in ("undecided", "keep") for n in view.nodes):
        parts.append("◌ not yet real")
    return "Markers: " + ", ".join(parts) + "." if parts else ""


def layer_legend(view: View) -> str:
    """Which colour stands for which architecture layer, for the layers this view draws.

    The diagram fills every shape by its ArchiMate layer but draws no box around the layers
    (`to_mermaid` says why), so what a box would have been labelled is carried here: a swatch
    and the layer's name, in the exported Markdown and in the source of the diagram itself.
    On a screen the same legend is drawn as chips in the layers' own colours
    (`ui.components.layer_chips`), which is what a text format cannot do.
    """
    layers = view.layers()
    if not layers:
        return ""
    named = ", ".join(f"{LAYER_SWATCH.get(layer, '⬜')} {LAYER_TITLES.get(layer, layer)}" for layer in layers)
    return f"Filled by layer: {named}."


def to_mermaid(view: View, direction: str = "BT", marked: bool = False, legend: bool = False) -> str:
    """Every element as a shape filled by its architecture layer, joined by the relationships themselves.

    The layers are **not** drawn as boxes. A subgraph per layer pushes the shapes apart —
    Mermaid gives every box its own rank band and its own padding — so a view of a dozen
    elements spreads over a page and the relationships, which are the point of it, run half
    its width. The layer is in the fill colour instead, named above the diagram by
    `layer_legend`, and the shapes sit where their own relationships put them.

    Drawn bottom-to-top: most relationships in an EA model point from the lower layers
    upwards (technology stores data, applications process it, roles own assets), so the
    layout's natural rank order agrees with the ArchiMate stacking instead of fighting it.
    With `marked`, shapes and edges carry their target state: new dashed green, changed
    amber, decommissioned red, merged violet, and what is not yet real dashed.
    """
    lines = [f"flowchart {direction}"]
    if legend:
        # A diagram whose subject is the notation itself — the metamodel, drawn — carries the
        # marker the architecture documents' validator reads, so its stereotypes are allowed.
        lines.append("  %% legend")
    # The colours mean nothing without their names, and the source is pasted where the line
    # above the diagram does not travel with it: Mermaid ignores a comment, a reader does not.
    said = layer_legend(view)
    if said:
        lines.append(f"  %% {said}")
    for n in view.nodes:
        lines.append("  " + _node_line(n, marked))
    if view.edges:
        lines.append("")
    for e in view.edges:
        lines.append(f'  {node_id(e.src)} -->|"{_quote(e.label)}"| {node_id(e.dst)}')
    lines.append("")
    for layer in view.layers():
        fill, stroke = LAYER_STYLE.get(layer, LAYER_STYLE["other"])
        lines.append(f"  classDef {layer} fill:{fill},stroke:{stroke},color:#333")
    for fid in view.focus_ids:
        lines.append(f"  style {node_id(fid)} stroke-width:3px")
    if marked:
        lines += _state_lines(view)
        lines += _edge_style_lines(view)
    return "\n".join(lines) + "\n"


def to_markdown(view: View, marked: bool = False, legend: bool = False) -> str:
    """The view as a Markdown section: title, the fenced diagram, and the elements it shows."""
    out = [f"## {view.title}", ""]
    if view.note:
        out += [f"_{view.note}_", ""]
    notes = [layer_legend(view)]
    if marked:
        notes.append(state_legend(view))
    said = " ".join(n for n in notes if n)
    if said:
        out += [f"_{said}_", ""]
    out += ["```mermaid", to_mermaid(view, marked=marked, legend=legend).rstrip("\n"), "```", ""]
    if marked:
        out += [
            "| ID | Element | Type | Current state | Target state |",
            "| -- | ------- | ---- | ------------- | ------------ |",
        ]
        for n in view.nodes:
            out.append(
                f"| `{n.id}` | {n.glyph} {n.name} | {n.stereotype or n.type_name} ({n.type_name}) | "
                f"{state_label(n.current_state, CURRENT_STYLE)} | {state_label(n.target_state, TARGET_STYLE)} |"
            )
    else:
        out += ["| ID | Element | Type |", "| -- | ------- | ---- |"]
        for n in view.nodes:
            out.append(f"| `{n.id}` | {n.glyph} {n.name} | {n.stereotype or n.type_name} ({n.type_name}) |")
    out.append("")
    return "\n".join(out)
