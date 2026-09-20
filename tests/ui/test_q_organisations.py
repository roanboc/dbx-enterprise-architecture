"""Group Q — Organisations: the partition a metamodel version is tried in before it is applied.

An organisation is a partition of the one store (decision 0014): its elements, relationships,
branches and reviews are its own, it applies exactly one metamodel version, and one of them is
the default — what the application opens. The point of more than one is that a metamodel
change can be tried on a copy of the real content, in the same repository, without a second
environment and without touching what everybody else reads.

This group creates one sandbox, `Q sandbox`, works in it and deletes it again, so the round
ends with the single default organisation it started with. Everything it writes happens
inside that sandbox; the only thing it does to the default organisation is read it, check a
version against it, and — once — move the default flag and move it straight back.
"""

from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.gui

DEFAULT = "default"
DEFAULT_NAME = "Default organisation"
SANDBOX = "Q sandbox"
SANDBOX_ID = "q-sandbox"
PACK = "higher_education"
PUBLISHED = "higher_education@2026-08-11"
PUBLISHED_VERSION = "2026-08-11"
TRIAL = "q-trial"
TRIAL_REF = f"{PACK}@{TRIAL}"
ELEMENT = "PAC-CMS"  # an application the sample model holds; renamed inside the sandbox only
RENAMED = "CMS, as tried in the sandbox"


def _pm(**parts: str) -> str:
    return "[id='" + json.dumps(parts, sort_keys=True, separators=(",", ":")) + "']"


def _action(action: str, org_id: str) -> str:
    return json.dumps(
        {"action": action, "org": org_id, "type": "orgs-action"}, sort_keys=True, separators=(",", ":")
    )


