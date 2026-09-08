"""Group K — Health: freshness per source system, completeness per type, and the link behind every figure.

The page makes one promise in its own subtitle — *every number is a link to the rows behind
it* — so most of this group is spent taking a figure, following it into Browse, and checking
that the grid it lands on holds exactly the rows the figure counted.

Nothing here asserts an absolute total: the round shares one database and the groups before
this one create and edit elements. Every figure is read from the page at the moment it is
used, and compared with what Browse then shows. The one element this group creates is named
with a `K-` prefix so it cannot collide with another group's data, and the branch K16 measures
on is drafted on, never merged, so main carries only what K07 put there.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.gui

FRESHNESS, COMPLETENESS = 0, 1  # the two tables inside #health-body, in the order they are drawn
FRESH_COLUMNS = (
    "source",
    "elements",
    "relationships",
    "first loaded",
    "last updated",
    "stale 30 d",
    "stale 90 d",
    "stale 180 d",
    "never updated",
)
SOURCE, ELEMENTS, RELATIONSHIPS, FIRST_LOADED, LAST_UPDATED = 0, 1, 2, 3, 4
STALE_30, STALE_90, STALE_180, NEVER_UPDATED = 5, 6, 7, 8
STALE_COLUMNS = ((STALE_30, 30), (STALE_90, 90), (STALE_180, 180))
FACET_COLUMNS = ("Description", "Link", "Relationship", "Required attributes", "Target decided")
# What the totals above the table say of each column: a sentence about the rows it counts,
# in the words Browse uses for those rows, rather than the heading pressed into service as
# a noun — '5 target decided missing' said the opposite of what it counted.
FACET_TOTALS = {
    "Description": "without a description",
    "Link": "without a link",
    "Relationship": "without a relationship",
    "Required attributes": "with a required attribute empty",
    "Target decided": "with an undecided target state",
}
# What Browse writes in its yellow note for each facet a Health figure can send it.
FACET_NOTES = {
    "description": "without a description",
    "links": "without a link",
    "relationships": "without a relationship",
    "attributes": "with a required attribute empty",
    "target": "with an undecided target state",
    "never_updated": "never updated since the import",
}
SEEDED_SOURCE = "sample"  # the round's own seed loads the sample model under this source system
AUTHORED = "(authored)"  # where the page groups elements that came from no source system

# One pass over the completeness table: what each type row says, and the link behind each figure.
COMPLETENESS_JS = """
t => Array.from(t.querySelectorAll('tbody tr')).map(tr => {
  const tds = Array.from(tr.querySelectorAll('td'));
  const a0 = tds[0].querySelector('a');
  return {
    type: a0 ? a0.innerText.trim() : tds[0].innerText.trim(),
    type_href: a0 ? a0.getAttribute('href') : null,
    elements: tds[1].innerText.trim(),
    facets: tds.slice(2).map(td => {
      const bar = td.querySelector('[role="progressbar"]');
      const a = td.querySelector('a');
      return {
        text: td.innerText.trim().replace(/\\s+/g, ' '),
        aria: bar ? bar.getAttribute('aria-valuenow') : null,
        href: a ? a.getAttribute('href') : null,
        label: a ? a.innerText.trim() : '',
      };
    }),
  };
})
"""


# --------------------------------------------------------------------------------- helpers


def _open_health(ui) -> None:
    ui.goto("/health")
    ui.page.wait_for_selector("#health-body table", timeout=20_000)
    ui.settle()


def _table(ui, index: int):
    return ui.page.locator("#health-body table").nth(index)


def _headers(ui, index: int) -> list[str]:
    return [h.strip() for h in _table(ui, index).locator("thead th").all_inner_texts()]


def _rows(ui, index: int) -> list[list[str]]:
    return (
        _table(ui, index)
        .locator("tbody tr")
        .evaluate_all(
            "rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim()))"
        )
    )


def _cell(ui, index: int, row: int, col: int):
    return _table(ui, index).locator("tbody tr").nth(row).locator("td").nth(col)


def _href(cell) -> str | None:
    link = cell.locator("a")
    return link.first.get_attribute("href") if link.count() else None


def _fresh_row(ui, source: str) -> int | None:
    """The index of the freshness row for one source system, or None when it has none."""
    for i, row in enumerate(_rows(ui, FRESHNESS)):
        if row and row[SOURCE] == source:
            return i
    return None


def _fresh_figures(ui, source: str) -> list[str]:
    i = _fresh_row(ui, source)
    return _rows(ui, FRESHNESS)[i] if i is not None else []


def _number(text: str) -> int:
    match = re.search(r"-?\d+", (text or "").replace(",", ""))
    return int(match.group()) if match else -1


def _section_titles(ui) -> list[str]:
    """The section headings, lower-cased: the stylesheet renders them in capitals."""
    return [t.strip().lower() for t in ui.page.locator("#health-body .ea-section-title").all_inner_texts()]


def _completeness_total(ui) -> int:
    """The element count the completeness heading claims to have measured."""
    for title in _section_titles(ui):
        match = re.search(r"completeness\D+(\d+)\s+element", title)
        if match:
            return int(match.group(1))
    return -1


def _browse_counts(ui) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+) of (\d+)", ui.text("browse-count"))
    return (int(match.group(1)), int(match.group(2))) if match else (-1, -1)


def _follow(ui, locator) -> None:
    """A figure on Health is a plain anchor, so following one loads Browse afresh."""
    locator.click()
    ui.page.wait_for_url(re.compile(r"/browse"), timeout=20_000)
    ui.page.wait_for_selector("#browse-grid", state="attached")
    ui.page.wait_for_timeout(400)
    ui.settle()


def _subtitle(ui) -> str:
    """The sentence under the page title, which names the branch the figures were taken on."""
    return ui.page.evaluate(
        "() => { const h = document.querySelector('#page h1');"
        " const p = h && h.parentElement.querySelector('p'); return p ? p.innerText.trim() : ''; }"
    )


def _as_of(ui) -> str:
    """The moment the freshness figures say they were taken, as an ISO stamp to the minute."""
    for title in _section_titles(ui):
        match = re.search(r"as of (\d{4}-\d{2}-\d{2})[t ](\d{2}:\d{2})", title)
        if match:
            return f"{match.group(1)}T{match.group(2)}"
    return ""


def _newest_change(ui) -> str:
    """The most recent 'last updated' the freshness table shows, in the same shape as the stamp."""
    stamps = [row[LAST_UPDATED].strip().replace(" ", "T")[:16] for row in _rows(ui, FRESHNESS)]
    return max((s for s in stamps if s), default="")


def _a_minute_before(stamp: str) -> str:
    """One minute of slack, so a recompute that straddles the turn of a minute is not a failure."""
    moment = datetime.fromisoformat(stamp) - timedelta(minutes=1)
    return moment.strftime("%Y-%m-%dT%H:%M")


def _finding(finding_id: str, where: str, severity: str, summary: str, detail: str):
    from tests.ui.evidence import Finding

    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


def _every(ui, name: str, offenders: list[str], summary: str) -> None:
    """One check over every cell of a table, naming the cells that broke it rather than all of them."""
    ui.check(name, not offenders, "; ".join(offenders[:6]) if offenders else summary)


def _selected_type(ui) -> str:
    return ui.page.evaluate(
        "() => { const e = document.querySelector('#browse-type'); return e ? (e.value ?? e.innerText) : ''; }"
    )


def _create_elsewhere(ui, name: str) -> str:
    """Create an element in a second tab, so a figure on Health goes out of date without a reload."""
    page = ui.page.context.new_page()
    try:
        page.goto(ui.base_url + "/browse", wait_until="domcontentloaded")
        page.wait_for_selector("#new-open", timeout=20_000)
        page.wait_for_timeout(900)
        page.locator("#new-open").click()
        page.wait_for_selector("#new-modal-body", timeout=10_000)
        page.locator("#new-type").click()
        # Whatever type the metamodel still offers: an earlier group may have renamed or
        # retired the one this scenario would otherwise have named.
        options = page.locator("[role='option']")
        preferred = options.filter(has_text=re.compile(r"^Capability$"))
        (preferred if preferred.count() else options).first.click()
        page.locator("#new-name").fill(name)
        page.locator("#new-save").click()
        deadline = time.time() + 20
        while time.time() < deadline and "/element/" not in page.url:
            page.wait_for_timeout(200)
        return page.url.rsplit("/", 1)[-1] if "/element/" in page.url else ""
    finally:
        page.close()
        ui.page.bring_to_front()


# ------------------------------------------------------------------------------ the page


@pytest.mark.scenario(
    scenario_id="K01",
    group="K",
    title="Health opens with freshness, activity, completeness and the unused relationship types",
    feature="Health · the page",
    expected="The page names the branch it measured, offers Recompute, and draws four sections; the "
    "freshness table carries a column per figure and a row per source system.",
)
def test_health_opens(ui, record):
    _open_health(ui)
    ui.must("the health body rendered", ui.visible("health-body"))
    # The page title is the one h1 (`page_title` draws it as `order=1, size="h2"`); the h2s
    # below it are the section headings, so `h2` first reads 'Freshness · as of …'.
    heading = ui.page.locator("#page h1").first.inner_text().strip()
    ui.check("the page is titled Health", heading == "Health", heading)
    subtitle = _subtitle(ui)
    ui.check("the subtitle says which branch was measured", "on main" in subtitle, subtitle)
    ui.check("Recompute is offered", ui.visible("health-refresh") and not ui.disabled("health-refresh"))
    ui.check(
        "freshness and completeness are two cards",
        ui.page.locator("#health-body .ea-card").count() == 2,
        f"{ui.page.locator('#health-body .ea-card').count()} card(s)",
    )

    titles = _section_titles(ui)
    for wanted in ("freshness", "change activity", "completeness", "relationship types with no instance"):
        ui.check(f"there is a '{wanted}' section", any(wanted in t for t in titles), str(titles))
    ui.check(
        "freshness says when it was computed",
        any(re.search(r"freshness .*as of \d{4}-\d{2}-\d{2}", t) for t in titles),
        str(titles),
    )

    headers = _headers(ui, FRESHNESS)
    ui.check("the freshness table has a column per figure", headers == list(FRESH_COLUMNS), str(headers))
    rows = _rows(ui, FRESHNESS)
    ui.must("there is a row per source system", len(rows) >= 1, f"{len(rows)} row(s)")
    ui.check("every row names its source", all(r[SOURCE] for r in rows), str([r[SOURCE] for r in rows]))

    seeded = _fresh_figures(ui, SEEDED_SOURCE)
    ui.must(
        f"the imported model is grouped under '{SEEDED_SOURCE}'", bool(seeded), str([r[SOURCE] for r in rows])
    )
    ui.check("it counts its elements", _number(seeded[ELEMENTS]) > 0, seeded[ELEMENTS])
    ui.check("it counts its relationships", _number(seeded[RELATIONSHIPS]) > 0, seeded[RELATIONSHIPS])
    ui.check("it says when it was first loaded", bool(seeded[FIRST_LOADED].strip()), seeded[FIRST_LOADED])
    ui.check("it says when a row last moved", bool(seeded[LAST_UPDATED].strip()), seeded[LAST_UPDATED])
    ui.check(
        "the table explains what a stale figure counts",
        "30, 90 and 180 days" in ui.text("health-body"),
        ui.text("health-body")[:200].replace("\n", " · "),
    )
    ui.shot("Health opens on the freshness table, one row per source system, every figure beside it")


@pytest.mark.scenario(
    scenario_id="K02",
    group="K",
    title="Change activity draws a bar per week and names the changes behind one",
    feature="Health · change activity",
    expected="The chart draws one bar for each of the twelve weeks it names, labels each with its week "
    "number, colours the weeks that saw a change, and a bar's tooltip says how many changes and of what kind.",
)
def test_change_activity(ui, record):
    _open_health(ui)
    titles = _section_titles(ui)
    ui.must(
        "the chart says what period it covers",
        any("change activity, last 12 weeks" in t for t in titles),
        str(titles),
    )
    bars = ui.page.locator('#health-body div[style*="width: 22px"]')
    count = bars.count()
    ui.must("the chart drew its bars", count > 0, f"{count} bar(s)")
    # The heading says twelve weeks and the chart draws thirteen bars: activity() in
    # src/ea/services/health.py walks from `now - 12 weeks` to `now` inclusive, so the
    # current part-week is drawn as a thirteenth column under a heading that excludes it.
    ui.check("the chart draws one bar for each of the twelve weeks it names", count == 12, f"{count} bars")

    labels = bars.evaluate_all("ds => ds.map(d => d.parentElement.innerText.trim())")
    ui.check(
        "every bar is labelled with its week", all(re.fullmatch(r"W\d{1,2}", x) for x in labels), str(labels)
    )
    ui.check("no week is drawn twice", len(set(labels)) == len(labels), str(labels))

    colours = bars.evaluate_all("ds => ds.map(d => d.style.background)")
    busy = [c for c in colours if "233, 236, 239" not in c]
    ui.check("a week with changes is coloured apart from a quiet one", len(busy) >= 1, str(colours[-3:]))
    heights = bars.evaluate_all("ds => ds.map(d => parseInt(d.style.height))")
    ui.check("the busiest week is the tallest bar", max(heights) > min(heights), str(heights))

    bars.nth(count - 1).hover()
    ui.page.wait_for_timeout(700)
    tip = ui.page.locator('[class*="Tooltip-tooltip"], [role="tooltip"]')
    text = tip.first.inner_text().strip() if tip.count() else ""
    ui.check("hovering a bar names its week", bool(re.search(r"\d{4}-W\d{2}", text)), text or "(no tooltip)")
    ui.check("and says how many changes it holds", "change(s)" in text, text or "(no tooltip)")
    ui.shot("The change-activity chart, with the tooltip of the most recent week open")


# -------------------------------------------------------------------- following the figures


@pytest.mark.scenario(
    scenario_id="K03",
    group="K",
    title="The never-updated figure opens the rows it counted",
    feature="Health · freshness links",
    expected="The never-updated count on a source row is a link carrying missing=never_updated and the "
    "source; Browse arrives with the yellow note naming both, and holds exactly that many rows.",
)
def test_never_updated_link(ui, record):
    _open_health(ui)
    row = _fresh_row(ui, SEEDED_SOURCE)
    ui.must(f"the '{SEEDED_SOURCE}' source has a row", row is not None)
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    figure = _number(cell.inner_text())
    ui.must("it counts rows never touched since the import", figure > 0, cell.inner_text())
    href = _href(cell)
    ui.must("the figure is a link", bool(href), href or "(no link)")
    ui.check("the link carries the facet", "missing=never_updated" in href, href)
    ui.check("and the source system it counted", f"source={SEEDED_SOURCE}" in href, href)
    ui.shot("The never-updated figure on the freshness table is a link into Browse")

    _follow(ui, cell.locator("a").first)
    ui.check("Browse was asked for that facet", "missing=never_updated" in ui.page.url, ui.page.url)
    note = ui.text("browse-filter-note")
    ui.check("the note says what is being shown", FACET_NOTES["never_updated"] in note, note or "(no note)")
    ui.check("the note names the source", f"from source {SEEDED_SOURCE}" in note, note or "(no note)")
    ui.check("the note says where the filter came from", "from the Health page" in note, note or "(no note)")
    shown, total = _browse_counts(ui)
    ui.check(
        "Browse holds exactly the rows the figure counted",
        shown == figure,
        f"the figure said {figure}, Browse shows {shown} of {total}",
    )
    ui.check("and the rows are rendered", ui.grid_row_count("browse-grid") > 0)
    ui.shot("Following it lands on Browse filtered to those rows, with the yellow note saying so")


@pytest.mark.scenario(
    scenario_id="K04",
    group="K",
    title="Completeness draws a bar per facet, a link per gap, and names the unused relationship types",
    feature="Health · completeness",
    expected="Every type row carries five facets; each shows a progress bar whose value matches its "
    "percentage and either offers the rows it is missing or says it is complete; the badges above the "
    "table total the columns beneath them, and one badge per relationship type nothing uses names it "
    "with the two types it would join.",
)
def test_completeness_table(ui, record):
    _open_health(ui)
    headers = _headers(ui, COMPLETENESS)
    ui.check(
        "the table has a column per facet",
        headers == ["type", "elements", *FACET_COLUMNS],
        str(headers),
    )
    rows = _table(ui, COMPLETENESS).evaluate(COMPLETENESS_JS)
    ui.must("there is a row per element type with content", len(rows) > 0, f"{len(rows)} row(s)")
    cells = [
        (row, name, facet) for row in rows for name, facet in zip(FACET_COLUMNS, row["facets"], strict=False)
    ]
    # One check per cell would be two hundred lines of report for a table a reader takes in at
    # a glance, so each rule is checked over every cell at once and names the cells that broke it.
    shape = f"{len(rows)} types × {len(FACET_COLUMNS)} facets"

    _every(
        ui,
        "every type is measured on all five facets",
        [f"{r['type']} has {len(r['facets'])}" for r in rows if len(r["facets"]) != 5],
        shape,
    )
    _every(
        ui,
        "every type counts its elements and links to its own rows",
        [
            f"{r['type']} → {r['type_href']!r}, {r['elements']!r}"
            for r in rows
            if not (r["type_href"] or "").startswith("/browse?type=") or _number(r["elements"]) <= 0
        ],
        shape,
    )
    _every(
        ui,
        "every facet draws a progress bar",
        [f"{r['type']} · {n}: {f['text']}" for r, n, f in cells if f["aria"] is None],
        f"{len(cells)} bars",
    )
    _every(
        ui,
        "every bar is drawn at the percentage printed beside it",
        [
            f"{r['type']} · {n}: printed {_number(f['text'])}%, bar at {f['aria']}"
            for r, n, f in cells
            if f["aria"] != str(_number(f["text"]))
        ],
        f"{len(cells)} bars",
    )
    gaps = [(r, n, f) for r, n, f in cells if f["href"]]
    _every(
        ui,
        "every gap says how many are missing and opens exactly those rows",
        [
            f"{r['type']} · {n}: {f['label']!r} → {f['href']!r}"
            for r, n, f in gaps
            if not re.fullmatch(r"\d+ missing", f["label"])
            or f"type={r['type_href'].split('type=')[-1]}" not in f["href"]
            or "missing=" not in f["href"]
        ],
        f"{len(gaps)} gaps, each a link",
    )
    _every(
        ui,
        "every facet with nothing missing says it is complete, at a hundred per cent",
        [
            f"{r['type']} · {n}: {f['text']}"
            for r, n, f in cells
            if not f["href"] and not ("complete" in f["text"] and _number(f["text"]) == 100)
        ],
        f"{len(cells) - len(gaps)} complete",
    )

    totals = dict.fromkeys(FACET_COLUMNS, 0)
    for _row, name, facet in gaps:
        totals[name] += _number(facet["label"])
    body = ui.text("health-body").lower()
    for name in FACET_COLUMNS:
        match = re.search(rf"(\d+)\s+{re.escape(FACET_TOTALS[name])}", body)
        ui.check(f"a badge totals the {name} column", match is not None, name)
        if match:
            ui.check(
                f"the {name} badge agrees with the column beneath it",
                int(match.group(1)) == totals[name],
                f"badge {match.group(1)}, column {totals[name]}",
            )
    ui.shot("The completeness table: a bar, a percentage and a way to the missing rows for every facet")

    # The same card ends with the relationship types the metamodel declares and no content uses.
    heading = next((t for t in _section_titles(ui) if "relationship types with no instance" in t), "")
    ui.must("the card names the relationship types nothing uses", bool(heading), str(_section_titles(ui)))
    declared = _number(heading)
    badges = ui.page.locator('#health-body [class*="Badge-root"][data-variant="outline"]')
    labels = [b.strip() for b in badges.all_inner_texts()]
    if declared:
        ui.check(
            "there is a badge for each one, up to the sixty it shows",
            len(labels) == min(declared, 60),
            f"the heading says {declared}, {len(labels)} badge(s)",
        )
        _every(
            ui,
            "every badge names the type and the two types it would join",
            [x for x in labels if not re.fullmatch(r".+\(.+ → .+\)", x)],
            f"{len(labels)} badges, e.g. {labels[0]!r}" if labels else "",
        )
        _every(
            ui,
            "no two badges read the same, so a name used twice is still told apart",
            [x for x in labels if labels.count(x) > 1],
            f"{len(set(labels))} distinct",
        )
    else:
        ui.check(
            "with nothing to list it says every type is used",
            "every relationship type has at least one instance" in ui.text("health-body").lower(),
            ui.text("health-body")[-160:].replace("\n", " · "),
        )
    ui.shot("The relationship types the metamodel declares and no content uses")


@pytest.mark.scenario(
    scenario_id="K05",
    group="K",
    title="A 'N missing' figure opens the rows of that type that lack the facet",
    feature="Health · completeness links",
    expected="Following a 'N missing' link lands on Browse with the type preselected, the yellow note "
    "naming the facet, and exactly N rows.",
)
def test_missing_link(ui, record):
    _open_health(ui)
    rows = _table(ui, COMPLETENESS).evaluate(COMPLETENESS_JS)
    picked = None
    for r_index, row in enumerate(rows):
        for f_index, facet in enumerate(row["facets"]):
            if facet["href"] and (picked is None or "missing=target" in facet["href"]):
                picked = (r_index, f_index, row, facet)
                if "missing=target" in facet["href"]:
                    break
        if picked and "missing=target" in picked[3]["href"]:
            break
    ui.must(
        "some type is missing something to follow",
        picked is not None,
        picked[3]["href"] if picked else "every facet of every type is complete",
    )
    r_index, f_index, row, facet = picked
    figure = _number(facet["label"])
    facet_key = facet["href"].split("missing=")[-1].split("&")[0]
    ui.check("the link carries the type and the facet", "type=" in facet["href"], facet["href"])
    ui.shot(f"The completeness row for {row['type']}, with its missing figures as links")

    cell = _cell(ui, COMPLETENESS, r_index, 2 + f_index)
    _follow(ui, cell.locator("a").first)
    ui.check("Browse was asked for that facet", f"missing={facet_key}" in ui.page.url, ui.page.url)
    note = ui.text("browse-filter-note")
    ui.check(
        f"the note says the rows lack {facet_key}",
        FACET_NOTES[facet_key] in note,
        note or "(no note)",
    )
    ui.check("the note says where the filter came from", "from the Health page" in note, note or "(no note)")
    selected = _selected_type(ui)
    ui.check(
        "Browse arrives with the type already chosen",
        row["type"] in selected,
        f"the figure was on {row['type']}, Browse shows {selected!r}",
    )
    shown, total = _browse_counts(ui)
    ui.check(
        "Browse holds exactly the rows the figure counted",
        shown == figure,
        f"the figure said {figure}, Browse shows {shown} of {total}",
    )
    ui.shot("Browse arrives filtered to the elements of that type that lack the facet")


@pytest.mark.scenario(
    scenario_id="K06",
    group="K",
    title="Staleness is counted over three windows, and the window travels into Browse",
    feature="Health · staleness",
    expected="Each source row carries a 30, 90 and 180 day figure; a figure that counts something is a "
    "link carrying missing=stale and its days, a zero is plain text, and the address behind the 180 day "
    "window shows Browse the same number the page did.",
)
def test_stale_windows(ui, record):
    _open_health(ui)
    headers = _headers(ui, FRESHNESS)
    for column, days in STALE_COLUMNS:
        ui.check(f"there is a {days} day column", headers[column] == f"stale {days} d", headers[column])
    row = _fresh_row(ui, SEEDED_SOURCE)
    ui.must(f"the '{SEEDED_SOURCE}' source has a row", row is not None)

    figures: dict[int, int] = {}
    for column, days in STALE_COLUMNS:
        cell = _cell(ui, FRESHNESS, row, column)
        figures[days] = _number(cell.inner_text())
        href = _href(cell)
        ui.check(f"the {days} day figure is a number", figures[days] >= 0, cell.inner_text())
        if figures[days]:
            ui.check(f"the {days} day figure is a link", bool(href), href or "(no link)")
            ui.check(
                f"the {days} day link carries its window",
                f"missing=stale&days={days}" in (href or ""),
                href or "",
            )
        else:
            # Nothing has aged in a round that seeds its own database minutes earlier, so the
            # link cannot be clicked; a zero is deliberately not a link to an empty grid.
            ui.check(f"a {days} day figure of zero is not a link", href is None, href or "(none)")
    ui.check(
        "a longer window can never count more than a shorter one",
        figures[180] <= figures[90] <= figures[30],
        str(figures),
    )
    ui.shot("The three staleness windows on the freshness table, and what each of them counts")

    # The address the page builds for the 180 day window, followed by hand because the figure
    # behind it is zero on a freshly seeded round.
    ui.goto(f"/browse?missing=stale&days=180&source={SEEDED_SOURCE}")
    note = ui.text("browse-filter-note")
    ui.check(
        "Browse says which window it is showing",
        "not updated for 180 days or more" in note,
        note or "(no note)",
    )
    ui.check("and which source", f"from source {SEEDED_SOURCE}" in note, note or "(no note)")
    shown, _ = _browse_counts(ui)
    ui.check(
        "Browse shows the same number the freshness table did",
        shown == figures[180],
        f"Health said {figures[180]}, Browse shows {shown}",
    )
    ui.check(
        "an empty result still offers the way back to the whole model",
        ui.page.locator("#browse-filter-note a").count() > 0,
    )
    ui.shot("The 180 day window in Browse: no rows, and the note that says why")


# ------------------------------------------------------- authored rows, and recomputing


@pytest.mark.scenario(
    scenario_id="K07",
    group="K",
    title="Recompute picks up an element created after the page was drawn",
    feature="Health · Recompute",
    expected="An element created in another tab does not change the figures until Recompute is pressed; "
    "then the completeness total grows by one and the new element is grouped under (authored).",
)
def test_recompute(ui, record):
    _open_health(ui)
    before_total = _completeness_total(ui)
    ui.must("the completeness heading counts the elements it measured", before_total > 0, str(before_total))
    before = _fresh_figures(ui, AUTHORED)
    before_elements = _number(before[ELEMENTS]) if before else 0
    before_never = _number(before[NEVER_UPDATED]) if before else 0

    made = _create_elsewhere(ui, "K-authored-probe")
    ui.must("an element was created in the other tab", bool(made), made or "(no element opened)")
    ui.check(
        "the figures do not change on their own",
        _completeness_total(ui) == before_total,
        f"{_completeness_total(ui)} against {before_total}",
    )
    ui.shot("Health still shows the figures it was drawn with, an element having been created elsewhere")

    ui.click("health-refresh")
    ui.check(
        "Recompute counts the new element",
        _completeness_total(ui) == before_total + 1,
        f"{_completeness_total(ui)} after {before_total}",
    )
    after = _fresh_figures(ui, AUTHORED)
    ui.must(
        f"an element with no source system is grouped under {AUTHORED}",
        bool(after),
        str(_rows(ui, FRESHNESS)),
    )
    ui.check(
        f"the {AUTHORED} row grew by one element",
        _number(after[ELEMENTS]) == before_elements + 1,
        f"{after[ELEMENTS]} after {before_elements}",
    )
    ui.check(
        "and counts it as never updated since it was written",
        _number(after[NEVER_UPDATED]) == before_never + 1,
        f"{after[NEVER_UPDATED]} after {before_never}",
    )
    ui.check("the page kept its four sections", len(_section_titles(ui)) == 4, str(_section_titles(ui)))
    ui.shot("Recompute redraws the page and the new element appears under (authored)")


@pytest.mark.scenario(
    scenario_id="K08",
    group="K",
    title="The (authored) figure opens the authored rows, not everybody's",
    feature="Health · freshness links",
    expected="The never-updated figure on the (authored) row links to the rows it counted, and Browse "
    "arrives holding exactly that many.",
)
def test_authored_link(ui, record):
    _open_health(ui)
    row = _fresh_row(ui, AUTHORED)
    ui.must(
        f"there is an {AUTHORED} row to follow",
        row is not None,
        str([r[SOURCE] for r in _rows(ui, FRESHNESS)]),
    )
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    figure = _number(cell.inner_text())
    ui.must("it counts authored rows never updated", figure > 0, cell.inner_text())
    href = _href(cell)
    ui.must("the figure is a link", bool(href), href or "(no link)")
    ui.check("the link carries the facet", "missing=never_updated" in href, href)
    # The page builds this link without a source, so it opens every source's never-updated rows
    # rather than the authored ones the figure counted: _freshness() in src/ea/ui/pages/health.py
    # writes `q = "" if src == "(authored)"`, although HealthService.ids_for() filters on
    # "(authored)" perfectly well. The figure and the grid it opens disagree.
    ui.check("and the source system it counted", "source=" in href, href)
    ui.shot("The (authored) row on the freshness table, and the link behind its figure")

    _follow(ui, cell.locator("a").first)
    note = ui.text("browse-filter-note")
    ui.check("the note says what is being shown", FACET_NOTES["never_updated"] in note, note or "(no note)")
    shown, total = _browse_counts(ui)
    ui.check(
        "Browse holds exactly the rows the figure counted",
        shown == figure,
        f"the figure said {figure}, Browse shows {shown} of {total}",
    )
    ui.shot("Browse after following the (authored) figure, with the number it arrived at")


@pytest.mark.scenario(
    scenario_id="K09",
    group="K",
    title="Freshness is measured against the present, not the moment the application started",
    feature="Health · freshness",
    expected="Recomputing stamps the page with the moment it was recomputed, so the 'as of' stamp — and "
    "the three staleness windows counted back from it — are never older than the changes the same table "
    "is showing.",
)
def test_as_of_moves_with_the_clock(ui, record, finding):
    # The stamp is HealthService.now, and the service is built once: get_context() in
    # src/ea/ui/context.py caches one AppContext for the process, so `now` is frozen at the
    # first request. Recompute redraws the figures but cannot move the clock they are measured
    # against, and on a server that stays up for weeks "not updated for 30 days" quietly means
    # "for 30 days before the application started".
    _open_health(ui)
    ui.click("health-refresh")
    stamp = _as_of(ui)
    ui.must("the page says when the figures were taken", bool(stamp), stamp or "(no stamp)")
    newest = _newest_change(ui)
    ui.must("the table shows when its rows last moved", bool(newest), newest or "(no timestamp)")
    # The browser and the application both keep UTC in this round, so the clock in the page is
    # the clock the stamp should have been taken from.
    clock = ui.page.evaluate("() => new Date().toISOString().slice(0, 16)")
    ui.check(
        "recomputing stamps the page with the moment it was recomputed",
        stamp >= _a_minute_before(clock),
        f"stamped as of {stamp}, recomputed at {clock}",
    )
    ui.check(
        "and never earlier than a change the same table is showing",
        stamp >= newest,
        f"stamped as of {stamp}, showing a change made at {newest}",
    )
    if stamp < _a_minute_before(clock) or stamp < newest:
        finding.append(
            _finding(
                finding_id="K-1",
                where="src/ea/ui/pages/health.py · Freshness · as of, and src/ea/services/health.py",
                severity="defect",
                summary="Freshness is measured against the moment the application started, not the present, "
                "and Recompute cannot move it.",
                detail=f"The page was recomputed at {clock} and stamped 'as of {stamp}', with the same "
                f"table showing a row last updated at {newest}. HealthService.now is set when the service "
                "is built, and "
                "get_context() keeps one AppContext for the life of the process, so the 30, 90 and 180 day "
                "windows are counted back from the application's start time. On a long-running server the "
                "staleness figures drift by however long it has been up.",
            )
        )
    ui.shot("The freshness stamp after a recompute, beside the change the same table is showing")


# ------------------------------------------------- what the figures are counted from, and where they lead

# The type column of the completeness table: the name, the domain badge beside it, and the count.
TYPE_CELL_JS = """
t => Array.from(t.querySelectorAll('tbody tr')).map(tr => {
  const tds = Array.from(tr.querySelectorAll('td'));
  const a = tds[0].querySelector('a');
  const badge = tds[0].querySelector('[class*="Badge-root"]');
  return {
    type: a ? a.innerText.trim() : tds[0].innerText.trim(),
    href: a ? a.getAttribute('href') : null,
    domain: badge ? badge.innerText.trim() : '',
    elements: parseInt(tds[1].innerText.trim(), 10),
  };
})
"""

# Every progress bar in the completeness table, with the colour the browser resolved for it.
BAR_JS = """
t => Array.from(t.querySelectorAll('tbody tr')).flatMap(tr => {
  const tds = Array.from(tr.querySelectorAll('td'));
  const name = (tds[0].querySelector('a') || tds[0]).innerText.trim();
  return tds.slice(2).map((td, i) => {
    const bar = td.querySelector('[role="progressbar"]');
    const link = td.querySelector('a');
    return {
      type: name,
      facet: i,
      pct: bar ? parseInt(bar.getAttribute('aria-valuenow'), 10) : -1,
      colour: bar ? getComputedStyle(bar).backgroundColor : '',
      text: td.innerText.trim().replace(/\\s+/g, ' '),
      missing: link ? link.innerText.trim() : '',
    };
  });
})
"""

BRANCH_NAME = "K-health-branch"  # the group's own branch: drafted on, never merged
BRANCH_ID = "k-health-branch"  # what `branch_id_from_name` makes of it, and what the page names


def _home_figures(ui) -> dict[str, int]:
    """The stat tiles on the front page: what the application says the model holds."""
    ui.goto("/")
    tiles = ui.page.evaluate(
        "() => Array.from(document.querySelectorAll('#page .mantine-Paper-root'))"
        ".map(p => p.innerText.trim().replace(/\\s+/g, ' '))"
    )
    out: dict[str, int] = {}
    for tile in tiles:
        match = re.fullmatch(r"(\d+) ([a-z ]+)", tile)
        if match:
            out[match.group(2)] = int(match.group(1))
    return out


def _grid_column(ui, column: str) -> list[str]:
    """What one column of the Browse grid reads, down the rows it has rendered."""
    return ui.page.locator(
        f"#browse-grid .ag-center-cols-container .ag-cell[col-id='{column}']"
    ).evaluate_all("cells => cells.map(c => c.innerText.trim())")


def _search(ui, text: str) -> None:
    """Type into Browse's search box and wait out its 400 ms debounce before the grid reloads."""
    ui.fill("browse-text", text)
    ui.page.wait_for_timeout(700)
    ui.settle()


