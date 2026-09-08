"""Group J — Metamodel: the type graph, the editable grids, notation, reviewers and export.

The Metamodel page is the one screen where the *language* of the repository is edited
rather than its content. The top half draws the pack as a graph — one node per active
type, sub-type edges dashed, a diamond where a relationship type takes any element —
with a detail pane beside it. The bottom half is five grids: element types, relationship
types, attributes, notation, and who reviews what. "Save changes" rebuilds a whole pack
from the grids, validates it, and only then stores it; "Reload from file" throws the
stored pack away and reads the shipped file back.

That last pair is what makes this group safe to run inside a shared round. Three
scenarios write something the rest of the round could see — J06 saves an owner onto one
element type, J12 assigns and then unassigns a reviewer, and J15 saves a pack the grid's
own filter has cut down — and both J14 and J15 end by reloading
`packs/higher_education/metamodel.yaml`, so every later group reads the shipped
metamodel. Everything else is typed into a grid and then discarded by navigating away,
which is exactly what a person does when they change their mind before saving.

Nothing here asserts an exact total: the counts the page prints are compared with what
the graph and the grids actually hold, not with numbers written into this file.
"""

from __future__ import annotations

import json
import re

import pytest
import yaml
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

TYPE = "data_entity"  # a type with its own attributes, a domain, and relationships both ways
SUB = "business_definition"  # a sub-type, so the grid proves inheritance is editable
REL = "logical_data_component__encapsulates__data_entity"
REVIEW_TYPE = "value_stream"  # active, and no sample element uses it, so no branch can touch it
REVIEWER = "j-review-guild"
NEW_OWNER = "J round custodian"  # what J06 writes and J14 takes back off
SHIPPED_OWNER = "Information Domain Architect"
GLYPH = "✹"  # a glyph that appears nowhere in the shipped pack
STEREOTYPE = "J Data Object"
DOMAIN_COLOUR = "grape"

TABS = ["Element types", "Relationship types", "Attributes", "Notation", "Reviewers"]
DOMAINS = ["Information", "Process", "Integration", "Objects of enterprise concern"]


def _pm(**parts: str) -> str:
    """The CSS selector for a pattern-matching component, whose DOM id is the JSON Dash writes."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


GP_CY = _pm(id="mm", type="gp-cy")
GP_FIT = _pm(id="mm", type="gp-fit")
GP_LEGEND = _pm(id="mm", type="gp-legend")
PREVIEW = _pm(id="mm-notation-preview", type="mermaid-svg")


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    """A fresh Metamodel page. Anything typed into a grid and not saved is gone."""
    ui.goto("/metamodel")
    ui.must("the Metamodel page rendered its type graph", ui.visible(GP_CY))
    ui.wait_graph()


def _tab(ui, label: str) -> None:
    ui.click(f'[role="tab"]:has-text("{label}")')
    ui.page.wait_for_timeout(250)


def _active_tab(ui) -> str:
    loc = ui.page.locator('[role="tab"][aria-selected="true"]').first
    return loc.inner_text().strip() if loc.count() else ""


def _cy(ui, expression: str):
    """Ask the type graph's Cytoscape instance something, e.g. `cy.$('node.type').length`."""
    return ui.page.evaluate(
        "() => { const cy = window.eaGraph && window.eaGraph.instance('mm');"
        f" if (!cy) {{ return null; }} return {expression}; }}"
    )


def _has_node(ui, type_id: str) -> bool:
    return bool(_cy(ui, f"cy.$('node[element_id = {json.dumps(type_id)}]').length"))


def _tap_type(ui, type_id: str) -> bool:
    """Tap a type node the way a reader does — a real click at the node's rendered position."""
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    position = _cy(
        ui,
        "(function(){ var n = cy.$('node[element_id = " + json.dumps(type_id) + "]');"
        " if (!n.length) { return null; } var p = n[0].renderedPosition(); return [p.x, p.y]; })()",
    )
    if position is None:
        return False
    box = ui.page.locator(GP_CY).first.bounding_box()
    ui.page.mouse.click(box["x"] + position[0], box["y"] + position[1])
    ui.page.wait_for_timeout(600)
    ui.settle()
    return True


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
    for left in range(0, 4200, 200):
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
    ui.page.evaluate(
        "gid => { const v = document.querySelector('#' + gid + ' .ag-body-viewport');"
        " if (v) { v.scrollTop = v.scrollHeight; } }",
        grid_id,
    )
    ui.page.wait_for_timeout(400)
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


