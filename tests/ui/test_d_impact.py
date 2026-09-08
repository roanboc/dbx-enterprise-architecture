"""Group D — Impact: the closure both ways, the completeness footer, the graph and the view.

The page answers one question — what a change to an element would touch — so every scenario
here reads the answer the way an architect would: the sentence at the top, the honest footer
under it, the two tables with their hops and the relationship chain that got there, the
network graph, and the generated architecture view with the two files it can be taken away in.

The sample model gives the group two reliable subjects. `DE-SRS-COURSE` (SRS_Course) is
depended on by four elements at one hop and by fourteen more within three, and depends on
nothing itself, so it proves both the filled table and the empty one. `INT-CMS-SRS` has real
closure in both directions and is an Integration, a type the model declares relationship
types for that nothing yet uses, so it proves the completeness footer when it has something
to warn about.

Counts are never asserted absolutely: the round shares one database and an earlier group may
have added to it, so every assertion is a row that must be there, a chain that must read a
certain way, or a number that must have grown.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.gui

RESULT = "imp-result"
UPSTREAM = "Depends on this (upstream)"
DOWNSTREAM = "This depends on (downstream)"
MERMAID_SVG = '[id=\'{"id":"imp-view","type":"mermaid-svg"}\']'
GRAPH_FRAME = ".ea-graph-frame"

COURSE = "DE-SRS-COURSE"  # SRS_Course — four elements at one hop, nothing downstream
SYNC = "INT-CMS-SRS"  # CMS to SRS curriculum sync — closure both ways, an incomplete type


# --------------------------------------------------------------------------- the controls


def _input(ui, component_id: str):
    """A Mantine control puts its id on the wrapper or on the field; take whichever is there."""
    return ui.page.locator(f"#{component_id} input, input#{component_id}").first


def _depth(ui) -> str:
    return _input(ui, "imp-depth").input_value()


def _set_depth(ui, value: int) -> None:
    box = _input(ui, "imp-depth")
    box.click()
    box.fill(str(value))
    ui.page.wait_for_timeout(200)
    ui.settle()


def _selected(ui) -> str:
    return _input(ui, "imp-element").input_value()


def _type_in_selector(ui, text: str) -> None:
    """Open the element selector and type, which asks the server for the ranked matches."""
    box = _input(ui, "imp-element")
    box.click()
    box.fill("")
    ui.page.keyboard.type(text, delay=25)
    ui.page.wait_for_timeout(500)  # the search callback runs per keystroke
    ui.settle()


def _options(ui) -> list[str]:
    return [t.strip() for t in ui.page.locator("[role='option']").all_inner_texts()]


def _pick(ui, text: str, element_id: str) -> bool:
    """Search the selector and choose the option for one element; choosing runs the impact."""
    _type_in_selector(ui, text)
    option = ui.page.locator("[role='option']").filter(has_text=f"[{element_id}]")
    if not option.count():
        ui.page.keyboard.press("Escape")
        return False
    option.first.click()
    ui.settle()
    return True


def _run(ui) -> None:
    ui.click("imp-run")


# ----------------------------------------------------------------------------- the answer


def _summary(ui) -> str:
    """The sentence and the footer at the top of the result, as one block of text."""
    return ui.text(RESULT)


def _sentence(ui) -> str:
    match = re.search(r"\d+ elements depend on it within \d+ hops; it depends on \d+\..*", _summary(ui))
    return match.group(0) if match else ""


def _panel(ui, heading: str):
    return ui.page.locator(f"#{RESULT} .mantine-Paper-root").filter(has_text=heading).last


def _headers(ui, heading: str) -> list[str]:
    return [h.strip() for h in _panel(ui, heading).locator("thead th").all_inner_texts()]


def _rows(ui, heading: str) -> list[list[str]]:
    """One list per row of a closure table: [hops, element, type, via]."""
    panel = _panel(ui, heading)
    if not panel.count():
        return []
    body = panel.locator("tbody tr")
    return [[c.strip() for c in body.nth(i).locator("td").all_inner_texts()] for i in range(body.count())]


def _row_for(rows: list[list[str]], name: str) -> list[str]:
    return next((r for r in rows if len(r) > 1 and r[1] == name), [])


def _alert(ui, fragment: str):
    return ui.page.locator(f"#{RESULT} .mantine-Alert-root").filter(has_text=fragment).first


def _alert_colour(ui, fragment: str) -> str:
    """A Mantine alert paints itself from a CSS variable that names the colour it was given."""
    return ui.page.evaluate(
        """(text) => {
            const found = Array.from(document.querySelectorAll('#imp-result .mantine-Alert-root'))
                .find(el => (el.textContent || '').includes(text));
            if (!found) { return ''; }
            const style = getComputedStyle(found);
            return (style.getPropertyValue('--alert-bg') || style.backgroundColor || '').trim();
        }""",
        fragment,
    )


# ------------------------------------------------------------------------------ the graph


def _graph_nodes(ui) -> list[str]:
    return ui.page.evaluate(
        """() => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            return cy ? cy.nodes().map(n => n.data('element_id')).filter(Boolean) : [];
        }"""
    )


def _node_point(ui, element_id: str):
    return ui.page.evaluate(
        """(eid) => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            if (!cy) { return null; }
            const hit = cy.nodes().filter(n => n.data('element_id') === eid);
            if (!hit.length) { return null; }
            const p = hit[0].renderedPosition();
            const box = document.getElementById(JSON.stringify({id: 'imp', type: 'gp-cy'}))
                .getBoundingClientRect();
            return {x: box.left + p.x, y: box.top + p.y, height: window.innerHeight};
        }""",
        element_id,
    )


def _tap_node(ui, element_id: str) -> bool:
    """Tap a node the way a reader does — a click on the canvas where the node is drawn."""
    ui.page.locator(GRAPH_FRAME).first.scroll_into_view_if_needed()
    ui.page.wait_for_timeout(300)
    point = _node_point(ui, element_id)
    if not point:
        return False
    if not (0 < point["y"] < point["height"]):
        ui.page.evaluate("dy => window.scrollBy(0, dy)", point["y"] - point["height"] / 2)
        ui.page.wait_for_timeout(300)
        point = _node_point(ui, element_id)
        if not point or not (0 < point["y"] < point["height"]):
            return False
    ui.page.mouse.click(point["x"], point["y"])
    ui.settle()
    return True


# ------------------------------------------------------------------------------ scenarios


@pytest.mark.scenario(
    scenario_id="D01",
    group="D",
    title="Impact opens with its question, its controls and nothing computed",
    feature="Impact · the page",
    expected="The page names what it answers, offers an element selector, a depth of 3 and Run, "
    "and shows an empty graph and an empty architecture view until an element is chosen.",
)
def test_page_opens(ui, record):
    ui.goto("/impact")
    heading = ui.page.locator("#page h2").first
    ui.must("the page is Impact", heading.count() and heading.inner_text().strip() == "Impact")
    subtitle = ui.text("#page .mantine-Group-root")
    for word in ("upstream", "downstream", "depth"):
        ui.check(f"the subtitle says what {word} means here", word in subtitle, subtitle[:160])

    ui.check("the element selector is on the page", ui.visible("imp-element"))
    ui.check(
        "it invites a search",
        _input(ui, "imp-element").get_attribute("placeholder") == "Search an element…",
        _input(ui, "imp-element").get_attribute("placeholder") or "",
    )
    ui.check("nothing is chosen yet", _selected(ui) == "", _selected(ui))
    ui.check("the depth starts at 3", _depth(ui) == "3", _depth(ui))
    ui.check("Run is offered", ui.text("imp-run") == "Run", ui.text("imp-run"))
    ui.check("no answer is shown before one is asked for", ui.text(RESULT) == "", ui.text(RESULT))

    ui.check("the network graph panel is on the page", ui.visible(GRAPH_FRAME))
    body = ui.body()
    ui.check("the generated view has its own section", "Architecture view" in body)
    ui.check("both downloads are offered", ui.visible("imp-view-md") and ui.visible("imp-view-drawio"))
    ui.shot("Impact before anything is asked: the selector, the depth, Run, and an empty view")


@pytest.mark.scenario(
    scenario_id="D02",
    group="D",
    title="Searching the selector finds an element and running it answers straight away",
    feature="Impact · the element selector",
    expected="Typing part of a name lists matching elements as 'name [id] · type', and choosing "
    "one runs the impact without pressing Run.",
)
def test_selector_search(ui, record):
    ui.goto("/impact")
    _type_in_selector(ui, "SRS_Course")
    options = _options(ui)
    ui.must("the search offers matches", bool(options), f"{len(options)} options")
    ui.check(
        "an option carries the name, the identifier and the type",
        any(f"[{COURSE}]" in o and "Data Entity" in o and "SRS_Course" in o for o in options),
        " | ".join(options[:4]),
    )
    ui.check(
        "the search narrowed to what was typed",
        all("SRS_Course" in o or "srs_course" in o.lower() for o in options),
        " | ".join(options[:6]),
    )
    ui.shot("The element selector lists the matches for what was typed")

    option = ui.page.locator("[role='option']").filter(has_text=f"[{COURSE}]")
    ui.must("the wanted element is among them", option.count() > 0)
    option.first.click()
    ui.settle()
    ui.check(
        "the selector now holds it", COURSE in _selected(ui) or "SRS_Course" in _selected(ui), _selected(ui)
    )
    ui.check(
        "choosing an element answers without pressing Run",
        "elements depend on it within" in _summary(ui),
        _summary(ui)[:160].replace("\n", " · "),
    )
    ui.shot("Choosing an element in the selector runs its impact at once")


@pytest.mark.scenario(
    scenario_id="D03",
    group="D",
    title="Run reports the blast radius in one sentence and says how complete it is",
    feature="Impact · the summary and the completeness footer",
    expected="The summary names the element, counts both directions at the depth asked for, breaks "
    "the count down by type, links to the element, and a footer says how many declared "
    "relationship types of that element's type have any content.",
)
def test_summary_and_completeness(ui, record):
    ui.goto("/impact")
    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    _run(ui)

    summary = _summary(ui)
    ui.check("the element is named", "SRS_Course" in summary, summary[:120])
    ui.check("its type is badged", "Data Entity" in summary, summary[:160])
    ui.check(
        "the element can be opened from here",
        ui.page.locator(f"#{RESULT} a[href='/element/{COURSE}']").count() > 0,
    )
    sentence = _sentence(ui)
    ui.must("the summary sentence is there", bool(sentence), summary[:200].replace("\n", " · "))
    ui.check("it counts at the depth that was asked for", "within 3 hops" in sentence, sentence)
    ui.check("it breaks the answer down by type", "By type:" in sentence, sentence)
    counted = re.search(r"(\d+) elements depend on it within \d+ hops; it depends on (\d+)", sentence)
    ui.must("both directions are counted", counted is not None, sentence)
    ui.check(
        "the upstream count is the number of rows in the upstream table",
        int(counted.group(1)) == len(_rows(ui, UPSTREAM)),
        f"sentence {counted.group(1)}, table {len(_rows(ui, UPSTREAM))}",
    )

    footer = _alert(ui, "Completeness:")
    ui.must("the completeness footer is shown", footer.count() > 0, summary[-200:])
    text = footer.inner_text().strip()
    ui.check("it is headed as a caveat on the answer", "How complete is this answer?" in text, text[:80])
    ui.check(
        "it counts the relationship types declared for this element's type",
        re.search(r"Completeness: \d+ of \d+ relationship types declared for Data Entity", text) is not None,
        text.replace("\n", " · ")[:200],
    )
    complete = "Every declared relationship type has content." in text
    colour = _alert_colour(ui, "Completeness:")
    ui.check(
        "a complete answer says so in green, an incomplete one names what is missing",
        ("green" in colour) if complete else ("yellow" in colour and "No instances yet for:" in text),
        f"{colour} · {text.replace(chr(10), ' · ')[:160]}",
    )
    ui.shot("The impact summary sentence and the completeness footer under it")


@pytest.mark.scenario(
    scenario_id="D04",
    group="D",
    title="The upstream table gives the hops and the relationships they went through",
    feature="Impact · the closure tables",
    expected="Everything that depends on SRS_Course is listed with its hop count, its type and the "
    "chain of relationship names it was reached by; the downstream table says 'Nothing.' "
    "because SRS_Course points at nothing.",
)
def test_upstream_table(ui, record):
    ui.goto("/impact")
    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    _set_depth(ui, 3)
    _run(ui)

    ui.check("both directions have a panel", _panel(ui, UPSTREAM).count() and _panel(ui, DOWNSTREAM).count())
    ui.check(
        "the upstream table is headed hops, element, type and via",
        _headers(ui, UPSTREAM) == ["hops", "element", "type", "via"],
        str(_headers(ui, UPSTREAM)),
    )
    rows = _rows(ui, UPSTREAM)
    ui.must("the upstream table has rows", bool(rows), f"{len(rows)} rows")

    curriculum = _row_for(rows, "Curriculum")
    ui.must("the data component that encapsulates it is listed", bool(curriculum), str(rows[:3]))
    ui.check("it is one hop away", curriculum[0] == "1", curriculum[0])
    ui.check("its type is named", curriculum[2] == "Logical Data Component", curriculum[2])
    ui.check("the relationship it was reached by is named", curriculum[3] == "encapsulates", curriculum[3])

    srs = _row_for(rows, "Student Records System (SRS)")
    ui.check("the system that processes it is listed one hop away", srs[:1] == ["1"], str(srs))
    ui.check(
        "nothing is listed beyond the depth asked for",
        all(r[0].isdigit() and int(r[0]) <= 3 for r in rows),
        str(sorted({r[0] for r in rows})),
    )
    chained = [r for r in rows if "›" in r[3]]
    ui.check("a row further out shows the whole chain it was reached by", bool(chained), str(rows[-1]))
    if chained:
        deep = chained[-1]
        ui.check(
            "the chain has one relationship per hop",
            len(deep[3].split("›")) == int(deep[0]),
            f"{deep[0]} hops, via {deep[3]}",
        )

    ui.check(
        "an element that points at nothing says so rather than showing an empty table",
        "Nothing." in _panel(ui, DOWNSTREAM).inner_text(),
        _panel(ui, DOWNSTREAM).inner_text().strip()[:120],
    )
    ui.shot("Upstream closure with hops and the relationship chain; nothing downstream")


@pytest.mark.scenario(
    scenario_id="D05",
    group="D",
    title="The depth control decides how far the closure runs",
    feature="Impact · depth",
    expected="At depth 1 only immediate neighbours are listed; raising the depth to 3 and pressing "
    "Run brings back more, none of it further than three hops.",
)
def test_depth_control(ui, record):
    ui.goto("/impact")
    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    _set_depth(ui, 1)
    _run(ui)
    near = _rows(ui, UPSTREAM)
    ui.must("depth 1 returns the immediate neighbours", bool(near), f"{len(near)} rows")
    ui.check("all of them are one hop away", {r[0] for r in near} == {"1"}, str(sorted({r[0] for r in near})))
    ui.check("the sentence says the depth it used", "within 1 hops" in _sentence(ui), _sentence(ui))
    ui.check(
        "a one-hop row went through exactly one relationship",
        all("›" not in r[3] for r in near),
        str([r[3] for r in near]),
    )
    ui.shot("Depth 1: only what depends on the element directly")

    _set_depth(ui, 3)
    ui.check(
        "changing the depth alone does not re-answer",
        "within 1 hops" in _sentence(ui),
        _sentence(ui),
    )
    _run(ui)
    far = _rows(ui, UPSTREAM)
    ui.check("depth 3 reaches further than depth 1", len(far) > len(near), f"{len(near)} then {len(far)}")
    ui.check("the sentence says the new depth", "within 3 hops" in _sentence(ui), _sentence(ui))
    ui.check(
        "and nothing further out than three hops came back",
        all(int(r[0]) <= 3 for r in far),
        str(sorted({r[0] for r in far})),
    )
    ui.check(
        "the work package that touches the chain is reached at three hops",
        _row_for(far, "CMS upgrade")[:1] == ["3"] if _row_for(far, "CMS upgrade") else False,
        str(_row_for(far, "CMS upgrade")),
    )
    ui.shot("Depth 3: the same element reaches three hops of dependents")


@pytest.mark.scenario(
    scenario_id="D06",
    group="D",
    title="An element with closure both ways fills both tables, and the footer warns what is missing",
    feature="Impact · both directions",
    expected="The integration lists what depends on it and what it depends on, each with hops and a "
    "relationship chain, and the completeness footer names the relationship types its type "
    "declares that nothing in the repository uses.",
)
def test_both_directions(ui, record):
    ui.goto("/impact")
    ui.must("the integration was found in the selector", _pick(ui, SYNC, SYNC))
    _set_depth(ui, 2)
    _run(ui)

    up, down = _rows(ui, UPSTREAM), _rows(ui, DOWNSTREAM)
    ui.must("both tables have rows", bool(up) and bool(down), f"{len(up)} upstream, {len(down)} downstream")
    ui.check(
        "the downstream table is headed the same way",
        _headers(ui, DOWNSTREAM) == ["hops", "element", "type", "via"],
        str(_headers(ui, DOWNSTREAM)),
    )
    platform = _row_for(up, "Integration platform")
    ui.check("the platform that realises it depends on it", platform[:1] == ["1"], str(platform))
    ui.check(
        "and the relationship is named", platform[3:] == ["realises"] if platform else False, str(platform)
    )

    curriculum = _row_for(down, "Curriculum")
    ui.check("it processes the curriculum data component", curriculum[:1] == ["1"], str(curriculum))
    course = _row_for(down, "SRS_Course")
    ui.check("and reaches the course entity through it at two hops", course[:1] == ["2"], str(course))
    ui.check(
        "the chain names both relationships",
        course[3] == "processes › encapsulates" if course else False,
        str(course),
    )

    footer = _alert(ui, "Completeness:")
    ui.must("the completeness footer is shown", footer.count() > 0)
    text = footer.inner_text().strip()
    ui.check(
        "it counts the types declared for an Integration",
        "relationship types declared for Integration" in text,
        text.replace("\n", " · ")[:160],
    )
    ui.check(
        "it names the declared relationship types nothing uses yet",
        "No instances yet for:" in text,
        text.replace("\n", " · ")[:200],
    )
    ui.check(
        "an incomplete answer is warned in yellow",
        "yellow" in _alert_colour(ui, "Completeness:"),
        _alert_colour(ui, "Completeness:"),
    )
    ui.shot("Both closure tables filled, with a footer naming what the model has no content for")


@pytest.mark.scenario(
    scenario_id="D07",
    group="D",
    title="The graph draws the neighbourhood and a tap on a node opens that element",
    feature="Impact · the network graph",
    expected="The graph holds the element and its neighbours grouped by layer, and tapping a "
    "neighbour navigates to that element's page.",
)
def test_graph_and_tap(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    ui.wait_graph()
    nodes = _graph_nodes(ui)
    ui.must("the graph drew the neighbourhood", bool(nodes), f"{len(nodes)} nodes")
    ui.check("the element itself is in it", COURSE in nodes, str(sorted(nodes)[:8]))
    for neighbour in ("LDC-CURR", "PAC-SRS", "PTC-RDBMS"):
        ui.check(f"{neighbour} is drawn as a neighbour", neighbour in nodes, str(sorted(nodes)))
    ui.check(
        "the nodes are boxed by layer",
        ui.page.evaluate(
            "() => { const cy = window.eaGraph.instance('imp');"
            " return cy ? cy.nodes().filter(n => n.hasClass('group')).length : 0; }"
        )
        > 1,
    )
    ui.shot("The impact neighbourhood as a network graph, grouped by layer")

    ui.must("the neighbour node could be tapped", _tap_node(ui, "LDC-CURR"))
    ui.page.wait_for_timeout(500)
    ui.settle()
    ui.check("the tap opened that element", ui.page.url.endswith("/element/LDC-CURR"), ui.page.url)
    heading = ui.page.locator("#page h2").first
    ui.check(
        "and the element page is the one tapped",
        heading.count() and heading.inner_text().strip() == "Curriculum",
        heading.inner_text().strip() if heading.count() else "no heading",
    )
    ui.shot("Tapping a node in the impact graph opens that element")


@pytest.mark.scenario(
    scenario_id="D08",
    group="D",
    title="The generated architecture view renders and both downloads produce the file they name",
    feature="Impact · the generated view",
    expected="The impact is drawn as a layered architecture diagram in which every shape carries "
    "its element identifier, and Download Markdown and Download draw.io each return a file "
    "named for the element that holds the same view.",
)
def test_view_and_downloads(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    ui.wait_mermaid()
    svg = ui.page.locator(f"{MERMAID_SVG} svg")
    ui.must("the view was drawn", svg.count() > 0)
    drawn = ui.text(MERMAID_SVG)
    ui.check("every shape carries an element identifier", f"[{COURSE}]" in drawn, drawn[:160])
    ui.check("the element it is about is drawn", "SRS_Course" in drawn, drawn[:160])
    ui.check(
        "the shapes are stacked in labelled layers",
        sum(word in drawn for word in ("Application", "Technology", "Business")) >= 2,
        drawn[:200].replace("\n", " · "),
    )
    ui.shot("The impact as a generated architecture view, every shape carrying its identifier")

    md = ui.download("imp-view-md", ".md")
    ui.check("the file is named for the element", md.name == f"{COURSE}-impact.md", md.name)
    text = md.read_text(encoding="utf-8")
    ui.check("it is titled as the impact of the element", "## Impact of SRS_Course" in text, text[:80])
    ui.check("it carries the diagram as Mermaid", "```mermaid" in text, text[:200])
    ui.check("and the table of elements it shows", f"| `{COURSE}` |" in text, text[-400:])

    drawio = ui.download("imp-view-drawio", ".drawio")
    ui.check(
        "the draw.io file is named for the element", drawio.name == f"{COURSE}-impact.drawio", drawio.name
    )
    diagram = drawio.read_text(encoding="utf-8")
    ui.check("it is a draw.io file", diagram.lstrip().startswith("<mxfile"), diagram[:60])
    ui.check("and it carries the element identifiers too", COURSE in diagram, diagram[:200])


@pytest.mark.scenario(
    scenario_id="D09",
    group="D",
    title="A link into the page with an element in it answers on arrival",
    feature="Impact · deep link",
    expected="Opening /impact?element=DE-SRS-COURSE preselects the element and shows its impact, "
    "its graph and its view without anything being pressed.",
)
def test_preselected_element(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    ui.check(
        "the selector arrives holding the element",
        "SRS_Course" in _selected(ui) or COURSE in _selected(ui),
        _selected(ui),
    )
    ui.check("the depth is the default three", _depth(ui) == "3", _depth(ui))
    ui.check(
        "the impact is answered on arrival",
        "elements depend on it within 3 hops" in _summary(ui),
        _summary(ui)[:160].replace("\n", " · "),
    )
    ui.check("the upstream table came with it", bool(_rows(ui, UPSTREAM)))
    ui.check("so did the completeness footer", _alert(ui, "Completeness:").count() > 0)
    ui.wait_graph()
    ui.check("the graph was drawn for it", COURSE in _graph_nodes(ui), str(_graph_nodes(ui)[:6]))
    ui.wait_mermaid()
    ui.check("and so was the architecture view", f"[{COURSE}]" in ui.text(MERMAID_SVG))
    ui.shot("A deep link to an element answers its impact on arrival")


@pytest.mark.scenario(
    scenario_id="D10",
    group="D",
    title="An element id nothing matches is refused in red",
    feature="Impact · unknown element",
    expected="Asking for an element the repository does not hold says 'Unknown element.' in red "
    "rather than an empty answer, whether it was typed or arrived in the address.",
)
def test_unknown_element(ui, record):
    unknown = "D-NO-SUCH-ELEMENT"
    ui.goto(f"/impact?element={unknown}")
    arrival = _summary(ui)
    # A deep link to an element that does not exist is ignored on arrival: the page renders
    # blank instead of saying the id is unknown, which the Run button then does say.
    ui.check(
        "arriving with an unknown element says the id is unknown",
        "Unknown element." in arrival,
        f"the result area read {arrival[:80]!r}",
    )
    ui.shot("Arriving at Impact with an element id nothing matches")

    _run(ui)
    result = _summary(ui)
    ui.must("running an unknown element refuses it", "Unknown element." in result, result[:120])
    ui.check(
        "the refusal is in red",
        "red" in _alert_colour(ui, "Unknown element."),
        _alert_colour(ui, "Unknown element."),
    )
    ui.check("no closure table is shown for it", not _rows(ui, UPSTREAM) and not _rows(ui, DOWNSTREAM))
    ui.shot("Running an element id nothing matches is refused in red")
