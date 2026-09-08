"""Group N — Downloads: every file the application can produce, read as a file.

Eleven files leave this application, and every one of them leaves through the same
component: a single `dcc.Download` in the shell (`ui/layout.py`), which seven callbacks
on seven pages write to. So the group has three jobs. The first is to prove each producer
separately — the element view, the impact view and the target-state view, each as Markdown
and as draw.io; the answer document, the same two ways; the metamodel pack as YAML; the
import template as a zip; and the Proposal Template as Markdown. The second is to prove
that the one shared component survives being used eleven times in a session and twice in a
row on the same button. The third is what a download button does when there is nothing to
produce, which is where the group's two failures are: a press that is swallowed in silence
tells the reader nothing, and on the Ask page a document that drew no diagram cannot be
downloaded at all, because the callback states a component that only exists with the
diagram.

Both of those failures are fixed, and the two scenarios that found them now pass: the
Impact page disables both buttons and puts the reason beside them, and the Ask page reads
the positions of every view through a wildcard, so a document that drew no diagram still
comes down as Markdown. Two more jobs stand behind them. The fourth is the control that
decides what a file holds — the element page's depth slider and the impact page's depth box
are State on their download callbacks, the work-package selector names the target-state
file, and the layout the browser reports is what the draw.io export is written from, shape
for shape, including one the reader has moved by hand. The fifth is holding a file against
the page it came from — the impact file against the tables of the answer it exports, the
metamodel against the counts the page prints, the clipboard against the file the button
writes — and against who asked for it: downloading is a read, so a Reader is handed the same
document an Admin is while the write control beside it stays refused.

That leaves the group two failures of its own. An answer that drew no diagram disables
Download draw.io and then says nothing: the reason is computed, used to grey the button out
and dropped, where the Impact page shows its own (N24). And a view first drawn on a tab the
page did not open on is measured while it is hidden, so every shape in its draw.io file is
the same default box; Reset layout, pressed with the tab in front of the reader, re-measures
the view and the very next file is right (N25).

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


# =========================================== the controls that decide what the file holds


def _depth_thumb(ui):
    """The element page's depth slider, which the download reads as State."""
    return ui.page.locator("#el-graph-depth [role='slider']").first


def _impact_depth_box(ui):
    """A Mantine NumberInput carries its id on the wrapper or on the field; take whichever is there."""
    return ui.page.locator("#imp-depth input, input#imp-depth").first


def _set_impact_depth(ui, depth: int) -> None:
    box = _impact_depth_box(ui)
    box.click()
    box.fill(str(depth))
    ui.page.wait_for_timeout(200)
    ui.settle()


def _screen_nodes(ui, block_id: str) -> dict[str, dict[str, float]]:
    """Every shape the browser drew in one generated view: its identifier, centre and size.

    Read out of the rendered SVG the way the page's own script reads it — the label ends in
    `[ID]`, the group carries a translate — so a file can be held against the picture a
    reader is looking at rather than against another copy of the same server-side call.
    """
    rows = ui.page.evaluate(
        r"""(sel) => Array.from(document.querySelectorAll(sel + ' g.node')).map(g => {
            const m = /\[([^\[\]]+)\]\s*$/.exec((g.textContent || '').trim());
            const t = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(g.getAttribute('transform') || '');
            let bb;
            try { bb = g.getBBox(); } catch (e) { bb = {width: 0, height: 0}; }
            return {
                id: m ? m[1] : '', x: t ? parseFloat(t[1]) : null, y: t ? parseFloat(t[2]) : null,
                w: bb.width, h: bb.height,
            };
        }).filter(n => n.id && n.x !== null)""",
        _pm(id=block_id, type="mermaid-svg"),
    )
    return {r["id"]: r for r in rows}


def _file_boxes(root: ET.Element) -> dict[str, dict[str, float]]:
    """Where the exported file puts each shape: the geometry of every element's own cell."""
    out: dict[str, dict[str, float]] = {}
    for shape in _shapes(root):
        cell = shape.find("mxCell")
        geometry = cell.find("mxGeometry") if cell is not None else None
        if geometry is None:
            continue
        out[shape.get("ea_id", "")] = {
            "x": float(geometry.get("x") or 0),
            "y": float(geometry.get("y") or 0),
            "w": float(geometry.get("width") or 0),
            "h": float(geometry.get("height") or 0),
            "parent": cell.get("parent") or "",
        }
    return out


def _linked_ids(ui, selector: str) -> set[str]:
    """Every element the page names inside `selector`, read from the links it renders."""
    hrefs = ui.page.locator(f"{selector} a[href^='/element/']").evaluate_all(
        "els => els.map(a => a.getAttribute('href') || '')"
    )
    return {h.rsplit("/", 1)[-1] for h in hrefs if h}