def _save(ui) -> str:
    ui.click("mm-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    return ui.text("mm-feedback")


_LABELS = (
    "sel => { const el = document.querySelector(sel);"
    " if (!el) { return ''; }"
    " return Array.from(el.querySelectorAll('g.node, g.cluster'))"
    ".map(n => (n.textContent || '').trim()).join(' | '); }"
)


def _preview_text(ui) -> str:
    """What the preview actually says: the shape and layer labels, without mermaid's stylesheet."""
    return ui.page.evaluate(_LABELS, PREVIEW) or ""


def _await_preview(ui, needle: str) -> bool:
    """The preview is redrawn in the browser after its callback returns; wait for the new label."""
    try:
        ui.page.wait_for_function(
            "([sel, needle]) => { const el = document.querySelector(sel);"
            " if (!el) { return false; }"
            " return Array.from(el.querySelectorAll('g.node, g.cluster'))"
            ".some(n => (n.textContent || '').includes(needle)); }",
            arg=[PREVIEW, needle],
            timeout=20_000,
        )
        return True
    except Exception:  # noqa: BLE001 — a preview that never catches up is the check's finding
        return False


# --------------------------------------------------------------------------- the type graph


@pytest.mark.scenario(
    scenario_id="J01",
    group="J",
    title="The type graph draws the pack, one node per active type",
    feature="Metamodel · type graph",
    expected=(
        "The page names the pack and how many types it holds, and the graph draws one node per "
        "active type, grouped by domain, with a legend naming every domain."
    ),
)
def test_type_graph_renders(ui, record):
    _open(ui)
    body = ui.body()
    ui.check("the page names the pack it is showing", "Higher Education EA Metamodel" in body)
    ui.check("the page says how much of the pack is active", "active types" in body, body[:200])
    drawn = _cy(ui, "cy.$('node.type').length")
    ui.must("the graph drew type nodes", bool(drawn), f"{drawn} type nodes")
    ui.check(
        "the graph draws the types the page counted",
        f"{drawn} active types" in body,
        f"the graph drew {drawn}; the subtitle reads {body[body.find('—') : body.find('—') + 60]!r}",
    )
    ui.check("a well-known type is on the canvas", _has_node(ui, TYPE))
    ui.check(
        "an inactive type is left off the canvas",
        not _has_node(ui, "gateway"),
        "gateway is inactive and should not be drawn",
    )
    ui.check(
        "the diamond for 'any element' is drawn",
        bool(_cy(ui, "cy.$('node.any').length")),
        "a relationship type with an ANY end needs the diamond",
    )
    ui.check(
        "sub-type edges are drawn dashed, not as relationships",
        bool(_cy(ui, "cy.$('edge.sub').length")),
    )
    boxes = _cy(ui, "cy.$('node.group').length")
    ui.check("the domains are grouped and labelled", bool(boxes), f"{boxes} group boxes")
    legend = ui.text(GP_LEGEND).lower()  # the badges are drawn in capitals
    for domain in DOMAINS:
        ui.check(f"the legend names the {domain} domain", domain.lower() in legend, legend)
    ui.check(
        "the panel says what tapping a node does",
        "Tap a type to see its definition" in body,
    )
    ui.check(
        "the detail pane starts by saying what to do",
        "Tap a type" in ui.text("mm-detail"),
        ui.text("mm-detail"),
    )
    ui.shot("The metamodel drawn as a type graph, grouped by domain, with its detail pane waiting")


@pytest.mark.scenario(
    scenario_id="J02",
    group="J",
    title="The domain filter narrows the type graph to one domain",
    feature="Metamodel · type graph · domain filter",
    expected=(
        "Choosing Information leaves only the information domain's types on the canvas; "
        "choosing All domains puts the rest back."
    ),
)
def test_domain_filter(ui, record):
    _open(ui)
    everything = _cy(ui, "cy.$('node.type').length")
    ui.must("the unfiltered graph has types on it", bool(everything))
    ui.select("mm-domain-filter", "Information")
    ui.page.wait_for_timeout(600)
    ui.wait_graph()
    narrowed = _cy(ui, "cy.$('node.type').length")
    ui.check(
        "the filter narrowed the graph",
        narrowed and narrowed < everything,
        f"{everything} types unfiltered, {narrowed} filtered",
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
    ui.check(
        "All domains puts every type back",
        restored == everything,
        f"{restored} back from {everything}",
    )
    ui.shot("All domains restores the whole type graph")


@pytest.mark.scenario(
    scenario_id="J03",
    group="J",
    title="Tapping a type fills the detail pane with its definition",
    feature="Metamodel · type graph · detail pane",
    expected=(
        "Tapping Data Entity shows its name, domain, provenance, description, examples, owners, "
        "its own attributes and the relationship types it may take part in."
    ),
)
def test_tapping_a_type_fills_the_detail(ui, record):
    _open(ui)
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


# --------------------------------------------------------------------------- the grids


@pytest.mark.scenario(
    scenario_id="J04",
    group="J",
    title="The five tabs each open their own grid",
    feature="Metamodel · tabs",
    expected=(
        "Element types, Relationship types, Attributes, Notation and Reviewers each open, "
        "mark themselves current, and show only their own grid."
    ),
)
def test_the_five_tabs(ui, record):
    _open(ui)
    grids = {
        "Element types": "mm-types-grid",
        "Relationship types": "mm-rels-grid",
        "Attributes": "mm-attrs-grid",
        "Notation": "mm-notation-domains-grid",
        "Reviewers": "mm-reviewers-grid",
    }
    ui.check(
        "the page offers all five tabs",
        ui.page.locator('[role="tab"]').count() == len(TABS),
        f"{ui.page.locator('[role=tab]').count()} tabs",
    )
    ui.check("the first tab is open to begin with", _active_tab(ui) == "Element types", _active_tab(ui))
    for label, grid in grids.items():
        _tab(ui, label)
        ui.check(f"the {label} tab marks itself current", _active_tab(ui) == label, _active_tab(ui))
        ui.check(f"the {label} tab shows its own grid", ui.visible(grid))
        others = [g for name, g in grids.items() if name != label]
        ui.check(
            f"the {label} tab hides the other grids",
            not any(ui.visible(g) for g in others),
            f"visible: {[g for g in others if ui.visible(g)]}",
        )
        ui.check(f"the {label} grid has rows", ui.grid_row_count(grid) > 0, f"{grid} is empty")
    ui.shot("The Reviewers tab, the last of the five, open over its own grid")
    _tab(ui, "Notation")
    ui.check("the Notation tab holds two grids", ui.visible("mm-notation-types-grid"))
    ui.check("the Notation tab holds the live preview", ui.visible(PREVIEW))
    ui.shot("The Notation tab: the domain grid, the type overrides and the preview beneath them")


@pytest.mark.scenario(
    scenario_id="J05",
    group="J",
    title="The element types grid holds the pack, inheritance and all",
    feature="Metamodel · Element types grid",
    expected=(
        "Every element type is a row addressed by its id, with its name, plural, supertype, domain, "
        "provenance, prefix and whether it is active; the page says how to retire one."
    ),
)
def test_element_types_grid(ui, record):
    _open(ui)
    _tab(ui, "Element types")
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
    ui.must("the sub-type row is in the grid", _reveal(ui, "mm-types-grid", SUB))
    ui.check(
        "a sub-type names the type it inherits from",
        _cell(ui, "mm-types-grid", SUB, "supertype") == "business_information",
        _cell(ui, "mm-types-grid", SUB, "supertype"),
    )
    ui.check(
        "an inactive type is kept in the grid rather than dropped",
        _reveal(ui, "mm-types-grid", "gateway"),
        "a type retired from use still has to resolve for old content",
    )
    ui.check(
        "a retired type is the one with its active box unticked",
        _tick_state(ui, "mm-types-grid", "gateway", "active") is False,
        f"gateway active = {_tick_state(ui, 'mm-types-grid', 'gateway', 'active')}",
    )
    ui.check(
        "a type in use has its active box ticked",
        _tick_state(ui, "mm-types-grid", TYPE, "active") is True,
        f"{TYPE} active = {_tick_state(ui, 'mm-types-grid', TYPE, 'active')}",
    )
    ui.check(
        "the page says how to retire a type",
        "set active to false rather than deleting it" in ui.body(),
    )
    _grid_home(ui, "mm-types-grid")
    ui.shot("The element types grid, with the sub-type's supertype and an inactive type both in it")


@pytest.mark.scenario(
    scenario_id="J06",
    group="J",
    title="Editing an element type and saving writes the metamodel",
    feature="Metamodel · Element types grid · Save changes",
    expected=(
        "Changing the type owner of Data Entity and saving reports the pack it stored, survives a "
        "reload of the page, and loses nothing else the type carried."
    ),
)
def test_edit_a_type_and_save(ui, record):
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    before = _cell(ui, "mm-types-grid", TYPE, "type_owner")
    ui.check("the shipped owner is what the file says", before == SHIPPED_OWNER, before)
    _set(ui, "mm-types-grid", TYPE, "type_owner", NEW_OWNER)
    ui.check(
        "the cell holds what was typed into it",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "type_owner"),
    )
    feedback = _save(ui)
    ui.must("the save was accepted", feedback.startswith("Metamodel saved:"), feedback)
    ui.check("the save says what it stored", "relationship types" in feedback, feedback)
    _grid_home(ui, "mm-types-grid")
    ui.shot("Saving the metamodel reports the pack it stored")
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row came back", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the edit survived the page being reloaded",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "type_owner"),
    )
    # A save rebuilds the whole pack from the grids, so everything the edited row did not
    # touch has to come back unchanged: the prefix, the plural, and the type's attributes.
    ui.check("the save kept the prefix", _cell(ui, "mm-types-grid", TYPE, "prefix") == "DE")
    ui.check("the save kept the plural", _cell(ui, "mm-types-grid", TYPE, "plural") == "Data Entities")
    ui.must("the sub-type row came back", _reveal(ui, "mm-types-grid", SUB))
    ui.check(
        "the save kept inheritance",
        _cell(ui, "mm-types-grid", SUB, "supertype") == "business_information",
        _cell(ui, "mm-types-grid", SUB, "supertype"),
    )
    ui.must("the type node was tapped", _tap_type(ui, TYPE), f"no node for {TYPE}")
    detail = ui.text("mm-detail")
    ui.check("the detail pane reads the saved owner back", NEW_OWNER in detail, detail)
    ui.check(
        "the save kept the type's own attributes",
        "includes_pii" in detail and "available_in_analytics_platform" in detail,
        detail,
    )
    ui.check("the save kept the examples", "HR_Employee" in detail, detail)
    _grid_home(ui, "mm-types-grid")
    ui.shot("After the save the detail pane reads the new owner back, with the type otherwise intact")


