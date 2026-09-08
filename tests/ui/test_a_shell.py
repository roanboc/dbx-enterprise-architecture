"""Group A — the shell: the header, the four navigation groups, routing and the narrow viewport.

Every other group works inside this frame, so these scenarios prove the frame itself: that Home
summarises the model, that all ten links reach their page and say which one the reader is on,
that an address nobody typed correctly still lands somewhere, and that the header keeps its
badges, its branch selector and its persona switcher at 1600 px and at 480 px.

Two conventions the shell imposes on every assertion here: a Mantine badge and the navigation
group headings are upper-cased by CSS, so their text comes back upper-case however it was
written; and a Mantine modal puts its component id on its title and its body, not on a wrapper,
so a modal is found by `#<id>-body`. A third, for the scenarios that read a dropdown: a Mantine
select renders its options into a portal that stays in the document after the list is shut, so
the options offered are the ones actually drawn, not every `[role=option]` on the page.

The later scenarios take the same frame further: what Home's two summary tables claim is checked
against the tiles above them, a type on Home is followed into Browse as a query parameter, an
element address and the browser's own Back and Forward are routed, every address is opened
directly as a bookmark would open it, and the header is measured at 1024 px as well as at 1600
and 480.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.gui

HEADER = ".mantine-AppShell-header"
NAVBAR = ".mantine-AppShell-navbar"

# label, path, the id layout.py gives the link, and the heading the page answers with
NAV = [
    ("Home", "/", "nav-home", "Higher Education EA Metamodel"),
    ("Browse", "/browse", "nav-browse", "Browse"),
    ("Ask", "/ask", "nav-ask", "Ask the model"),
    ("Impact", "/impact", "nav-impact", "Impact"),
    ("Target state", "/target", "nav-target", "Target state"),
    ("Propose", "/propose", "nav-propose", "Propose a change"),
    ("Import", "/import", "nav-import", "Import"),
    ("Branches", "/branches", "nav-branches", "Branches"),
    ("Metamodel", "/metamodel", "nav-metamodel", "Metamodel"),
    ("Health", "/health", "nav-health", "Health"),
]

STAT_LABELS = [
    "elements",
    "relationships",
    "element types with content",
    "relationship types with content",
    "open branches",
    "elements that change",
]


def _tiles(ui) -> dict[str, str]:
    """The first grid on Home is the row of stat tiles, read back as {label: value}."""
    cells = ui.page.locator("#page .mantine-SimpleGrid-root").first.locator("> *")
    out: dict[str, str] = {}
    for i in range(cells.count()):
        lines = [line.strip() for line in cells.nth(i).inner_text().splitlines() if line.strip()]
        if len(lines) >= 2:
            out[lines[1].lower()] = lines[0]
    return out


def _page_heading(ui) -> str:
    heading = ui.page.locator("#page h1, #page h1").first
    return heading.inner_text().strip() if heading.count() else ""


def _marked(ui, nav_id: str) -> bool:
    """A Mantine NavLink marks the page the reader is on with data-active."""
    link = ui.page.locator(f"#{nav_id}")
    return bool(link.count()) and link.first.get_attribute("data-active") is not None


def _on_screen(ui, selector: str) -> bool:
    """Reachable, not merely present: a collapsed navbar is translated out of the viewport."""
    loc = ui.page.locator(selector).first
    if not loc.count() or not loc.is_visible():
        return False
    box = loc.bounding_box()
    return bool(box) and box["x"] >= 0 and box["width"] > 0


def _sideways(ui) -> tuple[bool, str]:
    scroll, client = ui.page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    return scroll <= client + 2, f"scrollWidth {scroll} vs clientWidth {client}"


# The four domains the loaded pack declares, as a badge renders them: Mantine upper-cases a
# badge, and a domain the page could not name would come back as its raw key instead.
DOMAIN_NAMES = {"INFORMATION", "PROCESS", "INTEGRATION", "OBJECTS OF ENTERPRISE CONCERN"}

RAW_KEY = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")  # what a name looks like when nothing named it

TABLE_JS = """(table) => ({
  headers: Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim()),
  rows: Array.from(table.querySelectorAll('tbody tr')).map(
    tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())),
  badges: Array.from(table.querySelectorAll('tbody tr')).map(
    tr => Array.from(tr.querySelectorAll('.mantine-Badge-root')).map(b => b.innerText.trim())),
})"""

# Everything the header lays out, measured where a reader would see it. `right` is the edge a
# control is clipped at, so a control pushed off the side is caught rather than merely narrow.
GEOMETRY_JS = """() => {
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
            h: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom)};
  };
  const controls = {
    'the branch badge': box(document.getElementById('branch-badge')),
    'the branch selector': box(document.getElementById('branch-select')),
    'the new-branch button': box(document.getElementById('branch-new-open')),
    'the role badge': box(document.getElementById('role-badge')),
    'the persona switcher': box(document.getElementById('persona-select')),
    'the pack badge': box(Array.from(
      document.querySelectorAll('.mantine-AppShell-header .mantine-Badge-root')
    ).filter(b => b.innerText.toLowerCase().includes('metamodel'))[0]),
  };
  return {
    header: box(document.querySelector('.mantine-AppShell-header')),
    navbar: box(document.querySelector('.mantine-AppShell-navbar')),
    heading: box(document.querySelector('#page h1, #page h1')),
    brand: box(document.querySelector('.ea-brand')),
    controls: controls,
  };
}"""

# An icon here is a span the stylesheet masks with the icon's own SVG, so a name that named no
# icon leaves the span with no mask at all rather than drawing something wrong.
NAV_ICONS_JS = """() => {
  const masked = (el) => {
    const cs = getComputedStyle(el);
    const m = cs.maskImage || cs.webkitMaskImage || 'none';
    return m === 'none' ? '' : m;
  };
  const links = Array.from(document.querySelectorAll('.mantine-AppShell-navbar a[href]'));
  const masks = [];
  const rows = links.map(a => {
    const span = Array.from(a.querySelectorAll('span')).filter(s => masked(s))[0];
    if (span) masks.push(masked(span));
    return {
      label: a.innerText.trim(),
      icon: !!span,
      size: span ? Math.round(span.getBoundingClientRect().width) : 0,
    };
  });
  return {links: rows, distinct: new Set(masks).size};
}"""

OPTIONS_JS = """() => Array.from(document.querySelectorAll('[role="option"]'))
  .filter(o => o.getBoundingClientRect().width > 0)
  .map(o => o.innerText.trim())"""

# Each stat tile is an icon and, beside it, the figure over its label. Where they sit is the
# whole of what a row of tiles promises, so the tile is measured rather than only read.
TILE_LAYOUT_JS = """() => {
  const grid = document.querySelector('#page .mantine-SimpleGrid-root');
  if (!grid) return [];
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y)};
  };
  return Array.from(grid.children).map(tile => {
    const lines = Array.from(tile.querySelectorAll('p, span, div'))
      .filter(el => el.children.length === 0 && (el.innerText || '').trim());
    return {
      value: lines[0] ? lines[0].innerText.trim() : '',
      label: lines[1] ? lines[1].innerText.trim() : '',
      tile: box(tile),
      icon: box(tile.querySelector('.mantine-ThemeIcon-root')),
      number: box(lines[0]),
    };
  });
}"""


def _table(ui, index: int) -> dict:
    """One of Home's summary tables, read in a single pass: headers, cells and the badges in them."""
    return ui.page.locator("#page table").nth(index).evaluate(TABLE_JS)


