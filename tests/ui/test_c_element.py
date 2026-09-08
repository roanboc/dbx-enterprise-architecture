"""Group C — Element: the header, the five tabs, editing, relationships, the graph, the view and history.

The scenarios work the sample model's Curriculum topic (`LDC-CURR`) and one of the data
entities it encapsulates (`DE-SRS-COURSE`). Everything this group writes it also puts
back: a description it edits is restored to the text it found, a relationship it adds is
deleted again, so a later group reads the model it expects. Nothing is asserted as an
exact total, because the round shares one database.
"""

from __future__ import annotations

import json
import re

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

EL = "LDC-CURR"  # Curriculum, a Logical Data Component
DE = "DE-SRS-COURSE"  # SRS_Course, a Data Entity it encapsulates
POS = "POS-DATA-GOV"  # a Position, whose one relationship type declares qualifiers


def _pm(**parts: str) -> str:
    """The CSS selector for a pattern-matching component, whose DOM id is the JSON Dash writes."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


DESC_TEXT = _pm(id="el-desc", type="md-text")
VIEW = _pm(id="el-view", type="mermaid-svg")
VIEW_ZOOM_IN = _pm(id="el-view", type="mermaid-zoom-in")
VIEW_ZOOM_OUT = _pm(id="el-view", type="mermaid-zoom-out")
VIEW_FIT = _pm(id="el-view", type="mermaid-fit")
VIEW_RESET = _pm(id="el-view", type="mermaid-reset")
GP_CY = _pm(id="el", type="gp-cy")
GP_GROUP = _pm(id="el", type="gp-group")
GP_LAYOUT = _pm(id="el", type="gp-layout")
GP_FIT = _pm(id="el", type="gp-fit")
GP_ZOOM_IN = _pm(id="el", type="gp-zoom-in")
GP_ZOOM_OUT = _pm(id="el", type="gp-zoom-out")

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


def _attr(name: str) -> str:
    return _pm(name=name, type="el-attr")


def _css(selector: str) -> str:
    """The harness writes a bare component id as an id; Playwright needs the `#`."""
    return f"#{selector}" if re.fullmatch(r"[a-z0-9][a-z0-9-]*", selector) else selector


def _open(ui, element_id: str) -> None:
    ui.goto(f"/element/{element_id}")


def _tab(ui, label: str) -> None:
    ui.click(f"#el-tabs [role='tab']:has-text({json.dumps(label)})")
    ui.page.wait_for_timeout(200)


def _panel(ui, value: str):
    """One tab's panel; Mantine keeps them all mounted, so visibility is what says which is open."""
    return ui.page.locator(f"#el-tabs-panel-{value}")


def _version(ui) -> int:
    """The `v3` the header prints beside the identifier."""
    loc = ui.page.get_by_text(re.compile(r"^v\d+$")).first
    return int(loc.inner_text().strip()[1:]) if loc.count() else -1


def _options(ui, selector: str) -> list[str]:
    """What a Select offers: open it, read the dropdown that is showing, close it again.

    Every Select on the page keeps its options in the DOM, so only the visible ones belong
    to the control that was just opened.
    """
    ui.page.locator(_css(selector)).first.click()
    ui.page.wait_for_timeout(350)
    out = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(250)
    return out


def _rel_names(options: list[str]) -> list[str]:
    """'encapsulates  (→ Data Entity)' → 'encapsulates'."""
    return [re.split(r"\s+\(", o)[0].strip() for o in options]


def _pick_other(ui, text: str, element_id: str) -> list[str]:
    """Search the other-element select for `text` and choose the option carrying `element_id`."""
    box = ui.page.locator("#el-rel-other").first
    box.click()
    box.fill(text)
    ui.page.wait_for_timeout(700)
    ui.settle()
    offered = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.locator("[role='option']:visible").filter(
        has_text=re.compile(re.escape(element_id))
    ).first.click()
    ui.settle()
    return offered


def _rel_tab_count(ui) -> int:
    """The number the Relationships tab prints in its own label."""
    label = ui.page.locator("#el-tabs [role='tab']:has-text('Relationships')").first.inner_text()
    match = re.search(r"\((\d+)\)", label)
    return int(match.group(1)) if match else -1


def _rel_rows(ui) -> int:
    """How many relationships the two tables under the form hold."""
    return ui.page.locator("#el-rel-tables tbody tr").count()


def _desc(ui) -> str:
    return ui.page.locator(DESC_TEXT).first.input_value()


def _set_desc(ui, text: str) -> None:
    ui.page.locator(DESC_TEXT).first.fill(text)
    ui.settle()


def _save(ui) -> str:
    ui.click("el-save")
    ui.page.wait_for_timeout(300)
    ui.settle()
    return ui.text("el-save-feedback")


def _cy(ui, expression: str):
    """Ask the panel's Cytoscape instance something, e.g. `cy.zoom()`."""
    return ui.page.evaluate(
        "() => { const cy = window.eaGraph && window.eaGraph.instance('el');"
        f" if (!cy) {{ return null; }} return {expression}; }}"
    )