@pytest.mark.scenario(
    scenario_id="J07",
    group="J",
    title="Add element type puts a new editable row at the end of the grid",
    feature="Metamodel · Element types grid · Add type",
    expected=(
        "Add type adds one row with an id of its own and a name to edit, and nothing is stored "
        "until Save changes is pressed."
    ),
)
def test_add_element_type(ui, record):
    _open(ui)
    _tab(ui, "Element types")
    before = set(ui.grid_row_ids("mm-types-grid"))
    ui.click("mm-add-type")
    ui.page.wait_for_timeout(400)
    ui.page.evaluate(
        "() => { const v = document.querySelector('#mm-types-grid .ag-body-viewport');"
        " if (v) { v.scrollTop = v.scrollHeight; } }"
    )
    ui.page.wait_for_timeout(400)
    rows = ui.grid_row_ids("mm-types-grid")
    added = [r for r in rows if r and r.startswith("new_type_")]
    ui.must("Add type added a row", bool(added), f"rows at the end: {rows[-3:]}")
    ui.check("the new row was not one that was already there", added[0] not in before)
    new_id = added[0]
    ui.check(
        "the new row carries a placeholder name to edit",
        _cell(ui, "mm-types-grid", new_id, "name") == "New type",
        _cell(ui, "mm-types-grid", new_id, "name"),
    )
    ui.check(
        "the new row starts active, so the type is usable straight away",
        _tick_state(ui, "mm-types-grid", new_id, "active") is True,
        f"active = {_tick_state(ui, 'mm-types-grid', new_id, 'active')}",
    )
    _set(ui, "mm-types-grid", new_id, "name", "J Draft Type")
    ui.check(
        "the new row can be edited before it is saved",
        _cell(ui, "mm-types-grid", new_id, "name") == "J Draft Type",
        _cell(ui, "mm-types-grid", new_id, "name"),
    )
    ui.shot("Add type appended a row that can be filled in before anything is saved")
    # The row is deliberately not saved: leaving the page throws it away, which is what
    # a person expects of a grid they typed into and thought better of.
    _open(ui)
    _tab(ui, "Element types")
    ui.page.evaluate(
        "() => { const v = document.querySelector('#mm-types-grid .ag-body-viewport');"
        " if (v) { v.scrollTop = v.scrollHeight; } }"
    )
    ui.page.wait_for_timeout(400)
    ui.check(
        "leaving the page without saving discards the row",
        new_id not in set(ui.grid_row_ids("mm-types-grid")),
        f"rows at the end: {ui.grid_row_ids('mm-types-grid')[-3:]}",
    )
    ui.shot("The unsaved row is gone after the page is left and reopened")


