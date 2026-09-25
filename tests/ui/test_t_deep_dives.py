"""Group T — Deep dives: a brief settled on Ask, a deep dive written and kept, the catalogue.

Initiative 25 adds a second way to ask. The reader chooses a deep dive beside the quick answer,
says what they need to know, and the assistant settles a brief with them — what it is about,
which kind of analysis, how far it reaches, which layers, what it is for — each question with
its choices, the brief read back as one sentence. Written, the deep dive is kept in the
catalogue under the reader's name and hands out a pack: a PDF and a draw.io file per diagram.

What the group proves is the part only a browser sees. The questions are controls wired to a
store; an answer has to reach the sentence; Write has to stay off until the brief can be
written, and say why; the pack has to arrive as a ZIP whose PDF is a PDF and whose draw.io
files parse, numbered from the context down to the detail. The catalogue has to narrow, open,
take a rating, run a deep dive again, withdraw one, and hand the pack out again; and the
element's own page has to list the deep dives that cite it. The rules underneath — the brief,
the analyses, the maturity, the findings, the layout — are proven in `tests/test_deep_dive_*.py`.

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
    """Start, write and return the title of the deep dive kept."""
    _start(ui, question)
    ui.click("ask-dd-write")
    ui.page.wait_for_selector("#ask-dd-pack", timeout=90_000)
    ui.settle()
    return ui.page.locator("#ask-dd-result h2").first.inner_text().strip()


def _open_catalogue_on(ui, title: str) -> None:
    ui.goto("/deep-dives")
    link = ui.page.locator("#dd-list a", has_text=title).first
    ui.must("the catalogue lists the deep dive", link.count() > 0, ui.text("dd-list")[:300])
    link.click()
    ui.page.wait_for_selector("#dd-rate", timeout=20_000)
    ui.settle()


# ---------------------------------------------------------------------------------- Ask


@pytest.mark.scenario(
    scenario_id="T01",
    group="T",
    title="A deep dive is a choice beside the quick answer",
    feature="Deep dives · the mode",
    expected=(
        "Ask opens on the quick answer with a switch to Deep dive; switching shows the deep "
        "panel and hides the question box; /ask?mode=deep opens on the deep panel."
    ),
)
def test_the_mode_switch(ui, record):
    ui.goto("/ask")
    ui.must("the quick answer is shown first", ui.visible("ask-input"))
    ui.check("the deep panel waits hidden", not ui.visible("ask-dd-input"))
    ui.segmented("ask-mode", "Deep dive")
    ui.check("switching shows the deep panel", ui.visible("ask-dd-input"))
    ui.check("and hides the quick question box", not ui.visible("ask-input"))
    ui.goto("/ask?mode=deep")
    ui.check("the address opens the deep mode", ui.visible("ask-dd-input") and not ui.visible("ask-input"))
    ui.shot("Ask, deep mode")


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
    title="The deep dive is written, kept, and its pack downloads as a PDF with its draw.io diagrams",
    feature="Deep dives · the pack",
    expected=(
        "Write keeps the deep dive and shows its summary, confidence and first findings; "
        "Download the pack (ask-dd-pack) hands out one ZIP holding deep-dive.pdf and draw.io "
        "files numbered 01 on, level 1 first, each parsing with an identifier on every shape."
    ),
)
def test_written_and_downloaded(ui, record):
    title = _written(ui)
    ui.check("it is titled for its kind and subject", title.startswith(f"Impact: {SUBJECT_NAME}"), title)
    result = ui.text("ask-dd-result")
    ui.check("it says it was kept", "Kept in the catalogue" in result)
    ui.check("it says how far it can be trusted", "confidence:" in result.lower())
    ui.shot("The deep dive, written")
    path = ui.download("ask-dd-pack", ".zip")
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


# ---------------------------------------------------------------------------- catalogue


@pytest.mark.scenario(
    scenario_id="T05",
    group="T",
    title="The catalogue narrows, opens a deep dive, takes a rating and hands the pack out again",
    feature="Deep dives · the catalogue",
    expected=(
        "The Deep dives page lists the deep dive; narrowing by kind to Landscape leaves it out; "
        "opened, four stars with a line of why are recorded as the reader's; Download the pack "
        "(dd-pack) hands out the same ZIP."
    ),
)
def test_the_catalogue(ui, record):
    title = _written(ui)
    ui.goto("/deep-dives")
    ui.must("the catalogue lists it", title in ui.text("dd-list"))
    ui.select("dd-kind", "Landscape", exact=True)
    ui.check("narrowed to landscapes, the impact is left out", title not in ui.text("dd-list"))
    ui.goto(f"/deep-dives?element={SUBJECT}")
    ui.check("narrowed to what cites PAC-CMS, it is there", title in ui.text("dd-list"))
    _open_catalogue_on(ui, title)
    ui.check("opened, it reads its brief", "An impact analysis" in ui.text("dd-detail"))
    ui.page.locator(".mantine-Rating-input[value='4']").first.locator(
        "xpath=following-sibling::label"
    ).click()
    ui.fill("dd-why", "Clear enough to take to the board")
    ui.click("dd-rate")
    detail = ui.text("dd-detail")
    ui.check("the rating is recorded", "Rated 4 of 5" in detail, detail[-300:])
    ui.check("and listed with its why", "Clear enough to take to the board" in detail)
    ui.shot("A deep dive opened in the catalogue, rated")
    path = ui.download("dd-pack", ".zip")
    ui.check(
        "the pack downloads again",
        any(n.endswith("/deep-dive.pdf") for n in zipfile.ZipFile(path).namelist()),
    )


@pytest.mark.scenario(
    scenario_id="T06",
    group="T",
    title="A deep dive is run again, withdrawn by its author, and cannot be withdrawn by another reader",
    feature="Deep dives · run again and withdraw",
    expected=(
        "Run again opens a new deep dive; withdrawing it takes it out of the list and Show "
        "withdrawn brings it back marked; a Reader opening the Admin's deep dive is offered no "
        "Withdraw."
    ),
)
def test_again_and_withdraw(ui, record):
    title = _written(ui)
    _open_catalogue_on(ui, title)
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
    ui.toggle("dd-withdrawn", True)
    ui.page.wait_for_timeout(600)
    ui.settle()
    hrefs = [a.get_attribute("href") or "" for a in ui.page.locator("#dd-list a").all()]
    ui.check("Show withdrawn brings it back", any(again in h for h in hrefs), str(hrefs))
    ui.persona("Reader")
    ui.goto(first.split(ui.base_url, 1)[-1])
    ui.page.wait_for_selector("#dd-rate", timeout=20_000)
    ui.check("a Reader is offered no Withdraw on another's deep dive", not ui.visible("dd-withdraw"))
    ui.check("but may rate it", not ui.disabled("dd-rate"))


@pytest.mark.scenario(
    scenario_id="T07",
    group="T",
    title="An element's page lists the deep dives that cite it, and opens one",
    feature="Deep dives · the element page",
    expected=(
        "PAC-CMS's page carries a Deep dives card naming the deep dive; its link opens it in the catalogue."
    ),
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
    ui.check("its link opens the deep dive in the catalogue", "/deep-dives?open=" in ui.page.url, ui.page.url)
