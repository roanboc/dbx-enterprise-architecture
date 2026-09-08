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


NONSENSE = "Zzqqxx blorptastic wumbulator kwyjibo"  # four words nothing in the model carries
CATALOGUE = "IA-COURSE-CAT"  # Course Catalogue — an Information Asset with owners and contributors
SUBJECT_RE = re.compile(r"^(.+?)\s+([A-Z][A-Z0-9]{1,7}-[A-Za-z0-9-]+)\s*[—-]")


def _ask_afresh(ui, text: str) -> None:
    """Ask, and wait until the document on screen is the one *this* question produced.

    A second question replaces the first in place, so waiting for `.ea-document` alone would
    read the answer that is already there.
    """
    _type_question(ui, text)
    ui.click("ask-button")
    ui.page.wait_for_function(
        "want => { const h = document.querySelector('#ask-answer .ea-document h2');"
        " return !!h && h.textContent.trim() === want; }",
        arg=text.strip().rstrip("?"),
        timeout=30_000,
    )
    ui.settle()


def _subject(ui) -> tuple[str, str]:
    """The element the answer opens with: the name it leads with and the identifier beside it."""
    lines = _section_body(ui, "Answer").split("\n")
    m = SUBJECT_RE.match(lines[0].strip() if lines else "")
    return (m.group(1).strip(), m.group(2)) if m else ("", "")


def _chip_labels(ui) -> list[str]:
    """The chips' own text — the stylesheet shouts a badge, so read what it was given."""
    return [
        (ui.page.locator(_pm(i=i, type="ask-example")).first.text_content() or "").strip()
        for i in range(len(EXAMPLES))
    ]


def _visible_chip(ui, i: int):
    """The chip a reader sees. The click may be reported by a wrapper around it that draws nothing."""
    holder = ui.page.locator(_pm(i=i, type="ask-example")).first
    inner = holder.locator(".ea-chip")
    return inner.first if inner.count() else holder


def _trace_calls(ui) -> list[str]:
    """The tools the trace says were called, in order."""
    return [
        t.strip() for t in ui.page.locator("#ask-trace .mantine-Accordion-control code").all_text_contents()
    ]


def _refusal_shown(ui) -> bool:
    """Anything on the page that tells the reader why their question was not asked."""
    box = _textarea(ui)
    if (box.get_attribute("aria-invalid") or "").lower() == "true":
        return True
    return (
        ui.page.locator("#page [role='alert'], #page .mantine-Alert-root, .mantine-Notification-root").count()
        > 0
    )


def _download_or_nothing(ui, control: str):
    """Press a download control; return the file it produced, or None, and what the browser logged.

    `ui.download` waits for a download and ends the scenario when none comes; a control that
    produces nothing at all is a finding to be read beside the checks around it.
    """
    logged: list[str] = []

    def _console(message) -> None:  # noqa: ANN001 — playwright event payload
        if message.type == "error":
            logged.append(message.text)

    ui.page.on("console", _console)
    path = None
    try:
        with ui.page.expect_download(timeout=8_000) as info:
            ui.page.locator(control).first.click()
        dl = info.value
        path = ui.run_dir / "downloads" / dl.suggested_filename
        dl.save_as(str(path))
    except Exception:  # noqa: BLE001 — nothing arriving is what this helper reports
        pass
    finally:
        ui.page.wait_for_timeout(200)
        ui.page.remove_listener("console", _console)
    ui.settle()
    return path, logged


def _canvas_scale(ui) -> float:
    """How far the reader has zoomed the generated view: the scale on the canvas it sits on."""
    canvas = ui.page.locator(f"{VIEW_SVG} .ea-mermaid-canvas").first
    style = (canvas.get_attribute("style") or "") if canvas.count() else ""
    m = re.search(r"scale\(([\d.]+)\)", style)
    return float(m.group(1)) if m else 0.0


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
        "and says what to do about it rather than handing back the tool's error",
        "search for it by name" in body.lower(),
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
    # The heading is drawn in capitals, so read it in the case it is measured in.
    heading = trace.lower()
    ui.check(
        "the trace heading counts one call as one call",
        "1 call" in heading and "1 calls" not in heading,
        trace[:120] or "(no trace)",
    )
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


