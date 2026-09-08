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
