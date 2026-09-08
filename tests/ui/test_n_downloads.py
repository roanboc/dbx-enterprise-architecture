"""Group N — Downloads: every file the application can produce, read as a file.

Eleven files leave this application, and every one of them leaves through the same
component: a single `dcc.Download` in the shell (`ui/layout.py`), which nine callbacks
across seven pages write to. So the group has two jobs. The first is to prove each
producer separately — the element view, the impact view and the target-state view, each
as Markdown and as draw.io; the answer document, the same two ways; the metamodel pack as
YAML; the import template as a zip; and the Proposal Template as Markdown. The second is
to prove that the one shared component survives being used eleven times in a session and
twice in a row on the same button.

What separates a check here from the same download seen in another group is that nothing
is asserted by looking at the screen. A Markdown view is read as Markdown — a closed
mermaid fence and an element table whose rows carry backticked identifiers. A draw.io file
is parsed as XML and walked: an `mxfile` holding an `mxGraphModel`, one `<object>` per
element carrying `ea_id`, `ea_type` and a `link` back to the page it came from, and edges
that only join shapes the file actually contains. The pack is loaded back through the same
loader the application loads a pack with. The archive is opened and its CSV headers read.
The point is that these files are handed to somebody else's tool, so being well-formed
matters more than looking right.

Nothing here writes to the model, so the group is safe wherever it runs in the round, and
nothing asserts a total: an earlier group may have added an element, given one a target
state or edited the metamodel, so a check is a file that parses, a row that must be there,
or two files that must agree with each other.
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml
from tests.ui.evidence import Finding

from ea.metamodel import Registry, load_pack

pytestmark = pytest.mark.gui

EL = "PAC-CMS"  # Curriculum Management System — an application component with neighbours both ways
EL_NAME = "Curriculum Management System"
IMP = "DE-SRS-COURSE"  # SRS_Course — a data entity with an upstream and a downstream
IMP_NAME = "SRS_Course"
WP = "WP-CMS-UPGRADE"  # the sample's one work package: three changed, two new, one decommissioned
WP_NAME = "Curriculum Management System Upgrade"
FORMS = "PTC-FORMS"  # Legacy Forms Server — the decommissioned element in that work package
OFFERING = "DE-SRS-COURSE-OFFERING"  # the element the stub's impact answer is about
GHOST = "FX-GHOST-ENTITY"  # shaped like an identifier, carried by nothing: an answer with no diagram
PACK = "higher_education"

ASK_QUESTION = "What is the impact of changing SRS_Course_Offering?"
DOCUMENT = "#ask-answer .ea-document"

# The identifier column of a generated view's element table: `| `PAC-CMS` | … |`.
TABLE_ID = re.compile(r"^\|\s*`([^`]+)`\s*\|")
MERMAID_FENCE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def _f(finding_id: str, where: str, severity: str, summary: str, detail: str) -> Finding:
    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


def _pm(**parts: str) -> str:
    """The CSS selector for a pattern-matching component, whose DOM id is the JSON Dash writes."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


# ------------------------------------------------------------------ getting to a producer


def _open_element_view(ui, element_id: str = EL) -> None:
    """The element page's Graph tab, where the generated view and its two buttons live."""
    ui.goto(f"/element/{element_id}")
    ui.click("#el-tabs [role='tab']:has-text('Graph')")
    ui.page.wait_for_timeout(200)
    ui.wait_mermaid()


def _open_impact(ui, element_id: str = IMP) -> None:
    ui.goto(f"/impact?element={element_id}")
    ui.wait_mermaid()


def _open_target(ui, work_package: str = WP) -> None:
    ui.goto(f"/target?wp={work_package}")
    ui.wait_mermaid()


def _ask(ui, question: str = ASK_QUESTION) -> None:
    """Put the question the stub answers with a view, and wait for the document."""
    ui.goto("/ask")
    box = ui.page.locator("textarea#ask-input")
    box = box.first if box.count() else ui.page.locator("#ask-input textarea").first
    box.click()
    box.fill(question)
    ui.settle()
    ui.click("ask-button")
    ui.page.wait_for_selector(DOCUMENT, timeout=30_000)
    ui.settle()


def _try_download(ui, selector: str) -> tuple[Path | None, str]:
    """A download that may not come: the file and why, rather than an exception."""
    try:
        with ui.page.expect_download(timeout=15_000) as info:
            ui.page.locator(ui._sel(selector)).first.click()
        dl = info.value
        path = ui.run_dir / "downloads" / dl.suggested_filename
        dl.save_as(str(path))
        ui.settle()
        return path, dl.suggested_filename
    except Exception as exc:  # noqa: BLE001 — no file is the finding, not a crash
        ui.settle()
        return None, f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