@pytest.mark.scenario(
    scenario_id="F11",
    group="F",
    title="The four chips carry exactly the four questions the page offers",
    feature="Ask · example questions",
    expected=(
        "Each chip reads as one whole question — the same question the page would ask — the four "
        "differ from one another, and the box says what it takes and announces itself."
    ),
)
def test_offered_questions_read_as_questions(ui, record):
    _open_ask(ui)
    labels = _chip_labels(ui)
    for i, question in enumerate(EXAMPLES):
        ui.check(
            f"chip {i + 1} reads as the whole question it offers",
            labels[i] == question,
            f"it reads {labels[i]!r}, expected {question!r}",
        )
    ui.check(
        "the four chips offer four different questions",
        len(set(labels)) == len(EXAMPLES),
        f"the chips read {labels}",
    )
    ui.check(
        "the chips are introduced as questions to try",
        "Try:" in ui.body(),
    )
    box = _textarea(ui)
    named = bool(
        box.evaluate(
            "el => !!(el.getAttribute('aria-label') || (el.labels||[]).length || el.closest('[aria-label]'))"
        )
    )
    ui.check(
        "the question box has a name a reader who cannot see it is given",
        named,
        "" if named else "the box carries neither an aria-label nor a label of its own",
    )
    placeholder = box.get_attribute("placeholder") or ""
    ui.check(
        "the box says what kind of question it takes",
        "ask about" in placeholder.lower(),
        f"the placeholder reads {placeholder!r}",
    )
    ui.check("Ask can be pressed", not ui.disabled("ask-button"))
    ui.shot("The four questions the page offers, each chip carrying one whole question")