def _bars(ui):
    """The bars of the change-activity chart, in the order they are drawn."""
    return ui.page.locator('#health-body div[style*="width: 22px"]')


def _tooltip_of(ui, bars, index: int) -> str:
    """Hover one bar and read the tooltip it opens, with any earlier one let go of first."""
    ui.page.mouse.move(2, 400)
    ui.page.wait_for_timeout(400)
    bars.nth(index).hover()
    ui.page.wait_for_timeout(700)
    tips = ui.page.locator('[class*="Tooltip-tooltip"], [role="tooltip"]')
    texts = [t.strip() for t in tips.all_inner_texts() if t.strip()]
    return texts[0] if texts else ""


def _week_labels(count: int) -> list[str]:
    """The ISO weeks a chart of `count` bars should name, the last of them the week we are in."""
    now = datetime.now(UTC)
    return [f"W{(now - timedelta(weeks=i)).isocalendar()[1]:02d}" for i in range(count - 1, -1, -1)]


def _branch_labels(ui) -> list[str]:
    """What the header's branch selector offers, leaving it closed again."""
    ui.page.locator("#branch-select").first.click()
    ui.page.wait_for_timeout(300)
    labels = [t.strip() for t in ui.page.locator("[role='option']").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(250)
    return labels


def _ensure_branch(ui, name: str) -> bool:
    """The group's own branch, created once; True when this scenario is the one that created it."""
    if any(name in label for label in _branch_labels(ui)):
        return False
    ui.click("branch-new-open")
    ui.must("the New branch modal opened", ui.visible("branch-new-modal-body"))
    ui.fill("branch-new-name", name)
    ui.fill("branch-new-desc", "Group K: the branch Health is asked to measure.")
    ui.click("branch-new-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    return True


@pytest.mark.scenario(
    scenario_id="K10",
    group="K",
    title="Health counts the same model the front page does, and its two cards agree with each other",
    feature="Health · the figures",
    expected="The elements and the relationships the freshness table adds up to are the ones Home reports; "
    "the completeness heading measured all of them and its rows account for all of them; and no source row "
    "counts more stale or never-updated rows than it holds.",
)
def test_figures_agree(ui, record):
    home = _home_figures(ui)
    ui.must(
        "the front page says what the model holds",
        "elements" in home and "relationships" in home,
        str(home),
    )
    _open_health(ui)
    rows = _rows(ui, FRESHNESS)
    ui.must("the freshness table has its rows", bool(rows), f"{len(rows)} row(s)")

    elements = [_number(r[ELEMENTS]) for r in rows]
    relationships = [_number(r[RELATIONSHIPS]) for r in rows]
    ui.check(
        "the source systems add up to every element the front page counts",
        sum(elements) == home["elements"],
        f"{' + '.join(str(e) for e in elements)} = {sum(elements)}, Home says {home['elements']}",
    )
    ui.check(
        "and to every relationship",
        sum(relationships) == home["relationships"],
        f"{' + '.join(str(r) for r in relationships)} = {sum(relationships)}, "
        f"Home says {home['relationships']}",
    )
    ui.check(
        "the source system holding the most is at the top",
        elements == sorted(elements, reverse=True),
        str(list(zip([r[SOURCE] for r in rows], elements, strict=False))),
    )

    # A figure that counts more rows than the source has is a figure counted over the wrong set.
    _every(
        ui,
        "no source counts more never-updated rows than it holds",
        [
            f"{r[SOURCE]}: {r[NEVER_UPDATED]} never updated of {r[ELEMENTS]}"
            for r in rows
            if _number(r[NEVER_UPDATED]) > _number(r[ELEMENTS])
        ],
        f"{len(rows)} source(s)",
    )
    _every(
        ui,
        "nor more stale rows than it holds",
        [
            f"{r[SOURCE]}: {r[column]} stale at {days} d of {r[ELEMENTS]}"
            for r in rows
            for column, days in STALE_COLUMNS
            if _number(r[column]) > _number(r[ELEMENTS])
        ],
        f"{len(rows)} source(s) × {len(STALE_COLUMNS)} windows",
    )
    _every(
        ui,
        "and on every row a longer window counts no more than a shorter one",
        [
            f"{r[SOURCE]}: {r[STALE_30]} / {r[STALE_90]} / {r[STALE_180]}"
            for r in rows
            if not (_number(r[STALE_180]) <= _number(r[STALE_90]) <= _number(r[STALE_30]))
        ],
        f"{len(rows)} source(s)",
    )
    _every(
        ui,
        "no source was last updated before it was first loaded",
        [
            f"{r[SOURCE]}: loaded {r[FIRST_LOADED]}, updated {r[LAST_UPDATED]}"
            for r in rows
            if r[FIRST_LOADED] and r[LAST_UPDATED] and r[FIRST_LOADED] > r[LAST_UPDATED]
        ],
        f"{len(rows)} source(s)",
    )

    total = _completeness_total(ui)
    ui.check(
        "the completeness card measured every element the front page counts",
        total == home["elements"],
        f"the heading says {total}, Home says {home['elements']}",
    )
    types = _table(ui, COMPLETENESS).evaluate(TYPE_CELL_JS)
    ui.must("the completeness table has a row per type", bool(types), f"{len(types)} row(s)")
    counted = sum(t["elements"] for t in types)
    ui.check(
        "and its rows account for all of them",
        counted == total,
        f"{len(types)} type rows hold {counted}, the heading says {total}",
    )
    ui.check(
        "the front page counts the same types with content",
        home.get("element types with content") == len(types),
        f"Home says {home.get('element types with content')}, the table has {len(types)} rows",
    )
    ui.check(
        "the type holding the most elements is at the top",
        [t["elements"] for t in types] == sorted((t["elements"] for t in types), reverse=True),
        str([(t["type"], t["elements"]) for t in types]),
    )
    _every(
        ui,
        "every type row names the domain it belongs to",
        [t["type"] for t in types if not t["domain"]],
        f"{len(types)} types",
    )
    ui.shot("The freshness and completeness cards, counting the same model the front page counts")


@pytest.mark.scenario(
    scenario_id="K11",
    group="K",
    title="A type name on the completeness table opens exactly that type's elements",
    feature="Health · completeness links",
    expected="The type name is a link carrying its type id; Browse arrives with that type chosen, counting "
    "what the table counted, every row of that type, and with no yellow note claiming a facet was filtered.",
)
def test_type_link(ui, record):
    _open_health(ui)
    types = _table(ui, COMPLETENESS).evaluate(TYPE_CELL_JS)
    ui.must("the completeness table has a row per type", bool(types), f"{len(types)} row(s)")
    # The smallest type, so every row it opens can be read without scrolling the grid.
    index, row = min(enumerate(types), key=lambda pair: pair[1]["elements"])
    ui.must(f"the {row['type']} row counts its elements", row["elements"] > 0, str(row["elements"]))
    href = row["href"] or ""
    ui.must("the type name is a link to its own rows", href.startswith("/browse?type="), href or "(no link)")
    type_id = href.split("type=")[-1]
    ui.shot(f"The completeness row for {row['type']}, whose name is a link to its {row['elements']} rows")

    _follow(ui, _cell(ui, COMPLETENESS, index, 0).locator("a").first)
    ui.check("Browse was asked for that type", f"type={type_id}" in ui.page.url, ui.page.url)
    selected = _selected_type(ui)
    ui.check("Browse arrives with the type chosen", row["type"] in selected, f"{selected!r}")
    labelled = re.search(r"\((\d+)\)\s*$", selected)
    ui.check(
        "the type selector counts the elements the Health table counted",
        bool(labelled) and int(labelled.group(1)) == row["elements"],
        f"Health said {row['elements']}, the selector says {selected!r}",
    )
    shown, total = _browse_counts(ui)
    ui.check(
        "Browse holds exactly the elements the row counted",
        shown == row["elements"] == total,
        f"the row said {row['elements']}, Browse shows {shown} of {total}",
    )
    ui.check(
        "a type on its own is not dressed up as a Health filter",
        ui.text("browse-filter-note") == "",
        ui.text("browse-filter-note") or "(no note)",
    )
    kinds = set(_grid_column(ui, "type"))
    ui.check(
        "every row the grid shows is of that type",
        kinds == {row["type"]},
        f"{sorted(kinds)} against {row['type']!r}",
    )
    ui.shot("Following the type name lands on Browse holding that type and nothing else")


@pytest.mark.scenario(
    scenario_id="K12",
    group="K",
    title="The activity chart runs week by week up to the week we are in",
    feature="Health · change activity",
    expected="The bars are consecutive ISO weeks ending at the current one, and hovering a quiet week says "
    "that week held no change rather than nothing at all.",
)
def test_activity_calendar(ui, record):
    _open_health(ui)
    bars = _bars(ui)
    count = bars.count()
    ui.must("the chart drew its bars", count > 0, f"{count} bar(s)")
    labels = bars.evaluate_all("ds => ds.map(d => d.parentElement.innerText.trim())")
    # Derived from however many bars the chart drew, so this scenario says nothing about how
    # many there should be — that is K02's question — only that they are the weeks up to now.
    wanted = _week_labels(count)
    ui.check(
        "the bars are consecutive weeks ending at the week we are in",
        labels == wanted,
        f"{labels} against {wanted}",
    )
    ui.check(
        "the last bar is the current week", labels[-1] == wanted[-1], f"{labels[-1]} against {wanted[-1]}"
    )

    colours = bars.evaluate_all("ds => ds.map(d => d.style.background)")
    quiet = [i for i, c in enumerate(colours) if "233, 236, 239" in c]
    ui.check(
        "a week with no change is drawn in the quiet colour",
        bool(quiet),
        f"{len(quiet)} quiet of {count}",
    )
    if quiet:
        index = quiet[-1]
        text = _tooltip_of(ui, bars, index)
        ui.check(
            "hovering a quiet week names that week",
            text.startswith("2") and text.split(":")[0][-3:] == labels[index],
            f"the bar is labelled {labels[index]}, the tooltip says {text or '(no tooltip)'}",
        )
        ui.check(
            "and says it held no change, rather than saying nothing",
            "0 change(s)" in text,
            text or "(no tooltip)",
        )
        ui.check(
            "and names no kind of change for a week that saw none",
            text.strip().endswith("0 change(s)"),
            text or "(no tooltip)",
        )
    ui.shot("The activity chart with a quiet week's tooltip open, naming the week and its nothing")


@pytest.mark.scenario(
    scenario_id="K13",
    group="K",
    title="The rows behind a source figure come from that source and no other",
    feature="Health · freshness links",
    expected="Following the never-updated figure on an imported row shows rows that all name that source; "
    "following it on the (authored) row shows rows that name no source at all.",
)
def test_rows_behind_the_figure(ui, record):
    _open_health(ui)
    row = _fresh_row(ui, SEEDED_SOURCE)
    ui.must(f"the '{SEEDED_SOURCE}' source has a row", row is not None)
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    figure = _number(cell.inner_text())
    ui.must("its never-updated figure counts something", figure > 0, cell.inner_text())
    _follow(ui, cell.locator("a").first)
    sources = _grid_column(ui, "source_system")
    ui.must("the grid rendered rows to read", bool(sources), f"{len(sources)} cell(s)")
    _every(
        ui,
        f"every row Browse shows was imported from {SEEDED_SOURCE}",
        sorted({s or "(no source)" for s in sources if s != SEEDED_SOURCE}),
        f"{len(sources)} rows read of {figure}",
    )
    ui.shot(f"The rows behind the {SEEDED_SOURCE} figure, each naming that source")

    _open_health(ui)
    row = _fresh_row(ui, AUTHORED)
    ui.must(
        f"there is an {AUTHORED} row to follow",
        row is not None,
        str([r[SOURCE] for r in _rows(ui, FRESHNESS)]),
    )
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    authored = _number(cell.inner_text())
    ui.must("its never-updated figure counts something", authored > 0, cell.inner_text())
    _follow(ui, cell.locator("a").first)
    sources = _grid_column(ui, "source_system")
    ui.must("the grid rendered rows to read", bool(sources), f"{len(sources)} cell(s)")
    # The figure counted the rows nobody imported: a row naming a source system is a row the
    # figure never counted, however closely the two numbers happen to agree.
    _every(
        ui,
        f"every row behind the {AUTHORED} figure came from no source system",
        sorted({s for s in sources if s}),
        f"{len(sources)} rows read of {authored}",
    )
    ui.shot(f"The rows behind the {AUTHORED} figure, none of them from a source system")


@pytest.mark.scenario(
    scenario_id="K14",
    group="K",
    title="A grid a Health figure filtered stays honest when it is narrowed, and gives the model back",
    feature="Health · the way back",
    expected="Searching inside a grid a Health figure filtered keeps the yellow note and can never show "
    "more than the figure counted; 'Show all elements' clears the filter, takes the note with it and "
    "returns the whole model.",
)
def test_narrowing_and_the_way_back(ui, record):
    _open_health(ui)
    row = _fresh_row(ui, SEEDED_SOURCE)
    ui.must(f"the '{SEEDED_SOURCE}' source has a row", row is not None)
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    figure = _number(cell.inner_text())
    ui.must("the figure counts something to follow", figure > 0, cell.inner_text())
    _follow(ui, cell.locator("a").first)
    filtered, _ = _browse_counts(ui)
    ui.must(
        "Browse arrived holding the rows the figure counted", filtered == figure, f"{filtered} of {figure}"
    )

    names = _grid_column(ui, "name")
    ui.must("the grid rendered rows to search", bool(names), f"{len(names)} row(s)")
    word = next(iter(re.findall(r"[A-Za-z]{4,}", names[0])), "")
    ui.must("a word from one of those rows to search for", bool(word), names[0])
    _search(ui, word)
    narrowed, _ = _browse_counts(ui)
    ui.check(
        "searching inside the filter can never show more than the filter did",
        0 < narrowed <= filtered,
        f"{narrowed} after {filtered}, searching for {word!r}",
    )
    ui.check(
        "the note still says the grid is filtered",
        FACET_NOTES["never_updated"] in ui.text("browse-filter-note"),
        ui.text("browse-filter-note") or "(no note)",
    )
    ui.shot(f"The Health filter narrowed further by searching for {word!r}, with the note still saying so")

    _search(ui, "")
    restored, _ = _browse_counts(ui)
    ui.check(
        "clearing the search leaves the Health filter where it was",
        restored == filtered,
        f"{restored} against {filtered}",
    )
    back = ui.page.locator("#browse-filter-note a").first
    ui.must("the note offers the way back to the whole model", back.count() > 0)
    # Not `_follow`: this address is a /browse the page is already on, so the wait has to be
    # for the query string to go rather than for the path to arrive.
    back.click()
    ui.page.wait_for_url(re.compile(r"/browse$"), timeout=20_000)
    ui.page.wait_for_selector("#browse-grid", state="attached")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check(
        "the way back takes the note with it",
        ui.text("browse-filter-note") == "",
        ui.text("browse-filter-note") or "(no note)",
    )
    ui.check("and asks Browse for nothing in particular", ui.page.url.endswith("/browse"), ui.page.url)
    whole, total = _browse_counts(ui)
    ui.check(
        "the whole model is back, and it is larger than the filter showed",
        whole == total > filtered,
        f"{whole} of {total}, after {filtered}",
    )
    ui.check(
        "and the type filter is back to every type", "All types" in _selected_type(ui), _selected_type(ui)
    )
    ui.shot("Show all elements gives the whole model back and the yellow note is gone")


@pytest.mark.scenario(
    scenario_id="K15",
    group="K",
    title="A Reader sees the same figures and may still recompute them",
    feature="Health · roles",
    expected="Health changes nothing, so a Reader is shown the same page an Admin is, down to the figures, "
    "and Recompute still works; the Browse page a figure opens tells the Reader they may not edit while "
    "still showing them the rows.",
    role="reader",
)
def test_health_as_a_reader(ui, record):
    _open_health(ui)
    admin_total = _completeness_total(ui)
    admin_fresh = _rows(ui, FRESHNESS)
    admin_sections = _section_titles(ui)
    ui.must("the page was drawn for an Admin first", admin_total > 0, str(admin_total))

    ui.persona("Reader")
    # The stylesheet renders a badge in capitals, so the persona reads 'REN (READER)'.
    ui.check(
        "the header says the reader is a Reader",
        "reader" in ui.role_badge().lower(),
        ui.role_badge(),
    )
    _open_health(ui)
    ui.must("Health opens for a Reader at all", ui.visible("health-body"))
    ui.check(
        "with the same four sections",
        [t.split(" · as of")[0] for t in _section_titles(ui)]
        == [t.split(" · as of")[0] for t in admin_sections],
        str(_section_titles(ui)),
    )
    ui.check(
        "and the same freshness figures",
        _rows(ui, FRESHNESS) == admin_fresh,
        f"{_rows(ui, FRESHNESS)} against {admin_fresh}",
    )
    ui.check(
        "and the same completeness total",
        _completeness_total(ui) == admin_total,
        f"{_completeness_total(ui)} against {admin_total}",
    )
    ui.check(
        "a page that changes nothing is not refused: Recompute is offered",
        ui.visible("health-refresh") and not ui.disabled("health-refresh"),
    )
    ui.click("health-refresh")
    ui.check(
        "and recomputing gives the Reader the same figures back",
        _completeness_total(ui) == admin_total,
        f"{_completeness_total(ui)} against {admin_total}",
    )
    ui.shot("Health as a Reader: the same figures, and Recompute still offered")

    row = _fresh_row(ui, SEEDED_SOURCE)
    ui.must(f"the '{SEEDED_SOURCE}' source has a row", row is not None)
    cell = _cell(ui, FRESHNESS, row, NEVER_UPDATED)
    figure = _number(cell.inner_text())
    _follow(ui, cell.locator("a").first)
    shown, _ = _browse_counts(ui)
    ui.check(
        "the rows behind the figure are shown to a Reader too",
        shown == figure,
        f"the figure said {figure}, Browse shows {shown}",
    )
    ui.check(
        "the note says what is being shown",
        FACET_NOTES["never_updated"] in ui.text("browse-filter-note"),
        ui.text("browse-filter-note") or "(no note)",
    )
    ui.check("but a Reader may not add an element to them", ui.disabled("new-open"))
    ui.check("nor bulk-edit them", ui.disabled("bulk-open"))
    ui.check(
        "and the page says why rather than only refusing",
        "You are a Reader on this page" in ui.body(),
        ui.body()[:200].replace("\n", " · "),
    )
    ui.shot("A Health figure followed as a Reader: the rows are there, the ways to change them are not")


@pytest.mark.scenario(
    scenario_id="K16",
    group="K",
    title="Health measures the branch the reader is on, not main",
    feature="Health · branches",
    expected="On a branch the page says so and counts the branch's draft; back on main the same figure is "
    "what it was, because a draft on a branch is not on main.",
    branch=BRANCH_NAME,
)
def test_health_on_a_branch(ui, record):
    _open_health(ui)
    main_total = _completeness_total(ui)
    ui.must("the completeness heading counts what main holds", main_total > 0, str(main_total))
    ui.check("the page says it measured main", "on main" in _subtitle(ui), _subtitle(ui))

    created = _ensure_branch(ui, BRANCH_NAME)
    ui.branch(BRANCH_NAME)
    ui.must(
        "the header is on the group's branch",
        ui.branch_badge().strip().lower() != "main",
        ui.branch_badge(),
    )
    _open_health(ui)
    subtitle = _subtitle(ui)
    ui.check("the page names the branch it measured", BRANCH_ID in subtitle.lower(), subtitle)
    ui.check("and no longer says main", "on main" not in subtitle, subtitle)
    branch_total = _completeness_total(ui)
    if created:
        ui.check(
            "a branch with nothing drafted on it yet shows the model main shows",
            branch_total == main_total,
            f"{branch_total} on the branch, {main_total} on main",
        )
    ui.shot("Health on a branch, saying which branch it measured")

    made = _create_elsewhere(ui, "K-branch-probe")
    ui.must("an element was drafted on the branch", bool(made), made or "(no element opened)")
    ui.click("health-refresh")
    ui.check(
        "the branch counts the element drafted on it",
        _completeness_total(ui) == branch_total + 1,
        f"{_completeness_total(ui)} after {branch_total}",
    )
    after = _fresh_figures(ui, AUTHORED)
    ui.check(
        f"and groups it under {AUTHORED}, like anything written rather than imported",
        bool(after) and _number(after[ELEMENTS]) >= 1,
        str(_rows(ui, FRESHNESS)),
    )
    ui.shot("The element drafted on the branch, counted by the page measuring that branch")

    ui.branch("main")
    _open_health(ui)
    ui.check("the page says it is back on main", "on main" in _subtitle(ui), _subtitle(ui))
    ui.check(
        "and main has not moved: a draft on a branch is not on main",
        _completeness_total(ui) == main_total,
        f"{_completeness_total(ui)} on main, {main_total} before the branch was written on",
    )
    ui.shot("Back on main, whose figures the branch's draft never touched")


@pytest.mark.scenario(
    scenario_id="K17",
    group="K",
    title="Every completeness bar is coloured by how far its facet has to go",
    feature="Health · completeness",
    expected="The bars are drawn in one colour per band — a facet nearly complete, one part way, one far "
    "off — no two bands share a colour, and no bar is drawn full while it still offers rows to fix.",
)
def test_bar_colours(ui, record, finding):
    _open_health(ui)
    cells = _table(ui, COMPLETENESS).evaluate(BAR_JS)
    ui.must("the completeness table drew its bars", bool(cells), f"{len(cells)} cell(s)")
    ui.must(
        "every bar says what it is drawn at",
        all(c["pct"] >= 0 for c in cells),
        str([f"{c['type']} · {c['facet']}" for c in cells if c["pct"] < 0][:6]),
    )
    ui.must(
        "and the browser resolved a colour for each",
        all(c["colour"] for c in cells),
        str([f"{c['type']} · {c['facet']}" for c in cells if not c["colour"]][:6]),
    )

    # The page paints a bar green at 90 and over, yellow from 60, red below that. A reader
    # takes in the colour before the number, so the three bands must not share one.
    def band(pct: int) -> str:
        return "nearly complete" if pct >= 90 else "part way" if pct >= 60 else "far off"

    bands: dict[str, set[str]] = {}
    for cell in cells:
        bands.setdefault(band(cell["pct"]), set()).add(cell["colour"])
    for name, colours in sorted(bands.items()):
        ui.check(
            f"every bar '{name}' is drawn in one colour",
            len(colours) == 1,
            f"{sorted(colours)}",
        )
    painted = [next(iter(c)) for c in bands.values()]
    ui.check(
        "and no two bands are drawn in the same colour",
        len(set(painted)) == len(painted),
        str({name: sorted(c) for name, c in bands.items()}),
    )
    ui.check(
        "the bands the seeded model reaches are all drawn",
        len(bands) >= 2,
        str(sorted(bands)),
    )
    # Rounding is the trap: 1 missing of 201 rounds to 100%, and a bar drawn full over a link
    # that says rows are missing tells the reader the opposite of what the link does.
    _every(
        ui,
        "no bar is drawn full while it still offers rows to fix",
        [f"{c['type']} · facet {c['facet']}: {c['text']}" for c in cells if c["missing"] and c["pct"] >= 100],
        f"{len([c for c in cells if c['missing']])} facets with rows to fix",
    )
    ui.shot("The completeness bars, one colour per band")

    # The totals above the table are sentences about the rows they count, in the same words
    # Browse uses for those rows, rather than column headings pressed into service as nouns.
    badges = [
        b.strip()
        for b in ui.page.locator('#health-body [class*="Badge-root"]').all_inner_texts()
        # Drawn in capitals, so read in the case they are measured in.
        if re.search(r"^\d+ (without|with) ", b.strip(), re.I)
    ]
    awkward = [
        b for b in badges if re.search(r"\b(link|target decided|required attributes) missing\b", b.lower())
    ]
    ui.check("the card totals each facet above the table", len(badges) >= len(FACET_COLUMNS), str(badges))
    ui.check(
        "and each total reads as what it counts",
        not awkward,
        str(awkward) if awkward else str(badges[:5]),
    )
    if awkward:
        finding.append(
            _finding(
                finding_id="K-2",
                where="src/ea/ui/pages/health.py · _completeness(), the totals above the table",
                severity="usability",
                summary="The totals badges read as broken English, and one of them says the opposite of "
                "what it counts.",
                detail='The badge is built as f"{totals[f]} {FACET_TITLES[f].lower()} missing", and '
                "FACET_TITLES holds column headings rather than countable nouns, so the card reads "
                f"{', '.join(repr(b) for b in awkward)}. The numbers are right (K04 checks each against "
                "the column beneath it), but '38 target decided missing' counts the elements whose target "
                "is undecided and says the reverse. Browse already has the phrasing: 'without a link', "
                "'with an undecided target state'.",
            )
        )
    ui.shot("The totals above the completeness table, one badge per facet")


@pytest.mark.scenario(
    scenario_id="K18",
    group="K",
    title="A row that has been changed stops being counted as never updated",
    feature="Health · freshness",
    expected="Editing one of the rows behind the never-updated figure takes it out of that figure and out "
    "of the grid the figure opens, leaves the source holding the same elements, and moves the row's last "
    "update; a figure that has fallen to zero stops offering rows at all.",
)
def test_an_edited_row_leaves_the_figure(ui, record):
    _open_health(ui)
    row = _fresh_row(ui, AUTHORED)
    ui.must(
        f"there is an {AUTHORED} row to work with",
        row is not None,
        str([r[SOURCE] for r in _rows(ui, FRESHNESS)]),
    )
    before = _fresh_figures(ui, AUTHORED)
    before_never = _number(before[NEVER_UPDATED])
    before_elements = _number(before[ELEMENTS])
    ui.must(
        "it counts a row nobody has touched since it was written", before_never > 0, before[NEVER_UPDATED]
    )

    _follow(ui, _cell(ui, FRESHNESS, row, NEVER_UPDATED).locator("a").first)
    ids = ui.grid_row_ids("browse-grid")
    names = _grid_column(ui, "name")
    ui.must("the figure opened the rows behind it", bool(ids), f"{len(ids)} row(s)")
    # This group's own element where there is one: another group's row is not ours to rename.
    pairs = list(zip(ids, names, strict=False))
    element_id = next((i for i, n in pairs if n.startswith("K-")), ids[0])

    ui.goto(f"/element/{element_id}")
    ui.click("#el-tabs [role='tab']:has-text('Edit')")
    ui.page.wait_for_timeout(200)
    name = (ui.page.locator("#el-name").first.input_value() or "").strip()
    ui.fill("el-name", f"{name} (K touched)")
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    ui.must("the row was saved", "Saved version" in feedback, feedback or "(no feedback)")
    ui.shot("One of the rows behind the never-updated figure, renamed and saved")

    _open_health(ui)
    after = _fresh_figures(ui, AUTHORED)
    ui.must(f"the {AUTHORED} row is still there", bool(after), str(_rows(ui, FRESHNESS)))
    ui.check(
        "the source still holds the same elements",
        _number(after[ELEMENTS]) == before_elements,
        f"{after[ELEMENTS]} after {before_elements}",
    )
    ui.check(
        "but one fewer of them has never been updated",
        _number(after[NEVER_UPDATED]) == before_never - 1,
        f"{after[NEVER_UPDATED]} after {before_never}",
    )
    ui.check(
        "and the row's last update is no older than it was",
        after[LAST_UPDATED] >= before[LAST_UPDATED],
        f"{after[LAST_UPDATED]} after {before[LAST_UPDATED]}",
    )
    cell = _cell(ui, FRESHNESS, _fresh_row(ui, AUTHORED), NEVER_UPDATED)
    if _number(after[NEVER_UPDATED]):
        _follow(ui, cell.locator("a").first)
        shown, _ = _browse_counts(ui)
        ui.check(
            "the rows behind the figure are one fewer",
            shown == before_never - 1,
            f"{shown} after {before_never}",
        )
        ui.check(
            "and the row that was edited is no longer among them",
            element_id not in ui.grid_row_ids("browse-grid"),
            element_id,
        )
    else:
        ui.check(
            "a figure that has fallen to zero stops offering rows",
            _href(cell) is None,
            _href(cell) or f"{cell.inner_text().strip()!r}, plain text",
        )
        ui.goto(f"/browse?missing=never_updated&source={AUTHORED}")
        shown, _ = _browse_counts(ui)
        ui.check("and the address behind it holds nothing", shown == 0, str(shown))
        ui.check(
            "not even the row that was edited",
            element_id not in ui.grid_row_ids("browse-grid"),
            element_id,
        )
    ui.shot("The never-updated figure after the row it counted was changed")
