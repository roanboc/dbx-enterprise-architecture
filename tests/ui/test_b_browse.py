"""Group B — Browse: the grid, the three filters, ranked search, the New element modal and bulk edit.

Every scenario here is written against the sample model but asserts relative facts only
(a row exists, a count narrowed, a message appeared), because the whole round shares one
database and an earlier group may have added to it. Anything this group creates is named
with a `B-` prefix so it cannot collide with another group's data.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.gui

GRID = "browse-grid"
# The Markdown editor inside the New element modal is a pattern-matching component, so its
# DOM id is the JSON Dash writes for it.
MD_TEXT = '[id=\'{"id":"new-desc","type":"md-text"}\']'
MD_MODE = '[id=\'{"id":"new-desc","type":"md-mode"}\']'
MD_WRAP = '[id=\'{"id":"new-desc","type":"md-wrap"}\']'
MD_PREVIEW = '[id=\'{"id":"new-desc","type":"md-preview"}\']'


def _md_insert(kind: str) -> str:
    return '[id=\'{"id":"new-desc","kind":"' + kind + '","type":"md-insert"}\']'


def _counts(ui) -> tuple[int, int]:
    """The `N of M` the page shows under the filters, as numbers."""
    match = re.fullmatch(r"(\d+) of (\d+)", ui.text("browse-count"))
    return (int(match.group(1)), int(match.group(2))) if match else (-1, -1)


def _search(ui, text: str) -> None:
    """Type into the search box and wait out its 400 ms debounce before the grid reloads."""
    ui.fill("browse-text", text)
    ui.page.wait_for_timeout(700)
    ui.settle()


def _column(ui, col: str, limit: int = 12) -> list[str]:
    """What one column reads down the rendered rows (the grid virtualises, so this is a sample)."""
    rows = min(ui.grid_row_count(GRID), limit)
    return [ui.grid_cell(GRID, i, col) for i in range(rows)]


def _md_value(ui) -> str:
    return ui.page.locator(MD_TEXT).first.input_value()


def _close_modal(ui, body_id: str) -> None:
    """Never leave a scenario mid-modal: Escape, and confirm it went."""
    if ui.page.locator(f"#{body_id}").count():
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_timeout(400)
        ui.settle()


# --------------------------------------------------------------------------- the grid


@pytest.mark.scenario(
    scenario_id="B01",
    group="B",
    title="Browse opens with the whole model in the grid",
    feature="Browse · the grid",
    expected="The grid fills with rows, the count reads 'N of M', and every declared column has a header.",
)
def test_grid_loads(ui, record):
    ui.goto("/browse")
    ui.must("the grid is on the page", ui.visible(GRID))
    shown, total = _counts(ui)
    ui.check("the count reads 'N of M'", shown >= 0, ui.text("browse-count"))
    ui.check("the model has rows to show", total > 0, f"{total} elements")
    ui.check("rows are rendered", ui.grid_row_count(GRID) > 0, f"{ui.grid_row_count(GRID)} rendered")
    headers = [h for h in ui.page.locator(f"#{GRID} .ag-header-cell-text").all_inner_texts()]
    for wanted in ("id", "Name", "Type", "Status", "current", "target", "source", "matched in"):
        ui.check(f"the grid has a '{wanted}' column", wanted in headers, str(headers))
    ui.check(
        "the first row carries an identifier",
        bool(ui.grid_cell(GRID, 0, "element_id")),
        ui.grid_cell(GRID, 0, "element_id"),
    )
    ui.shot("Browse opens with the whole model listed and the count under the filters")


@pytest.mark.scenario(
    scenario_id="B02",
    group="B",
    title="The type filter narrows the grid to one element type",
    feature="Browse · type filter",
    expected="Choosing Logical Data Component leaves fewer rows, and every row is of that type.",
)
def test_type_filter(ui, record):
    ui.goto("/browse")
    _, before = _counts(ui)
    ui.select("browse-type", "Logical Data Component")
    _, after = _counts(ui)
    ui.check("the filter narrowed the model", 0 < after < before, f"{after} of {before}")
    types = _column(ui, "type")
    ui.check(
        "every row shown is a Logical Data Component",
        bool(types) and all(t == "Logical Data Component" for t in types),
        str(types),
    )
    ui.shot("The type filter leaves only Logical Data Components")
    ui.select("browse-type", "All types")
    _, restored = _counts(ui)
    ui.check("clearing the filter restores the whole model", restored == before, f"{restored} of {before}")


@pytest.mark.scenario(
    scenario_id="B03",
    group="B",
    title="Text search ranks the hits and says where each one matched",
    feature="Browse · ranked search",
    expected="Searching 'curriculum' puts a name that starts with the word first and fills the 'matched in' column for rows matched elsewhere.",
)
def test_search_ranks_and_snippets(ui, record):
    ui.goto("/browse")
    _, before = _counts(ui)
    _search(ui, "curriculum")
    _, after = _counts(ui)
    ui.check("the search narrowed the model", 0 < after < before, f"{after} of {before}")
    first = ui.grid_cell(GRID, 0, "name")
    ui.check(
        "the best hit is a name that starts with the word",
        first.lower().startswith("curriculum"),
        f"first row is {first!r}",
    )
    ui.check("a row matched in its name shows no snippet", ui.grid_cell(GRID, 0, "snippet") == "")
    snippets = [s for s in _column(ui, "snippet") if s.strip()]
    ui.check("rows matched elsewhere show what they matched in", bool(snippets), str(snippets[:2]))
    ui.check(
        "a snippet holds the word that was searched for",
        any("curriculum" in s.lower() for s in snippets),
        str(snippets[:2]),
    )
    ui.shot("Searching 'curriculum' ranks names first and fills the 'matched in' column")


@pytest.mark.scenario(
    scenario_id="B04",
    group="B",
    title="Every word has to match, and a word that matches nothing empties the grid",
    feature="Browse · ranked search",
    expected="Adding a second word narrows the hits further, and a nonsense word leaves '0 of 0' and no rows.",
)
def test_search_every_word_matches(ui, record):
    ui.goto("/browse")
    _search(ui, "unit")
    _, one_word = _counts(ui)
    _search(ui, "unit outline")
    _, two_words = _counts(ui)
    ui.check("one word finds something", one_word > 0, f"{one_word} for 'unit'")
    ui.check(
        "a second word narrows the hits further",
        0 < two_words < one_word,
        f"{two_words} for 'unit outline' against {one_word} for 'unit'",
    )
    _search(ui, "zzqxnothinghere")
    shown, total = _counts(ui)
    ui.check("a word that matches nothing finds nothing", (shown, total) == (0, 0), ui.text("browse-count"))
    ui.check("and the grid is empty", ui.grid_row_count(GRID) == 0)
    ui.shot("A search word that matches nothing leaves the grid empty and the count at zero")


@pytest.mark.scenario(
    scenario_id="B05",
    group="B",
    title="The status filter shows only elements in that status",
    feature="Browse · status filter",
    expected="Choosing 'approved' narrows the grid and every row reads approved; 'Any status' restores it.",
)
def test_status_filter(ui, record):
    ui.goto("/browse")
    _, before = _counts(ui)
    ui.select("browse-status", "approved")
    _, approved = _counts(ui)
    ui.check("the status filter narrowed the model", 0 < approved <= before, f"{approved} of {before}")
    statuses = _column(ui, "status")
    ui.check(
        "every row shown is approved",
        bool(statuses) and all(s == "approved" for s in statuses),
        str(statuses),
    )
    ui.shot("The status filter leaves only approved elements")
    ui.select("browse-status", "Any status")
    _, restored = _counts(ui)
    ui.check("'Any status' restores the whole model", restored == before, f"{restored} of {before}")


@pytest.mark.scenario(
    scenario_id="B06",
    group="B",
    title="A click on a row opens the element, a click on the tick column does not",
    feature="Browse · opening an element",
    expected="Clicking the tick column leaves the reader on Browse; clicking the name opens that element's page.",
)
def test_row_click_opens_element(ui, record):
    ui.goto("/browse")
    _search(ui, "curriculum")
    element_id = ui.grid_cell(GRID, 0, "element_id")
    ui.must("there is a row to click", bool(element_id))
    ui.grid_click_cell(GRID, 0, "sel")
    ui.check(
        "clicking the tick column does not navigate away",
        ui.page.url.rstrip("/").endswith("/browse"),
        ui.page.url,
    )
    ui.shot("Ticking a row keeps the reader on Browse")
    ui.grid_click_cell(GRID, 0, "name")
    ui.check(
        "clicking the name opens that element",
        ui.page.url.endswith(f"/element/{element_id}"),
        f"{ui.page.url} for {element_id}",
    )
    ui.check("the element page names it", element_id in ui.body(), element_id)
    ui.shot("Clicking the name opens that element's page")


# ------------------------------------------------------------------- the New element modal


@pytest.mark.scenario(
    scenario_id="B07",
    group="B",
    title="The New element modal refuses a missing type or a missing name",
    feature="Browse · New element",
    expected="Saving with nothing, with a name only, or with a type only all say 'Type and name are required.'",
)
def test_new_element_validation(ui, record):
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element modal opened", ui.visible("new-modal-body"))
    ui.check("it asks for a type", "Type" in ui.text("new-modal-body"))
    ui.check("it asks for a name", "Name" in ui.text("new-modal-body"))
    ui.click("new-save")
    ui.check(
        "saving with nothing filled in is refused",
        "Type and name are required." in ui.text("new-feedback"),
        ui.text("new-feedback"),
    )
    ui.shot("The New element modal refuses a save with neither a type nor a name")
    ui.fill("new-name", "B-nameless-trial")
    ui.click("new-save")
    ui.check(
        "a name with no type is refused too",
        "Type and name are required." in ui.text("new-feedback"),
        ui.text("new-feedback"),
    )
    ui.select("new-type", "Capability", exact=True)
    ui.fill("new-name", "")
    ui.click("new-save")
    ui.check(
        "a type with no name is refused too",
        "Type and name are required." in ui.text("new-feedback"),
        ui.text("new-feedback"),
    )
    ui.shot("A type with the name cleared is refused with the same message")
    _close_modal(ui, "new-modal-body")
    ui.check("the modal closes on Escape", not ui.page.locator("#new-modal-body").count())


@pytest.mark.scenario(
    scenario_id="B08",
    group="B",
    title="The Markdown editor inserts its four snippets and switches between its three modes",
    feature="Browse · Markdown editor",
    expected="Heading, Bold, Table and Mermaid each append their snippet, and Edit, Split and Preview each change the editor.",
)
def test_markdown_editor(ui, record):
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element modal opened", ui.visible("new-modal-body"))
    ui.check("the editor starts empty", _md_value(ui) == "", _md_value(ui))
    for kind, expected in (
        ("heading", "## Heading"),
        ("bold", "**bold text**"),
        ("table", "| Column | Value |"),
        ("mermaid", "```mermaid"),
    ):
        ui.click(_md_insert(kind))
        ui.check(f"the {kind} button inserts its snippet", expected in _md_value(ui), _md_value(ui)[-60:])
    ui.check(
        "each insert is appended, not overwritten",
        _md_value(ui).count("\n") > 3 and "## Heading" in _md_value(ui),
        _md_value(ui)[:80],
    )
    ui.shot("The four insert buttons have appended their snippets to the description")
    for mode in ("split", "preview", "edit"):
        ui.segmented(MD_MODE, mode.capitalize())
        klass = ui.page.locator(MD_WRAP).first.get_attribute("class") or ""
        ui.check(f"{mode.capitalize()} mode is applied to the editor", f"mode-{mode}" in klass, klass)
    ui.segmented(MD_MODE, "Preview")
    preview = ui.page.locator(MD_PREVIEW).first.inner_text()
    ui.check("the preview renders the heading it was given", "Heading" in preview, preview[:80])
    ui.check("the preview renders the table it was given", "Example" in preview, preview[:120])
    ui.shot("Preview mode renders the Markdown the editor holds")
    _close_modal(ui, "new-modal-body")


@pytest.mark.scenario(
    scenario_id="B09",
    group="B",
    title="Creating an element opens the element it created",
    feature="Browse · New element",
    expected="A type, a name and a description create the element and navigate straight to its page.",
)
def test_create_element(ui, record):
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element modal opened", ui.visible("new-modal-body"))
    ui.select("new-type", "Capability", exact=True)
    ui.fill("new-name", "B-alpha-capability")
    ui.page.locator(MD_TEXT).first.fill("Created by the Browse round to prove the New element modal.")
    ui.settle()
    ui.click("new-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.must(
        "creating the element navigated to it",
        "/element/" in ui.page.url,
        f"{ui.page.url}; feedback: {ui.text('new-feedback')}",
    )
    ui.check(
        "the element it opened is a Capability, minted with the pack's prefix",
        "/element/CAP-" in ui.page.url,
        ui.page.url,
    )
    body = ui.body()
    ui.check("the element page shows the name that was typed", "B-alpha-capability" in body)
    ui.check("the description that was typed is on the page", "Browse round" in body)
    ui.shot("The element the New element modal created, opened on its own page")


@pytest.mark.scenario(
    scenario_id="B10",
    group="B",
    title="The element just created is findable in Browse",
    feature="Browse · ranked search",
    expected="Searching for its name finds exactly it, as a draft with an undecided target state.",
)
def test_created_element_is_findable(ui, record):
    ui.goto("/browse")
    _search(ui, "B-alpha-capability")
    shown, _ = _counts(ui)
    ui.must("the element created earlier is found", shown >= 1, ui.text("browse-count"))
    ui.check("it is the row that came back", ui.grid_cell(GRID, 0, "name") == "B-alpha-capability")
    ui.check("a new element starts as a draft", ui.grid_cell(GRID, 0, "status") == "draft")
    ui.check(
        "and with no target state decided",
        ui.grid_cell(GRID, 0, "target_state") == "undecided",
        ui.grid_cell(GRID, 0, "target_state"),
    )
    ui.shot("The newly created element found by name in Browse")


# ------------------------------------------------------------------------------ bulk edit


@pytest.mark.scenario(
    scenario_id="B11",
    group="B",
    title="Bulk edit with nothing ticked says so and says what to tick",
    feature="Browse · bulk edit",
    expected="Pressing Bulk edit before any row is ticked is answered in words — nothing is ticked, "
    "and here is how to tick — rather than by a button that appears to do nothing.",
)
def test_bulk_needs_a_tick(ui, record):
    # This scenario used to require the opposite (the modal stayed shut and nothing was said),
    # which is what the round found wrong: `open_bulk` now opens it and answers in the feedback.
    ui.goto("/browse")
    ui.check("Bulk edit is offered to an Admin on main", not ui.disabled("bulk-open"))
    ui.click("bulk-open")
    ui.must(
        "pressing it with nothing ticked is answered rather than ignored",
        ui.visible("bulk-modal-body"),
        f"{ui.page.locator('#bulk-modal-body').count()} modal bodies in the page",
    )
    feedback = ui.text("bulk-feedback")
    ui.check("it says nothing is ticked", "Nothing is ticked." in feedback, feedback or "(nothing said)")
    ui.check("and says what to tick instead", "tick the rows" in feedback, feedback or "(nothing said)")
    ui.check("and nothing is reported as changed", "Updated" not in feedback, feedback)
    ui.shot("Bulk edit with nothing ticked says so, and says what to tick")
    _close_modal(ui, "bulk-modal-body")


@pytest.mark.scenario(
    scenario_id="B12",
    group="B",
    title="Bulk edit opens with rows ticked and says how many it holds",
    feature="Browse · bulk edit",
    expected="Ticking two rows and pressing Bulk edit opens the modal, which reports two elements ticked.",
)
def test_bulk_opens_with_ticks(ui, record):
    ui.goto("/browse")
    ui.must("there are at least two rows to tick", ui.grid_row_count(GRID) >= 2)
    ui.grid_tick(GRID, [0, 1])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    ui.check(
        "it says how many rows it will change",
        "2 element(s) ticked." in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )
    body = ui.text("bulk-modal-body")
    for field in ("Status", "Current state", "Target state", "Work package", "Target note", "Attribute"):
        ui.check(f"the modal offers '{field}'", field in body)
    ui.check(
        "it explains that an empty field is not touched",
        "not touched" in body,
        body[:120].replace("\n", " · "),
    )
    ui.shot("Bulk edit opened on two ticked rows and says how many it holds")
    _close_modal(ui, "bulk-modal-body")


@pytest.mark.scenario(
    scenario_id="B13",
    group="B",
    title="Bulk edit refuses a save with no field filled in",
    feature="Browse · bulk edit",
    expected="Applying with every field empty changes nothing and says to fill one in.",
)
def test_bulk_refuses_empty_save(ui, record):
    ui.goto("/browse")
    ui.must("there are rows to tick", ui.grid_row_count(GRID) >= 2)
    ui.grid_tick(GRID, [0, 1])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    ui.click("bulk-save")
    ui.check(
        "a save with nothing set is refused",
        "Fill in at least one field." in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )
    ui.check("and nothing is reported as updated", "Updated" not in ui.text("bulk-feedback"))
    ui.shot("Bulk edit refuses to apply when no field has been set")
    _close_modal(ui, "bulk-modal-body")


@pytest.mark.scenario(
    scenario_id="B14",
    group="B",
    title="Bulk edit sets a target state and reports how many it updated",
    feature="Browse · bulk edit",
    expected="Setting a target state on the ticked row updates it, says so, and the grid shows the new value.",
)
def test_bulk_sets_target_state(ui, record):
    ui.goto("/browse")
    _search(ui, "B-alpha-capability")
    shown, _ = _counts(ui)
    ui.must("the element this group created is in the grid", shown >= 1, ui.text("browse-count"))
    ui.check("it starts undecided", ui.grid_cell(GRID, 0, "target_state") == "undecided")
    ui.grid_tick(GRID, [0])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    ui.select("bulk-target", "change")
    ui.click("bulk-save")
    ui.check(
        "it reports how many elements it updated",
        "Updated 1 element(s)" in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )
    ui.check("nothing was refused", "refused" not in ui.text("bulk-feedback"), ui.text("bulk-feedback"))
    ui.shot("Bulk edit reports what it changed")
    _close_modal(ui, "bulk-modal-body")
    ui.check(
        "the grid shows the target state it was given",
        ui.grid_cell(GRID, 0, "target_state") == "change",
        ui.grid_cell(GRID, 0, "target_state"),
    )
    ui.shot("The grid reloads with the new target state on the row that was ticked")


# ----------------------------------------------------------------------- who may change what


@pytest.mark.scenario(
    scenario_id="B15",
    group="B",
    title="A Reader is told the page changes nothing, and cannot",
    feature="Browse · permissions",
    expected="As a Reader the banner says so and both New element and Bulk edit are disabled.",
    role="reader",
)
def test_reader_banner(ui, record):
    ui.goto("/browse")
    ui.persona("Reader")
    ui.goto("/browse")
    ui.check("the header shows the Reader persona", "READER" in ui.role_badge().upper(), ui.role_badge())
    ui.check(
        "the page says a Reader changes nothing here",
        "You are a Reader on this page" in ui.body(),
        ui.body()[:200].replace("\n", " · "),
    )
    ui.check("New element is not offered", ui.disabled("new-open"))
    ui.check("Bulk edit is not offered", ui.disabled("bulk-open"))
    ui.check("a Reader can still see the model", _counts(ui)[1] > 0, ui.text("browse-count"))
    ui.shot("Browse as a Reader: the banner, and both editing buttons disabled")


@pytest.mark.scenario(
    scenario_id="B16",
    group="B",
    title="An Architect on main is told to switch to a branch",
    feature="Browse · permissions",
    expected="As an Architect on main the banner points at the branch selector and both editing buttons are disabled.",
    role="architect",
)
def test_architect_on_main_banner(ui, record):
    ui.goto("/browse")
    ui.persona("Architect")
    ui.goto("/browse")
    ui.check(
        "the header shows the Architect persona", "ARCHITECT" in ui.role_badge().upper(), ui.role_badge()
    )
    ui.check("the reader is still on main", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.check(
        "the page says to switch to a branch to edit",
        "You are on main: switch to a branch in the header" in ui.body(),
        ui.body()[:240].replace("\n", " · "),
    )
    ui.check("New element is not offered on main", ui.disabled("new-open"))
    ui.check("Bulk edit is not offered on main", ui.disabled("bulk-open"))
    ui.shot("Browse as an Architect on main: the banner points at the branch selector")


# --------------------------------------------------------------- the Health page's deep links


FACETS = [
    ("missing=description", "without a description"),
    ("missing=links", "without a link"),
    ("missing=relationships", "without a relationship"),
    ("missing=attributes", "with a required attribute empty"),
    ("missing=target", "with an undecided target state"),
    ("missing=stale&days=30", "not updated for 30 days or more"),
    ("missing=never_updated", "never updated since the import"),
]


@pytest.mark.scenario(
    scenario_id="B17",
    group="B",
    title="Every Health deep link lands on Browse with a note saying what it is showing",
    feature="Browse · Health filters",
    expected="Each of the seven facets shows a yellow note naming the facet and a grid holding only those rows.",
)
def test_health_facet_links(ui, record):
    for query, phrase in FACETS:
        ui.goto(f"/browse?{query}")
        note = ui.text("browse-filter-note")
        ui.check(f"?{query} explains what it is showing", phrase in note, note or "(no note)")
        ui.check(
            f"?{query} says the filter came from the Health page",
            "from the Health page" in note,
            note or "(no note)",
        )
        style = ui.page.locator("#browse-filter-note [class*='Alert-root']").first.get_attribute("style")
        ui.check(f"?{query} draws the note as a yellow alert", "yellow" in (style or ""), style or "(none)")
        shown, total = _counts(ui)
        ui.check(f"?{query} counts what it kept", shown >= 0 and shown == total, ui.text("browse-count"))
        if query.startswith("missing=description"):
            ui.shot("A Health deep link filters Browse to the elements without a description")
        if query.startswith("missing=never_updated"):
            ui.shot("The 'never updated since the import' facet, with its yellow note")
    ui.goto("/browse")
    ui.check("Browse without a facet shows no filter note", ui.text("browse-filter-note") == "")
    ui.shot("Browse without a Health facet carries no filter note")


@pytest.mark.scenario(
    scenario_id="B18",
    group="B",
    title="The note saying the grid is filtered cannot be dismissed, and offers the way out",
    feature="Browse · Health filters",
    expected="A grid filtered from the Health page keeps the note that says so — there is no way to "
    "close it and leave a slice of the model looking like the whole of it — and the note carries a "
    "link back to every element.",
)
def test_the_filter_note_cannot_be_dismissed(ui, record):
    # The note is the only thing on the page that says the grid holds a slice: the type, text
    # and status controls are all unset, because the filter arrived in the address. It used to
    # carry a close button, so a reader could dismiss it and be left looking at seven rows of a
    # forty-seven element model with nothing saying so.
    ui.goto("/browse")
    _, whole_model = _counts(ui)
    ui.goto("/browse?missing=description")
    _, filtered = _counts(ui)
    ui.must("the facet filtered the grid", 0 < filtered < whole_model, f"{filtered} of {whole_model}")
    ui.must("the note explains the filter", "from the Health page" in ui.text("browse-filter-note"))
    ui.check(
        "the note has no close button",
        ui.page.locator("#browse-filter-note button").count() == 0,
        f"{ui.page.locator('#browse-filter-note button').count()} button(s) in the note",
    )
    ui.shot("A grid filtered from Health keeps the note that says so")

    back = ui.page.locator("#browse-filter-note a")
    ui.must("the note offers a way back to the whole model", back.count() > 0)
    back.first.click()
    ui.page.wait_for_url("**/browse")
    ui.settle()
    _, after = _counts(ui)
    ui.check("taking it shows every element again", after == whole_model, f"{after} of {whole_model}")
    ui.check("and the note is gone with the filter", ui.text("browse-filter-note") == "")
    ui.shot("Following the note's link restores the whole model")


# ------------------------------------------------------- what the address, the grid and the
# ------------------------------------------------------- bulk modal do that nothing above reaches

# The Browse page reads four things out of the address — `type`, `q`, `missing`/`facet` with its
# `source` and `days` — of which only `missing` and `days` are exercised above. The grid sorts,
# selects every row from its header, and keeps a tick while the filters move under it. The bulk
# modal offers seven fields and only one of them has ever been set. These are those.

ATTR_LEVEL = '[id=\'{"name":"level","type":"el-attr"}\']'


def _value(ui, component_id: str) -> str:
    """What a select or a text box on the page is showing."""
    return ui.page.locator(f"#{component_id}").first.input_value() or ""


def _brief(text: str, limit: int = 240) -> str:
    return text[:limit].replace("\n", " · ")


def _finding(finding_id: str, where: str, severity: str, summary: str, detail: str):
    from tests.ui.evidence import Finding

    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


def _header_cell(ui, col: str):
    return ui.page.locator(f"#{GRID} .ag-header-cell[col-id='{col}']").first


def _page_text(ui) -> str:
    """What the routed page itself says, without the shell around it."""
    return ui.text("page")


def _choose(ui, component_id: str, label: str, exact: bool = True) -> None:
    """A select whose options exist on other, closed dropdowns too — pick from the open one only.

    Mantine keeps every dropdown mounted, so `[role='option']` with the text 'retired' matches the
    page's own status filter as well as the modal's. Only the open dropdown is visible.
    """
    ui.page.locator(f"#{component_id}").first.click()
    ui.page.wait_for_timeout(250)
    pattern = re.compile(f"^{re.escape(label)}$") if exact else re.compile(re.escape(label))
    ui.page.locator("[role='option']:visible").filter(has_text=pattern).first.click()
    ui.settle()


def _tab(ui, label: str) -> None:
    ui.click(f"#el-tabs [role='tab']:has-text('{label}')")
    ui.page.wait_for_timeout(250)


@pytest.mark.scenario(
    scenario_id="B19",
    group="B",
    title="The address can arrive with the type filter and the search already set",
    feature="Browse · the address",
    expected="/browse?type=data_entity fills the type filter and shows only that type, ?q= fills the "
    "search box and finds what typing the same word finds, and the two together apply both.",
)
def test_address_presets_the_filters(ui, record):
    ui.goto("/browse")
    _, whole_model = _counts(ui)
    ui.goto("/browse?type=data_entity")
    label = _value(ui, "browse-type")
    ui.check("the type filter shows the type the address named", label.startswith("Data Entity"), label)
    _, of_that_type = _counts(ui)
    ui.must("the address narrowed the grid to one type", 0 < of_that_type < whole_model, label)
    types = _column(ui, "type")
    ui.check(
        "every row shown is of that type",
        bool(types) and all(t == "Data Entity" for t in types),
        str(types),
    )
    counted = re.search(r"\((\d+)\)", label)
    ui.check(
        "the count the filter carries in its own label is the number of rows it yields",
        bool(counted) and int(counted.group(1)) == of_that_type,
        f"{label} against {ui.text('browse-count')}",
    )
    ui.shot("The address arrived with the type filter already set to Data Entity")

    ui.goto("/browse?q=curriculum")
    ui.check("the search box holds the word the address carried", _value(ui, "browse-text") == "curriculum")
    _, from_address = _counts(ui)
    first_from_address = ui.grid_cell(GRID, 0, "name")
    ui.goto("/browse")
    _search(ui, "curriculum")
    _, typed = _counts(ui)
    ui.check(
        "?q= finds exactly what typing the same word finds",
        from_address == typed and from_address > 0,
        f"{from_address} from the address, {typed} typed",
    )
    ui.check(
        "and ranks it the same way",
        first_from_address == ui.grid_cell(GRID, 0, "name"),
        f"{first_from_address!r} from the address, {ui.grid_cell(GRID, 0, 'name')!r} typed",
    )
    ui.shot("The address arrived with the search word already in the box")

    ui.goto("/browse?type=data_entity&q=unit")
    _, both = _counts(ui)
    ui.must("the two together find something", both > 0, ui.text("browse-count"))
    ui.check(
        "the two together are narrower than the type alone", both < of_that_type, f"{both} of {whole_model}"
    )
    rows = list(zip(_column(ui, "type"), _column(ui, "name"), _column(ui, "snippet"), strict=False))
    ui.check(
        "every row is of the type asked for and holds the word asked for",
        bool(rows) and all(t == "Data Entity" and "unit" in f"{n} {s}".lower() for t, n, s in rows),
        str(rows[:3]),
    )
    ui.shot("The address arrived with both the type and the search word set")


@pytest.mark.scenario(
    scenario_id="B20",
    group="B",
    title="A Health link can name the facet either way, and can narrow it to one source",
    feature="Browse · Health filters",
    expected="?facet= shows exactly what ?missing= shows, and &source= keeps only that source's rows "
    "and says so in the note.",
)
def test_facet_alias_and_source(ui, record):
    ui.goto("/browse?missing=description")
    by_missing = (ui.text("browse-filter-note"), ui.grid_row_ids(GRID), ui.text("browse-count"))
    ui.must("the facet kept rows to compare", bool(by_missing[1]), by_missing[2])
    ui.goto("/browse?facet=description")
    ui.check("?facet= says exactly what ?missing= says", ui.text("browse-filter-note") == by_missing[0])
    ui.check(
        "and keeps exactly the same rows", ui.grid_row_ids(GRID) == by_missing[1], ui.text("browse-count")
    )
    ui.check(
        "and counts them the same way", ui.text("browse-count") == by_missing[2], ui.text("browse-count")
    )
    ui.shot("?facet= is the same address as ?missing=")

    ui.goto("/browse?missing=never_updated")
    _, every_source = _counts(ui)
    sources = [s for s in _column(ui, "source_system") if s]
    ui.must("the facet holds rows that name a source", bool(sources) and every_source > 0, str(sources[:3]))
    source = sources[0]
    ui.goto(f"/browse?missing=never_updated&source={source}")
    note = ui.text("browse-filter-note")
    ui.check(
        "the note says it is showing one source only", f"from source {source}" in note, note or "(no note)"
    )
    ui.check("the note still says where the filter came from", "from the Health page" in note, note)
    _, from_one = _counts(ui)
    ui.check(
        "narrowing to one source keeps no more than the facet held",
        0 < from_one <= every_source,
        f"{from_one} of {every_source}",
    )
    kept = _column(ui, "source_system")
    ui.check("every row kept came from that source", bool(kept) and all(s == source for s in kept), str(kept))
    ui.shot("A Health link narrowed to one source system")

    ui.goto("/browse?missing=never_updated&source=zzz-no-such-source")
    ui.check("a source the model does not hold keeps nothing", _counts(ui) == (0, 0), ui.text("browse-count"))
    ui.check("and the grid is empty", ui.grid_row_count(GRID) == 0)
    ui.check(
        "and the note still says which source was asked for",
        "from source zzz-no-such-source" in ui.text("browse-filter-note"),
        ui.text("browse-filter-note") or "(no note)",
    )
    ui.check(
        "with the way back to the whole model still offered",
        ui.page.locator("#browse-filter-note a").count() > 0,
    )
    ui.shot("A source the model does not hold keeps nothing, and the note says which source was asked for")


@pytest.mark.scenario(
    scenario_id="B21",
    group="B",
    title="A facet the model does not know empties the grid rather than failing",
    feature="Browse · a bad address",
    expected="/browse?missing=nonsense renders the page in full, keeps nothing, and still offers the "
    "link back to every element.",
)
def test_unknown_facet(ui, record, finding):
    ui.goto("/browse?missing=zzz-no-such-facet")
    ui.must("the page still renders its grid", ui.visible(GRID), _brief(_page_text(ui)))
    ui.check(
        "nothing on the page reads as a failure",
        not re.search(r"traceback|failed to render|error:", _page_text(ui), re.I),
        _brief(_page_text(ui)),
    )
    ui.check(
        "the filters are still there to work with", ui.visible("browse-type") and ui.visible("browse-text")
    )
    ui.check("nothing is kept", _counts(ui) == (0, 0), ui.text("browse-count"))
    ui.check("and the grid is empty", ui.grid_row_count(GRID) == 0)
    note = ui.text("browse-filter-note")
    ui.check("a note still says the grid is filtered", "from the Health page" in note, note or "(no note)")
    ui.check(
        "and says the filter in the address is not one this page knows",
        "is not a filter this page knows" in note,
        note or "(no note)",
    )
    ui.check(
        "and the way back to the whole model is offered", ui.page.locator("#browse-filter-note a").count() > 0
    )
    ui.shot("A facet the model does not know: an empty grid, and the link back to every element")
    if "is not a filter this page knows" not in note:
        finding.append(
            _finding(
                finding_id="B-1",
                where="src/ea/ui/pages/browse.py · _filter_note(), FACET_LABELS.get(facet, facet)",
                severity="usability",
                summary="An unknown facet is read back to the reader as though it were a filter the page knows",
                detail=(
                    "FACET_LABELS falls back to the raw token, so /browse?missing=zzz-no-such-facet reads "
                    "'Showing only the elements zzz-no-such-facet (from the Health page).' over an empty "
                    "grid. A stale bookmark or a renamed facet therefore looks like a model with nothing "
                    "in it rather than an address the page could not read. Health links are the only "
                    "source of these addresses, so an unrecognised facet should say so."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="B22",
    group="B",
    title="A days= the page cannot read falls back rather than taking the page down",
    feature="Browse · a bad address",
    expected="/browse?missing=stale&days=abc still renders the grid and the filters, the way an "
    "unknown work package still renders the Target state page.",
)
def test_unreadable_days(ui, record):
    ui.goto("/browse?missing=stale&days=30")
    ui.must("the well-formed link works", ui.visible(GRID), _brief(_page_text(ui)))
    ui.check("and says how long is too long", "30 days or more" in ui.text("browse-filter-note"))

    ui.goto("/browse?missing=stale&days=abc")
    ui.check(
        "a days= that is not a number does not take the page down",
        ui.visible(GRID),
        _brief(_page_text(ui)),
    )
    ui.check(
        "and the reader is not shown a raw exception",
        not re.search(r"valueerror|traceback|failed to render", _page_text(ui), re.I),
        _brief(_page_text(ui)),
    )
    ui.check(
        "the filters are still there to work with",
        ui.visible("browse-type") and ui.visible("browse-text"),
        _brief(_page_text(ui)),
    )
    ui.shot("A days= the page cannot read")

    ui.goto("/browse")
    ui.check("and the page comes back as soon as the address is right", ui.visible(GRID))
    ui.check("with the whole model in it", _counts(ui)[1] > 0, ui.text("browse-count"))


@pytest.mark.scenario(
    scenario_id="B23",
    group="B",
    title="A column header sorts the grid without changing what is in it",
    feature="Browse · the grid",
    expected="Clicking the Name header sorts the rows by name, clicking it again reverses them, and "
    "the 'N of M' count never moves.",
)
def test_column_sorting(ui, record):
    ui.goto("/browse")
    ui.must("there are rows to sort", ui.grid_row_count(GRID) > 2)
    before = ui.text("browse-count")
    header = _header_cell(ui, "name")
    header.locator(".ag-header-cell-label").first.click()
    ui.settle()
    ascending = _column(ui, "name")
    ui.check(
        "one click sorts the names upwards",
        ascending == sorted(ascending) or ascending == sorted(ascending, key=str.lower),
        str(ascending[:4]),
    )
    ui.check(
        "and the header says which way it is sorted",
        (_header_cell(ui, "name").get_attribute("aria-sort") or "") == "ascending",
        f"aria-sort={_header_cell(ui, 'name').get_attribute('aria-sort')}",
    )
    ui.shot("The grid sorted by name, upwards")
    header.locator(".ag-header-cell-label").first.click()
    ui.settle()
    descending = _column(ui, "name")
    ui.check(
        "a second click sorts them downwards",
        descending == sorted(descending, reverse=True)
        or descending == sorted(descending, key=str.lower, reverse=True),
        str(descending[:4]),
    )
    ui.check(
        "which is not the order they arrived in",
        bool(descending) and bool(ascending) and descending[0] != ascending[0],
        f"{ascending[0]!r} upwards, {descending[0]!r} downwards",
    )
    ui.check(
        "and the header says so too",
        (_header_cell(ui, "name").get_attribute("aria-sort") or "") == "descending",
        f"aria-sort={_header_cell(ui, 'name').get_attribute('aria-sort')}",
    )
    ui.check(
        "sorting changes no count",
        ui.text("browse-count") == before,
        f"{ui.text('browse-count')} against {before}",
    )
    ui.shot("The same rows sorted by name, downwards")


@pytest.mark.scenario(
    scenario_id="B24",
    group="B",
    title="An identifier finds its element, whatever case it is typed in and however little of a word",
    feature="Browse · ranked search",
    expected="Searching an element's identifier finds it and says it matched on the identifier; the "
    "same search in the other case finds the same row, and part of a word finds the name it is part of.",
)
def test_search_by_identifier_and_part_of_a_word(ui, record):
    ui.goto("/browse")
    _search(ui, "LDC-CURR")
    shown, _ = _counts(ui)
    ui.must("the identifier finds something", shown >= 1, ui.text("browse-count"))
    ui.check(
        "the element with that identifier is one of them",
        "LDC-CURR" in ui.grid_row_ids(GRID),
        str(ui.grid_row_ids(GRID)[:5]),
    )
    ui.check(
        "and the 'matched in' column says the identifier is why",
        "LDC-CURR" in ui.grid_cell_of(GRID, "LDC-CURR", "snippet"),
        ui.grid_cell_of(GRID, "LDC-CURR", "snippet") or "(empty)",
    )
    ui.shot("An identifier finds its element and says the identifier is why")

    _search(ui, "ldc-curr")
    ui.check(
        "the same identifier in the other case finds the same row",
        "LDC-CURR" in ui.grid_row_ids(GRID),
        str(ui.grid_row_ids(GRID)[:5]),
    )
    _search(ui, "urriculu")
    ui.check(
        "part of a word finds the name it is part of",
        "LDC-CURR" in ui.grid_row_ids(GRID),
        str(ui.grid_row_ids(GRID)[:5]),
    )
    ui.check(
        "and a row matched inside its own name shows no snippet",
        ui.grid_cell_of(GRID, "LDC-CURR", "snippet") == "",
        ui.grid_cell_of(GRID, "LDC-CURR", "snippet"),
    )
    ui.shot("Part of a word finds the names it is part of")


@pytest.mark.scenario(
    scenario_id="B25",
    group="B",
    title="Bulk edit sets a status, a note and an attribute in one pass",
    feature="Browse · bulk edit",
    expected="Status, Target note and an attribute set together on the ticked row all land: the grid "
    "shows the new status and the element carries the note and the attribute.",
)
def test_bulk_sets_status_note_and_attribute(ui, record):
    # Only this group's own element is touched, and only in fields no other group reads: the
    # current state and the work package are left alone because the Target state page counts both.
    ui.goto("/browse")
    _search(ui, "B-alpha-capability")
    shown, _ = _counts(ui)
    ui.must("the element this group created is in the grid", shown >= 1, ui.text("browse-count"))
    element_id = ui.grid_cell(GRID, 0, "element_id")
    ui.check(
        "it is still a draft before the edit",
        ui.grid_cell(GRID, 0, "status") == "draft",
        ui.grid_cell(GRID, 0, "status"),
    )
    ui.grid_tick(GRID, [0])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    _choose(ui, "bulk-status", "approved")
    ui.fill("bulk-note", "Approved in bulk by the Browse round")
    ui.fill("bulk-attr-name", "level")
    ui.fill("bulk-attr-value", "3")
    ui.click("bulk-save")
    ui.check(
        "it reports the one element it updated",
        "Updated 1 element(s)" in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )
    ui.check("nothing was refused", "refused" not in ui.text("bulk-feedback"), ui.text("bulk-feedback"))
    ui.shot("Bulk edit applying a status, a note and an attribute together")
    _close_modal(ui, "bulk-modal-body")
    ui.check(
        "the grid shows the status it was given",
        ui.grid_cell(GRID, 0, "status") == "approved",
        ui.grid_cell(GRID, 0, "status"),
    )
    ui.check(
        "and the target state the round set earlier is untouched",
        ui.grid_cell(GRID, 0, "target_state") == "change",
        ui.grid_cell(GRID, 0, "target_state"),
    )
    ui.shot("The grid reloads with the new status on the row that was ticked")

    ui.goto(f"/element/{element_id}")
    ui.must("the element it edited opens", element_id in ui.body(), ui.page.url)
    ui.check(
        "the element carries the note bulk edit gave it",
        "Approved in bulk by the Browse round" in ui.body(),
        _brief(ui.body()),
    )
    _tab(ui, "Edit")
    level = ui.page.locator(ATTR_LEVEL).first
    ui.must("the attribute bulk edit named has an input on the element", level.count() > 0, "level")
    ui.check("and it holds the value bulk edit set", level.input_value() == "3", level.input_value())
    ui.shot("The element bulk edit changed: the note, and the attribute it was given")


@pytest.mark.scenario(
    scenario_id="B26",
    group="B",
    title="The header tick selects every row the filters left, and bulk edit counts them",
    feature="Browse · bulk edit",
    expected="Ticking the header box selects every row in view and Bulk edit opens saying how many "
    "that is; leaving the modal changes nothing.",
)
def test_header_tick_selects_every_row(ui, record):
    ui.goto("/browse")
    ui.select("browse-type", "Capability")
    shown, _ = _counts(ui)
    ui.must("the filter left a handful of rows", 1 < shown <= 20, ui.text("browse-count"))
    ui.must(
        "all of them are rendered", ui.grid_row_count(GRID) == shown, f"{ui.grid_row_count(GRID)} of {shown}"
    )
    header_box = ui.page.locator(f"#{GRID} .ag-header-cell[col-id='sel'] input").first
    ui.must("the header offers a tick of its own", header_box.count() > 0)
    header_box.click(force=True)
    ui.settle()
    ticked = ui.page.locator(f"#{GRID} .ag-row .ag-cell[col-id='sel'] input:checked").count()
    ui.check("it ticks every row in view", ticked == shown, f"{ticked} ticked of {shown} shown")
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    ui.check(
        "and it holds every row the filter left",
        f"{shown} element(s) ticked." in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )
    ui.shot("The header tick selects every row the type filter left, and bulk edit says how many")
    _close_modal(ui, "bulk-modal-body")
    ui.check(
        "leaving the modal reports nothing as changed",
        "Updated" not in ui.text("bulk-feedback"),
        ui.text("bulk-feedback"),
    )


@pytest.mark.scenario(
    scenario_id="B27",
    group="B",
    title="Every field in the bulk modal holds what it is given, and closing it applies nothing",
    feature="Browse · bulk edit",
    expected="Status, Current state, Target state, Work package, Target note and the attribute pair "
    "each read back what was chosen, and closing the modal leaves the ticked row exactly as it was.",
)
def test_bulk_fields_hold_what_they_are_given(ui, record):
    ui.goto("/browse")
    _search(ui, "B-alpha-capability")
    ui.must(
        "this group's own element is the row to tick", ui.grid_row_count(GRID) >= 1, ui.text("browse-count")
    )
    before = (
        ui.grid_cell(GRID, 0, "status"),
        ui.grid_cell(GRID, 0, "current_state"),
        ui.grid_cell(GRID, 0, "target_state"),
    )
    ui.grid_tick(GRID, [0])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened", ui.visible("bulk-modal-body"))
    _choose(ui, "bulk-status", "retired")
    _choose(ui, "bulk-current", "in_implementation")
    _choose(ui, "bulk-target", "decommission")
    _choose(ui, "bulk-wp", "Curriculum Management System Upgrade", exact=False)
    ui.fill("bulk-note", "Never applied — this scenario closes the modal")
    ui.fill("bulk-attr-name", "level")
    ui.fill("bulk-attr-value", "9")
    for field, value in (
        ("bulk-status", "retired"),
        ("bulk-current", "in_implementation"),
        ("bulk-target", "decommission"),
        ("bulk-attr-name", "level"),
        ("bulk-attr-value", "9"),
    ):
        ui.check(f"'{field}' reads back what it was given", _value(ui, field) == value, _value(ui, field))
    ui.check(
        "the work package offers the model's own work packages",
        "Curriculum Management System Upgrade" in _value(ui, "bulk-wp"),
        _value(ui, "bulk-wp"),
    )
    ui.check(
        "and the work package names the element behind it",
        "WP-" in _value(ui, "bulk-wp"),
        _value(ui, "bulk-wp"),
    )
    ui.check(
        "the note holds what was typed",
        _value(ui, "bulk-note").startswith("Never applied"),
        _value(ui, "bulk-note"),
    )
    ui.shot("Every field of the bulk edit modal filled in, before it is closed unapplied")
    _close_modal(ui, "bulk-modal-body")
    ui.check(
        "nothing was reported as updated", "Updated" not in ui.text("bulk-feedback"), ui.text("bulk-feedback")
    )
    after = (
        ui.grid_cell(GRID, 0, "status"),
        ui.grid_cell(GRID, 0, "current_state"),
        ui.grid_cell(GRID, 0, "target_state"),
    )
    ui.check("and the ticked row is exactly as it was", after == before, f"{before} before, {after} after")
    ui.shot("Closing the modal leaves the ticked row exactly as it was")


@pytest.mark.scenario(
    scenario_id="B28",
    group="B",
    title="A tick does not survive the filter that takes its row away",
    feature="Browse · bulk edit",
    expected="Ticking a row and then searching for something else leaves nothing ticked, so bulk edit "
    "can never change a row the reader cannot see.",
)
def test_a_tick_does_not_outlive_its_row(ui, record):
    ui.goto("/browse")
    _search(ui, "curriculum")
    ui.must("there is a row to tick", ui.grid_row_count(GRID) >= 1, ui.text("browse-count"))
    ticked_id = ui.grid_cell(GRID, 0, "element_id")
    ui.grid_tick(GRID, [0])
    ui.check(
        "the row is ticked to begin with",
        ui.page.locator(f"#{GRID} .ag-row .ag-cell[col-id='sel'] input:checked").count() == 1,
        ticked_id,
    )
    _search(ui, "B-alpha-capability")
    ui.must(
        "the row that was ticked is no longer in the grid",
        ticked_id not in ui.grid_row_ids(GRID),
        f"{ticked_id} against {ui.grid_row_ids(GRID)[:5]}",
    )
    still_ticked = ui.page.locator(f"#{GRID} .ag-row .ag-cell[col-id='sel'] input:checked").count()
    ui.check("nothing in the grid is ticked any more", still_ticked == 0, f"{still_ticked} still ticked")
    ui.click("bulk-open")
    opened = ui.page.locator("#bulk-modal-body").count() > 0
    feedback = ui.text("bulk-feedback")
    # Either answer is a safe one: the modal that stays shut, or the modal that opens holding
    # nothing. What it must not say is that it holds a row the reader can no longer see.
    ui.check(
        "and bulk edit holds nothing, because the row it was given is gone from the grid",
        (not opened) or "Nothing is ticked." in feedback,
        feedback or "the modal stayed shut",
    )
    ui.shot("A tick left behind by a change of search: what bulk edit says it holds")
    _close_modal(ui, "bulk-modal-body")


@pytest.mark.scenario(
    scenario_id="B29",
    group="B",
    title="The Reader's banner cannot be closed, because it is the only reason the page gives",
    feature="Browse · permissions",
    expected="The banner that says a Reader changes nothing carries no close button — closing it would "
    "leave New element and Bulk edit greyed out and unexplained — and both buttons are disabled with it "
    "on the page.",
    role="reader",
)
def test_reader_banner_is_not_dismissible(ui, record, finding):
    ui.goto("/browse")
    ui.persona("Reader")
    ui.goto("/browse")
    banner = ui.page.locator("[class*='Alert-root']").filter(has_text="You are a Reader on this page")
    ui.must(
        "the page explains why a Reader changes nothing", banner.count() == 1, f"{banner.count()} banner(s)"
    )
    ui.must(
        "both editing buttons are disabled to begin with",
        ui.disabled("new-open") and ui.disabled("bulk-open"),
        f"new={ui.disabled('new-open')}, bulk={ui.disabled('bulk-open')}",
    )
    close = banner.locator("button")
    dismissible = close.count() > 0
    ui.check(
        "the only reason the page gives cannot be taken off it",
        not dismissible,
        f"{close.count()} close button(s) on the banner",
    )
    if dismissible:
        close.first.click()
        ui.page.wait_for_timeout(300)
        ui.settle()
        ui.check(
            "closing the explanation takes it off the page",
            "You are a Reader on this page" not in ui.body(),
            _brief(ui.body()),
        )
    ui.check("New element is disabled with the reason beside it", ui.disabled("new-open"))
    ui.check("Bulk edit is disabled with the reason beside it", ui.disabled("bulk-open"))
    ui.check("and a Reader can still read the model", _counts(ui)[1] > 0, ui.text("browse-count"))
    ui.shot("Browse as a Reader: the reason stays on the page beside the two refused buttons")
    if dismissible:
        finding.append(
            _finding(
                finding_id="B-2",
                where="src/ea/ui/pages/browse.py · render(), the permission banner built by components.alert()",
                severity="usability",
                summary="The only reason given for the two disabled buttons can be closed, and nothing replaces it",
                detail=(
                    "components.alert() always sets withCloseButton=True, so the reader closes "
                    "'You are a Reader on this page…' (or 'You are on main: switch to a branch…') and is "
                    "left with New element and Bulk edit greyed out and unexplained for the rest of the "
                    "session. Neither button carries a tooltip of its own, although the header's New "
                    "branch icon in src/ea/ui/layout.py sets exactly that ('Your role may not create "
                    "branches'). The filter note above the grid was made non-dismissible for the same "
                    "reason; this banner was not."
                ),
            )
        )
    ticks = ui.page.locator(f"#{GRID} .ag-row[row-index='0'] .ag-cell[col-id='sel'] input").count()
    ui.check(
        "and no tick column is offered to a role that cannot act on a tick",
        ticks == 0,
        f"{ticks} tick(s) in the first row",
    )
    if ticks:
        finding.append(
            _finding(
                finding_id="B-3",
                where="src/ea/ui/pages/browse.py · COLUMNS, the 'sel' column",
                severity="usability",
                summary="A Reader is offered a tick column that leads nowhere",
                detail=(
                    "checkboxSelection and headerCheckboxSelection are set for every role, so a Reader "
                    "can tick a row — or the header box, and select the whole model — with Bulk edit "
                    "disabled and no other action to apply to the selection. The column promises "
                    "something the role cannot do."
                ),
            )
        )
    # The last scenario of the group: leave the application where the group found it.
    ui.persona("Admin")
    ui.goto("/browse")