def _count(tiles: dict[str, str], label: str) -> int:
    """A stat tile as the number it shows, or -1 when it shows something that is not one."""
    value = tiles.get(label, "")
    return int(value) if value.isdigit() else -1


def _geometry(ui) -> dict:
    return ui.page.evaluate(GEOMETRY_JS)


def _inside(box: dict | None, width: int) -> bool:
    return bool(box) and box["x"] >= 0 and box["right"] <= width + 1


def _marks(ui) -> list[str]:
    """Every navigation link currently marked as the page the reader is on."""
    return [nav_id for _, _, nav_id, _ in NAV if _marked(ui, nav_id)]


def _first_element_id(ui) -> str:
    """An element to open by address, taken from Browse so no fixture has to name one."""
    ui.goto("/browse")
    return next((row_id for row_id in ui.grid_row_ids("browse-grid") if row_id), "")


@pytest.mark.scenario(
    scenario_id="A01",
    group="A",
    title="Home summarises the loaded model",
    feature="Shell · Home",
    expected="Home names the pack and its version, shows the six stat tiles with their counts, and "
    "lists the elements by type and the most used relationships under headings that say so.",
)
def test_home(ui, record):
    ui.goto("/")
    ui.must("Home renders a heading", bool(_page_heading(ui)), _page_heading(ui))
    ui.check(
        "the heading names the pack",
        _page_heading(ui) == "Higher Education EA Metamodel",
        _page_heading(ui),
    )
    body = ui.body()
    ui.check("the pack id and version are named", "higher_education" in body and "version" in body)

    tiles = _tiles(ui)
    ui.check("six stat tiles are shown", len(tiles) == 6, f"tiles: {sorted(tiles)}")
    for label in STAT_LABELS:
        ui.check(f"a tile counts {label}", label in tiles, f"tiles: {sorted(tiles)}")
    ui.check(
        "the element count is a number above zero",
        tiles.get("elements", "0").isdigit() and int(tiles.get("elements", "0")) > 0,
        f"elements = {tiles.get('elements')!r}",
    )
    ui.check(
        "the relationship count is a number above zero",
        tiles.get("relationships", "0").isdigit() and int(tiles.get("relationships", "0")) > 0,
        f"relationships = {tiles.get('relationships')!r}",
    )

    tables = ui.page.locator("#page table")
    ui.check("both summary tables are drawn", tables.count() >= 2, f"{tables.count()} tables")
    rows = ui.page.locator("#page table tbody tr")
    ui.check("the tables have rows", rows.count() > 1, f"{rows.count()} rows")
    ui.check(
        "a type name links into Browse",
        ui.page.locator("#page a[href^='/browse?type=']").count() > 0,
    )
    # DEFECT: home.py writes both card headings as dmc.Title(..., order={"base": 4}). A responsive
    # order renders nothing at all, so the reader gets two unlabelled tables and no way to tell
    # which is which. Every other page heading uses a plain integer order and does render.
    ui.check("the elements table is headed 'Elements by type'", "Elements by type" in body)
    ui.check("the relationships table is headed 'Most used relationships'", "Most used relationships" in body)
    ui.check(
        "each summary card carries a heading",
        ui.page.locator("#page .mantine-Title-root").count() >= 3,
        f"{ui.page.locator('#page .mantine-Title-root').count()} headings rendered on Home",
    )
    ui.shot("Home: the pack, the six stat tiles, and the two summary tables")


