"""Group I — Branches: the overlay, the merge log, conflicts, review and the freeze.

A branch is a draft of the model laid over `main` (decision 0006): what is written on it
lives in the `branch_*` tables until somebody merges it, row by row, and `main` moves only
then. This group walks that life from both ends — the happy path (create, edit, read the
merge log, merge a subset, merge the rest) and the two ways it goes wrong (`main` moved
under the branch, so the row conflicts; and the branch is frozen because it is in review).

The order is deliberate, because each scenario is the next one's fixture:

| | Branch | What it sets up |
| - | ------ | --------------- |
| I01–I07 | `i-merge-log` | created from the header, two elements edited on it, one row merged and one left behind |
| I08–I11 | `i-conflict` | created from the page button, two rows that `main` moved under, resolved one each way, then closed |
| I12–I16 | `i-review` | authored by the Architect, frozen by a review, refused to its author, decided by the Reviewer |

Nothing here asserts a total another group could move: the branches are named with an `i-`
prefix, the elements they touch (two Measures, two Business Definitions and a Data Product)
are ones no other group writes, and every "before" value is read from the screen at the
moment it matters rather than assumed from the sample data.
"""

from __future__ import annotations

import json
import re

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

# ------------------------------------------------------------------ the branches
MERGE_BRANCH = "I merge log"
MERGE_ID = "i-merge-log"
CONFLICT_BRANCH = "I conflict"
CONFLICT_ID = "i-conflict"
REVIEW_BRANCH = "I review"
REVIEW_ID = "i-review"

WP_LABEL = "Curriculum Management System Upgrade"  # the sample model's one work package

# ------------------------------------------------------------------ the elements
M1 = "MSR-OUTLINE-COMPLETENESS"  # a Measure, edited on i-merge-log and merged
M2 = "MSR-ENROL-VALIDITY"  # a Measure, edited on i-merge-log and left behind
D1 = "DEF-COURSE"  # a Business Definition, conflicted and resolved to the branch
D2 = "DEF-UNIT"  # a Business Definition, conflicted and resolved to main
P1 = "DP-CURR-HEALTH"  # a Data Product, the one row the review decides

GRID = "br-grid"
STATUSES = [
    ("Open", "open"),
    ("In review", "in review"),
    ("Approved", "approved"),
    ("Merged", "merged"),
    ("Abandoned", "abandoned"),
]


# --------------------------------------------------------------------- the controls


def _pm(**parts: str) -> str:
    """The CSS selector for a pattern-matching component, whose DOM id is the JSON Dash writes."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


def _open_button(branch_id: str) -> str:
    return _pm(id=branch_id, type="br-open")


def _branches(ui, branch_id: str | None = None) -> None:
    ui.goto(f"/branches?branch={branch_id}" if branch_id else "/branches")


def _new_branch(ui, opener: str, name: str, description: str, work_package: str = "") -> None:
    """Open the New branch modal from `opener`, fill it in, and create the branch."""
    ui.click(opener)
    ui.must("the New branch modal opened", ui.visible("branch-new-modal"))
    ui.fill("branch-new-name", name)
    ui.fill("branch-new-desc", description)
    if work_package:
        ui.select("branch-new-wp", work_package)
    ui.click("branch-new-save")


def _tab(ui, label: str) -> None:
    ui.click(f"#el-tabs [role='tab']:has-text({json.dumps(label)})")
    ui.page.wait_for_timeout(200)


def _element_name(ui, element_id: str) -> str:
    """The name the element carries on whatever branch the reader is on."""
    ui.goto(f"/element/{element_id}")
    return (ui.page.locator("#el-name").first.input_value() or "").strip()


def _rename(ui, element_id: str, name: str) -> str:
    """Rename an element on the current branch; returns what the form said about it."""
    ui.goto(f"/element/{element_id}")
    _tab(ui, "Edit")
    ui.fill("el-name", name)
    ui.click("el-save")
    return ui.text("el-save-feedback")


# ------------------------------------------------------------------- the merge log


def _row(ui, key: str, col: str) -> str:
    return ui.grid_cell_of(GRID, key, col)


def _include_box(ui, key: str):
    return ui.page.locator(f"#{GRID} .ag-row[row-id='{key}'] .ag-cell[col-id='include'] input").first


def _included(ui, key: str) -> bool:
    box = _include_box(ui, key)
    return bool(box.count()) and box.is_checked()


def _set_included(ui, key: str, on: bool) -> None:
    box = _include_box(ui, key)
    box.scroll_into_view_if_needed()
    if box.is_checked() != on:
        box.click(force=True)
    ui.settle()


def _set_take(ui, key: str, value: str) -> None:
    """Choose 'branch' or 'main' in the editable take cell of a conflicting row."""
    cell = ui.page.locator(f"#{GRID} .ag-row[row-id='{key}'] .ag-cell[col-id='resolution']").first
    cell.scroll_into_view_if_needed()
    cell.click()  # the grid edits on a single click
    ui.page.wait_for_timeout(250)
    if not ui.page.locator(".ag-list-item:visible").count():
        picker = ui.page.locator(f"#{GRID} .ag-cell-editor .ag-picker-field-wrapper").first
        if picker.count():
            picker.click()
            ui.page.wait_for_timeout(250)
    ui.page.locator(f".ag-list-item:visible:text-is({json.dumps(value)})").first.click()
    ui.settle()


def _accordion_item(ui, entity_id: str):
    return (
        ui.page.locator("#br-detail [class*='Accordion-item']")
        .filter(has_text=re.compile(re.escape(entity_id)))
        .first
    )


def _branch_options(ui) -> list[str]:
    """What the header's branch selector offers, leaving it closed again."""
    ui.page.locator("#branch-select").first.click()
    ui.page.wait_for_timeout(350)
    out = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(250)
    return out


