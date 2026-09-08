"""Group A — the shell: the header, the four navigation groups, routing and the narrow viewport.

Every other group works inside this frame, so these scenarios prove the frame itself: that
Home summarises the model, that all ten links reach their page and say which one you are on,
that an address nobody typed correctly still lands somewhere, and that the header keeps its
badges, its branch selector and its persona switcher at 1600 px and at 480 px.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui

HEADER = ".mantine-AppShell-header"

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
    """The first grid on Home is the row of stat tiles: {label: value}."""
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
    """A Mantine NavLink says it is the current page with data-active."""
    link = ui.page.locator(f"#{nav_id}")
    return bool(link.count()) and link.first.get_attribute("data-active") is not None


def _on_screen(ui, selector: str) -> bool:
    """Visible and inside the viewport — a collapsed navbar is only translated away."""
    loc = ui.page.locator(selector).first
    if not loc.count() or not loc.is_visible():
        return False
    box = loc.bounding_box()
    return bool(box) and box["x"] >= 0 and box["width"] > 0


@pytest.mark.scenario(
    scenario_id="A01",
    group="A",
    title="Home summarises the loaded model",
    feature="Shell · Home",
    expected="Home names the pack and its version, shows the six stat tiles with counts, "
    "and lists both the elements by type and the most used relationships.",
)
def test_home(ui, record):
    ui.goto("/")
    ui.must("Home renders a heading", bool(_page_heading(ui)), _page_heading(ui))
    ui.check(
        "the heading names the pack", _page_heading(ui) == "Higher Education EA Metamodel", _page_heading(ui)
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

    ui.check("the elements-by-type table is titled", "Elements by type" in body)
    ui.check("the relationships table is titled", "Most used relationships" in body)
    tables = ui.page.locator("#page table")
    ui.check("both tables are drawn", tables.count() >= 2, f"{tables.count()} tables")
    rows = ui.page.locator("#page table tbody tr")
    ui.check("the tables have rows", rows.count() > 1, f"{rows.count()} rows")
    ui.check(
        "a type name links into Browse",
        ui.page.locator("#page a[href^='/browse?type=']").count() > 0,
    )
    ui.shot("Home: the pack, the six stat tiles, and the two summary tables")


@pytest.mark.scenario(
    scenario_id="A02",
    group="A",
    title="Every navigation link routes to its page and the current one is marked",
    feature="Shell · navigation",
    expected="Clicking each of the ten links changes the address, renders that page's heading, "
    "and leaves that link — and only that link — marked as current.",
)
def test_navigation_routes(ui, record):
    ui.goto("/")
    for label, path, nav_id, heading in NAV:
        ui.must(f"the {label} link is in the navigation", ui.visible(nav_id))
        ui.click(nav_id)
        url = ui.page.url
        ui.check(f"{label} goes to {path}", url.endswith(path), url)
        ui.check(f"{path} renders its heading", _page_heading(ui) == heading, _page_heading(ui))
        ui.check(f"{path} did not fail to render", "This page failed to render" not in ui.body())
        ui.check(f"the {label} link is marked as current", _marked(ui, nav_id))
        marked = [other for _, _, other, _ in NAV if _marked(ui, other)]
        ui.check(f"only {label} is marked while on {path}", marked == [nav_id], f"marked: {marked}")
        if path == "/health":
            ui.shot("The last page reached by the navigation, with its link marked as current")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A03",
    group="A",
    title="The navigation is grouped Home, Discover, Contribute, Manage",
    feature="Shell · navigation",
    expected="The four group headings are present, in that order, with the ten links under them.",
)
def test_navigation_groups(ui, record):
    ui.goto("/")
    sections = ui.page.locator(".ea-nav-section")
    found = [sections.nth(i).inner_text().strip() for i in range(sections.count())]
    ui.check(
        "the four groups are in order",
        found == ["Home", "Discover", "Contribute", "Manage"],
        f"found: {found}",
    )
    links = ui.page.locator(".mantine-AppShell-navbar a[href]")
    ui.check("ten links are offered", links.count() == 10, f"{links.count()} links")
    hrefs = {links.nth(i).get_attribute("href") for i in range(links.count())}
    ui.check(
        "every link in the model is offered",
        {path for _, path, _, _ in NAV}.issubset(hrefs),
        f"hrefs: {sorted(h for h in hrefs if h)}",
    )
    ui.shot("The navigation, grouped Home, Discover, Contribute and Manage")


@pytest.mark.scenario(
    scenario_id="A04",
    group="A",
    title="An address nobody recognises falls back to Home",
    feature="Shell · routing",
    expected="An unknown path renders Home rather than an error or a blank frame, "
    "and the shell around it is intact.",
)
def test_unknown_path(ui, record):
    ui.goto("/no-such-page")
    ui.check("the address is left as typed", ui.page.url.endswith("/no-such-page"), ui.page.url)
    ui.check(
        "Home is rendered instead", _page_heading(ui) == "Higher Education EA Metamodel", _page_heading(ui)
    )
    body = ui.body()
    ui.check("nothing reports a failure", "This page failed to render" not in body)
    ui.check("the Home content is there", "Elements by type" in body)
    ui.check("the header survived", ui.visible(HEADER))
    ui.check("the navigation survived", ui.visible("nav-browse"))
    # A fallback that keeps the unknown address means the navigation cannot mark Home; a
    # reader who bookmarks the page comes back to the same misleading address.
    ui.shot("An unknown address renders Home with the shell intact")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A05",
    group="A",
    title="The header carries the pack, the role, the branch and the way to change them",
    feature="Shell · header",
    expected="The header shows the pack badge, the role badge, the branch badge on main, the branch "
    "selector, an enabled new-branch button and the persona switcher.",
)
def test_header(ui, record):
    ui.goto("/")
    ui.must("the header is present", ui.visible(HEADER))
    header = ui.page.locator(HEADER).first.inner_text()

    ui.check("the application is named", "EA Repository" in header, header.replace("\n", " · ")[:120])
    ui.check("the pack is badged", "Higher Education EA Metamodel" in header)
    ui.check("the branch badge says main", ui.branch_badge() == "main", ui.branch_badge())
    ui.check("the role badge names the signed-in user", "Admin" in ui.role_badge(), ui.role_badge())
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
    ui.check("the burger is hidden on a wide screen", not ui.visible("nav-burger"))
    ui.shot(
        "The header: brand, branch badge and selector, new branch, role, persona and pack", selector=HEADER
    )


@pytest.mark.scenario(
    scenario_id="A06",
    group="A",
    title="At 480 px the burger opens the navigation",
    feature="Shell · narrow viewport",
    expected="On a narrow screen the navigation is out of the way behind a burger, the burger opens it, "
    "a link still routes, and choosing one closes it again.",
)
def test_narrow_viewport(ui, record):
    ui.goto("/")
    ui.narrow()
    try:
        ui.check("the burger appears", ui.visible("nav-burger"))
        ui.check("the navigation is out of the way", not _on_screen(ui, "#nav-browse"))
        ui.check("the header is still readable", ui.visible(HEADER))
        ui.check("the page is not scrolled sideways", _no_sideways_scroll(ui), _overflow(ui))
        ui.shot("At 480 px the navigation is behind a burger", full_page=False)

        ui.click("nav-burger")
        ui.check("the burger opens the navigation", _on_screen(ui, "#nav-browse"))
        ui.shot("The burger opens the four navigation groups over the page", full_page=False)

        ui.click("nav-browse")
        ui.check(
            "a link still routes from the narrow navigation", ui.page.url.endswith("/browse"), ui.page.url
        )
        ui.check("Browse renders at 480 px", _page_heading(ui) == "Browse", _page_heading(ui))
        ui.check("choosing a page closes the navigation again", not _on_screen(ui, "#nav-browse"))
    finally:
        ui.wide()
        ui.goto("/")


def _overflow(ui) -> str:
    widths = ui.page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    return f"scrollWidth {widths[0]} vs clientWidth {widths[1]}"


def _no_sideways_scroll(ui) -> bool:
    return bool(
        ui.page.evaluate(
            "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 2"
        )
    )


@pytest.mark.scenario(
    scenario_id="A07",
    group="A",
    title="The browser tab names the application on every page",
    feature="Shell · document title",
    expected="The tab reads EA Repository on Home and stays named while routing, never showing "
    "an updating placeholder.",
)
def test_tab_title(ui, record):
    ui.goto("/")
    ui.check("the tab names the application", ui.page.title() == "EA Repository", ui.page.title())
    ui.click("nav-metamodel")
    ui.check("routing does not blank the tab", ui.page.title() == "EA Repository", ui.page.title())
    ui.check("no updating placeholder is left behind", "Updating" not in ui.page.title(), ui.page.title())
    ui.shot("The Metamodel page, with the tab still named EA Repository")
    ui.goto("/")


@pytest.mark.scenario(
    scenario_id="A08",
    group="A",
    title="The new-branch button opens the shell's branch modal and closes without creating one",
    feature="Shell · new branch",
    expected="The + beside the branch selector opens a modal that explains what a branch is and asks "
    "for a name; Escape closes it and nothing is created.",
)
def test_new_branch_modal(ui, record):
    ui.goto("/")
    before = ui.page.locator("#branch-select").first.input_value()
    ui.click("branch-new-open")
    ui.must("the modal opens", ui.visible("branch-new-modal"))
    text = ui.text("branch-new-modal")
    ui.check("it is titled New branch", "New branch" in text, text[:80].replace("\n", " · "))
    ui.check("it says what a branch is", "starts from main" in text, text[:200].replace("\n", " · "))
    ui.check("it asks for a name", ui.visible("branch-new-name"))
    ui.check("it offers a work package", ui.visible("branch-new-wp"))
    ui.check("it offers to create and switch", ui.visible("branch-new-save"))
    ui.shot("The New branch modal, opened from the header")

    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("Escape closes it", not ui.visible("branch-new-modal"))
    ui.check(
        "nothing was created and the reader is still on main",
        ui.page.locator("#branch-select").first.input_value() == before,
        ui.page.locator("#branch-select").first.input_value(),
    )
    ui.check("the branch badge still says main", ui.branch_badge() == "main", ui.branch_badge())