@pytest.mark.scenario(
    scenario_id="A02",
    group="A",
    title="Every navigation link routes to its page and the current one is marked",
    feature="Shell · navigation",
    expected="Clicking each of the ten links changes the address, renders that page's heading without "
    "an error, and leaves that link — and only that link — marked as the current page.",
)
def test_navigation_routes(ui, record):
    ui.goto("/")
    unmarked: list[str] = []
    for label, path, nav_id, heading in NAV:
        ui.must(f"the {label} link is in the navigation", ui.visible(nav_id))
        ui.click(nav_id)
        url = ui.page.url
        ui.check(f"{label} goes to {path}", url.endswith(path), url)
        ui.check(f"{path} renders its heading", _page_heading(ui) == heading, _page_heading(ui))
        ui.check(f"{path} did not fail to render", "This page failed to render" not in ui.body())
        marked = [other for _, _, other, _ in NAV if _marked(ui, other)]
        if marked != [nav_id]:
            unmarked.append(f"{path} -> {marked or 'nothing marked'}")
        if path == "/browse":
            ui.page.mouse.move(1200, 600)  # away from the link, so hover is not mistaken for marking
            ui.shot("Browse is open, and no link in the navigation is marked as the current page")
    # DEFECT: layout.py builds each dmc.NavLink without `active`, whose default is False — "never
    # active, overrides all matching behaviour". No link is ever marked, so the navigation never
    # says where the reader is, and the .mantine-NavLink-root[data-active] rule in styles.css that
    # was written for it can never apply. `active="exact"` on Home and "partial" on the rest would
    # let Mantine match the address.
    ui.check(
        "the page the reader is on is the one marked in the navigation",
        not unmarked,
        "; ".join(unmarked) if unmarked else "",
    )
    ui.page.mouse.move(1200, 600)
    ui.shot("Health, the last page the navigation reached, with nothing marked in the navigation")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A03",
    group="A",
    title="The navigation is grouped Home, Discover, Contribute, Manage",
    feature="Shell · navigation",
    expected="The four group headings are present, in that order, with all ten links under them.",
)
def test_navigation_groups(ui, record):
    ui.goto("/")
    sections = ui.page.locator(".ea-nav-section")
    # The headings are upper-cased by .ea-nav-section, so compare what was written, not the casing.
    found = [sections.nth(i).inner_text().strip().lower() for i in range(sections.count())]
    ui.check(
        "the four groups are in order",
        found == ["home", "discover", "contribute", "manage"],
        f"found: {found}",
    )
    links = ui.page.locator(f"{NAVBAR} a[href]")
    ui.check("ten links are offered", links.count() == 10, f"{links.count()} links")
    hrefs = {links.nth(i).get_attribute("href") for i in range(links.count())}
    ui.check(
        "every page in the model is linked",
        {path for _, path, _, _ in NAV}.issubset(hrefs),
        f"hrefs: {sorted(h for h in hrefs if h)}",
    )
    labels = [links.nth(i).inner_text().strip() for i in range(links.count())]
    ui.check(
        "the links are labelled as the pages they open",
        [label for label, _, _, _ in NAV] == labels,
        f"labels: {labels}",
    )
    ui.page.mouse.move(1200, 600)
    ui.shot(
        "The navigation, grouped Home, Discover, Contribute and Manage",
        selector=NAVBAR,
    )


@pytest.mark.scenario(
    scenario_id="A04",
    group="A",
    title="An address nobody recognises falls back to Home",
    feature="Shell · routing",
    expected="An unknown path renders Home rather than an error or a blank frame, with the header and "
    "the navigation intact around it.",
)
def test_unknown_path(ui, record):
    ui.goto("/no-such-page")
    ui.check("the address is left as it was typed", ui.page.url.endswith("/no-such-page"), ui.page.url)
    ui.check(
        "Home is rendered instead",
        _page_heading(ui) == "Higher Education EA Metamodel",
        _page_heading(ui),
    )
    ui.check("nothing reports a failure", "This page failed to render" not in ui.body())
    ui.check("the Home content is there", "elements" in _tiles(ui), f"tiles: {sorted(_tiles(ui))}")
    ui.check("the summary tables are there", ui.page.locator("#page table").count() >= 2)
    ui.check("the header survived", ui.visible(HEADER))
    ui.check("the navigation survived", ui.visible("nav-browse"))
    ui.shot("An unknown address renders Home with the shell intact")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A05",
    group="A",
    title="The header carries the pack, the role, the branch and the way to change them",
    feature="Shell · header",
    expected="The header shows the application name, the pack badge, the role badge, the branch badge on "
    "main, the branch selector, an enabled new-branch button and the persona switcher.",
)
def test_header(ui, record):
    ui.goto("/")
    ui.must("the header is present", ui.visible(HEADER))
    header = ui.page.locator(HEADER).first.inner_text()
    flat = header.replace("\n", " · ")

    ui.check("the application is named", "EA Repository" in header, flat[:140])
    ui.check("the pack is badged", "higher education ea metamodel" in header.lower(), flat[:140])
    ui.check("the branch badge says main", ui.branch_badge().lower() == "main", ui.branch_badge())
    ui.check("the role badge names the signed-in user", "admin" in ui.role_badge().lower(), ui.role_badge())
    ui.check("the branch selector is offered", ui.visible("branch-select"))
    ui.check(
        "the branch selector shows main",
        (ui.page.locator("#branch-select").first.input_value() or "").lower().startswith("main"),
        ui.page.locator("#branch-select").first.input_value(),
    )
    ui.check("the new-branch button is offered", ui.visible("branch-new-open"))
    ui.check("an admin may use it", not ui.disabled("branch-new-open"))
    ui.check("the persona switcher is offered", ui.visible("persona-select"))
    ui.check(
        "the persona switcher starts on Admin",
        "Admin" in (ui.page.locator("#persona-select").first.input_value() or ""),
        ui.page.locator("#persona-select").first.input_value(),
    )
    ui.check("the burger is out of the way on a wide screen", not ui.visible("nav-burger"))
    ui.shot(
        "The header: brand, branch badge and selector, new branch, role, persona and pack", selector=HEADER
    )