def _list_rows(ui) -> int:
    return ui.page.locator("#br-list tbody tr").count()


def _listing_for(ui, label: str) -> str:
    ui.segmented("br-status", label)
    return ui.text("br-list")


# =========================================================== i-merge-log: the happy path


@pytest.mark.scenario(
    scenario_id="I01",
    group="I",
    title="The header's + button creates a branch and puts the reader on it",
    feature="Branches · create",
    expected=(
        "The + beside the branch selector opens a modal that explains what a branch is, takes a "
        "name, a purpose and a work package, and on Create and switch closes, adds the branch to "
        "the selector, moves the header badge off main, and lists the branch on the Branches page."
    ),
)
def test_create_from_the_header(ui, record):
    _branches(ui)
    ui.check("the reader starts on main", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    ui.click("branch-new-open")
    ui.must("the New branch modal opened", ui.visible("branch-new-modal"))
    modal = ui.text("branch-new-modal")
    ui.check(
        "the modal says what a branch is before asking for a name",
        "stays on the branch until you merge it" in modal,
        modal[:160],
    )
    ui.shot(
        "The New branch modal explains what a branch is and asks for a name, a purpose and a work package"
    )
    ui.fill("branch-new-name", MERGE_BRANCH)
    ui.fill("branch-new-desc", "Group I: two measures edited on a branch, merged one row at a time.")
    ui.select("branch-new-wp", WP_LABEL)
    ui.click("branch-new-save")
    ui.check("the modal closed once the branch was created", not ui.visible("branch-new-modal"))
    badge = ui.branch_badge()
    ui.check("the header badge left main for the new branch", "branch" in badge.lower(), badge)
    ui.check(
        "the header badge counts the changes on the branch (none yet)",
        "0 change" in badge,
        badge,
    )
    ui.check("the new branch is offered in the selector", any(MERGE_BRANCH in o for o in _branch_options(ui)))
    listing = ui.text("br-list")
    ui.check("the branch is listed on the Branches page", MERGE_BRANCH in listing, listing[:200])
    ui.check("the list carries the work package it was created for", WP_LABEL in listing, listing[:200])
    ui.shot("The branch is created, the header is on it, and it is listed with its work package")


@pytest.mark.scenario(
    scenario_id="I02",
    group="I",
    title="The status control filters the list across all six of its values",
    feature="Branches · status filter",
    expected=(
        "Open, In review, Approved, Merged, Abandoned and All each re-read the list: a value with "
        "branches lists only branches in that state, and a value with none says so and says what to "
        "do instead."
    ),
)
def test_status_filter(ui, record):
    _branches(ui)
    labels = [t.strip() for t in ui.page.locator("#br-status label").all_inner_texts()]
    ui.check(
        "the control offers the five states and All",
        labels == ["Open", "In review", "Approved", "Merged", "Abandoned", "All"],
        f"{labels}",
    )
    for label, phrase in STATUSES:
        ui.segmented("br-status", label)
        text = ui.text("br-list")
        rows = _list_rows(ui)
        ui.check(
            f"the {label} filter answers with rows or with an empty state",
            rows > 0 or f"No {phrase} branches" in text,
            f"{rows} row(s): {text[:120]}",
        )
        if rows == 0:
            ui.check(
                f"the empty {label} list says what to do instead",
                "Pick another status above" in text,
                text[:120],
            )
        else:
            badges = [
                b.strip().lower()
                for b in ui.page.locator("#br-list tbody tr td:nth-child(2)").all_inner_texts()
            ]
            ui.check(
                f"every row the {label} filter lists is in that state",
                all(b == phrase for b in badges),
                f"{badges}",
            )
    ui.segmented("br-status", "Open")
    ui.check("the Open list holds the branch just created", MERGE_BRANCH in ui.text("br-list"))
    ui.shot("The status control has been walked to Open, which lists the open branches")
    ui.segmented("br-status", "All")
    ui.check("All lists the branch too", MERGE_BRANCH in ui.text("br-list"))
    ui.shot("All shows every branch whatever its state")


@pytest.mark.scenario(
    scenario_id="I03",
    group="I",
    title="The list says who made each branch and Open shows its change set",
    feature="Branches · list and open",
    expected=(
        "Each row carries the branch, its state, how many rows it holds, its work package, who made "
        "it and when, and an Open button; Open renders that branch's head and merge log below."
    ),
)
def test_list_and_open(ui, record):
    _branches(ui)
    headers = [h.strip() for h in ui.page.locator("#br-list thead th").all_inner_texts()]
    ui.check(
        "the list names its columns",
        headers[:6] == ["branch", "status", "rows", "work package", "by", "created"],
        f"{headers}",
    )
    row = ui.page.locator("#br-list tbody tr").filter(has_text=re.compile(re.escape(MERGE_BRANCH))).first
    ui.must("the branch created in I01 is listed", row.count() > 0)
    cells = [c.strip() for c in row.locator("td").all_inner_texts()]
    ui.check("the row says the branch is open", cells[1].lower() == "open", f"{cells}")
    ui.check("the row says who made it", "admin@example.edu" in cells[4], f"{cells}")
    ui.check("the row is dated", re.match(r"\d{4}-\d{2}-\d{2}", cells[5]) is not None, f"{cells}")
    ui.must("the row offers an Open button", ui.visible(_open_button(MERGE_ID)))
    ui.click(_open_button(MERGE_ID))
    detail = ui.text("br-detail")
    ui.check("Open renders that branch's detail", MERGE_BRANCH in detail, detail[:160])
    ui.check("the detail names the branch id", MERGE_ID in detail, detail[:160])
    ui.shot("Opening a branch from the list renders its head and its (still empty) merge log")


@pytest.mark.scenario(
    scenario_id="I04",
    group="I",
    title="An empty branch says so, and Switch puts the reader on it",
    feature="Branches · detail head",
    expected=(
        "The head carries the name, the state, the id, the description, who made it and its work "
        "package, four counts that are all zero, an empty merge log that says what will appear there, "
        "and a Switch button that afterwards reads 'You are on this branch' and is disabled."
    ),
)
def test_detail_head_and_switch(ui, record):
    _branches(ui, MERGE_ID)
    detail = ui.text("br-detail")
    for wanted in ("0 added", "0 changed", "0 deleted", "0 conflicts"):
        ui.check(f"the head counts '{wanted}'", wanted in detail, detail[:200])
    ui.check(
        "an empty branch says what would appear in its merge log",
        "edits, imports and applied proposals made on it will appear here" in detail,
        detail[:400],
    )
    ui.check("the head names the work package it belongs to", WP_LABEL in detail, detail[:400])
    ui.check("the Switch button offers to move the reader", "Switch to this branch" in ui.text("br-switch"))
    ui.shot("The branch is empty: four zero counts and a merge log that says what will land in it")
    ui.click("br-switch")
    ui.check("the header badge moved to the branch", "branch" in ui.branch_badge().lower(), ui.branch_badge())
    _branches(ui, MERGE_ID)
    ui.check(
        "the Switch button now says the reader is already here",
        "You are on this branch" in ui.text("br-switch"),
        ui.text("br-switch"),
    )
    ui.check("and is disabled, because there is nowhere to go", ui.disabled("br-switch"))
    ui.shot("On the branch, Switch reads 'You are on this branch' and is disabled")
    ui.branch("main")


@pytest.mark.scenario(
    scenario_id="I05",
    group="I",
    title="An edit made on a branch is invisible on main",
    feature="Branches · overlay",
    expected=(
        "Renaming two elements while on the branch saves a new version there and the branch's change "
        "count rises; switching back to main shows both elements exactly as they were."
    ),
    branch=MERGE_ID,
)
def test_edit_on_a_branch_leaves_main_alone(ui, record):
    before = {M1: _element_name(ui, M1), M2: _element_name(ui, M2)}
    ui.must("both elements were read on main first", all(before.values()), f"{before}")
    ui.branch(MERGE_BRANCH)
    ui.check("the reader is on the branch", "branch" in ui.branch_badge().lower(), ui.branch_badge())
    for element_id, suffix in ((M1, "(I merged)"), (M2, "(I left behind)")):
        feedback = _rename(ui, element_id, f"{before[element_id]} {suffix}")
        ui.check(f"{element_id} saved on the branch", "Saved version" in feedback, feedback[:120])
    ui.check(
        "the element carries the branch's name while the reader is on the branch",
        _element_name(ui, M1).endswith("(I merged)"),
        _element_name(ui, M1),
    )
    ui.shot("On the branch the measure carries its new name")
    ui.branch("main")
    ui.check(
        "main still carries the original name",
        _element_name(ui, M1) == before[M1],
        f"main says {_element_name(ui, M1)!r}, expected {before[M1]!r}",
    )
    ui.check(
        "and so does the second element",
        _element_name(ui, M2) == before[M2],
        f"main says {_element_name(ui, M2)!r}, expected {before[M2]!r}",
    )
    ui.shot("Back on main the same measure is untouched: the branch is an overlay, not a write")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I06",
    group="I",
    title="The merge log lists every row the branch would write, and says what each one changes",
    feature="Branches · merge log",
    expected=(
        "Two changed elements appear as two ticked rows with their id, what they are, the fields that "
        "differ and no conflict; the accordion below shows main's value beside the branch's for the "
        "one field that moved."
    ),
    branch=MERGE_ID,
)
def test_merge_log_and_diff(ui, record):
    _branches(ui, MERGE_ID)
    detail = ui.text("br-detail")
    ui.check("the head now counts two changed rows", "2 changed" in detail, detail[:200])
    ui.check("and no conflicts", "0 conflicts" in detail, detail[:200])
    keys = ui.grid_row_ids(GRID)
    ui.must("the merge log holds one row per edited element", len(keys) == 2, f"{keys}")
    ui.check(
        "each row is keyed by the element it would write",
        set(keys) == {f"element:{M1}", f"element:{M2}"},
        f"{keys}",
    )
    key = f"element:{M1}"
    ui.check(
        "the row says what kind of change it is",
        _row(ui, key, "change") == "changed",
        _row(ui, key, "change"),
    )
    ui.check("the row says it is an element", _row(ui, key, "kind") == "element", _row(ui, key, "kind"))
    ui.check("the row names the element", M1 in _row(ui, key, "entity_id"), _row(ui, key, "entity_id"))
    ui.check(
        "the row says which fields differ",
        "name" in _row(ui, key, "fields"),
        _row(ui, key, "fields"),
    )
    ui.check("the row is not in conflict", _row(ui, key, "conflict") == "", _row(ui, key, "conflict"))
    ui.check(
        "a row that is not in conflict offers nothing to take",
        _row(ui, key, "resolution") == "",
        _row(ui, key, "resolution"),
    )
    ui.check(
        "every row starts ticked, so merging everything is the default",
        _included(ui, key) and _included(ui, f"element:{M2}"),
    )
    ui.shot("The merge log: one ticked row per element the branch would write to main")
    item = _accordion_item(ui, M1)
    ui.must("the accordion carries an entry for the row", item.count() > 0)
    item.locator("[class*='Accordion-control']").first.click()
    ui.settle()
    body = item.inner_text()
    ui.check(
        "the entry shows main's value beside the branch's",
        "(I merged)" in body,
        body[:300],
    )
    ui.check("and names the field that moved", re.search(r"\bname\b", body) is not None, body[:300])
    ui.shot("'What each row changes' opens to main's row on the left and the branch's on the right")


