"""Group E — Target state: the work packages, the current-by-target matrix and the marked view.

The page answers a planning question rather than a modelling one: what is true of each
artefact today, what the organisation intends for it, and which work package carries the
change. So every scenario here reads it the way an architect preparing a roadmap would —
the two controls at the top and how they answer each other, the badge row that counts the
scope, the matrix that crosses current against target, the generated view with the legend
that says what its markers mean, the two tables under it, and the two files the view can
be taken away in.

The sample model gives the group one work package, `WP-CMS-UPGRADE`, and eight elements
that name it: three changed, two new, one decommissioned and two kept. That is enough to
prove every marker, every badge and both halves of the "Only what changes" switch.

Counts are never asserted absolutely — the round shares one database and an earlier group
may have set a target state of its own — so an assertion here is a row that must be there,
a number that must have grown or shrunk, or an arithmetic identity between two figures the
page states in two places.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.gui

WP = "WP-CMS-UPGRADE"
WP_NAME = "Curriculum Management System Upgrade"
WP_OPTION = f"{WP_NAME} [{WP}]"
ALL_WPS = "All work packages"
VIEW_SVG = '[id=\'{"id":"tg-view","type":"mermaid-svg"}\']'
MATRIX_CARD = '#tg-body .ea-card:has-text("Current state by target state")'
VIEW_CARD = '#tg-body .ea-card:has-text("Architecture view, marked")'
TABLES_CARD = '#tg-body .ea-card:has-text("Relationships (")'

# The vocabulary the page draws from, and the glyph each target state is marked with.
TARGET_GLYPHS = {
    "undecided": "?",
    "keep": "=",
    "new": "+",
    "change": "Δ",
    "decommission": "×",
    "merge": "⇒",
}
# What the sample says of the work package: the element, its current state and its target.
WP_SCOPE = {
    "CMS_Unit_Outline": ("live", "change"),
    "Curriculum Management System": ("live", "change"),
    "CMS to SRS curriculum sync": ("live", "change"),
    "Curriculum to Student Administration interface": ("planned", "new"),
    "Curriculum Approval Workflow": ("proposed", "new"),
    "Legacy Forms Server": ("live", "decommission"),
}
WP_KEPT = {"Student Records System (SRS)", "Curriculum Management"}


# ------------------------------------------------------------------------ the two controls


def _input(ui, component_id: str):
    """A Mantine control puts its id on the wrapper or on the field; take whichever is there."""
    return ui.page.locator(f"#{component_id} input, input#{component_id}").first


def _wp(ui) -> str:
    return _input(ui, "tg-wp").input_value()


def _only_changes(ui) -> bool:
    return _input(ui, "tg-only-changes").is_checked()


def _choose_wp(ui, fragment: str) -> None:
    """Open the work package selector, clear whatever it was searching for, and choose."""
    box = _input(ui, "tg-wp")
    box.click()
    box.fill("")
    ui.page.wait_for_timeout(250)
    option = ui.page.locator("[role='option']:visible").filter(has_text=fragment)
    option.first.click()
    ui.settle()


def _wp_options(ui) -> list[str]:
    """Only the open dropdown's options: the header's own selects keep theirs in the page."""
    box = _input(ui, "tg-wp")
    box.click()
    box.fill("")
    ui.page.wait_for_timeout(250)
    names = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    return names


# --------------------------------------------------------------------------- the page body


def _brief(text: str, limit: int = 140) -> str:
    """A block of screen text as one readable line, for the detail beside a check."""
    return " · ".join(line.strip() for line in text.splitlines() if line.strip())[:limit]


def _card(ui, heading: str):
    return ui.page.locator("#tg-body .ea-card").filter(has_text=heading).first


def _tables_card(ui):
    """The two tables sit in the last card on the page, under the matrix and the view."""
    return ui.page.locator("#tg-body .ea-card").last


def _counts_row(ui):
    return ui.page.locator("#tg-body > div > div").first


def _badges(ui) -> dict[str, int]:
    """The badge row read back as {target state: how many}, however the CSS cases it."""
    out: dict[str, int] = {}
    for text in _counts_row(ui).locator(".mantine-Badge-root").all_inner_texts():
        match = re.match(r"\s*(\d+)\s+(\w+)", text.strip().lower())
        if match:
            out[match.group(2)] = int(match.group(1))
    return out


def _scope_line(ui) -> tuple[int, int, int]:
    """The dimmed sentence under the badges: elements, relationships, elements that change."""
    match = re.search(
        r"(\d+) elements · (\d+) relationships · (\d+) elements change", _counts_row(ui).inner_text()
    )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else (-1, -1, -1)


def _matrix(ui) -> tuple[list[str], dict[str, dict[str, str]]]:
    """The current-by-target matrix as its column headings and {current state: {target state: cell}}.

    The headings carry a glyph and the CSS upper-cases them, so a column is keyed by the
    state it names — `matrix["live"]["change"]` — and the headings are checked separately.
    """
    table = _card(ui, "Current state by target state").locator("table").first
    heads = [h.strip() for h in table.locator("thead th").all_inner_texts()]
    columns = [h.split()[-1].lower() for h in heads[1:]]
    rows = table.locator("tbody tr")
    out: dict[str, dict[str, str]] = {}
    for i in range(rows.count()):
        cells = [c.strip() for c in rows.nth(i).locator("td").all_inner_texts()]
        if cells:
            out[cells[0].lower()] = dict(zip(columns, cells[1:], strict=False))
    return heads, out


def _clipped_headings(ui) -> list[str]:
    """The matrix headings the browser has had to cut off, read back with what is left of them."""
    return ui.page.evaluate(
        """() => {
            const table = document.querySelectorAll('#tg-body table')[0];
            if (!table) { return ['no matrix']; }
            const out = [];
            table.querySelectorAll('thead th').forEach(th => {
                const label = th.querySelector('.mantine-Badge-label') || th;
                if (label.scrollWidth > label.clientWidth + 1) {
                    out.push(((th.innerText || '').trim()) + ' → ' +
                             label.clientWidth + ' of ' + label.scrollWidth + ' px');
                }
            });
            return out;
        }"""
    )


def _cell(row: dict[str, str], target_state: str) -> int:
    """One cell of the matrix as a number; a dot means nothing sits there."""
    value = row.get(target_state, "·")
    return int(value) if value.isdigit() else 0


def _section_count(ui, word: str) -> int:
    """The number in a section heading — the CSS upper-cases it, so read it either way."""
    match = re.search(rf"{word} \((\d+)\)", _tables_card(ui).inner_text(), re.I)
    return int(match.group(1)) if match else -1


def _table(ui, index: int):
    return _tables_card(ui).locator("table").nth(index)


def _rows(table) -> list[list[str]]:
    body = table.locator("tbody tr")
    return [[c.strip() for c in body.nth(i).locator("td").all_inner_texts()] for i in range(body.count())]


def _links(table, row_name: str) -> list[str]:
    """Every href in one row of a table, addressed by what the first cell reads."""
    row = table.locator("tbody tr", has_text=row_name).first
    return [a.get_attribute("href") or "" for a in row.locator("a").all()]


def _row_for(rows: list[list[str]], name: str) -> list[str]:
    return next((r for r in rows if r and r[0] == name), [])


def _names(rows: list[list[str]]) -> list[str]:
    return [r[0] for r in rows if r]


def _legend(ui) -> str:
    match = re.search(r"Markers:[^\n]*", _card(ui, "Architecture view, marked").inner_text())
    return match.group(0) if match else ""


# ------------------------------------------------- what the view draws, and what marks it

VIEW_SRC = '[id=\'{"id":"tg-view","type":"mermaid-src"}\']'
TARGET_ORDER = list(TARGET_GLYPHS)  # the vocabulary's own order, which both tables sort by
MAX_NODES = 60  # what a generated view draws before the rest is left out
NEW_HEX, DECOMMISSION_HEX = "#2f9e44", "#c92a2a"
NEW_RGB, DECOMMISSION_RGB = "rgb(47, 158, 68)", "rgb(201, 42, 42)"


def _source(ui) -> str:
    """The Mermaid the page generated, read from the hidden source the browser draws from."""
    block = ui.page.locator(VIEW_SRC).first
    return (block.text_content() or "") if block.count() else ""


def _drawn_ids(ui) -> set[str]:
    """Every element identifier the view draws, from the label on each shape."""
    return set(re.findall(r"\[([A-Za-z0-9][A-Za-z0-9_.-]*)\]", ui.text(VIEW_SVG)))


def _edge_strokes(ui) -> set[str]:
    """The colour the browser actually paints each edge of the view in."""
    return set(
        ui.page.evaluate(
            """() => {
                const out = new Set();
                document.querySelectorAll(
                    '.ea-mermaid .edgePaths path, .ea-mermaid path.flowchart-link'
                ).forEach(p => out.add(getComputedStyle(p).stroke));
                return Array.from(out);
            }"""
        )
    )


def _state_of(cell: str) -> str:
    """The state a badge cell names, however the CSS cases it: 'Δ CHANGE' → 'change'."""
    words = cell.strip().lower().split()
    return words[-1] if words else ""


def _order(rows: list[list[str]], column: int) -> list[int]:
    """Where each row's target state sits in the vocabulary, read down the table."""
    return [
        TARGET_ORDER.index(state) for row in rows if row and (state := _state_of(row[column])) in TARGET_ORDER
    ]