@pytest.mark.scenario(
    scenario_id="A06",
    group="A",
    title="At 480 px the burger opens the navigation",
    feature="Shell · narrow viewport",
    expected="On a narrow screen the navigation is out of the way behind a burger, and the burger opens "
    "it so a link can still be reached.",
)
def test_narrow_viewport(ui, record):
    ui.goto("/")
    ui.narrow()
    try:
        ui.check("the burger appears", ui.visible("nav-burger"))
        ui.check("the navigation is out of the way", not _on_screen(ui, "#nav-browse"))
        ui.check("the header is still readable", ui.visible(HEADER))
        no_scroll, detail = _sideways(ui)
        ui.check("the page does not scroll sideways", no_scroll, detail)
        ui.shot("At 480 px the navigation is behind a burger", full_page=False)

        ui.click("nav-burger")
        opened = ui.page.locator("#nav-burger .mantine-Burger-burger").first.get_attribute("data-opened")
        ui.check("the burger takes the click", opened == "true", f"data-opened={opened!r}")
        # DEFECT: the click reaches the callback — the burger draws itself open — but the navigation
        # stays translated a full width off-screen, so at 480 px the ten links cannot be reached at
        # all and the only way to another page is to type its address. app.py's toggle_mobile_nav
        # returns a new `navbar` prop to the AppShell; the shell does not act on it.
        reachable = _on_screen(ui, "#nav-browse")
        ui.check(
            "the burger opens the navigation",
            reachable,
            f"navbar at x={ui.page.locator(NAVBAR).first.bounding_box()['x']} in a 480 px viewport",
        )
        ui.shot(
            "After the burger is clicked: it draws itself open, the navigation stays away", full_page=False
        )

        if reachable:
            ui.click("nav-browse")
            ui.check("a link still routes from the narrow navigation", ui.page.url.endswith("/browse"))
            ui.check("Browse renders at 480 px", _page_heading(ui) == "Browse", _page_heading(ui))
            ui.check("choosing a page closes the navigation again", not _on_screen(ui, "#nav-browse"))
    finally:
        ui.wide()
        ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A07",
    group="A",
    title="The browser tab names the application on every page",
    feature="Shell · document title",
    expected="The tab reads EA Repository on Home and stays named while routing, never left showing an "
    "updating placeholder.",
)
def test_tab_title(ui, record):
    ui.goto("/")
    ui.check("the tab names the application", ui.page.title() == "EA Repository", ui.page.title())
    ui.click("nav-metamodel")
    ui.check("routing does not blank the tab", ui.page.title() == "EA Repository", ui.page.title())
    ui.check("no updating placeholder is left behind", "Updating" not in ui.page.title(), ui.page.title())
    ui.page.mouse.move(1200, 600)
    ui.shot("Metamodel, reached by routing, with the tab still named EA Repository")
    ui.goto("/no-such-page")
    ui.check(
        "even an unknown address keeps the tab named", ui.page.title() == "EA Repository", ui.page.title()
    )
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A08",
    group="A",
    title="The new-branch button opens the shell's branch modal and closes without creating one",
    feature="Shell · new branch",
    expected="The + beside the branch selector opens a modal that explains what a branch is and asks for "
    "a name; Escape closes it and no branch is created.",
)
def test_new_branch_modal(ui, record):
    ui.goto("/")
    before = ui.page.locator("#branch-select").first.input_value()
    ui.click("branch-new-open")
    # A Mantine modal carries its component id on its title and body, never on a wrapper.
    ui.must("the modal opens", ui.visible("branch-new-modal-body"))
    ui.check("it is titled New branch", ui.text("branch-new-modal-title").startswith("New branch"))
    text = ui.text("branch-new-modal-body")
    ui.check("it says what a branch is", "starts from main" in text, text[:200].replace("\n", " · "))
    ui.check("it says how a branch ends", "merge it" in text, text[:200].replace("\n", " · "))
    ui.check("it asks for a name", ui.visible("branch-new-name"))
    ui.check("it offers a work package", ui.visible("branch-new-wp"))
    ui.check("it offers to create and switch", ui.visible("branch-new-save"))
    ui.shot("The New branch modal, opened from the header")

    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("Escape closes it", not ui.visible("branch-new-modal-body"))
    ui.check(
        "nothing was created and the reader is still on main",
        ui.page.locator("#branch-select").first.input_value() == before,
        ui.page.locator("#branch-select").first.input_value(),
    )
    ui.check("the branch badge still says main", ui.branch_badge().lower() == "main", ui.branch_badge())
    ui.check("Home is still the page underneath", _page_heading(ui) == "Higher Education EA Metamodel")