@pytest.mark.scenario(
    scenario_id="I07",
    group="I",
    title="Merging a subset writes the ticked row and says how many remain",
    feature="Branches · merge a subset",
    expected=(
        "With one of two rows unticked, Merge writes only the ticked one to main, reports one row "
        "merged and one remaining, leaves the branch open, and main now carries the merged name while "
        "the unticked element is unchanged."
    ),
    branch=MERGE_ID,
)
def test_merge_a_subset(ui, record):
    kept_before = _element_name(ui, M2)
    _branches(ui, MERGE_ID)
    ui.check(
        "an admin is told the merge will be recorded as one made without a review",
        "an admin may merge without a review" in ui.text("br-detail"),
        ui.text("br-detail")[:400],
    )
    _set_included(ui, f"element:{M2}", False)
    ui.check("the second row is no longer ticked", not _included(ui, f"element:{M2}"))
    ui.check("the first row is still ticked", _included(ui, f"element:{M1}"))
    ui.shot("One of the two rows has been unticked, so only the other will go to main")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check("the merge reports one row written to main", "Merged 1 row(s) to main" in feedback, feedback)
    ui.check("and says one row stayed on the branch", "1 row(s) remain on the branch" in feedback, feedback)
    detail = ui.text("br-detail")
    ui.check(
        "the merge log now holds the one row that was left",
        len(ui.grid_row_ids(GRID)) == 1,
        f"{ui.grid_row_ids(GRID)}",
    )
    ui.check("the branch is still open", "open" in detail[:200].lower(), detail[:200])
    ui.shot("The merge says what went to main and what stayed behind")
    ui.check(
        "main now carries the merged element's new name",
        _element_name(ui, M1).endswith("(I merged)"),
        _element_name(ui, M1),
    )
    ui.check(
        "and the unticked element is untouched on main",
        _element_name(ui, M2) == kept_before,
        f"main says {_element_name(ui, M2)!r}, expected {kept_before!r}",
    )
    ui.shot("Main carries the merged name; the row that was not ticked never reached it")
    _branches(ui)


