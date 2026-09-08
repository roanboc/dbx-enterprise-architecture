"""Group F — Ask: the answer document, the views inside it, the trace, and the grounding.

The round runs on the stub provider: no model key, no network, the same tool sequence for
the same question every time. That is deliberate, and it is what these scenarios read. The
stub does not pretend to be a language model — it says so in the last line of every answer it
assembles — so the group asserts that sentence as documented behaviour rather than treating
it as a defect.

What the page owes a reader is a *document*, not a chat bubble: a title taken from the
question, a provenance line saying when and by whom it was answered, a generated architecture
view drawn from the model, the answer itself, the elements it names in a table that links to
them, and an honest account of how it was reached — the tool calls, their inputs and what
came back. Every scenario here reads one of those parts.

Two subjects carry the group. `SRS_Course_Offering` (DE-SRS-COURSE-OFFERING) is named by a
question that also carries the word "impact", so the stub runs search → get_element → impact
→ propose_view and the document gets its four-call trace, its elements table and its view.
`FX-GHOST-ENTITY` is an identifier shaped like a real one that no element carries, so the
answer can only say it was not found — which is the ungrounded-identifier path, and the one
place the "treat them as unverified" banner can be read.

Nothing here asserts an absolute total: the round shares one database and one agent with
every other group, so a check is a sentence that must be present, a row that must be there,
or a file that must have content.
"""

from __future__ import annotations

import json
import re

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

# The four chips the page offers, in the order ask.py lists them.
EXAMPLES = [
    "What is the impact of changing SRS_Course_Offering?",
    "Who owns the Course Catalogue and which applications contribute to it?",
    "Which data entities contain PII and where are they stored?",
    "List the information assets categorised by the Curriculum topic.",
]

OFFERING = "DE-SRS-COURSE-OFFERING"  # SRS_Course_Offering — a Data Entity with relationships both ways
GHOST = "FX-GHOST-ENTITY"  # shaped like an identifier, carried by nothing
IMPACT_Q = EXAMPLES[0]

DOCUMENT = "#ask-answer .ea-document"
SECTION_TITLE = "#ask-answer .ea-section-title"


def _pm(**parts: object) -> str:
    """The CSS selector for a pattern-matching component id, written the way Dash serialises it."""
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


VIEW_SVG = _pm(id="ask-view-0", type="mermaid-svg")
VIEW_SRC = _pm(id="ask-view-0", type="mermaid-src")


def _f(finding_id: str, where: str, severity: str, summary: str, detail: str) -> Finding:
    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


# --------------------------------------------------------------------------- the controls


def _textarea(ui):
    """The question box: Mantine may put the id on the field or on its wrapper."""
    field = ui.page.locator("textarea#ask-input")
    return field.first if field.count() else ui.page.locator("#ask-input textarea").first


def _question(ui) -> str:
    return _textarea(ui).input_value()


def _type_question(ui, text: str) -> None:
    box = _textarea(ui)
    box.click()
    box.fill(text)
    ui.settle()


def _ask(ui, text: str) -> None:
    """Put a question and press Ask, then wait for the document the callback returns."""
    _type_question(ui, text)
    ui.click("ask-button")
    ui.page.wait_for_selector(DOCUMENT, timeout=30_000)
    ui.settle()


def _open_ask(ui) -> None:
    ui.goto("/ask")
    ui.must("the Ask page rendered its question box", _textarea(ui).count() > 0)


def _section(ui, title: str):
    """One section of the answer document, addressed by the title it leads with."""
    return ui.page.locator("#ask-answer .ea-section").filter(
        has=ui.page.locator(f".ea-section-title:text-is('{title}')")
    )


def _section_body(ui, title: str) -> str:
    """A section's text without the heading the stylesheet shouts above it."""
    loc = _section(ui, title)
    if not loc.count():
        return ""
    body = loc.first.inner_text().strip()
    return body[len(title) :].strip() if body[: len(title)].lower() == title.lower() else body


def _section_titles(ui) -> list[str]:
    """The section headings as written, not as the stylesheet shouts them."""
    return [t.strip() for t in ui.page.locator(SECTION_TITLE).all_text_contents()]


def _document_text(ui) -> str:
    loc = ui.page.locator(DOCUMENT).first
    return loc.inner_text() if loc.count() else ""


