"""Group S — the critical path: one organisation taken from nothing to a model worth asking about.

Every other group proves a screen on the model the round seeds. This one proves the chain a
new enterprise walks, in the order each step needs the one before it: an organisation is
created, a metamodel version of its own is drafted, published and applied to it, elements are
created by hand and imported onto a branch, the branch is merged, the result is found, drawn and
analysed, a change is proposed and merged, the model is asked about, then updated and retired
in part, exported, and finally deleted with the version it applied. A step that fails stops the
steps after it, because they would be testing what it did not build.

Everything lives in the organisation `S Path` and in the version `s-path-1`, both removed by the
last scenario, so the round ends with the store it started with. The organisation starts empty,
which is what makes the isolation checks worth reading: whatever S Path shows, it made itself.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from tests.conftest import HIGHER_ED
from tests.ui.test_c_element import _choose, _pick_other
from tests.ui.test_c_element import _save as _save_element
from tests.ui.test_c_element import _tab as _element_tab
from tests.ui.test_j_metamodel import _act, _added_row, _confirm, _grid_home, _list, _set
from tests.ui.test_j_metamodel import _open as _open_metamodel
from tests.ui.test_j_metamodel import _tab as _metamodel_tab
from tests.ui.test_q_organisations import _create, _row

pytestmark = pytest.mark.gui

ORG = "S Path"
ORG_ID = "s-path"
DEFAULT_ORG = "Default organisation"
SHIPPED_NAME = "Higher Education EA Metamodel"
VERSION = "s-path-1"
VERSION_REF = f"{HIGHER_ED}@{VERSION}"

# The type the version adds: a kind of application, so it inherits what an application may do.
NEW_TYPE = "s_platform_service"
NEW_TYPE_NAME = "S Platform Service"
NEW_TYPE_PREFIX = "SPS"

BUILD = "S build"  # the branch the model is built on
BUILD_ID = "s-build"
SCRATCH = "S scratch"  # the branch that is abandoned
SCRATCH_ID = "s-scratch"
PROPOSAL_BRANCH = "s-proposal"

CAPABILITY = "S Enrolment Management"
PROCESS = "S Enrol a Student"
PORTAL = "S Enrolment Portal"
IDENTITY = "S Identity Service"
STUDENT = "DE-S-STUDENT"
ENROLMENT = "DE-S-ENROLMENT"
ANALYTICS = "S Enrolment Analytics"  # the element the proposal adds
WORK_PACKAGE = "S Rollout"

# One page per graph the application draws, and the id its panel carries.
GROUPINGS = [
    "No grouping",
    "Group by domain",
    "Group by layer",
    "Group by element type",
    "Group by status",
    "Group by source system",
    "Group by target state",
]
LAYOUTS = ["Grouped grid", "Organic", "Concentric", "Breadth-first", "Circle"]
FLAT_LAYOUTS = {"Concentric", "Circle"}  # they draw no boxes, by design

# The ids the application mints for what is created by hand, kept for the steps after.
MINTED: dict[str, str] = {}


def _pm(**parts: str) -> str:
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


# --------------------------------------------------------------------------- the controls


def _org(ui) -> str:
    return ui.page.locator("#org-select").first.input_value().strip()


def _enter(ui, name: str = ORG) -> None:
    """Stand in an organisation, whatever page the step before left the reader on."""
    if not ui.page.url.startswith("http"):
        ui.goto("/")
    if _org(ui) != name:
        ui.select("org-select", name)
        ui.page.wait_for_timeout(400)
        ui.settle()
    ui.must(f"the reader is in {name}", _org(ui) == name, f"the header reads {_org(ui)!r}")


def _need(ui, *keys: str) -> None:
    """A step that builds on an id an earlier step minted stops when that step did not run."""
    missing = [k for k in keys if not MINTED.get(k)]
    ui.must("the steps before this one built what it needs", not missing, f"missing: {missing}")


def _home_counts(ui) -> dict[str, str]:
    """Home's stat tiles, {label: figure}."""
    ui.goto("/")
    cells = ui.page.locator("#page .mantine-SimpleGrid-root").first.locator("> *")
    out: dict[str, str] = {}
    for i in range(cells.count()):
        lines = [x.strip() for x in cells.nth(i).inner_text().splitlines() if x.strip()]
        if len(lines) >= 2:
            out[lines[1].lower()] = lines[0]
    return out


