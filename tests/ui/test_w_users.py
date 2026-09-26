"""Group W — Users and roles: which workspace groups hold which role, decided by an admin (initiative 28).

The page is under Manage. An admin picks a workspace group as its name is typed, gives it
Reviewer, Architect or Admin with a line of why, reads every grant — the deployment's own first,
never changed here — removes one, checks which role a person gets and which group gives it, and
reads the recent changes. Everyone else reads their own role, where it comes from and whom to ask.

The round has no workspace: the picker offers the sample groups and the debug personas'
memberships, and says so beneath itself. Whatever the round grants it also removes, so no
scenario after this group reads a grant it did not make. On the Postgres engine
(`EA_ROUND_ENGINE=postgres`) a debug persona may not write grants into what stands for the
platform's store: the page says so and turns Grant and Remove off, and W02 reads that instead.

The rules themselves — the highest role wins, an admin's own Admin and the last admin grant are
kept, the all-users group is never Admin — are proved in `tests/test_access.py`; this group
proves the controls reach them and say what happened.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui

PAGE = "/users"
HEADING = "Users and roles"
GROUP = "solution-architects"  # a sample group: the architect persona is in it
NOTE = "They draft the solutions (W02)"
SAMPLE_NOTE = "Locally these are sample groups"
# The role is a group of radios whose `usr-role` id stays with Dash, so they are found by their role.
CONTROLS = ["usr-group", "usr-note", "usr-grant", "usr-check-email", "usr-check"]
SECTIONS = ["Grant a role", "Grants", "Check a person", "Recent changes"]


def _open(ui) -> None:
    ui.goto(PAGE)
    heading = ui.page.locator("#page h1").first
    ui.must(
        "the Users and roles page rendered",
        heading.count() > 0 and heading.inner_text().strip() == HEADING,
        heading.inner_text() if heading.count() else ui.body()[:200],
    )


def _pick(ui, typed: str, option: str) -> list[str]:
    """Type into the group picker and pick an option; what it offered."""
    ui.fill("usr-group", typed)
    offered = [t.strip() for t in ui.page.locator("[role='option']:visible").all_inner_texts()]
    ui.page.locator("[role='option']:visible", has_text=option).first.click()
    ui.settle()
    return offered


def _role(ui, label: str) -> None:
    ui.page.get_by_role("radio", name=label, exact=True).check()
    ui.settle()


def _grant(ui, typed: str, option: str, role: str, why: str = "") -> str:
    _pick(ui, typed, option)
    _role(ui, role)
    if why:
        ui.fill("usr-note", why)
    ui.click("usr-grant")
    return ui.text("usr-feedback")


@pytest.mark.scenario(
    scenario_id="W01",
    group="W",
    title="An admin opens Users and roles: the form, every grant, the check and the recent changes",
    feature="Users and roles · the page",
    expected=(
        "The page is reached from Manage in the navigation. An admin is given a group picker that says "
        "locally it offers sample groups, the three roles a grant gives each with what it lets a person "
        "do, a line of why and Grant; then the grants, a person to check, the recent changes, and a link "
        "to the Metamodel page's Reviewers tab for who reviews which type. At 480 px nothing scrolls sideways."
    ),
)
def test_the_page_as_an_admin(ui, record):
    ui.goto("/")
    ui.must("the navigation offers Users and roles", ui.visible("nav-users"))
    ui.click("nav-users")
    ui.check("the link opens /users", ui.page.url.endswith(PAGE), ui.page.url)
    _open(ui)
    missing = [c for c in CONTROLS if not ui.visible(c)]
    ui.check("the form and the check are offered", not missing, f"not shown: {missing}")
    body = ui.body()
    absent = [s for s in SECTIONS if s not in body]
    ui.check("the four sections are there", not absent, f"missing: {absent}")
    radios = ui.page.locator("#page").get_by_role("radio")
    ui.check("three roles are offered to grant", radios.count() == 3, f"{radios.count()} radios")
    ui.check(
        "each role says what it lets a person do",
        "approves or sends back branches" in body and "drafts on branches" in body and "Everything" in body,
        body[:300],
    )
    ui.check(
        "the picker says that locally it offers sample groups",
        SAMPLE_NOTE in ui.text("usr-search-note"),
        ui.text("usr-search-note") or "(nothing beneath the picker)",
    )
    link = ui.page.locator("#page a[href='/metamodel']")
    ui.check("who reviews which type is linked on the Metamodel page", link.count() > 0, body[-300:])
    ui.check("the recent changes are shown", ui.visible("usr-history"))
    ui.shot("Users and roles as an admin: the form, the grants, the check and the recent changes")
    ui.narrow()
    widths = ui.page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    ui.check("at 480 px nothing scrolls sideways", widths[0] <= widths[1], str(widths))
    ui.shot("Users and roles at 480 px")
    ui.wide()


@pytest.mark.scenario(
    scenario_id="W02",
    group="W",
    title="An admin grants a group Architect, checks a person it reaches, and removes it",
    feature="Users and roles · grant, check and remove",
    expected=(
        "Typing part of a group's name offers the groups that hold it; the admin picks one, gives it "
        "Architect with a line of why, and the page says so. The grant is listed with its why and who "
        "granted it, the recent changes say who granted what, and checking the architect persona says "
        "Architect, from that group. Remove, named for the grant it takes away, removes it and says so, "
        "and the grants no longer list it. Where the page may not write grants it says why instead."
    ),
)
def test_grant_check_and_remove(ui, record):
    _open(ui)
    if ui.disabled("usr-grant"):
        ui.check(
            "a local persona on the platform's store is told why Grant is off",
            "debug persona" in ui.body(),
            ui.body()[:300],
        )
        ui.shot("Users and roles where a local persona may not write grants")
        return
    offered = _pick(ui, "arch", GROUP)
    ui.check("typing part of a name offers the groups that hold it", GROUP in offered, str(offered))
    _role(ui, "Architect")
    ui.fill("usr-note", NOTE)
    ui.click("usr-grant")
    said = ui.text("usr-feedback")
    ui.must("the grant was made, and the page says so", f"Architect granted to {GROUP}" in said, said)
    grants = ui.text("usr-grants")
    ui.check("the grant is listed with its why", GROUP in grants and NOTE in grants, grants[:400])
    ui.check("and who granted it", "granted by admin@example.edu" in grants, grants[:400])
    ui.check(
        "the recent changes say who granted what",
        f"granted Architect to {GROUP}" in ui.text("usr-history"),
        ui.text("usr-history")[:300],
    )
    ui.fill("usr-check-email", "architect@example.edu")
    ui.click("usr-check")
    result = ui.text("usr-check-result")
    ui.check(
        "checking a person says the role they get and which group gives it",
        f"Architect — from the group {GROUP}" in result,
        result,
    )
    ui.shot("A group granted Architect, and a person checked")
    remove = ui.page.get_by_role("button", name=f"Remove the Architect grant of {GROUP}")
    ui.must("Remove is named for the grant it takes away", remove.count() == 1, ui.text("usr-grants")[:300])
    remove.first.click()
    ui.settle()
    said = ui.text("usr-feedback")
    ui.check(
        "the grant was removed, and the page says so", f"Removed the Architect grant of {GROUP}" in said, said
    )
    ui.check(
        "and the grants no longer list it", GROUP not in ui.text("usr-grants"), ui.text("usr-grants")[:300]
    )


@pytest.mark.scenario(
    scenario_id="W03",
    group="W",
    title="What an admin may not grant is refused in a sentence, and nothing is kept",
    feature="Users and roles · refusals",
    expected=(
        "Grant with no group picked asks for one; a group picked with no role asks for the role; Admin "
        "for the workspace's group of every person is refused, saying it would make every person an "
        "admin; and none of it is listed afterwards."
    ),
)
def test_what_an_admin_may_not_grant(ui, record):
    _open(ui)
    if ui.disabled("usr-grant"):
        ui.check("where grants cannot be written, Grant is off", True, "the Postgres round")
        return
    ui.click("usr-grant")
    said = ui.text("usr-feedback")
    ui.check("with no group picked it asks for one", "Pick the workspace group" in said, said)
    _pick(ui, "data", "data-team")
    ui.click("usr-grant")
    said = ui.text("usr-feedback")
    ui.check("with no role picked it asks for the role", "Pick the role" in said, said)
    said = _grant(ui, "users", "users", "Admin")
    ui.check(
        "Admin is never granted to the group of every person",
        "every person in the workspace an admin" in said,
        said,
    )
    grants = ui.text("usr-grants")
    ui.check(
        "and none of it is listed",
        "data-team" not in grants and "users" not in grants.lower().split(),
        grants[:300],
    )
    ui.shot("A refusal: Admin for every person in the workspace")


@pytest.mark.scenario(
    scenario_id="W04",
    group="W",
    title="A Reader opens Users and roles: their own role, where it comes from and whom to ask — and nothing else",
    feature="Users and roles · a person's own role",
    expected=(
        "As a Reader the page shows their role and what it lets them do, says that locally the role is "
        "the debug persona and what their groups would give on the platform, and whom to ask for another; "
        "it offers no form, no grants, no check and no recent changes, and says that is an admin's."
    ),
    role="reader",
)
def test_the_page_as_a_reader(ui, record):
    ui.goto("/")
    ui.persona("Reader")
    ui.must("the persona is Reader", "reader" in ui.role_badge().lower(), ui.role_badge())
    _open(ui)
    mine = ui.text("usr-mine")
    ui.check("their own role is shown", "Your role" in mine and "reader" in mine.lower(), mine[:300])
    ui.check("with what it lets them do", "Changes nothing in the model" in mine, mine[:300])
    ui.check("that locally the persona is the role", "debug persona" in mine, mine[:300])
    ui.check("and whom to ask for another", "For another role, ask" in mine, mine[:300])
    shown = [c for c in ("usr-group", "usr-grant", "usr-grants", "usr-check", "usr-history") if ui.visible(c)]
    ui.check("no form, grants, check or recent changes", not shown, f"shown: {shown}")
    ui.check("and it says that is an admin's", "may not see or change who holds which role" in ui.body())
    ui.shot("Users and roles as a Reader: their own role, and whom to ask")