def _row_ids(table) -> list[str]:
    """The element each row is about, in the order they are listed, from the link the row carries."""
    body = table.locator("tbody tr")
    out: list[str] = []
    for i in range(body.count()):
        link = body.nth(i).locator("a[href^='/element/']").first
        out.append((link.get_attribute("href") or "").rsplit("/", 1)[-1] if link.count() else "")
    return out


def _clipped_row_labels(ui) -> list[str]:
    """The matrix's row labels the browser has had to cut off, with what is left of them."""
    return ui.page.evaluate(
        """() => {
            const table = document.querySelectorAll('#tg-body table')[0];
            if (!table) { return ['no matrix']; }
            const out = [];
            table.querySelectorAll('tbody tr td:first-child').forEach(td => {
                const label = td.querySelector('.mantine-Badge-label') || td;
                if (label.scrollWidth > label.clientWidth + 1) {
                    out.push(((td.innerText || '').trim()) + ' → ' +
                             label.clientWidth + ' of ' + label.scrollWidth + ' px');
                }
            });
            return out;
        }"""
    )


def _search_options(ui, text: str) -> list[str]:
    """What the work package selector offers while its search box holds `text`."""
    box = _input(ui, "tg-wp")
    box.click()
    box.fill(text)
    ui.page.wait_for_timeout(250)
    return [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]


def _dropdown_text(ui) -> str:
    """Whatever the open dropdown says — a message, or nothing at all."""
    box = ui.page.locator("[role='listbox']:visible, .mantine-Combobox-dropdown:visible")
    return box.first.inner_text().strip() if box.count() else ""


def _finding(finding_id: str, where: str, severity: str, summary: str, detail: str):
    from tests.ui.evidence import Finding

    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


# ------------------------------------------------------------------------------- scenarios


@pytest.mark.scenario(
    scenario_id="E01",
    group="E",
    title="Target state opens on every work package, showing only what changes",
    feature="Target state · the default view",
    expected="Arriving at /target selects 'All work packages', leaves 'Only what changes' on, and "
    "shows the badge row, the current-by-target matrix, the marked architecture view and the two "
    "tables, with only the artefacts whose target state is not undecided or keep.",
)
def test_default_view(ui, record):
    ui.goto("/target")
    ui.check("the page is titled Target state", "Target state" in ui.text("#page h1"), ui.text("#page h1"))
    subtitle = re.search(r"What is true of each artefact today[^\n]*", ui.body())
    ui.check(
        "it says what a current and a target state are, and where they are edited",
        bool(subtitle) and "Edit the states on an element's page." in subtitle.group(0),
        subtitle.group(0) if subtitle else "no subtitle",
    )
    ui.must("the work package selector is offered", ui.visible("tg-wp"))
    ui.check("it opens on every work package", _wp(ui) == ALL_WPS, _wp(ui))
    ui.check("and 'Only what changes' is on", _only_changes(ui), f"checked={_only_changes(ui)}")
    for heading in ("Current state by target state", "Architecture view, marked"):
        ui.check(f"the page shows '{heading}'", _card(ui, heading).count() > 0)
    ui.check("and the two tables under them", _section_count(ui, "Elements") >= 0)

    elements, relationships, changes = _scope_line(ui)
    ui.must("the scope is stated in one sentence", elements > 0, _brief(_counts_row(ui).inner_text()))
    ui.check(
        "the whole model is in scope when no work package is chosen",
        elements >= 47 and relationships >= 99,
        f"{elements} elements, {relationships} relationships",
    )
    listed = _section_count(ui, "Elements")
    ui.check(
        "only what changes is listed, not the whole model",
        listed == changes and listed < elements,
        f"{listed} listed, {changes} change, {elements} in scope",
    )
    shown = _names(_rows(_table(ui, 0)))
    ui.check(
        "every element the work package changes is listed",
        set(WP_SCOPE) <= set(shown),
        str(sorted(set(WP_SCOPE) - set(shown))),
    )
    ui.check(
        "nothing merely kept is listed while the switch is on",
        not (WP_KEPT & set(shown)),
        str(sorted(WP_KEPT & set(shown))),
    )
    ui.shot("Target state on arrival: every work package, and only the artefacts that change")

    # Last, because opening the selector empties its search box and the shot above wants the page
    # as a reader first meets it.
    options = _wp_options(ui)
    ui.check("the selector offers the work package by name and id", WP_OPTION in options, str(options))
    ui.check("and an entry for all of them together", ALL_WPS in options, str(options))