def _marked_rows(text: str) -> dict[str, tuple[str, str]]:
    """The identifier, current state and target state of every row of a marked view's table."""
    out: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = TABLE_ID.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            out[m.group(1)] = (cells[-2], cells[-1])
    return out


@pytest.mark.scenario(
    scenario_id="N15",
    group="N",
    title="The file holds the depth the reader chose, not the depth the page opened at",
    feature="Downloads · element view · the depth control",
    expected="The element view's depth slider is State on the download callback. Moved from 1 to 3 it "
    "must change the file: a title saying depth 3, every element the depth-1 file held and more, and a "
    "draw.io file of the same widened view.",
)
def test_the_depth_control_decides_the_file(ui, record):
    _open_element_view(ui)
    near = _text(ui.download("el-view-md", ".md"))
    near_ids = _table_ids(near)
    ui.must("the file at depth 1 lists a neighbourhood", len(near_ids) >= 2, f"{len(near_ids)} rows")
    ui.check(
        "and says which depth it was taken at", "(depth 1)" in near.splitlines()[0], near.splitlines()[0]
    )

    thumb = _depth_thumb(ui)
    thumb.press("ArrowRight")
    thumb.press("ArrowRight")
    ui.page.wait_for_timeout(700)
    ui.settle()
    ui.must(
        "the slider is on depth 3",
        (thumb.get_attribute("aria-valuenow") or "") == "3",
        f"it reports {thumb.get_attribute('aria-valuenow')!r}",
    )
    try:
        ui.page.wait_for_function(
            "([sel, n]) => document.querySelectorAll(sel + ' g.node').length > n",
            arg=[_pm(id="el-view", type="mermaid-svg"), len(near_ids)],
            timeout=25_000,
        )
    except Exception as exc:  # noqa: BLE001 — the redraw is the page's, the file is the finding
        ui.check("the diagram redrew at the new depth", False, f"{type(exc).__name__}")

    far_path = ui.download("el-view-md", ".md")
    far = _text(far_path)
    far_ids = _table_ids(far)
    ui.check(
        "the file taken afterwards says it is the wider view",
        "(depth 3)" in far.splitlines()[0],
        far.splitlines()[0],
    )
    _check_markdown_view(ui, far_path, f"{EL_NAME} and its neighbourhood")
    missing = [i for i in near_ids if i not in far_ids]
    ui.check(
        "the wider view keeps everything the narrower one held",
        not missing,
        f"lost at depth 3: {missing[:5]}" if missing else f"all {len(near_ids)} of them",
    )
    ui.check(
        "and reaches further than it",
        len(far_ids) > len(near_ids),
        f"{len(near_ids)} elements at depth 1, {len(far_ids)} at depth 3",
    )
    drawn = list(_screen_nodes(ui, "el-view"))
    ui.check(
        "the file holds exactly what the reader is looking at",
        sorted(drawn) == sorted(far_ids),
        f"{len(drawn)} shapes drawn against {len(far_ids)} rows in the file",
    )
    drawio = ui.download("el-view-drawio", ".drawio")
    shape_ids = _shape_ids(_drawio(ui, drawio))
    ui.check(
        "and the draw.io file of the same view was taken at the same depth",
        sorted(set(shape_ids)) == sorted(set(far_ids)),
        f"{len(set(shape_ids))} shapes against {len(set(far_ids))} rows",
    )
    ui.shot("The element view at depth 3, and the two files taken from it")