def _view_scale(ui) -> float:
    """The zoom the generated view is drawn at, from the transform its canvas carries."""
    transform = ui.page.evaluate(
        "sel => { const c = document.querySelector(sel + ' .ea-mermaid-canvas');"
        " return c ? c.style.transform : ''; }",
        VIEW,
    )
    match = re.search(r"scale\(([\d.]+)\)", transform or "")
    return float(match.group(1)) if match else -1.0


def _open_graph_tab(ui) -> None:
    _tab(ui, "Graph")
    ui.wait_graph()


def _await_svg(ui, container: str) -> None:
    ui.page.wait_for_function(
        "sel => { const el = document.querySelector(sel); return !!(el && el.querySelector('svg')); }",
        arg=container,
        timeout=25_000,
    )


# --------------------------------------------------------------------------- the header


@pytest.mark.scenario(
    scenario_id="C01",
    group="C",
    title="The element header names the element, badges its type and states, and offers Impact",
    feature="Element · header",
    expected="The page opens with the name, the type, the status and the current state as badges, the identifier and the version, and an Impact button that opens the impact of this element.",
)
def test_header(ui, record):
    _open(ui, EL)
    ui.must("the element page rendered", ui.visible("el-tabs"))
    body = ui.body().lower()
    ui.check("the name is the page title", "curriculum" in body)
    ui.check("the type is badged", "logical data component" in body)
    ui.check("the status is badged", "approved" in body)
    ui.check("the current state is badged", "live" in body)
    ui.check(
        "the identifier is shown as code",
        ui.page.locator(f"#page code:has-text('{EL}')").count() > 0,
        EL,
    )
    ui.check("the version is shown", _version(ui) >= 1, f"v{_version(ui)}")
    impact = ui.page.locator("a[href*='/impact?element=']").first
    ui.must("an Impact button is offered", impact.count() > 0)
    ui.check(
        "Impact points at this element",
        (impact.get_attribute("href") or "").endswith(f"/impact?element={EL}"),
        impact.get_attribute("href") or "",
    )
    ui.shot("The element header: name, type, status, current state, identifier, version and Impact")
    impact.click()
    ui.settle()
    ui.check(
        "the Impact button opens the Impact page for this element", "/impact" in ui.page.url, ui.page.url
    )


@pytest.mark.scenario(
    scenario_id="C02",
    group="C",
    title="Overview shows the description, the attributes it holds and its links",
    feature="Element · Overview",
    expected="The Markdown description renders, the attributes that are set are listed with their labels, the link the model carries is a real anchor, and the type is described.",
)
def test_overview(ui, record):
    _open(ui, EL)
    overview = _panel(ui, "overview")
    ui.must("the Overview tab is the one that opens", overview.is_visible())
    text = overview.inner_text()
    ui.check("the description is rendered as Markdown", "learning opportunities" in text, text[:200])
    ui.check(
        "the description's bold run is rendered, not printed",
        ui.page.locator(".ea-markdown strong:has-text('Curriculum')").count() > 0,
        "no <strong> in the rendered description",
    )
    ui.check("the attributes card lists the level", "Level of Logical Data Component" in text)
    ui.check(
        "the attribute's value is shown beside its label",
        re.search(r"Level of Logical Data Component\s*2", text) is not None,
        text[:400],
    )
    ui.check("the source attribute is listed", "Reference data model v3" in text)
    link = overview.locator("a[href^='https://example.edu']").first
    ui.must("the link the model carries is an anchor", link.count() > 0)
    ui.check(
        "the link opens in a new tab",
        (link.get_attribute("target") or "") == "_blank",
        link.get_attribute("target") or "",
    )
    ui.check("the type is described under its own heading", "Type" in text and "encapsulates" in text)
    ui.shot("Overview: the rendered description, the attributes that are set, and the links")


@pytest.mark.scenario(
    scenario_id="C03",
    group="C",
    title="The State card puts what is true today beside what is intended",
    feature="Element · Overview · state",
    expected="The card names the current state, the target state, the work package and the note, and says where each is edited.",
)
def test_state_card(ui, record):
    _open(ui, EL)
    papers = _panel(ui, "overview").locator(".mantine-Paper-root")
    texts = [papers.nth(i).inner_text() for i in range(papers.count())]
    card = next((t for t in texts if t.startswith("State")), "")
    ui.must("Overview has a card of its own for the state", bool(card), str([t[:30] for t in texts]))
    for row in ("Current state", "Target state", "Work package", "Note"):
        ui.check(f"the card has a '{row}' row", row in card, card[:200])
    ui.check("the current state is badged in the card", "LIVE" in card.upper(), card[:200])
    ui.check(
        "the card says where the two states are edited",
        "Edit tab" in card and "Target state page" in card,
        card[-260:],
    )
    ui.shot("The State card: current against target, with the work package and the note")


