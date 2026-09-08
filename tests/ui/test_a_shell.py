"""Group A — the shell: the header, the four navigation groups, routing and the narrow viewport.

Every other group works inside this frame, so these scenarios prove the frame itself: that Home
summarises the model, that all ten links reach their page and say which one the reader is on,
that an address nobody typed correctly still lands somewhere, and that the header keeps its
badges, its branch selector and its persona switcher at 1600 px and at 480 px.

Two conventions the shell imposes on every assertion here: a Mantine badge and the navigation
group headings are upper-cased by CSS, so their text comes back upper-case however it was
written; and a Mantine modal puts its component id on its title and its body, not on a wrapper,
so a modal is found by `#<id>-body`.
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
    heading = ui.page.locator("#page h1, #page h2").first
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
