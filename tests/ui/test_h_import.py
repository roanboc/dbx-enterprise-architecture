"""Group H — Import: CSV files in, checked against the metamodel, then loaded.

The Import page is one pipeline with a gate in the middle. The banner at the top says
where a load would land — main changes the model directly, a branch stages it for a
merge. The left panel takes files and lists what it read from each; the right panel
says which source system the rows belong to, which mapping reads them, and offers the
three actions: download the template, validate only, load.

"Validate only" is the gate. It runs the whole pipeline — files classified by pattern,
columns renamed by the mapping, types and relationship types resolved against the pack,
states and statuses checked — and reports every issue it found without writing a row.
"Load" runs the same pipeline and writes. So the group proves the pair: the same files
report the same counts, and only the second one changes the model.

Everything this group creates is prefixed `H-` and carries the nonsense word `hqmark`
in its description, so a search finds this group's rows and nothing else, and no later
group can be moved by them. The branch it makes is `h-import`; it is left open, and the
group ends on main.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

BRANCH_NAME = "H import"
BRANCH_ID = "h-import"
SOURCE = "h-import-round"
MARKER = "hqmark"  # only this group's rows carry it, so a search returns only them

LDC = "H-LDC-ADMISSIONS"
DE = "H-DE-APPLICANT"

MAIN_BANNER = "You are on main: what you load changes the model directly."
BRANCH_BANNER = f"You are on branch {BRANCH_ID}:"
NO_FILES = "Upload at least one CSV file first."
NO_MATCH = "None of the files matched the element/relationship/link file patterns of the mapping."
DRY = "Validation only — nothing written."
LOADED = "Loaded."

ELEMENTS_CSV = (
    "id,type,name,key,description,status,lifecycle_status,current_state,target_state\n"
    f"{LDC},logical_data_component,H Admissions Data,H001,"
    f"The admissions data area loaded by the import round ({MARKER}).,approved,Live,live,keep\n"
    f"{DE},data_entity,H Applicant,H002,"
    f"One applicant record loaded by the import round ({MARKER}).,approved,Live,live,keep\n"
)
REVISED_CSV = ELEMENTS_CSV.replace("H Admissions Data", "H Admissions Data (revised)")
RELATIONSHIPS_CSV = f"src_id,rel_type,dst_id,qualifier,status\n{LDC},encapsulates,{DE},,approved\n"
# Three defects on purpose, one per row: a type the pack does not know, a row with no
# name, and an edge whose endpoints are nowhere — an error apiece, and nothing loaded.
BROKEN_ELEMENTS_CSV = (
    "id,type,name,description\n"
    "H-BROKEN-ONE,not_a_real_type,H Broken One,A row whose type the metamodel does not know.\n"
    "H-BROKEN-TWO,data_entity,,A row with no name at all.\n"
)
BROKEN_RELATIONSHIPS_CSV = "src_id,rel_type,dst_id\nH-BROKEN-ONE,encapsulates,H-BROKEN-MISSING\n"
# What a spreadsheet writes: a byte-order mark, CRLF endings, and a quoted description
# that wraps onto a second line.
SPREADSHEET_CSV = (
    "id,type,name,description\r\n"
    'H-DE-ENROLMENT,data_entity,H Enrolment,"A description that wraps\r\n'
    'onto a second line, and holds a comma."\r\n'
    "H-DE-OFFER,data_entity,H Offer,A second row to count.\r\n"
)
# Neither the default patterns nor the tool-export ones match this file name.
NOTES_CSV = "note\nNothing here follows the contract.\n"
# The headers an EA tool export writes: only the tool-export mapping can read them, and
# only its patterns classify a file called *object*.csv.
OBJECTS_CSV = (
    "ID,Name,Object Type,Lifecycle Status,Description\n"
    "H-PAC-PORTAL,H Applicant Portal,Physical Application Component,Live,"
    f"An application read through the tool-export mapping ({MARKER}).\n"
)

# ------------------------------------------------ what the first twelve scenarios did not reach

# A row carrying more fields than the header it declares. Read leniently it would load under
# identifiers the file never wrote, so the importer refuses the file whole.
RAGGED_CSV = (
    "id,type,name,description\n"
    "H-RAGGED-ONE,data_entity,H Ragged One,A tidy row.\n"
    "H-RAGGED-TWO,data_entity,H Ragged Two,A row with,an unquoted comma,and a field too many\n"
)
# An edge between the two elements the first load wrote, of a type the metamodel does not allow
# between them: the endpoints resolve from the model, the type does not.
BAD_REL_CSV = f"src_id,rel_type,dst_id\n{LDC},processes,{DE}\n"
# Four warnings and not one error: a status the vocabulary does not hold, a current and a target
# state it does not hold either, and the same id twice.
WARNING_CSV = (
    "id,type,name,description,status,lifecycle_status,current_state,target_state\n"
    f"H-DE-WARNED,data_entity,H Warned,A row that warns without failing ({MARKER}).,"
    "pending,Planned,sideways,maybe\n"
    f"H-DE-WARNED,data_entity,H Warned Again,The same id a second time ({MARKER}).,"
    "approved,Planned,planned,keep\n"
)
# The tool's own words rather than the pack's: a type label the pack carries under another name,
# and lifecycle text only the mapping's own table reads.
TOOL_OBJECTS_CSV = (
    "ID,Name,Object Type,Lifecycle Status,Description,Level of Logical Data Component\n"
    f"H-BD-COHORT,H Cohort,Definition,Sunset,A term read through the mapping ({MARKER}).,\n"
    f"H-LDC-ANALYTICS,H Analytics Data,Logical Data Component,Being built,"
    f"A data area read through the mapping ({MARKER}).,2\n"
)
# Two URLs in the one cell, the way the contract says to write them.
INLINE_LINKS_CSV = (
    "id,type,name,description,links\n"
    f"H-DE-LINKED,data_entity,H Linked,A row carrying two links inline ({MARKER}).,"
    "https://example.edu/one|https://example.edu/two\n"
)
# One link for an element the model already holds, one for an id that is nowhere.
LINKS_CSV = (
    "element_id,url,label\n"
    f"{LDC},https://example.edu/admissions,Admissions source page\n"
    "H-NOWHERE,https://example.edu/nowhere,A link to nothing\n"
)
# The same file name chosen twice, longer the second time.
GROWN_CSV = (
    "id,type,name,description\n"
    "H-DE-ONE,data_entity,H One,The first row of a file chosen twice.\n"
    "H-DE-TWO,data_entity,H Two,The second row of it.\n"
)
GROWN_MORE_CSV = GROWN_CSV + "H-DE-THREE,data_entity,H Three,A row added before it was chosen again.\n"
# Loaded on the branch and nowhere else, so a search that finds it names the branch it is on.
BRANCH_ONLY = "H-DE-BRANCHONLY"
BRANCH_MARKER = "hbranchonly"
BRANCH_CSV = (
    "id,type,name,description\n"
    f"{BRANCH_ONLY},data_entity,H Branch Only,A row loaded onto the branch alone "
    f"({MARKER} {BRANCH_MARKER}).\n"
)

# One error apiece, one more than the report's table will list.
OVERFLOW_ROWS = 501
OVERFLOW_CSV = "id,type,name\n" + "".join(
    f"H-OVER-{i:04d},not_a_real_type,H Over {i}\n" for i in range(OVERFLOW_ROWS)
)

NOTHING_LOADED = "Nothing was loaded."
NOT_READ = "Not read — a row does not match the header the file declares"


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    """A fresh Import page. The upload store is rebuilt empty on every render."""
    ui.goto("/import")
    ui.must("the Import page rendered its upload zone", ui.visible("im-upload"))


def _write(ui, name: str, text: str) -> Path:
    """Put a CSV where the browser can pick it up, beside the run's other evidence."""
    d = ui.run_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_text(text, encoding="utf-8")
    return path