@pytest.mark.scenario(
    scenario_id="C04",
    group="C",
    title="All five tabs open and each shows its own work",
    feature="Element · tabs",
    expected="Overview, Edit, Relationships, Graph and History each open, and the Relationships tab counts the relationships in its label.",
)
def test_five_tabs(ui, record):
    _open(ui, EL)
    labels = [t.strip() for t in ui.page.locator("#el-tabs [role='tab']").all_inner_texts()]
    ui.must("there are five tabs", len(labels) == 5, str(labels))
    ui.check(
        "the Relationships tab counts what it holds",
        any(re.fullmatch(r"Relationships \(\d+\)", label) for label in labels),
        str(labels),
    )
    # An element nothing has changed yet has an empty History, which says so rather than
    # printing an empty table, so either answer counts as the tab doing its work.
    expected = {
        "Overview": ("overview", ("Description",)),
        "Edit": ("edit", ("Save",)),
        "Relationships": ("rels", ("Add a relationship",)),
        "Graph": ("graph", ("Depth",)),
        "History": ("history", ("when", "No changes recorded")),
    }
    for label, (value, markers) in expected.items():
        _tab(ui, label)
        panel = _panel(ui, value)
        ui.check(f"the {label} tab opens", panel.is_visible(), f"panel {value}")
        ui.check(
            f"the {label} tab shows its own work",
            any(marker in panel.inner_text() for marker in markers),
            panel.inner_text()[:80],
        )
        ui.check(
            f"the {label} tab is the only one open",
            sum(1 for v, _ in expected.values() if _panel(ui, v).is_visible()) == 1,
            f"open while {label} is selected",
        )
        if label == "History":
            ui.shot("The History tab, the last of the five, open on its own panel")
    _tab(ui, "Overview")


# --------------------------------------------------------------------------- editing


@pytest.mark.scenario(
    scenario_id="C05",
    group="C",
    title="The Edit tab renders one input per attribute kind",
    feature="Element · Edit · typed attributes",
    expected="An integer attribute is a number input, an enumerated one a select of the values the pack declares, and a boolean one a yes/no select.",
)
def test_typed_attribute_inputs(ui, record, finding):
    _open(ui, EL)
    _tab(ui, "Edit")
    level = ui.page.locator(_attr("level")).first
    ui.must("the integer attribute has an input", level.count() > 0, "level")
    ui.check(
        "the integer attribute holds the value the model has", level.input_value() == "2", level.input_value()
    )
    ui.check(
        "the integer attribute is a number input",
        (level.get_attribute("inputmode") or "") in ("numeric", "decimal"),
        f"inputmode={level.get_attribute('inputmode')}",
    )
    ui.check(
        "the number input carries its steppers",
        ui.page.locator("#el-tabs-panel-edit .mantine-NumberInput-control").count() >= 2,
    )
    ui.click("#el-tabs-panel-edit .mantine-Accordion-control")
    ui.page.wait_for_timeout(400)
    approval = ui.page.locator(_attr("approval_status")).first
    ui.must("the common attributes open on their accordion", approval.is_visible(), "approval_status")
    options = _options(ui, _attr("approval_status"))
    ui.check(
        "the enumerated attribute offers exactly the values the pack declares",
        options == ["Approved", "Not Approved"],
        str(options),
    )
    ui.shot("The Edit tab: the integer attribute as a number input, the enumerated one as a select")
    # A date attribute has no branch of its own in `_attr_input`, so it falls through to a text box.
    date_attr = ui.page.locator(_attr("standard_creation_date")).first
    if date_attr.count() and not date_attr.get_attribute("type"):
        finding.append(
            Finding(
                finding_id="C-1",
                where="src/ea/ui/pages/element.py · _attr_input",
                severity="usability",
                summary="A date attribute is edited in a plain text box",
                detail=(
                    "`_attr_input` branches on boolean, enum, integer/number and text; the pack's four "
                    "`date` attributes (Standard Creation Date and its siblings) fall through to a bare "
                    "TextInput, so the reader gets no picker, no placeholder and no format checking."
                ),
            )
        )
    _open(ui, DE)
    _tab(ui, "Edit")
    pii = ui.page.locator(_attr("includes_pii")).first
    analytics = ui.page.locator(_attr("available_in_analytics_platform")).first
    ui.must("the boolean attributes have inputs", pii.count() > 0 and analytics.count() > 0)
    ui.check(
        "a boolean reads back the model's value in words",
        {pii.input_value(), analytics.input_value()} == {"no", "yes"},
        f"includes_pii={pii.input_value()}, analytics={analytics.input_value()}",
    )
    options = _options(ui, _attr("includes_pii"))
    ui.check("a boolean offers yes and no", options == ["yes", "no"], str(options))
    ui.shot("A boolean attribute is a yes/no select on the data entity")


