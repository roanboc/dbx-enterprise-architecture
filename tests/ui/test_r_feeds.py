"""Group R — Feeds: a configured source, what it reads, and running it now.

A feed reads a table a source left in the landing schema of the store's own database
(decision 0020) and loads it through the same pipeline an uploaded file goes through. This
group proves the screen around that: a feed is configured, its card says where it writes and
when it is meant to run, pressing Run now loads what is waiting, and the roles split the way
the work does.

Two things here are the screen's own and nothing else can see them. A feed that writes to
`main` skips the review every other change goes through, and the card has to show it rather
than leave it in a field nobody opened. And a schedule shown without its zone is a time in
somebody else's day, so every time on the page carries the zone it means.

Everything this group creates is prefixed `R-` and carries the nonsense word `rqmark` in its
description, so a search finds this group's rows and nothing else. The landing tables it
writes are named `r_*`; the group empties them by loading them.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui

SOURCE = "r-feed-round"
MARKER = "rqmark"
FEED_NAME = "R Reference model"
EL_TABLE = "r_elements"
REL_TABLE = "r_relationships"
LDC = "R-LDC-RESEARCH"
DE = "R-DE-PROJECT"

NOTICE = "it does not fire one"
EMPTY = "No feeds configured."
SCHEDULE = "30 2 * * *"
ZONE = "Australia/Brisbane"


def _open(ui) -> None:
    ui.goto("/feeds")


@pytest.mark.scenario(
    scenario_id="R01",
    group="R",
    title="The Feeds page says which zone it shows times in, and that it does not fire a schedule",
    feature="Feeds · the page",
    expected=(
        "The page opens with a notice naming the zone times are shown in and saying the schedule is "
        "honoured by a trigger outside the application — the page shows it and runs a feed on demand. "
        "With nothing configured it says so rather than showing an empty list."
    ),
)
def test_the_page(ui, record):
    _open(ui)
    ui.check("the page is titled Feeds", ui.text("#page h1") == "Feeds", ui.text("#page h1"))
    ui.check("the notice says the page does not fire the schedule", NOTICE in ui.body())
    ui.check("the notice names the zone times are read in", "Times are shown in" in ui.body())
    ui.check("an empty list says so rather than showing nothing", EMPTY in ui.body(), ui.body()[:200])
    ui.check("New feed is offered to an Admin", not ui.disabled("feed-new"))
    ui.shot("The Feeds page before anything is configured: the notice, and New feed")


@pytest.mark.scenario(
    scenario_id="R02",
    group="R",
    title="A feed is configured from the page, and its card says what it reads and where it writes",
    feature="Feeds · configuring",
    expected=(
        "New feed opens a dialog for the landing tables, the branch, the schedule and its zone. "
        "Saving it closes the dialog and the feed appears as a card naming the tables it reads, "
        "the schedule in the zone it was written in, and that it has never run."
    ),
)
def test_configure(ui, record):
    _open(ui)
    ui.click("#feed-new")
    ui.settle()
    ui.check("the dialog is open", ui.visible("feed-name"))
    ui.shot("The New feed dialog: tables, target, schedule and the zone it is written in")
    ui.fill("#feed-name", FEED_NAME)
    ui.fill("#feed-source", SOURCE)
    ui.fill("#feed-el-table", EL_TABLE)
    ui.fill("#feed-rel-table", REL_TABLE)
    ui.fill("#feed-schedule", SCHEDULE)
    ui.fill("#feed-tz", ZONE)
    ui.click("#feed-save")
    ui.settle()
    body = ui.body()
    ui.check("the feed is listed by name", FEED_NAME in body)
    ui.check("the card names the tables it reads", EL_TABLE in body and REL_TABLE in body, body[:400])
    ui.check("the schedule is read as a time of day in its own zone", "02:30 daily" in body and ZONE in body)
    ui.check("a feed that has never run says so", "Never run" in body)
    # A badge renders its text uppercase, so the card says "→ MAIN" however it was written.
    ui.check("the card says it writes to main", "→ main" in body.lower(), body[:400])
    ui.shot("A configured feed: what it reads, where it writes, and when it is meant to run")


@pytest.mark.scenario(
    scenario_id="R03",
    group="R",
    title="Run now loads what the source left in the landing schema, and reports what it did",
    feature="Feeds · running one",
    expected=(
        "With rows waiting in the landing tables, Run now loads them through the same pipeline a "
        "file goes through and reports the counts. The card then shows when it last ran, in the "
        "zone the page reads in."
    ),
)
def test_run_now(ui, record):
    _open(ui)
    ui.must("the feed is there to run", FEED_NAME in ui.body(), ui.body()[:300])
    ui.click('button:has-text("Run now")')
    ui.settle()
    body = ui.body()
    ui.check("the run reports what it loaded", "elements 2/2 loaded" in body, body[:500])
    ui.check("the relationship was loaded too", "relationships 1/1 loaded" in body, body[:500])
    ui.check("the run found nothing wrong", "0 errors" in body)
    ui.check("the card now says when it last ran", "Last run" in body and ZONE in body)
    ui.shot("After Run now: what the feed loaded, and the card saying when it last ran")


@pytest.mark.scenario(
    scenario_id="R04",
    group="R",
    title="What a feed loaded is in the model, under the identifiers the source used",
    feature="Feeds · what a run leaves behind",
    expected=(
        "The elements a feed loaded are browsable like any other, and the relationship between "
        "them is on the element page. A feed is the same load, from a table rather than a file."
    ),
)
def test_what_it_loaded(ui, record):
    ui.goto(f"/element/{LDC}")
    ui.check("the element the feed loaded is there", "R Research Data" in ui.body())
    ui.check("its description came with it", MARKER in ui.body())
    # The type is shown as a badge, and a badge renders its text uppercase.
    body = ui.body().lower()
    ui.check("it is an element of the type the source gave it", "logical data component" in body)
    ui.check("its provenance names the feed's source system", SOURCE in body)
    ui.check("the relationship the feed loaded is on it", "relationships (1)" in body)
    ui.shot("An element a feed loaded, on the Element page like any other")


@pytest.mark.scenario(
    scenario_id="R05",
    group="R",
    title="Running a feed a second time finds nothing waiting, because the first run emptied it",
    feature="Feeds · the landing tables are emptied by a run",
    expected=(
        "A feed empties its landing tables once it has loaded them, so a second run with nothing "
        "new reports nothing loaded rather than loading the same rows again."
    ),
)
def test_second_run(ui, record):
    _open(ui)
    ui.click('button:has-text("Run now")')
    ui.settle()
    body = ui.body()
    ui.check(
        "the second run loads nothing, the tables having been emptied", "elements 0/0" in body, body[:400]
    )
    ui.shot("A second run with nothing waiting: the landing tables were emptied by the first")


@pytest.mark.scenario(
    scenario_id="R06",
    group="R",
    title="A Reader sees what is configured and can press nothing",
    feature="Feeds · roles",
    expected=(
        "Configuring a feed is an admin's decision and running one is an architect's, so a Reader "
        "sees the feeds and finds Run now, Edit, Delete and New feed all disabled, with the page "
        "saying why rather than leaving them greyed out unexplained."
    ),
    role="reader",
)
def test_reader(ui, record):
    ui.persona("Reader")
    _open(ui)
    body = ui.body()
    ui.check("the reader still sees what is configured", FEED_NAME in body)
    ui.check("New feed is off", ui.disabled("feed-new"))
    ui.check("the page says why configuring is not offered", "may not configure a feed" in body, body[:500])
    disabled = ui.page.locator("#page button[disabled]").count()
    ui.check("the row's buttons are off as well", disabled >= 4, f"{disabled} disabled buttons")
    ui.shot("The Feeds page as a Reader: everything visible, nothing pressable, and the reason said")


@pytest.mark.scenario(
    scenario_id="R07",
    group="R",
    title="An Architect may run a configured feed but not configure one",
    feature="Feeds · roles",
    expected=(
        "Running a feed that is already configured is an import, so an Architect may press Run now; "
        "deciding where content comes from is an admin's, so New feed, Edit and Delete stay off."
    ),
    role="architect",
)
def test_architect(ui, record):
    ui.persona("Architect")
    _open(ui)
    ui.check("New feed is off for an architect", ui.disabled("feed-new"))
    ui.check("the page says configuring is an admin's decision", "may not configure a feed" in ui.body())
    run = ui.page.locator('button:has-text("Run now")').first
    ui.check("Run now is offered", not run.is_disabled())
    ui.shot("The Feeds page as an Architect: Run now offered, configuring not")


@pytest.mark.scenario(
    scenario_id="R08",
    group="R",
    title="The page reads at 480 px",
    feature="Feeds · narrow",
    expected="Every card, its badges and its buttons stay readable and reachable on a phone.",
)
def test_narrow(ui, record):
    ui.narrow()
    _open(ui)
    ui.check("the feed is still named", FEED_NAME in ui.body())
    ui.check("the notice is still there", NOTICE in ui.body())
    ui.shot("The Feeds page at 480 px", full_page=True)
    ui.wide()


@pytest.mark.scenario(
    scenario_id="R09",
    group="R",
    title="A feed naming a landing table that is not there says so rather than failing silently",
    feature="Feeds · a table that is not there",
    expected=(
        "A feed configured against a table the landing schema does not hold reports it as a "
        "warning naming the table, and loads nothing."
    ),
)
def test_missing_table(ui, record):
    _open(ui)
    ui.click("#feed-new")
    ui.settle()
    ui.fill("#feed-name", "R Absent")
    ui.fill("#feed-source", "r-absent")
    ui.fill("#feed-el-table", "r_never_created")
    ui.click("#feed-save")
    ui.settle()
    ui.must("the second feed is listed", "R Absent" in ui.body(), ui.body()[:400])
    ui.page.locator('button:has-text("Run now")').last.click()
    ui.settle()
    body = ui.body()
    ui.check("the run names the table it could not find", "r_never_created" in body, body[:600])
    ui.check("it is a warning, not a crash", "warning" in body.lower() or "0 errors" in body)
    ui.shot("A feed whose landing table is not there: named, and nothing loaded")