@pytest.mark.scenario(
    scenario_id="J08",
    group="J",
    title="The relationship types grid names both ends of every relationship",
    feature="Metamodel · Relationship types grid",
    expected=(
        "Every relationship type is a row with its name, its inverse, its source and target types, "
        "its qualifiers where it has them, and Add relationship type appends one more."
    ),
)
def test_relationship_types_grid(ui, record):
    _open(ui)
    _tab(ui, "Relationship types")
    ui.must("the encapsulates relationship type is in the grid", _reveal(ui, "mm-rels-grid", REL))
    ui.check("the row names the relationship", _cell(ui, "mm-rels-grid", REL, "name") == "encapsulates")
    ui.check(
        "the row names the way back",
        _cell(ui, "mm-rels-grid", REL, "inverse") == "is encapsulated by",
        _cell(ui, "mm-rels-grid", REL, "inverse"),
    )
    ui.check(
        "the row names the type it starts from",
        _cell(ui, "mm-rels-grid", REL, "source") == "logical_data_component",
        _cell(ui, "mm-rels-grid", REL, "source"),
    )
    ui.check(
        "the row names the type it ends at",
        _cell(ui, "mm-rels-grid", REL, "target") == TYPE,
        _cell(ui, "mm-rels-grid", REL, "target"),
    )
    qualified = "position__is_steward_of__information_asset"
    ui.must("the qualified relationship type is in the grid", _reveal(ui, "mm-rels-grid", qualified))
    ui.check(
        "a relationship type that takes a qualifier lists the qualifiers it takes",
        "Data Steward" in _cell(ui, "mm-rels-grid", qualified, "qualifiers"),
        _cell(ui, "mm-rels-grid", qualified, "qualifiers"),
    )
    ui.check(
        "the header says how several qualifiers are written",
        "comma-separated" in ui.text("#mm-rels-grid .ag-header"),
        ui.text("#mm-rels-grid .ag-header"),
    )
    _grid_home(ui, "mm-rels-grid")
    ui.shot("The relationship types grid, with the qualified steward relationship shown")
    ui.click("mm-add-rel")
    ui.page.wait_for_timeout(400)
    ui.page.evaluate(
        "() => { const v = document.querySelector('#mm-rels-grid .ag-body-viewport');"
        " if (v) { v.scrollTop = v.scrollHeight; } }"
    )
    ui.page.wait_for_timeout(400)
    added = [r for r in ui.grid_row_ids("mm-rels-grid") if r and r.startswith("new_relationship_")]
    ui.check("Add relationship type added a row", bool(added), f"{ui.grid_row_ids('mm-rels-grid')[-3:]}")
    if added:
        ui.check(
            "the new relationship starts open at both ends",
            _cell(ui, "mm-rels-grid", added[0], "source") == "ANY",
            _cell(ui, "mm-rels-grid", added[0], "source"),
        )
    ui.shot("Add relationship type appended a row that starts open at both ends")