def _switch_button(org_id: str) -> str:
    return json.dumps({"id": org_id, "type": "org-switch"}, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------------- the controls


def _open(ui) -> None:
    ui.goto("/organisations")
    ui.must("the Organisations page rendered its list", ui.visible("orgs-list"))


def _row(ui, name: str) -> str:
    """What the table says of one organisation, lower-cased: the row that carries its name or id.

    The default marker, the "you are here" marker and the version's state are Mantine badges,
    and a badge is drawn in capitals; the page is saying `published`, in the only voice a badge
    has, so a row is read without case rather than with the capitals written into the scenario.
    """
    rows = ui.page.locator("#orgs-list tbody tr")
    for i in range(rows.count()):
        text = rows.nth(i).inner_text()
        if name in text:
            return re.sub(r"\s+", " ", text).strip().lower()
    return ""


def _org_badge(ui) -> str:
    """Which organisation the header says the reader is in."""
    return ui.page.locator("#org-select").first.input_value().strip()


def _pack_badge(ui) -> str:
    """What the header says of the metamodel, lower-cased: it is a badge, drawn in capitals."""
    return ui.text("pack-badge").lower()


def _switch(ui, name: str) -> None:
    """Change organisation in the header, the way a reader does, and wait for the page to follow."""
    ui.select("org-select", name)
    ui.page.wait_for_timeout(400)
    ui.settle()


def _create(ui, name: str, copy_from: str | None, version: str | None = None, description: str = "") -> str:
    ui.fill("orgs-new-name", name)
    if description:
        ui.fill("orgs-new-desc", description)
    if version:
        ui.select("orgs-new-version", version)
    ui.select("orgs-new-copy", copy_from or "Nobody: start empty")
    ui.click("orgs-new-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    return ui.text("orgs-feedback")


def _draft(ui, version: str) -> None:
    """A draft of the shipped version to try in the sandbox, made where drafts are made."""
    ui.goto("/metamodel")
    ui.click('#mm-tabs > [role="tablist"] [role="tab"]:has-text("Versions")')
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.click(
        json.dumps(
            {"action": "draft", "ref": PUBLISHED, "type": "mm-ver-action"},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    ui.page.wait_for_timeout(400)
    ui.settle()


# =========================================================================== the list


@pytest.mark.scenario(
    scenario_id="Q01",
    group="Q",
    title="The page lists every organisation, what it applies and what it holds",
    feature="Organisations · the list",
    expected=(
        "The default organisation is listed as the default and as where the reader is, with the "
        "version it applies, its state, and how many elements, relationships and branches it holds; "
        "the header names the same organisation and the same version."
    ),
)
def test_the_list(ui, record):
    _open(ui)
    body = ui.text("page")
    ui.check(
        "the page says what an organisation is for",
        "where a version is tried on a copy of the content" in body,
        body[:400],
    )
    row = _row(ui, DEFAULT_NAME)
    ui.must("the default organisation is listed", bool(row), ui.text("orgs-list")[:300])
    ui.check("it is marked as the default", "default" in row, row)
    ui.check("and as where the reader is", "you are here" in row, row)
    ui.check("it says which version it applies", PUBLISHED in row, row)
    ui.check("and that the version is published", "published" in row, row)
    ui.check("it counts what the organisation holds", re.search(r"\b47\b", row) is not None, row)
    ui.check("the header names the organisation", _org_badge(ui) == DEFAULT_NAME, _org_badge(ui))
    ui.check(
        "and the version it applies", _pack_badge(ui) == f"{PACK} · {PUBLISHED_VERSION}", _pack_badge(ui)
    )
    ui.check("Switch to is off for the organisation the reader is in", ui.disabled(_switch_button(DEFAULT)))
    ui.check("the default organisation cannot be deleted", ui.disabled(_action("delete", DEFAULT)))
    ui.check("and cannot be made the default again", ui.disabled(_action("default", DEFAULT)))
    ui.shot("The Organisations page: one organisation, the default, applying the shipped version")


@pytest.mark.scenario(
    scenario_id="Q02",
    group="Q",
    title="A sandbox is created as a copy of the default organisation's content",
    feature="Organisations · create",
    expected=(
        "Creating an organisation copied from the default derives an id from the name, reports what "
        "was copied, lists it applying the same version, and says how to work in it."
    ),
)
def test_create_a_sandbox(ui, record):
    _open(ui)
    said = _create(ui, SANDBOX, DEFAULT_NAME, description="Where group Q tries a metamodel version.")
    ui.must("the sandbox was created", f"Organisation {SANDBOX} created" in said, said or "(no feedback)")
    ui.check("it applies the version it was given", PUBLISHED in said, said)
    ui.check("it says what was copied", "47 elements" in said and "99 relationships" in said, said)
    ui.check("and where it was copied from", f"copied from {DEFAULT}" in said, said)
    ui.check("it says how to work in it", "Switch to it with the selector in the header" in said, said)
    row = _row(ui, SANDBOX)
    ui.must("the sandbox is in the list", bool(row), ui.text("orgs-list")[:400])
    ui.check("the row carries the id derived from the name", SANDBOX_ID in row, row)
    ui.check("the row says what it holds", "47" in row and "99" in row, row)
    ui.check(
        "the row says what it was copied from and what it is for",
        "copied from default" in row and "group Q tries" in row,
        row,
    )
    ui.check("it is not the default", not ui.disabled(_action("default", SANDBOX_ID)), row)
    ui.check(
        "the header still names the organisation the reader is in",
        _org_badge(ui) == DEFAULT_NAME,
        _org_badge(ui),
    )
    ui.shot("A sandbox created as a copy of the default organisation")
    # a name already taken is refused, by the id it would take
    said = _create(ui, SANDBOX, DEFAULT_NAME)
    ui.check("the same name again is refused", "already" in said.lower() or "taken" in said.lower(), said)


@pytest.mark.scenario(
    scenario_id="Q03",
    group="Q",
    title="Switching organisation changes what every page reads, and the content is the organisation's own",
    feature="Organisations · switch · isolation",
    expected=(
        "Switching in the header moves the whole application into the sandbox; an element renamed "
        "there keeps its old name in the default organisation, and the branch selector starts again "
        "at main because a branch belongs to its organisation."
    ),
)
def test_switching_and_isolation(ui, record):
    _open(ui)
    _switch(ui, SANDBOX)
    ui.must("the header says the reader is in the sandbox", _org_badge(ui) == SANDBOX, _org_badge(ui))
    ui.check("the row says so too", "you are here" in _row(ui, SANDBOX), _row(ui, SANDBOX))
    ui.check(
        "the branch selector is back on main",
        ui.branch_badge().strip().lower().startswith("main"),
        ui.branch_badge(),
    )
    ui.goto("/")
    ui.check(
        "the home page is titled with the organisation", SANDBOX in ui.text("page"), ui.text("page")[:200]
    )
    ui.goto(f"/element/{ELEMENT}")
    ui.must("the copied element is there", ui.visible("el-tabs"))
    before = ui.text("#page h1, #page h2")
    ui.click("#el-tabs [role='tab']:has-text('Edit')")
    ui.page.wait_for_timeout(300)
    ui.fill("el-name", RENAMED)
    ui.click("el-save")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.must(
        "the rename was saved in the sandbox",
        "saved" in ui.text("el-save-feedback").lower(),
        ui.text("el-save-feedback"),
    )
    ui.shot("An element renamed inside the sandbox")
    _switch(ui, DEFAULT_NAME)
    ui.goto(f"/element/{ELEMENT}")
    name = ui.text("#page h1, #page h2")
    ui.check("the default organisation never saw the rename", RENAMED not in name, name)
    ui.check(
        "it still holds the name it was imported with",
        name.strip() == before.strip(),
        f"{name!r} against {before!r}",
    )
    ui.shot("The same element in the default organisation, untouched by the sandbox")


# =========================================================================== applying a version


@pytest.mark.scenario(
    scenario_id="Q04",
    group="Q",
    title="Check reads an organisation's content against a version and reports without applying",
    feature="Organisations · check",
    expected=(
        "Check on the version an organisation already applies reports that nothing would be left "
        "invalid, counts what it read, and changes nothing."
    ),
)
def test_check_a_version(ui, record):
    _open(ui)
    ui.select("orgs-apply-org", DEFAULT_NAME)
    ui.select("orgs-apply-version", PUBLISHED)
    ui.click("orgs-apply-check")
    ui.page.wait_for_timeout(400)
    ui.settle()
    said = ui.text("orgs-apply-result")
    ui.must("the check reported", bool(said.strip()), "(nothing in the result)")
    ui.check(
        "it says the version fits", "fits" in said and "nothing would be left invalid" in said, said[:300]
    )
    ui.check(
        "it names the version and the organisation",
        PUBLISHED.split("@")[1] in said and DEFAULT in said,
        said[:300],
    )
    ui.check("nothing was applied", "Applied" not in said, said[:300])
    ui.check("the row is unchanged", PUBLISHED in _row(ui, DEFAULT_NAME), _row(ui, DEFAULT_NAME))
    ui.shot("A version checked against the default organisation: nothing would be left invalid")


@pytest.mark.scenario(
    scenario_id="Q05",
    group="Q",
    title="A draft is applied to the sandbox from the Versions tab, and only there",
    feature="Organisations · apply",
    expected=(
        "The Metamodel's Versions tab hands the version to this page preselected; applying it to the "
        "sandbox reports the check it ran and the sandbox then applies it, while the default "
        "organisation stays on the published version."
    ),
)
def test_apply_a_version(ui, record):
    _draft(ui, TRIAL)
    said = ui.text("mm-feedback")
    ui.must("a draft was made from the published version", "created from" in said, said or "(no feedback)")
    draft_ref = re.search(r"Draft (\S+) created", said)
    ui.must("the draft is named in the message", draft_ref is not None, said)
    ref = draft_ref.group(1)
    ui.goto(f"/organisations?version={ref}")
    ui.must("the page opened", ui.visible("orgs-list"))
    ui.check(
        "the version is preselected from the address",
        ref in ui.page.locator("#orgs-apply-version").first.input_value(),
        ui.page.locator("#orgs-apply-version").first.input_value(),
    )
    ui.select("orgs-apply-org", SANDBOX)
    ui.click("orgs-apply-run")
    ui.page.wait_for_timeout(500)
    ui.settle()
    applied = ui.text("orgs-apply-result")
    feedback = ui.text("orgs-feedback")
    ui.must(
        "the version was applied",
        f"{SANDBOX} now applies {ref}" in feedback,
        feedback or applied or "(nothing said anywhere)",
    )
    ui.check("the report says it was applied", applied.startswith("Applied."), applied[:200])
    ui.check(
        "and what it checked", "elements and" in applied and "relationships checked" in applied, applied[:300]
    )
    ui.check("the sandbox's row follows", ref in _row(ui, SANDBOX), _row(ui, SANDBOX))
    ui.check(
        "the default organisation is left on the published version",
        PUBLISHED in _row(ui, DEFAULT_NAME),
        _row(ui, DEFAULT_NAME),
    )
    ui.shot("A draft applied to the sandbox alone")
    _switch(ui, SANDBOX)
    ui.check(
        "the header names the version the sandbox applies", _pack_badge(ui).endswith("draft"), _pack_badge(ui)
    )
    ui.check("and the pack and version in it", ref.split("@")[1] in _pack_badge(ui), _pack_badge(ui))
    ui.goto("/metamodel")
    ui.check(
        "the Metamodel page opens on the version the sandbox applies",
        f"version {ref.split('@')[1]} (draft)" in ui.text("mm-subtitle"),
        ui.text("mm-subtitle"),
    )
    ui.shot("Inside the sandbox: the header and the Metamodel page on the draft")
    _switch(ui, DEFAULT_NAME)
    ui.check(
        "back in the default organisation the header names the published version",
        _pack_badge(ui) == f"{PACK} · {PUBLISHED_VERSION}",
        _pack_badge(ui),
    )


# =========================================================================== the default, and deleting


@pytest.mark.scenario(
    scenario_id="Q06",
    group="Q",
    title="The default moves and moves back, and deleting asks before it takes everything with it",
    feature="Organisations · make default, delete",
    expected=(
        "Make default moves what the application opens to the sandbox and back; Delete asks first, "
        "naming what goes, and the organisation and its content are gone afterwards."
    ),
)
def test_default_and_delete(ui, record):
    _open(ui)
    ui.click(_action("default", SANDBOX_ID))
    ui.page.wait_for_timeout(400)
    ui.settle()
    said = ui.text("orgs-feedback")
    ui.must("the default moved", f"{SANDBOX} is the default organisation" in said, said or "(no feedback)")
    ui.check("the sandbox's row says it is the default", "default" in _row(ui, SANDBOX), _row(ui, SANDBOX))
    ui.check("and the old default may now be deleted", not ui.disabled(_action("delete", DEFAULT)))
    ui.shot("The default moved to the sandbox")
    ui.click(_action("default", DEFAULT))
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.must(
        "it moved back",
        f"{DEFAULT_NAME} is the default organisation" in ui.text("orgs-feedback"),
        ui.text("orgs-feedback"),
    )
    ui.check("the default organisation cannot be deleted again", ui.disabled(_action("delete", DEFAULT)))
    # the sandbox the round created goes, and everything in it with it
    ui.click(_action("delete", SANDBOX_ID))
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.must("the confirmation opened", ui.visible("orgs-confirm-modal-body"))
    asked = ui.text("orgs-confirm-text")
    ui.check(
        "it names the organisation and what goes with it",
        SANDBOX in asked and "removed for good" in asked,
        asked,
    )
    ui.check("and counts what it holds", "47 elements" in asked, asked)
    ui.shot("Deleting an organisation asks first, and says what goes")
    ui.click("orgs-confirm-yes")
    ui.page.wait_for_timeout(500)
    ui.settle()
    ui.must(
        "the sandbox was deleted",
        f"Organisation {SANDBOX_ID} deleted" in ui.text("orgs-feedback"),
        ui.text("orgs-feedback"),
    )
    ui.check("it is off the list", not _row(ui, SANDBOX), ui.text("orgs-list")[:300])
    ui.check(
        "the header offers the default organisation alone", _org_badge(ui) == DEFAULT_NAME, _org_badge(ui)
    )
    ui.goto("/metamodel")
    ui.click('#mm-tabs > [role="tablist"] [role="tab"]:has-text("Versions")')
    ui.page.wait_for_timeout(300)
    ui.settle()
    ui.check(
        "the version the sandbox applied is applied by nobody now",
        "nobody" in ui.text("mm-versions-table"),
        ui.text("mm-versions-table")[:300],
    )
    ui.shot("The sandbox deleted: the version it was trying is applied by nobody")


@pytest.mark.scenario(
    scenario_id="Q07",
    group="Q",
    title="Organisations are an Admin's to manage, and every other role may only read and check",
    feature="Organisations · role gating",
    expected=(
        "An Architect may read the list and check a version against an organisation, but Create, "
        "Apply, Make default and Delete are disabled and say why."
    ),
    role="architect",
)
def test_role_gating(ui, record):
    _open(ui)
    ui.persona("Architect")
    ui.page.wait_for_timeout(300)
    ui.goto("/organisations")
    ui.check("an Architect reads the list", ui.visible("orgs-list"))
    ui.check("Create is disabled", ui.disabled("orgs-new-save"))
    why = ui.text("orgs-new-why")
    ui.check(
        "and says why, naming the role",
        "Architect" in why and "only an admin" in why,
        why or "(nothing beside it)",
    )
    ui.check("Apply is disabled", ui.disabled("orgs-apply-run"))
    ui.check("Make default is disabled", ui.disabled(_action("default", DEFAULT)))
    ui.check("Check is still offered, because checking is reading", not ui.disabled("orgs-apply-check"))
    ui.click("orgs-apply-check")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("and it answers", bool(ui.text("orgs-apply-result").strip()), "(nothing in the result)")
    ui.shot("The Organisations page as an Architect: readable, checkable, not manageable")
    ui.persona("Admin")
    ui.page.wait_for_timeout(300)