# ---------------------------------------------------------------------- reading the files


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _table_ids(text: str) -> list[str]:
    """Every identifier the element table of a generated view lists, in order."""
    return [m.group(1) for line in text.splitlines() if (m := TABLE_ID.match(line))]


def _check_markdown_view(ui, path: Path, title_starts: str) -> str:
    """The shape every Markdown view owes a reader: a title, a closed fence, a table."""
    text = _text(path)
    first = text.splitlines()[0] if text.splitlines() else ""
    ui.check(
        "the document opens with the view's title as a heading",
        first.startswith(f"## {title_starts}"),
        f"the first line reads {first!r}",
    )
    ui.check(
        "the fences are balanced, so the diagram is closed",
        text.count("```") % 2 == 0 and text.count("```") >= 2,
        f"{text.count('```')} fence markers",
    )
    fences = MERMAID_FENCE.findall(text)
    ui.must("it carries the diagram as a mermaid fence", len(fences) == 1, f"{len(fences)} fences")
    diagram = fences[0]
    ui.check(
        "the fence holds a flowchart, not an empty block",
        diagram.strip().startswith("flowchart"),
        diagram.strip()[:60],
    )
    ids = _table_ids(text)
    ui.check("and a table of the elements it shows", len(ids) >= 2, f"{len(ids)} rows")
    absent = [i for i in ids if f"[{i}]" not in diagram]
    ui.check(
        "every element in the table is drawn in the diagram",
        not absent,
        f"not drawn: {absent[:5]}" if absent else f"all {len(ids)} of them",
    )
    return text


def _drawio(ui, path: Path) -> ET.Element:
    """Parse a draw.io export and prove it is one, rather than looking at it."""
    text = _text(path)
    ui.check(
        "the file opens with an XML declaration",
        text.lstrip().startswith("<?xml"),
        text[:40].replace("\n", " "),
    )
    try:
        root = ET.fromstring(text)  # noqa: S314 — a file this application just wrote
    except ET.ParseError as exc:
        ui.must("the draw.io file is well-formed XML", False, str(exc))
        raise
    ui.must("its root element is an mxfile", root.tag == "mxfile", f"the root is <{root.tag}>")
    ui.check(
        "which names this application as the host that wrote it",
        root.get("host") == "ea-repository",
        f"host={root.get('host')!r}",
    )
    model = root.find(".//mxGraphModel")
    ui.must("it holds an mxGraphModel", model is not None)
    return root


