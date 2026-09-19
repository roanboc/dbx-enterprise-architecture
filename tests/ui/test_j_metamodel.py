"""Group J — Metamodel: one version at a time, in six tabs.

The Metamodel page is the one screen where the *language* of the repository is edited
rather than its content. It shows one version of the pack at a time — the one the
organisation applies, unless the selector in the title says otherwise — under six tabs:
**Manage** (four grids: element types, relationship types, attributes, domains, saved
together), **Graph** (the type graph, grouped by domain, with a detail pane), **Architecture
view** (the metamodel drawn in its own notation, downloadable), **Notation** (how each
domain and type is drawn, with a live preview), **Versions** (every stored version, its
state, who applies it, drafts, publishing, retiring, deleting and the difference between
two) and **Reviewers** (who approves a branch per element type).

A published version is frozen. Saving edits made on one opens a dialog that stores them as
a new draft; a draft is edited in place; a draft nobody applies can be deleted, a published
version only retired (decision 0015). That lifecycle is what makes this group safe inside a
shared round: J06 turns the first edit into the draft `j-draft` without applying it to the
organisation, so every other group keeps reading the shipped, published version; J10, J15,
J20 and J21 write to that draft; J21 deletes rows on it and J24 publishes, retires and deletes it; and J25 loads a version
from a file, applies it, then loads the shipped file back so the round ends where it began.
Everything else is typed into a grid and discarded by navigating away, which is exactly
what a person does when they change their mind before saving.

Nothing here asserts an exact total: the counts the page prints are compared with what the
graph and the grids actually hold, not with numbers written into this file.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.gui

TYPE = "data_entity"  # a type with its own attributes, a domain, and relationships both ways
SUB = "business_definition"  # a sub-type, so the grid proves inheritance is editable
REL = "logical_data_component__encapsulates__data_entity"
REVIEW_TYPE = "value_stream"  # active, and no sample element uses it, so no branch can touch it
REVIEWER = "j-review-guild"
NEW_OWNER = "J round custodian"  # what J06 writes into the draft
FILTER_OWNER = "J filtered custodian"  # what J15 writes into the draft under a column filter
SHIPPED_OWNER = "Information Domain Architect"
GLYPH = "✹"  # a glyph that appears nowhere in the shipped pack
SUPER_GLYPH = "✤"  # nowhere in the shipped pack, so an inherited glyph names where it came from
DOMAIN_GLYPH = "✜"
STEREOTYPE = "J Data Object"
DOMAIN_COLOUR = "grape"
UNUSED_LAYER = "physical"  # no active type is drawn in it, so a new band is the edit landing
NEW_TYPE_NAME = "J Saved Type"
DELETED_TYPE = "measure"  # J21 deletes it from the draft: the sample model uses it, so the page warns
NEW_DOMAIN = "j_domain"
NEW_DOMAIN_NAME = "J Domain"

PACK = "higher_education"
PUBLISHED = "higher_education@2026-08-11"  # the shipped version, published
PUBLISHED_VERSION = "2026-08-11"
DRAFT = "j-draft"
DRAFT_REF = f"{PACK}@{DRAFT}"
FILE_VERSION = "j-file"
FILE_REF = f"{PACK}@{FILE_VERSION}"
ORG = "Default organisation"
SHIPPED_FILE = Path(__file__).resolve().parents[2] / "packs" / PACK / "metamodel.yaml"

TABS = ["Manage", "Graph", "Architecture view", "Notation", "Versions", "Reviewers"]
LISTS = ["Element types", "Relationship types", "Attributes", "Domains"]
DOMAINS = ["Information", "Process", "Integration", "Objects of enterprise concern"]
COUNTS = re.compile(r"(\d+) active types, (\d+) inactive, (\d+) relationship types, (\d+) attributes")


def _pm(**parts: str) -> str:
    """The CSS selector for a pattern-matching component, whose DOM id is the JSON Dash writes."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


GP_CY = _pm(id="mm", type="gp-cy")
GP_FIT = _pm(id="mm", type="gp-fit")
GP_LEGEND = _pm(id="mm", type="gp-legend")
PREVIEW = _pm(id="mm-notation-preview", type="mermaid-svg")
VIEW = _pm(id="mm-view", type="mermaid-svg")


def _action_id(action: str, ref: str) -> str:
    """The id of a Versions-tab row button, as the harness addresses a pattern-matching component."""
    return json.dumps(
        {"action": action, "ref": ref, "type": "mm-ver-action"}, sort_keys=True, separators=(",", ":")
    )


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    """A fresh Metamodel page, showing the version the organisation applies, on the Manage tab.

    Anything typed into a grid and not saved is gone."""
    ui.goto("/metamodel")
    ui.must("the Metamodel page rendered its lists", ui.visible("mm-types-grid"))


def _tab(ui, label: str) -> None:
    """One of the six tabs over the version shown."""
    ui.click(f'#mm-tabs > [role="tablist"] [role="tab"]:has-text("{label}")')
    ui.page.wait_for_timeout(250)


def _list(ui, label: str) -> None:
    """One of the four lists inside Manage."""
    _tab(ui, "Manage")
    ui.click(f'#mm-lists [role="tab"]:has-text("{label}")')
    ui.page.wait_for_timeout(250)


def _active_tab(ui) -> str:
    loc = ui.page.locator('#mm-tabs > [role="tablist"] [role="tab"][aria-selected="true"]').first
    return loc.inner_text().strip() if loc.count() else ""


def _active_list(ui) -> str:
    loc = ui.page.locator('#mm-lists [role="tab"][aria-selected="true"]').first
    return re.sub(r"\s*\(\d+\)$", "", loc.inner_text().strip()) if loc.count() else ""


def _graph(ui) -> None:
    _tab(ui, "Graph")
    ui.must("the type graph is drawn", ui.visible(GP_CY))
    ui.wait_graph()


def _show(ui, version: str) -> None:
    """Pick a version in the title's selector and wait for the page to show it."""
    ui.select("mm-version-select", version)
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.must(
        f"the page shows version {version}",
        f"version {version} " in ui.text("mm-subtitle"),
        ui.text("mm-subtitle"),
    )


def _shown_version(ui) -> str:
    """What the title's selector reads, which is what every tab beneath it is showing."""
    return ui.page.locator("#mm-version-select").first.input_value().strip()


def _subtitle_counts(ui) -> tuple[int, int, int, int] | None:
    m = COUNTS.search(ui.text("mm-subtitle"))
    return tuple(int(g) for g in m.groups()) if m else None  # type: ignore[return-value]


def _cy(ui, expression: str):
    """Ask the type graph's Cytoscape instance something, e.g. `cy.$('node.type').length`."""
    return ui.page.evaluate(
        "() => { const cy = window.eaGraph && window.eaGraph.instance('mm');"
        f" if (!cy) {{ return null; }} return {expression}; }}"
    )


def _has_node(ui, type_id: str) -> bool:
    return bool(_cy(ui, f"cy.$('node[element_id = {json.dumps(type_id)}]').length"))


def _tap_at(ui, position) -> bool:
    if position is None:
        return False
    box = ui.page.locator(GP_CY).first.bounding_box()
    ui.page.mouse.click(box["x"] + position[0], box["y"] + position[1])
    ui.page.wait_for_timeout(600)
    ui.settle()
    return True


def _tap_type(ui, type_id: str) -> bool:
    """Tap a type node the way a reader does — a real click at the node's rendered position."""
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    return _tap_at(
        ui,
        _cy(
            ui,
            "(function(){ var n = cy.$('node[element_id = " + json.dumps(type_id) + "]');"
            " if (!n.length) { return null; } var p = n[0].renderedPosition(); return [p.x, p.y]; })()",
        ),
    )


def _tap_any(ui) -> bool:
    """Tap the diamond that stands for 'any element' — a node with no element behind it."""
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    return _tap_at(
        ui,
        _cy(
            ui,
            "(function(){ var n = cy.$('node.any'); if (!n.length) { return null; }"
            " var p = n[0].renderedPosition(); return [p.x, p.y]; })()",
        ),
    )


def _reveal(ui, grid_id: str, row_id: str) -> bool:
    """Scroll a grid until the row with this id is rendered — ag-grid keeps only what is on screen."""
    for step in range(40):
        if row_id in ui.grid_row_ids(grid_id):
            return True
        ui.page.evaluate(
            "([gid, top]) => { const v = document.querySelector('#' + gid + ' .ag-body-viewport');"
            " if (v) { v.scrollTop = top; } }",
            [grid_id, step * 240],
        )
        ui.page.wait_for_timeout(120)
    return row_id in ui.grid_row_ids(grid_id)


def _reveal_cell(ui, grid_id: str, row_id: str, col: str) -> bool:
    """Bring one cell into the DOM: ag-grid renders neither the rows nor the columns off screen."""
    sel = f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']"
    if not _reveal(ui, grid_id, row_id):
        return False
    for left in range(0, 4800, 200):
        if ui.page.locator(sel).count():
            return True
        ui.page.evaluate(
            "([gid, left]) => { ['.ag-body-horizontal-scroll-viewport', '.ag-center-cols-viewport']"
            ".forEach(t => { const v = document.querySelector('#' + gid + ' ' + t);"
            " if (v) { v.scrollLeft = left; } }); }",
            [grid_id, left],
        )
        ui.page.wait_for_timeout(120)
    return bool(ui.page.locator(sel).count())


def _cell(ui, grid_id: str, row_id: str, col: str) -> str:
    _reveal_cell(ui, grid_id, row_id, col)
    return ui.grid_cell_of(grid_id, row_id, col)


def _set(ui, grid_id: str, row_id: str, col: str, value: str) -> None:
    _reveal_cell(ui, grid_id, row_id, col)
    ui.grid_set_of(grid_id, row_id, col, value)


def _grid_home(ui, grid_id: str) -> None:
    """Put a grid this module scrolled back where a reader left it, so a screenshot reads."""
    ui.page.evaluate(
        "gid => { ['.ag-body-horizontal-scroll-viewport', '.ag-center-cols-viewport', '.ag-body-viewport']"
        ".forEach(t => { const v = document.querySelector('#' + gid + ' ' + t);"
        " if (v) { v.scrollLeft = 0; v.scrollTop = 0; } }); }",
        grid_id,
    )
    ui.page.wait_for_timeout(300)


def _scroll_to_end(ui, grid_id: str) -> None:
    ui.page.evaluate(
        "gid => { const v = document.querySelector('#' + gid + ' .ag-body-viewport');"
        " if (v) { v.scrollTop = v.scrollHeight; } }",
        grid_id,
    )
    ui.page.wait_for_timeout(400)


def _filter(ui, grid_id: str, col: str, text: str) -> None:
    """Type into a column's filter, the way a person narrows a long grid to find one row."""
    ui.page.locator(f"#{grid_id} .ag-header-cell[col-id='{col}'] .ag-header-cell-filter-button").first.click()
    ui.page.wait_for_timeout(400)
    ui.page.locator(".ag-filter-body input, .ag-filter .ag-input-field-input").first.fill(text)
    ui.page.wait_for_timeout(800)
    ui.page.keyboard.press("Escape")
    ui.settle()


def _tick_state(ui, grid_id: str, row_id: str, col: str) -> bool | None:
    """Whether a boolean cell is ticked: ag-grid draws it as a checkbox and writes no text."""
    _reveal_cell(ui, grid_id, row_id, col)
    sel = f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']"
    box = ui.page.locator(f"{sel} input[type=checkbox]").first
    if box.count():
        return box.is_checked()
    wrapper = ui.page.locator(f"{sel} .ag-checkbox-input-wrapper").first
    if wrapper.count():
        return "ag-checked" in (wrapper.get_attribute("class") or "")
    return None


def _tick(ui, grid_id: str, row_id: str, col: str, on: bool) -> None:
    """Tick or untick a boolean cell, which ag-grid draws as a checkbox a reader clicks."""
    if _tick_state(ui, grid_id, row_id, col) == on:
        return
    sel = f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']"
    box = ui.page.locator(f"{sel} input[type=checkbox]").first
    (box if box.count() else ui.page.locator(f"{sel} .ag-checkbox-input-wrapper").first).click(force=True)
    ui.page.wait_for_timeout(250)
    ui.settle()