@pytest.mark.scenario(
    scenario_id="A09",
    group="A",
    title="Home's elements-by-type table agrees with the tiles above it",
    feature="Shell · Home",
    expected="The elements-by-type card names each type, the domain it belongs to and how many of it are "
    "loaded, holds one row per type the tiles say has content, adds up to the element count, and puts "
    "the most used type first.",
)
def test_home_type_table(ui, record):
    ui.goto("/")
    tiles = _tiles(ui)
    table = _table(ui, 0)
    ui.must("the elements-by-type table has rows", bool(table["rows"]), f"{len(table['rows'])} rows")
    ui.check(
        "its columns are the type, its domain and its count",
        [h.lower() for h in table["headers"][:3]] == ["type", "domain", "count"],
        f"headers: {table['headers']}",
    )
    ui.check(
        "it holds a row for every type the tiles count as having content",
        len(table["rows"]) == _count(tiles, "element types with content"),
        f"{len(table['rows'])} rows against a tile of {tiles.get('element types with content')!r}",
    )
    counts = [row[2] for row in table["rows"]]
    numbers = [int(c) for c in counts if c.isdigit()]
    ui.check(
        "every row counts something",
        len(numbers) == len(counts) and all(n > 0 for n in numbers),
        f"counts: {counts}",
    )
    ui.check(
        "the counts add up to the element count above them",
        sum(numbers) == _count(tiles, "elements"),
        f"{sum(numbers)} counted against a tile of {tiles.get('elements')!r}",
    )
    ui.check(
        "the most used type is at the top",
        numbers == sorted(numbers, reverse=True),
        f"counts: {counts}",
    )
    undomained = [row[0] for row, badges in zip(table["rows"], table["badges"], strict=False) if not badges]
    ui.check(
        "every type says which domain it belongs to",
        not undomained,
        "; ".join(undomained) if undomained else "",
    )
    keyed = [
        b[0] for b in table["badges"] if b and (b[0].upper() not in DOMAIN_NAMES or RAW_KEY.fullmatch(b[0]))
    ]
    ui.check(
        "the domains are named rather than keyed",
        not keyed,
        f"badges the pack does not name: {sorted(set(keyed))}" if keyed else "",
    )
    links = ui.page.locator("#page table").first.locator("a[href^='/browse?type=']")
    ui.check(
        "every type name is a link into Browse",
        links.count() == len(table["rows"]),
        f"{links.count()} links for {len(table['rows'])} rows",
    )
    ui.shot("Home: the elements-by-type card, one row per type with content")


@pytest.mark.scenario(
    scenario_id="A10",
    group="A",
    title="Home's most-used relationships table names both ends and is ordered by use",
    feature="Shell · Home",
    expected="The relationships card names the relationship and the types at either end of it, counts how "
    "often it is used, and shows the most used first — a top slice of the relationship types the tiles "
    "say have content.",
)
def test_home_relationship_table(ui, record):
    ui.goto("/")
    tiles = _tiles(ui)
    table = _table(ui, 1)
    ui.must("the relationships table has rows", bool(table["rows"]), f"{len(table['rows'])} rows")
    ui.check(
        "its columns are the relationship, both its ends and its count",
        [h.lower() for h in table["headers"]] == ["relationship", "from", "to", "count"],
        f"headers: {table['headers']}",
    )
    populated = _count(tiles, "relationship types with content")
    ui.check(
        "it shows at most the fifteen the card promises",
        len(table["rows"]) <= 15,
        f"{len(table['rows'])} rows",
    )
    ui.check(
        "it shows no more than the model holds",
        0 < len(table["rows"]) <= populated,
        f"{len(table['rows'])} rows against a tile of {tiles.get('relationship types with content')!r}",
    )
    counts = [row[3] for row in table["rows"]]
    numbers = [int(c) for c in counts if c.isdigit()]
    ui.check(
        "every relationship is counted",
        len(numbers) == len(counts) and all(n > 0 for n in numbers),
        f"counts: {counts}",
    )
    ui.check(
        "the most used relationship is at the top", numbers == sorted(numbers, reverse=True), f"{counts}"
    )
    ui.check(
        "no more relationships are counted than the model holds",
        sum(numbers) <= _count(tiles, "relationships"),
        f"{sum(numbers)} counted against a tile of {tiles.get('relationships')!r}",
    )
    nameless = [row[0] for row in table["rows"] if not row[0]]
    ui.check("every row names its relationship", not nameless, f"{len(nameless)} rows with no name")
    ends = [(row[0], row[1], row[2]) for row in table["rows"]]
    unnamed = [
        f"{name}: {source} -> {target}"
        for name, source, target in ends
        if not source or not target or RAW_KEY.fullmatch(source) or RAW_KEY.fullmatch(target)
    ]
    ui.check(
        "both ends are named as element types rather than left as identifiers",
        not unnamed,
        "; ".join(unnamed) if unnamed else "",
    )
    ui.shot("Home: the most used relationships, both ends named")