def _shapes(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//object")


def _shape_ids(root: ET.Element) -> list[str]:
    return [o.get("ea_id", "") for o in _shapes(root)]


def _check_linking_contract(ui, root: ET.Element, base_url: str) -> list[str]:
    """Principle P8: every shape carries its element identifier and a link back to its page."""
    shapes = _shapes(root)
    ui.must("the diagram holds shapes", len(shapes) >= 2, f"{len(shapes)} shapes")
    missing = [o.get("label", "?") for o in shapes if not o.get("ea_id")]
    ui.check("every shape carries an element identifier", not missing, f"without one: {missing[:5]}")
    untyped = [o.get("ea_id", "?") for o in shapes if not o.get("ea_type") or not o.get("ea_type_name")]
    ui.check("and the type it was drawn from", not untyped, f"without a type: {untyped[:5]}")
    wrong = [
        o.get("ea_id", "?") for o in shapes if (o.get("link") or "") != f"{base_url}/element/{o.get('ea_id')}"
    ]
    ui.check(
        "and a link back to its page in this repository",
        not wrong,
        f"badly linked: {wrong[:5]}" if wrong else f"all {len(shapes)} link to {base_url}/element/…",
    )
    ids = [o.get("ea_id", "") for o in shapes]
    ui.check(
        "no element is drawn twice", len(set(ids)) == len(ids), f"{len(ids)} shapes, {len(set(ids))} ids"
    )
    edges = root.findall(".//mxCell[@edge='1']")
    dangling = [
        f"{e.get('source')}→{e.get('target')}"
        for e in edges
        if e.get("source") not in set(ids) or e.get("target") not in set(ids)
    ]
    ui.check(
        "every relationship joins two shapes the file holds",
        not dangling,
        f"{len(edges)} edges; dangling: {dangling[:5]}" if dangling else f"{len(edges)} edges",
    )
    return ids


# ============================================================ the element view, both ways


@pytest.mark.scenario(
    scenario_id="N01",
    group="N",
    title="The element view downloads as Markdown that reads as a document",
    feature="Downloads · element view · Markdown",
    expected="Download Markdown on an element's Graph tab returns <element>-view.md: a heading naming "
    "the element, one closed mermaid fence holding a flowchart, and a table of every element drawn.",
)
def test_element_view_markdown(ui, record):
    _open_element_view(ui)
    path = ui.download("el-view-md", ".md")
    ui.check("the file is named for the element", path.name == f"{EL}-view.md", path.name)
    text = _check_markdown_view(ui, path, f"{EL_NAME} and its neighbourhood")
    ui.check(
        "the heading says how far around the element it reaches",
        "(depth 1)" in text.splitlines()[0],
        text.splitlines()[0],
    )
    ids = _table_ids(text)
    ui.check("the element the view is about is in its own table", EL in ids, f"the table lists {ids[:6]}")
    ui.check(
        "the table gives each element an identifier, a name and a type",
        "| ID | Element | Type |" in text,
        next((line for line in text.splitlines() if line.startswith("| ID")), "no header row"),
    )
    ui.shot("The element's Graph tab, whose Download Markdown button produced the file")


@pytest.mark.scenario(
    scenario_id="N02",
    group="N",
    title="The element view downloads as a draw.io file another tool can open",
    feature="Downloads · element view · draw.io",
    expected="Download draw.io returns <element>-view.drawio: well-formed XML holding an mxGraphModel, "
    "one shape per element carrying ea_id and its type, a link back to this repository, and edges "
    "that join only shapes the file holds.",
)
def test_element_view_drawio(ui, record):
    _open_element_view(ui)
    path = ui.download("el-view-drawio", ".drawio")
    ui.check("the file is named for the element", path.name == f"{EL}-view.drawio", path.name)
    root = _drawio(ui, path)
    ids = _check_linking_contract(ui, root, ui.base_url)
    ui.check("the element the view is about is one of the shapes", EL in ids, f"{len(ids)} shapes")
    shape = next((o for o in _shapes(root) if o.get("ea_id") == EL), None)
    ui.must("the element has a shape of its own", shape is not None)
    ui.check(
        "whose label is the element's name",
        shape.get("label") == "Curriculum Management System",
        f"the label reads {shape.get('label')!r}",
    )
    ui.check(
        "and which carries both states the model holds for it",
        bool(shape.get("ea_current_state")) and shape.get("ea_target_state") is not None,
        f"current={shape.get('ea_current_state')!r}, target={shape.get('ea_target_state')!r}",
    )
    cell = shape.find("mxCell")
    ui.must("the shape is a drawable cell", cell is not None)
    ui.check(
        "drawn with an ArchiMate stencil rather than a plain box",
        "mxgraph.archimate3" in (cell.get("style") or ""),
        (cell.get("style") or "")[:90],
    )
    geometry = cell.find("mxGeometry")
    ui.check(
        "and given a size and a position",
        geometry is not None and geometry.get("width") not in (None, "0"),
        ET.tostring(geometry, encoding="unicode").strip() if geometry is not None else "it has no geometry",
    )
    ui.shot("The generated view and the Download draw.io button that exported it")


@pytest.mark.scenario(
    scenario_id="N03",
    group="N",
    title="The two files of one view describe the same view",
    feature="Downloads · element view · the two formats agree",
    expected="Downloading the same view as Markdown and as draw.io gives two files listing exactly the "
    "same elements, so a reader who takes one away is not given a different model from the other.",
)
def test_the_two_formats_agree(ui, record):
    _open_element_view(ui)
    md = ui.download("el-view-md", ".md")
    drawio = ui.download("el-view-drawio", ".drawio")
    from_table = _table_ids(_text(md))
    from_shapes = _shape_ids(_drawio(ui, drawio))
    ui.must("both files carry elements", bool(from_table) and bool(from_shapes))
    only_md = sorted(set(from_table) - set(from_shapes))
    only_drawio = sorted(set(from_shapes) - set(from_table))
    ui.check(
        "every element in the Markdown is drawn in the draw.io file",
        not only_md,
        f"missing from the diagram: {only_md}" if only_md else f"all {len(from_table)} of them",
    )
    ui.check(
        "and nothing is drawn that the Markdown does not list",
        not only_drawio,
        f"only in the diagram: {only_drawio}" if only_drawio else f"all {len(from_shapes)} of them",
    )
    ui.check(
        "so the two files hold the same number of elements",
        len(from_table) == len(from_shapes),
        f"{len(from_table)} rows against {len(from_shapes)} shapes",
    )
    ui.shot("The one view behind both files, exported twice from the same page")


# ==================================================================== the impact view


@pytest.mark.scenario(
    scenario_id="N04",
    group="N",
    title="The impact view downloads as Markdown and as draw.io, both named for the element",
    feature="Downloads · impact view",
    expected="With an element chosen, both buttons return <element>-impact.md and <element>-impact.drawio, "
    "titled and named for the element, holding the same set of elements in the two formats.",
)
def test_impact_downloads(ui, record):
    _open_impact(ui)
    md = ui.download("imp-view-md", ".md")
    ui.check("the Markdown is named for the element", md.name == f"{IMP}-impact.md", md.name)
    text = _check_markdown_view(ui, md, f"Impact of {IMP_NAME}")
    ui.check("the element it is about is in the table", IMP in _table_ids(text), str(_table_ids(text)[:6]))

    drawio = ui.download("imp-view-drawio", ".drawio")
    ui.check("the draw.io file is named for it too", drawio.name == f"{IMP}-impact.drawio", drawio.name)
    root = _drawio(ui, drawio)
    ids = _check_linking_contract(ui, root, ui.base_url)
    ui.check(
        "the two formats hold the same elements",
        sorted(set(ids)) == sorted(set(_table_ids(text))),
        f"{len(set(ids))} shapes against {len(set(_table_ids(text)))} rows",
    )
    ui.shot("The impact page, its generated view and the two buttons that exported it")


# =============================================================== the target-state view


@pytest.mark.scenario(
    scenario_id="N05",
    group="N",
    title="The target-state view downloads as Markdown carrying both states of every element",
    feature="Downloads · target state · Markdown",
    expected="On a work package, Download Markdown returns target-state-<wp>.md: titled for the work "
    "package, carrying the marker legend, the marked diagram, and a table giving each element its "
    "current state and its target state.",
)
def test_target_markdown(ui, record):
    _open_target(ui)
    path = ui.download("tg-view-md", ".md")
    ui.check("the file is named for the work package", path.name == f"target-state-{WP}.md", path.name)
    text = _check_markdown_view(ui, path, f"Target state of {WP_NAME}")
    ui.check(
        "it explains what its markers mean before the diagram",
        "Markers:" in text.split("```mermaid")[0],
        text.split("```mermaid")[0][-200:].replace("\n", " · "),
    )
    ui.check(
        "the table adds both states to every row",
        "| ID | Element | Type | Current state | Target state |" in text,
        next((line for line in text.splitlines() if line.startswith("| ID")), "no header row"),
    )
    row = next((line for line in text.splitlines() if line.startswith(f"| `{FORMS}`")), "")
    ui.must(
        "the decommissioned element is in the table",
        bool(row),
        row.strip() or "the forms server has no row",
    )
    ui.check(
        "with the state it is in today and the state intended for it",
        "Live" in row and "Decommission" in row,
        row.strip(),
    )
    diagram = MERMAID_FENCE.findall(text)[0]
    marked = next((line for line in diagram.splitlines() if FORMS in line), "")
    ui.check(
        "and its name marked in the diagram the way the legend says",
        "×" in marked,
        marked.strip() or "the forms server is not in the diagram",
    )
    ui.shot("The work package's marked view and the Markdown it was downloaded as")


@pytest.mark.scenario(
    scenario_id="N06",
    group="N",
    title="The target-state draw.io file carries the marking into the diagram",
    feature="Downloads · target state · draw.io",
    expected="Download draw.io on a work package returns target-state-<wp>.drawio in which what is "
    "decommissioned is struck through and stroked red, what is new is dashed and marked, and every "
    "shape carries the two states it was drawn from.",
)
def test_target_drawio(ui, record):
    _open_target(ui)
    path = ui.download("tg-view-drawio", ".drawio")
    ui.check("the file is named for the work package", path.name == f"target-state-{WP}.drawio", path.name)
    root = _drawio(ui, path)
    ids = _check_linking_contract(ui, root, ui.base_url)
    ui.check("the work package's own element is in the diagram", WP in ids, f"{len(ids)} shapes")
    stateless = [
        o.get("ea_id", "?")
        for o in _shapes(root)
        if not o.get("ea_current_state") or not o.get("ea_target_state")
    ]
    ui.check("every shape carries both of its states", not stateless, f"without them: {stateless[:5]}")

    forms = next((o for o in _shapes(root) if o.get("ea_id") == FORMS), None)
    ui.must("the decommissioned element was drawn", forms is not None)
    ui.check(
        "what is decommissioned is struck through",
        (forms.get("label") or "").startswith("<s>"),
        f"its label reads {forms.get('label')!r}",
    )
    ui.check(
        "and its shape is stroked in the decommission colour",
        "strokeColor=#c92a2a" in (forms.find("mxCell").get("style") or ""),
        (forms.find("mxCell").get("style") or "")[-120:],
    )
    new = [o for o in _shapes(root) if o.get("ea_target_state") == "new"]
    ui.check("the work package also brings new elements", bool(new), f"{len(new)} new")
    if new:
        style = new[0].find("mxCell").get("style") or ""
        ui.check(
            "which are drawn dashed, because they are not real yet",
            "dashed=1" in style,
            style[-120:],
        )
        ui.check(
            "and labelled with the marker the legend gives them",
            (new[0].get("label") or "").startswith("+"),
            f"the label reads {new[0].get('label')!r}",
        )
    ui.shot("The marked view of the work package, exported for an architect to redraw")


# ================================================================== the answer document


@pytest.mark.scenario(
    scenario_id="N07",
    group="N",
    title="The answer document downloads as Markdown and as the diagram it leads with",
    feature="Downloads · Ask · the document",
    expected="After an answer, Download Markdown returns the whole document — title, provenance, "
    "diagram, answer, elements and trace — and Download draw.io returns the view it leads with, "
    "carrying the same identifiers.",
)
def test_answer_document_downloads(ui, record):
    _ask(ui)
    md = ui.download("ask-doc-md", ".md")
    ui.check("the file is named after the question", md.name.endswith(".md") and "-" in md.name, md.name)
    text = _text(md)
    for what, needle in (
        ("the question as its title", "# "),
        ("when and by what it was answered", "Answered "),
        ("a generated diagram", "```mermaid"),
        ("the answer itself", "## Answer"),
        ("the elements it names", "## Elements in this answer"),
        ("and how it was reached", "## How this was answered"),
    ):
        ui.check(
            f"the document carries {what}", needle in text, "" if needle in text else f"{needle!r} missing"
        )
    ui.check(
        "its fences are balanced",
        text.count("```") % 2 == 0 and text.count("```") >= 2,
        f"{text.count('```')} fence markers",
    )
    ui.check("the element the question is about is in it", OFFERING in text, f"{len(text)} characters")

    drawio = ui.download("ask-doc-drawio", ".drawio")
    ui.check("the diagram is named after the same question", drawio.name.endswith(".drawio"), drawio.name)
    ui.check(
        "and the two files are named for one document",
        drawio.name[: -len(".drawio")] == md.name[: -len(".md")],
        f"{md.name} and {drawio.name}",
    )
    root = _drawio(ui, drawio)
    ids = _check_linking_contract(ui, root, ui.base_url)
    ui.check("the element the answer is about is drawn", OFFERING in ids, f"{len(ids)} shapes")
    absent = [i for i in ids if i not in text]
    ui.check(
        "and every shape it holds is named in the Markdown too",
        not absent,
        f"only in the diagram: {absent[:5]}" if absent else f"all {len(ids)} of them",
    )
    ui.shot("The answer document, with the two buttons that take it away")


# ======================================================================= the metamodel


@pytest.mark.scenario(
    scenario_id="N08",
    group="N",
    title="The metamodel exports as YAML the application can load back as a pack",
    feature="Downloads · metamodel · YAML",
    expected="Export YAML returns <pack>-metamodel.yaml which parses as YAML, names the pack it came "
    "from, and loads through the same loader the application loads a pack with.",
)
def test_metamodel_yaml(ui, record):
    ui.goto("/metamodel")
    path = ui.download("mm-export", ".yaml")
    ui.check("the file is named for the pack", path.name == f"{PACK}-metamodel.yaml", path.name)
    try:
        data = yaml.safe_load(_text(path))
    except yaml.YAMLError as exc:
        ui.must("the export parses as YAML", False, str(exc))
        raise
    ui.must("the export parses as YAML into a mapping", isinstance(data, dict), type(data).__name__)
    for section in ("pack", "domains", "element_types", "relationship_types"):
        ui.check(f"it holds the {section} section", section in data, f"it holds {sorted(data)}")
    ui.check("the pack names itself", data.get("pack", {}).get("id") == PACK, str(data.get("pack", {}))[:120])
    ui.check(
        "and gives the pack a name and a version",
        bool(data.get("pack", {}).get("name")) and bool(data.get("pack", {}).get("version")),
        str(data.get("pack", {}))[:160],
    )
    types = data.get("element_types") or []
    rels = data.get("relationship_types") or []
    ui.check("it carries the element types", len(types) > 10, f"{len(types)} types")
    ui.check("and the relationship types between them", len(rels) > 5, f"{len(rels)} relationship types")
    entity = next((t for t in types if t.get("id") == "data_entity"), None)
    ui.check(
        "a type the sample model uses is among them, with the name the pages show",
        entity is not None and entity.get("name") == "Data Entity",
        str(entity)[:140] if entity else f"none of the {len(types)} types is called data_entity",
    )
    try:
        pack = load_pack(path)
        Registry(pack)
        loaded = f"{len(pack.element_types)} types, {len(pack.relationship_types)} relationship types"
        ok = True
    except Exception as exc:  # noqa: BLE001 — an export that will not load back is the finding
        loaded, ok = f"{type(exc).__name__}: {exc}", False
    ui.check("and the file loads back as a pack, references and all", ok, loaded)
    ui.shot("The Metamodel page, whose Export YAML button produced a loadable pack")


# =================================================================== the import template


@pytest.mark.scenario(
    scenario_id="N09",
    group="N",
    title="The import template downloads as an archive holding the four files the contract needs",
    feature="Downloads · import · the template archive",
    expected="Download template returns ea-import-template.zip: a readable archive of README.md, "
    "elements.csv, relationships.csv and links.csv, each CSV carrying the header columns the "
    "importer reads and at least one example row.",
)
def test_import_template_archive(ui, record):
    ui.goto("/import")
    path = ui.download("im-template", ".zip")
    ui.check("the archive is named for what it is", path.name == "ea-import-template.zip", path.name)
    ui.must("the file is a zip archive", zipfile.is_zipfile(path), f"{path.stat().st_size} bytes")
    with zipfile.ZipFile(path) as archive:
        damaged = archive.testzip()
        ui.check(
            "the archive is not damaged",
            damaged is None,
            "every entry read back" if damaged is None else f"{damaged} is corrupt",
        )
        names = sorted(archive.namelist())
        ui.check(
            "it holds the four template files and nothing else",
            names == ["README.md", "elements.csv", "links.csv", "relationships.csv"],
            f"it holds {names}",
        )
        for name in names:
            ui.check(
                f"{name} has content",
                archive.getinfo(name).file_size > 0,
                f"{archive.getinfo(name).file_size} bytes",
            )
        readme = archive.read("README.md").decode("utf-8")
        ui.check(
            "the README says what the files are for",
            "import" in readme.lower() and "csv" in readme.lower(),
            readme[:120].replace("\n", " · "),
        )
        expected = {
            "elements.csv": ("id", "type", "name", "current_state", "target_state"),
            "relationships.csv": ("src_id", "rel_type", "dst_id"),
            "links.csv": ("element_id", "url", "label"),
        }
        for name, columns in expected.items():
            rows = list(csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig"))))
            header = rows[0] if rows else []
            missing = [c for c in columns if c not in header]
            ui.check(f"{name} carries the columns the importer reads", not missing, f"missing {missing}")
            ui.check(f"{name} shows at least one example row", len(rows) > 1, f"{len(rows)} lines")
    ui.shot("The Import page and the template archive it hands out")


# =================================================================== the proposal template


@pytest.mark.scenario(
    scenario_id="N10",
    group="N",
    title="The Proposal Template downloads as the Markdown the analysis reads",
    feature="Downloads · Propose · the template",
    expected="Download Proposal Template returns proposal-template.md: a titled document with the "
    "sections a proposal needs and the two tables — elements and relationships — the analysis reads, "
    "each with its worked example row.",
)
def test_proposal_template(ui, record):
    ui.goto("/propose")
    path = ui.download("pr-template", ".md")
    ui.check("the file is named for what it is", path.name == "proposal-template.md", path.name)
    text = _text(path)
    ui.check("it opens as a proposal", text.lstrip().startswith("# Proposal:"), text.splitlines()[0])
    for heading in ("## Summary", "## Elements", "## Relationships"):
        ui.check(f"it offers the '{heading.strip('# ')}' section", heading in text, "")
    ui.check(
        "the elements table names the columns the analysis reads",
        "| Type | Name | Existing id | Description | Current state | Target state |" in text,
        next((line for line in text.splitlines() if line.startswith("| Type |")), "no elements header"),
    )
    ui.check(
        "the relationships table names its own",
        "| Source | Relationship | Target | Note |" in text,
        next(
            (line for line in text.splitlines() if line.startswith("| Source |")), "no relationships header"
        ),
    )
    rows = [line for line in text.splitlines() if line.startswith("|") and "---" not in line]
    ui.check("and both tables come filled in with an example", len(rows) >= 10, f"{len(rows)} table rows")
    vocabulary = ("proposed", "live", "decommission", "keep", "new", "change")
    absent = [word for word in vocabulary if word not in text]
    ui.check(
        "the states it offers are the vocabulary the model uses",
        not absent,
        f"missing from the template: {absent}" if absent else f"all of {list(vocabulary)}",
    )
    ui.shot("The Propose page and the template it starts an architect from")


# ============================================== the one component, used eleven times over


@pytest.mark.scenario(
    scenario_id="N11",
    group="N",
    title="Every file the application produces arrives in one session through one component",
    feature="Downloads · the shared download component",
    expected="Walking the seven pages that produce a file and pressing all eleven buttons in one "
    "browser session yields eleven files, each with a distinct name and real content, with no page "
    "declaring a download component of its own.",
)
def test_every_producer_in_one_session(ui, record):
    produced: list[tuple[str, Path]] = []
    components: dict[str, int] = {}

    def count_component(page: str) -> None:
        components[page] = ui.page.evaluate("() => document.querySelectorAll('#download').length")

    _open_element_view(ui)
    count_component("element")
    produced.append(("element view · Markdown", ui.download("el-view-md", ".md")))
    produced.append(("element view · draw.io", ui.download("el-view-drawio", ".drawio")))

    _open_impact(ui)
    count_component("impact")
    produced.append(("impact view · Markdown", ui.download("imp-view-md", ".md")))
    produced.append(("impact view · draw.io", ui.download("imp-view-drawio", ".drawio")))

    _open_target(ui)
    count_component("target")
    produced.append(("target state · Markdown", ui.download("tg-view-md", ".md")))
    produced.append(("target state · draw.io", ui.download("tg-view-drawio", ".drawio")))

    _ask(ui)
    count_component("ask")
    produced.append(("answer document · Markdown", ui.download("ask-doc-md", ".md")))
    produced.append(("answer document · draw.io", ui.download("ask-doc-drawio", ".drawio")))
    ui.shot("The answer document, the fourth of the seven pages that produce a file")

    ui.goto("/metamodel")
    count_component("metamodel")
    produced.append(("metamodel pack", ui.download("mm-export", ".yaml")))

    ui.goto("/import")
    count_component("import")
    produced.append(("import template", ui.download("im-template", ".zip")))

    ui.goto("/propose")
    count_component("propose")
    produced.append(("proposal template", ui.download("pr-template", ".md")))
    ui.shot("The Propose page, the last producer of the sweep")

    ui.check("all eleven files were produced in one session", len(produced) == 11, f"{len(produced)} files")
    names = [p.name for _, p in produced]
    ui.check(
        "every file has a name of its own",
        len(set(names)) == len(names),
        "; ".join(sorted(n for n in names if names.count(n) > 1)) or "; ".join(names),
    )
    empty = [f"{what} ({p.name})" for what, p in produced if p.stat().st_size == 0]
    ui.check(
        "and content",
        not empty,
        f"empty: {empty}" if empty else f"{sum(p.stat().st_size for _, p in produced)} bytes in all",
    )
    ui.check(
        "every page serves its downloads through the one shell component, not one of its own",
        len(set(components.values())) == 1 and max(components.values()) <= 1,
        "; ".join(f"{page}: {n}" for page, n in components.items())
        + " node(s) carrying the shared download id",
    )


@pytest.mark.scenario(
    scenario_id="N12",
    group="N",
    title="The same file can be downloaded twice in a row",
    feature="Downloads · the shared download component",
    expected="Pressing the same download button twice produces the file twice: the one shared "
    "component is not spent by the first press, so a reader who lost the first file can ask again.",
)
def test_the_same_download_twice(ui, record, finding):
    _open_element_view(ui)
    first = ui.download("el-view-md", ".md")
    ui.check("the first press produced the file", first.exists() and first.stat().st_size > 0, first.name)
    second, why = _try_download(ui, "el-view-md")
    got_second = second is not None
    ui.check("and pressing the same button again produces it again", got_second, why)
    if got_second:
        ui.check(
            "the second file is the same document",
            _text(second) == _text(first),
            f"{len(_text(second))} characters against {len(_text(first))}",
        )
    else:
        finding.append(
            _f(
                "N-repeat-download",
                "src/ea/ui/layout.py · the shared dcc.Download, and every view toolbar that writes to it",
                "defect",
                "Pressing a download button a second time with nothing changed in between produces no file.",
                "The whole application writes to one dcc.Download; when the callback returns the same "
                "content twice, the component's data property does not change and no file is offered. "
                "The reader gets no file and no message.",
            )
        )
    # A different button on the same page must still work after that, whatever happened above.
    other, why = _try_download(ui, "el-view-drawio")
    ui.check("a different file from the same page still comes through", other is not None, why)
    ui.shot("The element view after being downloaded twice from the same button")


@pytest.mark.scenario(
    scenario_id="N13",
    group="N",
    title="A download offered before there is anything to export says so",
    feature="Downloads · nothing to export",
    expected="The Impact page offers both downloads before an element is chosen. Pressing one should "
    "either produce a file or say why none came — a control that is enabled, silently does nothing "
    "and leaves no message cannot be told from one that is broken or slow.",
)
def test_a_download_with_nothing_to_produce(ui, record, finding):
    ui.goto("/impact")
    ui.must("the Impact page offers the view's downloads", ui.visible("imp-view-md"))
    drawn = ui.page.locator(f"{_pm(id='imp-view', type='mermaid-svg')} svg").count()
    ui.check(
        "with no element chosen there is no view to export",
        drawn == 0,
        f"{drawn} diagrams were drawn without an element",
    )
    before = ui.body()
    produced, why = _try_download(ui, "imp-view-md")
    said = ui.body() != before or ui.page.locator(".mantine-Notification-root").count() > 0
    disabled = ui.disabled("imp-view-md")
    ui.check(
        "pressing Download Markdown then produces a file, or is refused with a reason",
        produced is not None or disabled or said,
        f"a file arrived: {produced.name}"
        if produced is not None
        else f"the button is enabled, the page said nothing, and no file came ({why})",
    )
    ui.shot("The Impact page before an element is chosen, offering two downloads of an empty view")
    if produced is None and not said and not disabled:
        finding.append(
            _f(
                "N-impact-empty-download",
                "src/ea/ui/pages/impact.py · view_toolbar(IMP_VIEW_MD, IMP_VIEW_DRAWIO) and download_view",
                "usability",
                "The Impact page offers Download Markdown and Download draw.io before an element is "
                "chosen; pressing either does nothing and says nothing.",
                "download_view returns no_update when no element is selected, so the press is swallowed. "
                "The reader cannot tell a slow export from a broken one. Either disable the two buttons "
                "until an element is chosen — saying why they are disabled — or answer the press.",
            )
        )


@pytest.mark.scenario(
    scenario_id="N14",
    group="N",
    title="An answer that drew no diagram can still be taken away as Markdown",
    feature="Downloads · Ask · a document with no view",
    expected="An answer that grounds no element draws no diagram. Its Markdown — the answer, the "
    "identifiers it could not ground and the trace — is still a document, so Download Markdown must "
    "still produce it; a missing diagram may cost the reader the draw.io file, never the document.",
)
def test_an_answer_without_a_diagram(ui, record, finding):
    console: list[str] = []

    def listen(message) -> None:
        console.append(message.text)

    md: Path | None = None
    ui.page.on("console", listen)
    try:
        _ask(ui, f"What is the impact of changing {GHOST}?")
        drew = ui.page.locator("#ask-answer .ea-mermaid svg").count()
        ui.must("the answer grounded nothing and so drew no diagram", drew == 0, f"{drew} diagrams")
        answer = ui.body()
        ui.check(
            "the document is still a document: it says what it could not find",
            GHOST in answer,
            f"the answer reads {answer[answer.find('ANSWER') : answer.find('ANSWER') + 90]!r}"
            if "ANSWER" in answer
            else "the answer does not name the identifier it could not ground",
        )
        ui.check(
            "and it still offers both downloads", ui.visible("ask-doc-md") and ui.visible("ask-doc-drawio")
        )
        ui.shot("An answer with no diagram, still offering Download Markdown and Download draw.io")

        md, why_md = _try_download(ui, "ask-doc-md")
        ui.check("Download Markdown produces the document", md is not None, why_md)
        drawio, why_drawio = _try_download(ui, "ask-doc-drawio")
        refused = ui.disabled("ask-doc-drawio")
        ui.check(
            "and the diagram is either produced or refused with a reason",
            drawio is not None or refused,
            f"a file arrived: {drawio.name}"
            if drawio is not None
            else f"the button is enabled and nothing came ({why_drawio})",
        )
        complaint = next(
            (m for m in console if "not been found in the layout" in m or "nonexistent" in m.lower()), ""
        )
        ui.check(
            "and the browser is not left complaining about a component that is missing",
            not complaint,
            complaint[:220] or "nothing was logged",
        )
    finally:
        ui.page.remove_listener("console", listen)

    # The same button, on an answer that does draw a diagram: proof the button itself is sound.
    _ask(ui)
    again, why_again = _try_download(ui, "ask-doc-md")
    ui.check(
        "the same button produces the file for an answer that does carry a diagram",
        again is not None,
        why_again,
    )
    ui.shot("The same Download Markdown button on an answer that does carry a diagram")
    ui.click("ask-reset")  # leave the conversation where the group found it
    if md is None and again is not None:
        finding.append(
            _f(
                "N-ask-download-dies-with-the-diagram",
                "src/ea/ui/pages/ask.py · download_doc, whose State names {'type': 'mermaid-pos', "
                "'id': 'ask-view-0'}",
                "defect",
                "When an answer draws no diagram, neither of the document's downloads works — the "
                "Markdown of the whole document is lost with it, and no message is shown.",
                "download_doc takes the position store of the first view as State. A document that "
                "grounded no element renders no view, so that component is not in the layout and the "
                "callback never runs: the press reaches no server call at all. The same button works "
                "on an answer that does carry a diagram. Reading the positions from a store that always "
                "exists — or through a wildcard — would keep the Markdown reachable.",
            )
        )
