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
| I12–I17 | `i-review` | authored by the Architect, frozen by a review, refused to its author, decided by the Reviewer, then merged |
| I18 | — | what the header selector offers once two of the three are closed |

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
MODAL = "branch-new-modal-body"  # dmc.Modal puts the id on its parts, not on a root node
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
    ui.must("the New branch modal opened", ui.visible(MODAL))
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
    """Choose 'branch' or 'main' in the editable take cell of a conflicting row.

    The cell edits on a single click, which puts a collapsed picker in it; the picker's own
    click opens the list. Both take a moment, so the two are tried together until the list is up.
    """
    cell = ui.page.locator(f"#{GRID} .ag-row[row-id='{key}'] .ag-cell[col-id='resolution']").first
    options = ui.page.locator(".ag-list-item:visible")
    for _ in range(4):
        if options.count():
            break
        cell.scroll_into_view_if_needed()
        cell.click()
        ui.page.wait_for_timeout(350)
        picker = ui.page.locator(f"#{GRID} .ag-cell-editor .ag-picker-field-wrapper")
        if not options.count() and picker.count():
            picker.first.click()
            ui.page.wait_for_timeout(350)
    ui.must(f"the take cell of {key} offers a choice", options.count() > 0)
    options.filter(has_text=re.compile(rf"^\s*{re.escape(value)}\s*$")).first.click()
    ui.page.wait_for_timeout(250)
    ui.settle()


def _conflict_cell(ui, key: str):
    return ui.page.locator(f"#{GRID} .ag-row[row-id='{key}'] .ag-cell[col-id='conflict']").first