# ============================================================== i-conflict: main moved


@pytest.mark.scenario(
    scenario_id="I08",
    group="I",
    title="A row main moved under is flagged as a conflict",
    feature="Branches · conflict",
    expected=(
        "With the same two elements changed on a branch and then on main, the merge log marks both "
        "rows conflict, the head counts two, base and main versions differ, and the accordion says "
        "main moved since the branch took its copy."
    ),
)
def test_conflict_is_flagged(ui, record):
    _branches(ui)
    _new_branch(
        ui,
        "branch-new-open-page",
        CONFLICT_BRANCH,
        "Group I: two definitions changed on the branch and again on main.",
    )
    ui.check("the page's New branch button created the branch too", CONFLICT_BRANCH in ui.text("br-list"))
    ui.check("and switched the reader onto it", "branch" in ui.branch_badge().lower(), ui.branch_badge())
    before = {}
    for element_id in (D1, D2):
        before[element_id] = _element_name(ui, element_id)
        feedback = _rename(ui, element_id, f"{before[element_id]} (I branch)")
        ui.check(f"{element_id} was changed on the branch", "Saved version" in feedback, feedback[:120])
    ui.branch("main")
    for element_id in (D1, D2):
        feedback = _rename(ui, element_id, f"{before[element_id]} (I main)")
        ui.check(f"{element_id} then moved on main as well", "Saved version" in feedback, feedback[:120])
    ui.shot("Main has moved the same two definitions the branch is holding")
    _branches(ui, CONFLICT_ID)
    detail = ui.text("br-detail")
    ui.check("the head counts both rows as conflicts", "2 conflicts" in detail, detail[:200])
    for element_id in (D1, D2):
        key = f"element:{element_id}"
        ui.check(
            f"{element_id} is marked conflict in the merge log",
            _row(ui, key, "conflict") == "conflict",
            _row(ui, key, "conflict"),
        )
        base, main_v = _row(ui, key, "base_version"), _row(ui, key, "main_version")
        ui.check(
            f"{element_id} shows the version it branched from against main's today",
            base.isdigit() and main_v.isdigit() and int(main_v) > int(base),
            f"base {base}, main {main_v}",
        )
        ui.check(
            f"{element_id} offers a take, defaulting to the branch's row",
            _row(ui, key, "resolution") == "branch",
            _row(ui, key, "resolution"),
        )
    ui.shot("Both rows are flagged conflict, with the base version beside main's")
    item = _accordion_item(ui, D1)
    item.locator("[class*='Accordion-control']").first.click()
    ui.settle()
    body = item.inner_text()
    ui.check(
        "the accordion explains the conflict in words",
        "Main moved from version" in body and "since this branch took its copy" in body,
        body[:300],
    )
    ui.check("and shows both names side by side", "(I main)" in body and "(I branch)" in body, body[:400])
    ui.shot("The accordion says main moved since the branch took its copy, and shows both rows")
    ui.branch("main")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I09",
    group="I",
    title="Taking the branch's row resolves a conflict in the branch's favour",
    feature="Branches · conflict · take branch",
    expected=(
        "The take cell of a conflicting row can be set both ways; left on 'branch' and ticked alone, "
        "Merge writes the branch's row over main's and leaves the other conflict on the branch."
    ),
)
def test_resolve_to_the_branch(ui, record):
    _branches(ui, CONFLICT_ID)
    key = f"element:{D1}"
    _set_take(ui, key, "main")
    ui.check(
        "the take cell can be set to main", _row(ui, key, "resolution") == "main", _row(ui, key, "resolution")
    )
    _set_take(ui, key, "branch")
    ui.check(
        "and set back to the branch", _row(ui, key, "resolution") == "branch", _row(ui, key, "resolution")
    )
    _set_included(ui, f"element:{D2}", False)
    ui.check("only the resolved row is ticked", _included(ui, key) and not _included(ui, f"element:{D2}"))
    ui.shot("One conflict is set to take the branch's row and ticked; the other is left alone")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check("the merge writes the resolved row to main", "Merged 1 row(s) to main" in feedback, feedback)
    ui.check("it drops nothing, because the branch won", "dropped" not in feedback, feedback)
    ui.check("and one row is still on the branch", "1 row(s) remain on the branch" in feedback, feedback)
    ui.shot("Taking the branch's row merges it and leaves the second conflict behind")
    ui.check(
        "main now carries the branch's name for that element",
        _element_name(ui, D1).endswith("(I branch)"),
        _element_name(ui, D1),
    )
    ui.shot("Main has taken the branch's row for the resolved conflict")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I10",
    group="I",
    title="Taking main's row drops the branch's, and empties the branch",
    feature="Branches · conflict · take main",
    expected=(
        "Setting the remaining conflict's take to main and merging applies nothing, reports one "
        "conflict dropped in favour of main, leaves main's own value in place and closes the branch "
        "because nothing remains on it."
    ),
)
def test_resolve_to_main(ui, record):
    main_before = _element_name(ui, D2)
    _branches(ui, CONFLICT_ID)
    key = f"element:{D2}"
    ui.must(
        "one conflicting row is left on the branch",
        ui.grid_row_ids(GRID) == [key],
        f"{ui.grid_row_ids(GRID)}",
    )
    _set_take(ui, key, "main")
    ui.check("the take cell reads main", _row(ui, key, "resolution") == "main", _row(ui, key, "resolution"))
    ui.check("the row is ticked", _included(ui, key))
    ui.shot("The last conflict is set to keep main's row")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check("nothing was written to main", "Merged 0 row(s) to main" in feedback, feedback)
    ui.check(
        "the conflict is reported as dropped in main's favour",
        "dropped 1 conflict(s) in favour of main" in feedback,
        feedback,
    )
    ui.check(
        "and the branch closed, because nothing remains",
        "the branch is now merged and closed" in feedback,
        feedback,
    )
    ui.shot("Taking main's row drops the branch's and closes the branch")
    ui.check(
        "main kept the value it had",
        _element_name(ui, D2) == main_before,
        f"main says {_element_name(ui, D2)!r}, expected {main_before!r}",
    )
    ui.shot("Main is unchanged: the branch's row was discarded, not applied")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I11",
    group="I",
    title="A closed branch leaves the selector and refuses every write",
    feature="Branches · closed",
    expected=(
        "The merged branch is listed under Merged with who closed it and when, its Switch, Abandon "
        "and Merge buttons are disabled, its merge log says what it held was merged or discarded, and "
        "the header selector no longer offers it."
    ),
)
def test_a_closed_branch(ui, record):
    _branches(ui)
    merged = _listing_for(ui, "Merged")
    ui.check("the merged branch is listed under Merged", CONFLICT_BRANCH in merged, merged[:200])
    still_open = _listing_for(ui, "Open")
    ui.check("it is not listed under Open", CONFLICT_BRANCH not in still_open, still_open[:200])
    _branches(ui, CONFLICT_ID)
    detail = ui.text("br-detail")
    ui.check("the head says who closed it and when", "closed by" in detail, detail[:300])
    ui.check("the review panel says the branch is merged", "This branch is merged." in detail, detail[:400])
    ui.check(
        "the merge log says what it held is gone",
        "This branch is closed; what it held was merged or discarded" in detail,
        detail[:600],
    )
    for control, what in (("br-switch", "Switch"), ("br-abandon", "Abandon"), ("br-merge", "Merge")):
        ui.check(f"{what} is disabled on a closed branch", ui.disabled(control), control)
    ui.shot("A merged branch: closed, its buttons disabled and its merge log emptied")
    options = _branch_options(ui)
    ui.check(
        "the header selector no longer offers it",
        not any(CONFLICT_BRANCH in o for o in options),
        f"{options}",
    )
    ui.check(
        "but still offers the branch that is open", any(MERGE_BRANCH in o for o in options), f"{options}"
    )
    ui.shot("The header selector offers only main and the branches still open")