@pytest.mark.scenario(
    scenario_id="N16",
    group="N",
    title="The impact file holds exactly the elements the page's tables name, at the depth that was run",
    feature="Downloads · impact view · the depth control",
    expected="The exported impact view is the answer on the page: the same elements as the upstream and "
    "downstream tables, no more and no fewer. Run again at one hop and the file narrows with the page.",
)
def test_the_impact_file_matches_the_page(ui, record):
    _open_impact(ui)
    deep_shown = _linked_ids(ui, "#imp-result")
    ui.must("the page answered with elements", len(deep_shown) >= 2, f"{len(deep_shown)} elements linked")
    deep = _text(ui.download("imp-view-md", ".md"))
    deep_ids = set(_table_ids(deep))
    capped = "not shown" in deep or "capped" in deep
    ui.check(
        "the file holds every element the page's tables name",
        not (deep_shown - deep_ids),
        f"named but not exported: {sorted(deep_shown - deep_ids)[:5]}"
        if deep_shown - deep_ids
        else f"all {len(deep_shown)} of them",
    )
    ui.check(
        "and draws nothing the page did not name",
        not (deep_ids - deep_shown) or capped,
        f"exported but not named: {sorted(deep_ids - deep_shown)[:5]}"
        if deep_ids - deep_shown
        else f"{len(deep_ids)} rows",
    )

    _set_impact_depth(ui, 1)
    ui.click("imp-run")
    ui.wait_mermaid()
    shallow_shown = _linked_ids(ui, "#imp-result")
    shallow_path = ui.download("imp-view-md", ".md")
    shallow = _text(shallow_path)
    shallow_ids = set(_table_ids(shallow))
    ui.check(
        "run again at one hop, the file is the one-hop answer",
        shallow_ids == shallow_shown,
        f"{len(shallow_ids)} rows against {len(shallow_shown)} elements on the page"
        + (
            f"; only in the file: {sorted(shallow_ids - shallow_shown)[:5]}"
            if shallow_ids - shallow_shown
            else ""
        ),
    )
    ui.check(
        "which is narrower than the three-hop one",
        len(shallow_ids) < len(deep_ids),
        f"{len(shallow_ids)} at one hop against {len(deep_ids)} at three",
    )
    ui.check(
        "and holds nothing the wider run did not",
        not (shallow_ids - deep_ids),
        f"only at one hop: {sorted(shallow_ids - deep_ids)[:5]}" if shallow_ids - deep_ids else "nothing new",
    )
    ui.check(
        "the file is still named for the element, not for the depth it was run at",
        shallow_path.name == f"{IMP}-impact.md",
        shallow_path.name,
    )
    ui.shot("The impact page run at one hop, and the narrower file it exports")


@pytest.mark.scenario(
    scenario_id="N17",
    group="N",
    title="With no work package chosen the target state exports the whole model, named for all of it",
    feature="Downloads · target state · all work packages",
    expected="On 'All work packages' both downloads are named target-state-all, titled 'Target state of "
    "the model', and hold what changes or is deliberately kept across the model — never an element "
    "nobody has decided about — including everything the one work package's own file holds.",
)
def test_target_state_of_the_whole_model(ui, record):
    ui.goto("/target")
    ui.wait_mermaid()
    path = ui.download("tg-view-md", ".md")
    ui.check("the file is named for the whole model", path.name == "target-state-all.md", path.name)
    text = _check_markdown_view(ui, path, "Target state of the model")
    rows = _marked_rows(text)
    ui.must("it carries a table of states", len(rows) >= 2, f"{len(rows)} rows")
    ui.check(
        "every row carries both states",
        all(current and target for current, target in rows.values()),
        "; ".join(f"{k}: {v[0]}/{v[1]}" for k, v in list(rows.items())[:3]),
    )
    undecided = [k for k, (_, target) in rows.items() if target.lower().startswith("undecided")]
    ui.check(
        "and nothing nobody has decided about, because that is not a target state",
        not undecided,
        f"undecided in the model-wide export: {undecided[:5]}" if undecided else f"{len(rows)} decided rows",
    )
    ui.check(
        "the decommissioned element is one of them",
        FORMS in rows,
        f"{FORMS} is in the file, as {rows[FORMS][0]} today and {rows[FORMS][1]} intended"
        if FORMS in rows
        else f"the file lists {sorted(rows)[:6]}",
    )
    diagram = MERMAID_FENCE.findall(text)[0]
    marked = next((line for line in diagram.splitlines() if FORMS in line), "")
    ui.check("marked in the diagram the way the legend says", "×" in marked, marked.strip() or "not drawn")

    drawio = ui.download("tg-view-drawio", ".drawio")
    ui.check(
        "the draw.io file is named for the whole model too",
        drawio.name == "target-state-all.drawio",
        drawio.name,
    )
    root = _drawio(ui, drawio)
    _check_linking_contract(ui, root, ui.base_url)
    ui.check(
        "and holds the same elements as the Markdown",
        sorted(set(_shape_ids(root))) == sorted(rows),
        f"{len(set(_shape_ids(root)))} shapes against {len(rows)} rows",
    )
    ui.shot("Target state with no work package chosen, exported as the whole model")

    # The one work package's file is a part of the model's, not a different model.
    ui.select("tg-wp", WP_NAME)
    ui.wait_mermaid()
    package = _text(ui.download("tg-view-md", ".md"))
    ui.check(
        "choosing a work package renames the file after it",
        (ui.run_dir / "downloads" / f"target-state-{WP}.md").exists(),
        f"target-state-{WP}.md",
    )
    decided = {
        k for k, (_, target) in _marked_rows(package).items() if not target.lower().startswith("undecided")
    }
    absent = sorted(decided - set(rows))
    ui.check(
        "and everything it decides is in the model-wide file as well",
        not absent,
        f"only in the work package's file: {absent[:5]}" if absent else f"all {len(decided)} of them",
    )


# ================================================ the other way out, and who may use it


