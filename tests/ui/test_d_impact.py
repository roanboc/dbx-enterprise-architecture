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
from tests.ui.evidence import Finding

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
    """Only the open dropdown's options: the header's own selects keep theirs in the page."""
    return [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]


def _pick(ui, text: str, element_id: str) -> bool:
    """Search the selector and choose the option for one element; choosing runs the impact."""
    _type_in_selector(ui, text)
    option = ui.page.locator("[role='option']:visible").filter(has_text=f"[{element_id}]")
    if not option.count():
        ui.page.keyboard.press("Escape")
        return False
    option.first.click()
    ui.settle()
    return True


def _run(ui) -> None:
    ui.click("imp-run")


def _leave_depth(ui) -> str:
    """Leave the depth box, which is when Mantine pulls what was typed back into its range."""
    ui.page.keyboard.press("Tab")
    ui.page.wait_for_timeout(300)
    ui.settle()
    return _depth(ui)


def _dropdown(ui) -> str:
    """What the open selector is showing — its options, or the message standing in for them."""
    box = ui.page.locator(".mantine-Select-dropdown:visible, .mantine-Combobox-dropdown:visible").first
    return box.inner_text().strip() if box.count() else ""


def _no_download(ui, button: str, seconds: float = 3.0) -> bool:
    """True when pressing a download button produces no file at all."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        with ui.page.expect_download(timeout=seconds * 1000):
            ui.page.locator(f"#{button}").first.click()
    except PlaywrightTimeout:
        ui.settle()
        return True
    ui.settle()
    return False


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
    """What colour an alert was given, read back from the background Mantine paints it with."""
    painted = ui.page.evaluate(
        """(text) => {
            const found = Array.from(document.querySelectorAll('#imp-result .mantine-Alert-root'))
                .find(el => (el.textContent || '').includes(text));
            if (!found) { return ''; }
            const style = getComputedStyle(found);
            return (style.getPropertyValue('--alert-bg') || style.backgroundColor || '').trim();
        }""",
        fragment,
    )
    return _colour_name(painted)


def _colour_name(painted: str) -> str:
    """`rgba(64, 192, 87, 0.1)` is Mantine's green; name the channels rather than guess at them."""
    for name in ("green", "yellow", "red", "blue"):
        if name in painted:
            return name
    channels = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", painted)
    if not channels:
        return painted or "no colour"
    r, g, b = (int(channels.group(i)) for i in (1, 2, 3))
    if g > r and g > b:
        return f"green ({painted})"
    if r > 200 and g > 140 and b < 100:
        return f"yellow ({painted})"
    if r > 150 and r - g > 60 and r - b > 60:
        return f"red ({painted})"
    return painted


def _badge(ui) -> str:
    """The type badge beside the element's name in the summary (CSS upper-cases what it reads)."""
    badge = ui.page.locator(f"#{RESULT} .mantine-Paper-root").first.locator(".mantine-Badge-root").first
    return badge.inner_text().strip() if badge.count() else ""


def _by_type(ui) -> dict[str, int]:
    """The `By type:` breakdown in the summary sentence, as {type name: how many}."""
    parts = _sentence(ui).split("By type:", 1)
    if len(parts) < 2:
        return {}
    out: dict[str, int] = {}
    for entry in parts[1].split(","):
        match = re.match(r"\s*(.+?)\s+(\d+)\s*$", entry)
        if match:
            out[match.group(1).lower()] = int(match.group(2))
    return out


def _types_in_tables(ui) -> dict[str, int]:
    """The same count taken from the type column of both closure tables."""
    out: dict[str, int] = {}
    for row in _rows(ui, UPSTREAM) + _rows(ui, DOWNSTREAM):
        if len(row) > 2:
            out[row[2].lower()] = out.get(row[2].lower(), 0) + 1
    return out


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


def _graph_centre(ui) -> list[str]:
    return ui.page.evaluate(
        """() => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            return cy ? cy.nodes('.centre').map(n => n.data('element_id')) : [];
        }"""
    )


def _graph_groups(ui) -> list[str]:
    return ui.page.evaluate(
        """() => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            return cy ? cy.nodes('.group').map(n => n.data('label')) : [];
        }"""
    )