def _upload(ui, *paths: Path) -> None:
    """Hand files to the hidden input inside the upload zone, the way the picker does."""
    ui.page.locator("#im-upload input[type=file]").first.set_input_files([str(p) for p in paths])
    for p in paths:
        ui.page.locator("#im-files").get_by_text(p.name, exact=False).first.wait_for(timeout=20_000)
    ui.settle()


def _file_row(ui, name: str) -> str:
    """What the file list says about one file: its name and the rows it read."""
    row = ui.page.locator("#im-files [class*='Group-root']").filter(has_text=name).first
    return row.inner_text().replace("\n", " ").strip() if row.count() else ""


def _tab(ui, label: str) -> None:
    """Open one of the element page's tabs by its label."""
    ui.click(f"#el-tabs [role='tab']:has-text(\"{label}\")")


def _report(ui) -> str:
    return ui.text("im-report")


def _banner(ui) -> str:
    alerts = ui.page.locator("#page [class*='Alert-root']")
    return alerts.first.inner_text().strip() if alerts.count() else ""


def _banner_background(ui) -> str:
    return ui.page.evaluate(
        "() => { const a = document.querySelector('#page [class*=\"Alert-root\"]');"
        " return a ? getComputedStyle(a).backgroundColor : ''; }"
    )


def _switch_to_branch(ui) -> None:
    """Go to this group's branch, making it the first time round."""
    ui.click("branch-select")
    options = ui.page.locator("[role='option']:visible")
    if options.filter(has_text=BRANCH_NAME).count():
        options.filter(has_text=BRANCH_NAME).first.click()
        ui.settle()
        return
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.click("branch-new-open")
    ui.fill("branch-new-name", BRANCH_NAME)
    ui.click("branch-new-save")
    ui.settle()


# ------------------------------------------------------------------------------ the page


@pytest.mark.scenario(
    scenario_id="H01",
    group="H",
    title="The Import page says where a load would land and offers the template, Validate and Load",
    feature="Import · the page on main",
    expected=(
        "On main a blue banner warns that a load changes the model directly, and an Admin sees the "
        "upload zone, the source system, the mapping, and the three buttons with Load enabled."
    ),
)
def test_page_on_main(ui, record):
    _open(ui)
    ui.check("the page is titled Import", ui.text("#page h1") == "Import", ui.text("#page h1"))
    ui.check("the banner names main and what a load there does", MAIN_BANNER in ui.body(), _banner(ui))
    for control in ("im-upload", "im-source", "im-mapping", "im-template", "im-validate", "im-load"):
        ui.check(f"{control} is on the page", ui.visible(control))
    ui.check("Load is offered to an Admin on main", not ui.disabled("im-load"))
    source = ui.page.locator("#im-source").input_value()
    ui.check("the source system is filled in ready to change", source == "tool-export", source)
    mapping = ui.page.locator("#im-mapping").input_value()
    ui.check("the mapping starts at the plain CSV contract", "No mapping" in mapping, mapping)
    ui.check(
        "the page says what the contract is and where the command line does the same",
        "connectors/README.md" in ui.body() and "ea import" in ui.body(),
    )
    ui.shot("The Import page on main: the warning banner, the upload zone, and the three actions")


@pytest.mark.scenario(
    scenario_id="H02",
    group="H",
    title="On a branch the banner changes from a warning about main to where the load will be staged",
    feature="Import · the page on a branch",
    expected=(
        "Switching to a branch in the header replaces the blue main banner with an orange one naming "
        "the branch, and says the load reaches main only when the branch is merged."
    ),
    branch=BRANCH_ID,
)
def test_banner_on_a_branch(ui, record):
    _open(ui)
    on_main, main_bg = _banner(ui), _banner_background(ui)
    ui.must("the main banner was read", MAIN_BANNER in on_main, on_main)
    _switch_to_branch(ui)
    badge = ui.branch_badge().lower()
    ui.must("the header shows a branch rather than main", "branch" in badge and badge != "main", badge)
    on_branch, branch_bg = _banner(ui), _banner_background(ui)
    ui.check("the banner names the branch the load would land on", BRANCH_BANNER in on_branch, on_branch)
    ui.check(
        "it says the load reaches main only through a merge",
        "reaches main when it is merged" in on_branch,
        on_branch,
    )
    ui.check("the two banners say different things", on_branch != on_main)
    ui.check(
        "and are coloured differently, so the difference is visible before it is read",
        branch_bg != main_bg,
        f"main {main_bg}, branch {branch_bg}",
    )
    ui.check("Load is still offered on a branch", not ui.disabled("im-load"))
    ui.shot("On a branch the Import banner turns orange and names the branch the load lands on")
    ui.branch("main")
    ui.check("switching back restores the main banner", MAIN_BANNER in _banner(ui), _banner(ui))


