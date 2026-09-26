"""Group T — Deep dives: a brief settled on Ask, a deep dive written and kept, the ones kept.

Initiative 25 adds a second way to ask. The reader chooses a deep dive beside the quick answer,
says what they need to know, and the assistant settles a brief with them — what it is about,
which kind of analysis, how far it reaches, which layers, what it is for — each question with
its choices, the brief read back as one sentence. Written, the deep dive is kept under the
reader's name and opened on the Kept tab beside the brief, where it hands out a pack — a PDF and
a draw.io file per diagram — and is rated, run again or withdrawn. There is no page of its own:
everything lives in Ask's deep mode, and the navigation offers Ask alone.

What the group proves is the part only a browser sees. The questions are controls wired to a
store; an answer has to reach the sentence; Write has to stay off until the brief can be
written, and say why; the pack has to arrive as a ZIP whose PDF is a PDF and whose draw.io
files parse, numbered from the context down to the detail. The deep dives kept have to narrow,
open, show their rating as stars, take one rating per person and let that person clear it, run
a deep dive again and withdraw one; and the element's own page has to list the deep dives that
cite it. The rules underneath — the brief, the analyses, the maturity, the work in flight, the
findings, the layout — are proven in `tests/test_deep_dive_*.py`.

It writes deep dives, which nothing else in the round reads, into the seeded organisation.
Nothing is asserted about a total: another run of the group may have kept deep dives before it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

import pytest

pytestmark = pytest.mark.gui

SUBJECT = "PAC-CMS"
SUBJECT_NAME = "Curriculum Management System"
QUESTION = f"What happens if {SUBJECT} is decommissioned?"
SENTENCE = "ask-dd-sentence"


def _q(ui, kind: str, qid: str) -> str:
    return ui.pm(qid=qid, type=kind)


def _start(ui, question: str = QUESTION) -> None:
    ui.goto("/ask?mode=deep")
    ui.must("the deep mode opened from the address", ui.visible("ask-dd-input"))
    ui.fill("ask-dd-input", question)
    ui.click("ask-dd-start")
    ui.page.wait_for_selector(f"#{SENTENCE}", timeout=30_000)
    ui.settle()


def _card(ui, qid: str):
    """One question's card. A Mantine radio or checkbox group keeps its id to itself, so the
    card is found by the Answer button it holds, whose id is in the page."""
    send = ui.page.locator(ui._sel(_q(ui, "ask-dd-q-send", qid)))
    return ui.page.locator(".ea-question").filter(has=send).first


def _choose(ui, qid: str, label: str) -> None:
    _card(ui, qid).get_by_label(label, exact=True).check(force=True)
    ui.settle()
    ui.click(_q(ui, "ask-dd-q-send", qid))


def _written(ui, question: str = QUESTION) -> str:
    """Start, write and return the title of the deep dive kept, opened on the Kept tab."""
    _start(ui, question)
    ui.click("ask-dd-write")
    ui.page.wait_for_selector("#dd-pack", timeout=90_000)
    ui.settle()
    return ui.page.locator("#dd-detail h2").first.inner_text().strip()


def _kept(ui, search: str = "") -> None:
    ui.goto(f"/ask?mode=deep&tab=kept{search}")
    ui.must("the Kept tab opened from the address", ui.visible("dd-list"))


def _open_kept(ui, title: str) -> None:
    _kept(ui)
    link = ui.page.locator("#dd-list a", has_text=title).first
    ui.must("the deep dives kept list it", link.count() > 0, ui.text("dd-list")[:300])
    link.click()
    ui.page.wait_for_selector("#dd-rate", timeout=20_000)
    ui.settle()


def _rate(ui, stars: int, why: str = "") -> None:
    ui.page.locator(f"#dd-detail .mantine-Rating-input[value='{stars}']").first.locator(
        "xpath=following-sibling::label"
    ).click()
    if why:
        ui.fill("dd-why", why)
    ui.click("dd-rate")


def _stars_in(ui, scope: str, timeout: float = 20_000) -> bool:
    """Whether a read-only star rating is drawn under `scope`. Read-only, Mantine draws the stars
    as symbols with no radio inputs behind them, so it is the rating root that is looked for;
    the list is redrawn by a callback, so it is waited for rather than read at once."""
    try:
        ui.page.wait_for_selector(f"{scope} .mantine-Rating-root [data-read-only='true']", timeout=timeout)
    except Exception:  # noqa: BLE001 — the check below records what was not there
        return False
    return True


# ---------------------------------------------------------------------------------- Ask


@pytest.mark.scenario(
    scenario_id="T01",
    group="T",
    title="A deep dive is a choice beside the quick answer, and the ones kept are a tab of it",
    feature="Deep dives · the mode",
    expected=(
        "Ask opens on the quick answer with a switch to Deep dive; switching shows the New deep "
        "dive and Kept deep dives tabs and hides the question box; /ask?mode=deep&tab=kept opens "
        "on the deep dives kept; the navigation offers Ask and no separate Deep dives link."
    ),
)
def test_the_mode_switch(ui, record):
    ui.goto("/ask")
    ui.must("the quick answer is shown first", ui.visible("ask-input"))
    ui.check("the deep panel waits hidden", not ui.visible("ask-dd-input"))
    ui.segmented("ask-mode", "Deep dive")
    ui.check("switching shows the deep panel", ui.visible("ask-dd-input"))
    ui.check("and hides the quick question box", not ui.visible("ask-input"))
    tabs = ui.text("ask-dd-tabs")
    ui.check(
        "the deep mode offers a new deep dive and the ones kept",
        "New deep dive" in tabs and "Kept deep dives" in tabs,
    )
    links = [a.inner_text().strip() for a in ui.page.locator(".mantine-AppShell-navbar a").all()]
    ui.check("the navigation has no separate Deep dives link", "Deep dives" not in links, str(links))
    _kept(ui)
    ui.check("the address opens the deep dives kept", ui.visible("dd-list") and not ui.visible("ask-input"))
    ui.shot("Ask, deep mode, the deep dives kept")


@pytest.mark.scenario(
    scenario_id="T02",
    group="T",
    title="The brief starts from the reader's words and every answer reaches its sentence",
    feature="Deep dives · the brief",
    expected=(
        "A question naming PAC-CMS starts an impact analysis of it; answering three steps, the "
        "application layer and a purpose in words each changes the sentence; Write is on."
    ),
)
def test_the_brief(ui, record):
    _start(ui)
    sentence = ui.text(SENTENCE)
    ui.check("the words named the subject", f"{SUBJECT_NAME} [{SUBJECT}]" in sentence, sentence)
    ui.check("and pointed to an impact analysis", sentence.startswith("An impact analysis"), sentence)
    body = ui.text("ask-dd-brief")
    for question in (
        "What should the analysis be about?",
        "Which kind of analysis?",
        "How far should it reach",
    ):
        ui.check(f"it asks: {question}", question in body)
    _choose(ui, "reach", "Three steps")
    ui.check("three steps reaches the sentence", "three steps out" in ui.text(SENTENCE), ui.text(SENTENCE))
    group = _card(ui, "layers")
    group.get_by_label("Every layer", exact=True).uncheck(force=True)
    group.get_by_label("Application", exact=True).check(force=True)
    ui.settle()
    ui.click(_q(ui, "ask-dd-q-send", "layers"))
    ui.check(
        "one layer reaches the sentence", "the application layer" in ui.text(SENTENCE), ui.text(SENTENCE)
    )
    ui.page.locator(ui._sel(_q(ui, "ask-dd-q-text", "purpose"))).first.fill("decide whether to replace it")
    ui.settle()
    ui.click(_q(ui, "ask-dd-q-send", "purpose"))
    ui.check("the purpose reaches the sentence", "decide whether to replace it" in ui.text(SENTENCE))
    ui.check("Write is on", not ui.disabled("ask-dd-write"))
    ui.shot("The brief, settled")


@pytest.mark.scenario(
    scenario_id="T03",
    group="T",
    title="A brief without a kind of analysis cannot be written, and says so",
    feature="Deep dives · the brief",
    expected=(
        "Words that name an element but no kind leave Write off with 'Pick the kind of analysis "
        "first.' beside it; picking Landscape turns it on."
    ),
)
def test_write_waits_for_the_kind(ui, record):
    _start(ui, SUBJECT)
    ui.check("Write is off", ui.disabled("ask-dd-write"))
    ui.check("and says why", "Pick the kind of analysis first." in ui.text("ask-dd-write-hint"))
    _choose(ui, "kind", "Landscape — What makes up this area?")
    ui.check("the kind reaches the sentence", ui.text(SENTENCE).startswith("A landscape analysis"))
    ui.check("Write is on once the kind is picked", not ui.disabled("ask-dd-write"))


@pytest.mark.scenario(
    scenario_id="T04",
    group="T",
    title="The deep dive is written, kept, opened where it is kept, and its pack downloads",
    feature="Deep dives · the pack",
    expected=(
        "Write keeps the deep dive and opens it on the Kept tab with its summary, the work in "
        "flight and its findings; Download the pack (dd-pack) hands out one ZIP holding "
        "deep-dive.pdf and draw.io files numbered 01 on, level 1 first, each parsing with an "
        "identifier on every element shape."
    ),
)
def test_written_and_downloaded(ui, record):
    title = _written(ui)
    ui.check("it is titled for its kind and subject", title.startswith(f"Impact: {SUBJECT_NAME}"), title)
    ui.check("it opened on the Kept tab", "tab=kept" in ui.page.url and "open=" in ui.page.url, ui.page.url)
    detail = ui.text("dd-detail")
    ui.check("it says how far it can be trusted", "confidence:" in detail.lower())
    ui.check("it names the work in flight", "Work in flight" in detail and "WP-CMS-UPGRADE" in detail)
    ui.shot("The deep dive, written and opened where it is kept")
    path = ui.download("dd-pack", ".zip")
    names = zipfile.ZipFile(path).namelist()
    pdfs = [n for n in names if n.endswith("/deep-dive.pdf")]
    ui.must("the pack holds the PDF", len(pdfs) == 1, str(names[:5]))
    ui.check("the PDF is a PDF", zipfile.ZipFile(path).read(pdfs[0]).startswith(b"%PDF"))
    diagrams = sorted(n.rsplit("/", 1)[1] for n in names if n.endswith(".drawio"))
    ui.check("it holds a draw.io file per diagram", len(diagrams) >= 8, str(diagrams))
    levels = [int(m.group(1)) for d in diagrams if (m := re.match(r"\d\d-level-(\d)-", d))]
    ui.check(
        "numbered top-down, the context first", levels == sorted(levels) and levels[:1] == [1], str(diagrams)
    )
    ui.check("and nothing in Markdown", not any(n.endswith(".md") for n in names))
    for name in [n for n in names if n.endswith(".drawio")]:
        root = ET.fromstring(zipfile.ZipFile(path).read(name))
        objects = list(root.iter("object"))
        charted = "-maturity-" in name or "-findings-by-" in name
        ui.check(
            f"{name.rsplit('/', 1)[1]} parses, with an identifier on every element shape",
            (charted or objects) and all(o.get("ea_id") for o in objects),
        )


# ----------------------------------------------------------------------- the ones kept


@pytest.mark.scenario(
    scenario_id="T05",
    group="T",
    title="The deep dives kept narrow, open one, and show its rating as stars",
    feature="Deep dives · kept",
    expected=(
        "The Kept tab lists the deep dive; narrowing by kind to Landscape leaves it out; narrowing "
        "to what cites PAC-CMS keeps it; opened, four stars given to it show as four stars in the "
        "list and beside its title."
    ),
)
def test_the_ones_kept(ui, record):
    title = _written(ui)
    _kept(ui)
    ui.must("the Kept tab lists it", title in ui.text("dd-list"))
    ui.select("dd-kind", "Landscape", exact=True)
    ui.check("narrowed to landscapes, the impact is left out", title not in ui.text("dd-list"))
    _kept(ui, f"&element={SUBJECT}")
    ui.check("narrowed to what cites PAC-CMS, it is there", title in ui.text("dd-list"))
    _open_kept(ui, title)
    ui.check("opened, it reads its brief", "An impact analysis" in ui.text("dd-detail"))
    _rate(ui, 4, "Clear enough to take to the board")
    ui.check("the rating is recorded", "Rated 4 of 5" in ui.text("dd-detail"), ui.text("dd-detail")[:300])
    ui.check("the list shows its rating as stars", _stars_in(ui, "#dd-list"), ui.text("dd-list")[:300])
    ui.check("with how many rated it", "(1)" in ui.text("dd-list"), ui.text("dd-list")[:300])
    ui.shot("A deep dive opened among the ones kept, rated with stars")


@pytest.mark.scenario(
    scenario_id="T08",
    group="T",
    title="One rating per person: rating again replaces it, and clearing it takes it back",
    feature="Deep dives · rating",
    expected=(
        "Two stars then five from the same reader leave one rating of five; Clear my rating "
        "takes it back, the deep dive reads 'not rated yet', and it can be rated again."
    ),
)
def test_one_rating_per_person(ui, record):
    title = _written(ui)
    _open_kept(ui, title)
    _rate(ui, 2)
    _rate(ui, 5, "Better on a second read")
    detail = ui.text("dd-detail")
    ui.check(
        "one rating, the later one", "(1)" in detail and "Better on a second read" in detail, detail[-300:]
    )
    ui.check("Clear my rating is offered once there is one", ui.visible("dd-unrate"))
    ui.click("dd-unrate")
    detail = ui.text("dd-detail")
    ui.check("clearing it says so", "Your rating is cleared" in detail, detail[:300])
    ui.check("and it is not rated any more", "not rated yet" in detail)
    ui.check("Clear my rating is gone with it", not ui.visible("dd-unrate"))
    ui.check("it can be rated again", not ui.disabled("dd-rate"))


@pytest.mark.scenario(
    scenario_id="T06",
    group="T",
    title="A deep dive is run again, withdrawn by its author, and cannot be withdrawn by another reader",
    feature="Deep dives · run again and withdraw",
    expected=(
        "Run again opens a new deep dive; withdrawing it takes it out of the list and Show "
        "withdrawn brings it back marked; a Reader opening the Admin's deep dive is offered no "
        "Withdraw, and may rate it."
    ),
)
def test_again_and_withdraw(ui, record):
    title = _written(ui)
    first = ui.page.url
    ui.click("dd-again")
    ui.page.wait_for_function(f"location.href !== {first!r}", timeout=90_000)
    ui.page.wait_for_selector("#dd-withdraw", timeout=20_000)
    ui.settle()
    ui.check("run again opened a new deep dive", ui.page.url != first, ui.page.url)
    again = ui.page.url.split("open=")[-1]
    ui.click("dd-withdraw")
    ui.check("withdrawing says what it means", "Withdrawn: it leaves the catalogue" in ui.text("dd-detail"))
    hrefs = [a.get_attribute("href") or "" for a in ui.page.locator("#dd-list a").all()]
    ui.check("it has left the list", not any(again in h for h in hrefs), str(hrefs))
    # the filters stand above the list: after Withdraw the page is scrolled down to the opened
    # deep dive, where the switch sits under the sticky header, so go back up to it as a reader would
    ui.page.evaluate("() => window.scrollTo(0, 0)")
    ui.toggle("dd-withdrawn", True)
    try:  # the list is redrawn by a callback: wait for it to say it holds the withdrawn too
        ui.page.wait_for_selector("#dd-list a[href*='withdrawn=1']", timeout=20_000)
    except Exception:  # noqa: BLE001 — the check below records what the list held
        pass
    ui.settle()
    hrefs = [a.get_attribute("href") or "" for a in ui.page.locator("#dd-list a").all()]
    ui.check("Show withdrawn brings it back", any(again in h for h in hrefs), str(hrefs))
    ui.persona("Reader")
    ui.goto(first.split(ui.base_url, 1)[-1])
    ui.page.wait_for_selector("#dd-rate", timeout=20_000)
    ui.check("a Reader is offered no Withdraw on another's deep dive", not ui.visible("dd-withdraw"))
    ui.check("but may rate it", not ui.disabled("dd-rate"))
    ui.check("the title is the one first written", title in ui.text("dd-detail"))


@pytest.mark.scenario(
    scenario_id="T07",
    group="T",
    title="An element's page lists the deep dives that cite it, and opens one where it is kept",
    feature="Deep dives · the element page",
    expected="PAC-CMS's page carries a Deep dives card naming the deep dive; its link opens it on Ask's Kept tab.",
)
def test_the_element_page(ui, record):
    title = _written(ui)
    ui.goto(f"/element/{SUBJECT}")
    card = ui.page.locator(".mantine-Paper-root", has_text="Analyses kept that cite it").first
    ui.must("the element page has a Deep dives card", card.count() > 0)
    ui.check("it names the deep dive", title in card.inner_text())
    ui.shot("The Deep dives card on the element page", full_page=False)
    card.locator("a", has_text=title).first.click()
    ui.page.wait_for_selector("#dd-rate", timeout=20_000)
    ui.check("its link opens the deep dive on the Kept tab", "tab=kept" in ui.page.url, ui.page.url)