@pytest.mark.scenario(
    scenario_id="N18",
    group="N",
    title="Copy Markdown hands over exactly the document Download Markdown writes",
    feature="Downloads · Ask · copy against file",
    expected="The answer document offers Copy Markdown beside the two downloads. What lands on the "
    "clipboard is the same document the file holds, character for character — two ways out of one "
    "document, not two documents.",
)
def test_copy_gives_the_same_document_as_the_file(ui, record):
    _ask(ui)
    md = ui.download("ask-doc-md", ".md")
    written = _text(md)
    clipboard = ui.page.locator(f"{DOCUMENT} .ea-clipboard")
    ui.must("the document offers a copy control beside its downloads", clipboard.count() > 0)
    copied = ""
    try:
        ui.page.evaluate("() => navigator.clipboard.writeText('')")
        clipboard.first.click()
        ui.page.wait_for_timeout(400)
        copied = ui.page.evaluate("() => navigator.clipboard.readText()")
    except Exception as exc:  # noqa: BLE001 — a browser that refuses the clipboard is not the app's fault
        ui.check("the clipboard could be read back in this browser", True, f"not read: {exc}")
    if copied:
        ui.check(
            "what was copied is the whole document, not a fragment",
            copied.strip().startswith("# ") and "## Answer" in copied,
            f"the clipboard holds {len(copied)} characters starting {copied[:60]!r}",
        )
        ui.check(
            "and it is the file, character for character",
            copied.strip() == written.strip(),
            f"{len(copied)} characters copied against {len(written)} written"
            if copied.strip() != written.strip()
            else f"both are the same {len(written)} characters",
        )
        ui.check(
            "so the elements the document names travel with either one",
            OFFERING in copied,
            f"{OFFERING} is in both" if OFFERING in copied else f"{OFFERING} is not in the copied text",
        )
    ui.shot("The answer document, whose Copy Markdown and Download Markdown carry the same text")
    ui.click("ask-reset")  # leave the conversation where the group found it


@pytest.mark.scenario(
    scenario_id="N19",
    group="N",
    title="A Reader may take every file away, and gets the same file an Admin gets",
    feature="Downloads · roles · a Reader",
    expected="Downloading is a read, and the roles table gives every role it. As a Reader the view, the "
    "impact, the metamodel, the import template and the proposal template must all still arrive — "
    "unredacted, the same document an Admin was handed — while the write control beside each is refused.",
)
def test_a_reader_may_take_every_file(ui, record):
    _open_element_view(ui)
    as_admin = _text(ui.download("el-view-md", ".md"))

    ui.persona("Reader")
    ui.check("the header says who is reading", "reader" in ui.role_badge().lower(), ui.role_badge())

    _open_element_view(ui)
    view = ui.download("el-view-md", ".md")
    ui.check("a Reader is handed the element view", view.name == f"{EL}-view.md", view.name)
    ui.check(
        "and it is the document an Admin was handed, not a redacted one",
        _text(view) == as_admin,
        f"{len(_text(view))} characters against {len(as_admin)}",
    )
    drawio = ui.download("el-view-drawio", ".drawio")
    _check_linking_contract(ui, _drawio(ui, drawio), ui.base_url)

    _open_impact(ui)
    impact = ui.download("imp-view-md", ".md")
    _check_markdown_view(ui, impact, f"Impact of {IMP_NAME}")

    ui.goto("/metamodel")
    ui.check("a Reader may not save the metamodel", ui.disabled("mm-save"))
    pack = ui.download("mm-export", ".yaml")
    ui.check(
        "but may export it",
        (yaml.safe_load(_text(pack)) or {}).get("pack", {}).get("id") == PACK,
        pack.name,
    )
    ui.shot("The Metamodel page as a Reader: Save refused, Export YAML given")

    ui.goto("/import")
    ui.check("a Reader may not load an import", ui.disabled("im-load"))
    template = ui.download("im-template", ".zip")
    ui.check(
        "but may take the template that says how one is shaped",
        zipfile.is_zipfile(template),
        template.name,
    )

    ui.goto("/propose")
    proposal = ui.download("pr-template", ".md")
    ui.check(
        "and may take the proposal template, which is how a Reader asks for a change",
        _text(proposal).lstrip().startswith("# Proposal:"),
        _text(proposal).splitlines()[0],
    )
    ui.shot("The Propose page as a Reader, handing over the template it starts from")
    ui.persona("Admin")  # leave the session as the round found it


# ======================================= the file against the page it was taken from