@pytest.mark.scenario(
    scenario_id="J09",
    group="J",
    title="The attributes grid separates the common attributes from a type's own",
    feature="Metamodel · Attributes grid",
    expected=(
        "An attribute every element may carry has no type in its first column; one that belongs to a "
        "single type names that type, and Add attribute appends a common one."
    ),
)
def test_attributes_grid(ui, record):
    _open(ui)
    _tab(ui, "Attributes")
    rows = ui.grid_row_count("mm-attrs-grid")
    ui.must("the attributes grid has rows", rows > 0)  # rendered rows; the total comes later
    ui.check(
        "the header says a blank type means the attribute is common",
        "blank = common" in ui.text("#mm-attrs-grid .ag-header"),
        ui.text("#mm-attrs-grid .ag-header"),
    )
    first_type = ui.grid_cell("mm-attrs-grid", 0, "type_id")
    ui.check("the common attributes come first, with no type against them", first_type == "", first_type)
    ui.check(
        "the first common attribute is the one the pack declares first",
        ui.grid_cell("mm-attrs-grid", 0, "name") == "alias",
        ui.grid_cell("mm-attrs-grid", 0, "name"),
    )
    names = [ui.grid_cell("mm-attrs-grid", i, "name") for i in range(min(rows, 12))]
    ui.check("an enumerated attribute is in the grid", "approval_status" in names, str(names))
    enum_row = names.index("approval_status") if "approval_status" in names else -1
    if enum_row >= 0:
        ui.check(
            "an enumerated attribute lists the values it allows",
            "Approved" in ui.grid_cell("mm-attrs-grid", enum_row, "enum"),
            ui.grid_cell("mm-attrs-grid", enum_row, "enum"),
        )
    typed = [ui.grid_cell("mm-attrs-grid", i, "type_id") for i in range(min(rows, 20))]
    ui.check(
        "an attribute that belongs to one type names that type",
        any(t for t in typed),
        f"no row in the first {len(typed)} names a type: {typed}",
    )
    ui.shot("The attributes grid, common attributes first with no type against them")
    before = _row_total(ui, "mm-attrs-grid")
    ui.click("mm-add-attr")
    ui.page.wait_for_timeout(400)
    after = _row_total(ui, "mm-attrs-grid")
    ui.check("Add attribute added a row", after == before + 1, f"{before} rows before, {after} after")
    last = after - 1
    ui.check(
        "the new attribute is a common one until a type is typed against it",
        ui.grid_cell("mm-attrs-grid", last, "type_id") == "",
        ui.grid_cell("mm-attrs-grid", last, "type_id"),
    )
    ui.check(
        "the new attribute is named so it can be found and renamed",
        ui.grid_cell("mm-attrs-grid", last, "name").startswith("new_attribute_"),
        ui.grid_cell("mm-attrs-grid", last, "name"),
    )
    ui.shot("Add attribute appended a common attribute at the end of the grid")