@pytest.mark.scenario(
    scenario_id="F12",
    group="F",
    title="Every question the page offers is answered, about the element it names",
    feature="Ask · example questions",
    expected=(
        "Each of the four offered questions comes back as a document: an answer about an element "
        "of the model rather than a refusal, the elements it names in a table, and a generated "
        "view — and a question that names an element by its name is answered about that element."
    ),
)
def test_every_offered_question_is_answered(ui, record, finding):
    _open_ask(ui)
    # The model carries an element named exactly "Course Catalogue", so this question has one subject.
    named = {1: ("Course Catalogue", CATALOGUE)}
    wrong: list[str] = []
    for i, question in enumerate(EXAMPLES):
        _ask_afresh(ui, question)
        body = _section_body(ui, "Answer")
        ui.check(
            f"question {i + 1} is answered from the model, not refused",
            "could not match your question" not in body,
            f"the answer opens {body[:160]!r}",
        )
        name, ident = _subject(ui)
        ui.check(
            f"question {i + 1} says which element it is about, with its identifier",
            bool(name and ident),
            f"the answer opens {body[:160]!r}",
        )
        ui.check(
            f"question {i + 1} lists the elements it names in a table",
            "Elements in this answer" in _section_titles(ui),
            f"the sections are {_section_titles(ui)}",
        )
        drawn = ui.page.locator(VIEW_SRC).count() > 0
        ui.check(
            f"question {i + 1} is drawn as a view of the model",
            drawn,
            "" if drawn else "no diagram was placed in the document",
        )
        if i in named:
            want_name, want_id = named[i]
            about_it = ident == want_id
            if not about_it:
                wrong.append(f"{question!r} was answered about {name} [{ident}]")
            ui.check(
                f"the question about the {want_name} is answered about the {want_name}",
                about_it,
                f"it is answered about {name} [{ident}], not {want_name} [{want_id}]",
            )
            ui.shot(f"The answer to the offered question about the {want_name}")
    ui.shot("The last of the four offered questions, answered as a document")
    if wrong:
        finding.append(
            _f(
                "F-7",
                "src/ea/agent/agent.py · StubProvider.answer, the element it takes the question to be about",
                "defect",
                "A question naming an element by name is answered about a different element, without saying so",
                "The stub searches for the longest words of the question and takes `matches[0]`. "
                "`search_elements` orders its matches alphabetically by name and matches the "
                "description and the attributes as well as the name, so an exact name match does "
                "not win: searching 'Catalogue' returns 'CMS to SRS curriculum sync' first and "
                "'Course Catalogue' third. The page offers the question 'Who owns the Course "
                "Catalogue and which applications contribute to it?' as one to try, and the answer "
                "that comes back is about the integration — every identifier in it is real, so "
                "nothing marks it unverified, and the document never says which element the "
                "question was taken to be about. " + "; ".join(wrong) + ". Prefer an exact name "
                "match, or open the answer with the element that was chosen and why.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F13",
    group="F",
    title="A question the model cannot match is refused with the size of the repository and a way forward",
    feature="Ask · grounding",
    expected=(
        "A question whose words match nothing says so plainly, says how much the repository holds "
        "(from a tool result), says what to try instead, invents no element, draws no view — and "
        "the refusal can still be taken away as Markdown."
    ),
)
def test_a_question_that_matches_nothing(ui, record, finding):
    _open_ask(ui)
    _ask_afresh(ui, NONSENSE)
    body = _section_body(ui, "Answer")
    ui.check(
        "the answer says it could not match the question to an element",
        "could not match your question to an element" in body,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "it says how much the repository holds, counted rather than guessed",
        re.search(r"holds \d+ elements and \d+ relationships", body) is not None,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "it says what to try instead, so the reader is not left at a dead end",
        "try naming an element" in body and "ask with its id" in body,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "no identifier is invented for a question that matched nothing",
        re.search(r"\b[A-Z][A-Z0-9]{1,7}-[A-Za-z0-9][A-Za-z0-9-]+\b", body) is None,
        f"the answer reads {body[:200]!r}",
    )
    ui.check(
        "no elements table is shown, because no element was found",
        "Elements in this answer" not in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    ui.check(
        "no view is drawn, because there is nothing in the model to draw",
        ui.page.locator(VIEW_SRC).count() == 0,
    )
    ui.check(
        "nothing is marked unverified, because the answer names no identifier",
        "treat them as unverified" not in _document_text(ui),
    )
    called = _trace_calls(ui)
    ui.check(
        # The shape, not the count: how many words the reader tries before giving up is its
        # own business, and pinning the number here would fail on a better reader.
        "the trace shows the words it searched for and then the fallback to the metamodel",
        len(called) > 1 and set(called[:-1]) == {"search_elements"} and called[-1] == "list_types",
        f"the trace lists {called}",
    )
    first = ui.page.locator("#ask-trace .mantine-Accordion-control").first.inner_text()
    ui.check(
        "the first search shows the word it looked for",
        "blorptastic" in first,
        f"the first row reads {first!r}",
    )
    ui.shot("A question that matches nothing: the refusal, the size of the repository and what to try next")
    # This document carries no view, and the download callback holds a State on a view's position
    # store, so pressing a download is the moment that costs the reader the file.
    md, logged = _download_or_nothing(ui, "#ask-doc-md")
    ui.check(
        "the refusal can be taken away as Markdown, the way an answer with a view can",
        md is not None,
        "" if md is not None else "Download Markdown was pressed and produced no file at all",
    )
    ui.check(
        "pressing Download Markdown raises nothing in the browser",
        not logged,
        "" if not logged else f"the browser logged {'; '.join(logged)[:240]!r}",
    )
    if md is not None:
        text = md.read_text(encoding="utf-8")
        ui.check(
            "the refusal is what was taken away",
            "## Answer" in text and "could not match your question to an element" in text,
            f"the file opens {text[:160]!r}",
        )
        ui.check(
            "the exported Markdown lists no elements, because none were found",
            "## Elements in this answer" not in text,
        )
        ui.check(
            "the exported Markdown carries no diagram, because none was drawn",
            "```mermaid" not in text,
        )
        ui.check(
            "the exported Markdown still accounts for how it was answered",
            "## How this was answered" in text and "list_types()" in text,
            f"the file closes {text[-200:]!r}",
        )
    else:
        finding.append(
            _f(
                "F-10",
                "src/ea/ui/pages/ask.py · the download_doc callback, and both buttons in the document toolbar",
                "defect",
                "Neither download works on an answer that carries no view: the callback never runs",
                "download_doc holds a State on the position store of the first view "
                '({"id": "ask-view-0", "type": "mermaid-pos"}), and that store exists only inside a '
                "rendered view. An answer that names no element in the model — a question that "
                "matches nothing, or an identifier the model does not carry — has no view, so the "
                "component is not in the layout and Dash refuses to run the callback at all: the "
                "browser logs 'A nonexistent object was used in a `State` of a Dash callback' for "
                "that id and no request is made. Download Markdown is as dead as Download draw.io, "
                "although the Markdown is composed and already sitting in the document store, so "
                "the file could be written. This is the cause of the silence F-3 reports on the "
                "draw.io button. Take the positions with a pattern-matching ALL state, or keep a "
                "position store in the page whether or not a view was drawn.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F14",
    group="F",
    title="Ask with an empty question keeps the answer already on screen, and says why nothing happened",
    feature="Ask · the question box",
    expected=(
        "Pressing Ask with an empty box (or one holding only spaces) answers nothing and destroys "
        "nothing: the document already on screen stays, and the page either says why the question "
        "was not asked or does not offer Ask at all."
    ),
)
def test_ask_with_an_empty_question(ui, record, finding):
    _open_ask(ui)
    _ask_afresh(ui, IMPACT_Q)
    before = ui.page.locator(f"{DOCUMENT} h2").first.inner_text().strip()
    silent: list[str] = []
    for what, text in (("an empty box", ""), ("a box holding only spaces", "   ")):
        _type_question(ui, text)
        refused = ui.disabled("ask-button")
        if not refused:
            ui.click("ask-button")
            ui.page.wait_for_timeout(600)
            ui.settle()
        said = _refusal_shown(ui)
        if not (refused or said):
            silent.append(what)
        ui.check(
            f"Ask with {what} says why nothing happened, or cannot be pressed",
            refused or said,
            ""
            if (refused or said)
            else "the button is offered, pressing it does nothing and the page says nothing",
        )
        ui.check(
            f"Ask with {what} leaves exactly one answer on screen",
            ui.page.locator(DOCUMENT).count() == 1,
            f"{ui.page.locator(DOCUMENT).count()} documents",
        )
        title = ui.page.locator(f"{DOCUMENT} h2").first.inner_text().strip()
        ui.check(
            f"Ask with {what} does not replace the answer with an empty document",
            title == before,
            f"the document is now titled {title!r}",
        )
        kept = bool(ui.text("ask-trace"))
        ui.check(
            f"Ask with {what} leaves the trace of the answer that is on screen",
            kept,
            "" if kept else "the trace was cleared by a question that was never asked",
        )
    ui.shot("Ask pressed on an empty question box: the answer already on screen is untouched")
    # A question typed after the empty press must still be answered, or the no-op has cost the reader the page.
    _ask_afresh(ui, f"What is the impact of changing {CATALOGUE}?")
    ui.check(
        "a real question typed afterwards is still answered",
        _subject(ui)[1] == CATALOGUE,
        f"the answer is about {_subject(ui)}",
    )
    if silent:
        finding.append(
            _f(
                "F-8",
                "src/ea/ui/pages/ask.py · the ask callback and the Ask button",
                "usability",
                "Ask with an empty question does nothing, silently",
                "The callback returns no_update for a question that is empty or only whitespace, "
                "which is right — but the button stays enabled and pressing it gives the reader "
                "nothing at all: no message, no mark on the box, no disabled state with a reason "
                f"({', '.join(silent)}). It is the same silent no-op as the draw.io button on a "
                "document with no view. Disable Ask while the box is empty, or say that a question "
                "is needed.",
            )
        )


@pytest.mark.scenario(
    scenario_id="F15",
    group="F",
    title="A second question replaces the document and the trace under it",
    feature="Ask · the answer document",
    expected=(
        "Asking again leaves one document on the page — the new one, with its own title, subject, "
        "view and elements — and a trace of the calls that answered *this* question, not the one "
        "before it."
    ),
)
def test_a_second_question_replaces_the_first(ui, record):
    _open_ask(ui)
    _ask_afresh(ui, IMPACT_Q)
    ui.must("there is a first answer to replace", ui.page.locator(DOCUMENT).count() == 1)
    ui.check(
        "the first answer is about the element the first question named",
        _subject(ui)[1] == OFFERING,
        f"the first answer is about {_subject(ui)}",
    )
    second = f"What is the impact of changing {CATALOGUE}?"
    _ask_afresh(ui, second)
    ui.check(
        "one answer is on the page, not two",
        ui.page.locator(DOCUMENT).count() == 1,
        f"{ui.page.locator(DOCUMENT).count()} documents",
    )
    title = ui.page.locator(f"{DOCUMENT} h2").first.inner_text().strip()
    ui.check(
        "the document is titled with the second question",
        title == second.rstrip("?"),
        f"the title reads {title!r}",
    )
    name, ident = _subject(ui)
    ui.check(
        "the answer is about the element the second question named",
        (ident, name) == (CATALOGUE, "Course Catalogue"),
        f"the answer is about {name} [{ident}]",
    )
    titles = _section_titles(ui)
    ui.check(
        "the view is redrawn for the second question",
        "Impact of Course Catalogue" in titles,
        f"the sections are {titles}",
    )
    ui.check(
        "the first question's view is gone",
        "Impact of SRS_Course_Offering" not in titles,
        f"the sections are {titles}",
    )
    called = _trace_calls(ui)
    ui.check(
        "the trace is the second question's calls: the id was given, so nothing was searched for",
        called == ["get_element", "impact", "propose_view"],
        f"the trace lists {called}",
    )
    inputs = " ".join(
        t.strip() for t in ui.page.locator("#ask-trace .mantine-Accordion-control").all_text_contents()
    )
    ui.check(
        "the trace shows the second element, not the first",
        CATALOGUE in inputs and OFFERING not in inputs,
        f"the trace reads {inputs[:200]!r}",
    )
    ui.shot("A second question: one document, its own view, and a trace of the calls that answered it")


@pytest.mark.scenario(
    scenario_id="F16",
    group="F",
    title="'How this was answered' names every call, in order, with what it was called with",
    feature="Ask · tool trace",
    expected=(
        "The document's own account of how it was answered lists the same calls the trace under it "
        "lists, in the same order, each with the input it was made with — and the exported Markdown "
        "numbers them."
    ),
)
def test_how_this_was_answered(ui, record):
    _open_ask(ui)
    _ask_afresh(ui, IMPACT_Q)
    ui.must(
        "the document accounts for how it was answered",
        "How this was answered" in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    section = _section(ui, "How this was answered").first
    named = [c.strip() for c in section.locator("code").all_text_contents()]
    ui.check(
        "the account names every call, in the order they were made",
        named == ["search_elements", "get_element", "impact", "propose_view"],
        f"the account lists {named}",
    )
    ui.check(
        "the account matches the trace under the document",
        named == _trace_calls(ui),
        f"the account lists {named}, the trace lists {_trace_calls(ui)}",
    )
    body = section.inner_text()
    ui.check(
        "the search shows the text it searched for",
        "text='SRS_Course_Offering'" in body,
        f"the account reads {body[:240]!r}",
    )
    ui.check(
        "the element calls show the element they were made for",
        f"element_id='{OFFERING}'" in body,
        f"the account reads {body[:240]!r}",
    )
    ui.check(
        "the view the reader is looking at is shown as the call that asked for it",
        "title='Impact of SRS_Course_Offering'" in body,
        f"the account reads {body[-240:]!r}",
    )
    ui.shot("How this was answered: every call the answer rests on, with what it was called with")
    md = ui.download("ask-doc-md", ".md")
    text = md.read_text(encoding="utf-8")
    ui.check(
        "the exported Markdown numbers the calls in the same order",
        re.search(r"^1\. `search_elements\(", text, re.M) is not None
        and re.search(r"^4\. `propose_view\(", text, re.M) is not None,
        f"the account in the file reads {text[text.find('## How this was answered') :][:240]!r}",
    )


@pytest.mark.scenario(
    scenario_id="F17",
    group="F",
    title="The refusal for an identifier the model does not carry reads once, on screen and in the file",
    feature="Ask · grounding",
    expected=(
        "The answer for an unknown identifier says once that no element carries it, names the "
        "identifier once, and the exported Markdown carries the same refusal and repeats the "
        "warning that the identifier is unverified."
    ),
)
def test_unknown_identifier_refusal_reads_once(ui, record, finding):
    _open_ask(ui)
    _ask_afresh(ui, f"What is the impact of changing {GHOST}?")
    body = _section_body(ui, "Answer")
    doubled = body.lower().count("no element with id") > 1
    ui.check(
        "the refusal is said once, not twice",
        not doubled,
        f"the answer reads {body!r}",
    )
    ui.check(
        "the identifier is named once",
        body.count(GHOST) == 1,
        f"the answer reads {body!r}",
    )
    ui.shot("The refusal for an identifier the model does not carry, as the reader is given it")
    md, logged = _download_or_nothing(ui, "#ask-doc-md")
    ui.check(
        "the refusal can be taken away as Markdown (F-10: on a document with no view, it cannot)",
        md is not None,
        "" if md is not None else "Download Markdown was pressed and produced no file at all",
    )
    ui.check(
        "pressing Download Markdown raises nothing in the browser",
        not logged,
        "" if not logged else f"the browser logged {'; '.join(logged)[:240]!r}",
    )
    if md is not None:
        text = md.read_text(encoding="utf-8")
        answer = text[text.find("## Answer") : text.find("## Not found in the model")]
        ui.check(
            "the exported Markdown carries the same refusal",
            GHOST in answer and "no element with id" in answer.lower(),
            f"the exported answer reads {answer!r}",
        )
        ui.check(
            "the exported Markdown says once that no element carries it",
            answer.lower().count("no element with id") == 1,
            f"the exported answer reads {answer!r}",
        )
        ui.check(
            "the exported Markdown repeats the warning that the identifier is unverified",
            "## Not found in the model" in text
            and "treat them as unverified" in text
            and f"`{GHOST}`" in text,
            f"the file reads {text[:400]!r}",
        )
        ui.check(
            "the exported Markdown lists no elements and draws no diagram",
            "## Elements in this answer" not in text and "```mermaid" not in text,
        )
        ui.check(
            "the exported Markdown still says which call looked for it",
            "get_element(element_id='FX-GHOST-ENTITY')" in text,
            f"the file closes {text[-200:]!r}",
        )
    if doubled:
        finding.append(
            _f(
                "F-9",
                "src/ea/agent/tools.py · ToolBox.call, shown as the whole answer for an unknown identifier",
                "defect",
                "The unknown-identifier refusal is printed twice in one sentence",
                "NotFoundError already reads as a sentence — 'no element with id FX-GHOST-ENTITY' — "
                "because it is shown to people on the command line and beside a refused row. "
                "`ToolBox.call` catches it and wraps it in the same words again: "
                "`{'error': f'no element with id {exc}'}`. The stub makes that string the entire "
                "answer, so the reader is told 'no element with id no element with id "
                "FX-GHOST-ENTITY', on screen and in the exported Markdown. Pass the exception "
                "through as it stands, or name the identifier rather than the exception.",
            )
        )
    # Leave the page on something that works, so the next scenario does not open a stale refusal.
    ui.click("ask-reset")


@pytest.mark.scenario(
    scenario_id="F18",
    group="F",
    title="The reader can zoom and refit the generated view, and put it back",
    feature="Ask · generated view",
    expected=(
        "The view's controls do what they say: zoom in enlarges the diagram, zoom out returns it, "
        "fit brings it back to the window, and Reset layout redraws it from the model."
    ),
)
def test_the_view_can_be_arranged(ui, record):
    _open_ask(ui)
    _ask_afresh(ui, IMPACT_Q)
    ui.wait_mermaid()
    ui.must(
        "the diagram sits on a canvas the reader can move",
        ui.page.locator(f"{VIEW_SVG} .ea-mermaid-canvas").count() > 0,
    )
    fitted = _canvas_scale(ui)
    ui.must("the diagram was fitted to the window when it was drawn", fitted > 0, f"scale {fitted}")
    ui.click(_pm(id="ask-view-0", type="mermaid-zoom-in"))
    ui.page.wait_for_timeout(250)
    bigger = _canvas_scale(ui)
    ui.check(
        "zoom in makes the diagram bigger",
        bigger > fitted,
        f"the scale went from {fitted} to {bigger}",
    )
    ui.shot("The generated view zoomed in by the reader")
    ui.click(_pm(id="ask-view-0", type="mermaid-zoom-out"))
    ui.page.wait_for_timeout(250)
    back = _canvas_scale(ui)
    ui.check(
        "zoom out takes it back",
        abs(back - fitted) < max(0.01, fitted * 0.02),
        f"the scale went from {bigger} to {back}, expected about {fitted}",
    )
    ui.click(_pm(id="ask-view-0", type="mermaid-zoom-in"))
    ui.page.wait_for_timeout(250)
    ui.click(_pm(id="ask-view-0", type="mermaid-fit"))
    ui.page.wait_for_timeout(250)
    refitted = _canvas_scale(ui)
    ui.check(
        "fit to the window brings it back to the window",
        abs(refitted - fitted) < max(0.01, fitted * 0.02),
        f"the scale is {refitted}, expected about {fitted}",
    )
    reset = ui.page.locator(_pm(id="ask-view-0", type="mermaid-reset"))
    ui.check("the view offers Reset layout", reset.count() > 0)
    if reset.count():
        ui.click(_pm(id="ask-view-0", type="mermaid-reset"))
        ui.wait_mermaid()
        drawn = ui.page.locator(f"{VIEW_SVG} svg").first.text_content() or ""
        ui.check(
            "Reset layout redraws the same diagram from the model",
            f"[{OFFERING}]" in drawn,
            f"the diagram reads {drawn[:200]!r}",
        )
        ui.check(
            "and the answer it belongs to is still there",
            ui.page.locator(DOCUMENT).count() == 1 and "Answer" in _section_titles(ui),
            f"the sections are {_section_titles(ui)}",
        )
    ui.shot("The generated view after fit and Reset layout: back where it was drawn")


@pytest.mark.scenario(
    scenario_id="F19",
    group="F",
    title="A Reader may ask, and take the answer away",
    feature="Ask · roles",
    expected=(
        "Asking and downloading are what the lowest role may do, so a Reader gets the same "
        "document — the answer, the elements table linking to each element, and the Markdown "
        "download — and is refused nothing."
    ),
)
def test_a_reader_may_ask(ui, record):
    _open_ask(ui)
    ui.persona("Reader")
    ui.check(
        "the header says the reader is a Reader",
        "reader" in ui.role_badge().lower(),
        f"the badge reads {ui.role_badge()!r}",
    )
    ui.must("the Reader is still offered the question box", _textarea(ui).count() > 0)
    ui.check("the Reader is offered Ask", ui.visible("ask-button") and not ui.disabled("ask-button"))
    _ask_afresh(ui, IMPACT_Q)
    name, ident = _subject(ui)
    ui.check(
        "the Reader's question is answered about the element it named",
        ident == OFFERING,
        f"the answer is about {name} [{ident}]",
    )
    ui.check(
        "the Reader is given the elements table too",
        "Elements in this answer" in _section_titles(ui),
        f"the sections are {_section_titles(ui)}",
    )
    row = (
        _section(ui, "Elements in this answer")
        .first.locator("tbody tr", has=ui.page.locator(f"code:text-is('{OFFERING}')"))
        .first
    )
    link = row.locator("a").first
    ui.check(
        "and the elements a Reader may open still link to their own pages",
        (link.get_attribute("href") if link.count() else "") == f"/element/{OFFERING}",
        f"the href is {(link.get_attribute('href') if link.count() else '')!r}",
    )
    ui.check(
        "nothing tells the Reader they are not allowed to ask",
        "not permitted" not in ui.body().lower() and "forbidden" not in ui.body().lower(),
    )
    ui.shot("The Ask page as a Reader: the same document, answered and readable")
    md = ui.download("ask-doc-md", ".md")
    text = md.read_text(encoding="utf-8")
    ui.check(
        "a Reader may take the answer away as Markdown",
        text.startswith(f"# {IMPACT_Q.rstrip('?')}") and OFFERING in text,
        f"the file opens {text[:120]!r}",
    )
    ui.persona("Admin")


@pytest.mark.scenario(
    scenario_id="F20",
    group="F",
    title="The chip a reader points at is the thing that takes the click",
    feature="Ask · example questions",
    expected=(
        "The badge a reader sees is what carries the pointer cursor, clicking that badge — not "
        "some wrapper around it — puts its question in the box, and the question it leaves there "
        "can then be asked."
    ),
)
def test_the_visible_chip_takes_the_click(ui, record):
    _open_ask(ui)
    for i, question in enumerate(EXAMPLES):
        chip = _visible_chip(ui, i)
        ui.check(
            f"chip {i + 1} invites the click a reader is about to make",
            chip.evaluate("el => getComputedStyle(el).cursor") == "pointer",
            f"the cursor over it is {chip.evaluate('el => getComputedStyle(el).cursor')!r}",
        )
        ui.check(
            f"chip {i + 1} shows the question it will put in the box",
            (chip.text_content() or "").strip() == question,
            f"it reads {(chip.text_content() or '').strip()!r}",
        )
        # Start from something else each time, so a chip that does nothing is visible.
        _type_question(ui, "placeholder")
        chip.click()
        ui.page.wait_for_timeout(200)
        ui.settle()
        got = _question(ui)
        # F-1 already records a chip that reports no click; this reads the chip a reader points at.
        ui.check(
            f"clicking the chip a reader sees puts question {i + 1} in the box",
            got == question,
            f"the box holds {got!r}, expected {question!r}",
        )
    ui.shot("The question box after clicking the last chip: it holds the question that chip offers")
    if _question(ui) == EXAMPLES[-1]:
        ui.click("ask-button")
        ui.page.wait_for_selector(DOCUMENT, timeout=30_000)
        ui.settle()
        title = ui.page.locator(f"{DOCUMENT} h2").first.inner_text().strip()
        ui.check(
            "and the question a chip left in the box can then be asked",
            title == EXAMPLES[-1].rstrip("?"),
            f"the document is titled {title!r}",
        )
        ui.shot("A question taken from a chip and asked: the document it comes back as")