@pytest.mark.scenario(
    scenario_id="N20",
    group="N",
    title="The exported metamodel is the metamodel the page says it holds",
    feature="Downloads · metamodel · the file against the page",
    expected="The Metamodel page says how many active types, inactive types and relationship types it "
    "holds. The exported pack must hold exactly those, under the pack name shown, and carry the "
    "notation every generated view is drawn from.",
)
def test_the_metamodel_file_agrees_with_the_page(ui, record):
    ui.goto("/metamodel")
    subtitle = ui.text("mm-subtitle")
    counted = re.search(r"(\d+) active types, (\d+) inactive, (\d+) relationship types", subtitle)
    ui.must("the page says what the metamodel holds", counted is not None, subtitle or "no subtitle")
    active, inactive, rel_types = (int(g) for g in counted.groups())

    path = ui.download("mm-export", ".yaml")
    data = yaml.safe_load(_text(path)) or {}
    types = data.get("element_types") or []
    dormant = [t for t in types if t.get("active") is False]
    ui.check(
        "the pack is named as the page names it",
        subtitle.startswith(str(data.get("pack", {}).get("name") or " ")),
        f"the page says {subtitle[:60]!r}, the file says {data.get('pack', {}).get('name')!r}",
    )
    ui.check(
        "it holds every type the page counts",
        len(types) == active + inactive,
        f"{len(types)} in the file against {active} active and {inactive} inactive on the page",
    )
    ui.check(
        "with the inactive ones marked inactive rather than dropped",
        len(dormant) == inactive,
        f"{len(dormant)} marked inactive in the file against {inactive} on the page",
    )
    ui.check(
        "and every relationship type the page counts",
        len(data.get("relationship_types") or []) == rel_types,
        f"{len(data.get('relationship_types') or [])} in the file against {rel_types} on the page",
    )
    entity = next((t for t in types if t.get("id") == "data_entity"), None)
    ui.must("a type the sample model uses is in the file", entity is not None)
    notation = entity.get("notation") or {}
    ui.check(
        "which carries the notation the generated views are drawn from",
        bool(notation.get("archimate")) and bool(notation.get("shape")) and bool(notation.get("layer")),
        f"its notation is {notation}",
    )
    unnotated = [d.get("id") for d in (data.get("domains") or []) if not (d.get("notation") or {}).get("hex")]
    ui.check(
        "and every domain the colour the pages draw it in",
        not unnotated,
        f"without a colour: {unnotated}" if unnotated else f"all {len(data.get('domains') or [])} domains",
    )
    ui.check(
        "the attributes every type shares travel with it",
        len(data.get("common_attributes") or []) > 0,
        f"{len(data.get('common_attributes') or [])} common attributes",
    )
    ui.shot("The Metamodel page and the counts the exported pack has to match")


@pytest.mark.scenario(
    scenario_id="N21",
    group="N",
    title="The draw.io file puts every shape where the reader sees it",
    feature="Downloads · draw.io · the reader's arrangement",
    expected="The browser reports the layout of a generated view, and the draw.io export is written from "
    "it: every shape on the page itself rather than in a generated grid, each one the size it is drawn "
    "and all of them shifted by the one margin, so the file opens as the picture on screen.",
)
def test_the_file_reproduces_the_layout_on_screen(ui, record):
    _open_impact(ui)
    screen = _screen_nodes(ui, "imp-view")
    ui.must("the browser drew the view", len(screen) >= 3, f"{len(screen)} shapes on screen")
    root = _drawio(ui, ui.download("imp-view-drawio", ".drawio"))
    boxes = _file_boxes(root)
    ui.must(
        "the file holds a shape for each one", set(screen) <= set(boxes), f"{len(boxes)} shapes in the file"
    )
    parents = {b["parent"] for b in boxes.values()}
    ui.check(
        "every shape sits on the page itself, not in a generated grid of lanes",
        parents == {"1"},
        f"their parents are {sorted(parents)}",
    )
    sized = [
        f"{eid}: {boxes[eid]['w']:.0f} by {boxes[eid]['h']:.0f} against "
        f"{screen[eid]['w']:.0f} by {screen[eid]['h']:.0f}"
        for eid in screen
        if abs(boxes[eid]["w"] - screen[eid]["w"]) > 2 or abs(boxes[eid]["h"] - screen[eid]["h"]) > 2
    ]
    ui.check(
        "each is the size it is drawn on screen",
        not sized,
        "; ".join(sized[:3]) if sized else f"all {len(screen)} of them",
    )
    offsets = {
        eid: (
            round(screen[eid]["x"] - screen[eid]["w"] / 2 - boxes[eid]["x"], 1),
            round(screen[eid]["y"] - screen[eid]["h"] / 2 - boxes[eid]["y"], 1),
        )
        for eid in screen
    }
    xs = [o[0] for o in offsets.values()]
    ys = [o[1] for o in offsets.values()]
    spread = f"{max(xs) - min(xs):.1f} across and {max(ys) - min(ys):.1f} down"
    ui.check(
        "and all of them are shifted by the one margin, so the file is the arrangement on screen",
        max(xs) - min(xs) <= 2 and max(ys) - min(ys) <= 2,
        f"the shift spans {spread}"
        + (
            "; " + "; ".join(f"{k} at {v}" for k, v in list(offsets.items())[:3])
            if max(xs) - min(xs) > 2 or max(ys) - min(ys) > 2
            else ""
        ),
    )
    lanes = [c for c in root.findall(".//mxCell") if (c.get("id") or "").startswith("lane_")]
    ui.check(
        "the layer boxes are drawn behind the shapes rather than around them",
        all("dashed=1" in (c.get("style") or "") for c in lanes),
        "; ".join((c.get("id") or "") for c in lanes) or "no layer boxes",
    )
    ui.shot("The view on screen, and the draw.io file written from the same layout")


