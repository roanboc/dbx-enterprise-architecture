"""Group G — Propose: from a pasted design page to a change set applied to a branch.

The round runs on the stub reader — no model key, no network — and that is the honest
setting for this page: the stub reads the Proposal Template's tables and nothing else, so
every scenario here is reproducible and the one thing a hosted reader would add (free
prose) is asserted as the refusal it is.

The page is a pipeline with a gate in the middle. Panel 1 says where the change lands (a
branch, and the work package it belongs to); panel 2 takes the document. Analyse turns the
document into a change set — each element matched against the repository, each relationship
resolved against the metamodel — and what it cannot settle comes back as *pushback* rather
than as a guess. Only when the pushback is empty may the change set be applied, and then
only to a branch, never to main.

The template is the fixture the page ships with, so the group pastes the template's own
content. Four of its five elements already exist in the sample model (the workflow, the
curriculum management system, the sync and the forms server), one does not
(`CAW_Unit_Proposal`), and every one of its five relationships is legal in the metamodel —
so a correct reader links four, adopts one, resolves five, and pushes back on the one thing
the template deliberately leaves blank: the work package.

Nothing here asserts a total another group could move. The branch this group applies to is
named `g-proposal` so it cannot collide, and it is left open — merging belongs to group I.
A later scenario asks for that same branch name a second time, which the repository refuses,
so the round never writes the same change set twice.

Beyond the template the group hands the page every other source it accepts — a Markdown file
and a CSV dropped on the upload zone, a link it will not follow, and nothing at all, which is
the case the page itself suggests when there is no document — and pastes three short documents
whose only purpose is to be wrong in one way each, so that what the reader refuses is on the
record beside what it accepts. The last scenario reads the template back on the branch the
round applied to: the only proof that what the apply reported is what it wrote, and that main
was left alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "templates" / "proposal-template.md").read_text(encoding="utf-8")

# The proposal box is a markdown editor, so its textarea carries a pattern-matching id.
PASTE = '[id=\'{"id":"pr-text","type":"md-text"}\']'

WP_LABEL = "Curriculum Management System Upgrade"  # the sample model's one work package
WP_ID = "WP-CMS-UPGRADE"
NEW_WP = "G-CAW rollout"  # named for this group, and only ever created on a branch
BRANCH = "g-proposal"

# What the template's Elements table should become against the sample model.
LINKED = {"e0": "PAC-CAW", "e2": "PAC-CMS", "e3": "INT-CMS-SRS", "e4": "PTC-FORMS"}
NEW_ROW = "e1"  # CAW_Unit_Proposal — the one element the sample model does not carry

FREE_TEXT = (
    "We would like to retire the legacy forms server next year and move unit approval into "
    "a workflow application, so that academic staff stop emailing documents around. "
    "The curriculum management system stays, and the sync into student records is unchanged."
)


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    ui.goto("/propose")
    ui.must("the Propose page rendered its proposal box", ui.page.locator(PASTE).count() > 0)


def _paste(ui, text: str) -> None:
    box = ui.page.locator(PASTE).first
    box.click()
    box.fill(text)
    ui.settle()


def _open_select(ui, select_id: str) -> list[str]:
    """Open a select and read the labels it offers, leaving the dropdown open.

    Every select on the page keeps its option list mounted, so only the visible ones
    belong to the select that was just opened.
    """
    ui.click(select_id)
    return [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]


def _pick(ui, label: str) -> None:
    """Choose an option from the dropdown that is open."""
    options = ui.page.locator("[role='option']:visible")
    options.filter(has_text=re.compile(re.escape(label))).first.click()
    ui.settle()


def _close_select(ui) -> None:
    ui.page.keyboard.press("Escape")
    ui.settle()


def _analyse(ui, text: str = TEMPLATE, work_package: str | None = WP_LABEL) -> None:
    """Choose the work package (the destination is read when Analyse is pressed), paste, analyse."""
    if work_package:
        ui.select("pr-wp", work_package)
    _paste(ui, text)
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    ui.settle()


def _result(ui) -> str:
    return ui.text("pr-result")


def _pushback(ui) -> str:
    return ui.text("pr-pushback")


def _blocked(ui) -> bool:
    return "Not enough to apply" in _pushback(ui)


def _head(ui) -> str:
    """The line above the pushback block: the counts, the work package, and who read it."""
    return ui.text("#pr-result .mantine-Group-root")


def _counts(ui) -> str:
    """The three count badges, which the theme renders in upper case."""
    return _head(ui).lower()


def _overflow(ui, grid_id: str, row_id: str, col: str) -> float:
    """How far a cell sticks out past the right edge of its grid, in pixels."""
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id='{row_id}'] .ag-cell[col-id='{col}']").first
    if not cell.count():
        return 0.0
    box, grid = cell.bounding_box(), ui.page.locator(f"#{grid_id}").first.bounding_box()
    if not box or not grid:
        return 0.0
    return max(0.0, (box["x"] + box["width"]) - (grid["x"] + grid["width"]))


# --------------------------------------------------------------------------- the scenarios


@pytest.mark.scenario(
    scenario_id="G01",
    group="G",
    title="The Propose page offers a destination, a document and the reader that will read it",
    feature="Propose · the page",
    expected=(
        "The page names the stub reader in a badge and shows two panels: where the change lands "
        "(branch, work package, the template to download) and the proposal itself (a paste box, "
        "an upload zone, links and Analyse). Nothing is analysed until Analyse is pressed."
    ),
)
def test_page(ui, record):
    _open(ui)
    ui.check("the page is titled 'Propose a change'", "Propose a change" in ui.body())
    badge = ui.text("pr-provider")
    ui.check(
        "the reader badge names the stub reader",
        badge.lower().startswith("reader:") and "stub" in badge.lower(),
        f"badge reads {badge!r}",
    )
    ui.check(
        "the badge does not claim a model is configured",
        "·" not in badge,
        f"badge reads {badge!r}",
    )
    ui.check("panel 1 says where the change lands", "1 · Where it lands" in ui.body())
    ui.check("panel 2 takes the proposal", "2 · The proposal" in ui.body())
    for control in ("pr-branch", "pr-wp", "pr-template", "pr-upload", "pr-links", "pr-analyse"):
        ui.check(f"{control} is offered", ui.visible(control))
    ui.check("the paste box is offered", ui.page.locator(PASTE).first.is_visible())
    ui.check(
        "the page says the template's tables work without a model key",
        "its tables work without a model key" in ui.body(),
    )
    ui.check(
        "the page says rows can be added by hand when there is no document",
        "add the rows by hand" in ui.body(),
    )
    ui.check("nothing is analysed yet, so there is no change set", _result(ui) == "")
    ui.shot(
        "The Propose page before anything is handed in: the reader badge reads stub, panel 1 chooses "
        "the branch and the work package, panel 2 takes the document"
    )


@pytest.mark.scenario(
    scenario_id="G02",
    group="G",
    title="Choosing 'New branch' reveals the field that names it",
    feature="Propose · destination · branch",
    expected=(
        "The New branch name field is hidden until New branch is chosen; it then appears and says "
        "the branch is named after the proposal when the field is left empty."
    ),
)
def test_new_branch_field(ui, record):
    _open(ui)
    ui.check(
        "the New branch name field is hidden until it is needed",
        not ui.visible("pr-branch-new"),
    )
    ui.check(
        "its label is not shown either",
        "New branch name" not in ui.body(),
    )
    labels = _open_select(ui, "pr-branch")
    ui.check(
        "the branch select offers to create a new branch",
        any("New branch" in x for x in labels),
        f"options: {labels}",
    )
    _pick(ui, "New branch")
    ui.check("choosing New branch reveals the name field", ui.visible("pr-branch-new"))
    ui.check("the revealed field is labelled", "New branch name" in ui.body())
    placeholder = ui.page.locator("#pr-branch-new").first.get_attribute("placeholder") or ""
    ui.check(
        "the field says what happens when it is left empty",
        "Named after the proposal" in placeholder,
        f"placeholder reads {placeholder!r}",
    )
    ui.shot("Choosing 'New branch' has revealed the field that names it, with the default explained")


@pytest.mark.scenario(
    scenario_id="G03",
    group="G",
    title="The work package select offers the model's initiatives, and a field for a new one",
    feature="Propose · destination · work package",
    expected=(
        "The select lists the work packages the model carries; choosing New work package reveals a "
        "name field, and choosing an existing work package hides it again."
    ),
)
def test_work_package_field(ui, record):
    _open(ui)
    ui.check("the New work package name field is hidden until it is needed", not ui.visible("pr-wp-new"))
    labels = _open_select(ui, "pr-wp")
    ui.check(
        "the select offers the sample model's work package with its identifier",
        any(WP_LABEL in x and WP_ID in x for x in labels),
        f"options: {labels}",
    )
    ui.check(
        "the select offers to name a new work package",
        any("New work package" in x for x in labels),
        f"options: {labels}",
    )
    _pick(ui, "New work package")
    ui.check("choosing New work package reveals the name field", ui.visible("pr-wp-new"))
    ui.check("the revealed field is labelled", "New work package name" in ui.body())
    ui.shot("The work package select lists the model's initiatives and can name a new one")
    ui.select("pr-wp", WP_LABEL)
    ui.check(
        "choosing an existing work package hides the new-name field again",
        not ui.visible("pr-wp-new"),
    )


@pytest.mark.scenario(
    scenario_id="G04",
    group="G",
    title="Download Proposal Template hands back the template the reader can read",
    feature="Propose · the template",
    expected=(
        "The button downloads proposal-template.md, and the file carries the Elements and "
        "Relationships tables the stub reader parses, byte for byte as the repository holds it."
    ),
)
def test_download_template(ui, record):
    _open(ui)
    path = ui.download("pr-template", ".md")
    text = path.read_text(encoding="utf-8")
    ui.check("the file is the template the repository holds", text == TEMPLATE)
    ui.check("it carries an Elements section", "## Elements" in text)
    ui.check("it carries a Relationships section", "## Relationships" in text)
    ui.check(
        "the Elements table names the columns the reader maps",
        "| Type | Name | Existing id | Description | Current state | Target state |" in text,
    )
    ui.check(
        "the Relationships table names the columns the reader maps",
        "| Source | Relationship | Target | Note |" in text,
    )
    ui.check(
        "it explains the two state vocabularies",
        "proposed" in text and "decommission" in text,
    )
    ui.shot("The Propose page after the template has been downloaded")


@pytest.mark.scenario(
    scenario_id="G05",
    group="G",
    title="Free prose under the stub reader is pushed back, not guessed at",
    feature="Propose · pushback",
    expected=(
        "Pasting prose with no tables returns no elements and no relationships: the pushback says "
        "no language model is configured, that only the template's tables can be read, and that an "
        "Elements table is needed."
    ),
)
def test_free_text_is_pushed_back(ui, record):
    _open(ui)
    _analyse(ui, FREE_TEXT, work_package=None)
    ui.must("the page answered with a change set panel", _result(ui) != "")
    ui.check("nothing was applied — the change set is blocked", _blocked(ui))
    text = _pushback(ui)
    ui.check(
        "the pushback says no language model is configured",
        "No language model is configured" in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "it says only the Proposal Template's tables can be read",
        "only the Proposal Template's tables can be read" in text,
    )
    ui.check(
        "it says an Elements table is what is missing",
        "No elements were identified" in text and "Add an Elements table" in text,
    )
    ui.check(
        "it asks for the work package too",
        "Name the work package" in text,
    )
    counts = _counts(ui)
    ui.check(
        "nothing was invented: no new element, none linked, no relationship",
        "0 new" in counts and "0 linked" in counts and "0 relationships" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check("both grids came back empty", ui.grid_row_count("pr-el-grid") == 0)
    ui.check("the relationship grid came back empty", ui.grid_row_count("pr-rel-grid") == 0)
    ui.shot(
        "Free prose under the stub reader: nothing is guessed at, and the pushback says what the "
        "reader needs instead"
    )


@pytest.mark.scenario(
    scenario_id="G06",
    group="G",
    title="The template's own content links the elements that exist and adopts the new one",
    feature="Propose · analysis",
    expected=(
        "Pasting the Proposal Template returns five element rows — the four the sample model "
        "already carries linked to their identifiers, CAW_Unit_Proposal adopted as new — and five "
        "relationships each resolved to a relationship type of the metamodel."
    ),
)
def test_template_analysis(ui, record):
    _open(ui)
    _analyse(ui, TEMPLATE, work_package=None)  # no work package yet: that is G07's pushback
    ui.must("the change set came back", ui.grid_row_count("pr-el-grid") > 0)
    counts = _counts(ui)
    ui.check(
        "one element is adopted as new and four are linked",
        "1 new" in counts and "4 linked" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check(
        "all five relationships were carried through",
        "5 relationships" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check(
        "the counts line says which reader read it",
        "read by stub" in _head(ui),
        f"the counts line reads {_head(ui)!r}",
    )
    ui.check("the elements grid holds the template's five rows", ui.grid_row_count("pr-el-grid") == 5)
    ui.check(
        "the relationships grid holds the template's five rows",
        ui.grid_row_count("pr-rel-grid") == 5,
    )
    for key, element_id in LINKED.items():
        ui.check(
            f"{element_id} was recognised and linked",
            ui.grid_cell_of("pr-el-grid", key, "action") == "link"
            and ui.grid_cell_of("pr-el-grid", key, "existing_id") == element_id,
            f"row {key} reads action={ui.grid_cell_of('pr-el-grid', key, 'action')!r} "
            f"existing id={ui.grid_cell_of('pr-el-grid', key, 'existing_id')!r}",
        )
    ui.check(
        "the element the model does not carry is adopted as new",
        ui.grid_cell_of("pr-el-grid", NEW_ROW, "action") == "new"
        and ui.grid_cell_of("pr-el-grid", NEW_ROW, "name") == "CAW_Unit_Proposal"
        and ui.grid_cell_of("pr-el-grid", NEW_ROW, "existing_id") == "",
        f"row {NEW_ROW} reads {ui.grid_cell_of('pr-el-grid', NEW_ROW, 'name')!r} / "
        f"{ui.grid_cell_of('pr-el-grid', NEW_ROW, 'existing_id')!r}",
    )
    ui.check(
        "the new element keeps the states the template proposed",
        ui.grid_cell_of("pr-el-grid", NEW_ROW, "current_state") == "proposed"
        and ui.grid_cell_of("pr-el-grid", NEW_ROW, "target_state") == "new",
    )
    ui.check(
        "the linked element the template only re-states carries no issue",
        ui.grid_cell_of("pr-el-grid", "e2", "issues") == "",
        f"issues read {ui.grid_cell_of('pr-el-grid', 'e2', 'issues')!r}",
    )
    resolved = [ui.grid_cell_of("pr-rel-grid", f"r{i}", "resolved") for i in range(5)]
    ui.check(
        "every relationship resolved to a type of the metamodel",
        all(resolved) and all("__" in r for r in resolved),
        f"resolved column reads {resolved}",
    )
    ui.check(
        "the first relationship resolved to the one the metamodel names",
        resolved[0] == "physical_application_component__processes__data_entity",
        f"row 1 resolved to {resolved[0]!r}",
    )
    issues = [ui.grid_cell_of("pr-rel-grid", f"r{i}", "issues") for i in range(5)]
    ui.check("no relationship was left with an issue", not any(issues), f"issues read {issues}")
    ui.shot(
        "The template read against the model: four elements linked to their identifiers, "
        "CAW_Unit_Proposal adopted as new, and every relationship resolved"
    )


@pytest.mark.scenario(
    scenario_id="G07",
    group="G",
    title="Without a work package the proposal is blocked, and Apply refuses to write",
    feature="Propose · pushback · apply",
    expected=(
        "The template names no work package, so the pushback asks for one and says the change set "
        "is not enough to apply; pressing Apply writes nothing and says why."
    ),
)
def test_apply_refuses_while_blocked(ui, record):
    _open(ui)
    _analyse(ui, TEMPLATE, work_package=None)
    ui.must("the change set came back", ui.grid_row_count("pr-el-grid") > 0)
    text = _pushback(ui)
    ui.check("the change set is marked as not enough to apply", _blocked(ui), f"{text!r}")
    ui.check(
        "the one thing missing is the work package",
        "Name the work package" in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "nothing else is being asked for",
        len([line for line in text.splitlines() if line.strip().startswith(("Element", "Relationship"))])
        == 0,
        f"pushback reads {text!r}",
    )
    ui.check(
        "the counts panel says the work package is not named",
        "Work package: not named" in _head(ui),
        f"the counts line reads {_head(ui)!r}",
    )
    ui.check("Apply to branch is offered to an admin", not ui.disabled("pr-apply"))
    ui.click("pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.check(
        "Apply refuses and says where to look",
        "Not applied" in feedback and "see what is missing above" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.shot("Apply refused: the work package is still missing, and the refusal says where to look")


@pytest.mark.scenario(
    scenario_id="G08",
    group="G",
    title="Naming the work package clears the pushback and says whether it exists",
    feature="Propose · destination · work package",
    expected=(
        "Analysing with a new work package name says it will be created; analysing with the model's "
        "own work package says it exists, and the change set is then ready to apply."
    ),
)
def test_work_package_clears_the_pushback(ui, record):
    _open(ui)
    ui.select("pr-wp", "New work package")
    ui.fill("pr-wp-new", NEW_WP)
    _paste(ui, TEMPLATE)
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    head = _head(ui)
    ui.check(
        "a work package that does not exist is reported as one that will be created",
        f"Work package: {NEW_WP} (will be created)" in head,
        f"the counts line reads {head!r}",
    )
    ui.check("naming it clears the pushback", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.shot("A work package named but not yet in the model: the panel says it will be created")

    _open(ui)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    head = _head(ui)
    ui.check(
        "the model's own work package is recognised as existing",
        f"Work package: {WP_ID} (existing)" in head or f"Work package: {WP_LABEL} (existing)" in head,
        f"the counts line reads {head!r}",
    )
    ui.check("the change set is no longer blocked", not _blocked(ui), f"{_pushback(ui)!r}")
    ui.check(
        "the panel says the change set may be applied",
        "apply it to a branch when the rows read right" in _pushback(ui),
        f"panel reads {_pushback(ui)!r}",
    )
    ui.shot("With the work package named, every row is identified and the change set may be applied")


@pytest.mark.scenario(
    scenario_id="G09",
    group="G",
    title="A row added by hand is checked like every other, and Re-check says what it lacks",
    feature="Propose · editable merge log · elements",
    expected=(
        "Add element row appends an editable row ticked for inclusion; typing a name into it and "
        "pressing Re-check rows returns it with its own issues — no type, no description — named by "
        "its row number in the pushback."
    ),
)
def test_add_element_row(ui, record, finding):
    _open(ui)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    before = ui.grid_row_count("pr-el-grid")
    ui.must("the change set came back", before == 5)
    ui.click("pr-add-el")
    ui.check("the grid gained a row", ui.grid_row_count("pr-el-grid") == before + 1, f"was {before}")
    added = "m1-5"  # the key the page gives the first row added to a five-row grid
    ui.must(
        "the added row is addressable",
        added in ui.grid_row_ids("pr-el-grid"),
        f"row ids are {ui.grid_row_ids('pr-el-grid')}",
    )
    ui.check(
        "the added row starts as a new element in the proposed state",
        ui.grid_cell_of("pr-el-grid", added, "action") == "new"
        and ui.grid_cell_of("pr-el-grid", added, "current_state") == "proposed"
        and ui.grid_cell_of("pr-el-grid", added, "target_state") == "new",
    )
    ui.grid_set_of("pr-el-grid", added, "name", "G-Approval Notification Service")
    ui.check(
        "the name typed into the row was kept",
        ui.grid_cell_of("pr-el-grid", added, "name") == "G-Approval Notification Service",
        f"cell reads {ui.grid_cell_of('pr-el-grid', added, 'name')!r}",
    )
    ui.shot("A row added by hand, named in place, before it has been re-checked")
    ui.click("pr-analyse-again")
    ui.check("Re-check kept the six rows", ui.grid_row_count("pr-el-grid") == 6)
    issues = ui.grid_cell_of("pr-el-grid", "e5", "issues")
    ui.check(
        "the re-checked row is told it has no type",
        "type is missing" in issues,
        f"issues read {issues!r}",
    )
    ui.check(
        "and that it has no description",
        "description is missing" in issues,
        f"issues read {issues!r}",
    )
    text = _pushback(ui)
    ui.check("the change set is blocked again", _blocked(ui), f"pushback reads {text!r}")
    ui.check(
        "the pushback names the row by its number and its name",
        "Element row 6 (G-Approval Notification Service)" in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "the rows that were already right are not complained about",
        "CAW_Unit_Proposal" not in text,
        f"pushback reads {text!r}",
    )
    ui.shot("Re-check rows: the hand-added row is held to the same standard as the ones that were read")
    # The issues column is the one that says why a row is blocked, and it is the last of ten.
    overflow = _overflow(ui, "pr-el-grid", "e5", "issues")
    if overflow > 1:
        finding.append(
            Finding(
                finding_id="G-1",
                where="src/ea/ui/pages/propose.py · element_columns (PR_EL_GRID)",
                severity="usability",
                summary="The issues column of the elements grid is off the right edge on a wide screen",
                detail=(
                    "Ten columns are declared for the change set, so on a 1600 px window the last of "
                    f"them — issues, the column that says why a row cannot be applied — starts "
                    f"{overflow:.0f} px past the right edge of the grid and can only be read by "
                    "scrolling it sideways. The pushback block above repeats the same text, so nothing "
                    "is lost, but the architect who is correcting a row in the grid cannot see what is "
                    "wrong with it while editing."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="G10",
    group="G",
    title="A relationship added by hand is resolved against the metamodel, and unticking it clears it",
    feature="Propose · editable merge log · relationships",
    expected=(
        "Add relationship row appends an editable row; a relationship to something the model does "
        "not carry comes back with that as its issue, and unticking the row takes it out of the "
        "pushback."
    ),
)
def test_add_relationship_row(ui, record):
    _open(ui)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    before = ui.grid_row_count("pr-rel-grid")
    ui.must("the change set came back", before == 5)
    ui.click("pr-add-rel")
    ui.check("the grid gained a row", ui.grid_row_count("pr-rel-grid") == before + 1, f"was {before}")
    added = "m1-5"
    ui.must(
        "the added row is addressable",
        added in ui.grid_row_ids("pr-rel-grid"),
        f"row ids are {ui.grid_row_ids('pr-rel-grid')}",
    )
    ui.grid_set_of("pr-rel-grid", added, "source", "Curriculum Management System")
    ui.grid_set_of("pr-rel-grid", added, "relationship", "processes")
    ui.grid_set_of("pr-rel-grid", added, "target", "G-Nothing Of That Name")
    ui.check(
        "what was typed into the row was kept",
        ui.grid_cell_of("pr-rel-grid", added, "target") == "G-Nothing Of That Name",
        f"cell reads {ui.grid_cell_of('pr-rel-grid', added, 'target')!r}",
    )
    ui.click("pr-analyse-again")
    ui.check("Re-check kept the six rows", ui.grid_row_count("pr-rel-grid") == 6)
    issues = ui.grid_cell_of("pr-rel-grid", "r5", "issues")
    ui.check(
        "the row is told its target is in neither the table nor the repository",
        "G-Nothing Of That Name" in issues
        and "neither in the Elements table nor in the repository" in issues,
        f"issues read {issues!r}",
    )
    ui.check(
        "the pushback names the relationship row by its number",
        "Relationship row 6" in _pushback(ui),
        f"pushback reads {_pushback(ui)!r}",
    )
    ui.shot("A relationship to something the model does not carry, named as the issue it is")
    ui.grid_tick("pr-rel-grid", [5])
    ui.click("pr-analyse-again")
    ui.check(
        "unticking the row takes it out of the pushback",
        "Relationship row 6" not in _pushback(ui),
        f"pushback reads {_pushback(ui)!r}",
    )
    ui.check(
        "and the change set is ready to apply again",
        not _blocked(ui),
        f"pushback reads {_pushback(ui)!r}",
    )
    ui.check(
        "the row is still there, left out rather than deleted",
        ui.grid_row_count("pr-rel-grid") == 6,
    )
    ui.shot("The unticked row is left out of the change set rather than deleted, and the block lifts")


@pytest.mark.scenario(
    scenario_id="G11",
    group="G",
    title="Applying to a new branch reports what it created and links to the branch",
    feature="Propose · apply",
    expected=(
        "With the destination set to a new branch named g-proposal, Apply writes the change set to "
        "that branch — one element created as proposed, four linked, five relationships — says so, "
        "and links to the branch and to the work package's target state."
    ),
)
def test_apply_to_a_new_branch(ui, record):
    _open(ui)
    ui.select("pr-branch", "New branch")
    ui.fill("pr-branch-new", BRANCH)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    ui.must("the change set is ready to apply", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.click("pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.must("Apply reported what it did", feedback != "")
    ui.check(
        "it names the branch it wrote to",
        f"Applied to branch {BRANCH}" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.check(
        "it says one element was created as proposed",
        "1 element(s) created as proposed" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.check(
        "it says four existing elements were linked",
        "4 linked" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.check(
        "it says five relationships were written",
        "5 relationship(s) written" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.check("nothing was skipped", "skipped" not in feedback, f"feedback reads {feedback!r}")
    branch_link = ui.page.locator(f"#pr-apply-feedback a[href='/branches?branch={BRANCH}']")
    ui.check(
        "it links to the branch it created, for review and merge",
        branch_link.count() == 1,
        f"links: {ui.page.locator('#pr-apply-feedback a').all_inner_texts()}",
    )
    wp_link = ui.page.locator(f"#pr-apply-feedback a[href='/target?wp={WP_ID}']")
    ui.check(
        "it links to the target state of the work package it landed in",
        wp_link.count() == 1,
        f"hrefs: {[a.get_attribute('href') for a in ui.page.locator('#pr-apply-feedback a').all()]}",
    )
    ui.shot("Applied: the page reports what it created, what it linked, and links to the branch")
    labels = _open_select(ui, "branch-select")
    ui.check(
        "the header offers the new branch without a reload",
        any(x.startswith(BRANCH) for x in labels),
        f"header options: {labels}",
    )
    _close_select(ui)


@pytest.mark.scenario(
    scenario_id="G12",
    group="G",
    title="The branch the proposal created is offered as a destination for the next one",
    feature="Propose · destination · branch",
    expected=(
        "Re-opening Propose lists g-proposal among the open branches with the number of changes it "
        "holds, and choosing it leaves the New branch name field hidden."
    ),
)
def test_branch_is_offered_afterwards(ui, record):
    _open(ui)
    labels = _open_select(ui, "pr-branch")
    mine = [x for x in labels if x.startswith(BRANCH)]
    ui.must("the branch the proposal created is offered", bool(mine), f"options: {labels}")
    count = re.search(r"\((\d+)\)", mine[0])
    ui.check(
        "it is offered with the number of changes it holds",
        count is not None and int(count.group(1)) > 0,
        f"option reads {mine[0]!r}",
    )
    _pick(ui, BRANCH)
    ui.check(
        "choosing an existing branch does not ask for a new name",
        not ui.visible("pr-branch-new"),
    )
    ui.check("the model itself is not offered as a destination", "main" not in labels, f"options: {labels}")
    ui.shot("The branch the proposal created, offered as the destination for the next proposal")


@pytest.mark.scenario(
    scenario_id="G13",
    group="G",
    title="Applying the same proposal again to a branch of the same name is refused",
    feature="Propose · apply · negative path",
    expected=(
        "g-proposal already exists, so a second Apply that asks for a new branch of that name is "
        "refused with a message naming the branch, and nothing is written."
    ),
)
def test_applying_twice_is_refused(ui, record):
    _open(ui)
    ui.select("pr-branch", "New branch")
    ui.fill("pr-branch-new", BRANCH)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    ui.must("the change set is ready to apply", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.click("pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.must("Apply answered", feedback != "")
    ui.check(
        "the second attempt is refused",
        feedback.startswith("Not applied"),
        f"feedback reads {feedback!r}",
    )
    ui.check(
        "the refusal names the branch that is in the way",
        BRANCH in feedback and "already exists" in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.check(
        "nothing is reported as written a second time",
        "created as proposed" not in feedback,
        f"feedback reads {feedback!r}",
    )
    ui.shot("A second apply to a branch name that is taken: refused, and the refusal names the branch")


# ------------------------------------------------- the documents the round hands in as files

# Every document below is ASCII, so the number of characters the upload list reports is the
# number of characters the file holds.

UPLOAD_MD = """# Proposal: G hands in a file

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |

## Summary

One element that exists and one that does not, so the file is read exactly as pasted text is.

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Physical Application Component | Curriculum Management System | PAC-CMS | | live | change |
| Data Entity | G-CAW_Review_Comment | | A reviewer's comment on a unit proposal, kept with the proposal through approval. | proposed | new |

## Relationships

| Source | Relationship | Target | Note |
| ------ | ------------ | ------ | ---- |
| Curriculum Management System | processes | G-CAW_Review_Comment | the comments live with the curriculum |
"""

UPLOAD_CSV = (
    "Type,Name,Existing id,Description,Current state,Target state\n"
    "Physical Technology Component,Legacy Forms Server,PTC-FORMS,,live,decommission\n"
    "Data Entity,G-CAW_Approval_Record,,"
    '"The record of who approved a unit proposal and when, kept for audit.",proposed,new\n'
)

# The work package the document names, against a different one chosen in the panel.
WP_DOC = """# Proposal: G checks whose work package wins

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Physical Application Component | Curriculum Management System | PAC-CMS | | live | change |
"""

# Four element rows, each wrong in its own way, and nothing else wrong with them.
EL_DOC = """# Proposal: G checks what the reader cannot settle

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Physical Application Component | Curriculum Management System | PAC-NOSUCH | | live | change |
| Fairy Dust Component | G-Sparkle Service | | A service of a type the metamodel does not carry, so the reader cannot place it. | proposed | new |
| Physical Application Component | Curriculum Managment System | | A misspelling of an application that already exists, so the reader should offer the one it found. | proposed | new |
| Data Entity | CMS_Unit_Outline | DE-CMS-UNIT-OUTLINE | | alive | change |
"""

# Two ends the repository already carries, and four relationships between them: one the
# metamodel allows, one it does not, one with a role it does not carry, one with a role it does.
REL_DOC = """# Proposal: G checks the relationships the metamodel refuses

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Physical Technology Component | Legacy Forms Server | PTC-FORMS | | live | decommission |
| Data Entity | CMS_Unit_Outline | DE-CMS-UNIT-OUTLINE | | live | change |