@pytest.mark.scenario(
    scenario_id="A11",
    group="A",
    title="A type on Home opens Browse filtered to that type",
    feature="Shell · Home",
    expected="Clicking a type name carries it into Browse as a query parameter: the type filter is set to "
    "that type and the grid holds exactly the number of elements Home said it had.",
)
def test_home_type_link_filters_browse(ui, record):
    ui.goto("/")
    table = _table(ui, 0)
    ui.must("Home lists a type to follow", bool(table["rows"]), f"{len(table['rows'])} rows")
    name, count = table["rows"][0][0], table["rows"][0][2]
    ui.must("the type Home lists first is counted", count.isdigit(), f"count: {count!r}")
    link = ui.page.locator("#page table").first.locator("a[href^='/browse?type=']").first
    href = link.get_attribute("href") or ""
    ui.must("the type name carries an address", href.startswith("/browse?type="), f"href: {href!r}")
    link.click()
    ui.page.wait_for_url(f"**{href}")
    ui.settle()
    ui.check("the address carries the type as a query parameter", ui.page.url.endswith(href), ui.page.url)
    ui.check("Browse is the page that opened", _page_heading(ui) == "Browse", _page_heading(ui))
    ui.check("nothing reports a failure", "This page failed to render" not in ui.body())
    value = ui.page.locator("#browse-type").first.input_value() or ""
    ui.check(f"the type filter is set to {name}", value.startswith(name), f"the filter reads {value!r}")
    ui.check("the filter says how many that type has", f"({count})" in value, f"the filter reads {value!r}")
    ui.check(
        f"the grid holds the {count} elements Home counted",
        ui.grid_row_count("browse-grid") == int(count),
        f"{ui.grid_row_count('browse-grid')} rows for a Home count of {count}",
    )
    ui.check(
        "the count beside the filter says the same",
        ui.text("browse-count").startswith(f"{count} of "),
        ui.text("browse-count"),
    )
    ui.check("Browse is the link marked in the navigation", _marks(ui) == ["nav-browse"], f"{_marks(ui)}")
    ui.page.mouse.move(1200, 600)
    ui.shot(f"Browse, opened from {name} on Home and filtered to it")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A12",
    group="A",
    title="An element address opens the element and marks the Browse it belongs to",
    feature="Shell · routing",
    expected="An /element/<id> address renders that element inside the shell, and because an element has "
    "no link of its own the navigation marks Browse, which opens it.",
)
def test_element_address(ui, record):
    element_id = _first_element_id(ui)
    ui.must(
        "Browse offers an element to open",
        bool(element_id),
        element_id or "the grid returned no row identifiers",
    )
    ui.goto(f"/element/{element_id}")
    ui.check("the address is the element's own", ui.page.url.endswith(f"/element/{element_id}"), ui.page.url)
    ui.check("the element renders a heading", bool(_page_heading(ui)), _page_heading(ui))
    ui.check("nothing reports a failure", "This page failed to render" not in ui.body())
    ui.check("the page says which element it is", element_id in ui.body(), element_id)
    ui.check(
        "Browse, which opens an element, is the one link marked",
        _marks(ui) == ["nav-browse"],
        f"marked: {_marks(ui) or 'nothing'}",
    )
    ui.check("the header survived", ui.visible(HEADER))
    ui.check("the navigation survived", ui.visible("nav-browse"))
    ui.page.mouse.move(1200, 600)
    ui.shot(f"{element_id} open by address, with Browse marked in the navigation")
    ui.click("nav-browse")
    ui.check("Browse takes the reader back out", ui.page.url.endswith("/browse"), ui.page.url)
    ui.check("and renders itself", _page_heading(ui) == "Browse", _page_heading(ui))
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A13",
    group="A",
    title="Back and Forward walk the pages the reader has visited",
    feature="Shell · routing",
    expected="After moving through the navigation, Back returns to each earlier page — its heading and its "
    "marked link with it — and Forward returns to the one left behind, without ever reloading the "
    "application.",
)
def test_back_and_forward(ui, record):
    ui.goto("/")
    ui.page.evaluate("() => { window.__eaRouting = 'the same document'; }")
    ui.click("nav-browse")
    ui.check(
        "following a link routes inside the application rather than reloading it",
        ui.page.evaluate("() => window.__eaRouting || 'the application was reloaded'") == "the same document",
        ui.page.evaluate("() => window.__eaRouting || 'the application was reloaded'"),
    )
    ui.click("nav-impact")
    ui.must("the reader is on Impact", ui.page.url.endswith("/impact"), ui.page.url)

    ui.page.go_back()
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("Back returns to Browse", ui.page.url.endswith("/browse"), ui.page.url)
    ui.check("and renders Browse again", _page_heading(ui) == "Browse", _page_heading(ui))
    ui.check("and marks Browse in the navigation", _marks(ui) == ["nav-browse"], f"{_marks(ui) or 'nothing'}")

    ui.page.go_back()
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check(
        "Back again returns Home",
        _page_heading(ui) == "Higher Education EA Metamodel",
        _page_heading(ui),
    )
    ui.check("and marks Home in the navigation", _marks(ui) == ["nav-home"], f"{_marks(ui) or 'nothing'}")

    ui.page.go_forward()
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("Forward returns to the page left behind", ui.page.url.endswith("/browse"), ui.page.url)
    ui.check("and renders it", _page_heading(ui) == "Browse", _page_heading(ui))
    ui.check(
        "the application was never reloaded on the way",
        ui.page.evaluate("() => window.__eaRouting || 'the application was reloaded'") == "the same document",
        ui.page.evaluate("() => window.__eaRouting || 'the application was reloaded'"),
    )
    ui.page.mouse.move(1200, 600)
    ui.shot("Browse, returned to with the browser's own Back and Forward")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A14",
    group="A",
    title="The header reserves exactly the room it takes at each of its three heights",
    feature="Shell · header",
    expected="At 1600 px, 1024 px and 480 px the header sits above the page rather than over it or apart "
    "from it, the navigation begins where the header ends, and nothing scrolls sideways.",
)
def test_header_height_at_each_width(ui, record):
    ui.goto("/")
    try:
        for width, height in ((1600, 1000), (1024, 900), (480, 900)):
            ui.page.set_viewport_size({"width": width, "height": height})
            ui.page.wait_for_timeout(300)
            ui.settle()
            geo = _geometry(ui)
            header, heading = geo["header"], geo["heading"]
            ui.must(
                f"at {width} px the header and the page heading are both drawn",
                bool(header and heading),
                f"header={header}, heading={heading}",
            )
            gap = heading["y"] - header["bottom"]
            ui.check(
                f"at {width} px the header does not cover the page",
                gap >= 0,
                f"the heading starts at y={heading['y']}, the {header['h']} px header ends at "
                f"{header['bottom']}",
            )
            ui.check(
                f"at {width} px the header leaves no band of nothing under it",
                gap <= 48,
                f"{gap} px between the {header['h']} px header and the page heading",
            )
            if width >= 768:
                ui.check(
                    f"at {width} px the navigation begins where the header ends",
                    abs(geo["navbar"]["y"] - header["bottom"]) <= 1,
                    f"the navigation starts at y={geo['navbar']['y']}, the header ends at {header['bottom']}",
                )
            no_scroll, detail = _sideways(ui)
            ui.check(f"at {width} px the page does not scroll sideways", no_scroll, detail)
            if width == 1024:
                ui.shot("The header at 1024 px, wrapped onto two rows above the page", full_page=False)
    finally:
        ui.wide()
        ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A15",
    group="A",
    title="Every header control stays on the screen at a tablet width and at 480 px",
    feature="Shell · narrow viewport",
    expected="At 1024 px and at 480 px the branch badge, the branch selector, the new-branch button, the "
    "role badge, the persona switcher and the pack badge are all drawn inside the viewport, and the "
    "brand still names the application.",
)
def test_header_controls_when_narrow(ui, record):
    ui.goto("/")
    try:
        for width, height in ((1024, 900), (480, 900)):
            ui.page.set_viewport_size({"width": width, "height": height})
            ui.page.wait_for_timeout(300)
            ui.settle()
            geo = _geometry(ui)
            controls = geo["controls"]
            undrawn = [name for name, box in controls.items() if not box or box["w"] <= 0 or box["h"] <= 0]
            ui.check(
                f"at {width} px every header control is drawn",
                not undrawn,
                "; ".join(undrawn) if undrawn else "",
            )
            clipped = [
                f"{name} spans x={box['x']}..{box['right']}"
                for name, box in controls.items()
                if box and not _inside(box, width)
            ]
            ui.check(
                f"at {width} px no header control is pushed off the side",
                not clipped,
                "; ".join(clipped) if clipped else "",
            )
            ui.check(
                f"at {width} px the brand is inside the viewport too",
                _inside(geo["brand"], width),
                f"the brand spans x={geo['brand']['x']}..{geo['brand']['right']} in {width} px"
                if geo["brand"]
                else "the brand is not drawn",
            )
            brand = ui.text(".ea-brand")
            ui.check(
                f"at {width} px the application is still named",
                "EA Repository" in brand,
                brand.replace("\n", " · "),
            )
            no_scroll, detail = _sideways(ui)
            ui.check(f"at {width} px the header does not push the page sideways", no_scroll, detail)
            ui.shot(f"The header at {width} px, with every control still on the screen", full_page=False)
    finally:
        ui.wide()
        ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A16",
    group="A",
    title="Every address typed straight into the browser renders its own page",
    feature="Shell · routing",
    expected="Each of the ten addresses opened directly, rather than by clicking, renders that page and "
    "marks that link; a trailing slash is tolerated; and an address nobody recognises marks the Home it "
    "falls back to.",
)
def test_addresses_opened_directly(ui, record):
    wrong_page: list[str] = []
    wrong_mark: list[str] = []
    for _label, path, nav_id, heading in NAV:
        ui.goto(path)
        if _page_heading(ui) != heading:
            wrong_page.append(f"{path} -> {_page_heading(ui)!r}")
        marked = _marks(ui)
        if marked != [nav_id]:
            wrong_mark.append(f"{path} -> {marked or 'nothing marked'}")
    ui.check(
        "every address renders the page it names",
        not wrong_page,
        "; ".join(wrong_page) if wrong_page else "",
    )
    ui.check(
        "every address marks the link that opens it",
        not wrong_mark,
        "; ".join(wrong_mark) if wrong_mark else "",
    )

    ui.goto("/browse/")
    ui.check("a trailing slash still reaches the page", _page_heading(ui) == "Browse", _page_heading(ui))
    ui.check("and still marks it", _marks(ui) == ["nav-browse"], f"{_marks(ui) or 'nothing'}")

    ui.goto("/no-such-page")
    ui.check(
        "an address nobody recognises marks the Home it falls back to",
        _marks(ui) == ["nav-home"],
        f"{_marks(ui) or 'nothing'}",
    )
    ui.page.mouse.move(1200, 600)
    ui.shot("An unknown address, with Home marked as the page it fell back to")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A17",
    group="A",
    title="The header's branch controls offer main, every open branch, and a + that says what it does",
    feature="Shell · header",
    expected="The branch selector lists main and one entry for each open branch Home counts, and the + "
    "beside it carries a name of its own and a tooltip saying a branch starts from main.",
)
def test_branch_controls(ui, record):
    ui.goto("/")
    open_branches = _count(_tiles(ui), "open branches")
    ui.must("Home counts the open branches", open_branches >= 0, f"the tile reads {open_branches}")

    ui.click("branch-select")
    options = ui.page.evaluate(OPTIONS_JS)
    ui.must("the selector opens a list", bool(options), f"options: {options}")
    ui.check("main is offered first", options[0] == "main", f"options: {options}")
    ui.check(
        "main and every open branch are offered, and nothing else",
        len(options) == open_branches + 1,
        f"{len(options)} options for {open_branches} open branches: {options}",
    )
    ui.shot("The branch selector, offering main and every open branch")
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("the list closes again", not ui.page.evaluate(OPTIONS_JS))
    ui.check("and the reader is still on main", ui.branch_badge().lower() == "main", ui.branch_badge())

    button = ui.page.locator("#branch-new-open").first
    name = (button.get_attribute("aria-label") or "").strip()
    ui.check("the + carries a name of its own", bool(name), f"aria-label: {name!r}")
    button.hover()
    ui.page.wait_for_timeout(700)
    tip = ui.page.locator("[role='tooltip'], .mantine-Tooltip-tooltip")
    said = tip.first.inner_text().strip() if tip.count() else ""
    ui.check("hovering it says what it does", "new branch" in said.lower(), said or "no tooltip appeared")
    ui.check("and where the branch starts", "main" in said.lower(), said or "no tooltip appeared")
    ui.shot("The + beside the branch selector, saying it starts a branch from main", selector=HEADER)
    ui.page.mouse.move(1200, 600)