@pytest.mark.scenario(
    scenario_id="C06",
    group="C",
    title="Saving a description change bumps the version and says which one it wrote",
    feature="Element · Edit · save",
    expected="A changed description saves as the next version, the page says so, and reopening shows the new text at the new version.",
)
def test_save_bumps_the_version(ui, record):
    _open(ui, EL)
    before_version = _version(ui)
    _tab(ui, "Edit")
    original = _desc(ui)
    ui.must("the description editor holds the model's text", "Curriculum" in original, original[:80])
    _set_desc(ui, original + "\n\nC-round: this line was added by the element group.")
    feedback = _save(ui)
    ui.must("the save reported a version", "Saved version" in feedback, feedback)
    saved = int(re.search(r"Saved version (\d+)", feedback).group(1))
    ui.check(
        "the version it wrote is the next one",
        saved == before_version + 1,
        f"was v{before_version}, saved version {saved}",
    )
    ui.shot("The Edit tab says which version it saved")
    _open(ui, EL)
    ui.check("the header shows the new version", _version(ui) == saved, f"v{_version(ui)}")
    ui.check(
        "Overview shows the text that was saved",
        "this line was added by the element group" in _panel(ui, "overview").inner_text(),
    )
    ui.shot("Overview reopened on the saved description, at the version the save reported")
    _tab(ui, "Edit")
    _set_desc(ui, original)
    restored = _save(ui)
    ui.check("the description is put back for the groups that follow", "Saved version" in restored, restored)


@pytest.mark.scenario(
    scenario_id="C07",
    group="C",
    title="A Markdown description with a mermaid fence renders as a diagram",
    feature="Element · Overview · Markdown",
    expected="A fenced mermaid block in the description is drawn as an SVG on Overview, and the prose around it still reads as prose.",
)
def test_mermaid_in_the_description(ui, record):
    fence = "```mermaid\nflowchart LR\n  a[Course] --> b[Unit]\n```"
    _open(ui, EL)
    _tab(ui, "Edit")
    original = _desc(ui)
    _set_desc(ui, original + "\n\n" + fence + "\n\nC-round: prose after the fence.")
    ui.must("the description saved", "Saved version" in _save(ui))
    _open(ui, EL)
    block = _pm(id=f"el-desc-{EL}-mermaid-0", type="mermaid-svg")
    _await_svg(ui, block)
    ui.check(
        "the fence is drawn as a diagram, not printed as code", ui.page.locator(f"{block} svg").count() > 0
    )
    drawn = ui.page.locator(f"{block} svg").first.text_content() or ""
    ui.check("the diagram carries the shapes the fence declared", "Course" in drawn and "Unit" in drawn)
    overview = _panel(ui, "overview").inner_text()
    ui.check("the prose after the fence still reads as prose", "prose after the fence" in overview)
    ui.check("the fence itself is not shown as text", "```" not in overview, overview[-200:])
    ui.shot("The description's mermaid fence is rendered as a diagram inside Overview")
    _tab(ui, "Edit")
    _set_desc(ui, original)
    ui.check("the description is put back for the groups that follow", "Saved version" in _save(ui))


@pytest.mark.scenario(
    scenario_id="C08",
    group="C",
    title="An element cannot be saved without a name",
    feature="Element · Edit · validation",
    expected="Clearing the name and saving is refused with the reason, and nothing is written.",
)
def test_empty_name_is_refused(ui, record):
    _open(ui, EL)
    before = _version(ui)
    _tab(ui, "Edit")
    ui.fill("el-name", "")
    feedback = _save(ui)
    ui.check("the save is refused", "Saved version" not in feedback, feedback)
    ui.check("the refusal names what is wrong", "name" in feedback.lower(), feedback)
    ui.shot("Saving with the name cleared is refused, and says why")
    _open(ui, EL)
    ui.check("nothing was written", _version(ui) == before, f"was v{before}, now v{_version(ui)}")
    ui.check("the name is still the model's", "Curriculum" in ui.body())


@pytest.mark.scenario(
    scenario_id="C09",
    group="C",
    title="Two people editing the same element: the second save is refused, not silently applied",
    feature="Element · Edit · optimistic concurrency",
    expected="A save made from a second tab wins; the first tab's save is refused, naming the version clash and telling the reader to reload.",
)
def test_concurrent_save_is_refused(ui, record, finding):
    _open(ui, EL)
    _tab(ui, "Edit")
    original = _desc(ui)
    _set_desc(ui, original + "\n\nC-round: written from the first tab.")
    second = ui.page.context.new_page()
    try:
        second.goto(f"{ui.base_url}/element/{EL}", wait_until="domcontentloaded")
        second.wait_for_selector("#el-tabs", timeout=20_000)
        second.locator('#el-tabs [role="tab"]:has-text("Edit")').first.click()
        box = second.locator(DESC_TEXT).first
        box.wait_for(state="visible", timeout=10_000)
        box.fill(original + "\n\nC-round: written from the second tab.")
        second.locator("#el-save").click()
        second.wait_for_selector("#el-save-feedback:has-text('Saved version')", timeout=25_000)
        ui.check(
            "the second tab saved",
            "Saved version" in second.locator("#el-save-feedback").inner_text(),
            second.locator("#el-save-feedback").inner_text(),
        )
    finally:
        second.close()
    feedback = _save(ui)
    ui.check("the first tab's save is refused", "Saved version" not in feedback, feedback)
    ui.check("the refusal says it was not saved", "Not saved" in feedback, feedback)
    ui.check("the refusal names the version clash", "version" in feedback.lower(), feedback)
    ui.check("the refusal says what to do about it", "Reload" in feedback, feedback)
    ui.shot("The stale tab's save is refused, naming the version it had and telling the reader to reload")
    if re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", feedback):
        finding.append(
            Finding(
                finding_id="C-2",
                where="src/ea/ui/pages/element.py · save · the conflict message",
                severity="usability",
                summary="The conflict message prints the stored timestamp raw, to the microsecond",
                detail=(
                    "The refusal reads 'changed by admin@example.edu at 2026-09-08 08:04:13.219652'. "
                    "It says the right things, but the time comes straight from the row: seconds and "
                    "microseconds, no time zone, and the actor as a raw identifier rather than the "
                    "display name the header shows for the same person."
                ),
            )
        )
    _open(ui, EL)
    ui.check(
        "the model holds what the tab that won wrote",
        "written from the second tab" in _panel(ui, "overview").inner_text(),
    )
    _tab(ui, "Edit")
    _set_desc(ui, original)
    ui.check("the description is put back for the groups that follow", "Saved version" in _save(ui))


