"""Group V — Help and first visits (initiative 27).

A newcomer is met once, and an experienced reader is not met at all. The welcome stands under
the title of the first screen a browser opens, once; each screen's one-line tip stands there on
its first visit, once, until tips are turned off; the help beside every screen's title opens
only when it is pressed, in a side panel beside the screen rather than over it. What a person
has closed is kept by their browser (`help-seen`, local storage), never by the store.

Every other group runs in a browser seeded as a returning reader. These scenarios open a
browser of their own, with nothing kept, which is what a newcomer's is.
"""

from __future__ import annotations

import json

import pytest
from tests.ui.conftest import VIEWPORT
from tests.ui.harness import Ui

pytestmark = pytest.mark.gui

SEEN = "help-seen"  # the local store's key, and the id of the component that keeps it
DRAWER = ".mantine-Drawer-content:has(#help-title)"  # the help's side panel, not a page's own drawer
TITLE_BUTTON = "#page .ea-help-button"
HINT = "#help-hint"
SCREENS = ["/browse", "/ask", "/impact", "/target", "/branches", "/import", "/feeds", "/propose"]
SCREENS += ["/metamodel", "/organisations", "/systems", "/users", "/health", "/guide", "/"]


@pytest.fixture
def newcomer(browser, server, run_dir, record):
    """A browser that has never opened the application: nothing kept, nothing closed."""
    context = browser.new_context(
        viewport=VIEWPORT, device_scale_factor=1, locale="en-AU", timezone_id="UTC", reduced_motion="reduce"
    )
    page = context.new_page()
    page.set_default_timeout(20_000)
    helper = Ui(page=page, base_url=server, run_dir=run_dir)
    helper.bind(record)
    try:
        yield helper
    finally:
        helper.unbind()
        context.close()


#: Whether the help button's top is level with the title row's and its right edge with the row's.
TOP_RIGHT = """() => {
  const row = document.querySelector('#page .ea-page-title');
  const button = document.querySelector('#page .ea-help-button');
  if (!row || !button) return false;
  const r = row.getBoundingClientRect(), b = button.getBoundingClientRect();
  return Math.abs(b.top - r.top) <= 2 && Math.abs(b.right - r.right) <= 2;
}"""


def _kept(ui) -> dict:
    raw = ui.page.evaluate(f"() => window.localStorage.getItem('{SEEN}')")
    return json.loads(raw) if raw else {}


def _hint(ui) -> str:
    loc = ui.page.locator(HINT)
    return loc.inner_text().strip() if loc.count() else ""


def _drawer_open(ui) -> bool:
    return ui.page.locator(DRAWER).first.is_visible() if ui.page.locator(DRAWER).count() else False


def _shut(ui) -> bool:
    """Wait for the side panel to finish closing, and say whether it did."""
    try:
        ui.page.wait_for_selector(DRAWER, state="hidden", timeout=5_000)
        return True
    except Exception:  # noqa: BLE001 — a panel left open is the finding
        return False


def _focus(ui) -> str:
    """What has the keyboard: the element's tag and, for an input, its type."""
    return ui.page.evaluate(
        "() => { const e = document.activeElement; return e ? `${e.tagName} ${e.type || ''}`.trim() : ''; }"
    )


#: Whether the element a link points at stands at the top of the window, below the header, or as
#: near it as the page scrolls: the last section of a long page cannot be brought any higher.
LANDED = """id => {
  const el = document.getElementById(id);
  if (!el) { return false; }
  const top = el.getBoundingClientRect().top;
  const bottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
  return window.scrollY > 0 && top > -20 && (top < 150 || (bottom && top < window.innerHeight));
}"""


def _landed(ui, anchor: str) -> bool:
    """Wait for a link to land on its section, and say whether it stayed there."""
    try:
        ui.page.wait_for_function(LANDED, arg=anchor, timeout=10_000)
        ui.page.wait_for_timeout(400)  # the page may still be drawing what stands above it
        return bool(ui.page.evaluate(LANDED, anchor))
    except Exception:  # noqa: BLE001 — where the page stopped is the finding
        return False