@pytest.mark.scenario(
    scenario_id="H03",
    group="H",
    title="Download template hands out a ZIP of the contract, and what it hands out validates",
    feature="Import · the template archive",
    expected=(
        "The button downloads ea-import-template.zip holding a README and the three contract CSVs, "
        "and uploading those files back reports no errors."
    ),
)
def test_template_archive(ui, record):
    _open(ui)
    archive = ui.download("im-template", ".zip")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        header = z.read("elements.csv").decode("utf-8").splitlines()[0]
        out = ui.run_dir / "uploads" / "h-template"
        z.extractall(out)
    for name in ("README.md", "elements.csv", "relationships.csv", "links.csv"):
        ui.check(f"the archive holds {name}", name in names, str(names))
    ui.check(
        "the elements sheet carries the contract's columns",
        all(c in header for c in ("id", "type", "name", "description", "current_state", "target_state")),
        header,
    )
    _upload(ui, out / "elements.csv", out / "relationships.csv", out / "links.csv")
    ui.click("im-validate")
    text = _report(ui)
    ui.check("validating the template writes nothing", DRY in text, text[:160])
    ui.check("the template the page hands out has no errors", "0 errors" in text, text[:200])
    ui.check("and no issues at all", "No issues." in text, text[:200])
    ui.shot("The template archive, validated straight back in: three files, no issues")


@pytest.mark.scenario(
    scenario_id="H04",
    group="H",
    title="Uploaded files are listed by name with the number of rows read from each",
    feature="Import · the file list",
    expected="Dropping two CSVs lists both, each with the row count the page read from it.",
)
def test_file_list(ui, record, finding):
    _open(ui)
    elements = _write(ui, "h-elements.csv", ELEMENTS_CSV)
    relationships = _write(ui, "h-relationships.csv", RELATIONSHIPS_CSV)
    ui.check("nothing is listed before anything is uploaded", ui.text("im-files") == "", ui.text("im-files"))
    _upload(ui, elements, relationships)
    listed = ui.text("im-files")
    ui.check("the elements file is listed", "h-elements.csv" in listed, listed)
    ui.check("the relationships file is listed", "h-relationships.csv" in listed, listed)
    ui.check(
        "the elements file reports the two data rows it holds",
        "2 rows" in _file_row(ui, "h-elements.csv"),
        _file_row(ui, "h-elements.csv"),
    )
    ui.check(
        "the relationships file reports its one data row",
        "1 row" in _file_row(ui, "h-relationships.csv"),
        _file_row(ui, "h-relationships.csv"),
    )
    ui.shot("Two uploaded CSVs, each listed with the number of rows read from it")
    if "1 rows" in _file_row(ui, "h-relationships.csv"):
        finding.append(
            Finding(
                finding_id="H1",
                where="src/ea/ui/pages/import_page.py · the file list (`im-files`)",
                severity="usability",
                summary="A one-row file is listed as '1 rows'.",
                detail=(
                    'The count is written as f"{len(t.splitlines()) - 1} rows" with no singular form, '
                    "so a file with a single data row reads '1 rows'."
                ),
            )
        )
    finding.append(
        Finding(
            finding_id="H2",
            where="src/ea/ui/pages/import_page.py · the file list (`im-files`)",
            severity="usability",
            summary="An uploaded file cannot be removed; the only way to drop one is to reload the page.",
            detail=(
                "The upload callback only ever adds to `im-store`, and the list it renders carries no "
                "remove control, so a file chosen by mistake is loaded with the rest unless the reader "
                "knows to navigate away and back."
            ),
        )
    )


# ------------------------------------------------------------------- validate, then load


@pytest.mark.scenario(
    scenario_id="H05",
    group="H",
    title="Validate only reports what it read and writes nothing",
    feature="Import · validate",
    expected=(
        "Validating two elements and one relationship says nothing was written, counts 0 of 2 elements "
        "loaded with no errors, and the elements are still absent from the model afterwards."
    ),
)
def test_validate_writes_nothing(ui, record):
    _open(ui)
    _upload(
        ui, _write(ui, "h-elements.csv", ELEMENTS_CSV), _write(ui, "h-relationships.csv", RELATIONSHIPS_CSV)
    )
    ui.fill("im-source", SOURCE)
    ui.click("im-validate")
    text = _report(ui)
    ui.check("the report says plainly that nothing was written", DRY in text, text[:160])
    ui.check("it read both elements and loaded neither", "elements 0/2 loaded" in text, text[:260])
    ui.check("and read the relationship without loading it", "relationships 0/1 loaded" in text, text[:260])
    ui.check("the files are clean", "0 errors" in text and "No issues." in text, text[:260])
    ui.check("it names the source system the rows would carry", SOURCE in text, text[:160])
    ui.shot("Validate only: what the files hold, checked against the metamodel, and nothing written")
    ui.goto(f"/element/{LDC}")
    body = ui.body()
    ui.check("the validated element is still not in the model", "Not found" in body, body[:200])
    ui.check("and the page says which id it could not find", LDC in body, body[:200])
    ui.shot("The validated element is still absent: validation wrote nothing")


@pytest.mark.scenario(
    scenario_id="H06",
    group="H",
    title="Load writes the rows, says so, and the elements are in the model",
    feature="Import · load",
    expected=(
        "Loading the same two files reports two elements and one relationship loaded, and the element "
        "page then shows the imported element with the relationship the file declared."
    ),
)
def test_load_writes(ui, record):
    _open(ui)
    _upload(
        ui, _write(ui, "h-elements.csv", ELEMENTS_CSV), _write(ui, "h-relationships.csv", RELATIONSHIPS_CSV)
    )
    ui.fill("im-source", SOURCE)
    ui.click("im-load")
    text = _report(ui)
    ui.check("the report says it loaded rather than validated", LOADED in text, text[:160])
    ui.check("both elements were written", "elements 2/2 loaded" in text, text[:260])
    ui.check("the relationship was written", "relationships 1/1 loaded" in text, text[:260])
    ui.check("with nothing to report", "0 errors" in text and "No issues." in text, text[:260])
    ui.shot("Load: two elements and one relationship written, and the report says so")
    ui.goto(f"/element/{LDC}")
    body = ui.body()
    ui.check("the imported element opens by its id", ui.text("#page h1") == "H Admissions Data", body[:200])
    # The type badge is upper-cased by the stylesheet, so read it without the case.
    ui.check("carrying the type the file gave it", "logical data component" in body.lower(), body[:400])
    ui.check("and the description it was imported with", MARKER in body, body[:400])
    ui.check("the element counts the relationship the file declared", "Relationships (1)" in body, body[:600])
    _tab(ui, "Relationships")
    rels = ui.text("el-rel-tables")
    ui.check("which reaches the other imported element", "H Applicant" in rels, rels[:400])
    ui.check("under the label the metamodel gives it", "encapsulates" in rels.lower(), rels[:400])
    ui.shot("The imported element, with the relationship the CSV declared")