def _set_select(ui, grid_id: str, row_id: str, col: str, value: str) -> None:
    """A cell whose editor is a list, not a text box: open it and pick the value."""
    _reveal_cell(ui, grid_id, row_id, col)
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']").first
    cell.scroll_into_view_if_needed()
    cell.dblclick()
    ui.page.wait_for_timeout(250)
    editor = ui.page.locator(f"#{grid_id} .ag-cell-editor").first
    if editor.count():
        picker = editor.locator(".ag-picker-field-wrapper").first
        native = editor.locator("select").first
        if picker.count():
            picker.click()
            ui.page.wait_for_timeout(250)
            item = ui.page.locator(f"#{grid_id} .ag-list-item:has-text({json.dumps(value)})").first
            if not item.count():
                item = ui.page.locator(f".ag-list-item:has-text({json.dumps(value)})").first
            item.click()
        elif native.count():
            native.select_option(value)
    ui.page.wait_for_timeout(250)
    if ui.page.locator(f"#{grid_id} .ag-cell-editor").count():
        ui.page.keyboard.press("Enter")
    ui.settle()


def _row_total(ui, grid_id: str) -> int:
    """How many rows the grid holds, not how many it has drawn: scroll to the end and read the last index."""
    _scroll_to_end(ui, grid_id)
    last = ui.page.evaluate(
        "gid => { let m = -1;"
        " document.querySelectorAll('#' + gid + ' .ag-center-cols-container .ag-row').forEach(r => {"
        " const i = parseInt(r.getAttribute('row-index'), 10); if (!isNaN(i) && i > m) { m = i; } });"
        " return m; }",
        grid_id,
    )
    return int(last) + 1


def _clear_cell(ui, grid_id: str, row_id: str, col: str) -> None:
    """Empty a text cell: selecting everything and committing keeps the old value, so delete it."""
    _reveal_cell(ui, grid_id, row_id, col)
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']").first
    cell.scroll_into_view_if_needed()
    cell.dblclick()
    ui.page.keyboard.press("Control+a")
    ui.page.keyboard.press("Delete")
    ui.page.keyboard.press("Enter")
    ui.settle()