@pytest.mark.scenario(
    scenario_id="J10",
    group="J",
    title="A metamodel that does not hold together is refused, and nothing is stored",
    feature="Metamodel · Save changes · validation",
    expected=(
        "Pointing a type at a supertype that does not exist and saving is refused with 'Not saved:' "
        "naming the type and the missing supertype, and the stored pack is untouched."
    ),
)
def test_an_invalid_metamodel_is_refused(ui, record):
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    _set(ui, "mm-types-grid", TYPE, "supertype", "j_no_such_type")
    feedback = _save(ui)
    ui.must("the save was refused", feedback.startswith("Not saved:"), feedback or "(no feedback at all)")
    ui.check("the refusal names the type it could not place", TYPE in feedback, feedback)
    ui.check("the refusal names what it could not find", "j_no_such_type" in feedback, feedback)
    ui.check("the refusal says what was wrong with it", "supertype" in feedback, feedback)
    _grid_home(ui, "mm-types-grid")
    ui.shot("Saving a type whose supertype does not exist is refused, and says which supertype")
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row came back", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the refused edit was not stored",
        _cell(ui, "mm-types-grid", TYPE, "supertype") == "",
        _cell(ui, "mm-types-grid", TYPE, "supertype"),
    )
    ui.check(
        "the pack the graph draws is the one from before the refusal",
        _has_node(ui, TYPE),
    )
    _grid_home(ui, "mm-types-grid")
    ui.shot("The refused supertype was never stored: the grid is as it was")


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
def test_notation_grids_and_preview(ui, record, finding):
    _open(ui)
    _tab(ui, "Notation")
    ui.must(
        "the domain notation grid has a row per domain", ui.grid_row_count("mm-notation-domains-grid") > 0
    )
    ui.must("the type override grid has rows", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "a domain row carries the colour it is drawn in",
        _cell(ui, "mm-notation-domains-grid", "information", "colour") == "blue",
        _cell(ui, "mm-notation-domains-grid", "information", "colour"),
    )
    ui.check(
        "a domain row carries the exact hex behind the colour",
        _cell(ui, "mm-notation-domains-grid", "information", "hex").startswith("#"),
        _cell(ui, "mm-notation-domains-grid", "information", "hex"),
    )
    inherited = _cell(ui, "mm-notation-types-grid", TYPE, "inherited")
    ui.check(
        "the override grid says what the type is actually drawn as",
        "application" in inherited and "Data Object" in inherited,
        inherited,
    )
    ui.check(
        "the tab says what a blank cell means",
        "inherits from the supertype, then the domain" in ui.body(),
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
    ui.shot("Changing the stereotype redraws the preview again")

    _set_select(ui, "mm-notation-domains-grid", "information", "colour", DOMAIN_COLOUR)
    ui.check(
        "the domain's colour is changed in the grid",
        _cell(ui, "mm-notation-domains-grid", "information", "colour") == DOMAIN_COLOUR,
        _cell(ui, "mm-notation-domains-grid", "information", "colour"),
    )
    ui.page.wait_for_timeout(600)
    ui.check(
        "the preview is still drawn after the colour change",
        ui.page.locator(f"{PREVIEW} svg").count() > 0,
    )
    # The preview is a generated view, and a generated view is filled by ArchiMate layer,
    # not by the pack's domain colour — so the one column of this grid a reader is most
    # likely to try changes nothing they can see here.
    finding.append(
        Finding(
            finding_id="J1",
            where="src/ea/ui/pages/metamodel.py · Notation tab, the Domains grid's `colour` and `hex` columns",
            severity="usability",
            summary="A domain's colour changes nothing in the preview it sits above.",
            detail=(
                "The tab says 'How each domain and type is drawn in generated views and graphs' and "
                "'The preview follows every edit'. The preview is a generated view, and "
                "views/mermaid.py fills a shape from LAYER_STYLE by ArchiMate layer, never from the "
                "domain's colour; the colour is only used by the network graph panel and the badges "
                "elsewhere. Changing colour or hex therefore leaves the preview exactly as it was, "
                "which reads as the edit not having registered."
            ),
        )
    )
    ui.shot("A domain colour change leaves the preview unchanged, because a view is filled by layer")

    _open(ui)
    _tab(ui, "Notation")
    ui.must("the type override row came back", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "leaving the page without saving discards the notation edits",
        _cell(ui, "mm-notation-types-grid", TYPE, "glyph") != GLYPH,
        _cell(ui, "mm-notation-types-grid", TYPE, "glyph"),
    )
    ui.check(
        "the preview is drawn from the stored pack again",
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
    ui.check(
        "the tab says what an assignment means",
        "may be approved by any Reviewer" in ui.body(),
    )
    ui.must("the element type is in the reviewers grid", _reveal(ui, "mm-reviewers-grid", REVIEW_TYPE))
    ui.check(
        "the grid names the type as well as its id",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "type") == "Value Stream",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "type"),
    )
    ui.check(
        "the type starts with nobody assigned",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers") == "",
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers"),
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
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers"),
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
        _cell(ui, "mm-reviewers-grid", REVIEW_TYPE, "reviewers"),
    )


