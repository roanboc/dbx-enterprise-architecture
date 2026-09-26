"""Group U — Connected systems: the enterprise's systems the assistant may read (initiative 26).

The page is an admin's decision laid out for everyone: which systems the assistant may read over
the Model Context Protocol, where each answers, which of its tools — each a read — it may call,
what it speaks for and as whom it is read. An admin connects and disconnects; everyone else reads
the list, so a reader can see what an answer may have consulted. Nothing here reaches a system:
keeping one is a record, and reading it happens when an answer needs it. So the round connects a
system that answers nowhere (the discard port on the machine it runs on) and needs no network.

A workspace connection can fill the form in, and the round has no workspace; the page says so
beside the picker rather than offering an empty list. Where a round does run with one, the
picker is read as offered instead.

The group runs last in file order and leaves nothing behind: every system it connects it also
disconnects, so no answer after it would try to read one.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui

PAGE = "/systems"
HEADING = "Connected systems"
EMPTY = "No system is connected: the assistant reads the model alone."
DEAD_URL = "http://127.0.0.1:9/mcp"  # nothing answers the protocol there, and nothing need
WIKI = "https://wiki.example.org/"
PAGE_PATTERN = r"/pages/(?P<page_id>\d+)"
PAGE_ARGUMENTS = '{"pageId": "{page_id}"}'
AS_NOBODY = "As nobody (a server open inside the network)"
READ_MODES = [
    "As the person asking",
    "With the organisation's credential",
    "As the application's own identity",
    "As nobody",
]
FIELDS = [
    "sys-name",
    "sys-url",
    "sys-tools",
    "sys-speaks-for",
    "sys-pages",
    "sys-page-tool",
    "sys-page-pattern",
    "sys-page-arguments",
    "sys-auth",
    "sys-credential",
    "sys-roles",
    "sys-save",
]
DISCONNECT = "#sys-list button:has-text('Disconnect')"


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    ui.goto(PAGE)
    heading = ui.page.locator("#page h1").first
    ui.must(
        "the Connected systems page rendered",
        heading.count() > 0 and heading.inner_text().strip() == HEADING,
        heading.inner_text() if heading.count() else ui.body()[:200],
    )


def _connect(ui, name: str, **fields: str) -> str:
    """Fill the form as an admin does and press Connect; what the page said back."""
    ui.fill("sys-name", name)
    ui.fill("sys-url", fields.get("url", DEAD_URL))
    ui.fill("sys-tools", fields.get("tools", "search"))
    for key, control in (
        ("pages", "sys-pages"),
        ("page_tool", "sys-page-tool"),
        ("page_pattern", "sys-page-pattern"),
        ("page_arguments", "sys-page-arguments"),
    ):
        if key in fields:
            ui.fill(control, fields[key])
    if "speaks_for" in fields:
        ui.multi_select("sys-speaks-for", fields["speaks_for"], exact=True)
    ui.select("sys-auth", fields.get("auth", "As nobody"))
    ui.click("sys-save")
    return ui.text("sys-feedback")


def _disconnect(ui, name: str) -> str:
    """Press Disconnect on the one card that names the system; what the page said back."""
    card = ui.page.locator("#sys-list .mantine-Paper-root", has_text=name).first
    card.get_by_role("button", name="Disconnect").click()
    ui.settle()
    return ui.text("sys-feedback")


def _read_modes(ui) -> list[str]:
    """What the Read select offers, leaving it closed again."""
    ui.click("sys-auth")
    offered = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    return offered


# --------------------------------------------------------------------------- the scenarios


@pytest.mark.scenario(
    scenario_id="U01",
    group="U",
    title="An admin opens Connected systems: nothing connected yet, the form, and why no workspace connection is offered",
    feature="Connected systems · the page",
    expected=(
        "The page is reached from the navigation and says the assistant reads the model alone while "
        "nothing is connected; an admin is given the form to connect a system — its address, tools, "
        "pages and how a page's id becomes the page tool's arguments, and the four ways it may be "
        "read — and the workspace connection picker says why it offers nothing rather than showing an "
        "empty list."
    ),
)
def test_the_page_as_an_admin(ui, record):
    ui.goto("/")
    ui.must("the navigation offers Connected systems", ui.visible("nav-systems"))
    ui.click("nav-systems")
    ui.check("the link opens /systems", ui.page.url.endswith(PAGE), ui.page.url)
    _open(ui)
    ui.check(
        "the subtitle says what a connected system is for, and what it is never",
        "cited as the system's" in ui.body() and "never written into the model" in ui.body(),
    )
    ui.check("with nothing connected it says so", EMPTY in ui.text("sys-list"), ui.text("sys-list"))
    missing = [f for f in FIELDS if not ui.visible(f)]
    ui.check("the form offers every field a system is kept with", not missing, f"not shown: {missing}")
    offered = _read_modes(ui)
    ui.check(
        "the four ways a system may be read are offered",
        all(any(o.startswith(mode) for o in offered) for mode in READ_MODES),
        str(offered),
    )
    note = ui.text("sys-connections-note")
    if ui.disabled("sys-connection"):
        ui.check(
            "with no workspace here, the picker says why it offers none",
            note.startswith("No workspace connection is listed:") and len(note) > 40,
            note or "(nothing beside the disabled picker)",
        )
    else:
        # A round run where a workspace is configured: the picker offers what the workspace has.
        ui.click("sys-connection")
        choices = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
        ui.page.keyboard.press("Escape")
        ui.settle()
        ui.check("the workspace's connections are offered to pick from", bool(choices), str(choices))
    ui.shot("Connected systems as an admin: nothing connected, and the form to connect one")


@pytest.mark.scenario(
    scenario_id="U02",
    group="U",
    title="Connecting a system read as nobody puts its card in the list, and Disconnect takes it away",
    feature="Connected systems · connect and disconnect",
    expected=(
        "Filled in and connected, a system answers nothing yet is kept — keeping it reaches nothing — "
        "and the page says the assistant may read it from the next answer; its card says where it "
        "answers, how it is read, the tools, the type it speaks for, the pages it answers for, the "
        "pattern that finds a page's id and what the page tool is given. Disconnect takes the card "
        "away and says so, and the list is empty again."
    ),
)
def test_connect_and_disconnect(ui, record):
    _open(ui)
    said = _connect(
        ui,
        "U wiki",
        tools="search, read_page",
        pages=WIKI,
        page_tool="read_page",
        page_pattern=PAGE_PATTERN,
        page_arguments=PAGE_ARGUMENTS,
        speaks_for="Data Entity",
    )
    ui.must(
        "the system was connected, and the page says when the assistant may read it",
        "Connected U wiki: the assistant may read it from the next answer." in said,
        said,
    )
    card = ui.text("sys-list")
    ui.check("its card is in the list", "U wiki" in card and EMPTY not in card, card[:300])
    ui.check("and it is on", "on" in card.lower().split(), card[:120])
    for what, shown in (
        ("where it answers", DEAD_URL),
        ("that it is read as nobody", AS_NOBODY),
        ("the tools the assistant may call", "search, read_page"),
        ("the type it speaks for, by its name", "Data Entity"),
        ("the pages it answers for, and the tool that reads one", f"{WIKI} with read_page"),
        ("the pattern that finds a page's id in its address", PAGE_PATTERN),
        ("what the page tool is given", PAGE_ARGUMENTS),
    ):
        ui.check(f"the card says {what}", shown in card, card[:400])
    ui.check("an admin may disconnect it", ui.visible(DISCONNECT))
    ui.shot("A system connected: its card says where it answers, as whom, and what it reads")

    said = _disconnect(ui, "U wiki")
    ui.check("Disconnect says what it let go", "Disconnected U wiki." in said, said)
    ui.check("and the list is empty again", EMPTY in ui.text("sys-list"), ui.text("sys-list"))
    ui.shot("Disconnected: the assistant reads the model alone again")


@pytest.mark.scenario(
    scenario_id="U03",
    group="U",
    title="What the page will not keep is said in one refusal, and nothing is connected",
    feature="Connected systems · refusals",
    expected=(
        "A system with an address that is not one, no tools, and a page pattern and arguments with no "
        "page tool — the arguments not even a JSON object — is refused in one red message naming "
        "each, the form keeps what was typed so it can be put right, and the list is unchanged."
    ),
)
def test_what_is_refused(ui, record):
    _open(ui)
    said = _connect(
        ui,
        "U broken",
        url="wiki.example.org/mcp",
        tools=" ",
        page_pattern=PAGE_PATTERN,
        page_arguments="[1]",
    )
    for what, words in (
        ("an address that is not one", "the address must start with http:// or https://"),
        ("a system with no tools", "list the tools the assistant may call"),
        ("page arguments that are not a JSON object", "the page arguments are a JSON object"),
        (
            "a pattern with no page tool to hand it to",
            "a page pattern or page arguments are for the page tool",
        ),
    ):
        ui.check(f"the refusal names {what}", words in said, said)
    ui.check("the form keeps what was typed", ui.page.locator("#sys-name").input_value() == "U broken")
    ui.check("and nothing was connected", EMPTY in ui.text("sys-list"), ui.text("sys-list"))
    ui.shot("A system the page will not keep: every reason in one refusal, the form as it was typed")


@pytest.mark.scenario(
    scenario_id="U04",
    group="U",
    title="A Reader sees what the assistant may consult, and neither the form nor Disconnect",
    feature="Connected systems · roles",
    expected=(
        "With a system connected by an admin, a Reader reads its card — what an answer may have "
        "consulted — with no Disconnect on it and, in place of the form, a sentence saying that "
        "which systems are read, and as whom, is an admin's decision; an Architect is told the "
        "same. Back as the admin, the system is disconnected again."
    ),
    role="reader",
)
def test_the_page_as_a_reader(ui, record):
    _open(ui)
    said = _connect(ui, "U catalogue", tools="lookup")
    ui.must("an admin connected a system for the others to read", "Connected U catalogue" in said, said)

    ui.persona("Reader")
    _open(ui)
    ui.check("a Reader reads the connected system's card", "U catalogue" in ui.text("sys-list"))
    ui.check("with no Disconnect on it", ui.page.locator(DISCONNECT).count() == 0)
    ui.check("and no form to connect one", not ui.visible("sys-save") and not ui.visible("sys-name"))
    ui.check(
        "the page says why, as a sentence",
        "A Reader may not connect a system: which of the enterprise's systems the assistant reads, "
        "and as whom, is an admin's decision." in ui.body(),
        ui.body()[-400:],
    )
    ui.shot("Connected systems as a Reader: the list, and why there is no form")

    ui.persona("Architect")
    _open(ui)
    ui.check(
        "an Architect is told the same",
        "An Architect may not connect a system" in ui.body() and ui.page.locator(DISCONNECT).count() == 0,
        ui.body()[-300:],
    )

    ui.persona("Admin")
    _open(ui)
    said = _disconnect(ui, "U catalogue")
    ui.check("back as the admin, the system is disconnected", "Disconnected U catalogue." in said, said)
    ui.check("leaving nothing connected for the groups after", EMPTY in ui.text("sys-list"))