# --------------------------------------------------------------------------- relationships


@pytest.mark.scenario(
    scenario_id="C10",
    group="C",
    title="The direction toggle changes which relationships may be added",
    feature="Element · Relationships · direction",
    expected="Switching from 'this element →' to '→ this element' replaces the list with the relationships this type may receive.",
)
def test_direction_toggle(ui, record):
    _open(ui, EL)
    _tab(ui, "Relationships")
    outgoing = _options(ui, "el-rel-type")
    ui.must("the outgoing relationships are offered", len(outgoing) > 0, str(outgoing))
    ui.check(
        "an outgoing relationship of this type is offered",
        "encapsulates" in _rel_names(outgoing),
        str(outgoing),
    )
    ui.segmented("el-rel-direction", "→ this element")
    incoming = _options(ui, "el-rel-type")
    ui.check("the incoming relationships are a different list", incoming != outgoing, str(incoming))
    ui.check(
        "an incoming relationship of this type is offered",
        "processes" in _rel_names(incoming),
        str(incoming),
    )
    ui.check(
        "the incoming list names the type at the other end",
        any("Physical Application Component →" in o for o in incoming),
        str(incoming),
    )
    ui.shot("The direction toggle set to '→ this element', with the relationships this element may receive")
    ui.segmented("el-rel-direction", "this element →")


@pytest.mark.scenario(
    scenario_id="C11",
    group="C",
    title="The other element is searched for, and the pair decides the relationships on offer",
    feature="Element · Relationships · the pair",
    expected="Typing part of a name finds the element with its identifier and type; once it is chosen only the relationships the metamodel allows between the two types remain.",
)
def test_pair_constrains_the_relationship_types(ui, record):
    _open(ui, EL)
    _tab(ui, "Relationships")
    before = _options(ui, "el-rel-type")
    offered = _pick_other(ui, "SRS_Course", DE)
    ui.must("the search finds something", len(offered) > 0, "nothing offered for SRS_Course")
    ui.check(
        "an option names the element, its identifier and its type",
        any(DE in o and "Data Entity" in o for o in offered),
        str(offered[:6]),
    )
    after = _options(ui, "el-rel-type")
    ui.check(
        "the list narrowed once both ends were known",
        len(after) < len(before),
        f"{len(after)} of {len(before)}: {after}",
    )
    ui.check(
        "only the relationship the metamodel allows between the two types is offered",
        _rel_names(after) == ["encapsulates"],
        str(after),
    )
    ui.shot("With a Data Entity at the other end, only 'encapsulates' remains on offer")


@pytest.mark.scenario(
    scenario_id="C12",
    group="C",
    title="The qualifier is dead until the relationship type declares qualifiers",
    feature="Element · Relationships · qualifiers",
    expected="On a Position the qualifier select is disabled until the stewardship relationship is chosen, and then offers the four roles the pack declares.",
)
def test_qualifier_enables_with_its_type(ui, record):
    _open(ui, POS)
    _tab(ui, "Relationships")
    ui.check("the qualifier starts disabled", ui.disabled("el-rel-qualifier"), "el-rel-qualifier")
    _pick_other(ui, "Unit Outlines", "IA-UNIT-OUTLINES")
    ui.check("choosing the other end alone does not enable it", ui.disabled("el-rel-qualifier"))
    types = _options(ui, "el-rel-type")
    ui.must("a relationship is on offer for the pair", len(types) > 0, str(types))
    ui.select("el-rel-type", "Owner / Data Custodian")
    ui.check("choosing a type that declares qualifiers enables it", not ui.disabled("el-rel-qualifier"))
    qualifiers = _options(ui, "el-rel-qualifier")
    ui.check(
        "it offers the four roles the pack declares",
        qualifiers == ["Owner", "Data Custodian", "Data Steward", "Data Administrator"],
        str(qualifiers),
    )
    ui.shot("The qualifier select, enabled by a relationship type that declares qualifiers")