@pytest.mark.scenario(
    scenario_id="N22",
    group="N",
    title="A shape the reader moved is where they left it in the file",
    feature="Downloads · draw.io · a shape moved by hand",
    expected="The page says Ctrl-drag moves a shape and that nothing is saved; the draw.io export is what "
    "the move is for. Moving the element's own shape and exporting again must put it where it was left, "
    "the same distance from its neighbours as on screen.",
)
def test_a_shape_the_reader_moved(ui, record):
    _open_element_view(ui)
    before_screen = _screen_nodes(ui, "el-view")
    ui.must("the element's own shape is on the canvas", EL in before_screen, f"{len(before_screen)} shapes")
    before = _file_boxes(_drawio(ui, ui.download("el-view-drawio", ".drawio")))

    node = ui.page.locator(f"{_pm(id='el-view', type='mermaid-svg')} g.node").filter(has_text=f"[{EL}]").first
    box = node.bounding_box()
    ui.must("the shape can be aimed at", box is not None and box["width"] > 0, str(box))
    start = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    ui.page.mouse.move(*start)
    ui.page.keyboard.down("Control")
    ui.page.mouse.down()
    for step in range(1, 6):
        ui.page.mouse.move(start[0] + 44 * step, start[1] - 18 * step)
        ui.page.wait_for_timeout(40)
    ui.page.mouse.up()
    ui.page.keyboard.up("Control")
    ui.page.wait_for_timeout(500)
    ui.settle()

    after_screen = _screen_nodes(ui, "el-view")
    moved_x = after_screen[EL]["x"] - before_screen[EL]["x"]
    moved_y = after_screen[EL]["y"] - before_screen[EL]["y"]
    ui.must(
        "Ctrl-dragging the shape moved it on screen",
        abs(moved_x) > 20,
        f"it moved {moved_x:.0f} across and {moved_y:.0f} down, in the diagram's own units",
    )
    still = [
        eid
        for eid in before_screen
        if eid != EL and eid in after_screen and abs(after_screen[eid]["x"] - before_screen[eid]["x"]) > 1
    ]
    ui.check(
        "and moved nothing else",
        not still,
        f"also moved: {still[:5]}" if still else f"{len(after_screen)} shapes, one of them moved",
    )
    ui.shot("The element's own shape dragged clear of its neighbours")

    after = _file_boxes(_drawio(ui, ui.download("el-view-drawio", ".drawio")))
    ui.must("the file still holds the moved shape", EL in after, f"{len(after)} shapes in the file")
    neighbour = next(eid for eid in before if eid != EL and eid in after)
    shifted = (after[EL]["x"] - after[neighbour]["x"]) - (before[EL]["x"] - before[neighbour]["x"])
    ui.check(
        "the file exported afterwards carries the move, not the layout before it",
        abs(shifted - moved_x) <= 3,
        f"it moved {shifted:.0f} away from {neighbour} in the file against {moved_x:.0f} on screen",
    )
    disturbed = [
        eid
        for eid in before
        if eid not in (EL, neighbour)
        and eid in after
        and abs((after[eid]["x"] - after[neighbour]["x"]) - (before[eid]["x"] - before[neighbour]["x"])) > 1
    ]
    ui.check(
        "and leaves every other shape where it already was",
        not disturbed,
        f"also moved in the file: {disturbed[:5]}"
        if disturbed
        else f"the other {len(before) - 1} shapes are unmoved",
    )


# ============================== a download that is refused, and what the reader is told


def _choose_impact_element(ui, element_id: str, search: str) -> None:
    """Pick an element in the Impact selector the way a reader does, so the run callback fires."""
    box = ui.page.locator("#imp-element input, input#imp-element").first
    box.click()
    box.fill("")
    ui.page.keyboard.type(search, delay=25)
    ui.page.wait_for_timeout(600)  # the selector asks the server per keystroke
    ui.settle()
    ui.page.locator("[role='option']").filter(has_text=f"[{element_id}]").first.click()
    ui.settle()