## Relationships

| Source | Relationship | Target | Qualifier | Note |
| ------ | ------------ | ------ | --------- | ---- |
| Legacy Forms Server | stores | CMS_Unit_Outline | | the metamodel allows this one |
| Legacy Forms Server | processes | CMS_Unit_Outline | | the metamodel does not |
| Manager, Curriculum Systems | position__is_steward_of__information_asset | Unit Outlines | Chief Wizard | a role the type does not carry |
| Manager, Curriculum Systems | is Owner / Data Custodian / Data Steward / Data Administrator of | Unit Outlines | Data Steward | a role it does |
"""

BAD_LINK = "ftp://example.invalid/g-design.md"  # a scheme the fetcher refuses, so nothing is fetched

HAND_NAME = "G-Unit Approval Notice"
HAND_TYPE = "Data Entity"
HAND_DESC = "The notice sent to a course coordinator when a unit proposal has been approved."


# ------------------------------------------------------------------- the controls (continued)


def _write(ui, name: str, text: str) -> Path:
    """Put a file where the browser can pick it up, beside the run's other evidence."""
    d = ui.run_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_text(text, encoding="utf-8")
    return path


def _upload(ui, *paths: Path) -> None:
    """Hand files to the hidden input inside the upload zone, the way the picker does."""
    ui.page.locator("#pr-upload input[type=file]").first.set_input_files([str(p) for p in paths])
    for p in paths:
        ui.page.locator("#pr-files").get_by_text(p.name, exact=False).first.wait_for(timeout=20_000)
    ui.settle()