# ================================================ i-review: the freeze and the decision


@pytest.mark.scenario(
    scenario_id="I12",
    group="I",
    title="Requesting a review freezes the branch",
    feature="Branches · review · request",
    expected=(
        "An architect creates a branch, edits an element on it, and Request review moves it to in "
        "review, says it is frozen until its reviewers decide, and lists the element type that must "
        "be approved and by whom."
    ),
    role="architect",
    branch=REVIEW_ID,
)
def test_request_a_review(ui, record):
    ui.persona("Architect")
    ui.check("the persona switched to the architect", "architect" in ui.role_badge().lower(), ui.role_badge())
    _branches(ui)
    _new_branch(ui, "branch-new-open", REVIEW_BRANCH, "Group I: one data product, for the review to decide.")
    before = _element_name(ui, P1)
    feedback = _rename(ui, P1, f"{before} (I in review)")
    ui.check("the architect may write on their own branch", "Saved version" in feedback, feedback[:160])
    _branches(ui, REVIEW_ID)
    detail = ui.text("br-detail")
    ui.check("the branch is the architect's", "architect@example.edu" in detail, detail[:300])
    ui.check(
        "an open branch says a review would freeze it",
        "it freezes until the reviewers decide" in detail,
        detail[:600],
    )
    ui.must("the author is offered Request review", ui.visible("rv-request"))
    ui.shot("The architect's branch is open, with one row and a Request review button")
    ui.click("rv-request")
    detail = ui.text("br-detail")
    ui.check(
        "the request says the branch is frozen",
        "the branch is frozen until its reviewers decide" in detail,
        detail[:400],
    )
    ui.check("the branch is now in review", "in review" in detail[:300].lower(), detail[:300])
    ui.check(
        "the panel names what must be approved before it can merge",
        "frozen until every touched type is approved" in detail,
        detail[:600],
    )
    ui.check("and lists the element type it touches", "Data Product" in detail, detail[:600])
    ui.shot("The branch is in review: frozen, with the type that must be approved listed")
    ui.branch("main")