@pytest.mark.scenario(
    scenario_id="E02",
    group="E",
    title="Choosing a work package widens the scope to everything it touches",
    feature="Target state · work package",
    expected="Choosing the Curriculum Management System Upgrade turns 'Only what changes' off by "
    "itself, so the scope shows what the work package keeps as well as what it changes; turning "
    "the switch back on narrows it again without losing the work package.",
)
def test_choosing_a_work_package(ui, record, finding):
    ui.goto("/target")
    ui.must("the page opened on every work package", _wp(ui) == ALL_WPS, _wp(ui))
    _choose_wp(ui, WP)
    ui.must("the work package is selected", WP_NAME in _wp(ui), _wp(ui))
    ui.check(
        "choosing one turns 'Only what changes' off, so nothing it touches is hidden",
        not _only_changes(ui),
        f"checked={_only_changes(ui)}",
    )
    with_kept = _names(_rows(_table(ui, 0)))
    ui.check(
        "what the work package keeps is now listed too",
        WP_KEPT <= set(with_kept),
        str(sorted(WP_KEPT - set(with_kept))),
    )
    ui.check(
        "and so is everything it changes",
        set(WP_SCOPE) <= set(with_kept),
        str(sorted(set(WP_SCOPE) - set(with_kept))),
    )
    ui.check(
        "nothing outside the work package is listed",
        set(with_kept) <= set(WP_SCOPE) | WP_KEPT,
        str(sorted(set(with_kept) - set(WP_SCOPE) - WP_KEPT)),
    )
    ui.check(
        "the work package itself is drawn in the view",
        f"[{WP}]" in ui.text(VIEW_SVG),
        _brief(ui.text(VIEW_SVG)),
    )
    ui.shot("The work package chosen: the switch off, and everything the package touches listed")

    ui.toggle("tg-only-changes", True)
    only_changes = _names(_rows(_table(ui, 0)))
    ui.check("the work package is still selected", WP_NAME in _wp(ui), _wp(ui))
    ui.check(
        "turning the switch back on drops what is merely kept",
        not (WP_KEPT & set(only_changes)) and set(WP_SCOPE) <= set(only_changes),
        f"listed {sorted(only_changes)}",
    )
    ui.check(
        "and the count under the heading follows it",
        _section_count(ui, "Elements") == len(only_changes) < len(with_kept),
        f"{_section_count(ui, 'Elements')} of {len(with_kept)}",
    )
    ui.shot("The same work package with 'Only what changes' back on: the kept artefacts drop out")

    work_packages = [row[4] for row in _rows(_table(ui, 0))]
    if not any(work_packages):
        finding.append(
            _finding(
                finding_id="E-4",
                where="src/ea/ui/pages/target.py · _body(), the elements table",
                severity="usability",
                summary="The 'work package' column stays in the table when one work package is in scope",
                detail=(
                    "Every row of the elements table names the same work package as the selector, so "
                    "the cell is left blank and the column is an empty stripe across the table. It "
                    "would read better dropped while a work package is chosen."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="E03",
    group="E",
    title="The badge row counts the scope by target state and agrees with itself",
    feature="Target state · the badge row",
    expected="A badge per target state that occurs, counting the elements in scope, and a sentence "
    "giving the elements, the relationships and how many change; the badges add up to the elements "
    "and the ones that are neither undecided nor keep add up to the changes.",
)
def test_badge_row(ui, record):
    ui.goto("/target")
    badges = _badges(ui)
    elements, relationships, changes = _scope_line(ui)
    ui.must("the badge row counts something", bool(badges), str(badges))
    ui.check(
        "every badge names a target state of the vocabulary",
        set(badges) <= set(TARGET_GLYPHS),
        str(sorted(set(badges) - set(TARGET_GLYPHS))),
    )
    ui.check("no badge counts nothing", all(v for v in badges.values()), str(badges))
    ui.check(
        "the badges add up to the elements in scope",
        sum(badges.values()) == elements,
        f"{sum(badges.values())} badged, {elements} in scope",
    )
    ui.check(
        "and everything neither undecided nor kept adds up to what changes",
        sum(v for k, v in badges.items() if k not in ("undecided", "keep")) == changes,
        f"{badges} against {changes} changing",
    )
    ui.check(
        "the model at large is mostly undecided",
        badges.get("undecided", 0) >= 38,
        str(badges),
    )
    ui.check("with the relationships counted beside them", relationships > 0, str(relationships))
    ui.shot("The badge row: how many elements sit at each target state, and the scope beneath it")

    _choose_wp(ui, WP)
    scoped = _badges(ui)
    wp_elements, wp_relationships, wp_changes = _scope_line(ui)
    ui.check(
        "choosing a work package counts only what names it",
        wp_elements < elements and wp_elements == sum(scoped.values()),
        f"{wp_elements} elements, badges {scoped}",
    )
    ui.check(
        "nothing in the work package is left undecided",
        "undecided" not in scoped,
        str(scoped),
    )
    for state in ("keep", "new", "change", "decommission"):
        ui.check(f"the work package has something to {state}", scoped.get(state, 0) >= 1, str(scoped))
    ui.check(
        "its relationships are counted too",
        0 < wp_relationships < relationships,
        f"{wp_relationships} of {relationships}",
    )
    ui.check("and six of its elements change", wp_changes >= 6, str(wp_changes))
    ui.shot("The badge row recounted for one work package: nothing in it is undecided")


@pytest.mark.scenario(
    scenario_id="E04",
    group="E",
    title="The current-by-target matrix crosses what is true today with what is intended",
    feature="Target state · the matrix",
    expected="A row per current state that something sits in and a column per target state, whose "
    "cells count the elements in each pair, add up to the elements in scope, and read as a dot "
    "rather than a zero where there is nothing.",
)
def test_matrix(ui, record, finding):
    ui.goto("/target")
    heads, matrix = _matrix(ui)
    ui.must("the matrix is drawn", bool(matrix), str(heads))
    ui.check(
        "its corner says which way to read it",
        "current" in heads[0] and "target" in heads[0],
        heads[0],
    )
    ui.check(
        "there is a column for every target state",
        [h.split()[-1].lower() for h in heads[1:]] == list(TARGET_GLYPHS),
        str(heads[1:]),
    )
    ui.check(
        "each column heading carries the glyph its state is marked with",
        all(TARGET_GLYPHS[h.split()[-1].lower()].lower() in h.lower() for h in heads[1:]),
        str(heads[1:]),
    )
    ui.check(
        "a row is shown for the states the model actually sits in",
        {"live", "planned", "proposed"} <= set(matrix),
        str(sorted(matrix)),
    )
    ui.check(
        "and no row for a current state nothing is in",
        all(any(cell.isdigit() for cell in row.values()) for row in matrix.values()),
        str({k: v for k, v in matrix.items() if not any(c.isdigit() for c in v.values())}),
    )
    cells = [c for row in matrix.values() for c in row.values()]
    ui.check("an empty cell reads as a dot, not a zero", "0" not in cells, str(sorted(set(cells))))
    total = sum(int(c) for c in cells if c.isdigit())
    ui.check(
        "the cells add up to the elements in scope",
        total == _scope_line(ui)[0],
        f"{total} in the matrix, {_scope_line(ui)[0]} in scope",
    )
    live = matrix.get("live", {})
    ui.check("what is live today and changing is counted", _cell(live, "change") >= 3, str(live))
    ui.check("so is what is live and being decommissioned", _cell(live, "decommission") >= 1, str(live))
    proposed = matrix.get("proposed", {})
    ui.check(
        "and what is only proposed is new rather than kept",
        _cell(proposed, "new") >= 1 and _cell(proposed, "keep") == 0,
        str(proposed),
    )
    # Believed wrong: the column headings are Mantine badges inside the table head, and the
    # browser clips them to the column width, so the reader sees "= K…" and "⇒ ME…" and cannot
    # tell one target state from another. The vocabulary is fixed and short; the heading should
    # fit, wrap, or be spelled out beside the glyph.
    clipped = _clipped_headings(ui)
    ui.check(
        "every column heading can be read in full",
        not clipped,
        "clipped: " + "; ".join(clipped) if clipped else "",
    )
    ui.shot("The current-by-target matrix: what is true today against what is intended")
    ui.shot(
        "The matrix headings up close: every one is cut off, so keep cannot be told from merge",
        selector=MATRIX_CARD,
    )

    finding.append(
        _finding(
            finding_id="E-2",
            where="src/ea/ui/pages/target.py · _matrix(), the column headings",
            severity="usability",
            summary="The matrix column headings are clipped, so the target states cannot be told apart",
            detail=(
                "Each heading is a Badge in a table cell narrower than its text, so the six columns "
                "read '? UNDECI…', '= K…', '+ N…', 'Δ CHA…', '× DECOMMIS…' and '⇒ ME…'. The reader "
                "cannot tell keep from merge without counting columns against the badge row above."
            ),
        )
    )
    finding.append(
        _finding(
            finding_id="E-3",
            where="src/ea/ui/pages/target.py · _body(), the SimpleGrid of the matrix and the view",
            severity="usability",
            summary="The matrix card is stretched to the height of the diagram beside it and is mostly empty",
            detail=(
                "The two cards share a SimpleGrid, so the matrix — three rows on the sample model — "
                "is padded out to the height of the generated view, leaving about two thirds of the "
                "card blank and pushing the two tables below the fold."
            ),
        )
    )


@pytest.mark.scenario(
    scenario_id="E05",
    group="E",
    title="The generated view is marked with each artefact's target state, and says what the marks mean",
    feature="Target state · the marked view",
    expected="The view renders as a layered diagram in which every shape carries its element "
    "identifier and the changing ones carry their target state's glyph, above a legend line that "
    "names only the markers the diagram actually uses.",
)
def test_marked_view(ui, record):
    ui.goto(f"/target?wp={WP}")
    ui.wait_mermaid()
    svg = ui.page.locator(f"{VIEW_SVG} svg")
    ui.must("the view was drawn", svg.count() > 0)
    drawn = ui.text(VIEW_SVG)
    ui.check("the work package itself is drawn", f"[{WP}]" in drawn, _brief(drawn))
    for element_id in ("PAC-CAW", "PTC-FORMS", "PAC-CMS"):
        ui.check(f"every shape carries its identifier ({element_id})", f"[{element_id}]" in drawn)
    ui.check(
        "the shapes are stacked in labelled layers",
        sum(word in drawn for word in ("Application", "Technology", "Implementation")) >= 2,
        _brief(drawn),
    )
    for state, glyph in (("new", "+"), ("change", "Δ"), ("decommission", "×")):
        ui.check(f"what is {state} is marked with {glyph}", glyph in drawn, _brief(drawn))

    legend = _legend(ui)
    ui.must("a legend says what the markers mean", legend.startswith("Markers:"), legend or "no legend")
    for word in ("new", "change", "decommission"):
        ui.check(f"the legend names {word}", word in legend.lower(), legend)
    ui.check(
        "and names nothing the diagram does not use",
        "merge" not in legend.lower() and "undecided" not in legend.lower(),
        legend,
    )
    note = _card(ui, "Architecture view, marked").inner_text()
    ui.check(
        "the toolbar says how the states are drawn",
        "New shapes are dashed green, changed amber, decommissioned red" in note,
        _brief(note[-200:]),
    )
    ui.shot("The marked architecture view for the work package, with the legend above it")
    ui.shot(
        "The view up close: new shapes dashed green, changed amber and the decommissioned server red",
        selector=VIEW_CARD,
    )


@pytest.mark.scenario(
    scenario_id="E06",
    group="E",
    title="Both tables give every artefact its current state, its target state and its note",
    feature="Target state · the two tables",
    expected="The elements table names each element, its type, its current and target states, its "
    "work package and the note, and links to the element; the relationships table does the same "
    "for the relationships that carry a target state.",
)
def test_the_two_tables(ui, record):
    ui.goto("/target")
    card = _tables_card(ui)
    ui.must(
        "both sections are headed with their counts",
        _section_count(ui, "Elements") >= 0 and _section_count(ui, "Relationships") >= 0,
        _brief(card.inner_text()),
    )

    el_heads = [h.strip().lower() for h in _table(ui, 0).locator("thead th").all_inner_texts()]
    ui.check(
        "the elements table has the columns an architect reads",
        el_heads == ["element", "type", "current", "target", "work package", "note"],
        str(el_heads),
    )
    el_rows = _rows(_table(ui, 0))
    ui.check(
        "the elements table lists the count in its heading",
        len(el_rows) == _section_count(ui, "Elements"),
        f"{len(el_rows)} rows, heading says {_section_count(ui, 'Elements')}",
    )
    wrong = [
        name
        for name, (current, target) in WP_SCOPE.items()
        if not ((row := _row_for(el_rows, name)) and current in row[2].lower() and target in row[3].lower())
    ]
    ui.check(
        "every element that changes carries the two states the model holds for it",
        not wrong,
        str(wrong),
    )
    forms = _row_for(el_rows, "Legacy Forms Server")
    ui.must("the decommissioned server is listed", bool(forms), str(_names(el_rows)))
    ui.check("with the type it is", "technology" in forms[1].lower(), forms[1])
    ui.check("what is true of it today", "live" in forms[2].lower(), forms[2])
    ui.check("what is intended for it", "decommission" in forms[3].lower(), forms[3])
    ui.check("the work package that will do it", WP in forms[4], forms[4])
    ui.check(
        "and the note saying when",
        "teaching period" in forms[5].lower(),
        forms[5],
    )
    links = _links(_table(ui, 0), "Legacy Forms Server")
    ui.check(
        "the element is a link to its page",
        "/element/PTC-FORMS" in links,
        str(links),
    )
    ui.check(
        "and the work package is a link that scopes the page to it",
        f"/target?wp={WP}" in links,
        str(links),
    )

    rel_heads = [h.strip().lower() for h in _table(ui, 1).locator("thead th").all_inner_texts()]
    ui.check(
        "the relationships table reads from one end to the other",
        rel_heads == ["from", "relationship", "to", "current", "target", "note"],
        str(rel_heads),
    )
    rel_rows = _rows(_table(ui, 1))
    ui.check(
        "it lists the count in its heading",
        len(rel_rows) == _section_count(ui, "Relationships"),
        f"{len(rel_rows)} rows, heading says {_section_count(ui, 'Relationships')}",
    )
    realises = next((r for r in rel_rows if r and r[0] == "Legacy Forms Server"), [])
    ui.must("the relationship the decommissioning breaks is listed", bool(realises), str(rel_rows[:3]))
    ui.check("it names the relationship type", "realises" in realises[1].lower(), realises[1])
    ui.check("the element at the other end", realises[2] == "Curriculum Management System", realises[2])
    ui.check("that it is live today", "live" in realises[3].lower(), realises[3])
    ui.check("and decommissioned in the target", "decommission" in realises[4].lower(), realises[4])
    ui.shot("The elements and relationships tables, each artefact with both its states and its note")
    ui.shot(
        "Both tables up close: the element, its type, both its states, its work package and the note",
        selector=TABLES_CARD,
    )


@pytest.mark.scenario(
    scenario_id="E07",
    group="E",
    title="The view can be taken away as Markdown or draw.io, named for what is in scope",
    feature="Target state · downloads",
    expected="Download Markdown and Download draw.io each return a file named for the work package "
    "in scope, holding the marked diagram, the legend and a table of every element with its "
    "current and target state.",
)
def test_downloads(ui, record):
    ui.goto(f"/target?wp={WP}")
    ui.wait_mermaid()
    md = ui.download("tg-view-md", ".md")
    ui.check("the Markdown is named for the work package", md.name == f"target-state-{WP}.md", md.name)
    text = md.read_text(encoding="utf-8")
    ui.check("it is titled for the work package", f"## Target state of {WP_NAME}" in text, text[:80])
    ui.check("it carries the legend line", "Markers:" in text, text[:300].replace("\n", " · "))
    ui.check("it carries the diagram as Mermaid", "```mermaid" in text, text[:300])
    ui.check(
        "the table gives both states of every element",
        "| Current state | Target state |" in text,
        text[-600:],
    )
    ui.check(
        "and the decommissioned server is in it with its states",
        re.search(r"\| `PTC-FORMS` \|.*\| Live \| Decommission \|", text) is not None,
        next((line for line in text.splitlines() if "PTC-FORMS" in line), "no row"),
    )

    drawio = ui.download("tg-view-drawio", ".drawio")
    ui.check("the draw.io file is named for it too", drawio.name == f"target-state-{WP}.drawio", drawio.name)
    diagram = drawio.read_text(encoding="utf-8")
    ui.check(
        "it is a draw.io file",
        diagram.lstrip().startswith("<?xml") and "<mxfile" in diagram,
        diagram[:60],
    )
    ui.check("every shape in it carries an element identifier", "PTC-FORMS" in diagram, diagram[:200])
    forms_shape = next((line for line in diagram.splitlines() if 'ea_id="PTC-FORMS"' in line), "")
    ui.check(
        "what is decommissioned is struck through in it",
        "&lt;s&gt;Legacy Forms Server&lt;/s&gt;" in forms_shape,
        forms_shape[:200],
    )
    ui.check(
        "and each shape carries the two states it was drawn from",
        'ea_current_state="live"' in forms_shape and 'ea_target_state="decommission"' in forms_shape,
        forms_shape[:200],
    )
    ui.shot("The work package's view, with the two buttons that produced the files")

    ui.goto("/target")
    ui.wait_mermaid()
    whole = ui.download("tg-view-md", ".md")
    ui.check(
        "without a work package the file is named for all of them",
        whole.name == "target-state-all.md",
        whole.name,
    )
    ui.check(
        "and it is titled for the model rather than a package",
        "## Target state of the model" in whole.read_text(encoding="utf-8"),
        whole.read_text(encoding="utf-8")[:80],
    )
    ui.shot("The whole model's target state, downloadable under a name of its own")


@pytest.mark.scenario(
    scenario_id="E08",
    group="E",
    title="A work package the model does not hold is dropped rather than failing",
    feature="Target state · a bad address",
    expected="Opening /target?wp=NOPE, or with the id of an element that is not a work package, "
    "falls back to every work package and renders the page in full instead of erroring.",
)
def test_unknown_work_package(ui, record, finding):
    ui.goto("/target?wp=NOPE")
    ui.must("the page still renders", ui.visible("tg-body"), _brief(ui.body()))
    ui.check("the selector falls back to every work package", _wp(ui) == ALL_WPS, _wp(ui))
    ui.check(
        "with 'Only what changes' on, as if nothing had been asked for",
        _only_changes(ui),
        f"checked={_only_changes(ui)}",
    )
    ui.check(
        "nothing on the page reads as a failure",
        not re.search(r"traceback|error|exception", ui.body(), re.I),
        _brief(ui.body()),
    )
    ui.check("the matrix is drawn all the same", bool(_matrix(ui)[1]))
    ui.check("and so is the view", _card(ui, "Architecture view, marked").count() > 0)
    ui.shot("An address naming a work package that does not exist falls back to every work package")

    ui.goto("/target?wp=PAC-CMS")
    ui.check(
        "an element that is not a work package is dropped the same way",
        _wp(ui) == ALL_WPS,
        _wp(ui),
    )
    ui.check("and the page is the default page again", _only_changes(ui), f"checked={_only_changes(ui)}")
    ui.shot("An address naming an ordinary element is dropped the same way")

    finding.append(
        _finding(
            finding_id="E-1",
            where="src/ea/ui/pages/target.py · render(), the ?wp= parameter",
            severity="usability",
            summary="A work package in the address that the model does not hold is dropped without a word",
            detail=(
                "render() resets the preset to '' when it is not in work_package_options(), so a stale "
                "bookmark or a link to a work package that has since been renamed silently shows the "
                "whole model instead. Impact refuses an unknown element out loud ('Unknown element.'); "
                "Target state should say the same rather than answer a different question."
            ),
        )
    )


@pytest.mark.scenario(
    scenario_id="E09",
    group="E",
    title="The address can carry the work package, and the page arrives set to it",
    feature="Target state · a work package in the address",
    expected="Opening /target?wp=WP-CMS-UPGRADE selects the work package in the picker and starts "
    "with 'Only what changes' already off, and the matrix and the relationships table count that "
    "work package alone rather than the whole model.",
)
def test_a_work_package_in_the_address(ui, record, finding):
    ui.goto("/target")
    whole_elements, whole_relationships, _ = _scope_line(ui)
    every_wp = _rows(_table(ui, 1))
    ui.must(
        "the model's changing relationships are listed to compare against", bool(every_wp), str(every_wp[:1])
    )
    ui.check(
        "among them the one the work package itself makes",
        bool(_row_for(every_wp, WP_NAME)),
        str(_names(every_wp)),
    )

    ui.goto(f"/target?wp={WP}")
    ui.check("the address chose the work package in the picker", WP_NAME in _wp(ui), _wp(ui))
    ui.check(
        "and 'Only what changes' arrives off, as choosing it by hand would leave it",
        not _only_changes(ui),
        f"checked={_only_changes(ui)}",
    )
    elements, relationships, changes = _scope_line(ui)
    ui.check(
        "the scope is the work package, not the model",
        0 < elements < whole_elements and 0 < relationships < whole_relationships,
        f"{elements} of {whole_elements} elements, {relationships} of {whole_relationships} relationships",
    )
    heads, matrix = _matrix(ui)
    ui.must("the matrix is drawn for the work package", bool(matrix), str(heads))
    cells = [c for row in matrix.values() for c in row.values()]
    ui.check(
        "its cells count the work package and nothing else",
        sum(int(c) for c in cells if c.isdigit()) == elements,
        f"{sum(int(c) for c in cells if c.isdigit())} in the matrix, {elements} in scope",
    )
    ui.check(
        "what the work package keeps is counted as kept",
        sum(_cell(row, "keep") for row in matrix.values()) >= len(WP_KEPT),
        str({k: v.get("keep") for k, v in matrix.items()}),
    )
    ui.check(
        "and no cell of it is left undecided",
        all(_cell(row, "undecided") == 0 for row in matrix.values()),
        str({k: v.get("undecided") for k, v in matrix.items()}),
    )
    clipped = _clipped_row_labels(ui)
    ui.check(
        "every row label of the matrix can be read in full",
        not clipped,
        "clipped: " + "; ".join(clipped) if clipped else "",
    )

    scoped = _rows(_table(ui, 1))
    ui.check(
        "the relationships table holds what the work package's scope holds",
        len(scoped) == relationships == _section_count(ui, "Relationships"),
        f"{len(scoped)} rows, {relationships} in scope, heading says {_section_count(ui, 'Relationships')}",
    )
    ui.check(
        "the one that names no work package has dropped out",
        not _row_for(scoped, WP_NAME),
        str(_names(scoped)),
    )
    ui.check(
        "the relationship that breaks when the server goes is still here",
        bool(_row_for(scoped, "Legacy Forms Server")),
        str(_names(scoped)),
    )
    listed = set(_names(_rows(_table(ui, 0))))
    ui.check(
        "and a relationship the work package changes is listed even where its own ends are not",
        bool(_row_for(scoped, "Manager, Curriculum Systems")) and "Manager, Curriculum Systems" not in listed,
        f"listed elements {sorted(listed)}",
    )
    ui.shot("The work package taken from the address: both controls set, and both tables scoped to it")

    rel_heads = [h.lower() for h in _table(ui, 1).locator("thead th").all_inner_texts()]
    if not any("work package" in h for h in rel_heads):
        finding.append(
            _finding(
                finding_id="E-5",
                where="src/ea/ui/pages/target.py · _body(), the relationships table",
                severity="usability",
                summary="The relationships table never says which work package carries the change",
                detail=(
                    "The elements table gives each row its work package, and links from it to the "
                    "page scoped to that package; the relationships table beside it has no such "
                    "column. With every work package in scope the two kinds of row sit together — "
                    "five that name WP-CMS-UPGRADE and one that names no work package at all — and "
                    "nothing on screen tells them apart or leads to the package that owns one."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="E10",
    group="E",
    title="Going back to every work package widens the scope and turns the switch on again",
    feature="Target state · work package",
    expected="Choosing 'All work packages' after a work package restores the whole model and turns "
    "'Only what changes' back on by itself, and the address that scoped the page still scopes it "
    "when it is opened again.",
)
def test_back_to_every_work_package(ui, record, finding):
    ui.goto(f"/target?wp={WP}")
    scoped_elements, scoped_relationships, _ = _scope_line(ui)
    ui.must("the page opened on the work package", WP_NAME in _wp(ui), _wp(ui))

    _choose_wp(ui, ALL_WPS)
    ui.check("the picker goes back to every work package", _wp(ui) == ALL_WPS, _wp(ui))
    ui.check(
        "and 'Only what changes' comes back on by itself",
        _only_changes(ui),
        f"checked={_only_changes(ui)}",
    )
    elements, relationships, changes = _scope_line(ui)
    ui.check(
        "the scope widens back to the whole model",
        elements > scoped_elements and relationships > scoped_relationships,
        f"{elements} elements and {relationships} relationships, from {scoped_elements} and {scoped_relationships}",
    )
    listed = _names(_rows(_table(ui, 0)))
    ui.check(
        "the list is what changes again, not what a package touches",
        _section_count(ui, "Elements") == changes == len(listed),
        f"{len(listed)} listed, {changes} change",
    )
    ui.check(
        "so what the work package merely keeps is out of it",
        not (WP_KEPT & set(listed)),
        str(sorted(WP_KEPT & set(listed))),
    )
    ui.check(
        "and what it changes is still there, under the whole model",
        set(WP_SCOPE) <= set(listed),
        str(sorted(set(WP_SCOPE) - set(listed))),
    )
    ui.shot("Back to every work package: the scope widens and the switch turns itself on again")

    left_behind = ui.page.url
    ui.goto(left_behind)
    ui.check(
        "the address that scoped the page scopes it again when it is opened",
        WP_NAME in _wp(ui) if f"wp={WP}" in left_behind else _wp(ui) == ALL_WPS,
        f"{left_behind} → {_wp(ui)}",
    )
    if f"wp={WP}" in left_behind:
        finding.append(
            _finding(
                finding_id="E-6",
                where="src/ea/ui/pages/target.py · render() and refresh(), the ?wp= parameter",
                severity="usability",
                summary="The address is read on arrival but never follows the picker afterwards",
                detail=(
                    "render() takes the work package from ?wp=, and the elements table hands out "
                    "/target?wp=… links, so the address is how a scope is shared. The picker never "
                    "writes it back: after moving from the work package to 'All work packages' the "
                    "address still reads /target?wp=WP-CMS-UPGRADE, so copying the link, or "
                    "reloading, silently returns to the scope the reader has just left. Browse and "
                    "Impact leave their filters out of the address in the same way, so the fix is "
                    "one the whole application shares."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="E11",
    group="E",
    title="Turning 'Only what changes' off lists the whole model, undecided and all",
    feature="Target state · only what changes",
    expected="With every work package in scope, turning the switch off lists every element and "
    "every relationship the scope holds — the undecided ones included — grouped by target state in "
    "the vocabulary's order, and leaves the badge row, the matrix and the scope sentence untouched.",
)
def test_the_switch_off_on_the_whole_model(ui, record):
    ui.goto("/target")
    elements, relationships, changes = _scope_line(ui)
    badges, matrix = _badges(ui), _matrix(ui)[1]
    changing = _section_count(ui, "Elements")
    ui.must("the page opened on what changes", changing == changes, f"{changing} listed, {changes} change")

    ui.toggle("tg-only-changes", False)
    ui.check("the switch stays where it was put", not _only_changes(ui), f"checked={_only_changes(ui)}")
    ui.check("and the work package picker is left alone", _wp(ui) == ALL_WPS, _wp(ui))
    rows = _rows(_table(ui, 0))
    ui.check(
        "every element in scope is now listed, not only what changes",
        len(rows) == elements > changing,
        f"{len(rows)} rows, {elements} in scope, {changing} of them changing",
    )
    ui.check(
        "the heading counts what is under it",
        _section_count(ui, "Elements") == len(rows),
        f"{_section_count(ui, 'Elements')} in the heading, {len(rows)} rows",
    )
    ui.check(
        "what the model has not decided on is listed too",
        sum(1 for r in rows if _state_of(r[3]) == "undecided") >= 1,
        str(sorted({_state_of(r[3]) for r in rows if r})),
    )
    ui.check(
        "and so is what is merely kept",
        WP_KEPT <= set(_names(rows)),
        str(sorted(WP_KEPT - set(_names(rows)))),
    )
    rel_rows = _rows(_table(ui, 1))
    ui.check(
        "every relationship in scope is listed as well",
        len(rel_rows) == relationships,
        f"{len(rel_rows)} rows, {relationships} in scope",
    )
    ui.check(
        "with its own heading counting them",
        _section_count(ui, "Relationships") == len(rel_rows),
        f"{_section_count(ui, 'Relationships')} in the heading, {len(rel_rows)} rows",
    )
    element_order = _order(rows, 3)
    ui.check(
        "the elements are grouped by target state, in the order the vocabulary reads",
        element_order == sorted(element_order),
        str([TARGET_ORDER[i] for i in element_order][:12]),
    )
    relationship_order = _order(rel_rows, 4)
    ui.check(
        "and the relationships the same way",
        relationship_order == sorted(relationship_order),
        str([TARGET_ORDER[i] for i in relationship_order][:12]),
    )
    ui.check(
        "the matrix counts the scope rather than the list, so the switch leaves it as it was",
        _matrix(ui)[1] == matrix,
        str(_matrix(ui)[1]),
    )
    ui.check("the badge row too", _badges(ui) == badges, f"{_badges(ui)} against {badges}")
    ui.check(
        "and the sentence beneath it says exactly what it said before",
        _scope_line(ui) == (elements, relationships, changes),
        str(_scope_line(ui)),
    )
    ui.shot("Every work package with the switch off: the whole model, undecided artefacts and all")

    ui.toggle("tg-only-changes", True)
    ui.check(
        "turning it back on narrows the list to what changes again",
        _section_count(ui, "Elements") == changes,
        f"{_section_count(ui, 'Elements')} listed, {changes} change",
    )


@pytest.mark.scenario(
    scenario_id="E12",
    group="E",
    title="The view draws what changes and what is kept, and nothing the model has left undecided",
    feature="Target state · the marked view",
    expected="With every work package in scope the diagram holds one shape per element that changes "
    "or is kept — the same elements the table names when the switch is off — and none of the "
    "undecided ones, and the switch changes the list under it rather than the picture.",
)
def test_what_the_view_draws(ui, record):
    ui.goto("/target")
    ui.wait_mermaid()
    badges = _badges(ui)
    elements, _, changes = _scope_line(ui)
    drawn = _drawn_ids(ui)
    ui.must("the view drew something", bool(drawn), str(sorted(drawn))[:140])
    expected = changes + badges.get("keep", 0)
    ui.check(
        "it draws what changes and what is kept, and stops there",
        len(drawn) == min(expected, MAX_NODES),
        f"{len(drawn)} shapes, {changes} change and {badges.get('keep', 0)} are kept",
    )
    ui.check(
        "so the picture is smaller than the model it is cut from",
        len(drawn) < elements,
        f"{len(drawn)} of {elements} elements",
    )

    ui.toggle("tg-only-changes", False)
    ui.wait_mermaid()
    ui.check(
        "the switch changes the list under the view, not the view itself",
        _drawn_ids(ui) == drawn,
        str(sorted(_drawn_ids(ui) ^ drawn)),
    )
    rows = _rows(_table(ui, 0))
    named = [(i, _state_of(r[3])) for i, r in zip(_row_ids(_table(ui, 0)), rows, strict=False) if i and r]
    undecided = {i for i, state in named if state == "undecided"}
    wanted = {i for i, state in named if state and state != "undecided"}
    ui.must(
        "every row of the table names the element it is about",
        len(named) == len(rows),
        f"{len(named)} rows carried an identifier, of {len(rows)}",
    )
    ui.check(
        "nothing the model has not decided on is drawn",
        not (drawn & undecided),
        str(sorted(drawn & undecided)),
    )
    ui.check(
        "and everything that changes or is kept is",
        drawn == wanted if len(wanted) <= MAX_NODES else drawn <= wanted,
        str(sorted(drawn ^ wanted)),
    )
    ui.check(
        "what is kept is drawn beside what changes, so the reader sees what stays",
        "PAC-SRS" in drawn,
        str(sorted(drawn)),
    )
    ui.shot("The whole model's view against the table that names every element behind it")


@pytest.mark.scenario(
    scenario_id="E13",
    group="E",
    title="The view marks the relationships as well as the shapes",
    feature="Target state · the marked view",
    expected="On a work package the generated diagram marks the relationships it changes as well as "
    "the elements: the decommissioned one is drawn red and the new ones green, the work package "
    "itself is the focus of its own view, and the browser paints those colours.",
)
def test_the_view_marks_relationships(ui, record):
    ui.goto(f"/target?wp={WP}")
    ui.wait_mermaid()
    source = _source(ui)
    ui.must("the page keeps the diagram it generated", source.startswith("flowchart"), source[:60])
    ui.check(
        "the decommissioned server's shape is marked as decommissioned",
        "class n_PTC_FORMS st_decommission" in source,
        _brief(source[-400:]),
    )
    for state in ("new", "change", "decommission"):
        ui.check(
            f"a style is defined for what is {state}",
            f"classDef st_{state} " in source,
            _brief(source[-400:]),
        )
    ui.check(
        "and the work package is the focus of its own view",
        "style n_WP_CMS_UPGRADE stroke-width" in source,
        _brief(source[-400:]),
    )
    links = re.findall(r"linkStyle \d+ stroke:(#[0-9a-fA-F]{6})", source)
    ui.check("the relationships are marked too, not only the shapes", bool(links), str(links))
    ui.check(
        "the one that goes with the server is drawn in the decommission colour",
        DECOMMISSION_HEX in links,
        str(links),
    )
    ui.check("and the new ones in the colour for new", NEW_HEX in links, str(links))
    strokes = _edge_strokes(ui)
    ui.must("the browser drew the edges", bool(strokes), str(sorted(strokes)))
    ui.check(
        "and it paints them in those same colours",
        {NEW_RGB, DECOMMISSION_RGB} <= strokes,
        str(sorted(strokes)),
    )
    ui.shot(
        "The work package's view: the relationships marked as well as the shapes",
        selector=VIEW_CARD,
    )


@pytest.mark.scenario(
    scenario_id="E14",
    group="E",
    title="The downloads follow the picker, and the whole model has a draw.io of its own",
    feature="Target state · downloads",
    expected="A work package chosen in the picker rather than the address still names the files, and "
    "Download draw.io with every work package in scope returns target-state-all.drawio holding "
    "exactly the shapes the page draws, each with both its states.",
)
def test_downloads_follow_the_picker(ui, record):
    ui.goto("/target")
    ui.wait_mermaid()
    _choose_wp(ui, WP)
    ui.wait_mermaid()
    ui.must(
        "the work package was chosen without the address ever naming it",
        WP_NAME in _wp(ui) and "wp=" not in ui.page.url,
        f"{_wp(ui)} at {ui.page.url}",
    )
    md = ui.download("tg-view-md", ".md")
    ui.check(
        "the file is named for what the picker holds, not for what the address says",
        md.name == f"target-state-{WP}.md",
        md.name,
    )
    ui.check(
        "and it is the work package's own view",
        f"## Target state of {WP_NAME}" in md.read_text(encoding="utf-8"),
        md.read_text(encoding="utf-8")[:80],
    )
    ui.shot("A work package chosen in the picker alone, and the file it produced named for it")

    ui.goto("/target")
    ui.wait_mermaid()
    drawn = _drawn_ids(ui)
    drawio = ui.download("tg-view-drawio", ".drawio")
    ui.check(
        "the whole model's diagram is named for all of them",
        drawio.name == "target-state-all.drawio",
        drawio.name,
    )
    diagram = drawio.read_text(encoding="utf-8")
    ui.check(
        "it is a draw.io file",
        diagram.lstrip().startswith("<?xml") and "<mxfile" in diagram,
        diagram[:60],
    )
    exported = set(re.findall(r'ea_id="([^"]+)"', diagram))
    ui.check(
        "it holds exactly the shapes the page draws",
        exported == drawn,
        str(sorted(exported ^ drawn)),
    )
    ui.check(
        "every shape carries both of its states",
        diagram.count("ea_target_state=") == diagram.count("ea_id=") == len(exported),
        f"{diagram.count('ea_id=')} shapes, {diagram.count('ea_target_state=')} with a target state",
    )
    ui.check(
        "what is kept is exported beside what changes, though the table beside it lists neither",
        'ea_id="PAC-SRS"' in diagram and 'ea_target_state="keep"' in diagram,
        next((line for line in diagram.splitlines() if "PAC-SRS" in line), "no shape")[:200],
    )
    ui.shot("The whole model's target state taken away as draw.io")


@pytest.mark.scenario(
    scenario_id="E15",
    group="E",
    title="The work package picker searches, and offers work packages only",
    feature="Target state · work package",
    expected="Typing in the picker narrows it to the work packages that match, an ordinary element "
    "of the model is never offered, and a search that matches nothing says so.",
)
def test_the_picker_searches(ui, record, finding):
    ui.goto("/target")
    offered = _wp_options(ui)
    ui.must("the picker offers something to choose", bool(offered), str(offered))
    ui.check(
        "every entry is a work package, named with its identifier",
        all(o == ALL_WPS or o.endswith("]") for o in offered),
        str(offered),
    )
    ui.check(
        "an ordinary element of the model is not among them",
        not any("[PAC-" in o or "[PTC-" in o or "[DE-" in o for o in offered),
        str(offered),
    )

    matching = _search_options(ui, "Upgrade")
    ui.check(
        "typing part of a name narrows the list to it",
        WP_OPTION in matching and ALL_WPS not in matching,
        str(matching),
    )
    by_id = _search_options(ui, WP)
    ui.check("and the identifier finds it just as well", WP_OPTION in by_id, str(by_id))
    ui.shot("The picker searched by name: the work packages that match, and nothing else")

    missing = _search_options(ui, "PAC-CMS")
    ui.check(
        "an element that is not a work package cannot be searched into the picker",
        not missing,
        str(missing),
    )
    said = _dropdown_text(ui)
    ui.check(
        "and a search that matches nothing says so rather than showing an empty box",
        bool(said),
        f"the dropdown reads {said!r}",
    )
    ui.shot("A search that matches nothing: the picker answers with an empty box")
    ui.page.keyboard.press("Escape")
    ui.settle()
    if not said:
        finding.append(
            _finding(
                finding_id="E-7",
                where="src/ea/ui/pages/target.py · render(), the work package Select",
                severity="consistency",
                summary="The work package picker says nothing when a search matches nothing",
                detail=(
                    "The picker is searchable but carries no nothingFoundMessage, so typing "
                    "'PAC-CMS' — an element that exists but is not a work package — leaves an empty "
                    "dropdown and no word about why. The same control on Impact "
                    "(src/ea/ui/pages/impact.py) and on an element's relationship form answers "
                    "'Type to search' in the same situation, and both carry a placeholder saying "
                    "what may be typed; this one has neither."
                ),
            )
        )


@pytest.mark.scenario(
    scenario_id="E16",
    group="E",
    title="The page leads on to the branches, and its work package link scopes it",
    feature="Target state · where it leads",
    expected="The Branches button beside the title opens the branches page, and the work package "
    "link in the elements table reloads Target state scoped to that work package.",
)
def test_where_the_page_leads(ui, record):
    ui.goto("/target")
    branches = ui.page.locator("#page a[href='/branches']").first
    ui.must("the page offers the branches beside its title", branches.count() > 0, ui.text("#page h1"))
    ui.check(
        "the button says what it opens",
        "Branches" in branches.inner_text(),
        branches.inner_text().strip(),
    )
    branches.click()
    ui.settle()
    ui.check("it opens the branches page", ui.page.url.endswith("/branches"), ui.page.url)
    ui.check(
        "and the branches page is what arrived",
        ui.text("#page h1") == "Branches",
        ui.text("#page h1"),
    )
    ui.shot("The Branches button beside the title opens the page that carries the work")

    ui.goto("/target")
    link = _table(ui, 0).locator(f"a[href='/target?wp={WP}']").first
    ui.must("the elements table links to the work package that will do the work", link.count() > 0)
    link.click()
    ui.settle()
    ui.check("following it scopes the page to that work package", WP_NAME in _wp(ui), _wp(ui))
    ui.check(
        "with 'Only what changes' off, as the address asks",
        not _only_changes(ui),
        f"checked={_only_changes(ui)}",
    )
    ui.check(
        "and what the work package keeps listed with what it changes",
        WP_KEPT <= set(_names(_rows(_table(ui, 0)))),
        str(sorted(WP_KEPT - set(_names(_rows(_table(ui, 0)))))),
    )
    ui.shot("The work package link from the table, followed to the page scoped to it")