def _press_analyse(ui) -> None:
    """Analyse what the page already holds — an uploaded file, a link, or nothing at all."""
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    ui.settle()


def _pasted(ui) -> str:
    return ui.page.locator(PASTE).first.input_value()


def _head_alert(ui) -> str:
    """The alert above the change set, where a source that could not be read is reported."""
    loc = ui.page.locator("#pr-result [class*='Alert-root']").first
    return loc.inner_text().strip() if loc.count() else ""


def _long_editor(ui, grid_id: str):
    """The textarea of a popup cell editor, wherever the grid chose to mount it."""
    return ui.page.locator(
        f"#{grid_id} textarea, .ag-popup-editor textarea, .ag-popup textarea, .ag-large-text textarea"
    ).first


def _set_long_text(ui, grid_id: str, row_id: str, col: str, value: str) -> None:
    """Fill a popup text editor: it opens over the grid and commits when it loses focus."""
    cell = ui.page.locator(f"#{grid_id} .ag-row[row-id='{row_id}'] .ag-cell[col-id='{col}']").first
    cell.scroll_into_view_if_needed()
    cell.click()
    editor = _long_editor(ui, grid_id)
    try:
        editor.wait_for(timeout=5_000)
    except Exception:  # noqa: BLE001 — a single click did not open it; a double click does
        cell.dblclick()
        editor = _long_editor(ui, grid_id)
        editor.wait_for(timeout=10_000)
    editor.fill(value)
    ui.page.locator("#pr-result .ea-section-title").first.click()  # inert text: the editor blurs
    ui.settle()