@pytest.mark.scenario(
    scenario_id="N23",
    group="N",
    title="The two impact downloads are refused with a reason until there is a view, then work",
    feature="Downloads · impact view · refused, then given",
    expected="With no element chosen both buttons are disabled and the line beside them says why. "
    "Choosing an element runs the impact, clears that line, enables both buttons, and each then "
    "produces the file named for the element.",
)
def test_the_impact_downloads_are_refused_then_given(ui, record):
    ui.goto("/impact")
    ui.check("Download Markdown is refused before an element is chosen", ui.disabled("imp-view-md"))
    ui.check("and so is Download draw.io", ui.disabled("imp-view-drawio"))
    note = ui.text("imp-view-note")
    ui.check(
        "the line beside them says why, so a reader is not left guessing",
        "no view to export" in note.lower() and "choose an element" in note.lower(),
        note or "there is nothing beside the buttons",
    )
    ui.shot("The Impact page with nothing chosen: both downloads refused, and the reason beside them")

    _choose_impact_element(ui, IMP, IMP_NAME)
    ui.wait_mermaid()
    ui.check("choosing an element enables Download Markdown", not ui.disabled("imp-view-md"))
    ui.check("and Download draw.io with it", not ui.disabled("imp-view-drawio"))
    after = ui.text("imp-view-note")
    ui.check(
        "and takes the refusal away, because it no longer applies",
        not after.strip(),
        "there is nothing beside the buttons now" if not after.strip() else f"it still reads {after!r}",
    )
    md = ui.download("imp-view-md", ".md")
    ui.check("the button now produces the file", md.name == f"{IMP}-impact.md", md.name)
    _check_markdown_view(ui, md, f"Impact of {IMP_NAME}")
    drawio = ui.download("imp-view-drawio", ".drawio")
    ui.check("and so does the other one", drawio.name == f"{IMP}-impact.drawio", drawio.name)
    _check_linking_contract(ui, _drawio(ui, drawio), ui.base_url)
    ui.shot("The same two buttons after an element was chosen, both now producing their file")


@pytest.mark.scenario(
    scenario_id="N24",
    group="N",
    title="A download the document refuses says why where the reader is looking",
    feature="Downloads · Ask · a refusal without a reason",
    expected="An answer that drew no diagram disables Download draw.io — the code even names the reason, "
    "'This answer drew no diagram, so there is nothing to export.' The reader has to be given it: on the "
    "button, described by it, or beside it, the way the Impact page gives its own.",
)
def test_a_refused_download_says_why(ui, record, finding):
    _ask(ui, f"What is the impact of changing {GHOST}?")
    drew = ui.page.locator("#ask-answer .ea-mermaid svg").count()
    ui.must("the answer grounded nothing and so drew no diagram", drew == 0, f"{drew} diagrams")
    refused = ui.disabled("ask-doc-drawio")
    ui.check(
        "the document refuses the diagram rather than offering a button that does nothing",
        refused,
        "Download draw.io is greyed out"
        if refused
        else "Download draw.io is offered on a document with no diagram",
    )
    button = ui.page.locator("#ask-doc-drawio").first
    ui.must("the button is in the document", button.count() > 0)
    title = (button.get_attribute("title") or "").strip()
    described = ui.page.evaluate(
        """() => {
            const el = document.getElementById('ask-doc-drawio');
            const ids = (el && el.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean);
            return ids.map(i => (document.getElementById(i) || {}).innerText || '').join(' ').trim();
        }"""
    )
    beside = button.evaluate(
        "el => ((el.closest('.mantine-Group-root') || el.parentElement || {}).innerText || '')"
    )
    beside = " ".join(beside.replace("Download draw.io", "").replace("Download Markdown", "").split())
    words = ("diagram", "nothing to export", "no view")
    told = [
        where
        for where, text in (("on the button", title), ("described by it", described), ("beside it", beside))
        if any(word in text.lower() for word in words)
    ]
    ui.check(
        "the reason the code computed reaches the reader",
        bool(told),
        f"the reader is told {', '.join(told)}"
        if told
        else f"title={title!r}, aria-describedby={described!r}, beside it {beside!r}",
    )
    ui.shot("An answer with no diagram: Download draw.io disabled, with nothing saying why")
    ui.click("ask-reset")  # leave the conversation where the group found it
    if not told:
        finding.append(
            _f(
                "N-refusal-without-a-reason",
                "src/ea/ui/pages/ask.py · document_card's view_toolbar(drawio_reason=…), which passes no "
                "note, and components.py · view_toolbar, which drops a reason it is not asked to show",
                "usability",
                "The Ask document disables Download draw.io and never says why: the reason is computed, "
                "used to grey the button out, and then thrown away.",
                "view_toolbar's own contract is that 'a reason disables the button it names and says why', "
                "and the Impact page keeps it — it passes the same text as `note` and the reader sees "
                "'Choose an element and press Run: there is no view to export yet.' beside the two greyed "
                "buttons. The Ask document passes only `drawio_reason`, so the string 'This answer drew no "
                "diagram, so there is nothing to export.' never reaches the DOM: no note, no title, no "
                "aria-describedby. A reader who wanted the diagram sees a dead control on a document that "
                "otherwise worked, and is left to guess whether the export is broken. Rendering the reason "
                "whenever one is given — as a note beside the buttons, or as the button's title — would "
                "make the two pages behave alike.",
            )
        )


