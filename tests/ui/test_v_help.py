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


def _kept(ui) -> dict:
    raw = ui.page.evaluate(f"() => window.localStorage.getItem('{SEEN}')")
    return json.loads(raw) if raw else {}


def _hint(ui) -> str:
    loc = ui.page.locator(HINT)
    return loc.inner_text().strip() if loc.count() else ""


def _drawer_open(ui) -> bool:
    return ui.page.locator(DRAWER).first.is_visible() if ui.page.locator(DRAWER).count() else False


def _focus(ui) -> str:
    """What has the keyboard: the element's tag and, for an input, its type."""
    return ui.page.evaluate(
        "() => { const e = document.activeElement; return e ? `${e.tagName} ${e.type || ''}`.trim() : ''; }"
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
    title="The help beside every screen's title opens that screen's help in a side panel, only when asked",
    feature="Help · the side panel",
    expected=(
        "Every screen of the navigation carries one help button beside its title. Pressing it — or "
        "the ? key — opens a side panel titled with the screen's name: why, what you see, how, the "
        "flow drawn, and what the reader's own role may do there. Escape closes it; moving to "
        "another screen closes it too. ? works from a checkbox, a switch or a segmented control "
        "that has the focus, and does nothing while the panel, or another dialog or side panel, is "
        "open."
    ),
)
def test_the_side_panel_opens_when_asked(ui, record):
    missing = []
    for path in SCREENS:
        ui.goto(path)
        if ui.page.locator(TITLE_BUTTON).count() != 1:
            missing.append(path)
    ui.check("every screen carries one help button beside its title", not missing, f"without one: {missing}")
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