# ------------------------------------------------------------------ the scenarios (continued)


@pytest.mark.scenario(
    scenario_id="G14",
    group="G",
    title="With nothing handed in the page asks for a document, and the rows can be typed instead",
    feature="Propose · no document",
    expected=(
        "Analyse with an empty box returns an empty change set that asks for an Elements table and "
        "complains about nothing else; Add element row then builds a row by hand — named, typed and "
        "described in the grid — until the change set is ready to apply."
    ),
)
def test_analyse_with_nothing(ui, record, finding):
    _open(ui)
    ui.select("pr-wp", WP_LABEL)
    _press_analyse(ui)
    ui.must("the page answered with a change set panel", _result(ui) != "")
    counts = _counts(ui)
    ui.check(
        "nothing was read, so the change set is empty",
        "0 new" in counts and "0 linked" in counts and "0 relationships" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check("the elements grid is empty", ui.grid_row_count("pr-el-grid") == 0)
    ui.check("the relationships grid is empty", ui.grid_row_count("pr-rel-grid") == 0)
    text = _pushback(ui)
    ui.check("the change set is not enough to apply", _blocked(ui), f"pushback reads {text!r}")
    ui.check(
        "it asks for an Elements table",
        "No elements were identified" in text and "Add an Elements table" in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "it does not complain about a language model — nothing was handed in to read",
        "No language model is configured" not in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "the work package chosen in the panel is already accepted",
        f"Work package: {WP_ID} (existing)" in _head(ui),
        f"the counts line reads {_head(ui)!r}",
    )
    ui.shot("Analyse with nothing handed in: an empty change set that asks for a document")

    ui.click("pr-add-el")
    added = "m1-0"  # the key the page gives the first row added to an empty grid
    ui.must(
        "a row can be added to an empty grid",
        added in ui.grid_row_ids("pr-el-grid"),
        f"row ids are {ui.grid_row_ids('pr-el-grid')}",
    )
    ui.grid_set_of("pr-el-grid", added, "name", HAND_NAME)
    ui.grid_set_of("pr-el-grid", added, "type", HAND_TYPE)
    ui.check(
        "the type cell offers the metamodel's types and keeps the one chosen",
        ui.grid_cell_of("pr-el-grid", added, "type") == HAND_TYPE,
        f"cell reads {ui.grid_cell_of('pr-el-grid', added, 'type')!r}",
    )
    ui.click("pr-analyse-again")
    ui.must("the typed row became the change set", ui.grid_row_count("pr-el-grid") == 1)
    ui.check(
        "it is adopted as a new element of the type that was chosen",
        ui.grid_cell_of("pr-el-grid", "e0", "action") == "new"
        and ui.grid_cell_of("pr-el-grid", "e0", "name") == HAND_NAME
        and ui.grid_cell_of("pr-el-grid", "e0", "type") == HAND_TYPE,
        f"row reads {ui.grid_cell_of('pr-el-grid', 'e0', 'action')!r} / "
        f"{ui.grid_cell_of('pr-el-grid', 'e0', 'type')!r}",
    )
    ui.check("the counts line now says one new element", "1 new" in _counts(ui), _counts(ui))
    text = _pushback(ui)
    ui.check(
        "the one thing still missing is the description",
        f"Element row 1 ({HAND_NAME}): description is missing" in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "nothing else is asked for",
        "type is missing" not in text and "name is missing" not in text,
        f"pushback reads {text!r}",
    )
    ui.shot("A row typed into an empty grid: named and typed, still asking for a description")

    _set_long_text(ui, "pr-el-grid", "e0", "description", HAND_DESC)
    ui.check(
        "the description typed into the row was kept",
        ui.grid_cell_of("pr-el-grid", "e0", "description") == HAND_DESC,
        f"cell reads {ui.grid_cell_of('pr-el-grid', 'e0', 'description')!r}",
    )
    ui.click("pr-analyse-again")
    ui.check(
        "a row built entirely by hand is ready to apply",
        not _blocked(ui),
        f"pushback reads {_pushback(ui)!r}",
    )
    ui.check(
        "and it carries no issue of its own",
        ui.grid_cell_of("pr-el-grid", "e0", "issues") == "",
        f"issues read {ui.grid_cell_of('pr-el-grid', 'e0', 'issues')!r}",
    )
    ui.shot("The hand-built change set, complete: one new element and nothing left to add")
    head, badge = _head(ui), ui.text("pr-provider")
    if "read by manual" in head and "stub" in badge.lower():
        finding.append(
            Finding(
                finding_id="G-2",
                where="src/ea/ui/pages/propose.py · _preview (the counts line)",
                severity="consistency",
                summary="The counts line says 'read by manual' where the reader's name goes",
                detail=(
                    "After Analyse with nothing pasted, and after every Re-check rows, the counts line "
                    f"reads {head.splitlines()[-1] if head else ''!r} while the page badge reads "
                    f"{badge!r}. 'manual' sits in exactly the slot the provider's name sits in after a "
                    "document has been read ('read by stub'), so it reads as the name of a third reader "
                    "rather than as 'these rows came from you, not from a document'."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="G15",
    group="G",
    title="A Markdown file dropped on the page is read exactly as pasted text is",
    feature="Propose · sources · upload",
    expected=(
        "The upload zone lists the file with the number of characters it holds, and Analyse with the "
        "paste box empty returns that file's change set: the element it names by id linked, the one it "
        "does not adopt as new, its relationship resolved, and its work package taken from the document."
    ),
)
def test_upload_markdown(ui, record):
    _open(ui)
    ui.check("nothing is listed before a file is handed in", ui.text("pr-files") == "", ui.text("pr-files"))
    path = _write(ui, "g-proposal-upload.md", UPLOAD_MD)
    _upload(ui, path)
    listed = ui.text("pr-files")
    ui.check("the file is listed by name", path.name in listed, f"the list reads {listed!r}")
    ui.check(
        "and by the number of characters read from it",
        f"{len(UPLOAD_MD)} chars" in listed,
        f"the list reads {listed!r}",
    )
    ui.shot("A Markdown proposal handed in as a file, listed with the characters read from it")
    ui.must("the paste box was left empty", _pasted(ui) == "", f"the box holds {_pasted(ui)!r}")
    _press_analyse(ui)
    ui.must("the file was read into a change set", ui.grid_row_count("pr-el-grid") == 2)
    counts = _counts(ui)
    ui.check(
        "one element is linked and one adopted as new",
        "1 new" in counts and "1 linked" in counts and "1 relationships" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check(
        "the element the file names by id is linked to it",
        ui.grid_cell_of("pr-el-grid", "e0", "action") == "link"
        and ui.grid_cell_of("pr-el-grid", "e0", "existing_id") == "PAC-CMS",
        f"row reads {ui.grid_cell_of('pr-el-grid', 'e0', 'existing_id')!r}",
    )
    ui.check(
        "the element the repository does not carry is adopted as new",
        ui.grid_cell_of("pr-el-grid", "e1", "action") == "new"
        and ui.grid_cell_of("pr-el-grid", "e1", "name") == "G-CAW_Review_Comment",
        f"row reads {ui.grid_cell_of('pr-el-grid', 'e1', 'name')!r}",
    )
    ui.check(
        "the file's relationship resolved against the metamodel",
        ui.grid_cell_of("pr-rel-grid", "r0", "resolved")
        == "physical_application_component__processes__data_entity",
        f"resolved reads {ui.grid_cell_of('pr-rel-grid', 'r0', 'resolved')!r}",
    )
    ui.check(
        "the work package came from the file, though none was chosen in the panel",
        f"Work package: {WP_ID} (existing)" in _head(ui),
        f"the counts line reads {_head(ui)!r}",
    )
    ui.check("nothing is left to add", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.shot("The uploaded file read: one element linked, one new, its relationship resolved")


@pytest.mark.scenario(
    scenario_id="G16",
    group="G",
    title="A CSV of the Elements columns is read too, and the panel supplies the work package",
    feature="Propose · sources · upload",
    expected=(
        "A .csv with the template's Elements columns is parsed like the table it is: the row naming an "
        "existing id is linked and keeps its decommission target, the other is adopted as new, and "
        "because the file names no work package the one chosen in panel 1 is used."
    ),
)
def test_upload_csv(ui, record):
    _open(ui)
    ui.select("pr-wp", WP_LABEL)
    path = _write(ui, "g-elements.csv", UPLOAD_CSV)
    _upload(ui, path)
    listed = ui.text("pr-files")
    ui.check("the CSV is listed by name", path.name in listed, f"the list reads {listed!r}")
    _press_analyse(ui)
    ui.must("the CSV was read into a change set", ui.grid_row_count("pr-el-grid") == 2)
    counts = _counts(ui)
    ui.check(
        "one row is linked and one is new",
        "1 new" in counts and "1 linked" in counts,
        f"the counts line reads {counts!r}",
    )
    ui.check(
        "the row naming an existing id is linked to it and keeps the target the CSV gives",
        ui.grid_cell_of("pr-el-grid", "e0", "existing_id") == "PTC-FORMS"
        and ui.grid_cell_of("pr-el-grid", "e0", "target_state") == "decommission",
        f"row reads {ui.grid_cell_of('pr-el-grid', 'e0', 'existing_id')!r} / "
        f"{ui.grid_cell_of('pr-el-grid', 'e0', 'target_state')!r}",
    )
    ui.check(
        "the other row is adopted as new, with the description the CSV quoted",
        ui.grid_cell_of("pr-el-grid", "e1", "action") == "new"
        and ui.grid_cell_of("pr-el-grid", "e1", "name") == "G-CAW_Approval_Record"
        and "kept for audit" in ui.grid_cell_of("pr-el-grid", "e1", "description"),
        f"row reads {ui.grid_cell_of('pr-el-grid', 'e1', 'description')!r}",
    )
    ui.check("a CSV of elements carries no relationships", ui.grid_row_count("pr-rel-grid") == 0)
    ui.check(
        "the work package chosen in the panel filled the gap the file left",
        f"Work package: {WP_ID} (existing)" in _head(ui),
        f"the counts line reads {_head(ui)!r}",
    )
    ui.check("the change set is ready to apply", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.shot("A CSV of the Elements columns, read as the table it is")


@pytest.mark.scenario(
    scenario_id="G17",
    group="G",
    title="The work package the document names wins over the one chosen in the panel",
    feature="Propose · destination · work package",
    expected=(
        "The panel says the document's own says wins. With a new work package name typed into panel 1 "
        "and a document naming WP-CMS-UPGRADE, the change set lands in WP-CMS-UPGRADE and the typed "
        "name is not used."
    ),
)
def test_document_work_package_wins(ui, record):
    _open(ui)
    ui.check(
        "the panel says the document's own work package wins when it names one",
        "the document's own says wins when it names one" in ui.body(),
    )
    ui.select("pr-wp", "New work package")
    ui.fill("pr-wp-new", NEW_WP)
    _analyse(ui, WP_DOC, work_package=None)
    head = _head(ui)
    ui.must("the document was read", ui.grid_row_count("pr-el-grid") == 1)
    ui.check(
        "the work package the document names is the one used, and it exists",
        f"Work package: {WP_ID} (existing)" in head,
        f"the counts line reads {head!r}",
    )
    ui.check(
        "the name typed into the panel was not used",
        NEW_WP not in head and "will be created" not in head,
        f"the counts line reads {head!r}",
    )
    ui.check("the change set is ready to apply", not _blocked(ui), f"pushback reads {_pushback(ui)!r}")
    ui.shot("The document names WP-CMS-UPGRADE, so the new name typed in the panel is not used")


@pytest.mark.scenario(
    scenario_id="G18",
    group="G",
    title="Every element the reader cannot settle says why, row by row",
    feature="Propose · pushback · elements",
    expected=(
        "An identifier that is not in the repository, a type that is not in the metamodel, a name one "
        "letter from an element that exists, and a state outside the vocabulary each come back as that "
        "row's own issue and as a numbered line in the pushback; the change set is blocked."
    ),
)
def test_element_issues(ui, record, finding):
    _open(ui)
    _analyse(ui, EL_DOC, work_package=None)
    ui.must("the four rows came back", ui.grid_row_count("pr-el-grid") == 4)
    issues = {key: ui.grid_cell_of("pr-el-grid", key, "issues") for key in ("e0", "e1", "e2", "e3")}
    ui.check(
        "the identifier that is not in the repository is named as the problem",
        "existing id 'PAC-NOSUCH' is not in the repository" in issues["e0"],
        f"row 1 issues read {issues['e0']!r}",
    )
    ui.check(
        "the row is still linked by its name, so the identifier is the only thing wrong with it",
        ui.grid_cell_of("pr-el-grid", "e0", "action") == "link"
        and ui.grid_cell_of("pr-el-grid", "e0", "existing_id") == "PAC-CMS",
        f"row 1 reads {ui.grid_cell_of('pr-el-grid', 'e0', 'existing_id')!r}",
    )
    ui.check(
        "the type that is not in the metamodel is named as the problem",
        "type 'Fairy Dust Component' is not in the metamodel" in issues["e1"],
        f"row 2 issues read {issues['e1']!r}",
    )
    ui.check(
        "the misspelled name is answered with the element that exists and its identifier",
        "a similar element exists" in issues["e2"] and "[PAC-CMS]" in issues["e2"],
        f"row 3 issues read {issues['e2']!r}",
    )
    ui.check(
        "and with what to do about it",
        "put its id in Existing id to link it, or keep it new" in issues["e2"],
        f"row 3 issues read {issues['e2']!r}",
    )
    ui.check(
        "the state outside the vocabulary is named, with the vocabulary",
        "current state 'alive' is not one of" in issues["e3"] and "non_existent" in issues["e3"],
        f"row 4 issues read {issues['e3']!r}",
    )
    text = _pushback(ui)
    ui.check("the change set is blocked", _blocked(ui), f"pushback reads {text!r}")
    for row, name in (
        (1, "Curriculum Management System"),
        (2, "G-Sparkle Service"),
        (3, "Curriculum Managment System"),
        (4, "CMS_Unit_Outline"),
    ):
        ui.check(
            f"the pushback names row {row} by its number and its name",
            f"Element row {row} ({name})" in text,
            f"pushback reads {text!r}",
        )
    ui.check(
        "the work package the document names is not asked for again",
        "Name the work package" not in text,
        f"pushback reads {text!r}",
    )
    ui.shot("Four rows, four different reasons the reader cannot settle them")
    if "type 'Fairy Dust Component' is not in the metamodel" in issues["e1"] and (
        "type is missing" in issues["e1"]
    ):
        finding.append(
            Finding(
                finding_id="G-3",
                where="src/ea/agent/proposal.py · _resolve_element",
                severity="consistency",
                summary="A row whose type is not in the metamodel is also told its type is missing",
                detail=(
                    "The row names a type; the metamodel does not carry it. The resolver says so, then "
                    "falls through to the new-element checks and adds 'type is missing' because no type "
                    f"id was resolved, so the cell reads {issues['e1']!r} and the pushback carries both "
                    "lines for the same cell. The second contradicts what the architect can see in the "
                    "row and sends them looking for an empty cell rather than a wrong one."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="G19",
    group="G",
    title="A relationship the metamodel does not allow is refused with the ones it does",
    feature="Propose · pushback · relationships",
    expected=(
        "Between the same two elements one relationship resolves and one does not: the refusal names "
        "the two types and lists what is allowed between them. A qualifier the relationship type does "
        "not carry is refused with the roles it does carry, and the ends may be named from the "
        "repository alone."
    ),
)
def test_relationship_issues(ui, record):
    _open(ui)
    _analyse(ui, REL_DOC, work_package=None)
    ui.must("the four relationships came back", ui.grid_row_count("pr-rel-grid") == 4)
    ui.check(
        "the relationship the metamodel allows resolved",
        ui.grid_cell_of("pr-rel-grid", "r0", "resolved")
        == "physical_technology_component__stores__data_entity",
        f"row 1 resolved to {ui.grid_cell_of('pr-rel-grid', 'r0', 'resolved')!r}",
    )
    ui.check("and carries no issue", ui.grid_cell_of("pr-rel-grid", "r0", "issues") == "")
    refused = ui.grid_cell_of("pr-rel-grid", "r1", "issues")
    ui.check(
        "the one it does not allow is refused, naming both types",
        "no relationship 'processes' from Physical Technology Component to Data Entity" in refused,
        f"row 2 issues read {refused!r}",
    )
    ui.check(
        "and says what is allowed between them instead",
        "allowed: stores" in refused,
        f"row 2 issues read {refused!r}",
    )
    ui.check(
        "the refused row resolved to nothing",
        ui.grid_cell_of("pr-rel-grid", "r1", "resolved") == "",
        f"row 2 resolved to {ui.grid_cell_of('pr-rel-grid', 'r1', 'resolved')!r}",
    )
    qualifier = ui.grid_cell_of("pr-rel-grid", "r2", "issues")
    ui.check(
        "a role the relationship type does not carry is refused with the roles it does",
        "qualifier 'Chief Wizard' is not one of" in qualifier
        and "Owner, Data Custodian, Data Steward, Data Administrator" in qualifier,
        f"row 3 issues read {qualifier!r}",
    )
    ui.check(
        "the ends of that row were resolved from the repository, though the Elements table omits them",
        ui.grid_cell_of("pr-rel-grid", "r2", "resolved") == "position__is_steward_of__information_asset",
        f"row 3 resolved to {ui.grid_cell_of('pr-rel-grid', 'r2', 'resolved')!r}",
    )
    ui.check(
        "the same relationship with a role it does carry is accepted",
        ui.grid_cell_of("pr-rel-grid", "r3", "issues") == ""
        and ui.grid_cell_of("pr-rel-grid", "r3", "qualifier") == "Data Steward",
        f"row 4 issues read {ui.grid_cell_of('pr-rel-grid', 'r3', 'issues')!r}",
    )
    text = _pushback(ui)
    ui.check("the change set is blocked", _blocked(ui), f"pushback reads {text!r}")
    ui.check(
        "the pushback names the two rows it cannot settle, and only those",
        "Relationship row 2" in text
        and "Relationship row 3" in text
        and "Relationship row 1 " not in text
        and "Relationship row 4" not in text,
        f"pushback reads {text!r}",
    )
    ui.check(
        "no element was complained about",
        "Element row" not in text,
        f"pushback reads {text!r}",
    )
    ui.shot("Between the same two elements: one relationship the metamodel allows, one it refuses")


@pytest.mark.scenario(
    scenario_id="G20",
    group="G",
    title="A link that cannot be read is reported, and nothing is invented in its place",
    feature="Propose · sources · links",
    expected=(
        "A link the fetcher will not follow comes back as an alert above the change set naming the "
        "link and the reason, and the change set itself stays empty rather than being guessed at."
    ),
)
def test_unreadable_link(ui, record, finding):
    _open(ui)
    ui.fill("pr-links", BAD_LINK)
    _press_analyse(ui)
    alert = _head_alert(ui)
    ui.must("the page reported the link rather than failing silently", alert != "")
    ui.check(
        "the alert says a link could not be read",
        "Some links could not be read" in alert,
        f"the alert reads {alert!r}",
    )
    ui.check("it names the link", BAD_LINK in alert, f"the alert reads {alert!r}")
    ui.check(
        "and the reason it was not followed",
        "only http(s) links can be fetched" in alert,
        f"the alert reads {alert!r}",
    )
    body = _result(ui).lower()
    ui.check(
        "nothing was invented in its place",
        "0 new" in body and "0 linked" in body and "0 relationships" in body,
        f"the change set panel reads {body[:200]!r}",
    )
    ui.check("both grids are empty", ui.grid_row_count("pr-el-grid") == 0)
    ui.check("the relationships grid is empty too", ui.grid_row_count("pr-rel-grid") == 0)
    ui.check(
        "the change set asks for an Elements table, as it does with no source at all",
        "No elements were identified" in _pushback(ui),
        f"pushback reads {_pushback(ui)!r}",
    )
    ui.shot("A link the fetcher will not follow: reported above the change set, and nothing guessed at")
    if alert.count(BAD_LINK) > 1:
        finding.append(
            Finding(
                finding_id="G-4",
                where="src/ea/ui/pages/propose.py · _sources",
                severity="consistency",
                summary="An unreadable link is named twice in the same sentence",
                detail=(
                    "`fetch_link` raises with the URL already in the message, and `_sources` prefixes the "
                    f"URL again, so the alert reads {alert!r}. One link makes the sentence hard to read; "
                    "a list of them repeats every URL twice."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="G21",
    group="G",
    title="On the branch it wrote to, the proposal's element is already there; on main it is not",
    feature="Propose · apply · what landed",
    expected=(
        "Reading on g-proposal, Propose offers that branch as the destination and analysing the same "
        "template links all five elements, CAW_Unit_Proposal included, because the apply created it "
        "there. Back on main the same template still adopts it as new, so nothing was written to main."
    ),
)
def test_what_landed_on_the_branch(ui, record):
    ui.goto("/propose")
    ui.branch(BRANCH)
    badge = ui.branch_badge()
    ui.must(
        "the header says the reader has left the model for a branch",
        "branch" in badge.lower() and badge.strip().lower() != "main",
        f"the badge reads {badge!r}",
    )
    header = ui.page.locator("#branch-select").first.input_value()
    ui.must("the header names the branch being read", header.startswith(BRANCH), f"it reads {header!r}")
    _open(ui)
    destination = ui.page.locator("#pr-branch").first.input_value()
    ui.check(
        "Propose offers the branch being read as the destination of the next change",
        destination.startswith(BRANCH),
        f"the branch select reads {destination!r}",
    )
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    ui.must("the template was read against the branch", ui.grid_row_count("pr-el-grid") == 5)
    counts = _counts(ui)
    ui.check(
        "every element of the template is now linked, and none is new",
        "5 linked" in counts and "0 new" in counts,
        f"the counts line reads {counts!r}",
    )
    created = ui.grid_cell_of("pr-el-grid", NEW_ROW, "existing_id")
    ui.check(
        "the element the proposal created is found on the branch, with an identifier of its own",
        ui.grid_cell_of("pr-el-grid", NEW_ROW, "action") == "link"
        and ui.grid_cell_of("pr-el-grid", NEW_ROW, "name") == "CAW_Unit_Proposal"
        and created != "",
        f"row {NEW_ROW} reads {ui.grid_cell_of('pr-el-grid', NEW_ROW, 'action')!r} / {created!r}",
    )
    ui.check(
        "it was created in the state the proposal asked for",
        ui.grid_cell_of("pr-el-grid", NEW_ROW, "current_state") == "proposed",
        f"row {NEW_ROW} reads {ui.grid_cell_of('pr-el-grid', NEW_ROW, 'current_state')!r}",
    )
    ui.shot("The same template read on the branch it was applied to: every element is already there")

    ui.branch("main")
    ui.must("the reader is back on the model", ui.branch_badge().strip().lower() == "main", ui.branch_badge())
    _open(ui)
    _analyse(ui, TEMPLATE, work_package=WP_LABEL)
    ui.must("the template was read against main", ui.grid_row_count("pr-el-grid") == 5)
    ui.check(
        "on main the element is still unknown, so the apply wrote to the branch and nowhere else",
        ui.grid_cell_of("pr-el-grid", NEW_ROW, "action") == "new"
        and ui.grid_cell_of("pr-el-grid", NEW_ROW, "existing_id") == "",
        f"row {NEW_ROW} reads {ui.grid_cell_of('pr-el-grid', NEW_ROW, 'action')!r} / "
        f"{ui.grid_cell_of('pr-el-grid', NEW_ROW, 'existing_id')!r}",
    )
    ui.check(
        "and the counts on main are the ones the round started with",
        "1 new" in _counts(ui) and "4 linked" in _counts(ui),
        f"the counts line reads {_counts(ui)!r}",
    )
    ui.shot("The same template read on main: the element the branch carries is still new here")