def _where(ui, anchor: str) -> str:
    """Where the page stands, for the report when a link did not land."""
    return ui.page.evaluate(
        "id => { const el = document.getElementById(id); return JSON.stringify({scrollY: window.scrollY, "
        "top: el ? Math.round(el.getBoundingClientRect().top) : null, hash: location.hash, "
        "path: location.pathname}); }",
        anchor,
    )


@pytest.mark.scenario(
    scenario_id="V01",
    group="V",
    title="A newcomer is welcomed once, on the first screen they open, and not again",
    feature="Help · the welcome",
    expected=(
        "The first screen a browser opens carries the welcome under its title — what the repository "
        "is for, the navigation's groups and where the reader's role starts — and nothing covers the "
        "screen. A reload, and every later screen, shows no welcome; the browser, not the store, "
        "keeps that it was shown."
    ),
)
def test_the_welcome_shows_once(newcomer, record):
    ui = newcomer
    ui.goto("/browse")
    ui.page.wait_for_selector(".ea-welcome", timeout=15_000)
    text = _hint(ui)
    ui.must("the welcome stands under the title", "Welcome to the EA Repository" in text, text[:200])
    ui.check(
        "it names the navigation's groups",
        all(g in text for g in ("Discover", "Contribute", "Manage")),
        text[:300],
    )
    ui.check("it says where the reader's role starts", "You are signed in as" in text, text[:300])
    ui.check("the side panel is not open", not _drawer_open(ui))
    ui.shot("the welcome on a first visit")
    ui.check("the browser keeps that it was shown", _kept(ui).get("welcome") is True, json.dumps(_kept(ui)))
    ui.goto("/browse")
    ui.check("a reload shows no welcome", ui.page.locator(".ea-welcome").count() == 0, _hint(ui)[:200])


@pytest.mark.scenario(
    scenario_id="V02",
    group="V",
    title="Each screen's tip shows on its first visit only, and Turn off tips stops them all",
    feature="Help · first-visit tips",
    expected=(
        "After the welcome, the first visit to another screen shows one line under its title saying "
        "what the screen is for, with Show me how, Got it and Turn off tips. The second visit shows "
        "nothing. Turn off tips leaves every later screen without one."
    ),
)
def test_the_tips_show_once_and_can_be_turned_off(newcomer, record):
    ui = newcomer
    ui.goto("/")  # the welcome is spent here
    ui.goto("/ask")
    ui.page.wait_for_selector(".ea-tip", timeout=15_000)
    ui.must("Ask's first visit carries its tip", bool(_hint(ui)), _hint(ui))
    ui.shot("a first-visit tip")
    ui.goto("/ask")
    ui.check("the second visit carries none", ui.page.locator(".ea-tip").count() == 0, _hint(ui))
    ui.goto("/impact")
    ui.page.wait_for_selector(".ea-tip", timeout=15_000)
    ui.page.get_by_role("button", name="Turn off tips").click()
    ui.settle()
    ui.check("turning tips off closes this one", ui.page.locator(".ea-tip").count() == 0)
    ui.check("the browser keeps that tips are off", _kept(ui).get("tips") is False, json.dumps(_kept(ui)))
    ui.goto("/target")
    ui.check("a new screen now shows no tip", ui.page.locator(".ea-tip").count() == 0, _hint(ui))