@pytest.mark.scenario(
    scenario_id="A18",
    group="A",
    title="The navigation draws an icon for every link and says what the repository is",
    feature="Shell · navigation",
    expected="Each of the ten links carries an icon of its own, no two the same, the navigation closes by "
    "saying what the repository is, and the brand in the header carries its name and its tagline.",
)
def test_navigation_furniture(ui, record):
    ui.goto("/")
    icons = ui.page.evaluate(NAV_ICONS_JS)
    ui.must("the ten links are read back", len(icons["links"]) == 10, f"{len(icons['links'])} links")
    without = [row["label"] for row in icons["links"] if not row["icon"]]
    ui.check("every link draws an icon", not without, "; ".join(without) if without else "")
    unsized = [
        f"{row['label']} at {row['size']} px" for row in icons["links"] if row["icon"] and not row["size"]
    ]
    ui.check("every icon takes up room", not unsized, "; ".join(unsized) if unsized else "")
    ui.check(
        "no two links are given the same icon",
        icons["distinct"] == len(icons["links"]),
        f"{icons['distinct']} icons across {len(icons['links'])} links",
    )
    navbar = ui.page.locator(NAVBAR).first.inner_text()
    ui.check(
        "the navigation closes by saying what the repository is",
        "metamodel-driven EA repository" in navbar,
        navbar[-140:].replace("\n", " · "),
    )
    brand = ui.text(".ea-brand")
    ui.check("the brand names the application", "EA Repository" in brand, brand.replace("\n", " · "))
    ui.check(
        "and carries the tagline that says what it runs on",
        "DuckDB now, Databricks next" in brand,
        brand.replace("\n", " · "),
    )
    ui.check(
        "the brand draws its mark",
        ui.page.evaluate(
            "() => { const s = document.querySelector('.ea-brand-mark span');"
            " if (!s) return false; const cs = getComputedStyle(s);"
            " return (cs.maskImage || cs.webkitMaskImage || 'none') !== 'none'; }"
        ),
    )
    ui.page.mouse.move(1200, 600)
    ui.shot("The navigation: an icon on every link, and the line that says what this is", selector=NAVBAR)