@pytest.mark.scenario(
    scenario_id="H07",
    group="H",
    title="A broken CSV comes back as an issue table, one row per defect",
    feature="Import · the issue report",
    expected=(
        "Files with an unknown type, a nameless row and an edge with no endpoints report three errors "
        "and list each one with its level, code, message, file and row."
    ),
)
def test_broken_files_report_issues(ui, record):
    _open(ui)
    _upload(
        ui,
        _write(ui, "h-broken-elements.csv", BROKEN_ELEMENTS_CSV),
        _write(ui, "h-broken-relationships.csv", BROKEN_RELATIONSHIPS_CSV),
    )
    ui.click("im-validate")
    text = _report(ui)
    ui.check("nothing was written while the files were checked", DRY in text, text[:160])
    ui.check("all three defects are counted as errors", "3 errors" in text, text[:260])
    ui.check("both element rows were skipped", "elements 0/2 loaded (2 skipped)" in text, text[:260])
    ui.check("and so was the edge", "relationships 0/1 loaded (1 skipped)" in text, text[:260])
    ui.check("the report heads the list with how many issues there are", "Issues (3)" in text, text[:260])
    headers = ui.page.locator("#im-report table thead").first
    head = headers.inner_text().lower().replace("\n", " ") if headers.count() else ""
    for column in ("level", "code", "message", "file", "row", "entity"):
        ui.check(f"the issue table has a {column} column", column in head, head)
    for code in ("unknown_type", "missing_name", "dangling_relationship"):
        ui.check(f"the {code} defect is named by its code", code in text, text[:600])
    ui.check(
        "each issue says which file and which row it came from",
        "h-broken-elements.csv" in text and "h-broken-relationships.csv" in text,
        text[:600],
    )
    ui.check("and every issue is marked with its level", text.lower().count("error") >= 3, text[:600])
    ui.shot("Three defects, three rows: level, code, message, file, row and entity")


# ------------------------------------------------------------------------ refusing well


@pytest.mark.scenario(
    scenario_id="H08",
    group="H",
    title="Validate with nothing uploaded asks for a file rather than reporting an empty run",
    feature="Import · nothing to validate",
    expected="Pressing Validate only with no files shows the yellow 'Upload at least one CSV file first.'",
)
def test_validate_without_files(ui, record):
    _open(ui)
    ui.check("the page starts with no file listed", ui.text("im-files") == "", ui.text("im-files"))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("the page asks for a file", NO_FILES in text, text[:160])
    ui.check("and reports no counts it did not run", "loaded" not in text.lower(), text[:160])
    ui.shot("Validate with nothing uploaded: the page asks for a file instead of running")