@pytest.mark.scenario(
    scenario_id="V03",
    group="V",
    title="The help at the top right of every screen opens that screen's help in a side panel, only when asked",
    feature="Help · the side panel",
    expected=(
        "Every screen of the navigation, and the Element page, carries one help button at the top "
        "right of its title's row, whatever wraps beside the title. Pressing it — or "
        "the ? key — opens a side panel titled with the screen's name: why, what you see, how, the "
        "flow drawn, and what the reader's own role may do there. Escape closes it; moving to "
        "another screen closes it too. ? works from a checkbox, a switch or a segmented control "
        "that has the focus, and does nothing while the panel, or another dialog or side panel, is "
        "open."
    ),
)
def test_the_side_panel_opens_when_asked(ui, record):
    missing, astray = [], []
    for path in [*SCREENS, "/element/LDC-CURR"]:
        ui.goto(path)
        if ui.page.locator(TITLE_BUTTON).count() != 1:
            missing.append(path)
        elif not ui.page.evaluate(TOP_RIGHT):
            astray.append(path)
    ui.check("every screen carries one help button beside its title", not missing, f"without one: {missing}")
    ui.check(
        "it stands in one place, the top right of the title's row, whatever wraps beside the title",
        not astray,
        f"elsewhere on: {astray}",
    )
    ui.goto("/branches")
    ui.check("the panel is shut until asked", not _drawer_open(ui))
    ui.click(TITLE_BUTTON)
    ui.page.wait_for_selector(DRAWER, state="visible", timeout=15_000)
    panel = ui.page.locator(DRAWER).first.inner_text()
    ui.must("the panel is the screen's help", "Help — Branches" in panel, panel[:200])
    ui.check(
        "it says why, what, how and what the role may do",
        all(p in panel for p in ("Why", "What you see", "How", "Your role")),
        panel[:400],
    )
    ui.wait_mermaid()
    ui.check("its flow is drawn", ui.page.locator(f"{DRAWER} .ea-mermaid svg").count() >= 1)
    ui.shot("the help of Branches in its side panel", full_page=False)
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.check("Escape closes it", not _drawer_open(ui))
    ui.page.locator("body").click(position={"x": 5, "y": 400})
    ui.page.keyboard.press("?")
    ui.settle()
    ui.check("the ? key opens it", _drawer_open(ui))
    title = ui.text("help-title")
    ui.page.keyboard.press("?")
    ui.settle()
    ui.check("? on the open panel leaves it as it is", _drawer_open(ui) and ui.text("help-title") == title)
    ui.goto("/ask")
    ui.check("another screen closes it", not _drawer_open(ui))
    # A control that takes no characters leaves ? to the help: a segmented control is a radio
    # underneath, and a switch a checkbox.
    ui.goto("/branches")
    ui.segmented("br-status", "Merged")
    focused = _focus(ui)
    ui.page.keyboard.press("?")
    ui.settle()
    ui.check(
        "? opens it from a segmented control that has the focus",
        focused == "INPUT radio" and _drawer_open(ui),
        focused,
    )
    ui.page.keyboard.press("Escape")
    ui.settle()
    ui.goto("/target")
    ui.page.locator("#tg-only-changes").focus()  # as the keyboard reaches it, and Space flips it
    ui.page.keyboard.press("Space")
    ui.settle()
    focused = _focus(ui)
    ui.page.keyboard.press("?")
    ui.settle()
    ui.check(
        "? opens it from a switch that has the focus",
        focused == "INPUT checkbox" and _drawer_open(ui),
        focused,
    )
    ui.page.keyboard.press("Escape")
    ui.settle()
    # Another panel over the screen keeps the keyboard: ? neither opens the help underneath it
    # nor moves the focus into a panel nobody can see.
    ui.goto("/browse")
    ui.click("browse-more-open")
    ui.page.wait_for_selector(".mantine-Drawer-content:has-text('Narrow the list')", state="visible")
    ui.page.keyboard.press("?")
    ui.settle()
    ui.check("? does nothing while another side panel is open", not _drawer_open(ui))
    lost = ui.page.evaluate(f"() => !!(document.activeElement && document.activeElement.closest('{DRAWER}'))")
    ui.check("the keyboard stays in the panel that is open", not lost, _focus(ui))
    ui.shot("? with the filters open leaves them on top", full_page=False)
    ui.page.keyboard.press("Escape")
    ui.settle()