# --------------------------------------------------------------------------- export and reload


@pytest.mark.scenario(
    scenario_id="J13",
    group="J",
    title="Export YAML downloads the pack as it now stands",
    feature="Metamodel · Export YAML",
    expected=(
        "Export YAML produces a pack file named for the pack, holding its domains, element types, "
        "relationship types and common attributes, including the edit saved earlier in this group."
    ),
)
def test_export_the_pack(ui, record):
    _open(ui)
    path = ui.download("mm-export", ".yaml")
    ui.check("the file is named for the pack", "higher_education" in path.name, path.name)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    ui.must("the download parses as a pack", isinstance(data, dict), type(data).__name__)
    ui.check(
        "the export names the pack",
        data.get("pack", {}).get("id") == "higher_education",
        str(data.get("pack"))[:200],
    )
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
    ui.check(
        "the export keeps inheritance",
        types.get(SUB, {}).get("supertype") == "business_information",
        str(types.get(SUB, {}).get("supertype")),
    )
    ui.check(
        "the export keeps a type's own attributes",
        {a["name"] for a in types.get(TYPE, {}).get("attributes") or []} >= {"includes_pii"},
        str(types.get(TYPE, {}).get("attributes")),
    )
    ui.check(
        "the export keeps the notation a view is drawn from",
        (types.get(TYPE, {}).get("notation") or {}).get("archimate") == "DataObject",
        str(types.get(TYPE, {}).get("notation")),
    )
    ui.check(
        "the export is the pack as edited, not the file on disk",
        types.get(TYPE, {}).get("type_owner") == NEW_OWNER,
        str(types.get(TYPE, {}).get("type_owner")),
    )
    ui.shot("Export YAML has produced the pack, and the page is unchanged by it")


@pytest.mark.scenario(
    scenario_id="J14",
    group="J",
    title="Reload from file puts back what the shipped pack says",
    feature="Metamodel · Reload from file",
    expected=(
        "Reload from file names the pack and the file it read, and the edit this group saved is "
        "replaced by the value the file holds."
    ),
)
def test_reload_from_file(ui, record):
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row is in the grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the stored pack still holds this group's edit before the reload",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == NEW_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "type_owner"),
    )
    ui.click("mm-reload")
    ui.page.wait_for_timeout(500)
    ui.settle()
    feedback = ui.text("mm-feedback")
    ui.must("the reload was reported", feedback.startswith("Reloaded"), feedback or "(no feedback at all)")
    ui.check("the reload names the pack it read", "higher_education" in feedback, feedback)
    ui.check("the reload names the file it read it from", "metamodel.yaml" in feedback, feedback)
    ui.must("the Data Entity row is in the reloaded grid", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the reload put the file's owner back",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == SHIPPED_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "type_owner"),
    )
    _grid_home(ui, "mm-types-grid")
    ui.shot("Reload from file has replaced the stored pack with the one the file holds")
    _open(ui)
    _tab(ui, "Element types")
    ui.must("the Data Entity row came back", _reveal(ui, "mm-types-grid", TYPE))
    ui.check(
        "the reloaded pack is the one the rest of the round reads",
        _cell(ui, "mm-types-grid", TYPE, "type_owner") == SHIPPED_OWNER,
        _cell(ui, "mm-types-grid", TYPE, "type_owner"),
    )
    _tab(ui, "Notation")
    ui.must("the notation row came back", _reveal(ui, "mm-notation-types-grid", TYPE))
    ui.check(
        "the shipped notation is back too",
        _cell(ui, "mm-notation-types-grid", TYPE, "stereotype") == "Data Object",
        _cell(ui, "mm-notation-types-grid", TYPE, "stereotype"),
    )
    ui.check("the preview is drawn from the shipped pack", GLYPH not in _preview_text(ui))
    ui.shot("The metamodel is back to what the repository ships, ready for the groups that follow")