def _editor_values(ui, grid_id: str, row_id: str, col: str) -> list[str]:
    """The list a cell offers, read by opening its editor and then leaving the cell alone."""
    _reveal_cell(ui, grid_id, row_id, col)
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']").first
    cell.scroll_into_view_if_needed()
    cell.dblclick()
    ui.page.wait_for_timeout(300)
    picker = ui.page.locator(f"#{grid_id} .ag-cell-editor .ag-picker-field-wrapper").first
    if picker.count():
        picker.click()
        ui.page.wait_for_timeout(400)
    values = [v.strip() for v in ui.page.locator(".ag-list-item").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(150)
    ui.page.keyboard.press("Escape")
    ui.settle()
    return values


def _opens_an_editor(ui, grid_id: str, row_id: str, col: str) -> bool:
    """Whether a cell may be typed into at all — the answer a read-only column has to give."""
    _reveal_cell(ui, grid_id, row_id, col)
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']").first
    cell.scroll_into_view_if_needed()
    cell.dblclick()
    ui.page.wait_for_timeout(300)
    open_ = bool(ui.page.locator(f"#{grid_id} .ag-cell-editor").count())
    ui.page.keyboard.press("Escape")
    ui.settle()
    return open_


def _tick(ui, grid_id: str, row_ids: list[str]) -> None:
    """Tick the rows an action is about to take, by the id the grid matches them on."""
    for row_id in row_ids:
        _reveal(ui, grid_id, row_id)
    ui.grid_tick_of(grid_id, row_ids)


def _filtered(ui, grid_id: str, col: str, text: str) -> int:
    """How many rows a column filter leaves, with the filter left on."""
    _filter(ui, grid_id, col, text)
    return _row_total(ui, grid_id)


def _clear_filter(ui, grid_id: str, col: str) -> None:
    _filter(ui, grid_id, col, "")


def _added_row(ui, grid_id: str, prefix: str) -> str:
    """The id of the row an Add button appended, which lands at the end of the grid."""
    ui.page.wait_for_timeout(400)
    _scroll_to_end(ui, grid_id)
    added = [r for r in ui.grid_row_ids(grid_id) if r and r.startswith(prefix)]
    return added[-1] if added else ""


def _save(ui) -> str:
    ui.click("mm-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    return ui.text("mm-feedback")


def _versions(ui) -> str:
    """The Versions tab, and what its table says."""
    _tab(ui, "Versions")
    ui.must("the versions table is on the tab", ui.visible("mm-versions-table"))
    return ui.text("mm-versions-table")


def _row_of(ui, ref: str) -> str:
    """What the Versions table says of one version, lower-cased: the row that carries its reference.

    Every state and every organisation in that table is a Mantine badge, and a badge is drawn
    in capitals, so a row is read without case rather than with the capitals written into the
    scenario — the page is saying `published`, in the only voice a badge has.
    """
    rows = ui.page.locator("#mm-versions-table tbody tr")
    for i in range(rows.count()):
        text = rows.nth(i).inner_text()
        if ref in text:
            return re.sub(r"\s+", " ", text).strip().lower()
    return ""


def _act(ui, action: str, ref: str) -> str:
    """Press one of a version's row buttons and read what the page said."""
    ui.click(_action_id(action, ref))
    ui.page.wait_for_timeout(300)
    ui.settle()
    return ui.text("mm-feedback")


def _confirm(ui) -> str:
    ui.must("the confirmation dialog opened", ui.visible("mm-confirm-modal-body"))
    ui.click("mm-confirm-yes")
    ui.page.wait_for_timeout(300)
    ui.settle()
    return ui.text("mm-feedback")


def _version_labels(ui) -> list[str]:
    """What the title's selector offers, leaving it closed again."""
    ui.click("mm-version-select")
    labels = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    return labels


def _upload(ui, path: Path) -> str:
    """Hand the Load YAML control a file, the way a reader's file dialog does."""
    ui.page.locator("#mm-reload input[type=file]").first.set_input_files(str(path))
    ui.page.wait_for_timeout(500)
    ui.settle()
    return ui.text("mm-feedback")


def _pack_badge(ui) -> str:
    """What the header says of the metamodel, lower-cased: it is a badge, drawn in capitals."""
    return ui.text("pack-badge").lower()


def _pack_file(run_dir: Path, stem: str, notes: str, **pack: str) -> Path:
    """The shipped pack as a draft under another version name (or with the header fields given),
    written where the run keeps its files."""
    data = yaml.safe_load(SHIPPED_FILE.read_text(encoding="utf-8"))
    data["pack"].update({"version": stem, "status": "draft", "notes": notes, **pack})
    path = run_dir / "downloads" / f"{stem}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


_LABELS = (
    "sel => { const el = document.querySelector(sel);"
    " if (!el) { return ''; }"
    " return Array.from(el.querySelectorAll('g.node, g.cluster'))"
    ".map(n => (n.textContent || '').trim()).join(' | '); }"
)


def _svg_text(ui, selector: str) -> str:
    """What a generated drawing actually says: the shape and layer labels, without mermaid's stylesheet."""
    return ui.page.evaluate(_LABELS, selector) or ""


def _preview_text(ui) -> str:
    return _svg_text(ui, PREVIEW)


def _await_label(ui, selector: str, needle: str, present: bool = True) -> bool:
    """A drawing is redrawn in the browser after its callback returns; wait for a label to come or go."""
    try:
        ui.page.wait_for_function(
            "([sel, needle, present]) => { const el = document.querySelector(sel);"
            " if (!el) { return false; }"
            " const hit = Array.from(el.querySelectorAll('g.node, g.cluster, g.edgeLabel, .edgeLabel'))"
            ".some(n => (n.textContent || '').includes(needle)); return hit === present; }",
            arg=[selector, needle, present],
            timeout=20_000,
        )
        return True
    except Exception:  # noqa: BLE001 — a drawing that never catches up is the check's finding
        return False


def _await_preview(ui, needle: str) -> bool:
    return _await_label(ui, PREVIEW, needle)


def _legend(ui, block: str) -> str:
    """The line above a diagram that says which colour is which layer."""
    return ui.text(_pm(id=block, type="mermaid-legend"))


def _layer_class(ui, type_id: str) -> str:
    """The layer a shape is filled by: mermaid writes the classDef's name onto the node."""
    return (
        ui.page.evaluate(
            "([sel, needle]) => { const el = document.querySelector(sel);"
            " if (!el) { return ''; }"
            " const g = Array.from(el.querySelectorAll('g.node'))"
            ".find(n => (n.textContent || '').includes(needle));"
            " return g ? (g.getAttribute('class') || '') : ''; }",
            [PREVIEW, f"[{type_id}]"],
        )
        or ""
    )


def _outline(ui, type_id: str) -> str:
    """What mermaid drew a type's shape with: a box is a <rect>, a hexagon a <polygon>."""
    return (
        ui.page.evaluate(
            "([sel, needle]) => { const el = document.querySelector(sel);"
            " if (!el) { return ''; }"
            " const g = Array.from(el.querySelectorAll('g.node'))"
            ".find(n => (n.textContent || '').includes(needle));"
            " if (!g) { return ''; }"
            " return Array.from(g.querySelectorAll('rect,polygon,path,circle,ellipse'))"
            ".map(e => e.tagName.toLowerCase()).sort().join(','); }",
            [PREVIEW, f"[{type_id}]"],
        )
        or ""
    )


def _label_of(ui, type_id: str) -> str:
    """The one label the preview drew for a type, so a check shows exactly what it said."""
    return (
        ui.page.evaluate(
            "([sel, needle]) => { const el = document.querySelector(sel);"
            " if (!el) { return ''; }"
            " const g = Array.from(el.querySelectorAll('g.node'))"
            ".find(n => (n.textContent || '').includes(needle));"
            " return g ? (g.textContent || '').trim() : ''; }",
            [PREVIEW, f"[{type_id}]"],
        )
        or f"(nothing drawn for {type_id})"
    )


def _await_class(ui, type_id: str, layer: str) -> bool:
    """The preview is redrawn in the browser; wait for the shape to carry the layer's fill class."""
    for _ in range(60):
        if layer in _layer_class(ui, type_id):
            return True
        ui.page.wait_for_timeout(250)
    return False


def _await_outline(ui, type_id: str, was: str) -> str:
    """The preview is redrawn in the browser; wait for the shape itself to change, not the label."""
    for _ in range(60):
        now = _outline(ui, type_id)
        if now and now != was:
            return now
        ui.page.wait_for_timeout(250)
    return _outline(ui, type_id)


# --------------------------------------------------------------------------- the type graph


@pytest.mark.scenario(
    scenario_id="J01",
    group="J",
    title="The Graph tab draws the version shown, one node per active type",
    feature="Metamodel · Graph",
    expected=(
        "The title names the pack, the version and the organisation that applies it, and the Graph "
        "tab draws one node per active type, grouped by domain, with a legend naming every domain."
    ),
)
def test_type_graph_renders(ui, record):
    _open(ui)
    subtitle = ui.text("mm-subtitle")
    ui.check("the page names the pack it is showing", "Higher Education EA Metamodel" in subtitle, subtitle)
    ui.check(
        "the page names the version and its state",
        f"version {PUBLISHED_VERSION} (published)" in subtitle,
        subtitle,
    )
    ui.check(
        "the page says which organisation applies the version", f"applied to {ORG}" in subtitle, subtitle
    )
    counts = _subtitle_counts(ui)
    ui.must("the page says how much of the pack is active", counts is not None, subtitle)
    ui.check(
        "the selector in the title reads the same version",
        PUBLISHED_VERSION in _shown_version(ui),
        _shown_version(ui),
    )
    _graph(ui)
    drawn = _cy(ui, "cy.$('node.type').length")
    ui.must("the graph drew type nodes", bool(drawn), f"{drawn} type nodes")
    ui.check(
        "the graph draws the types the page counted",
        drawn == counts[0],
        f"{drawn} drawn, {counts[0]} counted",
    )
    ui.check("a well-known type is on the canvas", _has_node(ui, TYPE))
    ui.check("an inactive type is left off the canvas", not _has_node(ui, "gateway"), "gateway is inactive")
    ui.check("the diamond for 'any element' is drawn", bool(_cy(ui, "cy.$('node.any').length")))
    ui.check(
        "sub-type edges are drawn dashed, not as relationships", bool(_cy(ui, "cy.$('edge.sub').length"))
    )
    boxes = _cy(ui, "cy.$('node.group').length")
    ui.check("the domains are grouped and labelled", bool(boxes), f"{boxes} group boxes")
    legend = ui.text(GP_LEGEND).lower()  # the badges are drawn in capitals
    for domain in DOMAINS:
        ui.check(f"the legend names the {domain} domain", domain.lower() in legend, legend)
    ui.check("the panel says what tapping a node does", "Tap a type to see its definition" in ui.body())
    ui.check(
        "the detail pane starts by saying what to do",
        "Tap a type" in ui.text("mm-detail"),
        ui.text("mm-detail"),
    )
    ui.shot("The metamodel drawn as a type graph, grouped by domain, with its detail pane waiting")


@pytest.mark.scenario(
    scenario_id="J02",
    group="J",
    title="The domain filter and the inactive switch decide what the type graph draws",
    feature="Metamodel · Graph · filters",
    expected=(
        "Choosing Information leaves only the information domain's types on the canvas, All domains "
        "puts the rest back, and 'Inactive types too' adds the retired ones."
    ),
)
def test_domain_filter_and_inactive_switch(ui, record):
    _open(ui)
    _graph(ui)
    everything = _cy(ui, "cy.$('node.type').length")
    ui.must("the unfiltered graph has types on it", bool(everything))
    ui.select("mm-domain-filter", "Information")
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    narrowed = _cy(ui, "cy.$('node.type').length")
    ui.check(
        "the filter narrowed the graph",
        narrowed and narrowed < everything,
        f"{everything} unfiltered, {narrowed} filtered",
    )
    ui.check("an information type is kept", _has_node(ui, TYPE))
    ui.check(
        "a type from another domain is dropped",
        not _has_node(ui, "actor"),
        "Actor belongs to the process domain",
    )
    boxes = _cy(ui, "cy.$('node.group').length")
    ui.check("only the one domain box is left", boxes == 1, f"{boxes} group boxes")
    ui.shot("The type graph narrowed to the information domain")
    ui.select("mm-domain-filter", "All domains")
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    restored = _cy(ui, "cy.$('node.type').length")
    ui.check("All domains puts every type back", restored == everything, f"{restored} back from {everything}")
    ui.toggle("mm-graph-inactive", True)
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    with_inactive = _cy(ui, "cy.$('node.type').length")
    ui.check(
        "the inactive switch adds the retired types",
        with_inactive > everything,
        f"{with_inactive} with, {everything} without",
    )
    ui.check("a retired type is drawn now", _has_node(ui, "gateway"), "gateway is inactive")
    ui.shot("The type graph with the inactive types drawn as well")
    ui.toggle("mm-graph-inactive", False)
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    ui.check("switching it off takes them away again", _cy(ui, "cy.$('node.type').length") == everything)


@pytest.mark.scenario(
    scenario_id="J03",
    group="J",
    title="Tapping a type fills the detail pane with its definition",
    feature="Metamodel · Graph · detail pane",
    expected=(
        "Tapping Data Entity shows its name, domain, provenance, description, examples, owners, "
        "its own attributes and the relationship types it may take part in."
    ),
)
def test_tapping_a_type_fills_the_detail(ui, record):
    _open(ui)
    _graph(ui)
    ui.must("the type node was tapped", _tap_type(ui, TYPE), f"no node for {TYPE}")
    detail = ui.text("mm-detail")
    ui.check("the pane names the type", "Data Entity" in detail, detail[:200])
    ui.check("the pane names its domain", "information" in detail.lower(), detail[:200])
    ui.check("the pane names where the type came from", "TOGAF" in detail, detail[:200])
    ui.check("the pane carries the definition", "physical encapsulation of data" in detail, detail[:300])
    ui.check("the pane lists the examples the pack gives", "Examples:" in detail and "HR_Employee" in detail)
    ui.check("the pane names the source of record", "Source of record:" in detail)
    ui.check("the pane names both owners", "Owners: type" in detail and "instances" in detail, detail)
    ui.check(
        "the pane lists the type's own attributes",
        "includes_pii" in detail and "available_in_analytics_platform" in detail,
        detail,
    )
    ui.check(
        "the pane lists what the type may point at",
        "Outgoing:" in detail and "contributes to → data_product" in detail,
        detail,
    )
    ui.check(
        "the pane lists what may point at the type",
        "Incoming:" in detail and "logical_data_component encapsulates" in detail,
        detail,
    )
    ui.shot("Tapping Data Entity fills the detail pane with its definition and its relationships")


# --------------------------------------------------------------------------- the tabs and the grids


@pytest.mark.scenario(
    scenario_id="J04",
    group="J",
    title="Six tabs over the version, and four lists inside Manage",
    feature="Metamodel · tabs",
    expected=(
        "Manage, Graph, Architecture view, Notation, Versions and Reviewers each open, mark themselves "
        "current and show their own panel; inside Manage the four lists each open their own grid, "
        "with the count of rows in the pill's label."
    ),
)
def test_the_tabs_and_the_lists(ui, record):
    _open(ui)
    tabs = ui.page.locator('#mm-tabs > [role="tablist"] [role="tab"]')
    ui.check(
        "the page offers the six tabs",
        tabs.count() == len(TABS),
        f"{tabs.count()} tabs: {tabs.all_inner_texts()}",
    )
    ui.check("Manage is open to begin with", _active_tab(ui) == "Manage", _active_tab(ui))
    proof = {
        "Manage": lambda: ui.visible("mm-types-grid"),
        "Graph": lambda: ui.visible(GP_CY),
        "Architecture view": lambda: (ui.wait_mermaid(), ui.visible(VIEW))[1],
        "Notation": lambda: ui.visible("mm-notation-domains-grid"),
        "Versions": lambda: ui.visible("mm-versions-table"),
        "Reviewers": lambda: ui.visible("mm-reviewers-grid"),
    }
    for label in TABS:
        _tab(ui, label)
        ui.check(f"the {label} tab marks itself current", _active_tab(ui) == label, _active_tab(ui))
        ui.check(f"the {label} tab shows its own panel", proof[label]())
    ui.shot("The Reviewers tab, the last of the six, open over its own grid")
    grids = {
        "Element types": "mm-types-grid",
        "Relationship types": "mm-rels-grid",
        "Attributes": "mm-attrs-grid",
        "Domains": "mm-domains-grid",
    }
    _tab(ui, "Manage")
    pills = ui.page.locator('#mm-lists [role="tab"]').all_inner_texts()
    ui.check(
        "each list says how many rows it holds",
        all(re.search(r"\(\d+\)$", p.strip()) for p in pills),
        str(pills),
    )
    for label, grid in grids.items():
        _list(ui, label)
        ui.check(f"the {label} list marks itself current", _active_list(ui) == label, _active_list(ui))
        ui.check(f"the {label} list shows its own grid", ui.visible(grid))
        others = [g for name, g in grids.items() if name != label]
        ui.check(
            f"the {label} list hides the other grids",
            not any(ui.visible(g) for g in others),
            f"visible: {[g for g in others if ui.visible(g)]}",
        )
        ui.check(f"the {label} grid has rows", ui.grid_row_count(grid) > 0, f"{grid} is empty")
    ui.shot("Manage: the Domains list, the last of the four, open over its own grid")


@pytest.mark.scenario(
    scenario_id="J05",
    group="J",
    title="The element types grid holds the pack, inheritance and all",
    feature="Metamodel · Manage · Element types",
    expected=(
        "Every element type is a row addressed by its id, with its name, plural, supertype, domain, "
        "provenance, prefix, whether it is active or abstract and its properties; the page says how to "
        "retire one, and that the published version cannot change in place."
    ),
)
def test_element_types_grid(ui, record):
    _open(ui)
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check("the row carries the type's name", _cell(ui, "mm-types-grid", TYPE, "name") == "Data Entity")
    ui.check("the row carries its plural", _cell(ui, "mm-types-grid", TYPE, "plural") == "Data Entities")
    ui.check("the row carries its domain", _cell(ui, "mm-types-grid", TYPE, "domain") == "information")
    ui.check("the row carries its provenance", _cell(ui, "mm-types-grid", TYPE, "provenance") == "TOGAF")
    ui.check("the row carries its identifier prefix", _cell(ui, "mm-types-grid", TYPE, "prefix") == "DE")
    ui.check(
        "the row names the owner of its instances",
        _cell(ui, "mm-types-grid", TYPE, "instance_owner") == SHIPPED_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "instance_owner"),
    )
    ui.check(
        "the id is pinned so a scrolled row is still identifiable",
        _cell(ui, "mm-types-grid", TYPE, "id") == TYPE,
    )
    ui.check(
        "a concrete type has its abstract box unticked",
        _tick_state(ui, "mm-types-grid", TYPE, "abstract") is False,
    )
    ui.check(
        "a type with no properties shows an empty properties cell",
        _cell(ui, "mm-types-grid", TYPE, "properties") == "",
    )
    ui.must("the sub-type row is in the grid", _reveal(ui, "mm-types-grid", SUB))
    ui.check(
        "a sub-type names the type it inherits from",
        _cell(ui, "mm-types-grid", SUB, "supertype") == "business_information",
        _cell(ui, "mm-types-grid", SUB, "supertype"),
    )
    ui.check(
        "an inactive type is kept in the grid rather than dropped", _reveal(ui, "mm-types-grid", "gateway")
    )
    ui.check(
        "a retired type is the one with its active box unticked",
        _tick_state(ui, "mm-types-grid", "gateway", "active") is False,
    )
    ui.check(
        "a type in use has its active box ticked", _tick_state(ui, "mm-types-grid", TYPE, "active") is True
    )
    body = ui.body()
    ui.check("the page says rows can be deleted", "Tick rows and delete them" in body, body[:400])
    ui.check(
        "and when to deactivate instead",
        "to keep existing content resolving, set a type's active to false instead" in body,
        body[:400],
    )
    ui.check("the page says what an abstract type is", "An abstract type groups its sub-types" in body)
    why = ui.text("mm-save-why")
    ui.check(
        "the page says the published version cannot change in place",
        "is published, so it cannot change" in why,
        why,
    )
    ui.check(
        "the save button says it will make a draft",
        "Save as a new draft" in ui.text("mm-save"),
        ui.text("mm-save"),
    )
    _grid_home(ui, "mm-types-grid")
    ui.shot("The element types grid, with the sub-type's supertype and an inactive type both in it")


@pytest.mark.scenario(
    scenario_id="J06",
    group="J",
    title="Saving an edit made on the published version creates a draft, and leaves the version applied alone",
    feature="Metamodel · Save as a new draft",
    expected=(
        "Changing the type owner of Data Entity and saving opens the draft dialog with a suggested "
        "version name; naming it j-draft creates the draft, shows it, and the organisation still "
        "applies the published version, which is unchanged."
    ),
)
def test_save_on_the_published_version_creates_a_draft(ui, record):
    _open(ui)
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the shipped owner is what the file says",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == SHIPPED_OWNER,
    )
    _set(ui, "mm-types-grid", TYPE, "type_owner", NEW_OWNER)
    ui.check(
        "the cell holds what was typed into it", _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER
    )
    ui.click("mm-save")
    ui.must("the draft dialog opened instead of saving in place", ui.visible("mm-draft-modal-body"))
    dialog = ui.text("mm-draft-modal-body")
    ui.check(
        "the dialog says why a draft is made",
        "The version shown is published, so it cannot change" in dialog,
        dialog[:200],
    )
    suggested = ui.page.locator("#mm-draft-version").first.input_value().strip()
    ui.check("a version name is suggested", bool(suggested), suggested or "(empty)")
    ui.check("the apply box names the organisation", f"Apply the draft to {ORG} now" in dialog, dialog)
    ui.check(
        "the draft is not applied to the default organisation unless asked",
        not ui.page.locator("#mm-draft-apply").first.is_checked(),
    )
    ui.shot("Saving an edit on the published version opens the draft dialog")
    ui.fill("mm-draft-version", DRAFT)
    ui.fill("mm-draft-notes", "J: the round's trial draft")
    ui.click("mm-draft-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    feedback = ui.text("mm-feedback")
    ui.must("the draft was created", f"Draft {DRAFT_REF} created from {PUBLISHED}" in feedback, feedback)
    ui.check("the dialog closed", not ui.visible("mm-draft-modal-body"))
    ui.check("nothing was applied", "Applied to" not in feedback, feedback)
    subtitle = ui.text("mm-subtitle")
    ui.check("the page now shows the draft", f"version {DRAFT} (draft)" in subtitle, subtitle)
    ui.check(
        "and says the organisation does not apply it",
        f"not the version {ORG} applies ({PUBLISHED})" in subtitle,
        subtitle,
    )
    ui.check("the selector reads the draft", DRAFT in _shown_version(ui), _shown_version(ui))
    ui.check("the save button now saves in place", ui.text("mm-save") == "Save changes", ui.text("mm-save"))
    ui.check(
        "the header still names the published version",
        _pack_badge(ui) == f"{PACK} · {PUBLISHED_VERSION}",
        _pack_badge(ui),
    )
    ui.must("the Data Entity row is in the draft's grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check("the draft carries the edit", _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER)
    _grid_home(ui, "mm-types-grid")
    ui.shot("The draft created from the edit, shown, with the organisation still on the published version")
    _open(ui)
    ui.check(
        "a fresh page opens on the version the organisation applies",
        f"version {PUBLISHED_VERSION} (published)" in ui.text("mm-subtitle"),
    )
    ui.must("the Data Entity row is in the published grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the published version is untouched", _cell(ui, "mm-types-grid", TYPE, "type_owner") == SHIPPED_OWNER
    )
    _show(ui, DRAFT)
    ui.must("the Data Entity row came back on the draft", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the edit survived the page being reloaded",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER,
    )
    # A save rebuilds the whole pack from the grids, so everything the edited row did not
    # touch has to come back unchanged: the prefix, the plural, and the type's attributes.
    ui.check("the draft kept the prefix", _cell(ui, "mm-types-grid", TYPE, "prefix") == "DE")
    ui.check("the draft kept the plural", _cell(ui, "mm-types-grid", TYPE, "plural") == "Data Entities")
    ui.must("the sub-type row came back", _reveal(ui, "mm-types-grid", SUB))
    ui.check(
        "the draft kept inheritance", _cell(ui, "mm-types-grid", SUB, "supertype") == "business_information"
    )
    _graph(ui)
    ui.must("the type node was tapped", _tap_type(ui, TYPE), f"no node for {TYPE}")
    detail = ui.text("mm-detail")
    ui.check("the detail pane reads the draft's owner back", NEW_OWNER in detail, detail)
    ui.check(
        "the draft kept the type's own attributes",
        "includes_pii" in detail and "available_in_analytics_platform" in detail,
        detail,
    )
    ui.check("the draft kept the examples", "HR_Employee" in detail, detail)
    ui.shot("The draft's graph: the detail pane reads the new owner back, with the type otherwise intact")


@pytest.mark.scenario(
    scenario_id="J07",
    group="J",
    title="Add type puts a new editable row at the end of the grid",
    feature="Metamodel · Manage · Add type",
    expected=(
        "Add type adds one row with an id of its own and a name to edit, and nothing is stored "
        "until a save is pressed."
    ),
)
def test_add_element_type(ui, record):
    _open(ui)
    _list(ui, "Element types")
    before = set(ui.grid_row_ids("mm-types-grid"))
    ui.click("mm-add-type")
    new_id = _added_row(ui, "mm-types-grid", "new_type_")
    ui.must("Add type added a row", bool(new_id), f"rows at the end: {ui.grid_row_ids('mm-types-grid')[-3:]}")
    ui.check("the new row was not one that was already there", new_id not in before)
    ui.check(
        "the new row carries a placeholder name to edit",
        _cell(ui, "mm-types-grid", new_id, "name") == "New type",
    )
    ui.check(
        "the new row starts active, so the type is usable straight away",
        _tick_state(ui, "mm-types-grid", new_id, "active") is True,
    )
    ui.check(
        "and concrete, so it can be an element's type",
        _tick_state(ui, "mm-types-grid", new_id, "abstract") is False,
    )
    _set(ui, "mm-types-grid", new_id, "name", "J Draft Type")
    ui.check(
        "the new row can be edited before it is saved",
        _cell(ui, "mm-types-grid", new_id, "name") == "J Draft Type",
    )
    ui.shot("Add type appended a row that can be filled in before anything is saved")
    # The row is deliberately not saved: leaving the page throws it away, which is what
    # a person expects of a grid they typed into and thought better of.
    _open(ui)
    _list(ui, "Element types")
    _scroll_to_end(ui, "mm-types-grid")
    ui.check(
        "leaving the page without saving discards the row",
        new_id not in set(ui.grid_row_ids("mm-types-grid")),
    )
    ui.shot("The unsaved row is gone after the page is left and reopened")


@pytest.mark.scenario(
    scenario_id="J08",
    group="J",
    title="The relationship types grid names both ends and both bounds of every relationship",
    feature="Metamodel · Manage · Relationship types",
    expected=(
        "Every relationship type is a row with its name, its inverse, its source and target types, "
        "its qualifiers and cardinality bounds where it has them, and Add relationship type appends one more."
    ),
)
def test_relationship_types_grid(ui, record):
    _open(ui)
    _list(ui, "Relationship types")
    ui.must("the encapsulates relationship type is in the grid", _reveal(ui, "mm-rels-grid", REL))
    ui.check("the row names the relationship", _cell(ui, "mm-rels-grid", REL, "name") == "encapsulates")
    ui.check("the row names the way back", _cell(ui, "mm-rels-grid", REL, "inverse") == "is encapsulated by")
    ui.check(
        "the row names the type it starts from",
        _cell(ui, "mm-rels-grid", REL, "source") == "logical_data_component",
    )
    ui.check("the row names the type it ends at", _cell(ui, "mm-rels-grid", REL, "target") == TYPE)
    ui.check(
        "the row carries the bounds either end may take", _reveal_cell(ui, "mm-rels-grid", REL, "dst_max")
    )
    ui.check("and a properties cell of its own", _reveal_cell(ui, "mm-rels-grid", REL, "properties"))
    qualified = "position__is_steward_of__information_asset"
    ui.must("the qualified relationship type is in the grid", _reveal(ui, "mm-rels-grid", qualified))
    ui.check(
        "a relationship type that takes a qualifier lists the qualifiers it takes",
        "Data Steward" in _cell(ui, "mm-rels-grid", qualified, "qualifiers"),
        _cell(ui, "mm-rels-grid", qualified, "qualifiers"),
    )
    _grid_home(ui, "mm-rels-grid")
    ui.check(
        "the header says how several qualifiers are written",
        "comma-separated" in ui.text("#mm-rels-grid .ag-header"),
    )
    ui.shot("The relationship types grid, with the qualified steward relationship shown")
    ui.click("mm-add-rel")
    new_id = _added_row(ui, "mm-rels-grid", "new_relationship_")
    ui.check("Add relationship type added a row", bool(new_id), f"{ui.grid_row_ids('mm-rels-grid')[-3:]}")
    if new_id:
        ui.check(
            "the new relationship starts open at both ends",
            _cell(ui, "mm-rels-grid", new_id, "source") == "ANY",
        )
    ui.shot("Add relationship type appended a row that starts open at both ends")


@pytest.mark.scenario(
    scenario_id="J09",
    group="J",
    title="The attributes grid lists every attribute with its owner, its type and its rules",
    feature="Metamodel · Manage · Attributes",
    expected=(
        "The common attributes come first with a blank owner, a type's own attribute names the type, "
        "the type column offers the attribute types as a list, the rule columns (required, default, "
        "multiple, group, help, unit, pattern, min, max) are there, and Add attribute appends one more."
    ),
)
def test_attributes_grid(ui, record):
    _open(ui)
    _list(ui, "Attributes")
    ui.must("the attributes grid has rows", ui.grid_row_count("mm-attrs-grid") > 0)
    ui.check(
        "the first rows are the common attributes, with no owner",
        ui.grid_cell("mm-attrs-grid", 0, "type_id") == "",
    )
    ui.check(
        "the owner column says what a blank owner means",
        "blank = common" in ui.text("#mm-attrs-grid .ag-header"),
    )
    _filter(ui, "mm-attrs-grid", "name", "includes_pii")
    ui.must(
        "the filter found the type's own attribute",
        _row_total(ui, "mm-attrs-grid") == 1,
        f"{_row_total(ui, 'mm-attrs-grid')} rows",
    )
    row = ui.grid_row_ids("mm-attrs-grid")[0]
    ui.check("the attribute names the type it belongs to", _cell(ui, "mm-attrs-grid", row, "type_id") == TYPE)
    ui.check("the attribute carries its type", _cell(ui, "mm-attrs-grid", row, "type") == "boolean")
    values = _editor_values(ui, "mm-attrs-grid", row, "type")
    ui.check(
        "the type column offers the attribute types as a list",
        {"string", "integer", "date", "url", "json"} <= set(values),
        str(values),
    )
    ui.check("required is a box to tick", _tick_state(ui, "mm-attrs-grid", row, "required") is not None)
    ui.check("multiple is a box to tick", _tick_state(ui, "mm-attrs-grid", row, "multiple") is False)
    for col in ("default", "group", "help", "unit", "pattern", "min", "max", "properties"):
        ui.check(f"the {col} column is there to fill", _reveal_cell(ui, "mm-attrs-grid", row, col))
    _grid_home(ui, "mm-attrs-grid")
    ui.shot("The attributes grid narrowed to one attribute of Data Entity, with its rule columns")
    _filter(ui, "mm-attrs-grid", "name", "")
    ui.click("mm-add-attr")
    new_row = _added_row(ui, "mm-attrs-grid", "")
    ui.must("Add attribute added a row", bool(new_row))
    ui.check(
        "the new attribute has a name to edit",
        _cell(ui, "mm-attrs-grid", new_row, "name").startswith("new_attribute_"),
    )
    ui.check("and starts as a string", _cell(ui, "mm-attrs-grid", new_row, "type") == "string")
    ui.shot("Add attribute appended a row that starts common and a string")


@pytest.mark.scenario(
    scenario_id="J10",
    group="J",
    title="A draft that does not validate is refused, and the draft is left as it was",
    feature="Metamodel · Save changes · validation",
    expected=(
        "Giving Data Entity a supertype that does not exist and saving the draft is refused with "
        "'Not saved' and the reason; reopening the draft shows the supertype untouched."
    ),
)
def test_invalid_save_is_refused(ui, record):
    _open(ui)
    _show(ui, DRAFT)
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    _set(ui, "mm-types-grid", TYPE, "supertype", "j_no_such_type")
    feedback = _save(ui)
    ui.must("the save was refused", feedback.startswith("Not saved:"), feedback or "(no feedback)")
    ui.check(
        "the refusal names the problem",
        "unknown supertype" in feedback and "j_no_such_type" in feedback,
        feedback,
    )
    ui.check("the page still shows the draft", DRAFT in _shown_version(ui), _shown_version(ui))
    _grid_home(ui, "mm-types-grid")
    ui.shot("A draft that cannot be validated is refused, with the reason")
    _open(ui)
    _show(ui, DRAFT)
    ui.must("the Data Entity row came back", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the draft is as it was",
        _cell(ui, "mm-types-grid", TYPE, "supertype") == "",
        _cell(ui, "mm-types-grid", TYPE, "supertype"),
    )


# --------------------------------------------------------------------------- notation


@pytest.mark.scenario(
    scenario_id="J11",
    group="J",
    title="The Notation tab's two grids drive the preview as it is edited",
    feature="Metamodel · Notation",
    expected=(
        "The domain grid and the type-override grid say how each type is drawn, the override grid "
        "shows what a blank cell inherits, and the preview redraws after every edit without saving."
    ),
)
def test_notation_grids_and_preview(ui, record):
    _open(ui)
    _tab(ui, "Notation")
    ui.must(
        "the domain notation grid has a row per domain", ui.grid_row_count("mm-notation-domains-grid") > 0
    )
    ui.must("the type override grid has rows", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "a domain row carries the colour it is drawn in",
        _cell(ui, "mm-notation-domains-grid", "information", "colour") == "blue",
    )
    ui.check(
        "a domain row carries the exact hex behind the colour",
        _cell(ui, "mm-notation-domains-grid", "information", "hex").startswith("#"),
    )
    inherited = _cell(ui, "mm-notation-types-grid", TYPE, "inherited")
    ui.check(
        "the override grid says what the type is actually drawn as",
        "application" in inherited and "Data Object" in inherited,
        inherited,
    )
    ui.check(
        "the tab says what a blank cell means", "inherits from the supertype, then the domain" in ui.body()
    )
    ui.must("the preview is drawn", ui.page.locator(f"{PREVIEW} svg").count() > 0)
    original = _preview_text(ui)
    ui.check("the preview draws a shape per active type", "Data Entity" in original, original[:200])
    ui.check("the preview writes the identifier into every shape", f"[{TYPE}]" in original, original[:200])
    ui.check("the preview carries the pack's stereotypes", "«" in original, original[:200])
    ui.shot("The Notation tab: the two grids and the preview drawn from them")
    _set(ui, "mm-notation-types-grid", TYPE, "glyph", GLYPH)
    ui.check("the preview redrew with the new glyph", _await_preview(ui, GLYPH), _preview_text(ui)[:300])
    ui.check(
        "the glyph landed on the type that was edited",
        f"{GLYPH} «Data Object» Data Entity" in _preview_text(ui),
        _preview_text(ui)[:300],
    )
    ui.shot("Changing one type's glyph redraws the preview beneath the grid, with nothing saved")
    _set(ui, "mm-notation-types-grid", TYPE, "stereotype", STEREOTYPE)
    ui.check(
        "the preview redrew with the new stereotype",
        _await_preview(ui, f"«{STEREOTYPE}»"),
        _preview_text(ui)[:300],
    )
    _set_select(ui, "mm-notation-domains-grid", "information", "colour", DOMAIN_COLOUR)
    ui.check(
        "the domain's colour is changed in the grid",
        _cell(ui, "mm-notation-domains-grid", "information", "colour") == DOMAIN_COLOUR,
    )
    ui.page.wait_for_timeout(600)
    ui.check(
        "the preview is still drawn after the colour change", ui.page.locator(f"{PREVIEW} svg").count() > 0
    )
    swatches = ui.text("mm-notation-swatches")
    ui.check(
        "and the chips that carry the domain colours follow the edit",
        DOMAIN_COLOUR in swatches.lower(),
        swatches[:200] or "(no chips)",
    )
    ui.shot("A domain colour change leaves the preview unchanged, because a view is filled by layer")
    _open(ui)
    _tab(ui, "Notation")
    ui.must("the type override row came back", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "leaving the page without saving discards the notation edits",
        _cell(ui, "mm-notation-types-grid", TYPE, "glyph") != GLYPH,
    )
    ui.check(
        "the preview is drawn from the stored version again",
        GLYPH not in _preview_text(ui),
        _preview_text(ui)[:200],
    )


# --------------------------------------------------------------------------- reviewers


@pytest.mark.scenario(
    scenario_id="J12",
    group="J",
    title="The Reviewers tab assigns a reviewer to an element type and saves it",
    feature="Metamodel · Reviewers",
    expected=(
        "Typing a reviewer against an element type and saving reports it saved, the assignment is "
        "read back after a reload, and clearing the cell and saving takes it off again."
    ),
)
def test_assign_a_reviewer(ui, record):
    _open(ui)
    _tab(ui, "Reviewers")
    ui.check("the tab says what an assignment means", "may be approved by any Reviewer" in ui.body())
    ui.check("the tab says the assignments belong to the organisation", "in this organisation" in ui.body())
    ui.must("the element type is in the reviewers grid", _reveal(ui, "mm-reviewers-grid", REVIEW_TYPE))
    ui.check(
        "the grid names the type as well as its id",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "type") == "Value Stream",
    )
    ui.check(
        "the type starts with nobody assigned", _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers") == ""
    )
    _set(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers", REVIEWER)
    ui.click("mm-reviewers-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    feedback = ui.text("mm-reviewers-feedback")
    ui.must("the assignment was saved", "saved" in feedback.lower(), feedback or "(no feedback at all)")
    ui.shot("Assigning a reviewer to an element type and saving says so")
    _open(ui)
    _tab(ui, "Reviewers")
    ui.must("the element type came back", _reveal(ui, "mm-reviewers-grid", REVIEW_TYPE))
    ui.check(
        "the assignment survived the page being reloaded",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers") == REVIEWER,
    )
    ui.shot("The saved reviewer assignment is read back on a fresh page")
    _clear_cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers")
    ui.click("mm-reviewers-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    _open(ui)
    _tab(ui, "Reviewers")
    ui.must("the element type came back a second time", _reveal(ui, "mm-reviewers-grid", REVIEW_TYPE))
    ui.check(
        "clearing the cell and saving takes the assignment off again",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers") == "",
    )


# --------------------------------------------------------------------------- versions


@pytest.mark.scenario(
    scenario_id="J13",
    group="J",
    title="Export YAML downloads the version shown, and a row's Export any version",
    feature="Metamodel · Export YAML",
    expected=(
        "Export YAML on the draft produces a pack file named for the pack and the version, holding the "
        "draft's edit, its state and what it derives from; the published row's Export produces the "
        "shipped definition."
    ),
)
def test_export_the_pack(ui, record):
    _open(ui)
    _show(ui, DRAFT)
    path = ui.download("mm-export", ".yaml")
    ui.check(
        "the file is named for the pack and the version",
        path.name == f"{PACK}-{DRAFT}-metamodel.yaml",
        path.name,
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ui.must("the download parses as a pack", isinstance(data, dict), type(data).__name__)
    pack = data.get("pack", {})
    ui.check(
        "the export names the pack and the version",
        (pack.get("id"), pack.get("version")) == (PACK, DRAFT),
        str(pack)[:200],
    )
    ui.check("the export says the version is a draft", pack.get("status") == "draft", str(pack.get("status")))
    ui.check("and what it derives from", pack.get("derived_from") == PUBLISHED, str(pack.get("derived_from")))
    ui.check("and carries its notes", "trial draft" in str(pack.get("notes")), str(pack.get("notes")))
    ui.check(
        "the export carries the domains",
        len(data.get("domains") or []) == len(DOMAINS),
        str(len(data.get("domains") or [])),
    )
    types = {t["id"]: t for t in data.get("element_types") or []}
    rels = {r["id"]: r for r in data.get("relationship_types") or []}
    ui.check("the export carries the element types", TYPE in types and SUB in types, str(len(types)))
    ui.check("the export carries the relationship types", REL in rels, str(len(rels)))
    ui.check("the export carries the common attributes", bool(data.get("common_attributes")))
    ui.check("the export keeps inheritance", types.get(SUB, {}).get("supertype") == "business_information")
    ui.check(
        "the export keeps a type's own attributes",
        {a["name"] for a in types.get(TYPE, {}).get("attributes") or []} >= {"includes_pii"},
    )
    ui.check(
        "the export keeps the notation a view is drawn from",
        (types.get(TYPE, {}).get("notation") or {}).get("archimate") == "DataObject",
    )
    ui.check(
        "the export is the draft as edited",
        types.get(TYPE, {}).get("type_owner") == NEW_OWNER,
        str(types.get(TYPE, {}).get("type_owner")),
    )
    _versions(ui)
    shipped = ui.download(_action_id("export", PUBLISHED), ".yaml")
    ui.check(
        "a row's Export names its own version",
        shipped.name == f"{PACK}-{PUBLISHED_VERSION}-metamodel.yaml",
        shipped.name,
    )
    shipped_data = yaml.safe_load(shipped.read_text(encoding="utf-8"))
    shipped_types = {t["id"]: t for t in shipped_data.get("element_types") or []}
    ui.check(
        "the published export is the shipped definition",
        shipped_types.get(TYPE, {}).get("type_owner") == SHIPPED_OWNER,
    )
    ui.check("and says it is published", shipped_data.get("pack", {}).get("status") == "published")
    ui.shot("The Versions tab, after both exports, with the page unchanged by them")


@pytest.mark.scenario(
    scenario_id="J14",
    group="J",
    title="The Versions tab lists every version, compares two, and shows the one chosen",
    feature="Metamodel · Versions",
    expected=(
        "The table lists the published version applied by the organisation and the draft applied by "
        "nobody, with what it derives from; Compare defaults to the two and lists the changed type "
        "owner; Show on the draft's row switches the whole page to the draft."
    ),
)
def test_versions_tab(ui, record):
    _open(ui)
    table = _versions(ui)
    ui.check("the tab says what a version's state means", "a published version is frozen" in ui.body())
    ui.must("both versions are listed", PUBLISHED in table and DRAFT_REF in table, table[:300])
    published = _row_of(ui, PUBLISHED)
    draft = _row_of(ui, DRAFT_REF)
    ui.check(
        "the published row says it is published and shown",
        "published" in published and "shown" in published,
        published,
    )
    ui.check("the published row says who applies it", ORG.lower() in published, published)
    ui.check("the draft row says it is a draft nobody applies", "draft" in draft and "nobody" in draft, draft)
    ui.check("the draft row names the version it derives from", PUBLISHED in draft, draft)
    ui.check("the draft row carries its notes", "trial draft" in draft, draft)
    ui.check("Show is disabled on the version already shown", ui.disabled(_action_id("show", PUBLISHED)))
    ui.check(
        "Retire is off while the organisation applies the version",
        ui.disabled(_action_id("retire", PUBLISHED)),
    )
    ui.check("Delete is off on a published version", ui.disabled(_action_id("delete", PUBLISHED)))
    ui.check("Publish is offered on the draft", not ui.disabled(_action_id("publish", DRAFT_REF)))
    href = ui.page.locator("#mm-tabs a[href*='/organisations']").first.get_attribute("href") or ""
    ui.check(
        "applying is handed to the Organisations page with the version shown",
        href == f"/organisations?version={PUBLISHED}",
        href,
    )
    cmp_from = ui.page.locator("#mm-cmp-a").first.input_value()
    cmp_to = ui.page.locator("#mm-cmp-b").first.input_value()
    ui.check("Compare starts from the version shown", PUBLISHED in cmp_from, cmp_from)
    ui.check("to the other version in the store", DRAFT_REF in cmp_to, cmp_to)
    ui.click("mm-cmp-run")
    result = ui.text("mm-cmp-result")
    ui.check(
        "the comparison names the type that changed",
        "element type" in result and TYPE in result,
        result[:300],
    )
    ui.check(
        "and the field, before and after",
        "type_owner" in result and NEW_OWNER in result and SHIPPED_OWNER in result,
        result[:300],
    )
    ui.check("and counts what changed", "element type: 1 changed" in result, result[:200])
    ui.shot("The Versions tab: both versions, and the difference between them")
    ui.select("mm-cmp-b", PUBLISHED, exact=False)
    ui.click("mm-cmp-run")
    ui.check(
        "a version compared with itself is reported as the same",
        "define the same metamodel" in ui.text("mm-cmp-result"),
        ui.text("mm-cmp-result"),
    )
    _act(ui, "show", DRAFT_REF)
    ui.check(
        "Show switches the page to the draft",
        f"version {DRAFT} (draft)" in ui.text("mm-subtitle"),
        ui.text("mm-subtitle"),
    )
    ui.check("the selector followed", DRAFT in _shown_version(ui), _shown_version(ui))
    ui.check("the tab stayed on Versions", _active_tab(ui) == "Versions", _active_tab(ui))
    ui.check(
        "the shown badge moved to the draft's row",
        "shown" in _row_of(ui, DRAFT_REF) and "shown" not in _row_of(ui, PUBLISHED),
    )
    ui.shot("Show on the draft's row: the whole page now shows the draft")


@pytest.mark.scenario(
    scenario_id="J15",
    group="J",
    title="An edit made under a column filter is the one that gets saved, and nothing hidden is lost",
    feature="Metamodel · Save changes · grid filters",
    expected=(
        "Narrowing the element types grid of the draft to one row, editing it and saving stores that "
        "edit in place and keeps every row the filter hid, in this grid and in the others."
    ),
)
def test_an_edit_under_a_filter_is_saved(ui, record):
    _open(ui)
    _show(ui, DRAFT)
    _list(ui, "Element types")
    types_before = _row_total(ui, "mm-types-grid")
    ui.must("the element types grid was counted", types_before > 1, f"{types_before} rows")
    _grid_home(ui, "mm-types-grid")
    _list(ui, "Relationship types")
    rels_before = _row_total(ui, "mm-rels-grid")
    ui.must("the relationship types grid was counted", rels_before > 1, f"{rels_before} rows")
    _grid_home(ui, "mm-rels-grid")
    _list(ui, "Element types")
    _filter(ui, "mm-types-grid", "id", TYPE)
    shown = _row_total(ui, "mm-types-grid")
    ui.must("the filter narrowed the grid to the one row", shown == 1, f"{shown} rows shown")
    _set(ui, "mm-types-grid", TYPE, "type_owner", FILTER_OWNER)
    ui.check(
        "the cell holds what was typed into it",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == FILTER_OWNER,
    )
    ui.shot("The draft's element types grid narrowed to one row, with that row edited")
    feedback = _save(ui)
    ui.must("the save was accepted", feedback.startswith(f"Version {DRAFT} saved:"), feedback[:300])
    stored = re.search(r"(\d+) types, (\d+) relationship types", feedback)
    ui.must("the save said what it stored", stored is not None, feedback[:300])
    ui.check(
        "saving keeps the element types the filter hid",
        int(stored.group(1)) == types_before,
        f"{types_before} before, {stored.group(1)} stored",
    )
    ui.check(
        "saving keeps the relationship types, which the filter never touched",
        int(stored.group(2)) == rels_before,
        f"{rels_before} before, {stored.group(2)} stored",
    )
    ui.check("the page still shows the draft", DRAFT in _shown_version(ui), _shown_version(ui))
    ui.shot("What the save reports it stored, with the filter still on the grid")
    _open(ui)
    _show(ui, DRAFT)
    ui.must("the Data Entity row came back", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the edit made under the filter is the one that was stored",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == FILTER_OWNER,
    )
    ui.check(
        "the grid holds as many types as it did before the save",
        _row_total(ui, "mm-types-grid") == types_before,
    )
    ui.must("the sub-type row came back", _reveal(ui, "mm-types-grid", SUB))
    ui.check(
        "a row the filter hid kept everything it carried",
        _cell(ui, "mm-types-grid", SUB, "supertype") == "business_information",
    )
    _graph(ui)
    ui.must("the type node was tapped", _tap_type(ui, TYPE), f"no node for {TYPE}")
    detail = ui.text("mm-detail")
    ui.check("the saved draft still holds the type's own attributes", "includes_pii" in detail, detail)
    ui.check(
        "and the relationship types it takes part in", "logical_data_component encapsulates" in detail, detail
    )
    ui.shot("After a save made under a filter, the draft is whole and the edit is in it")


# --------------------------------------------------------------------------- the architecture view


@pytest.mark.scenario(
    scenario_id="J16",
    group="J",
    title="The Architecture view draws the version in its own notation and downloads it",
    feature="Metamodel · Architecture view",
    expected=(
        "The view draws one shape per active element type labelled with its identifier, an 'is a' edge "
        "to a supertype and an edge per relationship type; the domain selector and the inactive switch "
        "redraw it; Markdown and draw.io downloads are named for the version."
    ),
)
def test_architecture_view(ui, record):
    _open(ui)
    _tab(ui, "Architecture view")
    ui.wait_mermaid()
    ui.must("the view is drawn", ui.visible(VIEW))
    labels = _svg_text(ui, VIEW)
    ui.check(
        "every shape carries its identifier", f"[{TYPE}]" in labels and f"[{SUB}]" in labels, labels[:200]
    )
    legend = _legend(ui, "mm-view")
    ui.check(
        "the layers are named above the diagram rather than boxed inside it",
        legend.startswith("Filled by layer:") and "Application (blue)" in legend,
        legend or "(no legend line)",
    )
    ui.check("an inactive type is left out", "[gateway]" not in labels)
    ui.check(
        "the tab says nothing is drawn by hand",
        "nothing here is drawn by hand" in ui.text("mm-view-note"),
        ui.text("mm-view-note"),
    )
    ui.shot("The metamodel drawn as an architecture view, in the notation it declares")
    ui.select("mm-view-domain", "Information")
    ui.must(
        "the view redrew for the domain",
        _await_label(ui, VIEW, "[actor]", present=False),
        _svg_text(ui, VIEW)[:200],
    )
    ui.check("an information type is kept", f"[{TYPE}]" in _svg_text(ui, VIEW))
    ui.shot("The view narrowed to the information domain")
    ui.select("mm-view-domain", "All domains")
    ui.must("All domains puts the rest back", _await_label(ui, VIEW, "[actor]"))
    ui.toggle("mm-view-inactive", True)
    ui.must("the inactive switch draws the retired types", _await_label(ui, VIEW, "[gateway]"))
    md = ui.download("mm-view-md", ".md")
    ui.check(
        "the Markdown is named for the version",
        md.name == f"{PACK}-{PUBLISHED_VERSION}-metamodel.md",
        md.name,
    )
    text = md.read_text(encoding="utf-8")
    ui.check("the Markdown holds the drawing", "```mermaid" in text and f"[{TYPE}]" in text)
    ui.check("with the legend a document opens with", "%% legend" in text)
    ui.check("and the state the view was in", "[gateway]" in text)
    drawio = ui.download("mm-view-drawio", ".drawio")
    root = ET.fromstring(drawio.read_text(encoding="utf-8"))
    cells = root.findall(".//mxCell")
    ui.check("the draw.io file holds a cell per shape and edge", len(cells) > 20, f"{len(cells)} cells")
    ui.check("and names the element types in them", any(TYPE in (c.get("value") or "") for c in cells))
    ui.shot("The view with the inactive types drawn, after both downloads")


# ------------------------------------------------------------- a second pass over the page
#
# Everything below came from reading the page source against the scenarios above: a control
# or a column no scenario worked (the Notation tab's three list columns, the ANY diamond,
# the domains list), a branch of a callback nothing reached (the preview's rebuild failing,
# the confirmation behind Retire and Delete, the frozen refusal of a loaded file), and a
# claim the page makes about itself that nothing checked (the counts in its subtitle, "a
# blank cell inherits from the supertype, then the domain").


@pytest.mark.scenario(
    scenario_id="J17",
    group="J",
    title="The page's own counts agree with the graph and the grids beneath them",
    feature="Metamodel · page title",
    expected=(
        "The subtitle's active, inactive, relationship-type and attribute counts are the numbers the "
        "graph and the four grids actually hold, not a summary that has drifted from them."
    ),
)
def test_the_counts_agree_with_what_is_drawn(ui, record):
    _open(ui)
    counts = _subtitle_counts(ui)
    ui.must("the subtitle says what the version holds", counts is not None, ui.text("mm-subtitle"))
    active, inactive, rels, attrs = counts
    ui.check("the version it names holds something", active > 0 and rels > 0 and attrs > 0, str(counts))
    _graph(ui)
    drawn = _cy(ui, "cy.$('node.type').length")
    ui.check(
        "the graph draws one node per active type it counted",
        drawn == active,
        f"{drawn} drawn, {active} counted",
    )
    _list(ui, "Element types")
    held = _row_total(ui, "mm-types-grid")
    ui.check(
        "the element types grid holds the active and the inactive types together",
        held == active + inactive,
        f"{held} rows, {active} + {inactive}",
    )
    _grid_home(ui, "mm-types-grid")
    _list(ui, "Relationship types")
    rel_rows = _row_total(ui, "mm-rels-grid")
    ui.check(
        "the relationship types grid holds the relationship types it counted",
        rel_rows == rels,
        f"{rel_rows} rows, {rels} counted",
    )
    _grid_home(ui, "mm-rels-grid")
    _list(ui, "Attributes")
    attr_rows = _row_total(ui, "mm-attrs-grid")
    ui.check(
        "the attributes grid holds the attributes it counted",
        attr_rows == attrs,
        f"{attr_rows} rows, {attrs} counted",
    )
    _grid_home(ui, "mm-attrs-grid")
    pills = " ".join(ui.page.locator('#mm-lists [role="tab"]').all_inner_texts())
    ui.check(
        "the list pills count the same rows",
        f"({held})" in pills and f"({rel_rows})" in pills and f"({attr_rows})" in pills,
        pills,
    )
    ui.shot("The attributes grid holding exactly what the page's subtitle counts")


@pytest.mark.scenario(
    scenario_id="J18",
    group="J",
    title="The Notation tab's three list columns are what a view is drawn from",
    feature="Metamodel · Notation · layer, shape and ArchiMate",
    expected=(
        "Changing a type's layer refills the shape in that layer's colour and names the layer in the "
        "line above the preview, changing its shape redraws the shape itself, and the ArchiMate "
        "column offers the draw.io stencils."
    ),
)
def test_notation_layer_shape_and_stencil(ui, record):
    _open(ui)
    _tab(ui, "Notation")
    ui.must("the preview is drawn", ui.page.locator(f"{PREVIEW} svg").count() > 0)
    ui.must("the type override row is in the grid", _reveal(ui, "mm-notation-types-grid", TYPE))
    legend = _legend(ui, "mm-notation-preview")
    ui.must(
        "a line above the preview says which colour is which layer",
        legend.startswith("Filled by layer:"),
        legend,
    )
    ui.check(
        "the type is drawn in the layer the pack gives it",
        _cell(ui, "mm-notation-types-grid", TYPE, "layer") == "application",
    )
    ui.check("the layer it is in is named and coloured", "Application (blue)" in legend, legend)
    ui.check(
        "the shape is filled by that layer", "application" in _layer_class(ui, TYPE), _layer_class(ui, TYPE)
    )
    ui.check("no type is drawn in the physical layer to begin with", "Physical" not in legend, legend)
    _set_select(ui, "mm-notation-types-grid", TYPE, "layer", UNUSED_LAYER)
    ui.check(
        "the layer cell holds what was chosen",
        _cell(ui, "mm-notation-types-grid", TYPE, "layer") == UNUSED_LAYER,
    )
    ui.check(
        "the shape is refilled in the new layer", _await_class(ui, TYPE, UNUSED_LAYER), _layer_class(ui, TYPE)
    )
    ui.check(
        "the line above the preview names the layer that appeared",
        "Physical (green)" in _legend(ui, "mm-notation-preview"),
        _legend(ui, "mm-notation-preview"),
    )
    ui.check(
        "the type is still drawn, and nothing else moved",
        f"[{TYPE}]" in _preview_text(ui) and "Application (blue)" in _legend(ui, "mm-notation-preview"),
        _legend(ui, "mm-notation-preview"),
    )
    ui.shot("Changing a type's layer refills its shape and names the layer above the preview")
    was = _outline(ui, TYPE)
    ui.check("the type is drawn as a box to begin with", "rect" in was, was or "(no shape found)")
    _set_select(ui, "mm-notation-types-grid", TYPE, "shape", "hex")
    now = _await_outline(ui, TYPE, was)
    ui.check("the preview redrew the type as another shape", now != was, f"{was!r} → {now!r}")
    ui.check(
        "the hexagon is drawn with an outline a box does not have",
        ("path" in now or "polygon" in now) and "path" not in was and "polygon" not in was,
        f"the box was drawn with {was!r}, the hexagon with {now!r}",
    )
    ui.shot("Changing a type's shape redraws the shape itself, not only its label")
    values = _editor_values(ui, "mm-notation-types-grid", TYPE, "archimate")
    ui.check(
        "the ArchiMate column offers a list rather than free text",
        len(values) > 5,
        f"{len(values)} options: {values[:8]}",
    )
    ui.check(
        "the list is the draw.io stencil set",
        "ApplicationComponent" in values,
        f"{len(values)} options: {values[:8]}",
    )
    # The ArchiMate name is what the draw.io export picks a stencil with; mermaid draws from
    # `shape` instead, so this column is read by the downloads (group N), not by the preview.
    _set_select(ui, "mm-notation-types-grid", TYPE, "archimate", "BusinessObject")
    ui.check(
        "the ArchiMate cell holds the stencil that was chosen",
        _cell(ui, "mm-notation-types-grid", TYPE, "archimate") == "BusinessObject",
    )
    _open(ui)
    _tab(ui, "Notation")
    ui.must("the type override row came back", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "leaving the page without saving discards the layer, the shape and the stencil",
        (
            _cell(ui, "mm-notation-types-grid", TYPE, "layer") == "application"
            and _cell(ui, "mm-notation-types-grid", TYPE, "shape") == "rect"
            and _cell(ui, "mm-notation-types-grid", TYPE, "archimate") == "DataObject"
        ),
        f"layer={_cell(ui, 'mm-notation-types-grid', TYPE, 'layer')} "
        f"shape={_cell(ui, 'mm-notation-types-grid', TYPE, 'shape')} "
        f"archimate={_cell(ui, 'mm-notation-types-grid', TYPE, 'archimate')}",
    )
    ui.check(
        "the preview is drawn from the stored version again",
        "Physical" not in _legend(ui, "mm-notation-preview"),
        _legend(ui, "mm-notation-preview"),
    )


@pytest.mark.scenario(
    scenario_id="J19",
    group="J",
    title="A blank notation cell inherits from the supertype, then the domain",
    feature="Metamodel · Notation · inheritance",
    expected=(
        "Emptying a type's glyph draws it with its supertype's; emptying the supertype's too "
        "draws both with the domain's, and a type in another domain is left alone."
    ),
)
def test_a_blank_notation_cell_inherits(ui, record):
    _open(ui)
    _tab(ui, "Notation")
    ui.check(
        "the tab says what a blank cell falls back to",
        "inherits from the supertype, then the domain" in ui.body(),
    )
    ui.must("the sub-type's notation row is in the grid", _reveal(ui, "mm-notation-types-grid", SUB))
    ui.must(
        "its supertype's row is in the grid", _reveal(ui, "mm-notation-types-grid", "business_information")
    )
    _set(ui, "mm-notation-types-grid", "business_information", "glyph", SUPER_GLYPH)
    ui.check(
        "the supertype is drawn with the glyph it was given",
        _await_preview(ui, f"{SUPER_GLYPH} «Business Object» Business Information"),
        _label_of(ui, "business_information"),
    )
    ui.check(
        "the sub-type still draws the glyph of its own",
        _label_of(ui, SUB).startswith("▤"),
        _label_of(ui, SUB),
    )
    _clear_cell(ui, "mm-notation-types-grid", SUB, "glyph")
    ui.check(
        "emptying the sub-type's glyph draws it with its supertype's",
        _await_preview(ui, f"{SUPER_GLYPH} «Business Object» Business Definition"),
        _label_of(ui, SUB),
    )
    ui.shot("With its own glyph emptied, the sub-type is drawn with the one its supertype carries")
    _clear_cell(ui, "mm-notation-types-grid", "business_information", "glyph")
    _set(ui, "mm-notation-domains-grid", "information", "glyph", DOMAIN_GLYPH)
    ui.check(
        "with neither the type nor its supertype naming one, the domain's glyph is drawn",
        _await_preview(ui, f"{DOMAIN_GLYPH} «Business Object» Business Definition"),
        _label_of(ui, SUB),
    )
    ui.check(
        "the supertype falls back to the same domain",
        _label_of(ui, "business_information").startswith(DOMAIN_GLYPH),
        _label_of(ui, "business_information"),
    )
    ui.check(
        "a type in the same domain that names a glyph of its own keeps it",
        _label_of(ui, TYPE) == f"▤ «Data Object» Data Entity [{TYPE}]",
        _label_of(ui, TYPE),
    )
    ui.check(
        "a type in another domain is not touched by this domain's glyph",
        _label_of(ui, "process") == "⚙ «Business Process» Process [process]",
        _label_of(ui, "process"),
    )
    ui.shot("With the supertype's glyph emptied too, both fall back to the domain's")
    _open(ui)
    _tab(ui, "Notation")
    ui.must("the sub-type's row came back", _reveal(ui, "mm-notation-types-grid", SUB))
    ui.check(
        "leaving the page without saving puts the shipped glyphs back",
        _cell(ui, "mm-notation-types-grid", SUB, "glyph") not in ("", SUPER_GLYPH, DOMAIN_GLYPH),
        _cell(ui, "mm-notation-types-grid", SUB, "glyph"),
    )
    ui.check(
        "and the preview is drawn from them",
        SUPER_GLYPH not in _preview_text(ui) and DOMAIN_GLYPH not in _preview_text(ui),
        f"{_label_of(ui, SUB)} · {_label_of(ui, 'business_information')}",
    )


@pytest.mark.scenario(
    scenario_id="J20",
    group="J",
    title="A domain and a type added and saved reach the draft, the graph and the page's own count",
    feature="Metamodel · Manage · Add domain, Add type, Save changes",
    expected=(
        "Filling in an added domain and an added type in it and saving the draft stores both, draws "
        "the type on the graph under the new domain without the page being reloaded, offers the domain "
        "in the graph's filter, and leaves no count on the page contradicting it."
    ),
)
def test_adding_a_domain_and_a_type_and_saving(ui, record):
    _open(ui)
    _show(ui, DRAFT)
    counts = _subtitle_counts(ui)
    ui.must("the subtitle says what the draft holds", counts is not None, ui.text("mm-subtitle"))
    active_before = counts[0]
    _list(ui, "Domains")
    ui.must("the domains grid lists the pack's domains", _reveal(ui, "mm-domains-grid", "information"))
    ui.check(
        "a domain row carries its name", _cell(ui, "mm-domains-grid", "information", "name") == "Information"
    )
    ui.click("mm-add-domain")
    new_domain_row = _added_row(ui, "mm-domains-grid", "new_domain_")
    ui.must("Add domain added a row", bool(new_domain_row))
    _set(ui, "mm-domains-grid", new_domain_row, "id", NEW_DOMAIN)
    _set(ui, "mm-domains-grid", new_domain_row, "name", NEW_DOMAIN_NAME)
    _set(ui, "mm-domains-grid", new_domain_row, "description", "A domain the round added.")
    ui.check(
        "the domain's id can be set before it is saved",
        _cell(ui, "mm-domains-grid", new_domain_row, "id") == NEW_DOMAIN,
    )
    _list(ui, "Element types")
    types_before = _row_total(ui, "mm-types-grid")
    ui.click("mm-add-type")
    new_row = _added_row(ui, "mm-types-grid", "new_type_")
    ui.must(
        "Add type added a row", bool(new_row), f"rows at the end: {ui.grid_row_ids('mm-types-grid')[-3:]}"
    )
    ui.check("an added type's id can be set", _opens_an_editor(ui, "mm-types-grid", new_row, "id"))
    ui.check("an existing type's id cannot", not _opens_an_editor(ui, "mm-types-grid", TYPE, "id"))
    _set(ui, "mm-types-grid", new_row, "id", "j_saved_type")
    _set(ui, "mm-types-grid", new_row, "name", NEW_TYPE_NAME)
    _set(ui, "mm-types-grid", new_row, "plural", "J Saved Types")
    _set(ui, "mm-types-grid", new_row, "domain", NEW_DOMAIN)
    _set(ui, "mm-types-grid", new_row, "prefix", "JST")
    _grid_home(ui, "mm-types-grid")
    feedback = _save(ui)
    ui.must("the save was accepted", feedback.startswith(f"Version {DRAFT} saved:"), feedback[:300])
    stored = re.search(r"(\d+) types", feedback)
    ui.must("the save said how many types it stored", stored is not None, feedback[:300])
    # A row added by the button is in the grid but not yet in the rowData the page was given,
    # so this is the one path where the save has to take what is only on screen.
    ui.check(
        "the save stored one type more than the draft held",
        int(stored.group(1)) == types_before + 1,
        f"{types_before} before, {stored.group(1)} stored",
    )
    after = _subtitle_counts(ui)
    ui.check(
        "the page's own count of active types followed the save",
        after is not None and after[0] == active_before + 1,
        str(after),
    )
    _graph(ui)
    ui.check("the new type is a node of its own", _has_node(ui, "j_saved_type"))
    ui.check("the type graph draws one more type", _cy(ui, "cy.$('node.type').length") == active_before + 1)
    ui.select("mm-domain-filter", NEW_DOMAIN_NAME)
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    ui.check(
        "the graph's filter offers the new domain and narrows to its one type",
        _cy(ui, "cy.$('node.type').length") == 1,
    )
    ui.shot("A domain and a type added and saved: on the graph at once, under the new domain")
    _open(ui)
    _show(ui, DRAFT)
    _list(ui, "Element types")
    ui.check("the type is in the stored draft", _reveal(ui, "mm-types-grid", "j_saved_type"))
    ui.check(
        "with the name it was given", _cell(ui, "mm-types-grid", "j_saved_type", "name") == NEW_TYPE_NAME
    )
    _list(ui, "Domains")
    ui.check("the domain is in the stored draft", _reveal(ui, "mm-domains-grid", NEW_DOMAIN))
    _open(ui)
    _graph(ui)
    ui.check("the published version the organisation applies is untouched", not _has_node(ui, "j_saved_type"))


@pytest.mark.scenario(
    scenario_id="J21",
    group="J",
    title="Ticked rows are deleted with what depended on them, and nothing is stored until the save",
    feature="Metamodel · Manage · delete",
    expected=(
        "Deleting a domain clears the domain of the types in it rather than deleting them; deleting "
        "element types takes the relationship types that named them and their attributes, and warns "
        "that content in the organisation is of that type; the save writes it and the graph follows; "
        "a deletion not saved is undone by leaving the page; and nothing ticked deletes nothing."
    ),
)
def test_deleting_rows(ui, record):
    _open(ui)
    _show(ui, DRAFT)
    # Nothing ticked is a refusal, not a silent no-op.
    _list(ui, "Element types")
    ui.click("mm-del-type")
    ui.page.wait_for_timeout(300)
    ui.settle()
    nothing = ui.text("mm-feedback")
    ui.check(
        "with nothing ticked the page says so", "Tick the element types to delete first" in nothing, nothing
    )
    ui.check("and nothing left the grid", "Taken out of the grids" not in nothing, nothing)

    # A domain: its types are kept, their domain cleared, because deleting a domain is not
    # an instruction to delete everything in it.
    _list(ui, "Domains")
    ui.must("the domain J20 added is in the grid", _reveal(ui, "mm-domains-grid", NEW_DOMAIN))
    _tick(ui, "mm-domains-grid", [NEW_DOMAIN])
    ui.click("mm-del-domain")
    ui.page.wait_for_timeout(300)
    ui.settle()
    said = ui.text("mm-feedback")
    ui.check("the domain went", "1 domain(s)" in said, said)
    ui.check(
        "and the type in it did not",
        "the domain of 1 element type(s), cleared rather than deleted" in said,
        said,
    )
    ui.check("the page says nothing is stored yet", "Nothing is stored yet" in said, said)
    ui.check("the domain is off the grid", NEW_DOMAIN not in set(ui.grid_row_ids("mm-domains-grid")))
    _list(ui, "Element types")
    ui.must("the type J20 added is still there", _reveal(ui, "mm-types-grid", "j_saved_type"))
    ui.check("with its domain cleared", _cell(ui, "mm-types-grid", "j_saved_type", "domain") == "")
    ui.shot("A domain deleted: the types that were in it stay, with the domain cleared")

    # Two element types: one the round added, one the sample model uses.
    _list(ui, "Relationship types")
    rels_before = _row_total(ui, "mm-rels-grid")
    measure_rels = _filtered(ui, "mm-rels-grid", "id", "measure")
    ui.must("the sample's type is an end of some relationship types", measure_rels > 0, f"{measure_rels}")
    _clear_filter(ui, "mm-rels-grid", "id")
    _list(ui, "Element types")
    types_before = _row_total(ui, "mm-types-grid")
    _tick(ui, "mm-types-grid", ["j_saved_type", DELETED_TYPE])
    ui.click("mm-del-type")
    ui.page.wait_for_timeout(300)
    ui.settle()
    said = ui.text("mm-feedback")
    ui.check("both types went", "2 element type(s)" in said, said)
    ui.check(
        "and the relationship types that named one of them as an end",
        f"{measure_rels} relationship type(s) that named one of them as an end" in said,
        said,
    )
    ui.check("and the attributes of what went", "attribute(s) of what went with them" in said, said)
    ui.check(
        "the page says what content in this organisation is of that type",
        f"element(s) in {ORG} are of what you deleted" in said,
        said,
    )
    ui.check(
        "the types are off the grid",
        not {"j_saved_type", DELETED_TYPE} & set(ui.grid_row_ids("mm-types-grid")),
    )
    ui.check("the grid holds two rows fewer", _row_total(ui, "mm-types-grid") == types_before - 2)
    _list(ui, "Relationship types")
    ui.check(
        "the relationship types went with them", _row_total(ui, "mm-rels-grid") == rels_before - measure_rels
    )
    ui.shot("Two element types deleted, with the relationship types and attributes that depended on them")

    feedback = _save(ui)
    ui.must("the save was accepted", feedback.startswith(f"Version {DRAFT} saved:"), feedback[:300])
    stored = re.search(r"(\d+) types, (\d+) relationship types", feedback)
    ui.must("the save said what it stored", stored is not None, feedback[:300])
    ui.check(
        "the deletion is what was stored",
        int(stored.group(1)) == types_before - 2,
        f"{stored.group(1)} types",
    )
    ui.check("and the relationship types with it", int(stored.group(2)) == rels_before - measure_rels)
    _graph(ui)
    ui.check("the type graph no longer draws the deleted type", not _has_node(ui, DELETED_TYPE))
    ui.shot("After the save: the draft and its graph without what was deleted")

    _open(ui)
    _show(ui, DRAFT)
    _list(ui, "Element types")
    ui.check("the deletion survived the page being reloaded", not _reveal(ui, "mm-types-grid", DELETED_TYPE))
    _open(ui)
    _list(ui, "Element types")
    ui.check(
        "the published version the organisation applies is untouched",
        _reveal(ui, "mm-types-grid", DELETED_TYPE),
        "the deletion was made on the draft alone",
    )

    # A deletion that is not saved is undone by leaving the page, which is what the page promises.
    _show(ui, DRAFT)
    _list(ui, "Attributes")
    attrs_before = _row_total(ui, "mm-attrs-grid")
    row = f"{TYPE}|includes_pii"
    ui.must("the attribute is in the grid", _reveal(ui, "mm-attrs-grid", row))
    _tick(ui, "mm-attrs-grid", [row])
    ui.click("mm-del-attr")
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.check(
        "the attribute went from the grid", "1 attribute(s)" in ui.text("mm-feedback"), ui.text("mm-feedback")
    )
    ui.check("the grid is one row shorter", _row_total(ui, "mm-attrs-grid") == attrs_before - 1)
    _open(ui)
    _show(ui, DRAFT)
    _list(ui, "Attributes")
    ui.check(
        "leaving the page without saving puts the attribute back",
        _reveal(ui, "mm-attrs-grid", row) and _row_total(ui, "mm-attrs-grid") == attrs_before,
        f"{_row_total(ui, 'mm-attrs-grid')} rows, {attrs_before} before",
    )
    ui.shot("The unsaved deletion is undone by leaving the page")


@pytest.mark.scenario(
    scenario_id="J22",
    group="J",
    title="The preview says why it has stopped following, and follows again once the grid is fixed",
    feature="Metamodel · Notation · preview",
    expected=(
        "With a row in another grid the pack cannot be built from, a notation edit leaves a note "
        "saying what holds the preview back; fixing the row and editing again redraws it and clears the note."
    ),
)
def test_the_preview_when_another_grid_is_broken(ui, record):
    _open(ui)
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    _set(ui, "mm-types-grid", TYPE, "supertype", "j_no_such_type")
    ui.check(
        "the element types grid holds the row the pack cannot be built from",
        _cell(ui, "mm-types-grid", TYPE, "supertype") == "j_no_such_type",
    )
    _tab(ui, "Notation")
    before = _preview_text(ui)
    ui.must("the preview is drawn", bool(before), "(nothing in the preview)")
    ui.must("the type override row is in the grid", _reveal(ui, "mm-notation-types-grid", TYPE))
    _set(ui, "mm-notation-types-grid", TYPE, "glyph", GLYPH)
    ui.check(
        "the glyph cell holds what was typed into it",
        _cell(ui, "mm-notation-types-grid", TYPE, "glyph") == GLYPH,
    )
    ui.page.wait_for_timeout(800)
    note = ui.text("mm-notation-note")
    ui.check(
        "the tab says the preview cannot be drawn",
        "The preview cannot be drawn from the grids as they stand" in note,
        note or "(no note)",
    )
    ui.check("and names what holds it back", "j_no_such_type" in note, note)
    ui.check("and that it will follow again", "It will follow again once that is fixed" in note, note)
    ui.check("the last drawing is left on screen rather than blanked", bool(_preview_text(ui)))
    ui.shot(
        "A notation edit made while another grid holds an unbuildable row, and the note beneath the grids"
    )
    _list(ui, "Element types")
    _clear_cell(ui, "mm-types-grid", TYPE, "supertype")
    ui.check("the supertype is empty again", _cell(ui, "mm-types-grid", TYPE, "supertype") == "")
    _tab(ui, "Notation")
    _set(ui, "mm-notation-types-grid", TYPE, "stereotype", STEREOTYPE)
    ui.check(
        "with every grid buildable again, the next edit reaches the preview",
        _await_preview(ui, f"«{STEREOTYPE}»"),
        _preview_text(ui)[:300],
    )
    ui.check("and the glyph typed while it was held back is drawn too", GLYPH in _preview_text(ui))
    ui.check("the note is gone", ui.text("mm-notation-note") == "", ui.text("mm-notation-note"))
    ui.shot("The grid fixed: the preview follows again and the note is gone")


@pytest.mark.scenario(
    scenario_id="J23",
    group="J",
    title="Tapping the diamond for 'any element' leaves the detail pane as it was",
    feature="Metamodel · Graph · the ANY diamond",
    expected=(
        "The diamond stands for no type, so tapping it neither fills the detail pane nor empties "
        "it, and the hint beneath the graph says what it is."
    ),
)
def test_tapping_the_any_diamond(ui, record):
    _open(ui)
    _graph(ui)
    ui.check("the hint says what the diamond is", "diamond = any element" in ui.text("#page"))
    ui.check("the hint says what a dashed edge is", "Dashed edge = sub-type" in ui.text("#page"))
    ui.check(
        "the diamond is labelled on the canvas too",
        _cy(ui, "cy.$('node.any')[0].data('label')") == "Any element",
    )
    ui.check(
        "the diamond stands for no element type", _cy(ui, "cy.$('node.any')[0].data('element_id')") == ""
    )
    ui.must("the type node was tapped", _tap_type(ui, TYPE), f"no node for {TYPE}")
    filled = ui.text("mm-detail")
    ui.must("the pane is showing a type to begin with", "Data Entity" in filled, filled[:200])
    ui.must("the diamond was tapped", _tap_any(ui))
    after = ui.text("mm-detail")
    ui.check("tapping the diamond does not empty the pane", bool(after.strip()), "(the pane went blank)")
    ui.check(
        "the pane is left showing the type the reader last opened",
        after == filled,
        f"{after[:160]!r} after, {filled[:160]!r} before",
    )
    ui.shot("Tapping the diamond leaves the type the reader was reading in the detail pane")


@pytest.mark.scenario(
    scenario_id="J24",
    group="J",
    title="Publish freezes the draft; Retire and Delete ask first, and take it out of use and out of the store",
    feature="Metamodel · Versions · Publish, Retire, Delete",
    expected=(
        "Publish reports the draft published and frozen, after which an edit on it opens the draft "
        "dialog again; Retire asks, then reports it retired; Delete asks, removes it, and the page "
        "falls back to the version the organisation applies."
    ),
)
def test_publish_retire_and_delete(ui, record):
    _open(ui)
    _versions(ui)
    feedback = _act(ui, "publish", DRAFT_REF)
    ui.must("the draft was published", f"{DRAFT_REF} is published and frozen." in feedback, feedback)
    row = _row_of(ui, DRAFT_REF)
    ui.check("the row says it is published", "published" in row, row)
    ui.check("Publish is off once it is published", ui.disabled(_action_id("publish", DRAFT_REF)))
    ui.check("Retire is offered, because nobody applies it", not ui.disabled(_action_id("retire", DRAFT_REF)))
    ui.check("Delete is off on a published version", ui.disabled(_action_id("delete", DRAFT_REF)))
    ui.shot("The draft published: frozen, retirable, not deletable")
    _show(ui, DRAFT)
    ui.check(
        "the page says the version cannot change in place",
        "is published, so it cannot change" in ui.text("mm-save-why"),
        ui.text("mm-save-why"),
    )
    ui.check(
        "the save button offers a draft instead",
        "Save as a new draft" in ui.text("mm-save"),
        ui.text("mm-save"),
    )
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    _set(ui, "mm-types-grid", TYPE, "type_owner", "J after publishing")
    ui.click("mm-save")
    ui.check("an edit on the published draft opens the draft dialog", ui.visible("mm-draft-modal-body"))
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.check(
        "closing the dialog saves nothing",
        not ui.visible("mm-draft-modal-body") and "saved" not in ui.text("mm-feedback").lower(),
    )
    _versions(ui)
    _act(ui, "retire", DRAFT_REF)
    ui.check(
        "Retire asks first, naming the version",
        f"Retire {DRAFT_REF}?" in ui.text("mm-confirm-text"),
        ui.text("mm-confirm-text"),
    )
    feedback = _confirm(ui)
    ui.must("the version was retired", f"{DRAFT_REF} is retired." in feedback, feedback)
    ui.check("the row says so", "retired" in _row_of(ui, DRAFT_REF), _row_of(ui, DRAFT_REF))
    ui.check("a retired version may be deleted", not ui.disabled(_action_id("delete", DRAFT_REF)))
    ui.shot("The version retired: kept for the record, no longer applicable")
    _act(ui, "delete", DRAFT_REF)
    ui.check(
        "Delete asks first, naming the version",
        f"Delete {DRAFT_REF}?" in ui.text("mm-confirm-text"),
        ui.text("mm-confirm-text"),
    )
    feedback = _confirm(ui)
    ui.must("the version was deleted", f"{DRAFT_REF} deleted." in feedback, feedback)
    ui.check("the table no longer lists it", DRAFT_REF not in ui.text("mm-versions-table"))
    ui.check(
        "the page fell back to the version the organisation applies",
        f"version {PUBLISHED_VERSION} (published)" in ui.text("mm-subtitle"),
        ui.text("mm-subtitle"),
    )
    labels = _version_labels(ui)
    ui.check("the selector no longer offers it", not any(DRAFT in x for x in labels), str(labels))
    ui.shot("The draft deleted: one version in the store again, the one the organisation applies")


@pytest.mark.scenario(
    scenario_id="J25",
    group="J",
    title="Load YAML file stores the version a file names and applies it after the check; the shipped file puts the shipped version back",
    feature="Metamodel · Load YAML file",
    expected=(
        "A file that differs from the published version under its name is refused as frozen; a file "
        "naming a new version is stored as a draft and applied to the organisation after its content "
        "is checked; loading the shipped file applies the shipped version again, and the draft can then be deleted."
    ),
)
def test_load_a_yaml_file(ui, record):
    _open(ui)
    frozen = _pack_file(
        ui.run_dir,
        "j-frozen",
        "J: a file that differs from the published version",
        version=PUBLISHED_VERSION,
        name="J edited edition",
    )
    feedback = _upload(ui, frozen)
    ui.check(
        "a file that differs from a published version is refused",
        feedback.startswith("j-frozen.yaml not loaded:") and "frozen" in feedback,
        feedback,
    )
    ui.check(
        "the header still names the published version",
        _pack_badge(ui) == f"{PACK} · {PUBLISHED_VERSION}",
        _pack_badge(ui),
    )
    trial = _pack_file(ui.run_dir, FILE_VERSION, "J: loaded from a file")
    feedback = _upload(ui, trial)
    ui.must(
        "the file's version was stored",
        feedback.startswith(f"Loaded {FILE_REF} (draft) from {FILE_VERSION}.yaml."),
        feedback,
    )
    ui.check(
        "and applied to the organisation after the check",
        f"Applied to {ORG}:" in feedback and "0 errors" in feedback,
        feedback,
    )
    ui.check(
        "the header names the loaded version",
        _pack_badge(ui) == f"{PACK} · {FILE_VERSION} · draft",
        _pack_badge(ui),
    )
    ui.check(
        "the page shows it as applied",
        f"version {FILE_VERSION} (draft), applied to {ORG}" in ui.text("mm-subtitle"),
        ui.text("mm-subtitle"),
    )
    ui.check(
        "the selector says which version is applied here",
        any(FILE_VERSION in x and "applied here" in x for x in _version_labels(ui)),
        str(_version_labels(ui)),
    )
    _versions(ui)
    ui.check(
        "the versions table shows the organisation on the loaded version",
        ORG.lower() in _row_of(ui, FILE_REF),
        _row_of(ui, FILE_REF),
    )
    ui.check("and nobody on the published one", "nobody" in _row_of(ui, PUBLISHED), _row_of(ui, PUBLISHED))
    ui.shot("A version loaded from a file, stored as a draft and applied to the organisation")
    feedback = _upload(ui, SHIPPED_FILE)
    ui.must(
        "the shipped file is loaded again",
        feedback.startswith(f"Loaded {PUBLISHED} (published) from metamodel.yaml."),
        feedback,
    )
    ui.check(
        "and the organisation applies the shipped version again", f"Applied to {ORG}:" in feedback, feedback
    )
    ui.check(
        "the header names the shipped version again",
        _pack_badge(ui) == f"{PACK} · {PUBLISHED_VERSION}",
        _pack_badge(ui),
    )
    _versions(ui)
    _act(ui, "delete", FILE_REF)
    feedback = _confirm(ui)
    ui.check(
        "the loaded draft, applied by nobody now, is deleted", f"{FILE_REF} deleted." in feedback, feedback
    )
    ui.check(
        "one version is left, the shipped one",
        ui.text("mm-versions-table").count(PACK + "@") == 1,
        ui.text("mm-versions-table")[:200],
    )
    _open(ui)
    _list(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the metamodel is the shipped one again, for the groups that follow",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == SHIPPED_OWNER,
    )
    _grid_home(ui, "mm-types-grid")
    ui.shot("The metamodel is back to what the repository ships, ready for the groups that follow")