@pytest.mark.scenario(
    scenario_id="V04",
    group="V",
    title="The Guide opens with Getting started, gathers every screen's help, and brings the welcome back",
    feature="Help · the Guide",
    expected=(
        "The Guide lists Getting started, the screens and the roles; Getting started and each "
        "screen draw their flows; Show the welcome and tips again clears what the browser kept, so the "
        "next screen shows the welcome once more."
    ),
)
def test_the_guide_gathers_the_help(newcomer, record):
    ui = newcomer
    ui.goto("/")
    ui.goto("/guide")
    body = ui.body()
    ui.must("the Guide opens with Getting started", "Getting started" in body, body[:200])
    ui.check("it gathers the screens' help", "The screens" in body and "Browse" in body)
    ui.check("the roles follow", "Solution architect" in body and "What belongs in the repository" in body)
    blocks = ui.page.locator(".ea-mermaid").count()
    ui.check("Getting started and every screen carry a diagram", blocks >= 16, str(blocks))
    try:
        ui.wait_mermaid(blocks)
        drawn = True
    except Exception:  # noqa: BLE001 — how many were drawn is the finding
        drawn = False
    svgs = ui.page.locator(".ea-mermaid svg")
    ui.check(
        "every diagram on the Guide is drawn", drawn and svgs.count() >= blocks, f"{svgs.count()} of {blocks}"
    )
    broken = [i for i in range(svgs.count()) if "Syntax error" in (svgs.nth(i).text_content() or "")]
    ui.check("no diagram shows a syntax error", not broken, str(broken))
    ui.shot("the Guide")
    ui.page.get_by_role("button", name="Show the welcome and tips again").click()
    ui.settle()
    ui.check("the browser forgets what was closed", _kept(ui).get("welcome") is False, json.dumps(_kept(ui)))
    ui.goto("/impact")
    ui.page.wait_for_selector(".ea-welcome", timeout=15_000)
    ui.check("the next screen welcomes again", "Welcome to the EA Repository" in _hint(ui))


@pytest.mark.scenario(
    scenario_id="V05",
    group="V",
    title="At 480 px the welcome, a tip and the side panel stay readable, with nothing to scroll sideways",
    feature="Help · the narrow viewport",
    expected=(
        "On a narrow screen the welcome's groups stack, a tip's buttons wrap under its line, and the "
        "side panel fits the width; the page never scrolls sideways."
    ),
)
def test_help_at_480(newcomer, record):
    ui = newcomer
    ui.narrow()
    ui.goto("/")
    ui.page.wait_for_selector(".ea-welcome", timeout=15_000)
    sideways = ui.page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1")
    ui.check("the welcome causes no sideways scroll", not sideways)
    ui.shot("the welcome at 480 px")
    ui.click(TITLE_BUTTON)
    ui.page.wait_for_selector(DRAWER, state="visible", timeout=15_000)
    box = ui.page.locator(DRAWER).first.bounding_box() or {"width": 10_000}
    ui.check("the side panel fits the width", box["width"] <= 481, str(box))
    ui.shot("the side panel at 480 px", full_page=False)


def _dash_call(url: str) -> bool:
    """A callback's request; its address carries a query string, so a glob would miss it."""
    return "/_dash-update-component" in url


def _presses(post_data: str | None) -> bool:
    """Whether a callback request carries a press on the welcome, a tip or the Guide."""
    try:
        body = json.loads(post_data or "{}")
    except ValueError:
        return False
    for group in body.get("inputs", []):
        for item in group if isinstance(group, list) else [group]:
            key = item.get("id") if isinstance(item, dict) else None
            if isinstance(key, dict) and key.get("type") == "help-action" and item.get("value"):
                return True
    return False


