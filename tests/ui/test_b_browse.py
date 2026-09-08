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
    title="Bulk edit does not open with nothing ticked",
    feature="Browse · bulk edit",
    expected="Pressing Bulk edit before any row is ticked leaves the modal shut.",
)
def test_bulk_needs_a_tick(ui, record):
    ui.goto("/browse")
    ui.check("Bulk edit is offered to an Admin on main", not ui.disabled("bulk-open"))
    ui.click("bulk-open")
    ui.check(
        "the modal stays shut with nothing ticked",
        ui.page.locator("#bulk-modal-body").count() == 0,
        f"{ui.page.locator('#bulk-modal-body').count()} modal bodies in the page",
    )
    ui.shot("Bulk edit with nothing ticked leaves the reader on the grid")
    # Nothing tells the reader why the button did nothing — see the round's findings.
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
    title="Dismissing the Health filter note must not hide that the grid is still filtered",
    feature="Browse · Health filters",
    expected="Closing the yellow note either clears the filter or leaves something on the page saying the grid is filtered.",
)
def test_dismissing_the_filter_note(ui, record):
    # The note is the only thing that says the grid holds a slice of the model, and
    # `alert()` in src/ea/ui/components.py always gives it a close button. Closing it
    # leaves the reader looking at 7 rows of a 48-element model with nothing saying so —
    # and the count, which browse.py `_load` recomputes as `total = len(rows)` under a
    # facet, reads "7 of 7" rather than "7 of 48", so it reinforces the illusion.
    ui.goto("/browse")
    _, whole_model = _counts(ui)
    ui.goto("/browse?missing=description")
    _, filtered = _counts(ui)
    ui.must("the facet filtered the grid", 0 < filtered < whole_model, f"{filtered} of {whole_model}")
    ui.must("the note explains the filter", "from the Health page" in ui.text("browse-filter-note"))
    ui.page.locator("#browse-filter-note button").first.click()
    ui.settle()
    ui.check("the note can be dismissed", ui.text("browse-filter-note") == "", ui.text("browse-filter-note"))
    _, after = _counts(ui)
    body = ui.body()
    still_says_so = "from the Health page" in body or "without a description" in body
    ui.check(
        "dismissing the note either clears the filter or still says the grid is filtered",
        after == whole_model or still_says_so,
        f"the grid still holds {after} of {whole_model} elements and nothing on the page says so",
    )
    ui.shot("The filter note dismissed: the grid is still filtered and nothing says so")