def _selected_nodes(ui) -> list[str]:
    return ui.page.evaluate(
        """() => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            return cy ? cy.nodes(':selected').map(n => n.data('id')) : [];
        }"""
    )


def _wait_for_graph(ui, previous: list[str]) -> list[str]:
    """Wait until the graph holds a different set of elements than it did, then read it back."""
    ui.page.wait_for_function(
        """(before) => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            if (!cy) { return false; }
            const now = cy.nodes().map(n => n.data('element_id')).filter(Boolean).sort().join('|');
            return Boolean(now) && now !== before;
        }""",
        arg="|".join(sorted(previous)),
        timeout=20_000,
    )
    ui.page.wait_for_timeout(300)
    return _graph_nodes(ui)


def _group_point(ui, label: str):
    """A point just inside the top of a group box, above the nodes it holds."""
    return ui.page.evaluate(
        """(label) => {
            const cy = window.eaGraph && window.eaGraph.instance('imp');
            if (!cy) { return null; }
            const hit = cy.nodes('.group').filter(n => n.data('label') === label);
            if (!hit.length) { return null; }
            const bb = hit[0].renderedBoundingBox({includeLabels: false});
            const box = document.getElementById(JSON.stringify({id: 'imp', type: 'gp-cy'}))
                .getBoundingClientRect();
            return {x: box.left + (bb.x1 + bb.x2) / 2, y: box.top + bb.y1 + 10, height: window.innerHeight};
        }""",
        label,
    )


def _tap_group(ui, label: str) -> bool:
    """Tap the box a layer's elements sit in, the way a reader would miss a node and hit the box."""
    ui.page.locator(GRAPH_FRAME).first.scroll_into_view_if_needed()
    ui.page.wait_for_timeout(300)
    point = _group_point(ui, label)
    if not point:
        return False
    if not (0 < point["y"] < point["height"]):
        ui.page.evaluate("dy => window.scrollBy(0, dy)", point["y"] - point["height"] / 2)
        ui.page.wait_for_timeout(300)
        point = _group_point(ui, label)
        if not point or not (0 < point["y"] < point["height"]):
            return False
    ui.page.mouse.click(point["x"], point["y"])
    ui.settle()
    return True


# ------------------------------------------------------------------------------- the view