def _new_branch(ui, name: str) -> str:
    ui.click("branch-new-open")
    ui.must("the New branch modal opened", ui.visible("branch-new-modal-body"))
    ui.fill("branch-new-name", name)
    ui.fill("branch-new-desc", f"{name}: made by the critical path.")
    ui.click("branch-new-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    return ui.branch_badge()


def _create_element(ui, type_label: str, name: str, description: str) -> str:
    """Create an element from Browse and return the identifier the application minted."""
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element modal opened", ui.visible("new-modal-body"))
    ui.select("new-type", type_label, exact=True)
    ui.fill("new-name", name)
    ui.page.locator(_pm(id="new-desc", type="md-text")).first.fill(description)
    ui.settle()
    ui.click("new-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.must(
        f"creating {name} opened it",
        "/element/" in ui.page.url,
        f"{ui.page.url}; feedback: {ui.text('new-feedback')}",
    )
    return ui.page.url.rstrip("/").rsplit("/", 1)[-1]


def _relate(ui, element_id: str, other_text: str, other_id: str, relationship: str) -> str:
    ui.goto(f"/element/{element_id}")
    _element_tab(ui, "Relationships")
    _pick_other(ui, other_text, other_id)
    ui.select("el-rel-type", relationship)
    ui.click("el-rel-add")
    return ui.text("el-rel-feedback")


def _write(ui, name: str, text: str) -> Path:
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


def _merge(ui, branch_id: str) -> str:
    """Merge every row of a branch from its merge log, as an Admin does."""
    ui.goto(f"/branches?branch={branch_id}")
    ui.must("the merge log is on the page", ui.visible("br-grid"), ui.text("page")[:200])
    rows = [k for k in ui.grid_row_ids("br-grid") if k]
    ui.must("the branch holds rows to merge", bool(rows), f"rows: {rows}")
    ui.click("br-merge")
    ui.page.wait_for_timeout(400)
    ui.settle()
    return ui.text("br-feedback")


def _browse_ids(ui, query: str = "") -> list[str]:
    ui.goto(f"/browse?q={query}" if query else "/browse")
    return [r for r in ui.grid_row_ids("browse-grid") if r]


def _heading(ui) -> str:
    h = ui.page.locator("#page h1").first
    return h.inner_text().strip() if h.count() else ""


# The state of one graph panel, read from its Cytoscape instance: the element nodes it draws,
# the boxes, positions that are not numbers, and how many nodes a reader can actually see.
GRAPH_STATE_JS = """(pid) => {
  const cy = window.eaGraph && window.eaGraph.instance(pid);
  if (!cy) { return null; }
  const els = cy.nodes().filter(n => n.data('element_id'));
  const w = cy.width(), h = cy.height();
  return {
    nodes: els.length,
    boxes: cy.$('.group').length,
    nan: els.filter(n => { const p = n.position(); return !isFinite(p.x) || !isFinite(p.y); }).length,
    seen: els.filter(n => { const b = n.renderedBoundingBox();
      return b.x2 > 0 && b.y2 > 0 && b.x1 < w && b.y1 < h; }).length,
    places: new Set(els.map(n => Math.round(n.position().x) + ',' + Math.round(n.position().y))).size,
  };
}"""


def _graph(ui, panel: str) -> dict | None:
    return ui.page.evaluate(GRAPH_STATE_JS, panel)


def _graph_select(ui, panel: str, kind: str, label: str) -> None:
    ui.page.locator(_pm(id=panel, type=kind)).first.click()
    ui.page.locator("[role='option']:visible").filter(
        has_text=re.compile(rf"^{re.escape(label)}$")
    ).first.click()
    ui.settle()
    ui.page.wait_for_timeout(700)


def _every_mode(ui, panel: str) -> list[str]:
    """Every layout with every grouping, in the order a reader might try them, and what went wrong.

    Layouts are the outer loop on purpose: a layout that fails part way leaves the panel half
    updated, and it is the layouts chosen after it that show the damage.
    """
    errors: list[str] = []

    def listen(message) -> None:  # noqa: ANN001 — playwright event payload
        if message.type == "error":
            errors.append(message.text.splitlines()[0][:160])

    ui.page.on("console", listen)
    ui.page.on("pageerror", lambda exc: errors.append(f"pageerror: {str(exc)[:160]}"))
    wrong: list[str] = []
    try:
        base = _graph(ui, panel)
        if not base:
            return [f"the {panel!r} panel drew no graph to switch"]
        for layout in LAYOUTS:
            _graph_select(ui, panel, "gp-layout", layout)
            for grouping in GROUPINGS:
                before = len(errors)
                _graph_select(ui, panel, "gp-group", grouping)
                s = _graph(ui, panel) or {}
                said: list[str] = []
                if s.get("nodes") != base["nodes"]:
                    said.append(f"{s.get('nodes')} of {base['nodes']} nodes")
                if s.get("nan"):
                    said.append(f"{s['nan']} nodes with no position")
                if s.get("seen", 0) < s.get("nodes", 0):
                    said.append(f"only {s.get('seen')} of {s.get('nodes')} nodes in view")
                if s.get("nodes", 0) > 2 and s.get("places", 0) < 2:
                    said.append("every node drawn in one place")
                boxed = grouping != "No grouping" and layout not in FLAT_LAYOUTS
                if boxed and not s.get("boxes"):
                    said.append("no group boxes")
                if not boxed and s.get("boxes"):
                    said.append(f"{s['boxes']} boxes where none belong")
                if len(errors) > before:
                    said.append("the browser reported: " + "; ".join(errors[before:])[:200])
                if said:
                    wrong.append(f"{layout} / {grouping}: " + ", ".join(said))
    finally:
        ui.page.remove_listener("console", listen)
    _graph_select(ui, panel, "gp-layout", "Grouped grid")
    return wrong


# =========================================================================== 1 · the organisation


@pytest.mark.scenario(
    scenario_id="S01",
    group="S",
    title="A new organisation starts empty, on the shipped metamodel, and is entered from the header",
    feature="Critical path · organisation",
    expected=(
        "Creating S Path with nothing copied into it lists it with no content on the shipped "
        "version; switching to it in the header shows a Home with no elements and a Browse with "
        "no rows, while the default organisation keeps its own content."
    ),
)
def test_new_organisation(ui, record):
    MINTED.clear()
    _enter(ui, DEFAULT_ORG)
    default_elements = _home_counts(ui).get("elements", "")
    ui.must("the default organisation holds a model", default_elements.isdigit(), default_elements)
    MINTED["default_elements"] = default_elements
    ui.goto("/organisations")
    said = _create(ui, ORG, None, f"{SHIPPED_NAME} 2026-08-11", "The critical path's own enterprise.")
    ui.must("the organisation was created", ORG in said and "created" in said.lower(), said)
    row = _row(ui, ORG)
    ui.check("it is listed", bool(row), row)
    ui.check("on the shipped version", "2026-08-11" in row, row)
    _enter(ui, ORG)
    counts = _home_counts(ui)
    ui.check("Home is headed by the organisation", _heading(ui) == ORG, _heading(ui))
    ui.check("and counts no elements", counts.get("elements") == "0", str(counts))
    ui.check("Browse lists nothing", _browse_ids(ui) == [], str(_browse_ids(ui)[:5]))
    ui.shot("S Path, a new organisation, empty")
    _enter(ui, DEFAULT_ORG)
    ui.check(
        "the default organisation still holds what it held",
        _home_counts(ui).get("elements") == default_elements,
        f"{default_elements} before, {_home_counts(ui).get('elements')} now",
    )


# =========================================================================== 2 · its metamodel


@pytest.mark.scenario(
    scenario_id="S02",
    group="S",
    title="A metamodel version of its own is drafted, published and applied to the new organisation alone",
    feature="Critical path · metamodel",
    expected=(
        "Adding a type that inherits from Physical Application Component and saving it on the "
        "shipped version drafts s-path-1 and applies it to S Path; publishing it freezes it; S Path "
        "then applies s-path-1 while the default organisation stays on the shipped version, and the "
        "New element modal in S Path offers the new type."
    ),
)
def test_new_metamodel_version(ui, record):
    _enter(ui)
    _open_metamodel(ui)
    _list(ui, "Element types")
    ui.click("mm-add-type")
    row = _added_row(ui, "mm-types-grid", "new_type_")
    ui.must("Add type added a row", bool(row), str(ui.grid_row_ids("mm-types-grid")[-3:]))
    for col, value in (
        ("id", NEW_TYPE),
        ("name", NEW_TYPE_NAME),
        ("plural", f"{NEW_TYPE_NAME}s"),
        ("supertype", "physical_application_component"),
        ("domain", "integration"),
        ("prefix", NEW_TYPE_PREFIX),
    ):
        _set(ui, "mm-types-grid", row, col, value)
    _grid_home(ui, "mm-types-grid")
    ui.click("mm-save")
    ui.must("saving on a published version asks for a draft", ui.visible("mm-draft-modal-body"))
    ui.fill("mm-draft-version", VERSION)
    ui.fill("mm-draft-notes", "S: the critical path's own version.")
    box = ui.page.locator("#mm-draft-apply").first
    if not box.is_checked():
        box.click(force=True)
    ui.click("mm-draft-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    said = ui.text("mm-feedback")
    ui.must("the draft was created", f"{VERSION} created from" in said, said)
    ui.check("and applied to S Path", f"Applied to {ORG}" in said, said)
    ui.shot("The version S Path drafted, with the type it adds")

    _metamodel_tab(ui, "Versions")
    said = _act(ui, "publish", VERSION_REF)
    ui.must("the version was published", f"{VERSION} is published" in said, said)

    ui.goto("/organisations")
    ui.check("S Path applies the new version", VERSION in _row(ui, ORG), _row(ui, ORG))
    ui.check(
        "the default organisation stays on the shipped version",
        "2026-08-11" in _row(ui, DEFAULT_ORG) and VERSION not in _row(ui, DEFAULT_ORG),
        _row(ui, DEFAULT_ORG),
    )
    ui.check("the header names it", VERSION in ui.text("pack-badge").lower(), ui.text("pack-badge"))
    ui.goto("/browse")
    ui.click("new-open")
    ui.click("new-type")
    offered = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("the New element modal offers the new type", NEW_TYPE_NAME in offered, f"{len(offered)} offered")
    ui.shot("S Path's Organisations row on its own version")


# =========================================================================== 3 · elements by hand


@pytest.mark.scenario(
    scenario_id="S03",
    group="S",
    title="Elements are created, edited and related by hand on a branch, one of them of the new type",
    feature="Critical path · elements · by hand",
    expected=(
        "On the branch s-build, a Capability, a Process, an application and an S Platform Service are "
        "created with the pack's prefixes; the application's states are edited; and three 'realises' "
        "relationships are drawn to the Capability, one of them inherited by the new type."
    ),
    role="admin",
    branch=BUILD_ID,
)
def test_elements_by_hand(ui, record):
    _enter(ui)
    ui.goto("/browse")
    badge = _new_branch(ui, BUILD)
    ui.must("the reader is on the new branch", badge.strip().lower() != "main", badge)
    for key, type_label, name, prefix in (
        ("capability", "Capability", CAPABILITY, "CAP-"),
        ("process", "Process", PROCESS, ""),
        ("portal", "Physical Application Component", PORTAL, "PAC-"),
        ("identity", NEW_TYPE_NAME, IDENTITY, f"{NEW_TYPE_PREFIX}-"),
    ):
        MINTED[key] = _create_element(ui, type_label, name, f"{name}: created by the critical path.")
        ui.check(
            f"{name} was minted an identifier with its type's prefix",
            MINTED[key].startswith(prefix),
            MINTED[key],
        )
    ui.shot("The S Platform Service, created in S Path from its own type")

    ui.goto(f"/element/{MINTED['portal']}")
    _element_tab(ui, "Edit")
    _choose(ui, "el-current-state", "Planned")
    _choose(ui, "el-target-state", "New")
    said = _save_element(ui)
    ui.check("the application's states were saved", "Saved version" in said, said)

    for key in ("process", "portal", "identity"):
        said = _relate(ui, MINTED[key], CAPABILITY, MINTED["capability"], "realises")
        ui.check(f"{key} realises the capability", "added" in said.lower(), said)
    ui.shot("The new type's element relates to the capability through a relationship it inherited")


# =========================================================================== 4 · elements imported


@pytest.mark.scenario(
    scenario_id="S04",
    group="S",
    title="Elements imported onto the same branch connect to the ones created by hand",
    feature="Critical path · elements · import",
    expected=(
        "Two data entities and three 'processes' edges that name the identifiers minted by hand "
        "validate clean and load onto s-build: 2 of 2 elements and 3 of 3 relationships."
    ),
    branch=BUILD_ID,
)
def test_elements_imported(ui, record):
    _need(ui, "portal", "identity")
    _enter(ui)
    ui.select("branch-select", BUILD)
    ui.settle()
    ui.goto("/import")
    ui.must("the load will land on the branch", f"You are on branch {BUILD_ID}:" in ui.text("page"))
    elements = (
        "id,type,name,description\n"
        f"{STUDENT},data_entity,S Student Record,The record of a student the critical path enrols.\n"
        f"{ENROLMENT},data_entity,S Enrolment,One enrolment of one student in one offering.\n"
    )
    relationships = (
        "src_id,rel_type,dst_id\n"
        f"{MINTED['portal']},processes,{STUDENT}\n"
        f"{MINTED['portal']},processes,{ENROLMENT}\n"
        f"{MINTED['identity']},processes,{STUDENT}\n"
    )
    _upload(
        ui,
        _write(ui, "s-elements.csv", elements),
        _write(ui, "s-relationships.csv", relationships),
    )
    ui.fill("im-source", "s-path")
    ui.click("im-validate")
    checked = ui.text("im-report")
    ui.check("the files validate clean", "0 errors" in checked, checked[:300])
    ui.click("im-load")
    loaded = ui.text("im-report")
    ui.check("both elements were loaded", "elements 2/2 loaded" in loaded, loaded[:300])
    ui.check("all three relationships were loaded", "relationships 3/3 loaded" in loaded, loaded[:300])
    ui.shot("The imported rows, loaded onto s-build beside the ones made by hand")


# =========================================================================== 5 · the merge


@pytest.mark.scenario(
    scenario_id="S05",
    group="S",
    title="The branch is merged, and S Path's main then holds the whole model",
    feature="Critical path · branches · merge",
    expected=(
        "Main does not carry the branch's elements before the merge; merging every row writes them, "
        "closes the branch, and Home and Browse on main count the six elements."
    ),
)
def test_merge_the_build(ui, record):
    _need(ui, "capability", "portal")
    _enter(ui)
    ui.check("main does not hold the branch's work yet", _browse_ids(ui) == [], str(_browse_ids(ui)[:6]))
    said = _merge(ui, BUILD_ID)
    ui.must("the branch was merged", "Merged" in said and "to main" in said, said)
    ui.check("and closed", "merged and closed" in said, said)
    ui.shot("s-build merged into S Path's main")
    ids = _browse_ids(ui)
    ui.check(
        "Browse on main lists the six elements",
        {MINTED["capability"], MINTED["portal"], MINTED["identity"], STUDENT, ENROLMENT} <= set(ids)
        and len(ids) == 6,
        str(ids),
    )
    ui.check("Home counts them", _home_counts(ui).get("elements") == "6", str(_home_counts(ui)))


# =========================================================================== 6 · discovery


@pytest.mark.scenario(
    scenario_id="S06",
    group="S",
    title="What was built is found, opened, traced and analysed",
    feature="Critical path · discovery",
    expected=(
        "Browse filters to the new type and finds by name; the application's page shows its "
        "relationships and draws its neighbourhood; Impact of the student record names both "
        "applications that process it; Health reads the organisation without failing."
    ),
)
def test_discovery(ui, record):
    _need(ui, "portal", "identity")
    _enter(ui)
    ui.goto(f"/browse?type={NEW_TYPE}")
    typed = [r for r in ui.grid_row_ids("browse-grid") if r]
    ui.check(
        "the type filter narrows to the one S Platform Service", typed == [MINTED["identity"]], str(typed)
    )
    found = _browse_ids(ui, "Enrolment")
    ui.check(
        "a word finds the elements named with it",
        {MINTED["capability"], MINTED["portal"], ENROLMENT} <= set(found),
        str(found),
    )
    ui.goto(f"/element/{MINTED['portal']}")
    ui.check("the application's page opens", PORTAL in ui.body(), ui.text("page")[:200])
    _element_tab(ui, "Relationships")
    tables = ui.text("el-rel-tables")
    ui.check(
        "it lists what it realises and what it processes",
        CAPABILITY in tables and "S Student Record" in tables and "S Enrolment" in tables,
        tables[:300],
    )
    _element_tab(ui, "Graph")
    ui.wait_graph()
    drawn = _graph(ui, "el") or {}
    ui.check("the graph draws its neighbourhood", drawn.get("nodes", 0) >= 4, str(drawn))
    ui.shot("The application's neighbourhood in S Path")

    ui.goto(f"/impact?element={STUDENT}")
    ui.wait_graph()
    result = ui.text("imp-result")
    ui.check(
        "Impact of the student record names both applications",
        PORTAL in result and IDENTITY in result,
        result[:400],
    )
    ui.shot("Impact of the student record: both applications that process it")

    ui.goto("/health")
    ui.check("Health reads S Path", "This page failed to render" not in ui.body(), ui.text("page")[:200])


@pytest.mark.scenario(
    scenario_id="S07",
    group="S",
    title="Every layout with every grouping draws the whole graph, on all three pages that draw one",
    feature="Critical path · graph modes",
    expected=(
        "On the element's Graph tab, on Impact and on the Metamodel's type graph, each of the five "
        "layouts with each of the seven groupings keeps every node, in view and apart, boxes them "
        "when a grouping asks for it (Concentric and Circle excepted), and raises no browser error; "
        "the type graph opens with every type in view."
    ),
)
def test_every_graph_mode(ui, record):
    _need(ui, "portal")
    _enter(ui)
    ui.goto(f"/element/{MINTED['portal']}")
    _element_tab(ui, "Graph")
    ui.wait_graph()
    wrong = _every_mode(ui, "el")
    ui.check("every mode draws the element's graph", not wrong, "; ".join(wrong[:6]))
    ui.shot("The element's graph, back on the grouped grid after every mode")

    ui.goto(f"/impact?element={STUDENT}")
    ui.wait_graph()
    wrong = _every_mode(ui, "imp")
    ui.check("every mode draws the impact graph", not wrong, "; ".join(wrong[:6]))

    ui.goto("/metamodel")
    _metamodel_tab(ui, "Graph")
    ui.wait_graph()
    ui.page.wait_for_timeout(400)
    opened = _graph(ui, "mm") or {}
    ui.check(
        "the type graph opens with every type in view",
        opened.get("nodes") and opened.get("seen") == opened.get("nodes"),
        str(opened),
    )
    wrong = _every_mode(ui, "mm")
    ui.check("every mode draws the type graph", not wrong, "; ".join(wrong[:6]))
    ui.shot("The type graph of S Path's version after every mode")


# =========================================================================== 7 · a proposal


PROPOSAL = f"""# Proposal: S enrolment analytics

| Field | Value |
| ----- | ----- |
| **Work package** | {WORK_PACKAGE} |

## Summary

Enrolment managers need to see enrolments as they happen, so an analytics application is added
that reads the enrolment records the portal writes, in support of enrolment management.

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
| Capability | {CAPABILITY} | {{capability}} | | | |
| Process | {PROCESS} | {{process}} | | | |
| Physical Application Component | {ANALYTICS} | | An analytics application that reports enrolments to enrolment managers as they happen. | proposed | new |
| Data Entity | S Enrolment | {ENROLMENT} | | live | keep |

## Relationships

| Source | Relationship | Target | Note |
| ------ | ------------ | ------ | ---- |
| {ANALYTICS} | realises | {CAPABILITY} | |
| {ANALYTICS} | processes | S Enrolment | |
"""


@pytest.mark.scenario(
    scenario_id="S08",
    group="S",
    title="A change proposed against the model is applied to a branch of its own and merged",
    feature="Critical path · propose",
    expected=(
        "A proposal that adds an analytics application, naming the capability, the process and the "
        "enrolment record by the identifiers S Path gave them, is read with nothing to push back on, "
        "applied to the new branch s-proposal with its new work package, and merged; main then holds "
        "the application and its two relationships."
    ),
)
def test_propose_and_merge(ui, record):
    _need(ui, "capability", "process")
    _enter(ui)
    ui.goto("/propose")
    ui.select("pr-branch", "New branch")
    ui.fill("pr-branch-new", PROPOSAL_BRANCH)
    box = ui.page.locator(_pm(id="pr-text", type="md-text")).first
    box.click()
    box.fill(PROPOSAL.replace("{capability}", MINTED["capability"]).replace("{process}", MINTED["process"]))
    ui.settle()
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=30_000)
    ui.settle()
    pushback = ui.text("pr-pushback")
    ui.must("nothing stops the proposal", "Not enough to apply" not in pushback, pushback[:600])
    ui.click("pr-apply")
    said = ui.text("pr-apply-feedback")
    ui.must("it was applied to the new branch", f"Applied to branch {PROPOSAL_BRANCH}" in said, said)
    # The work package it names is new too, so it is created beside the application.
    ui.check("it created the application and its work package", "2 element(s) created" in said, said)
    ui.check("and linked the three it named by identifier", "3 linked" in said, said)
    ui.check("and wrote both relationships", "2 relationship(s) written" in said, said)
    ui.shot("The proposal applied to s-proposal")
    said = _merge(ui, PROPOSAL_BRANCH)
    ui.must("the proposal's branch was merged", "Merged" in said and "to main" in said, said)
    found = [i for i in _browse_ids(ui, "Analytics") if i.startswith("PAC-")]
    ui.check("main holds the proposed application", len(found) == 1, str(found))
    if found:
        MINTED["analytics"] = found[0]
        ui.goto(f"/element/{found[0]}")
        _element_tab(ui, "Relationships")
        tables = ui.text("el-rel-tables")
        ui.check(
            "with both its relationships",
            CAPABILITY in tables and "S Enrolment" in tables,
            tables[:300],
        )


# =========================================================================== 8 · asking


@pytest.mark.scenario(
    scenario_id="S09",
    group="S",
    title="The model is asked about, and answers from S Path's content alone",
    feature="Critical path · ask",
    expected=(
        "Asking for the impact of changing the enrolment record answers with the applications that "
        "process it, cites only S Path's identifiers and draws the view; the same question in the "
        "default organisation finds no such element."
    ),
)
def test_ask(ui, record):
    _need(ui, "portal")
    _enter(ui)
    ui.goto("/ask")
    question = f"What is the impact of changing {ENROLMENT}?"
    ui.page.locator("#ask-input").first.fill(question)
    ui.settle()
    ui.click("ask-button")
    ui.page.wait_for_selector("#ask-answer .ea-document", timeout=30_000)
    ui.settle()
    answer = ui.text("ask-answer")
    ui.check("the answer is about the enrolment record", "S Enrolment" in answer, answer[:300])
    ui.check("it names the portal that processes it", PORTAL in answer, answer[:500])
    cited = set(re.findall(r"\b[A-Z]{2,4}-[A-Z0-9][A-Z0-9-]+\b", answer))
    ours = {STUDENT, ENROLMENT, *(v for k, v in MINTED.items() if k != "default_elements")}
    ui.check("every identifier it cites is S Path's own", cited <= ours, str(sorted(cited - ours)))
    ui.shot("Ask in S Path: the answer, from S Path's content")
    _enter(ui, DEFAULT_ORG)
    ui.goto("/ask")
    ui.page.locator("#ask-input").first.fill(question)
    ui.settle()
    ui.click("ask-button")
    ui.page.wait_for_selector("#ask-answer .ea-document", timeout=30_000)
    ui.settle()
    answer = ui.text("ask-answer")
    ui.check(
        "the default organisation has no such element",
        "could not find" in answer.lower() or "not found" in answer.lower(),
        answer[:300],
    )


# =========================================================================== 9 · updating and deleting


@pytest.mark.scenario(
    scenario_id="S10",
    group="S",
    title="The model is updated in bulk, an element retired, a relationship and a branch thrown away",
    feature="Critical path · update and delete",
    expected=(
        "Bulk edit sets a target state on every element; the S Platform Service is retired and "
        "Browse's status filter finds it; one 'processes' edge is deleted and Impact no longer "
        "names it; an element made on s-scratch is gone with the branch when it is abandoned."
    ),
)
def test_update_and_delete(ui, record):
    _need(ui, "portal", "identity")
    _enter(ui)
    ui.goto("/browse")
    shown = ui.grid_row_count("browse-grid")
    ui.page.locator("#browse-grid .ag-header-cell[col-id='sel'] input").first.click(force=True)
    ui.settle()
    ui.click("bulk-open")
    ui.must("the bulk modal opened", ui.visible("bulk-modal-body"))
    ui.select("bulk-target", "keep")  # the bulk modal offers the states as the model writes them
    ui.click("bulk-save")
    said = ui.text("bulk-feedback")
    ui.check(f"bulk edit updated all {shown} elements", f"Updated {shown}" in said, said)
    ui.page.keyboard.press("Escape")
    ui.settle()

    ui.goto(f"/element/{MINTED['identity']}")
    _element_tab(ui, "Edit")
    _choose(ui, "el-status", "retired")
    said = _save_element(ui)
    ui.check("the S Platform Service was retired", "Saved version" in said, said)
    ui.goto("/browse?status=retired")
    retired = [r for r in ui.grid_row_ids("browse-grid") if r]
    ui.check("Browse's status filter finds it retired", retired == [MINTED["identity"]], str(retired))

    ui.goto(f"/element/{MINTED['portal']}")
    _element_tab(ui, "Relationships")
    row = ui.page.locator("#el-rel-tables tr:has-text('S Enrolment')").filter(has_not_text="Student").first
    ui.must("the portal's edge to the enrolment is listed", row.count() > 0, ui.text("el-rel-tables")[:300])
    row.locator("button").last.click()
    ui.settle()
    ui.page.wait_for_timeout(300)
    ui.check(
        "the edge was removed", "removed" in ui.text("el-rel-feedback").lower(), ui.text("el-rel-feedback")
    )
    ui.goto(f"/impact?element={ENROLMENT}")
    ui.check("Impact of the enrolment no longer names the portal", PORTAL not in ui.text("imp-result"))

    ui.goto("/browse")
    _new_branch(ui, SCRATCH)
    scratch = _create_element(ui, "Capability", "S Thrown Away", "Made on a branch that is abandoned.")
    ui.goto(f"/branches?branch={SCRATCH_ID}")
    ui.click("br-abandon")
    said = ui.text("br-feedback")
    ui.check("the branch was abandoned", "its rows are discarded" in said, said)
    _enter(ui)
    ui.goto(f"/element/{scratch}")
    ui.check("its element never reached main", _heading(ui) == "Not found", _heading(ui))
    ui.shot("After the updates and the deletions: S Path's main")


# =========================================================================== 10 · export, isolation, removal


@pytest.mark.scenario(
    scenario_id="S11",
    group="S",
    title="S Path exports as its own content, never reached the default, and is deleted with its version",
    feature="Critical path · export and removal",
    expected=(
        "Download current content hands out S Path's elements and nothing of the default "
        "organisation's; the default holds what it held and none of S Path's; deleting S Path takes "
        "its content with it, and s-path-1, retired, is deleted too."
    ),
)
def test_export_isolation_and_removal(ui, record):
    _need(ui, "portal", "default_elements")
    _enter(ui)
    ui.goto("/import")
    path = ui.download("im-export", ".zip")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        member = next((n for n in names if n.endswith("elements.csv")), "")
        rows = list(csv.DictReader(io.StringIO(archive.read(member).decode("utf-8-sig")))) if member else []
    exported = {r.get("id", "") for r in rows}
    ui.check(
        "the export holds S Path's elements", {MINTED["portal"], STUDENT} <= exported, str(sorted(exported))
    )
    ui.check("and nothing of the default's", "PAC-CMS" not in exported, str(sorted(exported)))

    _enter(ui, DEFAULT_ORG)
    ui.check(
        "the default organisation holds what it held",
        _home_counts(ui).get("elements") == MINTED["default_elements"],
        f"{MINTED['default_elements']} before, {_home_counts(ui).get('elements')} now",
    )
    ui.goto(f"/element/{STUDENT}")
    ui.check("and none of S Path's elements", _heading(ui) == "Not found", _heading(ui))
    ui.check(
        "the header names the shipped version",
        ui.text("pack-badge").strip() == "2026-08-11",
        ui.text("pack-badge"),
    )

    ui.goto("/organisations")
    ui.click(_pm(action="delete", org=ORG_ID, type="orgs-action"))
    ui.must("deleting asks first", ui.visible("orgs-confirm-modal-body"))
    ui.click("orgs-confirm-yes")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("S Path is gone", not _row(ui, ORG), _row(ui, ORG))

    _open_metamodel(ui)
    _metamodel_tab(ui, "Versions")
    ui.click(_pm(action="retire", ref=VERSION_REF, type="mm-ver-action"))
    said = _confirm(ui)
    ui.check("s-path-1 was retired", f"{VERSION} is retired" in said, said)
    ui.click(_pm(action="delete", ref=VERSION_REF, type="mm-ver-action"))
    said = _confirm(ui)
    ui.check("and deleted", f"{VERSION} deleted" in said, said)
    ui.shot("The store as the critical path found it")