# --------------------------------------------------------------------------- the scenarios


@pytest.mark.scenario(
    scenario_id="F01",
    group="F",
    title="The Ask page says which provider will answer, and offers a question with it",
    feature="Ask · the page",
    expected=(
        "The page names the stub provider in a badge, starts with the first example question "
        "already in the box, and offers Ask, Reset conversation and the four example chips."
    ),
)
def test_page_and_provider_badge(ui, record):
    _open_ask(ui)
    ui.check("the page is titled 'Ask the model'", "Ask the model" in ui.body())
    badge = ui.text("ask-provider")
    ui.check(
        "the provider badge names the stub provider",
        badge.lower().startswith("provider:") and "stub" in badge.lower(),
        f"the badge reads {badge!r}",
    )
    ui.check(
        "the badge claims no model, because none is configured",
        "·" not in badge,
        f"the badge reads {badge!r}",
    )
    ui.check(
        "the box opens with the first example already in it",
        _question(ui) == EXAMPLES[0],
        f"the box holds {_question(ui)!r}",
    )
    ui.check("the Ask button is offered", ui.visible("ask-button"))
    ui.check("Reset conversation is offered", ui.visible("ask-reset"))
    chips = ui.page.locator("[id*='ask-example']")
    ui.check("all four example chips are offered", chips.count() == 4, f"{chips.count()} chips")
    ui.check(
        "the page says every identifier comes from a tool result",
        "Every identifier comes from a tool result" in ui.body(),
    )
    ui.check(
        "nothing has been answered yet, so no document is shown",
        ui.page.locator(DOCUMENT).count() == 0,
    )
    ui.shot(
        "The Ask page before any question: the provider badge reads stub, and the four example chips sit under the box"
    )