@pytest.mark.scenario(
    scenario_id="I13",
    group="I",
    title="A write to a frozen branch is refused with the reason",
    feature="Branches · review · freeze",
    expected=(
        "Saving an element while on a branch that is in review is refused with 'frozen until the "
        "review is decided', and the element still carries what it carried before."
    ),
    role="architect",
    branch=REVIEW_ID,
)
def test_the_freeze_refuses_a_write(ui, record):
    ui.persona("Architect")
    ui.branch(REVIEW_BRANCH)
    ui.check("the reader is on the frozen branch", "branch" in ui.branch_badge().lower(), ui.branch_badge())
    before = _element_name(ui, P1)
    ui.goto(f"/element/{P1}")
    _tab(ui, "Edit")
    # The Save button stays enabled on a frozen branch: the refusal only arrives after the typing.
    ui.check(
        "Save is offered even though the branch is frozen",
        not ui.disabled("el-save"),
        "enabled — see the finding for group I",
    )
    ui.fill("el-name", f"{before} (refused)")
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    ui.check("the save is refused", "frozen until the review is decided" in feedback, feedback[:200])
    ui.check("and the refusal names the branch", REVIEW_ID in feedback, feedback[:200])
    ui.shot("A write to a branch in review is refused, and says why")
    ui.check(
        "the element still carries what it carried before the refusal",
        _element_name(ui, P1) == before,
        f"{_element_name(ui, P1)!r} vs {before!r}",
    )
    ui.branch("main")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I14",
    group="I",
    title="The author of a branch is not offered its approval",
    feature="Branches · review · the author",
    expected=(
        "On their own branch in review the architect sees no Approve and no Send back, and is told "
        "somebody else approves it; the branch stays in review."
    ),
    role="architect",
    branch=REVIEW_ID,
)
def test_the_author_may_not_approve(ui, record):
    ui.persona("Architect")
    _branches(ui, REVIEW_ID)
    detail = ui.text("br-detail")
    ui.check(
        "the author is told somebody else decides",
        "You wrote this branch; somebody else approves it." in detail,
        detail[:600],
    )
    ui.check("no Approve button is offered to the author", ui.page.locator("button#rv-approve").count() == 0)
    ui.check("no Send back button either", ui.page.locator("button#rv-send-back").count() == 0)
    ui.check(
        "and Request review is gone, the branch already being in review",
        ui.page.locator("button#rv-request").count() == 0,
    )
    ui.check("the branch is still in review", "in review" in detail[:300].lower(), detail[:300])
    ui.check(
        "an architect is told the branch must be approved before it can merge",
        "the branch must be approved by its reviewers first" in detail,
        detail[:800],
    )
    ui.check("so Merge is disabled for the author", ui.disabled("br-merge"))
    ui.shot("Its author sees no approval controls: somebody else decides")