@pytest.mark.scenario(
    scenario_id="C13",
    group="C",
    title="A relationship is added from the element page and deleted again",
    feature="Element · Relationships · add and delete",
    expected="Choosing the other end and a relationship adds it to the outgoing table and says so; the bin on that row removes it and says so.",
)
def test_add_and_delete_a_relationship(ui, record):
    other_name = "Student Enrolment Records"
    _open(ui, EL)
    _tab(ui, "Relationships")
    tables = ui.page.locator("#el-rel-tables")
    ui.must("the element does not have this relationship yet", other_name not in tables.inner_text())
    _pick_other(ui, "Student Enrolment", "IA-STUDENT-ENROL")
    ui.select("el-rel-type", "categorises")
    ui.click("el-rel-add")
    feedback = ui.text("el-rel-feedback")
    ui.must("the page says it added the relationship", "added" in feedback.lower(), feedback)
    ui.check("the outgoing table now holds it", other_name in tables.inner_text(), tables.inner_text()[:300])
    row = ui.page.locator(f"#el-rel-tables tr:has-text({json.dumps(other_name)})").first
    ui.check("the row names the relationship", "categorises" in row.inner_text(), row.inner_text())
    ui.check("the row says where it came from", "user" in row.inner_text().lower(), row.inner_text())
    ui.shot("The relationship that was just added, in the outgoing table")
    row.locator("button").last.click()
    ui.settle()
    ui.page.wait_for_timeout(300)
    feedback = ui.text("el-rel-feedback")
    ui.check("the page says it removed the relationship", "removed" in feedback.lower(), feedback)
    ui.check(
        "the table no longer holds it",
        other_name not in ui.page.locator("#el-rel-tables").inner_text(),
        ui.page.locator("#el-rel-tables").inner_text()[:300],
    )
    ui.shot("The relationship is gone from the table, and the page says it was removed")


# --------------------------------------------------------------------------- the graph