@pytest.mark.scenario(
    scenario_id="N25",
    group="N",
    title="A view drawn on a tab the page did not open on is exported at the wrong size",
    feature="Downloads · draw.io · a diagram measured while it was hidden",
    expected="The element page draws its view on the Graph tab, which is not the tab the page opens on. "
    "Its draw.io file must still carry each shape at the size it is drawn, the way the Impact page's "
    "does; redrawing the same view with Reset layout, with the tab open, must not change the file.",
)
def test_a_view_drawn_on_a_hidden_tab(ui, record, finding):
    _open_element_view(ui)
    screen = _screen_nodes(ui, "el-view")
    ui.must("the browser drew the view", len(screen) >= 3, f"{len(screen)} shapes on screen")
    boxes = _file_boxes(_drawio(ui, ui.download("el-view-drawio", ".drawio")))
    wrong = [
        f"{eid}: {boxes[eid]['w']:.0f} by {boxes[eid]['h']:.0f} in the file against "
        f"{screen[eid]['w']:.0f} by {screen[eid]['h']:.0f} on screen"
        for eid in screen
        if eid in boxes
        and (abs(boxes[eid]["w"] - screen[eid]["w"]) > 2 or abs(boxes[eid]["h"] - screen[eid]["h"]) > 2)
    ]
    ui.check(
        "every shape is exported at the size it is drawn",
        not wrong,
        "; ".join(wrong[:3]) if wrong else f"all {len(screen)} of them",
    )
    stock = sorted({(round(b["w"]), round(b["h"])) for b in boxes.values()})
    ui.check(
        "so the file is not a set of identical boxes with the drawing's names in them",
        len(stock) > 1 or not wrong,
        f"every shape in the file is {stock[0][0]} by {stock[0][1]}"
        if len(stock) == 1
        else f"{len(stock)} sizes: {stock[:4]}",
    )
    ui.shot("The element view's Graph tab, whose draw.io file sizes every shape the same")

    # The same view, redrawn by the page's own Reset layout with the tab open in front of the
    # reader. Nothing about the view changed, so nothing about the file should either.
    ui.click(_pm(id="el-view", type="mermaid-reset"))
    ui.page.wait_for_timeout(700)
    ui.settle()
    redrawn = _screen_nodes(ui, "el-view")
    ui.must(
        "the view is still drawn after Reset layout", len(redrawn) == len(screen), f"{len(redrawn)} shapes"
    )
    after = _file_boxes(_drawio(ui, ui.download("el-view-drawio", ".drawio")))
    still_wrong = [
        eid
        for eid in redrawn
        if eid in after
        and (abs(after[eid]["w"] - redrawn[eid]["w"]) > 2 or abs(after[eid]["h"] - redrawn[eid]["h"]) > 2)
    ]
    ui.check(
        "and redrawing the same view in front of the reader gives the same file",
        bool(wrong) == bool(still_wrong),
        f"{len(wrong)} shapes were the wrong size before Reset layout and {len(still_wrong)} after",
    )
    ui.shot("The same view after Reset layout, redrawn while the tab was open")
    if wrong and not still_wrong:
        finding.append(
            _f(
                "N-size-measured-while-hidden",
                "src/ea/ui/app.py · the clientside render callback on {'type': 'mermaid-src'}, and "
                "assets/ea-views.js · positionsOf, whose w and h come from getBBox at render time",
                "defect",
                "A view first drawn on a tab that is not showing is exported to draw.io with every shape "
                "the same default size, so long names spill out of their boxes in the file.",
                "The element page renders its generated view when the page loads, while the Graph tab is "
                "still hidden, so getBBox measures nothing and the position store carries w and h of 0. "
                "to_drawio falls back to 170 by 60 for every shape, and because it places each one from "
                "its centre minus half that width, the shapes also drift relative to each other by up to "
                "a couple of dozen units against the picture on screen. Pressing Reset layout with the "
                "tab open re-measures the same view and the very next download is correct in both "
                "respects, which is where this scenario's evidence comes from; the Impact page, whose "
                "view is on screen the moment it renders, exports correctly the first time (N21). "
                "Measuring when the diagram becomes visible — or falling back to the size Mermaid gives "
                "the node rather than a constant — would make the first file as good as the second.",
            )
        )