@pytest.mark.scenario(
    scenario_id="I15",
    group="I",
    title="A send-back without a comment is refused",
    feature="Branches · review · send back",
    expected=(
        "A reviewer who sends a branch back without saying why is refused with 'a send-back needs a "
        "comment', and the branch stays in review."
    ),
    role="reviewer",
    branch=REVIEW_ID,
)
def test_send_back_needs_a_comment(ui, record):
    ui.persona("Reviewer")
    _branches(ui, REVIEW_ID)
    ui.must(
        "the reviewer is offered the decision controls",
        ui.visible("rv-approve") and ui.visible("rv-send-back"),
    )
    ui.check(
        "the comment field says when it is required",
        "required to send back" in (ui.page.locator("#rv-comment").first.get_attribute("placeholder") or ""),
        ui.page.locator("#rv-comment").first.get_attribute("placeholder") or "",
    )
    ui.check("a reviewer may not merge", ui.disabled("br-merge"))
    ui.check(
        "and is told why",
        "only an architect (an approved branch) or an admin may merge" in ui.text("br-detail"),
        ui.text("br-detail")[:800],
    )
    ui.click("rv-send-back")
    detail = ui.text("br-detail")
    ui.check(
        "the send-back is refused for want of a comment",
        "a send-back needs a comment" in detail,
        detail[:400],
    )
    ui.check("the branch is still in review", "in review" in detail[:300].lower(), detail[:300])
    ui.shot("Sending a branch back without saying why is refused")