@pytest.mark.scenario(
    scenario_id="C14",
    group="C",
    title="The depth slider widens the neighbourhood the graph draws",
    feature="Element · Graph · depth",
    expected="Moving the depth from 1 to 2 adds the neighbours of the neighbours to the graph.",
)
def test_graph_depth(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    first = _cy(ui, "cy.$('.element').length")
    ui.must("the graph drew the neighbourhood", (first or 0) > 1, f"{first} nodes")
    ui.shot("The neighbourhood graph at depth 1")
    thumb = ui.page.locator("#el-graph-depth [role='slider']").first
    thumb.press("ArrowRight")
    ui.page.wait_for_timeout(700)
    ui.settle()
    ui.wait_graph()
    second = _cy(ui, "cy.$('.element').length")
    ui.check("depth 2 draws more than depth 1", (second or 0) > (first or 0), f"{first} then {second} nodes")
    ui.check(
        "the slider reports the depth it is on",
        (thumb.get_attribute("aria-valuenow") or "") == "2",
        thumb.get_attribute("aria-valuenow") or "",
    )
    ui.shot("The same neighbourhood at depth 2, wider than before")


@pytest.mark.scenario(
    scenario_id="C15",
    group="C",
    title="Every grouping the panel offers boxes the nodes it draws",
    feature="Element · Graph · grouping",
    expected="All seven groupings apply; six draw labelled boxes around the nodes and 'No grouping' draws none.",
)
def test_graph_groupings(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    nodes = _cy(ui, "cy.$('.element').length")
    for label in GROUPINGS:
        ui.select(GP_GROUP, label, exact=True)
        ui.page.wait_for_timeout(500)
        boxes = _cy(ui, "cy.$('.group').length")
        drawn = _cy(ui, "cy.$('.element').length")
        ui.check(f"'{label}' keeps every node on the canvas", drawn == nodes, f"{drawn} of {nodes}")
        if label == "No grouping":
            ui.check("'No grouping' draws no boxes", boxes == 0, f"{boxes} boxes")
        else:
            ui.check(f"'{label}' draws its boxes", (boxes or 0) > 0, f"{boxes} boxes")
        if label == "Group by layer":
            ui.shot("The graph grouped by layer, each layer a labelled box")
    ui.shot("The graph grouped by target state, the last of the seven groupings")
    ui.select(GP_GROUP, "Group by domain", exact=True)


@pytest.mark.scenario(
    scenario_id="C16",
    group="C",
    title="Every layout the panel offers redraws the same graph",
    feature="Element · Graph · layout",
    expected="All five layouts run, keep every node, and do not all arrange them the same way.",
)
def test_graph_layouts(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    nodes = _cy(ui, "cy.$('.element').length")
    seen: list[tuple[float, float]] = []
    for label in LAYOUTS:
        ui.select(GP_LAYOUT, label, exact=True)
        ui.page.wait_for_timeout(900)
        drawn = _cy(ui, "cy.$('.element').length")
        ui.check(f"the {label} layout keeps every node", drawn == nodes, f"{drawn} of {nodes}")
        centre = _cy(ui, "(function(){ var p = cy.$('.element')[0].position(); return [p.x, p.y]; })()")
        seen.append(tuple(centre or (0, 0)))
        if label == "Circle":
            ui.shot("The neighbourhood drawn with the Circle layout")
    ui.check("the five layouts are not all the same arrangement", len(set(seen)) > 1, str(seen))
    ui.select(GP_LAYOUT, "Grouped grid", exact=True)
    ui.page.wait_for_timeout(700)
    ui.shot("Back on the grouped grid, the layout the panel opens with")


@pytest.mark.scenario(
    scenario_id="C17",
    group="C",
    title="Fit and the two zoom controls move the graph the way they say",
    feature="Element · Graph · fit and zoom",
    expected="Zoom in enlarges, zoom out shrinks, and Fit puts the whole graph back in the window.",
)
def test_graph_fit_and_zoom(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    fitted = _cy(ui, "cy.zoom()")
    ui.must("the graph reports the zoom it is drawn at", fitted is not None, str(fitted))
    ui.click(GP_ZOOM_IN)
    ui.page.wait_for_timeout(400)
    zoomed_in = _cy(ui, "cy.zoom()")
    ui.check("zoom in enlarges the graph", zoomed_in > fitted, f"{fitted} then {zoomed_in}")
    ui.shot("The graph zoomed in on the neighbourhood")
    ui.click(GP_ZOOM_OUT)
    ui.click(GP_ZOOM_OUT)
    ui.page.wait_for_timeout(400)
    zoomed_out = _cy(ui, "cy.zoom()")
    ui.check("zoom out shrinks it again", zoomed_out < zoomed_in, f"{zoomed_in} then {zoomed_out}")
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    refitted = _cy(ui, "cy.zoom()")
    ui.check(
        "Fit puts the whole graph back in the window",
        abs(refitted - fitted) < max(0.02, fitted * 0.15),
        f"fitted {fitted}, refitted {refitted}",
    )
    ui.shot("Fit has put the whole neighbourhood back inside the panel")


@pytest.mark.scenario(
    scenario_id="C18",
    group="C",
    title="Tapping a node in the graph opens that element",
    feature="Element · Graph · navigation",
    expected="Tapping the data entity in the neighbourhood leaves this page for that element's own page.",
)
def test_tapping_a_node_navigates(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    ui.click(GP_FIT)
    ui.page.wait_for_timeout(500)
    position = _cy(
        ui,
        "(function(){ var n = cy.$('node[element_id = " + json.dumps(DE) + "]');"
        " if (!n.length) { return null; } var p = n[0].renderedPosition(); return [p.x, p.y]; })()",
    )
    ui.must("the data entity is on the canvas", position is not None, f"no node for {DE}")
    box = ui.page.locator(GP_CY).first.bounding_box()
    ui.page.mouse.click(box["x"] + position[0], box["y"] + position[1])
    ui.page.wait_for_timeout(700)
    ui.settle()
    ui.check("tapping the node opened that element", ui.page.url.endswith(f"/element/{DE}"), ui.page.url)
    ui.check("the page that opened is the one that was tapped", "SRS_Course" in ui.body())
    ui.shot("Tapping the data entity in the graph opened its own element page")


# --------------------------------------------------------------------------- the generated view


@pytest.mark.scenario(
    scenario_id="C19",
    group="C",
    title="The generated architecture view draws the neighbourhood, and zooms and resets",
    feature="Element · Graph · generated view",
    expected="The view renders as an SVG whose every shape carries an element identifier; zoom in enlarges it, Fit puts it back, and Reset layout redraws it.",
)
def test_generated_view(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    _await_svg(ui, VIEW)
    ui.must("the view is drawn as an SVG", ui.page.locator(f"{VIEW} svg").count() > 0)
    text = ui.page.locator(f"{VIEW} svg").first.text_content() or ""
    ui.check("the centre of the view is this element", f"[{EL}]" in text, text[-200:])
    ui.check(
        "every shape carries an element identifier",
        len(re.findall(r"\[[A-Z]{2,}[A-Z0-9-]*\]", text)) >= 3,
        text[-300:],
    )
    ui.check("the shapes carry the pack's stereotypes", "«" in text, text[-200:])
    ui.shot("The generated architecture view of the neighbourhood, drawn from the model")
    fitted = _view_scale(ui)
    ui.must("the view reports the zoom it is drawn at", fitted > 0, str(fitted))
    ui.click(VIEW_ZOOM_IN)
    ui.page.wait_for_timeout(400)
    ui.check("zoom in enlarges the view", _view_scale(ui) > fitted, f"{fitted} then {_view_scale(ui)}")
    ui.shot("The generated view zoomed in")
    ui.click(VIEW_ZOOM_OUT)
    ui.page.wait_for_timeout(300)
    ui.click(VIEW_FIT)
    ui.page.wait_for_timeout(500)
    ui.check(
        "Fit puts the view back where it started",
        abs(_view_scale(ui) - fitted) < max(0.02, fitted * 0.15),
        f"fitted {fitted}, refitted {_view_scale(ui)}",
    )
    ui.click(VIEW_RESET)
    ui.page.wait_for_timeout(1000)
    _await_svg(ui, VIEW)
    ui.check("Reset layout redraws the view", ui.page.locator(f"{VIEW} svg").count() > 0)
    ui.shot("The generated view after Fit and Reset layout")


@pytest.mark.scenario(
    scenario_id="C20",
    group="C",
    title="The generated view downloads as Markdown and as draw.io",
    feature="Element · Graph · downloads",
    expected="Both buttons produce a file named for the element: the Markdown holds the mermaid source, the draw.io file a diagram of the same shapes.",
)
def test_view_downloads(ui, record):
    _open(ui, EL)
    _open_graph_tab(ui)
    md = ui.download("el-view-md", ".md")
    ui.check("the Markdown is named for the element", EL in md.name, md.name)
    body = md.read_text(encoding="utf-8")
    ui.check("the Markdown holds the mermaid source", "```mermaid" in body, body[:120])
    ui.check("the Markdown names this element", EL in body, body[:200])
    drawio = ui.download("el-view-drawio", ".drawio")
    ui.check("the draw.io file is named for the element", EL in drawio.name, drawio.name)
    xml = drawio.read_text(encoding="utf-8")
    ui.check("the draw.io file is a diagram", "<mxGraphModel" in xml, xml[:120])
    ui.check("its shapes carry the element identifiers", EL in xml, xml[:400])
    ui.shot("The generated view, with the two download buttons that produced the files")


# --------------------------------------------------------------------------- history


@pytest.mark.scenario(
    scenario_id="C21",
    group="C",
    title="The History tab lists the change that was just made",
    feature="Element · History",
    expected="Saving an edit adds a row to History naming when, who, that it was an update, and the version it wrote.",
)
def test_history_lists_the_change(ui, record):
    _open(ui, DE)
    _tab(ui, "History")
    before = ui.page.locator("#el-history tr").count()
    _tab(ui, "Edit")
    ui.fill("el-target-note", "C-round: a note, to prove History records the change.")
    feedback = _save(ui)
    ui.must("the edit saved", "Saved version" in feedback, feedback)
    saved = int(re.search(r"Saved version (\d+)", feedback).group(1))
    _tab(ui, "History")
    table = ui.page.locator("#el-history")
    rows = table.locator("tr").count()
    ui.check("History gained a row", rows > before, f"{before} then {rows} rows")
    for header in ("when", "who", "op", "version"):
        ui.check(f"History has a '{header}' column", header in table.inner_text())
    top = table.locator("tr").nth(1).inner_text()
    ui.check("the newest row is the change just made", "update" in top, top)
    ui.check("it names who made it", "admin@example.edu" in top, top)
    ui.check("it names the version it wrote", str(saved) in top, top)
    ui.shot("History lists the edit that was just saved, with who made it and the version it wrote")
    _tab(ui, "Edit")
    ui.fill("el-target-note", "")
    ui.check("the note is put back for the groups that follow", "Saved version" in _save(ui))


@pytest.mark.scenario(
    scenario_id="C22",
    group="C",
    title="The Relationships tab keeps its count true when one is added",
    feature="Element · Relationships · the tab count",
    expected="The count in the tab label is the number of relationships in the tables, before an addition and after it.",
)
def test_relationship_count_follows_the_table(ui, record):
    # The tab label is rendered once, with the page; adding a relationship rewrites the
    # tables but not the label, so the screen ends up saying two different numbers.
    other_name = "Student Enrolment Records"
    _open(ui, EL)
    _tab(ui, "Relationships")
    before_label, before_rows = _rel_tab_count(ui), _rel_rows(ui)
    ui.must(
        "the tab counts what the tables hold", before_label == before_rows, f"{before_label} vs {before_rows}"
    )
    _pick_other(ui, "Student Enrolment", "IA-STUDENT-ENROL")
    ui.select("el-rel-type", "categorises")
    ui.click("el-rel-add")
    ui.must("the relationship was added", "added" in ui.text("el-rel-feedback").lower())
    ui.check("the tables hold one more", _rel_rows(ui) == before_rows + 1, f"{_rel_rows(ui)} rows")
    ui.check(
        "the tab counts the relationship that was just added",
        _rel_tab_count(ui) == before_rows + 1,
        f"the tab says {_rel_tab_count(ui)}, the tables hold {_rel_rows(ui)}",
    )
    ui.shot("The tab label and the tables, after a relationship was added")
    row = ui.page.locator(f"#el-rel-tables tr:has-text({json.dumps(other_name)})").first
    row.locator("button").last.click()
    ui.settle()
    ui.page.wait_for_timeout(300)
    ui.must("the relationship was removed again", "removed" in ui.text("el-rel-feedback").lower())
    ui.check(
        "the tab counts what is left after the delete",
        _rel_tab_count(ui) == _rel_rows(ui),
        f"the tab says {_rel_tab_count(ui)}, the tables hold {_rel_rows(ui)}",
    )
    ui.shot("The tab label and the tables, after the relationship was deleted again")