@pytest.mark.scenario(
    scenario_id="V06",
    group="V",
    title="Turn off tips holds when the reader moves on before the server has answered the press",
    feature="Help · first-visit tips",
    expected=(
        "The browser keeps the press the moment it is made. With the server's answer to Turn off tips "
        "held back and the reader already on the next screen, that screen shows no tip; once the answer "
        "is let through, tips are still off and the screen after shows none either. What the server says "
        "a screen showed reaches the browser as a patch (help-patch) merged into what it holds, never "
        "written over it."
    ),
)
def test_tips_off_holds_when_the_reader_moves_on(newcomer, record):
    ui = newcomer
    ui.goto("/")  # the welcome is spent here
    ui.goto("/impact")
    ui.page.wait_for_selector(".ea-tip", timeout=15_000)
    held: list = []

    def hold(route, request):  # noqa: ANN001 — playwright's route and request
        if _presses(request.post_data):
            held.append(route)
        else:
            route.continue_()

    def first_visit(response) -> bool:  # noqa: ANN001 — playwright's response
        return _dash_call(response.url) and '"help-screen"' in (response.request.post_data or "")

    ui.page.route(_dash_call, hold)
    try:
        ui.page.get_by_role("button", name="Turn off tips").click()
        ui.page.wait_for_timeout(200)  # a moment, not the server's answer: that is held
        kept = _kept(ui)
        ui.check("the browser keeps the press at once", kept.get("tips") is False, json.dumps(kept))
        with ui.page.expect_response(first_visit, timeout=20_000):
            ui.page.locator("#nav-target").click()
        ui.page.wait_for_timeout(600)  # the answer drawn, if it drew anything
        ui.check("the server's answer to the press was held back", len(held) >= 1, str(len(held)))
        ui.check(
            "the next screen, reached before that answer, shows no tip",
            ui.page.locator(".ea-tip").count() == 0,
            _hint(ui),
        )
    finally:
        for route in held:  # let through before the handler goes, which would settle them itself
            route.continue_()
        ui.page.unroute(_dash_call, hold)
    ui.settle()
    kept = _kept(ui)
    ui.check("tips are still off once the answer lands", kept.get("tips") is False, json.dumps(kept))
    ui.goto("/feeds")
    ui.check("the screen after shows no tip either", ui.page.locator(".ea-tip").count() == 0, _hint(ui))


@pytest.mark.scenario(
    scenario_id="V07",
    group="V",
    title="A link to a section of the Guide lands on that section",
    feature="Help · the Guide",
    expected=(
        "A link in the Guide's contents scrolls to its section. From another screen, the side panel's "
        "link to the guide for the reader's role opens the Guide at that section. On the Guide itself, "
        "a link in the side panel closes the panel and scrolls to its section. An address naming a "
        "section, opened afresh, lands on it too."
    ),
)
def test_guide_links_land_on_their_section(ui, record):
    ui.goto("/guide")
    ui.page.locator(".ea-guide-contents a[href='#screen-users']").first.click()
    ui.check(
        "a link in the Guide's contents lands on its section",
        _landed(ui, "screen-users"),
        _where(ui, "screen-users"),
    )
    ui.shot("the Guide at Users and roles, from its contents", full_page=False)

    ui.goto("/browse")
    ui.click(TITLE_BUTTON)
    ui.page.wait_for_selector(DRAWER, state="visible", timeout=15_000)
    link = ui.page.locator(f"{DRAWER} a", has_text="The guide for your role").first
    role = (link.get_attribute("href") or "#").split("#", 1)[1]
    link.click()
    ui.settle()
    ui.check("the side panel's link opens the Guide", ui.page.evaluate("() => location.pathname") == "/guide")
    ui.check("it lands on the guide for the reader's role", _landed(ui, role), _where(ui, role))
    ui.check("the panel closes behind it", _shut(ui))
    ui.shot("the Guide at the reader's role, from the side panel of Browse", full_page=False)

    ui.click(TITLE_BUTTON)
    ui.page.wait_for_selector(DRAWER, state="visible", timeout=15_000)
    ui.page.locator(f"{DRAWER} a", has_text="Getting started").first.click()
    ui.settle()
    ui.check("on the Guide, a link in the side panel closes it", _shut(ui))
    ui.check("and lands on its section", _landed(ui, "getting-started"), _where(ui, "getting-started"))
    ui.shot("the Guide at Getting started, from its own side panel", full_page=False)

    ui.goto("/guide#the-boundary")
    ui.check(
        "an address naming a section, opened afresh, lands on it",
        _landed(ui, "the-boundary"),
        _where(ui, "the-boundary"),
    )
    ui.shot("the Guide opened at the boundary", full_page=False)