@pytest.mark.scenario(
    scenario_id="A19",
    group="A",
    title="The six stat tiles read as one row of figures",
    feature="Shell · Home",
    expected="The six tiles are one row of headline figures: every tile keeps its number beside its icon, "
    "and all six numbers sit on the same line, so the row can be read across.",
)
def test_home_stat_tiles_line_up(ui, record):
    ui.goto("/")
    tiles = ui.page.evaluate(TILE_LAYOUT_JS)
    ui.must("the six tiles are drawn", len(tiles) == 6, f"{len(tiles)} tiles")
    ui.must(
        "every tile is measurable",
        all(t["tile"] and t["icon"] and t["number"] for t in tiles),
        "; ".join(
            f"{t['label'] or '?'}: {t}" for t in tiles if not (t["tile"] and t["icon"] and t["number"])
        ),
    )
    ui.check(
        "the six tiles are laid out as one row",
        len({t["tile"]["y"] for t in tiles}) == 1,
        "; ".join(f"{t['label']} at y={t['tile']['y']}" for t in tiles),
    )
    # DEFECT: home.py's _stat() groups the icon and the figure with no `wrap="nowrap"`, so in a tile
    # whose label is long enough to wrap — "element types with content", "relationship types with
    # content", "elements that change" — the figure drops underneath the icon while the three short
    # labels keep theirs beside it. The row of headline figures is then read at two heights rather
    # than one, and the tiles only keep their common height by padding the short ones with space.
    beneath = [
        f"{t['label']} at x={t['number']['x']}, its icon at x={t['icon']['x']}"
        for t in tiles
        if t["number"]["x"] <= t["icon"]["x"]
    ]
    ui.check(
        "every tile keeps its figure beside its icon",
        not beneath,
        "; ".join(beneath) if beneath else "",
    )
    baselines = sorted({t["number"]["y"] for t in tiles})
    ui.check(
        "all six figures sit on the same line",
        len(baselines) == 1,
        f"{len(baselines)} heights ({baselines}): "
        + "; ".join(f"{t['value']} {t['label']} at y={t['number']['y']}" for t in tiles),
    )
    ui.shot("The six stat tiles, read as one row of headline figures")