def _wait_view_shows(ui, token: str) -> bool:
    """A redrawn view arrives after its callback; wait for the shape that proves it is the new one."""
    try:
        ui.page.wait_for_function(
            "t => Array.from(document.querySelectorAll('.ea-mermaid svg'))"
            ".some(s => (s.textContent || '').includes(t))",
            arg=token,
            timeout=25_000,
        )
    except Exception:  # noqa: BLE001 — a view that never redraws is the scenario's finding
        return False
    ui.page.wait_for_timeout(200)
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
    heading = ui.page.locator("#page h1").first
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

    option = ui.page.locator("[role='option']:visible").filter(has_text=f"[{COURSE}]")
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
    # a Mantine badge is upper-cased by CSS, so its text comes back however it was written
    ui.check("its type is named", curriculum[2].lower() == "logical data component", curriculum[2])
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
    upgrade = _row_for(far, "Curriculum Management System Upgrade")
    ui.check(
        "the work package that would touch it is reached at three hops",
        upgrade[:1] == ["3"],
        str(upgrade),
    )
    ui.check(
        "through the chain that got there",
        upgrade[3] == "encapsulates › processes › impacts" if upgrade else False,
        str(upgrade),
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
    counted = re.search(r"(\d+) elements depend on it within \d+ hops; it depends on (\d+)", _sentence(ui))
    ui.must("the sentence counts both directions", counted is not None, _sentence(ui))
    ui.check(
        "the sentence agrees with both tables",
        (int(counted.group(1)), int(counted.group(2))) == (len(up), len(down)),
        f"sentence {counted.group(1)}/{counted.group(2)}, tables {len(up)}/{len(down)}",
    )
    platform = _row_for(up, "Integration Platform")
    ui.check("the platform that realises it depends on it", platform[:1] == ["1"], str(platform))
    ui.check(
        "and the relationship it was reached by is named",
        platform[3] == "realises" if platform else False,
        str(platform),
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
    heading = ui.page.locator("#page h1").first
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
    ui.check(
        "it is a draw.io file",
        diagram.lstrip().startswith("<?xml") and "<mxfile" in diagram,
        diagram[:60],
    )
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
    expected="Asking for an element the repository does not hold says 'Unknown element.' in red, "
    "names the identifier the address carried and offers a way on, rather than an empty answer.",
)
def test_unknown_element(ui, record):
    unknown = "D-NO-SUCH-ELEMENT"
    ui.goto(f"/impact?element={unknown}")
    arrival = _summary(ui)
    ui.check(
        "arriving with an unknown element says the id is unknown",
        "Unknown element." in arrival,
        f"the result area read {arrival[:80]!r}",
    )
    ui.check(
        "and names the identifier the address carried",
        unknown in arrival,
        f"the result area read {arrival[:120]!r}",
    )
    ui.check(
        "and offers somewhere to go from a refusal",
        ui.page.locator("#imp-result a").count() > 0,
        f"{ui.page.locator('#imp-result a').count()} links in the refusal",
    )
    ui.check(
        "and the selector is left empty rather than holding an id that resolves to nothing",
        unknown not in _selected(ui),
        f"the selector reads {_selected(ui)!r}",
    )
    ui.check(
        "the refusal is in red",
        "red" in _alert_colour(ui, "Unknown element."),
        _alert_colour(ui, "Unknown element."),
    )
    ui.check("no closure table is shown for it", not _rows(ui, UPSTREAM) and not _rows(ui, DOWNSTREAM))
    ui.shot("Arriving at Impact with an element id nothing matches: named, in red, with a way on")


@pytest.mark.scenario(
    scenario_id="D11",
    group="D",
    title="Run before an element is chosen asks for one rather than doing nothing",
    feature="Impact · Run with nothing chosen",
    expected="Pressing Run before an element is chosen answers the press — 'Choose an element above, "
    "then press Run.' — invents no answer, and choosing an element afterwards still works.",
)
def test_run_with_nothing_chosen(ui, record, finding):
    ui.goto("/impact")
    ui.must("nothing is chosen yet", _selected(ui) == "", _selected(ui))
    ui.check("Run is offered all the same", not ui.disabled("imp-run"))
    _run(ui)
    answered = _summary(ui)
    ui.check(
        "the press is answered rather than swallowed",
        "Choose an element" in answered,
        answered[:120] or "(nothing at all)",
    )
    ui.check(
        "and no answer is invented for an element that was never named",
        "elements depend on it within" not in answered,
        answered[:120],
    )
    ui.check(
        "and nothing on the page reads as a failure",
        not re.search(r"traceback|exception|error:", ui.text("page"), re.I),
        ui.text("page")[:160].replace("\n", " · "),
    )
    ui.check("the graph is left empty", not _graph_nodes(ui), str(_graph_nodes(ui)[:6]))
    ui.check("so is the generated view", ui.text(MERMAID_SVG) == "", ui.text(MERMAID_SVG)[:80])
    ui.shot("Run pressed before an element is chosen: the page asks for one")

    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    ui.check(
        "the page still answers once an element is chosen",
        "elements depend on it within" in _summary(ui),
        _summary(ui)[:120].replace("\n", " · "),
    )
    if not answered.strip():
        finding.append(
            Finding(
                finding_id="D-1",
                where="src/ea/ui/pages/impact.py · run() (the `if not element_id` branch)",
                severity="usability",
                summary="Run is offered with nothing to run, and pressing it says nothing at all",
                detail=(
                    "The callback returns three `no_update`s when no element is selected, so the button "
                    "reports as loading for a moment and then leaves the page exactly as it was: no "
                    "message, no hint that an element has to be chosen first. Either disable Run until "
                    "the selector holds something, or answer the press with 'Choose an element first.'"
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="D12",
    group="D",
    title="The downloads are held back until there is a view to download",
    feature="Impact · the downloads before an answer",
    expected="Before an element is chosen neither download can be pressed, and the reason stands "
    "beside them; choosing an element opens both, and the same button downloads the view.",
)
def test_downloads_before_an_answer(ui, record):
    # This scenario used to require the opposite — both buttons live, both silent — and that
    # was the finding: a button that takes a click and produces nothing reads as broken.
    ui.goto("/impact")
    ui.must("nothing is chosen yet", _selected(ui) == "", _selected(ui))
    ui.check("Download Markdown cannot be pressed yet", ui.disabled("imp-view-md"))
    ui.check("nor can Download draw.io", ui.disabled("imp-view-drawio"))
    reason = ui.text("imp-view-note")
    ui.check("and the reason stands beside them", "no view to export yet" in reason, reason or "(nothing)")
    ui.shot("Before an element is chosen the downloads are held back, and say why")

    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    ui.wait_mermaid()
    ui.check("choosing one opens Download Markdown", not ui.disabled("imp-view-md"))
    ui.check("and Download draw.io", not ui.disabled("imp-view-drawio"))
    ui.check("and the reason is withdrawn", ui.text("imp-view-note") == "", ui.text("imp-view-note"))
    md = ui.download("imp-view-md", ".md")
    ui.check("the same button downloads the view", md.name == f"{COURSE}-impact.md", md.name)
    ui.shot("With an element chosen, both downloads are offered and Markdown arrives")


@pytest.mark.scenario(
    scenario_id="D13",
    group="D",
    title="The breakdown and the completeness footer agree with what is on screen",
    feature="Impact · the summary arithmetic",
    expected="Every element in the two tables is counted once in the by-type breakdown, type by type, "
    "and the footer's 'of' count agrees with the list of relationship types it says have nothing.",
)
def test_breakdown_agrees_with_the_answer(ui, record):
    ui.goto(f"/impact?element={SYNC}")
    ui.must("the impact was answered", bool(_sentence(ui)), _summary(ui)[:160].replace("\n", " · "))
    # the badge itself, not the word in the footer's prose: a badge that lost its type would
    # still leave "declared for Integration" on the page
    ui.check(
        "the element's own type is badged beside its name", _badge(ui).lower() == "integration", _badge(ui)
    )

    breakdown = _by_type(ui)
    ui.must("the summary breaks the answer down by type", bool(breakdown), _sentence(ui))
    up, down = _rows(ui, UPSTREAM), _rows(ui, DOWNSTREAM)
    ui.check(
        "every element in both tables is counted once in the breakdown",
        sum(breakdown.values()) == len(up) + len(down),
        f"breakdown {sum(breakdown.values())}, tables {len(up)} + {len(down)}",
    )
    ui.check(
        "and each type is counted as often as it appears in them",
        breakdown == _types_in_tables(ui),
        f"{breakdown} against {_types_in_tables(ui)}",
    )

    text = _alert(ui, "Completeness:").inner_text().strip()
    counted = re.search(r"Completeness: (\d+) of (\d+) relationship types", text)
    ui.must("the footer counts what is populated out of what is declared", counted is not None, text[:120])
    populated, declared = int(counted.group(1)), int(counted.group(2))
    listed = (
        [item.strip(" .") for item in text.split("No instances yet for:")[1].split(";")]
        if "No instances yet for:" in text
        else []
    )
    ui.check(
        "the types it names as empty are exactly the ones it did not count as populated",
        declared - populated == len(listed),
        f"{populated} of {declared}, {len(listed)} named",
    )
    ui.check(
        "and each one is named with the pair of types it would relate",
        bool(listed) and all(re.fullmatch(r".+ \(.+ -> .+\)", item) for item in listed),
        " | ".join(listed)[:200],
    )
    ui.shot("The by-type breakdown counted against both tables, and the footer against its own list")


@pytest.mark.scenario(
    scenario_id="D14",
    group="D",
    title="Choosing a second element replaces the whole answer",
    feature="Impact · asking again",
    expected="Choosing another element rewrites the sentence, the type badge, both tables and the "
    "footer, re-centres the graph on it and redraws the architecture view.",
)
def test_a_second_element_replaces_the_answer(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    ui.wait_graph()
    ui.wait_mermaid()
    ui.must("the first element was answered", "SRS_Course" in _summary(ui), _summary(ui)[:120])
    ui.check(
        "its downstream table says it depends on nothing",
        "Nothing." in _panel(ui, DOWNSTREAM).inner_text(),
        _panel(ui, DOWNSTREAM).inner_text().strip()[:80],
    )
    ui.check("and the graph is centred on it", _graph_centre(ui) == [COURSE], str(_graph_centre(ui)))
    before = _graph_nodes(ui)

    ui.must("the integration was found in the selector", _pick(ui, SYNC, SYNC))
    ui.check(
        "the summary now names the element that was chosen",
        "CMS to SRS curriculum sync" in _summary(ui),
        _summary(ui)[:120].replace("\n", " · "),
    )
    ui.check("badged with its own type", _badge(ui).lower() == "integration", _badge(ui))
    footer = _alert(ui, "Completeness:").inner_text()
    ui.check(
        "the completeness footer is about that type now",
        "declared for Integration" in footer,
        footer.replace("\n", " · ")[:160],
    )
    ui.check(
        "the downstream table that said Nothing has rows now",
        bool(_rows(ui, DOWNSTREAM)),
        f"{len(_rows(ui, DOWNSTREAM))} rows",
    )
    after = _wait_for_graph(ui, before)
    ui.check("the graph moved to the new element", _graph_centre(ui) == [SYNC], str(_graph_centre(ui)))
    ui.check("and drew it", SYNC in after, str(sorted(after)[:8]))
    ui.check(
        "the architecture view was redrawn for it",
        _wait_view_shows(ui, f"[{SYNC}]") and f"[{SYNC}]" in ui.text(MERMAID_SVG),
        ui.text(MERMAID_SVG)[:160].replace("\n", " · "),
    )
    ui.shot("A second element replaces the sentence, the tables, the footer, the graph and the view")


@pytest.mark.scenario(
    scenario_id="D15",
    group="D",
    title="The depth box holds its reader to the range it allows",
    feature="Impact · depth · the range",
    expected="A depth typed beyond six is pulled back to six and answered at six, one below one is "
    "pulled up to one, and an emptied box answers at the default three.",
)
def test_depth_bounds(ui, record, finding):
    ui.goto("/impact")
    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))

    _set_depth(ui, 9)
    ui.check("a depth past the end of the range is pulled back to six", _leave_depth(ui) == "6", _depth(ui))
    _run(ui)
    ui.check("and the answer says the depth it used", "within 6 hops" in _sentence(ui), _sentence(ui))
    deep = _rows(ui, UPSTREAM)
    ui.check(
        "nothing came back from further out than that",
        bool(deep) and all(int(r[0]) <= 6 for r in deep),
        str(sorted({r[0] for r in deep})),
    )
    ui.shot("A depth typed past the end of the range is answered at six")

    _set_depth(ui, 0)
    ui.check("a depth below the range is pulled up to one", _leave_depth(ui) == "1", _depth(ui))
    _run(ui)
    near = _rows(ui, UPSTREAM)
    ui.check(
        "and the closure is back to one hop",
        bool(near) and {r[0] for r in near} == {"1"},
        str(sorted({r[0] for r in near})),
    )

    box = _input(ui, "imp-depth")
    box.click()
    box.fill("")
    emptied = _leave_depth(ui)
    ui.check(
        "an emptied depth box is refilled with the depth the page answers at",
        emptied == "3",
        repr(emptied),
    )
    _run(ui)
    ui.check(
        "and the answer says the same depth the box now shows",
        "within 3 hops" in _sentence(ui),
        _sentence(ui),
    )
    ui.shot("An emptied depth box is put back to the three the page answers at")
    if emptied == "":
        finding.append(
            Finding(
                finding_id="D-3",
                where="src/ea/ui/pages/impact.py · run() (`int(depth or 3)`) and the imp-depth NumberInput",
                severity="usability",
                summary="An emptied depth box answers at three while the box itself stays blank",
                detail=(
                    "Mantine leaves the NumberInput empty when its contents are deleted, and the callback "
                    "falls back to `int(depth or 3)`, so the sentence reads 'within 3 hops' over a control "
                    "showing nothing. The sentence is honest, but the control disagrees with it. Put the "
                    "default back into the box when it is left empty."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="D16",
    group="D",
    title="Every row in a closure table opens the element it names",
    feature="Impact · the closure tables · navigation",
    expected="Each row's element is a link to that element's page, and following one leaves Impact "
    "for the element that was clicked.",
)
def test_a_row_opens_the_element_it_names(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    rows = _rows(ui, UPSTREAM)
    ui.must("the upstream table has rows", bool(rows), f"{len(rows)} rows")
    links = _panel(ui, UPSTREAM).locator("tbody a")
    hrefs = links.evaluate_all("els => els.map(e => e.getAttribute('href'))")
    ui.check(
        "every row names an element that can be opened from it",
        len(hrefs) == len(rows),
        f"{len(hrefs)} links for {len(rows)} rows",
    )
    ui.check(
        "each link addresses one element",
        bool(hrefs) and all((h or "").startswith("/element/") for h in hrefs),
        str(hrefs[:4]),
    )
    ui.check(
        "the row for the curriculum component points at that component",
        "/element/LDC-CURR" in hrefs,
        str(hrefs[:6]),
    )
    ui.shot("Each row of the closure table links to the element it names")

    link = _panel(ui, UPSTREAM).locator("tbody a[href='/element/LDC-CURR']").first
    ui.must("that link is on the page", link.count() > 0)
    link.click()
    ui.settle()
    ui.check("following it opens that element", ui.page.url.endswith("/element/LDC-CURR"), ui.page.url)
    heading = ui.page.locator("#page h1").first
    ui.check(
        "and the page that opened is the one the row named",
        heading.count() and heading.inner_text().strip() == "Curriculum",
        heading.inner_text().strip() if heading.count() else "no heading",
    )
    ui.shot("Following a row of the closure table opens that element")


@pytest.mark.scenario(
    scenario_id="D17",
    group="D",
    title="The graph follows the depth that was asked for, up to the two hops it draws",
    feature="Impact · the graph and the depth",
    expected="At depth 1 the graph draws the immediate neighbours only; at depth 3 it reaches two "
    "hops, which is as far as it ever draws even when the table answers from three.",
)
def test_the_graph_follows_the_depth(ui, record, finding):
    ui.goto(f"/impact?element={COURSE}")
    ui.wait_graph()
    far = _graph_nodes(ui)
    ui.must("the graph drew the neighbourhood", bool(far), f"{len(far)} nodes")
    ui.check("it reaches two hops out from the element", "INT-CMS-SRS" in far, str(sorted(far)[:10]))
    upgrade = _row_for(_rows(ui, UPSTREAM), "Curriculum Management System Upgrade")
    ui.check("the table answers from three hops out", upgrade[:1] == ["3"], str(upgrade))
    stops_short = "WP-CMS-UPGRADE" not in far
    ui.check(
        "the graph stops at the two hops it is built for",
        stops_short,
        f"{len(far)} nodes, the three-hop work package {'absent' if stops_short else 'drawn'}",
    )
    note = ui.text("imp-graph-note")
    ui.check(
        "and the panel says the picture is shorter than the answer above it",
        "two hops" in note and "3" in note,
        note or "(no note)",
    )
    ui.shot("At depth 3 the graph draws two hops of the neighbourhood, and says so")

    _set_depth(ui, 1)
    _run(ui)
    near = _wait_for_graph(ui, far)
    for neighbour in ("LDC-CURR", "PAC-SRS", "PTC-RDBMS", "DEF-COURSE"):
        ui.check(f"{neighbour} is still drawn one hop away", neighbour in near, str(sorted(near)))
    ui.check(
        "and nothing two hops out is drawn any more",
        "INT-CMS-SRS" not in near and "ORG-ACAD" not in near,
        str(sorted(near)),
    )
    ui.check("the element itself is still the centre", _graph_centre(ui) == [COURSE], str(_graph_centre(ui)))
    ui.check(
        "and with the answer inside the picture there is nothing left to say",
        ui.text("imp-graph-note") == "",
        ui.text("imp-graph-note") or "(no note)",
    )
    ui.shot("At depth 1 the graph draws only the immediate neighbours")
    if stops_short and not note.strip():
        finding.append(
            Finding(
                finding_id="D-4",
                where="src/ea/ui/pages/impact.py · _result() (`ctx.graph.neighbours(element_id, min(depth, 2))`)",
                severity="usability",
                summary="The graph is capped at two hops while the tables answer from six, and nothing says so",
                detail=(
                    "The picture under the tables is built from `neighbours(element_id, min(depth, 2))`, so "
                    "an answer run at three hops lists a work package the graph never draws — at depth 3 "
                    "the table names Curriculum Management System Upgrade three hops out and the graph "
                    "stops one hop short of it. The cap is sensible (the picture stays readable), but the "
                    "panel should say it is showing two hops of an answer that reaches further."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="D18",
    group="D",
    title="A search nothing matches empties the list rather than leaving the last one up",
    feature="Impact · the element selector · no matches",
    expected="Typing something no element matches offers no options and says so, and leaving the "
    "search keeps the element that was already chosen and its answer.",
)
def test_a_search_that_matches_nothing(ui, record, finding):
    ui.goto("/impact")
    ui.must("the element was found in the selector", _pick(ui, COURSE, COURSE))
    ui.must("it was answered", bool(_sentence(ui)), _summary(ui)[:120].replace("\n", " · "))

    _type_in_selector(ui, "zzzqqq-no-such-element")
    offered = _options(ui)
    ui.check("nothing is offered for a search nothing matches", not offered, " | ".join(offered[:4]))
    message = _dropdown(ui)
    # The search callback returns `no_update` when the repository matches nothing, so what is
    # left on screen is Mantine filtering the options it already had — the list has to end up
    # empty rather than keeping the last search's matches in front of the reader.
    ui.check(
        "the reader is told the list is empty rather than shown the last search's matches",
        bool(message) and "SRS_Course" not in message,
        repr(message[:120]),
    )
    ui.check(
        "and told that this search matched nothing, rather than told to start one",
        "zzzqqq-no-such-element" in message,
        repr(message[:160]),
    )
    ui.shot("A search nothing matches says so, naming what was searched for")

    ui.page.keyboard.press("Escape")
    ui.page.locator("#page h1").first.click()
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.check(
        "the element that was chosen is still chosen",
        "SRS_Course" in _selected(ui) or COURSE in _selected(ui),
        _selected(ui),
    )
    ui.check("and its answer is still on screen", "SRS_Course" in _summary(ui), _summary(ui)[:120])
    if "Type to search" in message:
        finding.append(
            Finding(
                finding_id="D-5",
                where="src/ea/ui/pages/impact.py · the imp-element Select (`nothingFoundMessage`)",
                severity="usability",
                summary="A search that matched nothing tells the reader to type a search",
                detail=(
                    "One `nothingFoundMessage` covers two states. Before anything is typed 'Type to "
                    "search' is the right instruction; after 'zzzqqq-no-such-element' has been typed it "
                    "reads as though the search never happened, when what the reader needs to know is "
                    "that the repository holds no element by that name."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="D19",
    group="D",
    title="Tapping the box a layer sits in stays where it is",
    feature="Impact · the graph · the layer boxes",
    expected="The graph's boxes are named for the layers they hold, and tapping one — rather than a "
    "node inside it — leaves the reader on Impact with the answer still on screen.",
)
def test_tapping_a_layer_box_goes_nowhere(ui, record):
    ui.goto(f"/impact?element={COURSE}")
    ui.wait_graph()
    labels = _graph_groups(ui)
    ui.must("the graph boxes its nodes", len(labels) > 1, str(labels))
    ui.check(
        "and names each box for the layer it holds",
        {"Application", "Technology"} <= set(labels),
        str(sorted(labels)),
    )
    ui.must("the application box could be tapped", _tap_group(ui, "Application"), str(labels))
    selected = _selected_nodes(ui)
    ui.check(
        "the tap landed on the box itself, not on an element inside it",
        any(s.startswith("g:layer:") for s in selected),
        str(selected),
    )
    ui.check("tapping a box opens nothing", "/element/" not in ui.page.url, ui.page.url)
    heading = ui.page.locator("#page h1").first
    ui.check(
        "the reader is still on Impact",
        heading.count() and heading.inner_text().strip() == "Impact",
        heading.inner_text().strip() if heading.count() else "no heading",
    )
    ui.check("with the answer still on screen", "SRS_Course" in _summary(ui), _summary(ui)[:120])
    ui.shot("Tapping the box a layer's elements sit in leaves the page where it was")