@pytest.mark.scenario(
    scenario_id="H09",
    group="H",
    title="A file whose name matches no pattern is refused, in red, saying why",
    feature="Import · an unrecognised file",
    expected=(
        "Uploading only h-notes.csv, which matches neither the element, relationship nor link pattern, "
        "refuses the run and names the patterns it was matched against."
    ),
)
def test_file_matching_no_pattern(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-notes.csv", NOTES_CSV))
    ui.check("the file was taken", "h-notes.csv" in ui.text("im-files"), ui.text("im-files"))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("the run is refused rather than reported as empty", NO_MATCH in text, text[:200])
    ui.check("nothing is counted", "loaded" not in text.lower(), text[:200])
    ui.shot("A file matching no pattern: refused, and the refusal says what it was matched against")


@pytest.mark.scenario(
    scenario_id="H10",
    group="H",
    title="Choosing the tool-export mapping reads a file the plain contract could not",
    feature="Import · mappings",
    expected=(
        "h-objects.csv is unmatched under no mapping; under the EA tool export mapping it is classified, "
        "its headers renamed and its type resolved, and the file that still matches nothing is named as ignored."
    ),
)
def test_mapping_classifies_and_renames(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-objects.csv", OBJECTS_CSV), _write(ui, "h-notes.csv", NOTES_CSV))
    ui.click("im-validate")
    plain = _report(ui)
    ui.check("under the plain contract neither file is recognised", NO_MATCH in plain, plain[:200])
    ui.select("im-mapping", "EA tool export")
    ui.click("im-validate")
    mapped = _report(ui)
    ui.check("the mapping's patterns classify the export", DRY in mapped, mapped[:200])
    ui.check("and its one row is read", "elements 0/1 loaded" in mapped, mapped[:260])
    ui.check("its renamed headers resolve to a type in the pack", "0 errors" in mapped, mapped[:260])
    ui.check(
        "the file that still matches nothing is named rather than silently dropped",
        "Ignored (no pattern matched): h-notes.csv" in mapped,
        mapped[:300],
    )
    ui.shot("With the tool-export mapping the export is read and the unmatched file is named as ignored")


@pytest.mark.scenario(
    scenario_id="H11",
    group="H",
    title="Re-importing the same source updates the rows in place rather than duplicating them",
    feature="Import · re-import",
    expected=(
        "Loading the same ids from the same source with a changed name reports two elements loaded, "
        "shows the new name on the element, and leaves the same number of rows in Browse."
    ),
)
def test_reimport_updates(ui, record):
    ui.goto(f"/browse?q={MARKER}")
    before = ui.grid_row_count("browse-grid")
    ui.must("the first import is in the model to re-import", before > 0, f"{before} rows match {MARKER}")
    _open(ui)
    _upload(ui, _write(ui, "h-elements-revised.csv", REVISED_CSV))
    ui.fill("im-source", SOURCE)
    ui.click("im-load")
    text = _report(ui)
    ui.check("the second load writes both rows again", "elements 2/2 loaded" in text, text[:260])
    ui.check("without an error", "0 errors" in text, text[:260])
    ui.goto(f"/element/{LDC}")
    ui.check(
        "the element carries the name the second file gave it",
        ui.text("#page h1") == "H Admissions Data (revised)",
        ui.text("#page h1"),
    )
    ui.goto(f"/browse?q={MARKER}")
    after = ui.grid_row_count("browse-grid")
    ui.check("and no row was duplicated by the re-import", after == before, f"{before} before, {after} after")
    ui.check(
        "the updated name is what Browse shows",
        "(revised)" in ui.grid_cell_of("browse-grid", LDC, "name"),
        ui.grid_cell_of("browse-grid", LDC, "name"),
    )
    ui.shot("After a re-import from the same source the rows are updated, not duplicated")


@pytest.mark.scenario(
    scenario_id="H12",
    group="H",
    title="A spreadsheet-shaped CSV — byte-order mark, CRLF, a quoted field over two lines — is read whole",
    feature="Import · a file straight out of a spreadsheet",
    expected=(
        "The importer reads the two records such a file holds, with no issue, and the file list agrees "
        "with the importer about how many rows were read."
    ),
)
def test_spreadsheet_shaped_csv(ui, record, finding):
    _open(ui)
    path = ui.run_dir / "uploads" / "h-spreadsheet-elements.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("﻿" + SPREADSHEET_CSV).encode("utf-8"))
    _upload(ui, path)
    ui.click("im-validate")
    text = _report(ui)
    ui.check("the byte-order mark did not break the first column", "missing_id" not in text, text[:300])
    ui.check("both records were read", "elements 0/2 loaded" in text, text[:300])
    ui.check("with nothing to report", "0 errors" in text and "No issues." in text, text[:300])
    listed = _file_row(ui, "h-spreadsheet-elements.csv")
    # The file list counts physical lines (`len(text.splitlines()) - 1`), not CSV records, so a
    # description that wraps onto a second line is counted as a row of its own. The importer reads
    # the file correctly; only the count shown to the reader is wrong.
    ui.check("the file list agrees with what the importer read", "2 rows" in listed, listed)
    ui.shot("A spreadsheet-shaped CSV: two records read, and what the file list says it saw")
    if "3 rows" in listed:
        finding.append(
            Finding(
                finding_id="H3",
                where="src/ea/ui/pages/import_page.py · the file list (`im-files`)",
                severity="defect",
                summary="The row count counts lines, not CSV records, so a quoted field that wraps is counted as a row.",
                detail=(
                    'The upload callback labels each file f"{len(t.splitlines()) - 1} rows". A CSV whose '
                    "description spans two lines — ordinary for a Markdown description written in a "
                    "spreadsheet — is listed with one row more than the importer reads, so the count the "
                    "reader checks before pressing Load disagrees with the count the report gives after it."
                ),
            )
        )


# ------------------------------------------------------- reading a file, or refusing to read it


def _report_background(ui) -> str:
    """The colour of the report's own first alert, which is not the page banner's."""
    return ui.page.evaluate(
        "() => { const a = document.querySelector('#im-report [class*=\"Alert-root\"]');"
        " return a ? getComputedStyle(a).backgroundColor : ''; }"
    )


def _issue_rows(ui) -> str:
    """The body of the issue table, without the summary above it that also says 'errors'."""
    body = ui.page.locator("#im-report table tbody").first
    return body.inner_text().replace("\n", " ") if body.count() else ""


def _file_count(ui) -> int:
    return ui.page.locator("#im-files [class*='Group-root']").count()


def _row_says(ui, name: str, text: str, tries: int = 20) -> bool:
    """The file list is rewritten by a callback; give it a moment to say the new thing."""
    for _ in range(tries):
        if text in _file_row(ui, name):
            return True
        ui.page.wait_for_timeout(200)
    return False


@pytest.mark.scenario(
    scenario_id="H13",
    group="H",
    title="A file whose rows do not match its own header is refused whole, by name and with the reason",
    feature="Import · a malformed file",
    expected=(
        "A CSV holding a row with more fields than its header is not read at all: the page names the "
        "file, quotes the line the parser stopped on, and says what reading it anyway would cost."
    ),
)
def test_ragged_file_is_refused(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-ragged-elements.csv", RAGGED_CSV))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("the file is refused rather than half-read", NOT_READ in text, text[:300])
    ui.check("the refusal names the file it is about", "h-ragged-elements.csv" in text, text[:300])
    ui.check(
        "and quotes the line the parser stopped on, so the row can be found",
        "Expected 4 fields in line 3" in text,
        text[:300],
    )
    ui.check(
        "it says why reading it anyway would be worse than refusing it",
        "identifiers the file never named" in text,
        text[:300],
    )
    ui.check(
        "and reports no count for a file nothing was read from",
        "loaded" not in text.lower(),
        text[:300],
    )
    ui.shot("A ragged CSV: refused whole, with the file, the line and the reason")


@pytest.mark.scenario(
    scenario_id="H14",
    group="H",
    title="A malformed file among sound ones stops only itself, and turns the summary red",
    feature="Import · a malformed file beside a sound one",
    expected=(
        "Adding a ragged file to a sound one still reports the sound file's two rows, names the ragged "
        "one as unread, and colours the summary differently from the clean run it followed."
    ),
)
def test_ragged_file_beside_a_sound_one(ui, record, finding):
    _open(ui)
    _upload(ui, _write(ui, "h-elements.csv", ELEMENTS_CSV))
    ui.click("im-validate")
    clean, clean_bg = _report(ui), _report_background(ui)
    ui.must("the sound file on its own reports its two rows", "elements 0/2 loaded" in clean, clean[:200])
    _upload(ui, _write(ui, "h-ragged-elements.csv", RAGGED_CSV))
    ui.click("im-validate")
    text, bg = _report(ui), _report_background(ui)
    ui.check("the sound file is still read", "elements 0/2 loaded" in text, text[:300])
    ui.check(
        "the ragged one is named as unread beside it",
        NOT_READ in text and "h-ragged-elements.csv" in text,
        text[:400],
    )
    ui.check(
        "and the summary is coloured differently from the clean run before it",
        bg != clean_bg,
        f"clean {clean_bg}, with the ragged file {bg}",
    )
    ui.check(
        "the file the reader is still asked to load is the sound one alone",
        "H-RAGGED-ONE" not in text,
        text[:400],
    )
    ui.shot("A ragged file beside a sound one: two rows read, one file refused, the summary red")
    if "0 errors" in text and "No issues." in text:
        finding.append(
            Finding(
                finding_id="H4",
                where="src/ea/ui/pages/import_page.py · the report (`im-report`)",
                severity="consistency",
                summary="A refused file is not counted as an error, so the same import reads '0 errors' "
                "in the app and one error on the command line.",
                detail=(
                    "`_run` renders the malformed files as an alert of their own and never adds them to "
                    "the report, so the summary says '0 errors' and the issue table says 'No issues.' "
                    "while a whole file went unread. `import_directory`, which the command line uses, "
                    "appends an error issue coded `ragged_row` for each such file, so `ea import` on the "
                    "same folder counts it. The count a reader skims and the count the command line "
                    "prints should agree."
                ),
            )
        )


# ------------------------------------------------------ what the report says it did, and did not


@pytest.mark.scenario(
    scenario_id="H15",
    group="H",
    title="Load with nothing loadable says so plainly instead of claiming a load",
    feature="Import · a load that writes nothing",
    expected=(
        "Pressing Load on files whose every row is defective reports 'Nothing was loaded.' rather than "
        "'Loaded.', counts the three errors, and the ids are still absent from the model afterwards."
    ),
)
def test_load_that_writes_nothing(ui, record):
    _open(ui)
    _upload(
        ui,
        _write(ui, "h-broken-elements.csv", BROKEN_ELEMENTS_CSV),
        _write(ui, "h-broken-relationships.csv", BROKEN_RELATIONSHIPS_CSV),
    )
    ui.fill("im-source", SOURCE)
    ui.click("im-load")
    text = _report(ui)
    ui.check("the report does not claim a load it did not make", LOADED not in text, text[:200])
    ui.check("it says plainly that nothing was written", NOTHING_LOADED in text, text[:200])
    ui.check("while making clear this was a load and not a validation", DRY not in text, text[:200])
    ui.check("every element row was skipped", "elements 0/2 loaded (2 skipped)" in text, text[:300])
    ui.check("and so was the edge", "relationships 0/1 loaded (1 skipped)" in text, text[:300])
    ui.check("the three defects are still counted", "3 errors" in text, text[:300])
    ui.shot("Load with nothing loadable: 'Nothing was loaded.', and the three defects behind it")
    ui.goto("/element/H-BROKEN-ONE")
    body = ui.body()
    ui.check("the row whose type the pack does not know reached nothing", "Not found" in body, body[:200])
    ui.check("and the page names the id it could not find", "H-BROKEN-ONE" in body, body[:200])
    ui.goto("/element/H-BROKEN-TWO")
    ui.check("nor did the row with no name", "Not found" in ui.body(), ui.body()[:200])
    ui.shot("After a load that wrote nothing, the broken ids are still absent from the model")


@pytest.mark.scenario(
    scenario_id="H16",
    group="H",
    title="A relationships file alone finds its endpoints in the model, and a refused type lists what is allowed",
    feature="Import · a relationship the metamodel does not allow",
    expected=(
        "A relationships file uploaded on its own resolves both endpoints from the earlier load rather "
        "than calling them dangling, and the type it names is refused with the type that is allowed."
    ),
)
def test_relationship_type_refused_names_what_is_allowed(ui, record):
    ui.goto(f"/browse?q={MARKER}")
    ui.must(
        "the elements of the earlier load are in the model to point at",
        ui.grid_row_count("browse-grid") > 0,
        ui.text("browse-count"),
    )
    _open(ui)
    _upload(ui, _write(ui, "h-badrel-relationships.csv", BAD_REL_CSV))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("no element file was needed", "elements 0/0 loaded" in text, text[:300])
    ui.check(
        "and the endpoints were found in the model rather than called dangling",
        "dangling_relationship" not in text,
        text[:400],
    )
    ui.check("the edge is refused by the metamodel", "unknown_relationship_type" in text, text[:400])
    ui.check("the message names the relationship the file asked for", "'processes'" in text, text[:400])
    ui.check(
        "and the two types it was asked to join",
        "logical_data_component" in text and "data_entity" in text,
        text[:400],
    )
    ui.check(
        "then lists what the metamodel does allow between them, so the file can be fixed",
        "allowed: encapsulates" in text,
        text[:400],
    )
    ui.check("the edge is counted as skipped", "relationships 0/1 loaded (1 skipped)" in text, text[:300])
    ui.check("and counted as an error", "1 errors" in text, text[:300])
    ui.shot("A relationship the metamodel refuses, answered with the one it allows")


@pytest.mark.scenario(
    scenario_id="H17",
    group="H",
    title="A warning says what the importer did instead, and does not cost the row",
    feature="Import · warnings",
    expected=(
        "A file with an unknown status, an unrecognised current and target state and a repeated id "
        "reports four warnings and no error, every one saying what was used instead, and skips nothing."
    ),
)
def test_warnings_do_not_skip_the_row(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-warning-elements.csv", WARNING_CSV))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("nothing about the file is an error", "0 errors" in text, text[:300])
    ui.check("all four warnings are counted", "4 warnings" in text, text[:300])
    ui.check("and listed", "Issues (4)" in text, text[:300])
    ui.check("no row was skipped for a warning", "elements 0/2 loaded (0 skipped)" in text, text[:300])
    for code in ("unknown_status", "unknown_current_state", "unknown_target_state", "duplicate_id"):
        ui.check(f"the {code} warning is named by its code", code in text, text[:800])
    ui.check("the unknown status says what was used instead", "using 'approved'" in text, text[:800])
    ui.check(
        "the unrecognised current state says it was derived from the lifecycle text instead",
        "derived from the lifecycle text instead" in text,
        text[:800],
    )
    ui.check(
        "the unrecognised target state says it fell back to undecided",
        "using 'undecided'" in text,
        text[:800],
    )
    ui.check("and the repeated id says which row wins", "last row wins" in text, text[:800])
    rows = _issue_rows(ui)
    ui.check("every issue in the table is marked a warning", rows.lower().count("warning") >= 4, rows[:400])
    ui.check("and none of them an error", "error" not in rows.lower(), rows[:400])
    ui.shot("Four warnings, no error: each says what was used instead, and no row is skipped")


# ---------------------------------------------------- the mapping, the source system, the links


@pytest.mark.scenario(
    scenario_id="H18",
    group="H",
    title="With the source box cleared the import falls back to the mapping's own source system",
    feature="Import · the source system",
    expected=(
        "The mapping offers the plain contract and the tool export by the file each comes from; with "
        "the source box emptied the run is recorded as `import` under no mapping and as `ea-tool` under "
        "the tool export."
    ),
)
def test_source_system_falls_back(ui, record):
    _open(ui)
    ui.click("im-mapping")
    options = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("the mapping offers exactly the two the page ships with", len(options) == 2, str(options))
    ui.check(
        "and names the file the tool export is read from, so it can be adapted",
        any("connectors/tool-export/mapping.yaml" in o for o in options),
        str(options),
    )
    _upload(ui, _write(ui, "h-elements.csv", ELEMENTS_CSV), _write(ui, "h-objects.csv", OBJECTS_CSV))
    ui.fill("im-source", "")
    ui.click("im-validate")
    plain = _report(ui)
    ui.check(
        "with the box empty and no mapping the run is recorded as import",
        "source=import" in plain,
        plain[:200],
    )
    ui.check("reading the file the contract matches", "elements 0/2 loaded" in plain, plain[:300])
    ui.check("and naming the one it does not", "h-objects.csv" in plain, plain[:300])
    ui.select("im-mapping", "EA tool export")
    ui.click("im-validate")
    mapped = _report(ui)
    ui.check(
        "under a mapping the same empty box takes the source the mapping declares",
        "source=ea-tool" in mapped,
        mapped[:200],
    )
    ui.check("and both files are now read", "elements 0/3 loaded" in mapped, mapped[:300])
    ui.check("with nothing left ignored", "Ignored" not in mapped, mapped[:300])
    ui.check(
        "the source box is still empty, so nothing was filled in behind the reader",
        ui.page.locator("#im-source").input_value() == "",
        ui.page.locator("#im-source").input_value(),
    )
    ui.shot("With the source box cleared the mapping's own source system is what the rows would carry")


@pytest.mark.scenario(
    scenario_id="H19",
    group="H",
    title="The tool-export mapping resolves the tool's own type label and lifecycle words",
    feature="Import · a mapping's vocabulary",
    expected=(
        "Loading a tool export whose type is written `Definition` and whose lifecycle reads `Being "
        "built` stores a Business Definition and a current state of in_implementation, under the "
        "mapping's own source system."
    ),
)
def test_mapping_reads_the_tools_own_words(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-tool-objects.csv", TOOL_OBJECTS_CSV))
    ui.select("im-mapping", "EA tool export")
    ui.fill("im-source", "")
    ui.click("im-load")
    text = _report(ui)
    ui.check("both rows were written", LOADED in text and "elements 2/2 loaded" in text, text[:300])
    ui.check("with nothing to report", "0 errors" in text and "No issues." in text, text[:300])
    ui.check("under the source system the mapping declares", "source=ea-tool" in text, text[:200])
    ui.shot("A tool export loaded through its mapping: two rows, no issue")
    ui.goto(f"/browse?q={MARKER}")
    kind = ui.grid_cell_of("browse-grid", "H-BD-COHORT", "type")
    ui.check(
        "the label the tool writes is stored as the type the pack names", kind == "Business Definition", kind
    )
    retired = ui.grid_cell_of("browse-grid", "H-BD-COHORT", "current_state")
    ui.check("a lifecycle text of Sunset becomes a current state of retired", retired == "retired", retired)
    building = ui.grid_cell_of("browse-grid", "H-LDC-ANALYTICS", "current_state")
    ui.check(
        "and Being built, which no default keyword reads, is taken from the mapping's own table",
        building == "in_implementation",
        building,
    )
    source = ui.grid_cell_of("browse-grid", "H-BD-COHORT", "source_system")
    ui.check(
        "both rows carry the mapping's source system, so a re-import finds them", source == "ea-tool", source
    )
    ui.shot("In Browse: the tool's words stored as the pack's type and the repository's states")


@pytest.mark.scenario(
    scenario_id="H20",
    group="H",
    title="Links arrive both in the element row and in a file of their own",
    feature="Import · links",
    expected=(
        "Two URLs separated by a bar in one cell are read as two links, and a links file naming an "
        "element the model already holds warns only about the id that is nowhere."
    ),
)
def test_links_inline_and_by_file(ui, record, finding):
    _open(ui)
    _upload(ui, _write(ui, "h-inline-elements.csv", INLINE_LINKS_CSV))
    ui.click("im-validate")
    inline = _report(ui)
    ui.check("the two URLs in the one cell are read as two links", "links 0/2" in inline, inline[:300])
    ui.check(
        "and the row carrying them is clean", "0 errors" in inline and "No issues." in inline, inline[:300]
    )
    ui.shot("Two URLs in a single cell, read as two links")
    _open(ui)  # a fresh page, so the element file above is not in the store to resolve against
    _upload(ui, _write(ui, "h-links.csv", LINKS_CSV))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("both rows of the links file are read", "links 0/2" in text, text[:300])
    ui.check("the link for an id that is nowhere is reported", "H-NOWHERE" in text, text[:500])
    ui.check("as a warning rather than an error", "0 errors" in text, text[:300])
    # The endpoints of a relationship are looked up in the model when they are not in the same
    # upload; the element of a link is not, so a links file on its own is refused row by row.
    ui.check(
        "the link for an element the model already holds is not called unknown",
        LDC not in text,
        text[:500],
    )
    ui.check("so only the id that is nowhere is an issue", "Issues (1)" in text, text[:300])
    ui.shot("A links file on its own: the id that is nowhere warned, the element in the model accepted")
    if LDC in text:
        finding.append(
            Finding(
                finding_id="H5",
                where="src/ea/importer/csv_import.py · `import_frames`, the links it builds",
                severity="defect",
                summary="A links file uploaded on its own calls every element unknown, even the ones "
                "the model already holds.",
                detail=(
                    "`import_frames` looks an unknown relationship endpoint up in the store — the "
                    "comment says 'endpoints may already be in the store from an earlier import' — but "
                    "does the same for no link, so `build_links` sees only the elements of this upload. "
                    "A links.csv uploaded without its elements.csv therefore reports 'link for unknown "
                    "element' for an id the reader can open in the model, and loads nothing. Links are "
                    "the one kind of file that cannot be re-imported on its own."
                ),
            )
        )


# ------------------------------------------------------ the upload zone, and where a load lands


@pytest.mark.scenario(
    scenario_id="H21",
    group="H",
    title="Files chosen one after another are kept together, and a file chosen again replaces itself",
    feature="Import · choosing files more than once",
    expected=(
        "A second choice of file adds to the list rather than replacing it, choosing the same name "
        "again updates that one entry instead of listing it twice, and leaving the page empties the list."
    ),
)
def test_upload_accumulates_and_replaces(ui, record):
    _open(ui)
    _upload(ui, _write(ui, "h-grown-elements.csv", GROWN_CSV))
    ui.check(
        "the first file is listed with the two rows it holds",
        _row_says(ui, "h-grown-elements.csv", "2 rows"),
        _file_row(ui, "h-grown-elements.csv"),
    )
    _upload(ui, _write(ui, "h-relationships.csv", RELATIONSHIPS_CSV))
    listed = ui.text("im-files")
    ui.check("choosing a second file keeps the first", "h-grown-elements.csv" in listed, listed)
    ui.check(
        "and lists both, so one upload can be built up from several choices", _file_count(ui) == 2, listed
    )
    _upload(ui, _write(ui, "h-grown-elements.csv", GROWN_MORE_CSV))
    ui.check(
        "choosing a file of the same name again replaces its entry rather than adding one",
        _file_count(ui) == 2,
        ui.text("im-files"),
    )
    ui.check(
        "and the count beside it follows the new content",
        _row_says(ui, "h-grown-elements.csv", "3 rows"),
        _file_row(ui, "h-grown-elements.csv"),
    )
    ui.shot("Two files chosen separately, the first replaced by a longer version of itself")
    _open(ui)
    ui.check(
        "and leaving the page is what empties the list, there being nothing else that does",
        ui.text("im-files") == "",
        ui.text("im-files"),
    )


@pytest.mark.scenario(
    scenario_id="H22",
    group="H",
    title="A load on a branch lands on the branch and leaves main alone, as the banner said it would",
    feature="Import · loading onto a branch",
    expected=(
        "Loading an element while on the branch reports it written and finds it in Browse on the "
        "branch, and the same search on main finds nothing until the branch is merged."
    ),
    branch=BRANCH_ID,
)
def test_load_onto_a_branch_stays_there(ui, record):
    _open(ui)
    _switch_to_branch(ui)
    ui.must("the page says the load would land on the branch", BRANCH_BANNER in ui.body(), _banner(ui))
    _upload(ui, _write(ui, "h-branch-elements.csv", BRANCH_CSV))
    ui.fill("im-source", SOURCE)
    ui.click("im-load")
    text = _report(ui)
    ui.check("the load reports the row it wrote", LOADED in text, text[:200])
    ui.check("one element, and nothing skipped", "elements 1/1 loaded (0 skipped)" in text, text[:300])
    ui.shot("A load on the branch: one element written where the banner said it would land")
    ui.goto(f"/browse?q={BRANCH_MARKER}")
    on_branch = ui.grid_row_count("browse-grid")
    ui.check("the row is there for a reader on the branch", on_branch == 1, f"{on_branch} rows")
    name = ui.grid_cell_of("browse-grid", BRANCH_ONLY, "name")
    ui.check("under the name the file gave it", name == "H Branch Only", name)
    ui.shot("On the branch the imported row is in Browse")
    ui.branch("main")
    ui.goto(f"/browse?q={BRANCH_MARKER}")
    on_main = ui.grid_row_count("browse-grid")
    ui.check("and main is untouched until the branch is merged", on_main == 0, f"{on_main} rows")
    ui.check("the count says so too", ui.text("browse-count").startswith("0 of"), ui.text("browse-count"))
    ui.shot("The same search on main finds nothing: the load stayed on the branch")


# --------------------------------------------------------------------- a report too long to show


@pytest.mark.scenario(
    scenario_id="H23",
    group="H",
    title="A file with more issues than the table shows still counts them all",
    feature="Import · a report at length",
    expected=(
        "Validating a file whose every row is defective counts all 501 errors in the summary and the "
        "heading, and lists the first 500 of them."
    ),
)
def test_more_issues_than_the_table_shows(ui, record, finding):
    _open(ui)
    _upload(ui, _write(ui, "h-overflow-elements.csv", OVERFLOW_CSV))
    ui.click("im-validate")
    text = _report(ui)
    ui.check("nothing was written while the file was checked", DRY in text, text[:200])
    ui.check(
        "every row was read and every row skipped", "elements 0/501 loaded (501 skipped)" in text, text[:300]
    )
    ui.check("the summary counts them all", "501 errors" in text, text[:300])
    ui.check("and so does the heading above the list", "Issues (501)" in text, text[:300])
    shown = ui.page.locator("#im-report table tbody tr").count()
    ui.check(
        "the list itself stops at the five hundred it is capped to", shown == 500, f"{shown} rows listed"
    )
    ui.shot("A file with 501 defects: all counted, the first five hundred listed", full_page=False)
    if shown < 501 and "501" in text and "not shown" not in text.lower():
        finding.append(
            Finding(
                finding_id="H6",
                where="src/ea/ui/pages/import_page.py · the issue table (`im-report`)",
                severity="usability",
                summary="The issue list is cut at 500 rows without saying so.",
                detail=(
                    "`issues_table(report.issues[:500])` shows the first five hundred issues under a "
                    "heading that counts all of them, so a reader who scrolls to the end of a longer "
                    "report has no way to tell that it stops early rather than finishing. The cap is "
                    "sound — the page would be unreadable otherwise — but the last row should say how "
                    "many were not shown, or the command line named as the way to see the rest."
                ),
            )
        )