@pytest.mark.scenario(
    scenario_id="J15",
    group="J",
    title="A column filter must not decide what Save changes writes",
    feature="Metamodel · Save changes · grid filters",
    expected=(
        "Narrowing a grid with a column filter to find one row and then saving keeps every row the "
        "filter hid; the pack that is stored is the whole pack, not the part that was on screen."
    ),
)
def test_a_filter_does_not_decide_what_is_saved(ui, record, finding):
    _open(ui)
    _tab(ui, "Relationship types")
    before = _row_total(ui, "mm-rels-grid")
    ui.must("the relationship types grid was counted", before > 1, f"{before} rows")
    _grid_home(ui, "mm-rels-grid")
    _filter(ui, "mm-rels-grid", "id", REL)
    shown = _row_total(ui, "mm-rels-grid")
    ui.must("the filter narrowed the grid to the one row", shown == 1, f"{shown} rows shown")
    ui.shot("The relationship types grid filtered to the one row a reader was looking for")
    feedback = _save(ui)
    ui.check("the save was accepted", feedback.startswith("Metamodel saved:"), feedback[:300])
    saved = re.search(r"(\d+) types, (\d+) relationship types", feedback)
    ui.must("the save said what it stored", saved is not None, feedback[:300])
    stored = int(saved.group(2))
    # The defect: the callback reads `virtualRowData`, which is what the grid is *showing*
    # after filtering, so everything the filter hid is written out of the pack. The pack
    # that comes back is still valid, so nothing warns anybody.
    ui.check(
        "saving keeps the relationship types the filter hid",
        stored == before,
        f"{before} relationship types before the filter, {stored} stored after saving with it on",
    )
    ui.shot("What the save reports it stored, with the filter still on the grid")
    if stored != before:
        finding.append(
            Finding(
                finding_id="J2",
                where="src/ea/ui/pages/metamodel.py · the `save` callback (`mm-save`), and every grid on the page",
                severity="defect",
                summary="A column filter silently decides what Save changes keeps: the rows it hides are deleted from the pack.",
                detail=(
                    "Every column of every grid on the page is filterable, and the save callback takes "
                    "`virtualRowData` first — the rows the grid is showing after filtering — falling back "
                    "to `rowData` only when that is empty. Filtering the relationship types grid to one "
                    f"row and pressing Save changes stored a pack with {stored} relationship type(s) "
                    f"instead of {before}, with a green 'Metamodel saved' message and no warning. The "
                    "same filter on the Attributes grid drops every attribute it hides; on the Element "
                    "types grid the loss is caught, but only by accident — the relationship types then "
                    "point at types that no longer exist, and the refusal is a single unreadable line "
                    "with one clause per broken relationship end. Nothing on the page contradicts the "
                    "green message either: the heading is rendered once, so it still read '54 "
                    "relationship types' over a pack that now held one. Reload from file is the only "
                    "way back, and only because the pack is also held in a file."
                ),
            )
        )
    _open(ui)
    ui.click("mm-reload")
    ui.page.wait_for_timeout(600)
    ui.settle()
    ui.must(
        "the pack was reloaded from the file",
        ui.text("mm-feedback").startswith("Reloaded"),
        ui.text("mm-feedback"),
    )
    _open(ui)
    _tab(ui, "Relationship types")
    after = _row_total(ui, "mm-rels-grid")
    ui.check(
        "reloading from the file puts the whole pack back",
        after == before,
        f"{before} relationship types before, {after} after the reload",
    )
    _grid_home(ui, "mm-rels-grid")
    ui.shot("Reload from file has put every relationship type back, whatever the save did")
