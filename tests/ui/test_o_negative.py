"""Group O — negative paths: what is supposed to fail, and how well it fails.

Every scenario here asks the application for something it must refuse, then reads the
refusal rather than the outcome: an address naming nothing, a form with a field left
empty, a name already taken, a file that is not the file it claims to be, a proposal too
thin to apply. A refusal only passes this group when it is visible, when it names what
was wrong, and when the model is exactly as it was afterwards — a page that fails
silently, or that half-applies a change, is a defect however tidy the screen looks.

Everything the group creates carries an `O` so no other group can be moved by it: the
branch `o-negative`, created once so that the same name can be refused a second time; the
element `O Probe Element oprobe`, whose whole purpose is to be saved badly; and the CSV
rows `O-BROKEN-…`, which are never meant to reach the model at all. One row does reach
it — the element the ragged file in O11 fabricates — and it is loaded onto `o-negative`
rather than onto main, so the defect is evidenced without the model other groups read
being touched. The group ends on main as Admin, with nothing open.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

GRID = "browse-grid"
BRANCH_MODAL = "branch-new-modal-body"  # dmc.Modal puts the id on its parts, not on a root node
NEW_MODAL = "new-modal-body"
BULK_MODAL = "bulk-modal-body"

BRANCH_NAME = "O negative"
BRANCH_ID = "o-negative"
REFUSED_BRANCH = "O not created"  # asked for on the Propose page, and never to be created
REFUSED_BRANCH_ID = "o-not-created"

PROBE_TOKEN = "oprobe"  # one word, in this group's element only, so a search finds it alone
PROBE_NAME = f"O Probe Element {PROBE_TOKEN}"
PROBE_TYPE = "Data Entity"

# The proposal box is a markdown editor, so its textarea carries a pattern-matching id.
PASTE = '[id=\'{"id":"pr-text","type":"md-text"}\']'

# Three rows, three defects, and an edge whose target is nowhere: nothing here may load.
BROKEN_ELEMENTS_CSV = (
    "id,type,name,description\n"
    "O-BROKEN-TYPE,not_a_real_type,O Broken Type,A row whose type the metamodel does not hold.\n"
    "O-BROKEN-NAME,data_entity,,A row with no name at all.\n"
    ",data_entity,O Broken Id,A row with neither an id nor a key.\n"
)
BROKEN_RELATIONSHIPS_CSV = "src_id,rel_type,dst_id\nO-BROKEN-TYPE,encapsulates,O-BROKEN-NOWHERE\n"
# Not the shape it claims: the header declares three columns and the row carries seven, so a
# reader that folds the surplus away keeps the tail of the line and drops the row that was written.
RAGGED_DECLARED = "O-RAGGED-DECLARED"
RAGGED_GHOST = "O-RAGGED-GHOST"
RAGGED_CSV = (
    "id,type,name\n"
    f"{RAGGED_DECLARED},data_entity,O Ragged Declared,spare,{RAGGED_GHOST},data_entity,O Ragged Ghost\n"
)

# A proposal with one defect per row: a type the pack does not hold, a row with no
# description, an existing id that is nowhere, and an edge into an element that is nowhere.
PROPOSAL = """# Proposal: O negative path

| Field | Value |
| ----- | ----- |
| **Work package** | Curriculum Management System Upgrade |

## Summary

A deliberately incomplete proposal, handed in by the negative-path group so that the
page's pushback can be read and its refusal to apply can be proved.

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Nonexistent Type | O Nowhere Service | | A service whose type the metamodel does not hold at all. | proposed | new |
| Data Entity | O Undescribed Record | | | proposed | new |
| Data Entity | O Ghost Reference | O-NO-SUCH-ID | A row pointing at an identifier the repository has never held. | live | keep |

## Relationships

| Source | Relationship | Target | Note |
| ------ | ------------ | ------ | ---- |
| O Nowhere Service | processes | O Missing Element | the target is nowhere |
"""


# --------------------------------------------------------------------------- the controls


def _finding(finding_id: str, where: str, severity: str, summary: str, detail: str) -> Finding:
    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


def _brief(text: str, limit: int = 240) -> str:
    return " · ".join(line.strip() for line in text.splitlines() if line.strip())[:limit]


def _pick(ui, select_id: str, label: str) -> None:
    """Open a select and choose from the dropdown that is showing.

    Every select keeps its options mounted, so only the visible ones belong to the one
    that was just opened.
    """
    ui.click(select_id)
    ui.page.locator("[role='option']:visible").filter(has_text=re.compile(re.escape(label))).first.click()
    ui.settle()


def _close_modal(ui, body_id: str) -> None:
    """Never leave a scenario mid-modal: Escape, and let the page settle."""
    if ui.page.locator(f"#{body_id}").count():
        ui.page.keyboard.press("Escape")
        ui.page.wait_for_timeout(400)
        ui.settle()


def _tab(ui, label: str) -> None:
    ui.click(f"#el-tabs [role='tab']:has-text({json.dumps(label)})")
    ui.page.wait_for_timeout(200)


def _page(ui) -> str:
    """What the page itself says, without the header and the navigation around it."""
    return ui.text("page")


def _heading(ui) -> str:
    heading = ui.page.locator("#page h1, #page h2").first
    return heading.inner_text().strip() if heading.count() else ""


def _version(ui) -> int:
    """The `v3` the element header prints beside the identifier."""
    loc = ui.page.get_by_text(re.compile(r"^v\d+$")).first
    return int(loc.inner_text().strip()[1:]) if loc.count() else -1


def _write(ui, name: str, text: str) -> Path:
    """Put a file where the browser can pick it up, beside the run's other evidence."""
    d = ui.run_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_text(text, encoding="utf-8")
    return path


def _upload(ui, *paths: Path) -> None:
    ui.page.locator("#im-upload input[type=file]").first.set_input_files([str(p) for p in paths])
    for p in paths:
        ui.page.locator("#im-files").get_by_text(p.name, exact=False).first.wait_for(timeout=20_000)
    ui.settle()


def _new_branch(ui, name: str) -> str:
    """Open the New branch modal from the header, ask for `name`, and return what it said."""
    ui.goto("/browse")
    ui.click("branch-new-open")
    ui.must("the New branch modal opened", ui.visible(BRANCH_MODAL))
    if name:
        ui.fill("branch-new-name", name)
    ui.click("branch-new-save")
    return ui.text("branch-new-feedback")


def _probe_id(ui) -> str:
    """This group's own element, created once and found by its one-word marker."""
    ui.goto(f"/browse?q={PROBE_TOKEN}")
    if ui.grid_row_count(GRID):
        return ui.grid_cell(GRID, 0, "element_id")
    ui.click("new-open")
    _pick(ui, "new-type", PROBE_TYPE)
    ui.fill("new-name", PROBE_NAME)
    ui.click("new-save")
    ui.page.wait_for_selector("#el-tabs", timeout=20_000)
    ui.settle()
    return ui.page.url.rstrip("/").rsplit("/", 1)[-1]