@pytest.mark.scenario(
    scenario_id="F02",
    group="F",
    title="Each example chip fills the question box with its own question",
    feature="Ask · example questions",
    expected="Clicking any of the four chips replaces the text in the box with exactly that question.",
)
def test_example_chips_fill_the_box(ui, record, finding):
    _open_ask(ui)
    chip = ui.page.locator(_pm(i=0, type="ask-example")).first
    ui.check(
        "a chip presents itself as something to click",
        chip.evaluate("el => getComputedStyle(el).cursor") == "pointer",
        "the chips are styled with a pointer cursor and a hover colour",
    )
    broken = []
    for i, question in enumerate(EXAMPLES):
        # Start from a different question each time, so a chip that does nothing is visible.
        _type_question(ui, "placeholder")
        ui.click(_pm(i=i, type="ask-example"))
        ui.page.wait_for_timeout(150)
        ui.settle()
        got = _question(ui)
        if got != question:
            broken.append(i + 1)
        ui.check(
            f"chip {i + 1} puts its own question in the box",
            got == question,
            f"the box holds {got!r}, expected {question!r}",
        )
    ui.shot("The example chips: clicking one leaves the question box holding whatever was typed before")
    if broken:
        # The chips are dmc.Badge, which has no n_clicks property, so the callback behind
        # {"type": "ask-example"} can never fire. The scenario asserts the behaviour the page
        # advertises (a pointer cursor and a hover highlight) and fails until a control that
        # reports clicks is used instead.
        finding.append(
            _f(
                "F-1",
                "src/ea/ui/pages/ask.py · the ask-example chips",
                "defect",
                "The four example question chips look clickable but do nothing",
                "The chips are rendered as dmc.Badge with a pattern-matching id and a callback on "
                "n_clicks, but Badge has no n_clicks property, so no click ever reaches the "
                "callback. They carry the ea-chip class, which sets a pointer cursor and a hover "
                "colour, so a reader is invited to click something inert. Every one of the four "
                f"chips is affected (chips {broken}). A Button, an Anchor or a NavLink would "
                "report the click.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F03",
    group="F",
    title="A question becomes a document with a title, a provenance line and the answer",
    feature="Ask · the answer document",
    expected=(
        "Asking about SRS_Course_Offering returns a document titled with the question, a line "
        "saying when it was answered and by which provider, an Answer section naming the element "
        "and its impact, and the stub's closing sentence that no language model is configured."
    ),
)
def test_answer_document(ui, record, finding):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    ui.must("the answer came back as a document", ui.page.locator(DOCUMENT).count() > 0)
    title = ui.page.locator(f"{DOCUMENT} h2").first.inner_text().strip()
    ui.check(
        "the document is titled with the question, without its question mark",
        title == IMPACT_Q.rstrip("?"),
        f"the title reads {title!r}",
    )
    text = _document_text(ui)
    provenance = re.search(r"Answered (\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC) · (\S+)", text)
    ui.check(
        "a provenance line says when it was answered and by whom",
        provenance is not None,
        f"the document opens {text[:180]!r}",
    )
    if provenance:
        ui.check(
            "the provenance names the stub provider",
            provenance.group(2) == "stub",
            f"the provenance names {provenance.group(2)!r}",
        )
    ui.check(
        "the document has an Answer section",
        "Answer" in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    body = _section_body(ui, "Answer")
    ui.check(
        "the answer leads with the element the question named, and its identifier",
        body.startswith("SRS_Course_Offering") and OFFERING in body.split("\n")[0],
        f"the answer opens {body[:160]!r}",
    )
    ui.check(
        "the answer counts what depends on the element and what it depends on",
        re.search(r"\d+ elements depend on it \(upstream\)", body) is not None,
        f"the answer opens {body[:200]!r}",
    )
    ui.check(
        "the answer carries the completeness caveat from the impact tool",
        "Completeness:" in body,
        f"the answer closes {body[-200:]!r}",
    )
    # Documented behaviour without a model key: the stub says plainly that it is not one.
    ui.check(
        "the answer closes by saying no language model is configured",
        "No language model is configured" in body and "assembled from tool results only" in body,
        f"the answer closes {body[-200:]!r}",
    )
    ui.check(
        "the document is not marked as holding unverified identifiers",
        "treat them as unverified" not in text,
    )
    # The caveat is a statement about the whole answer, so it must not read as part of the last
    # element in the list above it. It is appended without a blank line, so the renderer swallows
    # it into the final bullet; this check asserts the caveat a reader should get instead.
    glued = ui.page.locator("#ask-answer .ea-doc li", has_text="Completeness:")
    ui.check(
        "the completeness caveat stands on its own, not as the tail of the last bullet",
        glued.count() == 0,
        "" if glued.count() == 0 else f"it reads {glued.first.inner_text()[-160:]!r}",
    )
    ui.shot(
        "The answer document: the question as its title, the provenance line under it, and the answer assembled from tool results"
    )
    if glued.count():
        finding.append(
            _f(
                "F-4",
                "src/ea/agent/agent.py · the stub answer, and the Answer section that renders it",
                "usability",
                "The completeness caveat is swallowed into the last bullet of the answer",
                "The stub appends 'Completeness: n/m relationship types ... have instances.' straight "
                "after the last '- it depends on:' line with no blank line between them, so Markdown "
                "reads it as more of that list item. The caveat qualifies the whole answer and is the "
                "one sentence that says what the answer might be missing, and it arrives looking like "
                "a note about one element. A blank line before it separates the paragraph.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F04",
    group="F",
    title="'Elements in this answer' lists every element the answer names, and links to it",
    feature="Ask · elements table",
    expected=(
        "The document carries a table of the elements the answer cites, each with its identifier, "
        "type and status, and each name linking to that element's page."
    ),
)
def test_elements_table(ui, record):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    ui.must(
        "the document has an Elements in this answer section",
        "Elements in this answer" in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    table = _section(ui, "Elements in this answer").first
    headers = [h.strip() for h in table.locator("th").all_text_contents()]
    ui.check(
        "the table is headed ID, Element, Type and Status",
        headers == ["ID", "Element", "Type", "Status"],
        f"the headers are {headers}",
    )
    rows = table.locator("tbody tr")
    ui.check("the table lists at least one element", rows.count() >= 1, f"{rows.count()} rows")
    row = table.locator("tbody tr", has=ui.page.locator(f"code:text-is('{OFFERING}')"))
    ui.must(
        "the element the question named has a row",
        row.count() == 1,
        f"{row.count()} rows carry {OFFERING}",
    )
    # Mantine shouts a badge in uppercase, so read the text the page was given, not the paint.
    cells = [c.strip() for c in row.first.locator("td").all_text_contents()]
    ui.check("its row names the element", cells[1] == "SRS_Course_Offering", f"the cells are {cells}")
    ui.check("its row names the element type", cells[2] == "Data Entity", f"the cells are {cells}")
    ui.check("its row carries the element's status", cells[3] == "approved", f"the cells are {cells}")
    link = row.first.locator("a").first
    href = link.get_attribute("href") if link.count() else ""
    ui.check(
        "the element name links to the element's own page",
        href == f"/element/{OFFERING}",
        f"the href is {href!r}",
    )
    answer = _section_body(ui, "Answer")
    listed = [c.strip() for c in table.locator("tbody tr td code").all_text_contents()]
    ui.check(
        "every identifier in the table also appears in the answer",
        all(i in answer for i in listed),
        f"the table lists {listed}",
    )
    ui.shot("Elements in this answer: one row per element the answer cites, each linking to its own page")


@pytest.mark.scenario(
    scenario_id="F05",
    group="F",
    title="An identifier cited in the answer opens the element it names",
    feature="Ask · grounding",
    expected=(
        "The answer cites element identifiers so the reader can open them, so each citation is "
        "either plain text or a link to that element's page — and reading the answer never costs "
        "the reader the answer."
    ),
)
def test_cited_identifiers_are_openable(ui, record, finding):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    links = ui.page.locator("#ask-answer .ea-doc a")
    cited = links.count()
    ui.must("the answer renders its citations as links", cited > 0, f"{cited} anchors in the answer text")
    hrefs = links.evaluate_all("els => els.map(e => [e.textContent.trim(), e.getAttribute('href')])")
    wrong = [(t, h) for t, h in hrefs if h != f"/element/{t}"]
    ui.check(
        "every cited identifier links to the element it names",
        not wrong,
        f"{len(wrong)} of {cited} citations do not: {wrong[:4]}",
    )
    ui.shot("The answer text: every element identifier is rendered as a link the reader is invited to follow")
    if wrong:
        # dcc.Markdown reads `[DE-SRS-COURSE-OFFERING]` as a shortcut link reference with no
        # definition and emits <a href="">, which resolves to the page itself. Following one
        # reloads /ask and the answer is gone — the two checks below prove that, and are the
        # behaviour a reader would call wrong.
        first = links.first
        label = first.inner_text().strip()
        before = ui.page.url
        first.click()
        ui.page.wait_for_load_state("domcontentloaded")
        ui.page.wait_for_timeout(800)
        ui.check(
            f"following the citation {label} goes to that element's page",
            ui.page.url.endswith(f"/element/{label}"),
            f"it went from {before} to {ui.page.url}",
        )
        ui.check(
            "and following it does not throw the answer away",
            ui.page.locator(DOCUMENT).count() > 0,
            "the page reloaded and the answer document is gone",
        )
        ui.shot("After following a cited identifier: the page reloaded and the answer document has gone")
        finding.append(
            _f(
                "F-2",
                "src/ea/ui/pages/ask.py · the Answer section",
                "defect",
                "Element identifiers in the answer render as links with an empty href, and following one discards the answer",
                "The agent cites identifiers in square brackets so the reader can open them. The "
                "Markdown renderer reads `[PAC-SRS]` as a shortcut link reference, finds no "
                'definition, and emits `<a href="">PAC-SRS</a>`: the brackets disappear, the '
                "identifier is styled as a link, and following it resolves to the current URL. "
                "The page reloads and the answer document, which is held only in the callback's "
                "output, is lost. Render the citation as plain text, or link it to "
                "/element/<id> the way the elements table does.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F06",
    group="F",
    title="The document leads with a generated architecture view drawn from the model",
    feature="Ask · generated view",
    expected=(
        "The view the agent asked for is drawn inside the answer, above the answer text, with a "
        "title of its own, every shape carrying an element identifier, and the pan, zoom and "
        "reset controls a reader can arrange it with."
    ),
)
def test_generated_view(ui, record):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    ui.must("a diagram block was placed in the document", ui.page.locator(VIEW_SRC).count() > 0)
    ui.wait_mermaid()
    svg = ui.page.locator(f"{VIEW_SVG} svg")
    ui.must("the diagram was drawn in the browser", svg.count() > 0)
    titles = _section_titles(ui)
    view_title = "Impact of SRS_Course_Offering"
    ui.check(
        "the view carries the title the agent asked for",
        view_title in titles,
        f"the sections are {titles}",
    )
    if view_title in titles and "Answer" in titles:
        ui.check(
            "the view is placed above the answer",
            titles.index(view_title) < titles.index("Answer"),
            f"the sections are {titles}",
        )
    drawn = svg.first.text_content() or ""
    ui.check(
        "every shape carries its element identifier, so the reader can open it",
        f"[{OFFERING}]" in drawn,
        f"the diagram reads {drawn[:200]!r}",
    )
    source = ui.page.locator(VIEW_SRC).first.inner_text()
    ui.check(
        "the diagram is generated from the model, not written by the agent",
        source.lstrip().startswith("flowchart") and OFFERING in source,
        f"the source opens {source[:120]!r}",
    )
    for control, what in (
        ("mermaid-zoom-in", "zoom in"),
        ("mermaid-zoom-out", "zoom out"),
        ("mermaid-fit", "fit to the window"),
        ("mermaid-full", "full screen"),
    ):
        ui.check(
            f"the view offers {what}",
            ui.page.locator(_pm(id="ask-view-0", type=control)).count() > 0,
        )
    ui.check(
        "the view says a rearrangement is not saved",
        "Nothing is saved" in _document_text(ui),
    )
    ui.shot("The generated architecture view inside the answer, every shape carrying an element identifier")


@pytest.mark.scenario(
    scenario_id="F07",
    group="F",
    title="The tool trace lists every call with its input and what came back",
    feature="Ask · tool trace",
    expected=(
        "Under the document, a trace names the provider and the number of calls, one accordion "
        "row per call carrying the tool name and its input, and expanding a row shows the result "
        "the tool returned."
    ),
)
def test_tool_trace(ui, record):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    trace = ui.text("ask-trace")
    ui.must("a tool trace was written under the document", bool(trace), "nothing was rendered under it")
    header = re.search(r"Tool trace · (\d+) calls · provider (\S+)", trace, re.IGNORECASE)
    ui.must(
        "the trace says how many calls were made and by which provider",
        header is not None,
        f"the trace opens {trace[:160]!r}",
    )
    ui.check(
        "the trace names the stub provider",
        header.group(2).lower() == "stub",
        f"the trace names {header.group(2)!r}",
    )
    items = ui.page.locator("#ask-trace .mantine-Accordion-item")
    ui.check(
        "there is one row per call the trace counted",
        items.count() == int(header.group(1)),
        f"{items.count()} rows for {header.group(1)} calls",
    )
    names = [
        t.strip() for t in ui.page.locator("#ask-trace .mantine-Accordion-control code").all_text_contents()
    ]
    ui.check(
        "the calls are the ones an impact question needs, in the order they were made",
        names == ["search_elements", "get_element", "impact", "propose_view"],
        f"the trace lists {names}",
    )
    controls = ui.page.locator("#ask-trace .mantine-Accordion-control")
    first = controls.first.inner_text()
    ui.check(
        "each row shows the input the tool was called with",
        '"text"' in first and "SRS_Course_Offering" in first,
        f"the first row reads {first!r}",
    )
    controls.nth(1).click()
    ui.settle()
    panel = ui.page.locator("#ask-trace .mantine-Accordion-panel:visible").first
    preview = panel.inner_text() if panel.count() else ""
    ui.check(
        "expanding a row shows a preview of what the tool returned",
        OFFERING in preview and "SRS_Course_Offering" in preview,
        f"the panel reads {preview[:200]!r}",
    )
    ui.check(
        "the document repeats the calls as an account of how it was answered",
        "How this was answered" in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    ui.shot("The tool trace: one row per call, and the expanded row showing what the tool returned")


@pytest.mark.scenario(
    scenario_id="F08",
    group="F",
    title="The document can be copied as Markdown and downloaded as Markdown or draw.io",
    feature="Ask · take the document away",
    expected=(
        "The document offers Copy Markdown, and both downloads produce a real file: the Markdown "
        "carries the title, the answer, the elements table and a Mermaid fence; the draw.io file "
        "is a diagram carrying the same element identifiers."
    ),
)
def test_copy_and_downloads(ui, record):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    copy = ui.page.locator("#ask-answer .ea-copy")
    ui.must("the document offers a Copy Markdown control", copy.count() > 0)
    ui.check(
        "the copy control is labelled",
        "Copy Markdown" in copy.first.inner_text(),
        f"it reads {copy.first.inner_text()!r}",
    )
    clipboard = ui.page.locator("#ask-answer .ea-clipboard")
    ui.check("the copy control is a clipboard the reader can click", clipboard.count() > 0)
    copied = ""
    try:
        clipboard.first.click()
        ui.page.wait_for_timeout(300)
        copied = ui.page.evaluate("() => navigator.clipboard.readText()")
    except Exception as exc:  # noqa: BLE001 — a browser that refuses the clipboard is not the app's fault
        ui.check("the clipboard could be read back", True, f"not read: {exc}")
    if copied:
        ui.check(
            "what was copied is the whole document as Markdown",
            copied.startswith(f"# {IMPACT_Q.rstrip('?')}") and "```mermaid" in copied,
            f"the clipboard holds {copied[:120]!r}",
        )

    md = ui.download("ask-doc-md", ".md")
    text = md.read_text(encoding="utf-8")
    ui.check(
        "the Markdown is named after the question",
        "course-offering" in md.name.lower() or "impact" in md.name.lower(),
        f"the file is called {md.name}",
    )
    for what, needle in (
        ("the question as its title", f"# {IMPACT_Q.rstrip('?')}"),
        ("the provenance line", "Answered "),
        ("the answer", "## Answer"),
        ("the elements table", "## Elements in this answer"),
        ("a generated diagram as a Mermaid fence", "```mermaid"),
        ("the account of how it was answered", "## How this was answered"),
        ("the element the answer names", OFFERING),
    ):
        ui.check(
            f"the Markdown carries {what}",
            needle in text,
            "" if needle in text else f"{needle!r} is missing",
        )

    drawio = ui.download("ask-doc-drawio", ".drawio")
    xml = drawio.read_text(encoding="utf-8")
    ui.check(
        "the draw.io file is a draw.io document",
        xml.lstrip().startswith("<?xml") and "<mxfile" in xml,
        f"the file opens {xml[:120]!r}",
    )
    ui.check(
        "the draw.io diagram carries the same element identifier",
        OFFERING in xml,
        f"the file is {len(xml)} characters",
    )
    ui.shot("The document toolbar: Copy Markdown beside the two downloads, both of which produced a file")


@pytest.mark.scenario(
    scenario_id="F09",
    group="F",
    title="Reset conversation clears the answer and its trace",
    feature="Ask · reset",
    expected=(
        "After an answer is on screen, Reset conversation removes the document and the trace and "
        "leaves the question box as it was, ready to ask again."
    ),
)
def test_reset_clears_the_answer(ui, record):
    _open_ask(ui)
    _ask(ui, IMPACT_Q)
    ui.must("there is an answer to clear", ui.page.locator(DOCUMENT).count() > 0)
    ui.check("the trace is on screen too", bool(ui.text("ask-trace")))
    ui.click("ask-reset")
    ui.page.wait_for_timeout(200)
    ui.settle()
    ui.check(
        "the answer document is gone",
        ui.page.locator(DOCUMENT).count() == 0,
        f"{ui.page.locator(DOCUMENT).count()} documents remain",
    )
    ui.check(
        "the tool trace is gone",
        ui.text("ask-trace") == "",
        f"the trace reads {ui.text('ask-trace')[:80]!r}",
    )
    ui.check(
        "the question is still in the box, so it can be asked again",
        _question(ui) == IMPACT_Q,
        f"the box holds {_question(ui)!r}",
    )
    ui.check("the page still offers Ask", ui.visible("ask-button"))
    ui.shot(
        "After Reset conversation: the document and the trace are gone and the question box is ready again"
    )
    # Prove the page still answers after a reset rather than leaving the group on an empty screen.
    _ask(ui, IMPACT_Q)
    ui.check("a question asked after the reset is answered again", ui.page.locator(DOCUMENT).count() > 0)


@pytest.mark.scenario(
    scenario_id="F10",
    group="F",
    title="An identifier the model does not carry is answered as not found and marked unverified",
    feature="Ask · grounding",
    expected=(
        "Asking about FX-GHOST-ENTITY says no element carries that identifier, marks the "
        "identifier as unverified because no tool returned it, names no elements and draws no "
        "view — and offers no download that cannot produce a file."
    ),
)
def test_unknown_identifier_is_not_invented(ui, record, finding):
    _open_ask(ui)
    _ask(ui, f"What is the impact of changing {GHOST}?")
    ui.must("the question was answered as a document", ui.page.locator(DOCUMENT).count() > 0)
    text = _document_text(ui)
    body = _section_body(ui, "Answer")
    ui.check(
        "the answer says no element carries that identifier",
        "no element with id" in body.lower() and GHOST in body,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "nothing was invented for it",
        "depend on it" not in body,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "the identifier is marked as unverified, because no tool returned it",
        "treat them as unverified" in text and GHOST in text,
        f"the document reads {text[:300]!r}",
    )
    ui.check(
        "no elements table is shown, because the answer names no element that exists",
        "Elements in this answer" not in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    ui.check(
        "no view is drawn, because there is nothing in the model to draw",
        ui.page.locator(VIEW_SRC).count() == 0,
    )
    called = [
        t.strip() for t in ui.page.locator("#ask-trace .mantine-Accordion-control code").all_text_contents()
    ]
    ui.check(
        "the trace shows the one call that looked for it",
        called == ["get_element"],
        f"the trace lists {called}",
    )
    ui.shot(
        "An identifier the model does not carry: the answer says it was not found and the banner marks it unverified"
    )
    trace = ui.text("ask-trace")
    if re.search(r"1 calls", trace, re.IGNORECASE):
        finding.append(
            _f(
                "F-5",
                "src/ea/ui/pages/ask.py · the tool trace heading",
                "consistency",
                "The tool trace heading reads '1 calls' when only one tool was called",
                "The heading is built as '{n} calls' with no singular form, so a one-call answer — "
                "which is what a question about an identifier the model does not carry produces — "
                "is headed 'Tool trace · 1 calls · provider stub'.",
            )
        )
    if body.strip().lower().startswith("no element with id"):
        finding.append(
            _f(
                "F-6",
                "src/ea/agent/agent.py · the stub answer for an unknown identifier, shown as the Answer",
                "usability",
                "An unknown identifier is answered with the raw tool error and no way forward",
                "The tool's error string, 'no element with id FX-GHOST-ENTITY', becomes the whole "
                "answer: no capital, no full stop, and nothing about what the reader might do "
                "instead — search for the name, browse the type, or check the identifier. The other "
                "dead end in the same provider (a question that matches nothing) does say what to "
                "try next, so the two refusals do not read alike.",
            )
        )

    # The document has no view, so Download draw.io has nothing to write — but the button is
    # offered all the same, and clicking it does nothing and says nothing. The correct behaviour
    # is either to produce a file or to say why it cannot; this check asserts that and fails
    # until the application does one of the two.
    button = ui.page.locator("#ask-doc-drawio")
    excused = ui.disabled("ask-doc-drawio")
    produced = False
    if button.count() and not excused:
        try:
            with ui.page.expect_download(timeout=4_000) as info:
                button.first.click()
            produced = bool(info.value)
        except Exception:  # noqa: BLE001 — no download is the finding, not a crash
            produced = False
        ui.settle()
    ok = produced or excused or not button.count()
    ui.check(
        "Download draw.io either produces a file or is disabled with a reason",
        ok,
        "" if ok else "it is offered on a document with no view, and pressing it does nothing at all",
    )
    if not ok:
        finding.append(
            _f(
                "F-3",
                "src/ea/ui/pages/ask.py · the ask-doc-drawio button",
                "usability",
                "Download draw.io does nothing, silently, when the answer has no view",
                "An answer that names no element in the model carries no generated view, so the "
                "download callback returns no_update. The button is still offered in the document "
                "toolbar and gives the reader no feedback at all when it is pressed. Either hide "
                "or disable it with a reason, or say there is no diagram to export.",
            )
        )
    # Leave the page on something that works, so the next group does not open a stale refusal.
    ui.click("ask-reset")