def _flagged(ui, key: str) -> bool:
    """Whether the grid styles the row as a conflict (the class the column's rules apply)."""
    return "ea-conflict" in (_conflict_cell(ui, key).get_attribute("class") or "")


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
    ui.must("the New branch modal opened", ui.visible(MODAL))
    modal = ui.text(MODAL)
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
    ui.check("the modal closed once the branch was created", not ui.visible(MODAL))
    badge = ui.branch_badge()
    ui.check("the header badge left main for the new branch", "branch" in badge.lower(), badge)
    ui.check(
        "the header badge counts the changes on the branch (none yet)",
        "0 change" in badge.lower(),
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
        ui.check(f"the head counts '{wanted}'", wanted in detail.lower(), detail[:200])
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
    ui.check("the head now counts two changed rows", "2 changed" in detail.lower(), detail[:200])
    ui.check("and no conflicts", "0 conflicts" in detail.lower(), detail[:200])
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
    ui.check("the row is not in conflict", not _flagged(ui, key), _conflict_cell(ui, key).inner_html()[:120])
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
def test_conflict_is_flagged(ui, record, finding):
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
    ui.check("the head counts both rows as conflicts", "2 conflicts" in detail.lower(), detail[:200])
    for element_id in (D1, D2):
        key = f"element:{element_id}"
        ui.check(f"{element_id} is styled as a conflict in the merge log", _flagged(ui, key))
        # The column declares `valueFormatter: params.value ? 'conflict' : ''`, so the cell is
        # meant to read "conflict". The grid infers a boolean column instead and renders a tick,
        # which in a grid whose first column is a real tick box says the opposite of what is meant.
        ui.check(
            f"{element_id} says 'conflict' in the merge log, as its column declares",
            _row(ui, key, "conflict") == "conflict",
            f"the cell renders {_conflict_cell(ui, key).inner_html()[:160]!r}",
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
    title="A write to a frozen branch is refused before it is typed, with the reason",
    feature="Branches · review · freeze",
    expected=(
        "On a branch that is in review the element page offers no Save and says why beside it — "
        "'frozen until the review is decided' — and the element still carries what it carried before."
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
    # Nothing is offered that cannot be used: the freeze is said before the reader types.
    ui.check(
        "Save is not offered on a branch that is frozen",
        ui.disabled("el-save"),
        "enabled" if not ui.disabled("el-save") else "disabled",
    )
    why = ui.text("el-save-why")
    ui.check("and the reason is beside it", "frozen until the review is decided" in why, why[:200])
    ui.check("naming the branch that is frozen", REVIEW_ID in why, why[:200])
    ui.shot("A branch in review: Save is off, with the freeze said beside it")
    ui.fill("el-name", f"{before} (refused)")
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    ui.check(
        "and pressing it changes nothing, because there is nothing to press",
        "Saved version" not in feedback,
        feedback[:200] or "(no feedback at all)",
    )
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
def test_send_back_needs_a_comment(ui, record, finding):
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
    # A refusal belongs beside the button that raised it, not under a grid the reviewer was
    # not looking at: the review panel has its own slot and the outcome is written there.
    slot = ui.text("rv-feedback")
    ui.check(
        "the refusal is in the review panel, beside the button that raised it",
        "a send-back needs a comment" in slot,
        slot or "(the review panel's own slot is empty)",
    )
    button = ui.page.locator("#rv-send-back").first.bounding_box()
    message = ui.page.locator("#rv-feedback").first.bounding_box()
    gap = (message["y"] - button["y"] - button["height"]) if (button and message) else 0
    ui.check(
        "and within sight of it",
        0 <= gap < 200,
        f"{gap:.0f} px below the Send back button",
    )
    ui.check("the refusal reached the screen", "a send-back needs a comment" in detail)


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


# ======================================================= what else a branch can hold and be

# The three branches the scenarios below build, in the order they are built.
ADDED_BRANCH = "I added"
ADDED_ID = "i-added"
ABANDON_BRANCH = "I abandon"
ABANDON_ID = "i-abandon"
PENDING_BRANCH = "I pending"
PENDING_ID = "i-pending"

NEW_TYPE = "Capability"  # the type of the element created on i-added
NEW_ELEMENT = "I added capability"
OTHER_CAP = "CAP-ENROL-MGMT"  # the far end of the relationship added beside it
OTHER_CAP_NAME = "Student Enrolment Management"
D3 = "DEF-ENROLLED-STUDENT"  # a Business Definition, renamed and un-related on i-abandon
D3_REL = "SRS_Enrolment"  # the far end of the relationship i-abandon deletes
P2 = "DP-ENROL-EXTRACT"  # a Data Product, the type the reviewer approves on i-pending
T1 = "LTC-ANALYTICS"  # a Logical Technology Component, the type left pending


def _choose(ui, control: str, label: str, exact: bool = True) -> None:
    """Pick an option from a Select, taking only the list that control has just opened.

    Every Select on a page keeps its options in the DOM, so a page with several of them
    (Browse, the element form) offers the same word more than once; only the visible list
    belongs to the control that was clicked.
    """
    ui.page.locator(f"#{control}").first.click()
    ui.page.wait_for_timeout(300)
    pattern = re.compile(rf"^{re.escape(label)}$") if exact else re.compile(re.escape(label))
    ui.page.locator("[role='option']:visible").filter(has_text=pattern).first.click()
    ui.settle()


def _pick_other(ui, text: str, element_id: str) -> None:
    """Search the other-element select on the Relationships tab and choose one by its id."""
    box = ui.page.locator("#el-rel-other").first
    box.click()
    box.fill(text)
    ui.page.wait_for_timeout(700)
    ui.settle()
    ui.page.locator("[role='option']:visible").filter(
        has_text=re.compile(re.escape(element_id))
    ).first.click()
    ui.settle()


def _name_on_screen(ui, element_id: str) -> str:
    """The name the element page shows for this id, or '' when there is no element to show."""
    ui.goto(f"/element/{element_id}")
    box = ui.page.locator("#el-name")
    return (box.first.input_value() or "").strip() if box.count() else ""


def _create_element(ui, type_label: str, name: str) -> str:
    """Create an element from Browse and return the identifier the application minted for it."""
    ui.goto("/browse")
    ui.click("new-open")
    _choose(ui, "new-type", type_label)
    ui.fill("new-name", name)
    ui.click("new-save")
    for _ in range(24):
        if "/element/" in ui.page.url:
            break
        ui.page.wait_for_timeout(250)
    ui.settle()
    return ui.page.url.rsplit("/", 1)[-1].split("?")[0] if "/element/" in ui.page.url else ""


def _rel_tables(ui, element_id: str) -> str:
    """What the element's Relationships tab lists, on whatever branch the reader is on."""
    ui.goto(f"/element/{element_id}")
    _tab(ui, "Relationships")
    return ui.page.locator("#el-rel-tables").inner_text()


def _cell_class(ui, key: str, col: str) -> str:
    return (
        ui.page.locator(f"#{GRID} .ag-row[row-id='{key}'] .ag-cell[col-id='{col}']").first.get_attribute(
            "class"
        )
        or ""
    )


def _key_of(ui, kind: str) -> str:
    """The merge log's one row of this kind ('element' or 'relationship'), or ''."""
    keys = [k for k in ui.grid_row_ids(GRID) if k.startswith(f"{kind}:")]
    return keys[0] if len(keys) == 1 else ""


def _tick_all_box(ui):
    """The grid's own tick-all, which the include column declares in its header."""
    for selector in (
        f"#{GRID} .ag-header-cell[col-id='include'] input[type='checkbox']",
        f"#{GRID} .ag-header-select-all input[type='checkbox']",
    ):
        loc = ui.page.locator(selector).first
        if loc.count():
            return loc
    return None


def _set_all_included(ui, on: bool) -> bool:
    """Tick or untick every row from the header box; falls back to the rows themselves."""
    box = _tick_all_box(ui)
    if box is not None:
        box.scroll_into_view_if_needed()
        if box.is_checked() != on:
            box.click(force=True)
        ui.settle()
        return True
    for key in ui.grid_row_ids(GRID):
        _set_included(ui, key, on)
    return False


def _requirements(ui) -> list[list[str]]:
    """The review panel's 'type touched / reviewers / decision' table, row by row.

    The decision is a badge, which the stylesheet prints in capitals; the text is folded
    back to lower case so a scenario asserts the word rather than the styling.
    """
    rows = ui.page.locator("#rv-panel table tbody tr")
    out = []
    for i in range(rows.count()):
        cells = [c.strip() for c in rows.nth(i).locator("td").all_inner_texts()]
        out.append(cells[:2] + [c.lower() for c in cells[2:]])
    return out


def _pills(ui) -> list[str]:
    """The types the reviewer's approval control is holding."""
    return [t.strip() for t in ui.page.locator("#rv-panel [class*='Pill-label']").all_inner_texts()]


def _deselect_type(ui, label: str) -> None:
    """Take one type out of the reviewer's approval list, however the control offers it."""
    pill = (
        ui.page.locator("#rv-panel [class*='Pill-root']").filter(has_text=re.compile(re.escape(label))).first
    )
    remove = pill.locator("[class*='Pill-remove']").first if pill.count() else None
    if remove is not None and remove.count():
        remove.click()
    else:
        ui.page.locator("#rv-types").first.click()
        ui.page.wait_for_timeout(300)
        ui.page.locator("[role='option']:visible").filter(
            has_text=re.compile(rf"^{re.escape(label)}$")
        ).first.click()
        ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(250)
    ui.settle()


# ================================================================= i-added: rows main has never seen


@pytest.mark.scenario(
    scenario_id="I19",
    group="I",
    title="An element created on a branch, and a relationship drawn to it, are 'added' rows",
    feature="Branches · merge log · added rows",
    expected=(
        "A new element and a new relationship made while on a branch appear in the merge log as two "
        "added rows — the element named with its type, the relationship named in words rather than by "
        "its identifier — with nothing to say about main, and the accordion shows main's side as empty."
    ),
)
def test_added_rows(ui, record):
    _branches(ui)
    _new_branch(
        ui,
        "branch-new-open",
        ADDED_BRANCH,
        "Group I: an element and a relationship that main has never seen.",
    )
    ui.must("the reader is on the new branch", "branch" in ui.branch_badge().lower(), ui.branch_badge())
    new_id = _create_element(ui, NEW_TYPE, NEW_ELEMENT)
    ui.must("the element was created and opened", new_id.startswith("CAP-"), f"the page went to {new_id!r}")
    ui.check(
        "the element carries the name it was given",
        (ui.page.locator("#el-name").first.input_value() or "").strip() == NEW_ELEMENT,
        ui.page.locator("#el-name").first.input_value() or "",
    )
    _tab(ui, "Relationships")
    _pick_other(ui, OTHER_CAP_NAME, OTHER_CAP)
    _choose(ui, "el-rel-type", "contains", exact=False)
    ui.click("el-rel-add")
    feedback = ui.text("el-rel-feedback")
    ui.must("the relationship was added on the branch", "added" in feedback.lower(), feedback)
    ui.shot("A new capability, created on the branch, with a relationship drawn from it")
    _branches(ui, ADDED_ID)
    detail = ui.text("br-detail")
    ui.check("the head counts two added rows", "2 added" in detail.lower(), detail[:200])
    ui.check("and nothing changed or deleted", "0 changed" in detail.lower(), detail[:200])
    ui.check("and no conflict, main having neither row", "0 conflicts" in detail.lower(), detail[:200])
    element_key, rel_key = _key_of(ui, "element"), _key_of(ui, "relationship")
    ui.must(
        "the merge log holds one element row and one relationship row",
        bool(element_key) and bool(rel_key),
        f"{ui.grid_row_ids(GRID)}",
    )
    for key in (element_key, rel_key):
        ui.check(f"{key} is an addition", _row(ui, key, "change") == "added", _row(ui, key, "change"))
        ui.check(
            f"{key} is coloured as an addition",
            "ea-added" in _cell_class(ui, key, "change"),
            _cell_class(ui, key, "change"),
        )
        ui.check(
            f"{key} has nothing on main to compare with",
            _row(ui, key, "main_version") == "",
            _row(ui, key, "main_version"),
        )
        ui.check(f"{key} names no changed field", _row(ui, key, "fields") == "", _row(ui, key, "fields"))
        ui.check(f"{key} is not in conflict", not _flagged(ui, key), _row(ui, key, "conflict"))
        ui.check(
            f"{key} offers nothing to take", _row(ui, key, "resolution") == "", _row(ui, key, "resolution")
        )
    ui.check(
        "the element row names the element and its type",
        NEW_ELEMENT in _row(ui, element_key, "label") and NEW_TYPE in _row(ui, element_key, "label"),
        _row(ui, element_key, "label"),
    )
    ui.check(
        "the element row carries the identifier the application minted",
        _row(ui, element_key, "entity_id") == new_id,
        _row(ui, element_key, "entity_id"),
    )
    rel_label = _row(ui, rel_key, "label")
    ui.check("the relationship row says it is a relationship", _row(ui, rel_key, "kind") == "relationship")
    ui.check("the relationship row names the relationship in words", "contains" in rel_label, rel_label)
    ui.check("and names the element at the far end", OTHER_CAP_NAME in rel_label, rel_label)
    ui.check("and never falls back to a raw type identifier", "__" not in rel_label, rel_label)
    ui.shot("The merge log of a branch that adds an element and a relationship")
    item = _accordion_item(ui, new_id)
    ui.must("the accordion carries the new element", item.count() > 0, new_id)
    item.locator("[class*='Accordion-control']").first.click()
    ui.settle()
    body = item.inner_text()
    ui.check("the entry shows the branch's name for it", NEW_ELEMENT in body, body[:300])
    ui.check("and main's side of the row as empty", "—" in body, body[:300])
    anchor = item.locator("a").filter(has_text=re.compile("open on this branch")).first
    ui.check("an added element can be opened from the merge log", anchor.count() > 0)
    ui.check(
        "and the link points at the element itself",
        (anchor.get_attribute("href") if anchor.count() else "") == f"/element/{new_id}",
        anchor.get_attribute("href") if anchor.count() else "",
    )
    ui.shot("'What each row changes' for an added element: main's side is empty")
    ui.branch("main")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I20",
    group="I",
    title="Merging the added rows writes both the element and its relationship to main",
    feature="Branches · merge · added rows",
    expected=(
        "Neither the element nor the relationship exists on main before the merge; merging both rows "
        "writes them, closes the branch, and main's element page then carries the relationship."
    ),
)
def test_merge_added_rows(ui, record):
    _branches(ui, ADDED_ID)
    element_key = _key_of(ui, "element")
    ui.must(
        "the branch still holds its two rows", len(ui.grid_row_ids(GRID)) == 2, f"{ui.grid_row_ids(GRID)}"
    )
    new_id = _row(ui, element_key, "entity_id")
    ui.must("the merge log names the element it would write", new_id.startswith("CAP-"), new_id)
    ui.check("main does not carry the element yet", _name_on_screen(ui, new_id) == "", new_id)
    ui.check(
        "and the far end has no such relationship on main",
        NEW_ELEMENT not in _rel_tables(ui, OTHER_CAP),
        _rel_tables(ui, OTHER_CAP)[:200],
    )
    _branches(ui, ADDED_ID)
    ui.check("both rows are ticked", all(_included(ui, k) for k in ui.grid_row_ids(GRID)))
    ui.shot("The branch that adds two rows, both ticked for the merge")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check("both rows are written to main", "Merged 2 row(s) to main" in feedback, feedback)
    ui.check("and the branch closes, nothing remaining", "the branch is now merged and closed" in feedback)
    ui.shot("Both added rows are merged and the branch closes")
    ui.check("main now carries the element", _name_on_screen(ui, new_id) == NEW_ELEMENT, new_id)
    tables = _rel_tables(ui, new_id)
    ui.check("main's element carries the relationship too", OTHER_CAP_NAME in tables, tables[:300])
    ui.check("and names it in words", "contains" in tables, tables[:300])
    ui.shot("On main the merged element carries the relationship the branch drew")
    _branches(ui)


# ============================================================ merging nothing, and the tick-all


@pytest.mark.scenario(
    scenario_id="I21",
    group="I",
    title="Merging with nothing ticked is refused, and the branch is left as it was",
    feature="Branches · merge · nothing ticked",
    expected=(
        "The grid's header tick clears every row; Merge then says to tick at least one row, writes "
        "nothing to main, and leaves the row on the branch. The head also links the work package the "
        "branch was created for."
    ),
)
def test_merge_nothing_ticked(ui, record, finding):
    kept_before = _element_name(ui, M2)
    _branches(ui, MERGE_ID)
    wp_link = ui.page.locator("#br-detail a[href='/element/WP-CMS-UPGRADE']").first
    ui.check("the head links the work package the branch belongs to", wp_link.count() > 0)
    ui.check(
        "and the link is labelled with the work package",
        WP_LABEL in (wp_link.inner_text() if wp_link.count() else ""),
        wp_link.inner_text() if wp_link.count() else "",
    )
    keys = ui.grid_row_ids(GRID)
    ui.must("the branch left open still holds its one row", len(keys) == 1, f"{keys}")
    header_used = _set_all_included(ui, False)
    ui.check("the grid offers a tick-all in its header", header_used)
    ui.must("no row is ticked any more", not any(_included(ui, k) for k in keys), f"{keys}")
    ui.shot("Every row unticked, from the tick-all in the grid's header")
    ui.click("br-merge")
    feedback = ui.text("br-feedback")
    ui.check(
        "the merge is refused for want of a row",
        "Tick at least one row to merge." in feedback,
        feedback,
    )
    ui.check("the row is still on the branch", ui.grid_row_ids(GRID) == keys, f"{ui.grid_row_ids(GRID)}")
    ui.check("the branch is still open", "open" in ui.text("br-detail")[:200].lower())
    ui.shot("Merging nothing says to tick a row, and changes neither the branch nor main")
    ui.check(
        "and main is untouched",
        _element_name(ui, M2) == kept_before,
        f"main says {_element_name(ui, M2)!r}, expected {kept_before!r}",
    )
    _branches(ui, MERGE_ID)
    _set_all_included(ui, True)
    ui.check("the header tick puts every row back", all(_included(ui, k) for k in ui.grid_row_ids(GRID)))
    _branches(ui)
    if not header_used:
        finding.append(
            Finding(
                finding_id="I-6",
                where="src/ea/ui/pages/branches.py · GRID_COLUMNS, the include column (BR_GRID)",
                severity="usability",
                summary="The merge log's include column declares a tick-all in its header and draws none",
                detail=(
                    "The column carries `headerCheckboxSelection: True` beside its `checkboxSelection`, "
                    "but no checkbox is rendered in the header of the merge log, so the only way to "
                    "clear a change set is to untick every row in turn. On the branches this round "
                    "builds that is one or two clicks; on the change set of an import or an applied "
                    "proposal, which is what the page is for, it is one click per row. The row ticks "
                    "themselves work, so this is the header alone."
                ),
            )
        )


# ============================================== i-abandon: a deletion, and the branch thrown away


@pytest.mark.scenario(
    scenario_id="I22",
    group="I",
    title="A relationship deleted on a branch is a 'deleted' row in the merge log",
    feature="Branches · merge log · deleted rows",
    expected=(
        "Removing a relationship while on a branch leaves main alone and shows the removal as a "
        "deleted row: coloured as a deletion, named in words, with the branch's side of the row empty "
        "and nothing to open. The architect who wrote the branch may abandon it; somebody else's, not."
    ),
    role="architect",
    branch=ABANDON_ID,
)
def test_deleted_row(ui, record):
    ui.persona("Architect")
    _branches(ui)
    _new_branch(
        ui,
        "branch-new-open-page",
        ABANDON_BRANCH,
        "Group I: one rename and one deletion, both thrown away.",
    )
    before = _element_name(ui, D3)
    feedback = _rename(ui, D3, f"{before} (I abandoned)")
    ui.must("the definition was renamed on the branch", "Saved version" in feedback, feedback[:120])
    _tab(ui, "Relationships")
    row = ui.page.locator("#el-rel-tables tr").filter(has_text=re.compile(re.escape(D3_REL))).first
    ui.must("the relationship to be deleted is listed", row.count() > 0, D3_REL)
    row.locator("button").last.click()
    ui.settle()
    ui.page.wait_for_timeout(300)
    removed = ui.text("el-rel-feedback")
    ui.must("the page says it removed the relationship", "removed" in removed.lower(), removed)
    ui.shot("On the branch the relationship is gone from the definition's tables")
    _branches(ui, ABANDON_ID)
    detail = ui.text("br-detail")
    ui.check("the head counts the rename", "1 changed" in detail.lower(), detail[:200])
    ui.check("and the deletion", "1 deleted" in detail.lower(), detail[:200])
    ui.check("and nothing added", "0 added" in detail.lower(), detail[:200])
    rel_key = _key_of(ui, "relationship")
    ui.must("the merge log holds the deleted relationship", bool(rel_key), f"{ui.grid_row_ids(GRID)}")
    ui.check(
        "the row says it is a deletion", _row(ui, rel_key, "change") == "deleted", _row(ui, rel_key, "change")
    )
    ui.check(
        "and is coloured as one",
        "ea-deleted" in _cell_class(ui, rel_key, "change"),
        _cell_class(ui, rel_key, "change"),
    )
    label = _row(ui, rel_key, "label")
    ui.check("the row names both ends of what is going", "Enrolled Student" in label, label)
    ui.check("including the far end", D3_REL in label, label)
    ui.check("and the relationship in words", "relates to" in label, label)
    ui.shot("The merge log of a branch that deletes a relationship")
    item = _accordion_item(ui, rel_key.split(":", 1)[1])
    ui.must("the accordion carries the deleted relationship", item.count() > 0, rel_key)
    item.locator("[class*='Accordion-control']").first.click()
    ui.settle()
    body = item.inner_text()
    ui.check("the entry shows the branch's side of the row as empty", "—" in body, body[:300])
    ui.check(
        "and offers nothing to open, the row being on its way out",
        item.locator("a").filter(has_text=re.compile("open on this branch")).count() == 0,
    )
    ui.shot("'What each row changes' for a deletion: main's row, and nothing on the branch's side")
    ui.check("the architect may abandon the branch they wrote", not ui.disabled("br-abandon"))
    _branches(ui, MERGE_ID)
    ui.check("but not one somebody else wrote", ui.disabled("br-abandon"), "br-abandon on " + MERGE_ID)
    ui.shot("Abandon is offered on the architect's own branch and refused on the admin's")
    ui.branch("main")
    _branches(ui)


@pytest.mark.scenario(
    scenario_id="I23",
    group="I",
    title="Abandoning a branch discards its rows, and main never saw them",
    feature="Branches · abandon",
    expected=(
        "Abandon says the rows are discarded and main untouched; the branch is closed, empty and "
        "listed under Abandoned, its buttons are disabled, the selector no longer offers it, the "
        "reader who was standing on it is returned to main, and main still carries both the name and "
        "the relationship the branch was going to change."
    ),
    role="architect",
    branch=ABANDON_ID,
)
def test_abandon_a_branch(ui, record, finding):
    ui.persona("Architect")
    main_name = _element_name(ui, D3)
    main_rels = _rel_tables(ui, D3)
    ui.must("main still has the relationship the branch deleted", D3_REL in main_rels, main_rels[:200])
    ui.branch(ABANDON_BRANCH)
    _branches(ui, ABANDON_ID)
    ui.must(
        "the reader is standing on the branch they are about to abandon",
        "You are on this branch" in ui.text("br-switch"),
        ui.text("br-switch"),
    )
    ui.check("the branch holds two rows", len(ui.grid_row_ids(GRID)) == 2, f"{ui.grid_row_ids(GRID)}")
    ui.shot("The branch about to be abandoned, with the reader standing on it")
    ui.click("br-abandon")
    feedback = ui.text("br-feedback")
    ui.check("the page says the rows are discarded", "its rows are discarded" in feedback, feedback)
    ui.check("and that main is untouched", "main is untouched" in feedback, feedback)
    ui.check("and names the branch it threw away", ABANDON_ID in feedback, feedback)
    detail = ui.text("br-detail")
    ui.check("the head reads abandoned", "abandoned" in detail[:300].lower(), detail[:300])
    ui.check("and says who closed it", "closed by architect@example.edu" in detail, detail[:400])
    for wanted in ("0 added", "0 changed", "0 deleted", "0 conflicts"):
        ui.check(f"the head counts '{wanted}'", wanted in detail.lower(), detail[:300])
    ui.check("the review panel says the branch is abandoned", "This branch is abandoned." in detail)
    ui.check(
        "the merge log says what it held is gone",
        "This branch is closed; what it held was merged or discarded" in detail,
        detail[:600],
    )
    ui.check("nothing is left in the merge log", ui.grid_row_ids(GRID) == [], f"{ui.grid_row_ids(GRID)}")
    for control, what in (("br-switch", "Switch"), ("br-abandon", "Abandon"), ("br-merge", "Merge")):
        ui.check(f"{what} is disabled on an abandoned branch", ui.disabled(control), control)
    ui.check(
        "the reader who was on it is returned to main",
        ui.branch_badge().strip().lower() == "main",
        ui.branch_badge(),
    )
    # The header has moved the reader to main; the line above the list is written by the page
    # and no callback owns it, so it may still name the branch that has just been thrown away.
    stale = f"You are on {ABANDON_ID} as" in ui.text("page")
    ui.check(
        "and the page agrees with the header about where the reader is standing",
        not stale,
        ui.text("page")[:200],
    )
    ui.shot("The abandoned branch: closed, empty, its buttons disabled and the reader back on main")
    if stale:
        finding.append(
            Finding(
                finding_id="I-7",
                where="src/ea/ui/pages/branches.py · render (the 'You are on …' line) beside the merge and abandon callback",
                severity="defect",
                summary="After a branch closes under the reader, the page still says they are standing on it",
                detail=(
                    "`render` writes 'You are on {ctx.branch()} as {ctx.role_label()}.' into the page "
                    "body, and no callback owns that line. When Abandon (or a merge that closes the "
                    "branch) moves the reader back to main, the callback re-renders the branch detail, "
                    "the list and the header selector — but not that sentence, which goes on naming the "
                    "branch that has just been discarded while the badge a few centimetres above it "
                    "already reads main. Two statements about where the reader is standing, on the same "
                    "screen, disagreeing; the one that is wrong is the one written in words. A reader "
                    "who believes it and goes to Browse to make the next edit is editing main."
                ),
            )
        )
    listing = _listing_for(ui, "Abandoned")
    ui.check("it is listed under Abandoned", ABANDON_BRANCH in listing, listing[:200])
    badges = [
        b.strip().lower() for b in ui.page.locator("#br-list tbody tr td:nth-child(2)").all_inner_texts()
    ]
    ui.check("every row that filter lists is abandoned", badges and all(b == "abandoned" for b in badges))
    ui.shot("The Abandoned filter, which had nothing to list before")
    options = _branch_options(ui)
    ui.check("the selector no longer offers it", not any(ABANDON_BRANCH in o for o in options), f"{options}")
    ui.check(
        "main kept the name the branch was going to change",
        _element_name(ui, D3) == main_name,
        f"main says {_element_name(ui, D3)!r}, expected {main_name!r}",
    )
    kept = _rel_tables(ui, D3)
    ui.check("and kept the relationship the branch deleted", D3_REL in kept, kept[:200])
    ui.shot("Main is exactly as it was: the abandoned branch wrote nothing")
    _branches(ui)


# ==================================================== i-pending: half a review, and a send-back


@pytest.mark.scenario(
    scenario_id="I24",
    group="I",
    title="Approving one of the two types leaves the branch in review with the rest pending",
    feature="Branches · review · a partial approval",
    expected=(
        "A branch touching two element types lists both as pending; the reviewer takes one out of the "
        "approval control, approves the other, and the branch stays in review with one type approved "
        "against their name and the other still pending."
    ),
    role="reviewer",
    branch=PENDING_ID,
)
def test_a_partial_approval(ui, record, finding):
    ui.persona("Architect")
    _branches(ui)
    _new_branch(ui, "branch-new-open", PENDING_BRANCH, "Group I: two types, one approved and one not.")
    for element_id in (P2, T1):
        before = _element_name(ui, element_id)
        feedback = _rename(ui, element_id, f"{before} (I pending)")
        ui.must(f"{element_id} was changed on the branch", "Saved version" in feedback, feedback[:120])
    _branches(ui, PENDING_ID)
    ui.check("the head counts both rows", "2 changed" in ui.text("br-detail").lower())
    ui.click("rv-request")
    reqs = _requirements(ui)
    ui.must("the panel lists a row per type the branch touches", len(reqs) == 2, f"{reqs}")
    ui.check(
        "and names both types",
        {r[0] for r in reqs} == {"Data Product", "Logical Technology Component"},
        f"{reqs}",
    )
    ui.check(
        "with nobody assigned, any reviewer may decide", all("any reviewer" in r[1] for r in reqs), f"{reqs}"
    )
    ui.check("and neither is decided yet", all(r[2] == "pending" for r in reqs), f"{reqs}")
    ui.shot("The branch in review: two types touched, neither decided")
    ui.branch("main")
    ui.persona("Reviewer")
    _branches(ui, PENDING_ID)
    ui.must("the reviewer is offered both types to approve", len(_pills(ui)) == 2, f"{_pills(ui)}")
    _deselect_type(ui, "Logical Technology Component")
    ui.must("only the Data Product is left in the control", _pills(ui) == ["Data Product"], f"{_pills(ui)}")
    ui.shot("The reviewer approves one type and leaves the other for somebody else")
    ui.click("rv-approve")
    feedback = ui.text("br-feedback")
    ui.check("the approval names the type it approved", "Approved Data Product" in feedback, feedback)
    ui.check("and says the branch is not finished", "still pending" in feedback, feedback)
    # Everywhere else the panel calls a type by its name; in this one sentence the pending
    # types are printed as their raw identifiers. Measured here, reported below.
    named = "Logical Technology Component" in feedback
    ui.check(
        "and names what is still pending the way the panel names types everywhere else",
        named,
        f"the message reads {feedback!r}",
    )
    detail = ui.text("br-detail")
    ui.check("the branch is still in review", "in review" in detail[:300].lower(), detail[:300])
    reqs = _requirements(ui)
    decisions = {r[0]: r[2] for r in reqs}
    ui.check(
        "the Data Product is recorded as approved by its reviewer",
        "approved by reviewer@example.edu" in decisions.get("Data Product", ""),
        f"{reqs}",
    )
    ui.check(
        "and the other type is still pending",
        decisions.get("Logical Technology Component") == "pending",
        f"{reqs}",
    )
    ui.check("so the merge is still refused to a reviewer", ui.disabled("br-merge"))
    ui.check(
        "and only the undecided type is still on offer",
        _pills(ui) == ["Logical Technology Component"],
        f"{_pills(ui)}",
    )
    ui.shot("One type approved against the reviewer's name, one still pending")
    if not named:
        finding.append(
            Finding(
                finding_id="I-4",
                where="src/ea/ui/pages/branches.py · the `review` callback, the approval message",
                severity="usability",
                summary="The approval message names the approved type but prints the pending ones as raw identifiers",
                detail=(
                    "The message is built as 'Approved ' + the display names of the approved types + "
                    "'; still pending: ' + ', '.join(out['pending']), and `pending` holds type ids, not "
                    f"names. The reviewer therefore reads {feedback!r} — one half of the same sentence "
                    "in the language of the screen ('Data Product') and the other half in the language "
                    "of the pack ('logical_technology_component'), which appears nowhere else on the "
                    "page: the requirement table above it, the badges and the history all use the "
                    "type's name. The fix is the mapping the same callback already applies to the "
                    "approved types."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="I25",
    group="I",
    title="A send-back with a comment reopens the branch and voids the approval it had",
    feature="Branches · review · send back",
    expected=(
        "Sent back with a comment, the branch is open again and the comment is recorded against its "
        "reviewer; the approval given before it no longer counts, and the author may write on the "
        "branch again and ask for another review."
    ),
    role="reviewer",
    branch=PENDING_ID,
)
def test_send_back_with_a_comment(ui, record):
    comment = "Split the platform change out: it needs its own branch."
    ui.persona("Reviewer")
    _branches(ui, PENDING_ID)
    ui.must("the branch is still in review", "in review" in ui.text("br-detail")[:300].lower())
    ui.fill("rv-comment", comment)
    ui.shot("The reviewer has said what must change before sending the branch back")
    ui.click("rv-send-back")
    feedback = ui.text("br-feedback")
    ui.check(
        "the page says the branch went back to its author", "Sent back to the author" in feedback, feedback
    )
    ui.check("and that it is open again", "the branch is open again" in feedback, feedback)
    detail = ui.text("br-detail")
    ui.check("the head reads open", "open" in detail[:300].lower(), detail[:300])
    ui.check("the decision is recorded against its reviewer", "reviewer@example.edu sent back" in detail)
    ui.check("with the comment that was given", comment in detail, detail[:800])
    ui.check(
        "the approval it had before is still in the history",
        "reviewer@example.edu approved" in detail,
        detail[:800],
    )
    reqs = _requirements(ui)
    ui.check(
        "but no longer counts: every type is pending again",
        len(reqs) == 2 and all(r[2] == "pending" for r in reqs),
        f"{reqs}",
    )
    ui.check(
        "and the panel asks for the review to be requested afresh",
        "Not yet in review" in detail,
        detail[:600],
    )
    ui.shot("Sent back: open again, the comment recorded and the earlier approval void")
    ui.persona("Architect")
    ui.branch(PENDING_BRANCH)
    current = _element_name(ui, P2)
    saved = _rename(ui, P2, f"{current} (after the send back)")
    ui.check("the freeze is lifted, so the author may write again", "Saved version" in saved, saved[:160])
    _branches(ui, PENDING_ID)
    ui.check("and may ask for another review", ui.visible("rv-request"))
    ui.shot("Back with its author: the branch is writable again and a review can be asked for afresh")
    ui.click("br-abandon")  # leave the round with the one open branch it started this group with
    ui.must("the branch is closed again", "abandoned" in ui.text("br-detail")[:300].lower())
    _branches(ui)


# ================================================================ a branch that is not there


@pytest.mark.scenario(
    scenario_id="I26",
    group="I",
    title="A branch that does not exist is said so, and the page keeps working around it",
    feature="Branches · a missing branch",
    expected=(
        "Asking for a branch that does not exist answers 'No branch <id>.' rather than an empty page, "
        "the list above still holds the branches that do exist, and the status control above it still "
        "filters that list."
    ),
)
def test_a_branch_that_is_not_there(ui, record, finding):
    _branches(ui, "i-nope")
    detail = ui.text("br-detail")
    ui.check("the page says there is no such branch", "No branch i-nope." in detail, detail[:200])
    ui.check(
        "and does not fall over", "failed to render" not in ui.text("page").lower(), ui.text("page")[:200]
    )
    listing = ui.text("br-list")
    ui.check("the list still holds the branch that is open", MERGE_BRANCH in listing, listing[:200])
    ui.shot("A branch that does not exist: the page says so and lists the branches that do")
    ui.segmented("br-status", "Merged")
    active = ui.page.locator("#br-status label[data-active]").first
    moved = active.inner_text().strip() if active.count() else ""
    if not moved:
        chosen = ui.page.locator("#br-status input:checked").first
        moved = (chosen.get_attribute("value") if chosen.count() else "") or ""
    ui.check("the status control moved to Merged", moved.lower() == "merged", f"it reads {moved!r}")
    merged = ui.text("br-list")
    # What matters is that the list was re-read for the status that was asked for. Naming a
    # branch that should drop out is brittle: this group merges branches of its own, and a
    # merged one belongs in the merged list. Read the status column rather than the table's
    # text: every row carries an `Open` button, so the text says 'open' whatever is listed.
    cells = ui.page.locator("#br-list tbody tr td:nth-child(2)")
    statuses = [t.strip().lower() for t in cells.all_inner_texts()] if cells.count() else []
    filtered = all(s == "merged" for s in statuses) if statuses else "No merged branches" in merged
    ui.check(
        "and the list is re-read for that status, with nothing open left in it",
        filtered,
        f"the status column reads {statuses}" if statuses else f"the list reads {merged[:120]!r}",
    )
    ui.shot("The status control after asking for Merged on a branch the page could not draw")
    _branches(ui)
    if not filtered:
        finding.append(
            Finding(
                finding_id="I-5",
                where="src/ea/ui/pages/branches.py · the `filter_list` callback, State(BR_SELECTED)",
                severity="defect",
                summary="The status filter stops working whenever the branch detail below it cannot be drawn",
                detail=(
                    "`filter_list` reads `State(ids.BR_SELECTED, 'data')`, and that store is created "
                    "inside `_detail`, so it exists only when a branch could be rendered. When the "
                    "query names a branch that does not exist the detail is an alert instead, and on a "
                    "repository with no branch at all it is 'Pick a branch above.' — in both cases the "
                    "store is absent, the callback's State refers to a component that is not on the "
                    "page, and the front end refuses to run it. The control still moves under the "
                    "pointer and the list never changes, with nothing said: the page looks broken and "
                    "gives no reason. The store belongs beside the control that reads it, at the top "
                    "of the page, not inside the panel it describes."
                ),
            )
        )