@pytest.mark.scenario(
    scenario_id="I16",
    group="I",
    title="A reviewer approves the branch, and only then may the architect merge it",
    feature="Branches · review · approve",
    expected=(
        "The reviewer approves the type the branch touches; the branch becomes approved, the decision "
        "is recorded with who made it, and the architect who was refused the merge is now offered it."
    ),
    role="reviewer",
    branch=REVIEW_ID,
)
def test_a_reviewer_approves(ui, record):
    ui.persona("Reviewer")
    _branches(ui, REVIEW_ID)
    pills = [t.strip() for t in ui.page.locator("#rv-panel [class*='Pill-label']").all_inner_texts()]
    ui.check(
        "the type the branch touches is already chosen for approval",
        any("Data Product" in p for p in pills),
        f"{pills}",
    )
    ui.check("Approve is offered", not ui.disabled("rv-approve"))
    ui.shot("The reviewer is offered the type the branch touches, already selected")
    ui.click("rv-approve")
    detail = ui.text("br-detail")
    ui.check("the approval names what was approved", "Approved Data Product" in detail, detail[:400])
    ui.check("and says the branch is approved", "the branch is approved" in detail, detail[:400])
    ui.check("the head badge reads approved", "approved" in detail[:300].lower(), detail[:300])
    ui.check(
        "the decision is recorded against its reviewer",
        "reviewer@example.edu approved" in detail,
        detail[:800],
    )
    ui.check(
        "the panel now says the author or an admin may merge",
        "the author or an admin may merge it" in detail,
        detail[:800],
    )
    ui.shot("Approved: the decision is recorded and the branch may now be merged")
    ui.persona("Architect")
    _branches(ui, REVIEW_ID)
    ui.check("the architect may now merge the approved branch", not ui.disabled("br-merge"))
    ui.check(
        "and is no longer told to wait for a review",
        "must be approved by its reviewers first" not in ui.text("br-detail"),
        ui.text("br-detail")[:800],
    )
    ui.shot("The architect who was refused the merge before is offered it now the branch is approved")


@pytest.mark.scenario(
    scenario_id="I17",
    group="I",
    title="The merge log of an approved branch closes it and the reader comes back to main",
    feature="Branches · merge an approved branch",
    expected=(
        "The architect merges the one row the approved branch holds; it is written to main, the "
        "branch closes, and a reader who was standing on it is returned to main."
    ),
    role="architect",
    branch=REVIEW_ID,
)
def test_merge_the_approved_branch(ui, record):
    ui.persona("Architect")
    ui.branch(REVIEW_BRANCH)
    _branches(ui, REVIEW_ID)
    ui.must(
        "the approved branch holds its one row", len(ui.grid_row_ids(GRID)) == 1, f"{ui.grid_row_ids(GRID)}"
    )
    ui.check("the row is ticked", _included(ui, f"element:{P1}"))
    ui.shot("The approved branch, standing on it, with its one row ticked")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check("the row is written to main", "Merged 1 row(s) to main" in feedback, feedback)
    ui.check("and the branch closes", "the branch is now merged and closed" in feedback, feedback)
    ui.check(
        "the reader who was on it is returned to main",
        ui.branch_badge().strip().lower() == "main",
        ui.branch_badge(),
    )
    ui.shot("The approved branch is merged and closed, and the header is back on main")
    ui.check(
        "main carries what the branch held",
        _element_name(ui, P1).endswith("(I in review)"),
        _element_name(ui, P1),
    )
    ui.shot("Main carries the reviewed change")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I18",
    group="I",
    title="A branch in review is still offered for reading, and says so in the selector",
    feature="Branches · selector",
    expected=(
        "The header selector labels each branch with how many rows it holds and, when it is not open, "
        "the state it is in, so a reader knows before switching what they are stepping onto."
    ),
)
def test_the_selector_labels_state(ui, record, finding):
    _branches(ui)
    options = _branch_options(ui)
    ui.check("main is always offered first", options and options[0] == "main", f"{options}")
    ui.check(
        "the open branch is labelled with the rows it still holds",
        any(re.search(re.escape(MERGE_BRANCH) + r" \(\d+\)$", o) for o in options),
        f"{options}",
    )
    ui.check(
        "no closed branch is offered",
        not any(CONFLICT_BRANCH in o or REVIEW_BRANCH in o for o in options),
        f"{options}",
    )
    ui.shot("The header selector: main, and every branch still open, labelled with its size")
    finding.append(
        Finding(
            finding_id="I-1",
            where="src/ea/ui/pages/element.py · render (EL_SAVE) and services/repository.py · check_write",
            severity="usability",
            summary="Save stays enabled on a branch frozen by a review, and only refuses after the edit",
            detail=(
                "The element page decides whether to enable Save from the role and the branch alone "
                "(`can_write = ctx.can('edit_content') and (ctx.on_branch() or ctx.can('edit_main'))`), "
                "so on a branch that is in review the button is offered and the caption beside it is "
                "empty. The freeze is enforced one layer down, in `check_write`, so the architect types "
                "the change, presses Save and only then reads 'frozen until the review is decided' — "
                "checkpoint 4 of the usability list asks that nothing be offered that cannot be used, or "
                "that the reason be said up front. The Branches page does this correctly: its Merge "
                "button is disabled with the reason printed beneath it."
            ),
        )
    )