# ------------------------------------------------------------------------- bad addresses


@pytest.mark.scenario(
    scenario_id="O01",
    group="O",
    title="An element identifier the model does not hold says so instead of failing",
    feature="Negative · element · unknown identifier",
    expected=(
        "/element/NOPE renders a 'Not found' page naming the identifier that was asked for, with the "
        "header and the navigation intact and nothing reading as a crash."
    ),
)
def test_unknown_element_id(ui, record, finding):
    ui.goto("/element/NOPE")
    ui.must("the page rendered", ui.visible("page"), _brief(_page(ui)))
    body = _page(ui)
    ui.check("the page is headed 'Not found'", _heading(ui) == "Not found", _heading(ui))
    ui.check(
        "and it names the identifier that was asked for",
        "No element with id NOPE." in body,
        _brief(body),
    )
    ui.check("nothing reports a crash", "This page failed to render" not in body, _brief(body))
    ui.check(
        "no exception leaked onto the page",
        not re.search(r"traceback|NotFoundError|KeyError", body, re.I),
        _brief(body),
    )
    ui.check("the header survived", ui.visible(".mantine-AppShell-header"))
    ui.check("the navigation survived", ui.visible("nav-browse"))
    ui.check(
        "and the address is left as it was typed",
        ui.page.url.endswith("/element/NOPE"),
        ui.page.url,
    )
    ui.shot("An element identifier the model does not hold: 'Not found', naming the id that was asked for")

    # An identifier with punctuation in it goes down the same path rather than the router's.
    ui.goto("/element/O%20NOT%20AN%20ID")
    ui.check(
        "an identifier with spaces is refused the same way",
        _heading(ui) == "Not found",
        _heading(ui),
    )
    ui.check(
        "and it too says which identifier was not found",
        "O NOT AN ID" in _page(ui),
        _brief(_page(ui)),
    )
    ui.shot("An identifier with spaces in it is refused the same way, quoting what was asked for")

    way_out = ui.page.locator("#page a").count()
    if not way_out:
        finding.append(
            _finding(
                finding_id="O-1",
                where="src/ea/ui/pages/element.py · render(), the NotFoundError branch",
                severity="usability",
                summary="The 'Not found' page is a dead end: it names the identifier but offers no way on",
                detail=(
                    "The branch returns a title and one sentence and nothing else — no link to Browse, "
                    "no search box, not even a suggestion that the identifier may have been merged or "
                    "renamed. A reader who followed a stale link has to reach for the navigation. The "
                    "Import page's refusals name what to do next; this one should too."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="O02",
    group="O",
    title="An address the router does not know falls back to Home rather than erroring",
    feature="Negative · routing",
    expected=(
        "An unknown path, and a half-written /element with no identifier, both render Home with the "
        "shell intact; the navigation marks Home as the page the reader is on."
    ),
)
def test_unknown_route(ui, record, finding):
    ui.goto("/o-no-such-page")
    body = _page(ui)
    ui.check("Home is rendered instead", "Higher Education EA Metamodel" in _heading(ui), _heading(ui))
    ui.check("nothing reports a crash", "This page failed to render" not in body, _brief(body))
    marked = [
        nav
        for nav in ("nav-home", "nav-browse", "nav-import", "nav-branches")
        if ui.page.locator(f"#{nav}").first.get_attribute("data-active") is not None
    ]
    ui.check(
        "the navigation marks Home as where the reader is",
        marked == ["nav-home"],
        f"marked active: {marked or 'nothing'}",
    )
    ui.check("the header survived", ui.visible(".mantine-AppShell-header"))
    ui.check("the address is left as it was typed", ui.page.url.endswith("/o-no-such-page"), ui.page.url)
    ui.shot("An address the router does not know renders Home, with Home marked in the navigation")

    ui.goto("/element")
    ui.check(
        "an /element address with no identifier lands on Home too",
        "Higher Education EA Metamodel" in _heading(ui),
        _heading(ui),
    )
    ui.check("and not on an error", "This page failed to render" not in _page(ui), _brief(_page(ui)))

    said_so = re.search(r"not found|unknown|does not exist|no such", _page(ui), re.I)
    if not said_so:
        finding.append(
            _finding(
                finding_id="O-2",
                where="src/ea/ui/app.py · parse_path(), the fall-through to home",
                severity="usability",
                summary="An unrecognised address is answered with Home and no word that it was not recognised",
                detail=(
                    "parse_path() returns ('home', None) for anything it cannot place, so a mistyped or "
                    "stale link shows the front page as though it had been asked for. The reader is left "
                    "to notice that the address in the bar is not the page in front of them. A line on "
                    "Home — 'there is no page at /o-no-such-page' — would cost nothing and keep the "
                    "fallback honest."
                ),
            )
        )


# -------------------------------------------------------------------------- a branch name


@pytest.mark.scenario(
    scenario_id="O03",
    group="O",
    title="A branch with no name is refused, and the modal stays open to be corrected",
    feature="Negative · branches · a missing name",
    expected=(
        "Pressing Create with the name empty, and again with only spaces, is refused with "
        "'A branch needs a name.'; the modal stays open and the header is still on main."
    ),
)
def test_branch_without_a_name(ui, record):
    feedback = _new_branch(ui, "")
    ui.check("the refusal is shown", bool(feedback), f"the feedback box read {feedback!r}")
    ui.check("and it says what is missing", "A branch needs a name." in feedback, feedback)
    ui.check("the modal stayed open so the name can be typed", ui.visible(BRANCH_MODAL))
    ui.check("the header is still on main", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.shot("Creating a branch with no name is refused, and the modal stays open to be corrected")

    ui.fill("branch-new-name", "   ")
    ui.click("branch-new-save")
    spaces = ui.text("branch-new-feedback")
    ui.check(
        "a name of nothing but spaces is refused the same way", "A branch needs a name." in spaces, spaces
    )
    ui.check("and still nothing was created", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.shot("A name of nothing but spaces is refused with the same sentence")
    _close_modal(ui, BRANCH_MODAL)


@pytest.mark.scenario(
    scenario_id="O04",
    group="O",
    title="A branch called 'main', and a name that is all punctuation, are both refused",
    feature="Negative · branches · an impossible name",
    expected=(
        "'main' is refused as the model itself rather than a branch; a name of only punctuation is "
        "refused too, and the refusal should say that the name cannot be made into an identifier."
    ),
)
def test_impossible_branch_names(ui, record, finding):
    feedback = _new_branch(ui, "main")
    ui.check("a branch called 'main' is refused", bool(feedback), f"the feedback box read {feedback!r}")
    ui.check(
        "and the refusal says main is not a branch",
        "main" in feedback.lower(),
        feedback,
    )
    ui.check("nothing was created", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.shot("A branch called 'main' is refused: main is the model, not a branch")

    ui.fill("branch-new-name", "###")
    ui.click("branch-new-save")
    punctuation = ui.text("branch-new-feedback")
    ui.check("a name of only punctuation is refused too", bool(punctuation), f"read {punctuation!r}")
    ui.check(
        "and the refusal says what is wrong with this name",
        "main" not in punctuation.lower(),
        f"the refusal for '###' reads {punctuation!r}",
    )
    ui.check("still nothing was created", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.shot("A name of nothing but punctuation is refused, but with the message written for 'main'")
    _close_modal(ui, BRANCH_MODAL)

    if "main" in punctuation.lower():
        finding.append(
            _finding(
                finding_id="O-3",
                where="src/ea/backend/branching.py · branch_id_from_name()",
                severity="usability",
                summary="A name that cannot become an identifier is refused with the message written for 'main'",
                detail=(
                    "branch_id_from_name() slugs the name, and raises 'a branch needs a name other than "
                    "main' both when the slug is 'main' and when it is empty. Asking for '###' therefore "
                    "answers a question nobody asked — the reader never typed 'main' — and says nothing "
                    "about what a branch name may contain. The two cases need two sentences, the second "
                    "naming the characters an identifier is made of."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="O05",
    group="O",
    title="A branch name already taken is refused, naming the branch that holds it",
    feature="Negative · branches · a duplicate name",
    expected=(
        f"Asking a second time for the branch '{BRANCH_NAME}' is refused with "
        f"'branch {BRANCH_ID} already exists', and no second branch appears in the list."
    ),
)
def test_duplicate_branch_name(ui, record):
    first = _new_branch(ui, BRANCH_NAME)
    ui.check(
        "the first attempt either created the branch or found it already there",
        not first or "already exists" in first,
        f"the feedback box read {first!r}",
    )
    _close_modal(ui, BRANCH_MODAL)

    ui.goto("/branches")
    listed_before = _page(ui).count(BRANCH_NAME)
    ui.must("the branch is in the list to be asked for a second time", listed_before >= 1, _brief(_page(ui)))

    second = _new_branch(ui, BRANCH_NAME)
    ui.check("the second attempt is refused", bool(second), f"the feedback box read {second!r}")
    ui.check("and the refusal names the branch that already holds the name", BRANCH_ID in second, second)
    ui.check("saying that it exists", "already exists" in second.lower(), second)
    ui.check("the modal stayed open so another name can be given", ui.visible(BRANCH_MODAL))
    ui.shot("Asking twice for the same branch name: the second is refused, naming the branch that holds it")
    _close_modal(ui, BRANCH_MODAL)

    ui.goto("/branches")
    ui.check(
        "no second branch of that name was written",
        _page(ui).count(BRANCH_NAME) == listed_before,
        f"{listed_before} before, {_page(ui).count(BRANCH_NAME)} after",
    )
    ui.shot("The Branches page still holds one branch of that name, not two")


# ------------------------------------------------------------------------ an element form


@pytest.mark.scenario(
    scenario_id="O06",
    group="O",
    title="A new element with no name is refused, and creating one afterwards still works",
    feature="Negative · browse · New element",
    expected=(
        "Create with nothing filled in, and again with a type but no name, is refused with 'Type and "
        "name are required.'; filling the name in then creates the element and opens it."
    ),
)
def test_new_element_needs_a_name(ui, record):
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element modal opened", ui.visible(NEW_MODAL))
    ui.click("new-save")
    empty = ui.text("new-feedback")
    ui.check("an empty form is refused", bool(empty), f"the feedback box read {empty!r}")
    ui.check("and the refusal names both fields", "Type and name are required." in empty, empty)
    ui.check("the modal stayed open", ui.visible(NEW_MODAL))
    ui.check("and nothing was opened in its place", "/browse" in ui.page.url, ui.page.url)
    ui.shot("Create with nothing filled in is refused, naming both fields it needs")

    _pick(ui, "new-type", PROBE_TYPE)
    ui.click("new-save")
    typed = ui.text("new-feedback")
    ui.check("a type with no name is refused too", "Type and name are required." in typed, typed)
    ui.shot("A type chosen but no name typed: refused with the same sentence")

    ui.fill("new-name", PROBE_NAME)
    ui.click("new-save")
    ui.page.wait_for_selector("#el-tabs", timeout=20_000)
    ui.settle()
    ui.check(
        "filling the name in creates the element and opens it",
        PROBE_NAME in _heading(ui),
        f"the page is headed {_heading(ui)!r}",
    )
    ui.check("the refusal was not a dead end", "/element/" in ui.page.url, ui.page.url)
    ui.shot("The same form, with a name typed in, creates the element and opens it")


@pytest.mark.scenario(
    scenario_id="O07",
    group="O",
    title="Clearing an element's name and saving is refused, and nothing is written",
    feature="Negative · element · Edit · a missing name",
    expected=(
        "Saving with the name cleared is refused with 'name is required'; the version does not move "
        "and the element still carries the name it had."
    ),
)
def test_element_save_without_a_name(ui, record):
    element_id = _probe_id(ui)
    ui.must("this group's element is in the model to be edited", bool(element_id), f"id {element_id!r}")
    ui.goto(f"/element/{element_id}")
    before = _version(ui)
    _tab(ui, "Edit")
    ui.fill("el-name", "")
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    ui.check("the save is refused", "Saved version" not in feedback, feedback)
    ui.check("and the refusal says a name is required", "name is required" in feedback, feedback)
    ui.check(
        "the refusal is shown beside the form rather than swallowed",
        ui.visible("el-save-feedback"),
        feedback,
    )
    ui.shot("Saving an element with its name cleared is refused, and says a name is required")

    ui.goto(f"/element/{element_id}")
    ui.check("the version did not move", _version(ui) == before, f"was v{before}, now v{_version(ui)}")
    ui.check(
        "and the element still carries the name it had",
        PROBE_NAME in _heading(ui),
        f"the page is headed {_heading(ui)!r}",
    )
    ui.shot("The element is untouched: the same version, and the name it had before the refused save")


# --------------------------------------------------------------------------- a bulk edit


@pytest.mark.scenario(
    scenario_id="O08",
    group="O",
    title="A bulk edit with no field set is refused, and the ticks are not lost",
    feature="Negative · browse · bulk edit",
    expected=(
        "Applying with every field empty says 'Fill in at least one field.', reports nothing updated, "
        "and leaves the modal open with the rows still ticked."
    ),
)
def test_bulk_edit_without_a_field(ui, record):
    ui.goto("/browse")
    ui.must("there are rows to tick", ui.grid_row_count(GRID) >= 2)
    ui.grid_tick(GRID, [0, 1])
    ui.click("bulk-open")
    ui.must("the bulk edit modal opened on the ticked rows", ui.visible(BULK_MODAL))
    ui.click("bulk-save")
    feedback = ui.text("bulk-feedback")
    ui.check("the save is refused", bool(feedback), f"the feedback box read {feedback!r}")
    ui.check("and the refusal says what to do", "Fill in at least one field." in feedback, feedback)
    ui.check("nothing is reported as updated", "Updated" not in feedback, feedback)
    ui.check("the modal stayed open so a field can be filled in", ui.visible(BULK_MODAL))
    ui.shot("A bulk edit with every field empty is refused, and says to fill one in")

    still_ticked = ui.page.locator(f"#{GRID} .ag-center-cols-container .ag-row[aria-selected='true']").count()
    ui.check(
        "the ticked rows are still ticked, so the refusal cost the reader nothing",
        still_ticked == 2,
        f"{still_ticked} rows are still ticked behind the modal",
    )
    ui.check(
        "and the grid behind it was not reloaded out from under them",
        ui.grid_row_count(GRID) >= 2,
        f"{ui.grid_row_count(GRID)} rows in the grid",
    )
    _close_modal(ui, BULK_MODAL)
    ui.shot("The two rows are still ticked after the refusal, ready for the field that was missing")


@pytest.mark.scenario(
    scenario_id="O09",
    group="O",
    title="Bulk edit pressed with nothing ticked says so, and says what to tick",
    feature="Negative · browse · bulk edit with no rows",
    expected=(
        "Pressing Bulk edit before any row is ticked opens and answers in words — nothing is "
        "ticked, and here is how to tick — rather than taking the click and doing nothing a "
        "reader can see."
    ),
)
def test_bulk_edit_without_a_tick(ui, record):
    # This scenario used to require the opposite, and that requirement was the finding: the
    # button was live, took the click, and did nothing visible, which reads as a broken page.
    ui.goto("/browse")
    ui.must(
        "nothing is ticked to begin with",
        ui.page.locator(f"#{GRID} .ag-center-cols-container .ag-row[aria-selected='true']").count() == 0,
    )
    ui.check("Bulk edit is offered to an Admin all the same", not ui.disabled("bulk-open"))
    ui.click("bulk-open")
    ui.page.wait_for_timeout(400)
    ui.must(
        "pressing it is answered rather than ignored",
        ui.page.locator(f"#{BULK_MODAL}").count() > 0,
        "the modal did not open and nothing was said",
    )
    said = ui.text("bulk-feedback")
    ui.check("it says nothing is ticked", "Nothing is ticked." in said, said or "(nothing said)")
    ui.check("and says what to tick instead", "tick the rows" in said, said or "(nothing said)")
    ui.check("and claims nothing was changed", "Updated" not in said, said)
    ui.shot("Bulk edit pressed with no row ticked says so, and says what to tick")
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(300)
    ui.settle()


@pytest.mark.scenario(
    scenario_id="O10",
    group="O",
    title="A CSV whose every row is defective loads nothing, and says so row by row",
    feature="Negative · import · a broken file",
    expected=(
        "Loading files with an unknown type, a nameless row, a row with no id and an edge into nowhere "
        "writes nothing: the report counts four errors, 0 of 3 elements loaded, and the ids are not in "
        "the model afterwards."
    ),
)
def test_broken_csv_loads_nothing(ui, record, finding):
    ui.goto("/import")
    ui.must("the Import page rendered its upload zone", ui.visible("im-upload"))
    _upload(
        ui,
        _write(ui, "o-broken-elements.csv", BROKEN_ELEMENTS_CSV),
        _write(ui, "o-broken-relationships.csv", BROKEN_RELATIONSHIPS_CSV),
    )
    ui.fill("im-source", "o-negative-round")
    ui.click("im-validate")
    checked = ui.text("im-report")
    ui.check("checking writes nothing", "Validation only — nothing written." in checked, _brief(checked))
    ui.check("and counts every defect", "4 errors" in checked, _brief(checked))
    ui.shot("Validate only on a wholly broken pair of files: four errors, nothing written")

    ui.click("im-load")
    loaded = ui.text("im-report")
    ui.check("no element was loaded", "elements 0/3 loaded (3 skipped)" in loaded, _brief(loaded))
    ui.check("no relationship was loaded", "relationships 0/1 loaded (1 skipped)" in loaded, _brief(loaded))
    for code in ("unknown_type", "missing_name", "missing_id", "dangling_relationship"):
        ui.check(f"the {code} defect is named by its code", code in loaded, _brief(loaded, 600))
    ui.check(
        "each defect says which file and which row it came from",
        "o-broken-elements.csv" in loaded and "o-broken-relationships.csv" in loaded,
        _brief(loaded, 600),
    )
    ui.check(
        "the report says how many rows it refused",
        "3 skipped" in loaded and "1 skipped" in loaded,
        _brief(loaded),
    )
    ui.shot("Load on the same files: nothing written, and every defect named with its file and row")

    ui.goto("/element/O-BROKEN-TYPE")
    ui.check("the row with the unknown type is not in the model", _heading(ui) == "Not found", _heading(ui))
    ui.goto("/element/O-BROKEN-NAME")
    ui.check("nor is the row with no name", _heading(ui) == "Not found", _heading(ui))
    ui.shot("Neither identifier reached the model: the element page says Not found for both")

    if re.match(r"^Loaded\.", loaded.strip()):
        finding.append(
            _finding(
                finding_id="O-5",
                where="src/ea/ui/pages/import_page.py · _run(), the head of the report",
                severity="usability",
                summary="A load that wrote nothing still announces itself as 'Loaded.'",
                detail=(
                    "_run() writes 'Loaded. ' in front of the summary whenever dry_run is false, whatever "
                    "the counts behind it are. A file in which every row was refused therefore opens with "
                    "the word the reader is looking for, and the '0/3 loaded' that contradicts it sits in "
                    "the middle of a long sentence. The head should read from the counts: 'Nothing "
                    "loaded: 3 rows refused' when nothing was written."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="O11",
    group="O",
    title="A file that is not the shape it claims is refused, not re-read as something else",
    feature="Negative · import · a file that is not the shape it claims",
    expected=(
        "A file whose one data row carries more fields than its header declares is not the file its "
        "author wrote. It is refused and named, nothing of it is loaded, and neither the row it "
        "declares nor the row assembled from the tail of the same line reaches the model."
    ),
    branch=BRANCH_ID,
)
def test_ragged_csv_is_refused(ui, record):
    # The finding this scenario was written for: the parser folded the surplus away and the
    # file loaded without a word, under an identifier it never declared.
    ui.goto("/import")
    ui.must("the Import page rendered its upload zone", ui.visible("im-upload"))
    _upload(ui, _write(ui, "o-ragged-elements.csv", RAGGED_CSV))
    ui.check("the file was taken", "o-ragged-elements.csv" in ui.text("im-files"), ui.text("im-files"))
    ui.click("im-validate")
    report = ui.text("im-report")
    ui.must("the check ran and reported something", bool(report.strip()), "the report area stayed empty")
    ui.check("the file is reported as a problem", "Not read" in report, _brief(report))
    ui.check(
        "and it is named, so the reader knows which file to look at",
        "o-ragged-elements.csv" in report,
        _brief(report),
    )
    ui.check(
        "and the report says what is wrong with it",
        "header" in report.lower(),
        _brief(report),
    )
    ui.shot("A row with more fields than its header declares is refused, and the file is named")

    # Staged onto this group's branch, never onto main: if a load did write something, it
    # must not reach the model the other groups are reading.
    _pick(ui, "branch-select", BRANCH_NAME)
    ui.must(
        "the header left main for this group's branch",
        ui.branch_badge().strip().lower() != "main",
        f"the branch badge reads {ui.branch_badge()!r}",
    )
    ui.goto("/import")
    ui.must(
        "and the Import page says the load will be staged on it",
        f"You are on branch {BRANCH_ID}:" in _page(ui),
        _brief(_page(ui)),
    )
    _upload(ui, _write(ui, "o-ragged-elements.csv", RAGGED_CSV))
    ui.click("im-load")
    loaded = ui.text("im-report")
    ui.check(
        "loading it writes nothing", "elements 0/0 loaded" in loaded or "Not read" in loaded, _brief(loaded)
    )
    ui.shot("The same file, pressed through Load: still refused, and nothing written")

    for element_id, what in (
        (RAGGED_DECLARED, "the row the file declares"),
        (RAGGED_GHOST, "the row its tail would make"),
    ):
        ui.goto(f"/element/{element_id}")
        heading = _heading(ui)
        ui.check(f"{what} did not reach the model", heading == "Not found", f"{element_id} is {heading!r}")
    ui.shot("Neither identifier reached the branch: a file that cannot be read is not half-read")


@pytest.mark.scenario(
    scenario_id="O12",
    group="O",
    title="A proposal too thin to apply is pushed back, and Apply writes nothing at all",
    feature="Negative · propose · pushback",
    expected=(
        "A proposal with an unknown type, a row with no description, an existing id that is nowhere and "
        "an edge into nowhere comes back as pushback naming each; Apply refuses, and neither the branch "
        "it asked for nor any of the elements is written."
    ),
)
def test_thin_proposal_is_not_half_applied(ui, record):
    ui.goto("/propose")
    ui.must("the Propose page rendered its proposal box", ui.page.locator(PASTE).count() > 0)
    box = ui.page.locator(PASTE).first
    box.click()
    box.fill(PROPOSAL)
    ui.settle()
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    ui.settle()

    pushback = ui.text("pr-pushback")
    ui.check(
        "the change set is marked as not enough to apply",
        "Not enough to apply" in pushback,
        _brief(pushback, 400),
    )
    ui.check(
        "the unknown type is named, with the words that were not recognised",
        "Nonexistent Type" in pushback and "not in the metamodel" in pushback,
        _brief(pushback, 400),
    )
    ui.check(
        "the row with no description is named",
        "description is missing" in pushback,
        _brief(pushback, 400),
    )
    ui.check(
        "the existing id that is nowhere is named",
        "O-NO-SUCH-ID" in pushback and "not in the repository" in pushback,
        _brief(pushback, 400),
    )
    ui.check(
        "and the edge whose target is nowhere is named",
        "O Missing Element" in pushback,
        _brief(pushback, 400),
    )
    ui.check(
        "each line says which row it is about",
        "Element row" in pushback and "Relationship row" in pushback,
        _brief(pushback, 400),
    )
    ui.shot("The pushback on a thin proposal: one line per defect, each naming its row")

    _pick(ui, "pr-branch", "New branch")
    ui.fill("pr-branch-new", REFUSED_BRANCH)
    ui.click("pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.check("Apply is refused", "Not applied" in feedback, f"the feedback read {feedback!r}")
    ui.check("and says where to look for the reason", "see what is missing above" in feedback, feedback)
    ui.check(
        "nothing is reported as created",
        "Applied to branch" not in ui.text("pr-result"),
        _brief(ui.text("pr-result")),
    )
    ui.shot("Apply refused: the change set is not enough, and nothing is claimed to have been written")

    ui.goto("/branches")
    ui.check(
        "the branch the refusal asked for was never created",
        REFUSED_BRANCH_ID not in _page(ui) and REFUSED_BRANCH not in _page(ui),
        _brief(_page(ui), 400),
    )
    ui.shot("The Branches page: no branch was created for the proposal that was refused")

    for name in ("O Nowhere Service", "O Undescribed Record", "O Ghost Reference"):
        ui.goto(f"/browse?q={name.replace(' ', '+')}")
        ui.check(
            f"no element was written for {name!r}",
            ui.grid_row_count(GRID) == 0,
            f"{ui.grid_row_count(GRID)} rows match {name!r}",
        )
    ui.shot("Browse holds none of the proposal's elements: the refusal wrote nothing at all")


# ------------------------------------------------- what the router could not place, in words

UNKNOWN_PATH = "/o-no-such-page"
SURPLUS_PATH = "/browse/o-surplus-segment"


def _page_alerts(ui) -> list[str]:
    """Every alert the page itself is showing, the header and the navigation excluded."""
    return [t.strip() for t in ui.page.locator("#page .mantine-Alert-root").all_inner_texts()]


def _alert_saying(ui, fragment: str):
    return ui.page.locator("#page .mantine-Alert-root").filter(has_text=re.compile(re.escape(fragment))).first


def _alert_colour(ui, fragment: str) -> str:
    """The colour Mantine painted an alert, read back from the element rather than assumed."""
    painted = ui.page.evaluate(
        """(text) => {
            const found = Array.from(document.querySelectorAll('#page .mantine-Alert-root'))
                .find(el => (el.textContent || '').includes(text));
            if (!found) { return ''; }
            const style = getComputedStyle(found);
            return (style.getPropertyValue('--alert-bg') || style.backgroundColor || '').trim();
        }""",
        fragment,
    )
    for name in ("yellow", "red", "green", "blue"):
        if name in painted:
            return name
    channels = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", painted)
    if not channels:
        return painted or "no colour"
    r, g, b = (int(channels.group(i)) for i in (1, 2, 3))
    if r > 200 and g > 140 and b < 120:
        return f"yellow ({painted})"
    return painted or "no colour"


def _top(ui, selector: str) -> float:
    box = ui.page.locator(selector).first.bounding_box() or {}
    return float(box.get("y", -1))


@pytest.mark.scenario(
    scenario_id="O13",
    group="O",
    title="The address the router cannot place is named on the page it falls back to",
    feature="Negative · routing · what the reader is told",
    expected=(
        f"{UNKNOWN_PATH} renders Home under a warning that quotes the address, says there is no page "
        "there and says which page is being shown instead; the front door itself carries no such warning."
    ),
)
def test_unknown_route_names_the_address(ui, record, finding):
    ui.goto(UNKNOWN_PATH)
    body = _page(ui)
    ui.must(
        "the fallback says something about the address",
        _alert_saying(ui, "no page").count() > 0,
        f"the alerts on the page read {_page_alerts(ui) or 'nothing'}",
    )
    said = _alert_saying(ui, "no page").inner_text().strip()
    ui.check("the warning quotes the address that does not exist", UNKNOWN_PATH in said, said)
    ui.check("and says there is no page at it", "no page at" in said.lower(), said)
    ui.check("and says which page is being shown instead", "home page" in said.lower(), said)
    ui.check(
        "the warning is painted as a warning rather than as an error",
        "yellow" in _alert_colour(ui, "no page"),
        _alert_colour(ui, "no page"),
    )
    ui.check("Home is rendered under it", "Higher Education EA Metamodel" in _heading(ui), _heading(ui))
    ui.check(
        "and the warning comes first, so it is read before the page it fell back to",
        0 <= _top(ui, "#page .mantine-Alert-root") < _top(ui, "#page h1"),
        f"the alert at y={_top(ui, '#page .mantine-Alert-root')}, the title at y={_top(ui, '#page h1')}",
    )
    ui.check("nothing reports a crash", "This page failed to render" not in body, _brief(body))
    ui.shot("An address the router cannot place: Home, under a warning that quotes the address")

    ui.goto("/element")
    half = _alert_saying(ui, "no page")
    ui.check(
        "a half-written /element is named the same way rather than answered in silence",
        half.count() > 0 and "/element" in half.inner_text(),
        (half.inner_text().strip() if half.count() else "") or f"alerts: {_page_alerts(ui) or 'none'}",
    )
    ui.shot("An /element address with no identifier is named in the same words")

    ui.goto("/")
    ui.check(
        "the front door carries no such warning, so the warning means something",
        not any("no page at" in a.lower() for a in _page_alerts(ui)),
        f"the alerts on Home read {_page_alerts(ui) or 'nothing'}",
    )
    ui.check("and Home is Home", "Higher Education EA Metamodel" in _heading(ui), _heading(ui))
    ui.shot("The front door itself: Home, and no warning about the address")

    ui.goto(SURPLUS_PATH)
    ui.check(
        "a page that exists, asked for with a segment after it, still renders that page",
        "Browse" in _heading(ui),
        _heading(ui),
    )
    ui.check("and not an error", "This page failed to render" not in _page(ui), _brief(_page(ui)))
    swallowed = not any("no page at" in a.lower() for a in _page_alerts(ui))
    ui.shot("An address under a page that exists, with a segment the router ignored")
    if swallowed:
        finding.append(
            _finding(
                finding_id="O-6",
                where="src/ea/ui/app.py · parse_path(), the branch that keeps only the first segment",
                severity="usability",
                summary="A surplus segment after a page that exists is dropped without the word an unknown address gets",
                detail=(
                    f"parse_path() reads parts[0], so {SURPLUS_PATH} renders Browse and the rest of the "
                    "address means nothing. An address the router cannot place at all now says so — "
                    f"'There is no page at {UNKNOWN_PATH}' — but one it can half-place says nothing, so "
                    "the reader who mistyped a page's own address is the only one left to notice it. The "
                    "same line, naming the address, would cover both."
                ),
            )
        )


# ------------------------------------------------------------------- a relationship with one end


@pytest.mark.scenario(
    scenario_id="O14",
    group="O",
    title="Add with no pair chosen is refused, and no relationship is written",
    feature="Negative · element · Relationships · a missing end",
    expected=(
        "Pressing Add with neither end chosen, and again with the other element chosen but no "
        "relationship, is refused with 'Choose the other element and a relationship.'; the count in the "
        "tab label does not move and the tables still say None."
    ),
)
def test_relationship_add_without_a_pair(ui, record):
    element_id = _probe_id(ui)
    ui.must("this group's element is in the model", bool(element_id), f"id {element_id!r}")
    ui.goto(f"/element/{element_id}")
    _tab(ui, "Relationships")
    ui.must("the Relationships tab is showing its form", ui.visible("el-rel-add"))
    label_before = ui.text("el-rel-count")
    tables_before = ui.text("el-rel-tables")

    ui.click("el-rel-add")
    empty = ui.text("el-rel-feedback")
    ui.check("Add with nothing chosen is refused", bool(empty), f"the feedback box read {empty!r}")
    ui.check(
        "and the refusal names both ends", "Choose the other element and a relationship." in empty, empty
    )
    ui.check("the refusal is shown beside the form", ui.visible("el-rel-feedback"), empty)
    ui.check(
        "the count in the tab label did not move",
        ui.text("el-rel-count") == label_before,
        f"the tab read {label_before!r}, now {ui.text('el-rel-count')!r}",
    )
    ui.shot("Add pressed with neither end chosen: refused, naming what is missing")

    ui.click("el-rel-other")
    ui.page.locator("[role='option']:visible").first.click()
    ui.settle()
    chosen = ui.page.locator("#el-rel-other").first.input_value()
    ui.must("an element was chosen at the other end", bool(chosen.strip()), f"the box reads {chosen!r}")
    ui.click("el-rel-add")
    half = ui.text("el-rel-feedback")
    ui.check(
        "one end without a relationship is refused the same way",
        "Choose the other element and a relationship." in half,
        f"with {chosen!r} chosen the feedback read {half!r}",
    )
    ui.check("nothing says a relationship was added", "Relationship added." not in half, half)
    ui.check(
        "the count in the tab label still did not move",
        ui.text("el-rel-count") == label_before,
        f"the tab read {label_before!r}, now {ui.text('el-rel-count')!r}",
    )
    ui.check(
        "and the tables behind the form are as they were",
        ui.text("el-rel-tables") == tables_before,
        _brief(ui.text("el-rel-tables")),
    )
    ui.shot("The other element chosen but no relationship: refused with the same sentence")

    ui.goto(f"/element/{element_id}")
    _tab(ui, "Relationships")
    ui.check(
        "and nothing was written: the reloaded page counts what it counted before",
        ui.text("el-rel-count") == label_before,
        f"the tab read {label_before!r}, now {ui.text('el-rel-count')!r}",
    )
    ui.check(
        "with the same tables under it",
        ui.text("el-rel-tables") == tables_before,
        _brief(ui.text("el-rel-tables")),
    )
    ui.shot("The element reloaded: the two refusals wrote nothing")


# ------------------------------------------------------------------ a file with nothing in it

EMPTY_CSV = ""  # a file the reader believes holds their export, and which holds nothing
HEADER_ONLY_CSV = "id,type,name,description\n"  # the header alone: a file that declares no rows


def _server_log(ui, needle: str) -> str:
    """What the server wrote about the last request, when it wrote anything at all."""
    try:
        text = (ui.run_dir / "server.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line for line in text.splitlines() if needle in line]
    return lines[-1][:160] if lines else ""


@pytest.mark.scenario(
    scenario_id="O15",
    group="O",
    title="A file with nothing in it is refused and named, not answered with silence",
    feature="Negative · import · an empty file",
    expected=(
        "Validating a CSV that holds no bytes at all reports the file by name and says it could not be "
        "read, the way a file whose rows do not match its header is reported; a file that holds its "
        "header and no rows loads nothing and says so."
    ),
)
def test_empty_csv_is_refused(ui, record):
    ui.goto("/import")
    ui.must("the Import page rendered its upload zone", ui.visible("im-upload"))
    _upload(ui, _write(ui, "o-empty-elements.csv", EMPTY_CSV))
    listed = ui.text("im-files")
    ui.check("the file is listed", "o-empty-elements.csv" in listed, listed)
    ui.check("and counted as holding no rows before anything is pressed", "0 rows" in listed, listed)
    ui.fill("im-source", "o-negative-round")

    ui.click("im-validate")
    report = ui.text("im-report")
    crashed = _server_log(ui, "EmptyDataError")
    ui.check(
        "the check answers at all",
        bool(report.strip()),
        f"the report area stayed empty; the server log says: {crashed or '(nothing about it)'}",
    )
    ui.check(
        "and the answer names the file that could not be read",
        "o-empty-elements.csv" in report,
        _brief(report) or "(the report area is empty)",
    )
    ui.check(
        "nothing claims the file was read and found clean",
        "Validation only — nothing written." not in report or "o-empty-elements.csv" in report,
        _brief(report) or "(the report area is empty)",
    )
    ui.shot("Validate on a file that holds no bytes at all")

    ui.click("im-load")
    loaded = ui.text("im-report")
    ui.check(
        "pressing Load on it is answered too",
        bool(loaded.strip()),
        f"the report area stayed empty; the server log says: {_server_log(ui, 'EmptyDataError') or '(nothing)'}",
    )
    ui.check("and nothing says it was loaded", not loaded.strip().startswith("Loaded."), _brief(loaded))
    ui.shot("Load on the same empty file: what the reader is told")

    # A file that holds its header and no rows is a different thing: readable, and empty.
    ui.goto("/import")
    _upload(ui, _write(ui, "o-header-only-elements.csv", HEADER_ONLY_CSV))
    ui.fill("im-source", "o-negative-round")
    ui.click("im-validate")
    checked = ui.text("im-report")
    ui.check(
        "a header with no rows under it is read",
        "Validation only — nothing written." in checked,
        _brief(checked),
    )
    ui.check("and counted as the nothing it is", "checked elements 0" in checked, _brief(checked))
    ui.check("with nothing to report as an issue", "Issues (0)" in checked, _brief(checked))
    ui.shot("A file holding its header and no rows: read, and counted as empty")

    ui.click("im-load")
    empty_load = ui.text("im-report")
    ui.check(
        "loading it does not announce itself as a load",
        not empty_load.strip().startswith("Loaded."),
        _brief(empty_load),
    )
    ui.check(
        "and says in its first words that nothing was written",
        empty_load.strip().startswith("Nothing was loaded."),
        _brief(empty_load),
    )
    ui.check("counting what it wrote as nothing", "elements 0/0 loaded" in empty_load, _brief(empty_load))
    ui.shot("Load on a file with no rows: 'Nothing was loaded.', which is what happened")


# ---------------------------------------------------------------- a type the pack does not hold

UNKNOWN_TYPE = "o_not_a_real_type"


@pytest.mark.scenario(
    scenario_id="O16",
    group="O",
    title="An address filtering on a type the pack does not hold shows nothing, not everything",
    feature="Negative · browse · a type in the address",
    expected=(
        f"/browse?type={UNKNOWN_TYPE} keeps the filter it was given rather than dropping it: the grid "
        "holds no rows and the count says so; the type box can then be put back to All types and the "
        "model returns."
    ),
)
def test_browse_type_that_the_pack_does_not_hold(ui, record, finding):
    ui.goto("/browse")
    whole = ui.grid_row_count(GRID)
    ui.must("the model is in the grid to begin with", whole > 0, f"{whole} rows")

    ui.goto(f"/browse?type={UNKNOWN_TYPE}")
    ui.must("the page rendered its grid all the same", ui.visible(GRID), _brief(_page(ui)))
    rows = ui.grid_row_count(GRID)
    count = ui.text("browse-count")
    ui.check("nothing reports a crash", "This page failed to render" not in _page(ui), _brief(_page(ui)))
    ui.check(
        "the address was not quietly dropped: the whole model is not shown as though nothing was asked",
        rows < whole,
        f"{rows} rows against {whole} in the unfiltered grid",
    )
    ui.check("no row matches a type the pack does not hold", rows == 0, f"{rows} rows")
    ui.check("and the count says so rather than counting something else", count == "0 of 0", count)
    ui.shot("An address naming a type the pack does not hold: an empty grid, counted as empty")

    box = ui.page.locator("#browse-type").first.input_value()
    names_it = UNKNOWN_TYPE in _page(ui) or bool(re.search(r"unknown|no such type", _page(ui), re.I))
    _pick(ui, "browse-type", "All types")
    back = ui.grid_row_count(GRID)
    ui.check(
        "the reader is not stuck: All types brings the model back",
        back > 0,
        f"{back} rows after clearing the filter",
    )
    ui.shot("The same page with the type filter put back to All types: the model returns")
    if not names_it:
        finding.append(
            _finding(
                finding_id="O-7",
                where="src/ea/ui/pages/browse.py · render(), the ?type= parameter",
                severity="usability",
                summary="A type in the address that the pack does not hold empties the grid without a word",
                detail=(
                    f"render() passes the ?type= straight into the filter, so /browse?type={UNKNOWN_TYPE} "
                    f"counts '0 of 0' and shows nothing, while the type box reads {box!r} because the "
                    "value matches no option. A stale bookmark, or a link to a type since renamed in the "
                    "pack, therefore reads as a repository with nothing in it. The Impact page refuses an "
                    "element it does not hold out loud ('Unknown element.'); Browse should say the same "
                    "about a type rather than answer with an empty model."
                ),
            )
        )


# ------------------------------------------------- a branch name the proposal cannot be applied to

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "proposal-template.md"
WP_LABEL = "Curriculum Management System Upgrade"  # the sample model's one work package
IMPOSSIBLE_BRANCH = "###"  # a name with nothing in it an identifier can be made of


@pytest.mark.scenario(
    scenario_id="O17",
    group="O",
    title="A proposal ready to apply, aimed at a branch that cannot be named, is refused and kept",
    feature="Negative · propose · an impossible branch name",
    expected=(
        "A change set with no pushback, applied to a new branch called '###', is refused with what is "
        "wrong with the name; the change set is still on screen afterwards and no branch was created."
    ),
)
def test_apply_to_a_branch_that_cannot_be_named(ui, record):
    ui.goto("/branches")
    branches_before = ui.page.locator("#br-list tbody tr").count()
    ui.must("the branch list can be counted", branches_before >= 0, f"{branches_before} rows")

    ui.goto("/propose")
    ui.must("the Propose page rendered its proposal box", ui.page.locator(PASTE).count() > 0)
    ui.select("pr-wp", WP_LABEL)
    box = ui.page.locator(PASTE).first
    box.click()
    box.fill(TEMPLATE_PATH.read_text(encoding="utf-8"))
    ui.settle()
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    ui.settle()
    pushback = ui.text("pr-pushback")
    ui.must(
        "the change set is ready to apply, so what is refused next is the branch and nothing else",
        "Not enough to apply" not in pushback,
        _brief(pushback, 400),
    )
    rows_before = ui.grid_row_count("pr-el-grid")
    ui.must("the change set holds rows", rows_before > 0, f"{rows_before} element rows")

    _pick(ui, "pr-branch", "New branch")
    ui.fill("pr-branch-new", IMPOSSIBLE_BRANCH)
    ui.click("pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.check("the apply is refused", "Not applied" in feedback, f"the feedback read {feedback!r}")
    ui.check(
        "and the refusal says what is wrong with the name that was typed",
        "name" in feedback.lower() and "main" not in feedback.lower(),
        feedback,
    )
    ui.check(
        "naming what a branch identifier is made of",
        bool(re.search(r"letter|number|character", feedback, re.I)),
        feedback,
    )
    ui.check("nothing says it was applied", "Applied to branch" not in ui.text("pr-result"), feedback)
    ui.shot("A change set aimed at a branch called '###': refused, in the branch's own words")

    ui.check(
        "the change set survived the refusal, so the reader's work is not lost",
        ui.grid_row_count("pr-el-grid") == rows_before,
        f"{ui.grid_row_count('pr-el-grid')} rows now, {rows_before} before",
    )
    ui.check(
        "and the name that was refused is still in the box to be corrected",
        ui.page.locator("#pr-branch-new").first.input_value() == IMPOSSIBLE_BRANCH,
        ui.page.locator("#pr-branch-new").first.input_value(),
    )
    ui.shot("The change set is still on screen behind the refusal, with the name to be corrected")

    ui.goto("/branches")
    listed = _page(ui)
    ui.check(
        "no branch was created for the proposal",
        ui.page.locator("#br-list tbody tr").count() == branches_before,
        f"{ui.page.locator('#br-list tbody tr').count()} branches now, {branches_before} before",
    )
    ui.check(
        "and nothing in the list carries the name that was refused",
        IMPOSSIBLE_BRANCH not in listed,
        _brief(listed, 400),
    )
    ui.shot("The Branches page after the refusal: the same branches, and none of them nameless")


# ------------------------------------------------------------------- a link that is not a link


def _links_published(ui) -> list[tuple[str, str]]:
    """Every link the page offers that leaves the application's own addresses behind."""
    pairs = ui.page.evaluate(
        """() => Array.from(document.querySelectorAll('#page a'))
            .map(a => [(a.textContent || '').trim(), a.getAttribute('href') || ''])"""
    )
    return [(text, href) for text, href in pairs if not href.startswith("/")]


SCRIPT_LINK = "javascript:alert('o-negative')"
NOT_A_URL = "o-not-a-url-at-all"
BAD_LINKS = f"{SCRIPT_LINK} | Looks like a document\n{NOT_A_URL} | A line that is not an address\n"


@pytest.mark.scenario(
    scenario_id="O18",
    group="O",
    title="A links box takes anything, and what it takes is published as a link",
    feature="Negative · element · Edit · the links box",
    expected=(
        "Saving a links box holding a javascript: line and a line that is no address at all is refused, "
        "or at the very least neither line is published as something the reader can click; nothing on "
        "the page may carry a javascript: address."
    ),
)
def test_links_that_are_not_addresses(ui, record, finding):
    element_id = _probe_id(ui)
    ui.must("this group's element is in the model", bool(element_id), f"id {element_id!r}")
    ui.goto(f"/element/{element_id}")
    _tab(ui, "Edit")
    before = ui.page.locator("#el-links").first.input_value()
    ui.fill("el-links", BAD_LINKS)
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    refused = "Saved version" not in feedback
    ui.check(
        "the save either refuses the two lines or reports what it wrote",
        bool(feedback),
        f"the feedback box read {feedback!r}",
    )
    ui.shot("Two lines that are not addresses, handed to the links box and saved")

    ui.goto(f"/element/{element_id}")
    published = _links_published(ui)
    scripted = [pair for pair in published if pair[1].strip().lower().startswith("javascript:")]
    into_the_app = [pair for pair in published if NOT_A_URL in pair[1]]
    ui.check(
        "no link the page publishes runs a script instead of going somewhere",
        not scripted,
        f"the page publishes {published or 'no link of its own'}",
    )
    ui.check(
        "and the line that is no address at all is not published as a link either",
        refused or not into_the_app,
        f"the page publishes {published or 'no link of its own'}",
    )
    ui.check(
        "a refusal, if that is what happened, says which line it is about",
        (not refused) or SCRIPT_LINK in feedback or "link" in feedback.lower(),
        feedback,
    )
    ui.shot("What the element page publishes after the links box was given two lines that are not addresses")

    _tab(ui, "Edit")
    kept = ui.page.locator("#el-links").first.input_value()
    ui.check(
        "and the model did not keep a line the browser had to neutralise before drawing it",
        refused or SCRIPT_LINK not in kept,
        f"the links box reads {kept!r}",
    )
    ui.shot("The links the model kept, read back in the box they were typed into")

    if scripted or into_the_app or (not refused and SCRIPT_LINK in kept):
        finding.append(
            _finding(
                finding_id="O-8",
                where="src/ea/ui/pages/element.py · _parse_links(), and the anchors the Overview draws from it",
                severity="defect",
                summary="The links box takes any line as an address, and publishes what it took as a link",
                detail=(
                    "_parse_links() splits each line on '|' and keeps whatever is on the left as the url. "
                    "Nothing between the box and the browser looks at it: update_element does not, "
                    "set_links does not, and the Overview draws every one of them as dmc.Anchor(href=…) "
                    f"with target='_blank'. Saving {SCRIPT_LINK!r} and {NOT_A_URL!r} was accepted with "
                    f"{feedback!r}; the box reads {kept!r} on the way back, so the store kept both lines "
                    f"verbatim, and the element page published {published} — the scheme survives in the "
                    "model and only Chromium's own refusal to follow it turned the first into about:blank, "
                    "which the Markdown and draw.io exports of the same row have no reason to repeat. A "
                    "line that is no "
                    "address at all becomes a link into the application itself, which lands the reader on "
                    "the front page for no reason they can see; a line carrying a scheme the page never "
                    "meant to offer is stored just as willingly, on a field an import and a proposal can "
                    "write as easily as a person. The box should take http(s) and mailto, and name the "
                    "line it refuses, the way every other field on this page refuses what it cannot use."
                ),
            )
        )

    # Whatever the page did with them, the element goes back to the links it had.
    ui.goto(f"/element/{element_id}")
    _tab(ui, "Edit")
    ui.fill("el-links", before)
    ui.click("el-save")
    restored = ui.text("el-save-feedback")
    ui.check(
        "and the element is put back the way it was found",
        ("Saved version" in restored) or refused,
        restored,
    )
    ui.goto(f"/element/{element_id}")
    left = _links_published(ui)
    ui.check(
        "with none of the two lines left on it",
        not [
            pair for pair in left if NOT_A_URL in pair[1] or pair[1].strip().lower().startswith("javascript:")
        ],
        f"the page publishes {left or 'no link of its own'}",
    )
    ui.shot("The element with its links put back the way the group found them")
