"""Group L — Roles and permissions: four personas against every gated control.

The role is a property of the request (`services/roles.py`): one table, `ACTIONS`, says
what each role may do, `allowed()` is the only place that knows it, and the pages hide or
disable what the role may not use. This group reads that table back off the screen.

The four debug personas of mock authentication are Ada (Admin), Arjun (Architect),
Rae (Reviewer) and Ren (Reader), switched in the header. Two rules decide almost every
control on a page:

| Control | Needs |
| ------- | ----- |
| Browse's New element and Bulk edit, the Element page's Save, Import's Load | `edit_content` **and** (a branch, or `edit_main` — Admin only) |
| Propose's Apply, the header's and the page's New branch | `propose` / `create_branch` — Architect and Admin |
| Branches' Request review, Abandon, Merge | the action **and** who wrote the branch, and where the branch stands |
| The Metamodel's Save changes and Save reviewers | `edit_metamodel` / `assign_reviewers` — Admin only |
| Read, Ask, Download | every persona, always |

The scenarios run in file order and one branch, `L roles`, is the fixture the writing
ones share: L07 creates it as the Architect, L11 puts a row on it, L17 sends it to
review, and from there the review controls change hands. Nothing here asserts a total
another group could have moved, and the only element it writes to is a Data Entity no
other group touches — and then only on the branch, never on main.
"""

from __future__ import annotations

import json

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

# ---------------------------------------------------------------------- the personas
ADMIN = "Admin"
ARCHITECT = "Architect"
REVIEWER = "Reviewer"
READER = "Reader"
PERSONAS = [ADMIN, ARCHITECT, REVIEWER, READER]
DISPLAY = {
    ADMIN: "Ada (Admin)",
    ARCHITECT: "Arjun (Architect)",
    REVIEWER: "Rae (Reviewer)",
    READER: "Ren (Reader)",
}

# ---------------------------------------------------------------------- the fixture branch
BRANCH_NAME = "L roles"
BRANCH_ID = "l-roles"
ELEMENT = "DE-CMS-UNIT-OUTLINE"  # a Data Entity; no other group writes it
BRANCH_ELEMENT_NAME = "CMS_Unit_Outline (L branch draft)"

# ---------------------------------------------------------------------- what a page says
READER_BANNER = "You are a Reader on this page"
MAIN_BANNER = "switch to a branch in the header"
QUESTION = "Who owns the Course Catalogue and which applications contribute to it?"
DOCUMENT = "#ask-answer .ea-document"


def _f(finding_id: str, where: str, severity: str, summary: str, detail: str) -> Finding:
    return Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)


# --------------------------------------------------------------------------- the controls


def _a(persona: str) -> str:
    """'an Admin', 'a Reader' — the article the sentence needs."""
    return f"{'an' if persona[0] in 'AEIOU' else 'a'} {persona}"


def _as(ui, persona: str) -> None:
    """Become one of the four debug personas and wait for the page to re-render under it."""
    ui.persona(persona)


def _present(ui, selector: str) -> bool:
    return ui.visible(selector)


def _blocked(ui, selector: str) -> bool:
    """The control is on the page, and refuses to be used."""
    return ui.visible(selector) and ui.disabled(selector)


def _usable(ui, selector: str) -> bool:
    return ui.visible(selector) and not ui.disabled(selector)


def _badge_colour(ui) -> str:
    """The colour the header paints the role badge, as the browser resolves it."""
    return (
        ui.page.evaluate(
            "() => { const b = document.querySelector('#role-badge .mantine-Badge-root')"
            " || document.querySelector('#role-badge'); return b ? getComputedStyle(b).backgroundColor : ''; }"
        )
        or ""
    )


def _tooltip(ui, selector: str) -> str:
    """Hover a control and read the tooltip it raises, or '' when it raises none."""
    loc = ui.page.locator(selector).first
    try:
        loc.hover(force=True, timeout=3_000)
    except Exception:  # noqa: BLE001 — a control that cannot be hovered simply has no tooltip
        return ""
    ui.page.wait_for_timeout(400)
    tip = ui.page.locator(".mantine-Tooltip-tooltip")
    for i in range(tip.count()):
        if tip.nth(i).is_visible():
            return tip.nth(i).inner_text().strip()
    return ""


def _branch_labels(ui) -> list[str]:
    """What the header's branch selector offers, leaving it closed again."""
    ui.click("branch-select")
    labels = [t.strip() for t in ui.page.locator("[role='option']").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    return labels


def _ensure_branch(ui) -> None:
    """The group's own branch, created once by the Architect who then owns it."""
    if any(BRANCH_NAME in label for label in _branch_labels(ui)):
        return
    _as(ui, ARCHITECT)
    ui.click("branch-new-open")
    ui.must("the New branch modal opened", ui.visible("branch-new-modal-body"))
    ui.fill("branch-new-name", BRANCH_NAME)
    ui.fill("branch-new-desc", "The branch group L's role scenarios write on.")
    ui.click("branch-new-save")
    ui.settle()


def _on_branch(ui) -> None:
    """On the group's own branch, whichever branch the reset fixture left behind."""
    _ensure_branch(ui)
    ui.branch(BRANCH_NAME)


def _el_tab(ui, label: str) -> None:
    ui.click(f"#el-tabs [role='tab']:has-text({json.dumps(label)})")
    ui.page.wait_for_timeout(250)
    ui.settle()


def _mm_tab(ui, label: str) -> None:
    ui.click(f'[role="tab"]:has-text("{label}")')
    ui.page.wait_for_timeout(250)
    ui.settle()


def _branches(ui, branch_id: str = BRANCH_ID) -> None:
    ui.goto(f"/branches?branch={branch_id}")


def _detail(ui) -> str:
    return ui.text("br-detail")


def _page(ui) -> str:
    """What the routed page says, without the header and the navigation around it."""
    return ui.text("page")


def _alerts(ui) -> str:
    """Every banner the page is showing, as one line."""
    loc = ui.page.locator("#page .mantine-Alert-root")
    return " · ".join(t.strip().replace("\n", " ") for t in loc.all_inner_texts()) if loc.count() else ""


def _ask(ui, question: str = QUESTION) -> None:
    box = ui.page.locator("textarea#ask-input")
    box = box.first if box.count() else ui.page.locator("#ask-input textarea").first
    box.click()
    box.fill(question)
    ui.settle()
    ui.click("ask-button")
    ui.page.wait_for_selector(DOCUMENT, timeout=45_000)
    ui.settle()


# =========================================================================== the header


@pytest.mark.scenario(
    scenario_id="L01",
    group="L",
    title="The header names who you are and offers the four personas",
    feature="Shell · role badge and persona switcher",
    expected=(
        "As Admin the header shows Ada (Admin), the switcher offers Admin, Architect, Reviewer and "
        "Reader, and every control an Admin may use — New branch in the header, New element and Bulk "
        "edit on Browse, straight onto main — is available."
    ),
)
def test_admin_header(ui, record):
    ui.goto("/")
    badge = ui.role_badge()
    ui.check("the role badge names the persona and its role", "admin" in badge.lower(), badge)
    ui.check("the badge names the person behind the role", DISPLAY[ADMIN].lower() in badge.lower(), badge)
    ui.check(
        "the header says which branch is being read", ui.branch_badge().lower() == "main", ui.branch_badge()
    )
    ui.click("persona-select")
    offered = [t.strip() for t in ui.page.locator("[role='option']").all_inner_texts()]
    ui.page.keyboard.press("Escape")
    ui.settle()
    for persona in PERSONAS:
        ui.check(f"the switcher offers {persona}", any(o.startswith(persona) for o in offered), str(offered))
    ui.check(
        "the assistant is not a persona a person can wear",
        not any(o.startswith("Agent") for o in offered),
        str(offered),
    )
    ui.check("an admin may create a branch from the header", _usable(ui, "branch-new-open"))
    ui.goto("/browse")
    ui.check("an admin may add an element on main", _usable(ui, "new-open"))
    ui.check("an admin may bulk-edit on main", _usable(ui, "bulk-open"))
    ui.check("nothing warns an admin off main", READER_BANNER not in _page(ui), _alerts(ui) or "no banner")
    ui.shot("The header as an Admin: the badge, the persona switcher and every write control open")


@pytest.mark.scenario(
    scenario_id="L02",
    group="L",
    title="The role badge and its colour change with the persona",
    feature="Shell · role badge",
    expected=(
        "Each of the four personas paints the badge with its own name and its own colour, so who you "
        "are reading as is visible without opening the switcher."
    ),
)
def test_role_badge_per_persona(ui, record):
    ui.goto("/")
    colours: dict[str, str] = {}
    for persona in PERSONAS:
        _as(ui, persona)
        badge = ui.role_badge()
        ui.check(f"the badge names {DISPLAY[persona]}", DISPLAY[persona].lower() in badge.lower(), badge)
        colours[persona] = _badge_colour(ui)
        ui.shot(f"The header reading as {DISPLAY[persona]}")
    ui.check(
        "each role has a colour of its own",
        len(set(colours.values())) == len(PERSONAS),
        json.dumps(colours),
    )
    ui.check("every badge is painted at all", all(colours.values()), json.dumps(colours))


@pytest.mark.scenario(
    scenario_id="L03",
    group="L",
    title="New branch is offered to the roles that may create one and refused to the rest",
    feature="Shell · New branch",
    expected=(
        "The header's New branch button is available to an Admin and an Architect, disabled for a "
        "Reviewer and a Reader, and on a freshly loaded page its tooltip says why it is disabled."
    ),
)
def test_new_branch_per_persona(ui, record, finding):
    ui.goto("/")  # the header is built by the page load, so it is built here as an Admin
    for persona in (ADMIN, ARCHITECT):
        _as(ui, persona)
        ui.check(f"{_a(persona)} may create a branch", _usable(ui, "branch-new-open"))
    for persona in (REVIEWER, READER):
        _as(ui, persona)
        ui.check(f"{_a(persona)} may not create a branch", _blocked(ui, "branch-new-open"))
    # Read the reason now, on the header this session has been switching personas in: the
    # button is disabled, so whatever the tooltip says is what a Reader is actually told.
    live = _tooltip(ui, "#branch-new-open")
    ui.shot("New branch, disabled for a Reader after switching persona in place")
    # And read it again on a page loaded as the Reader, where the shell is built for them.
    ui.goto("/")
    ui.check("the button is still refused after a reload", _blocked(ui, "branch-new-open"))
    reloaded = _tooltip(ui, "#branch-new-open")
    ui.check(
        "the refusal says why, in the role's own terms",
        "may not create branches" in reloaded,
        reloaded or "no tooltip appeared",
    )
    ui.check(
        "the disabled button says something either way it was reached",
        bool(live) and bool(reloaded),
        f"switched in place: {live!r}; after a reload: {reloaded!r}",
    )
    ui.check(
        "and says the same thing whether the persona was switched in place or loaded",
        live == reloaded,
        f"switched in place: {live!r}; after a reload: {reloaded!r}",
    )
    ui.shot("New branch is disabled for a Reader, with the reason it gives")
    if reloaded and live != reloaded:
        finding.append(
            _f(
                "L-0",
                "src/ea/ui/layout.py — the New branch tooltip in the header",
                "usability",
                "The New branch tooltip goes stale when the persona changes without a page load",
                "`switch_persona` in src/ea/ui/app.py updates only `BRANCH_NEW_OPEN.disabled`; the "
                "tooltip label is fixed when `layout.shell` builds the header, and nothing rebuilds "
                f"it. Switching to a Reader in place leaves the disabled button saying {live!r}, "
                f"while the same button on a page loaded as a Reader says {reloaded!r} — the only "
                "explanation of a dead control contradicts itself. Output the tooltip's label from "
                "the persona callback beside the disabled flag.",
            )
        )
    ui.goto("/branches")
    ui.check("a Reader may not create a branch from the page either", _blocked(ui, "branch-new-open-page"))
    ui.shot("The Branches page as a Reader, whose New branch button is refused there too")


# =========================================================================== browse


@pytest.mark.scenario(
    scenario_id="L04",
    group="L",
    title="A Reader is told Browse changes nothing, and its write controls are refused",
    feature="Browse · role gating",
    expected=(
        "Browse tells a Reader that nothing on the page changes the model, and both New element and "
        "Bulk edit are disabled while search, filters and the grid keep working."
    ),
    role="reader",
)
def test_browse_as_reader(ui, record):
    _as(ui, READER)
    ui.goto("/browse")
    ui.check("a Reader may not add an element", _blocked(ui, "new-open"))
    ui.check("a Reader may not bulk-edit", _blocked(ui, "bulk-open"))
    ui.check("the page says the Reader changes nothing", READER_BANNER in _page(ui), _alerts(ui))
    ui.check("the grid still lists elements", ui.grid_row_count("browse-grid") > 0)
    ui.fill("browse-text", "course")
    ui.check("a Reader may still search", ui.grid_row_count("browse-grid") > 0, ui.text("browse-count"))
    ui.shot("Browse as a Reader: the banner, and both write buttons refused")


@pytest.mark.scenario(
    scenario_id="L05",
    group="L",
    title="A Reviewer may read Browse but not write on it",
    feature="Browse · role gating",
    expected=(
        "A Reviewer approves branches but drafts nothing, so New element and Bulk edit are disabled "
        "and the page states the refusal."
    ),
    role="reviewer",
)
def test_browse_as_reviewer(ui, record, finding):
    _as(ui, REVIEWER)
    ui.goto("/browse")
    ui.check("a Reviewer may not add an element", _blocked(ui, "new-open"))
    ui.check("a Reviewer may not bulk-edit", _blocked(ui, "bulk-open"))
    page = _page(ui)
    ui.check(
        "the page states the refusal, in the reviewer's own name",
        "You are a Reviewer on this page" in page or MAIN_BANNER in page,
        _alerts(ui),
    )
    ui.check("the grid still lists elements", ui.grid_row_count("browse-grid") > 0)
    if READER_BANNER in page:
        finding.append(
            _f(
                "L-1",
                "src/ea/ui/pages/browse.py — the banner above the filters",
                "consistency",
                "Browse tells a Reviewer 'You are a Reader on this page'",
                "The banner is chosen from `not ctx.can('edit_content')`, which is true for a Reviewer "
                "as well as a Reader, so a Reviewer is addressed by another role's name. Everywhere "
                "else — the header badge, the Element page's 'A Reviewer may not edit.' — the "
                "application calls the Reviewer a Reviewer. Reword it from `ctx.role_label()`.",
            )
        )
    ui.shot("Browse as a Reviewer: both write buttons refused, and what the banner calls them")


@pytest.mark.scenario(
    scenario_id="L06",
    group="L",
    title="An Architect on main is told to switch to a branch",
    feature="Browse · role and branch",
    expected=(
        "An Architect may draft, but only on a branch: on main New element and Bulk edit are disabled "
        "and the page says to switch to a branch in the header rather than that the role is wrong."
    ),
    role="architect",
)
def test_browse_architect_on_main(ui, record):
    _as(ui, ARCHITECT)
    ui.goto("/browse")
    ui.check("the Architect is on main", ui.branch_badge().lower() == "main", ui.branch_badge())
    ui.check("an Architect may not add an element on main", _blocked(ui, "new-open"))
    ui.check("an Architect may not bulk-edit on main", _blocked(ui, "bulk-open"))
    page = _page(ui)
    ui.check("the page says to switch to a branch", MAIN_BANNER in page, _alerts(ui))
    ui.check("it does not tell an Architect they are a Reader", READER_BANNER not in page, _alerts(ui))
    ui.shot("Browse as an Architect on main: the write buttons wait for a branch")


@pytest.mark.scenario(
    scenario_id="L07",
    group="L",
    title="An Architect on a branch may add and bulk-edit",
    feature="Browse · role and branch",
    expected=(
        "The same Architect, on a branch of their own, gets New element and Bulk edit back and the "
        "page stops warning them off."
    ),
    role="architect",
    branch=BRANCH_NAME,
)
def test_browse_architect_on_branch(ui, record):
    _as(ui, ARCHITECT)
    _on_branch(ui)
    ui.goto("/browse")
    ui.check(
        "the header says the reader is on a branch",
        "branch" in ui.branch_badge().lower(),
        ui.branch_badge(),
    )
    ui.check("an Architect may add an element on a branch", _usable(ui, "new-open"))
    ui.check("an Architect may bulk-edit on a branch", _usable(ui, "bulk-open"))
    page = _page(ui)
    ui.check(
        "no banner warns them off",
        READER_BANNER not in page and MAIN_BANNER not in page,
        _alerts(ui) or "no banner",
    )
    ui.shot("Browse as an Architect on the L roles branch: both write buttons open")


# =========================================================================== the element page


@pytest.mark.scenario(
    scenario_id="L08",
    group="L",
    title="A Reader may open an element but not save it",
    feature="Element · role gating",
    expected=(
        "The Edit tab still opens for a Reader — the fields are readable — but Save is disabled and "
        "beside it the page says a Reader may not edit; adding a relationship is refused too."
    ),
    role="reader",
)
def test_element_as_reader(ui, record):
    _as(ui, READER)
    ui.goto(f"/element/{ELEMENT}")
    ui.must("the element opened", ELEMENT in _page(ui), _page(ui)[:120])
    _el_tab(ui, "Edit")
    ui.check("a Reader may not save an element", _blocked(ui, "el-save"))
    ui.check("the refusal names the role", "A Reader may not edit." in _page(ui), _page(ui)[-300:])
    _el_tab(ui, "Relationships")
    ui.check("a Reader may not add a relationship", _blocked(ui, "el-rel-add"))
    ui.shot("The Element page's Edit tab as a Reader: Save refused, and the reason beside it")


@pytest.mark.scenario(
    scenario_id="L09",
    group="L",
    title="A Reviewer may not save an element either, and is named as a Reviewer",
    feature="Element · role gating",
    expected=(
        "A Reviewer gets the same refusal as a Reader, worded with their own role: 'A Reviewer may not edit.'"
    ),
    role="reviewer",
)
def test_element_as_reviewer(ui, record):
    _as(ui, REVIEWER)
    ui.goto(f"/element/{ELEMENT}")
    _el_tab(ui, "Edit")
    ui.check("a Reviewer may not save an element", _blocked(ui, "el-save"))
    ui.check("the refusal names the Reviewer", "A Reviewer may not edit." in _page(ui), _page(ui)[-300:])
    ui.shot("The Element page as a Reviewer: the refusal is worded in their own role")


@pytest.mark.scenario(
    scenario_id="L10",
    group="L",
    title="An Architect on main is sent to a branch rather than refused outright",
    feature="Element · role and branch",
    expected=(
        "On main the Architect's Save is disabled, and the sentence beside it is an instruction — "
        "switch to a branch — not a refusal of the role."
    ),
    role="architect",
)
def test_element_architect_on_main(ui, record):
    _as(ui, ARCHITECT)
    ui.goto(f"/element/{ELEMENT}")
    _el_tab(ui, "Edit")
    ui.check("an Architect may not save straight onto main", _blocked(ui, "el-save"))
    page = _page(ui)
    ui.check(
        "the page says how to get the Save back",
        "Switch to a branch in the header to edit." in page,
        page[-300:],
    )
    ui.check("it does not say the role may not edit", "may not edit" not in page, page[-300:])
    ui.shot("The Element page as an Architect on main: Save waits for a branch")


@pytest.mark.scenario(
    scenario_id="L11",
    group="L",
    title="An Architect on a branch saves the element, and the branch takes the row",
    feature="Element · role and branch",
    expected=(
        "On the branch the Architect's Save is enabled, saving reports success, and the change lands "
        "on the branch while main keeps its own name."
    ),
    role="architect",
    branch=BRANCH_NAME,
)
def test_element_architect_on_branch(ui, record):
    _as(ui, ARCHITECT)
    _on_branch(ui)
    ui.goto(f"/element/{ELEMENT}")
    _el_tab(ui, "Edit")
    ui.must("an Architect may save on a branch", _usable(ui, "el-save"))
    ui.fill("el-name", BRANCH_ELEMENT_NAME)
    ui.click("el-save")
    feedback = ui.text("el-save-feedback")
    ui.check("the save was accepted", "aved" in feedback or "pdated" in feedback, feedback)
    _el_tab(ui, "Relationships")
    ui.check("an Architect may add a relationship on a branch", _usable(ui, "el-rel-add"))
    _el_tab(ui, "Edit")
    ui.shot("The element saved on the L roles branch by its Architect")
    ui.branch("main")
    ui.goto(f"/element/{ELEMENT}")
    ui.check(
        "main never took the branch's name",
        BRANCH_ELEMENT_NAME not in _page(ui),
        _page(ui)[:200],
    )
    ui.shot("Main still carries the element's own name after the branch edit")


# =========================================================================== import


@pytest.mark.scenario(
    scenario_id="L12",
    group="L",
    title="A Reader may validate an import but not load it",
    feature="Import · role gating",
    expected=(
        "Import's Load button is disabled for a Reader, while Download template and Validate only — "
        "neither of which writes anything — stay available."
    ),
    role="reader",
)
def test_import_as_reader(ui, record, finding):
    _as(ui, READER)
    ui.goto("/import")
    ui.check("a Reader may not load an import", _blocked(ui, "im-load"))
    ui.check("a Reader may still download the template", _usable(ui, "im-template"))
    ui.check("a Reader may still validate", _usable(ui, "im-validate"))
    page = _page(ui)
    ui.check("the page says something about where the reader stands", "You are on main" in page, _alerts(ui))
    reason = _tooltip(ui, "#im-load")
    ui.check(
        "and names the role that may not load, rather than only the branch",
        "Reader" in page and "may not load an import" in page,
        _alerts(ui),
    )
    ui.shot("Import as a Reader: Load refused, with the role named as the reason")
    if "Reader" not in page and not reason:
        finding.append(
            _f(
                "L-2",
                "src/ea/ui/pages/import_page.py — the banner and the Load button",
                "usability",
                "Import never says a Reader's role is why Load is disabled",
                "The only banner on Import talks about main and branches, so a Reader is told to "
                "'switch to a branch in the header to stage an import for review' — advice that will "
                "not enable Load for them, because `import` needs Architect or Admin. The Load button "
                "raises no tooltip either, so the page never names the role. Browse and the Element "
                "page both name it in the same situation; Import should too.",
            )
        )


@pytest.mark.scenario(
    scenario_id="L13",
    group="L",
    title="An Architect may load an import onto a branch but not onto main",
    feature="Import · role and branch",
    expected=(
        "On main the Architect's Load is disabled and the banner says an import there would change "
        "the model directly; on the branch Load is enabled and the banner says what is loaded stays "
        "on the branch."
    ),
    role="architect",
    branch=BRANCH_NAME,
)
def test_import_architect(ui, record):
    _as(ui, ARCHITECT)
    ui.goto("/import")
    ui.check("an Architect may not load onto main", _blocked(ui, "im-load"))
    ui.check("the banner explains what main would mean", "You are on main" in _page(ui), _alerts(ui))
    ui.shot("Import as an Architect on main: Load is refused")
    _on_branch(ui)
    ui.goto("/import")
    ui.check("an Architect may load onto a branch", _usable(ui, "im-load"))
    ui.check("the banner says what the branch does with it", "lands on the branch" in _page(ui), _alerts(ui))
    ui.shot("Import as an Architect on the L roles branch: Load is open")


# =========================================================================== propose


@pytest.mark.scenario(
    scenario_id="L14",
    group="L",
    title="A Reader may run a proposal through the reader but not apply it",
    feature="Propose · role gating",
    expected=(
        "Analyse is open to everyone — it writes nothing — but Apply to branch is disabled for a "
        "Reader, so the merge log they are shown cannot reach a branch."
    ),
    role="reader",
)
def test_propose_as_reader(ui, record, finding):
    _as(ui, READER)
    ui.goto("/propose")
    ui.check("a Reader may still download the proposal template", _usable(ui, "pr-template"))
    ui.must("a Reader may still analyse", _usable(ui, "pr-analyse"))
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=45_000)
    ui.settle()
    ui.check("the analysis came back", ui.visible("pr-result"))
    ui.check("a Reader may not apply a proposal", _blocked(ui, "pr-apply"))
    reason = _tooltip(ui, "#pr-apply")
    why = ui.text("pr-apply-why")
    ui.check(
        "and the reason stands beside the button, naming the role",
        "Reader" in why and "may not apply" in why,
        why or "(nothing beside the button)",
    )
    ui.shot("Propose as a Reader: the analysis runs, Apply to branch does not, and says why")
    if not reason and "may not" not in _page(ui):
        finding.append(
            _f(
                "L-3",
                "src/ea/ui/pages/propose.py — the Apply to branch button",
                "usability",
                "Propose disables Apply to branch without saying why",
                "`disabled=not ctx.can('propose')` is the whole of it: no tooltip, no sentence beside "
                "the button, nothing on the page naming the role. A Reader who has just watched the "
                "reader work through their document is left with a dead button and no explanation.",
            )
        )


@pytest.mark.scenario(
    scenario_id="L15",
    group="L",
    title="An Architect may apply a proposal to a branch",
    feature="Propose · role gating",
    expected="The same page, read as an Architect, offers Apply to branch.",
    role="architect",
)
def test_propose_as_architect(ui, record):
    _as(ui, ARCHITECT)
    ui.goto("/propose")
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=45_000)
    ui.settle()
    ui.check("an Architect may apply a proposal", _usable(ui, "pr-apply"))
    ui.shot("Propose as an Architect: Apply to branch is open")


# =========================================================================== branches


@pytest.mark.scenario(
    scenario_id="L16",
    group="L",
    title="A Reader may read a branch and touch nothing on it",
    feature="Branches · role gating",
    expected=(
        "The Branches page opens for a Reader — the merge log, the counts and the review panel are "
        "all readable — while New branch, Abandon and Merge are disabled and no review control is "
        "offered. The merge button says why it is disabled."
    ),
    role="reader",
)
def test_branches_as_reader(ui, record):
    _as(ui, ARCHITECT)
    _ensure_branch(ui)
    _as(ui, READER)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.check("a Reader may not create a branch from the page", _blocked(ui, "branch-new-open-page"))
    ui.check("a Reader may not abandon a branch", _blocked(ui, "br-abandon"))
    ui.check("a Reader may not merge a branch", _blocked(ui, "br-merge"))
    detail = _detail(ui)
    ui.check(
        "the merge button says who may merge",
        "only an architect" in detail and "or an admin may merge" in detail,
        detail[:600],
    )
    ui.check("a Reader is offered no Request review", not _present(ui, "rv-request"))
    ui.check("a Reader is offered no Approve", not _present(ui, "rv-approve"))
    ui.check("a Reader is offered no Send back", not _present(ui, "rv-send-back"))
    ui.check("the page still names the role reading it", "as Reader" in _page(ui), _page(ui)[:200])
    ui.shot("The Branches page as a Reader: readable, and every control that writes refused")


@pytest.mark.scenario(
    scenario_id="L17",
    group="L",
    title="An Architect may request a review of their own branch but not merge it unapproved",
    feature="Branches · role gating",
    expected=(
        "On the branch they wrote, the Architect is offered Request review and Abandon, while Merge "
        "is disabled and says the branch must be approved by its reviewers first. Requesting the "
        "review moves the branch into review."
    ),
    role="architect",
    branch=BRANCH_NAME,
)
def test_branches_as_architect_author(ui, record):
    _as(ui, ARCHITECT)
    _on_branch(ui)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.check("an Architect may create a branch from the page", _usable(ui, "branch-new-open-page"))
    ui.check("an Architect may abandon the branch they wrote", _usable(ui, "br-abandon"))
    ui.check("an Architect may not merge an unapproved branch", _blocked(ui, "br-merge"))
    detail = _detail(ui)
    ui.check(
        "the merge button says what is missing",
        "must be approved by its reviewers first" in detail,
        detail[:600],
    )
    ui.must("the author is offered Request review", _usable(ui, "rv-request"))
    ui.shot("The branch as its Architect: review to request, merge refused until it is approved")
    ui.click("rv-request")
    ui.settle()
    after = _detail(ui)
    ui.check("the branch went into review", "in review" in after.lower(), after[:400])
    ui.check("the page says the branch is now frozen", "frozen" in after.lower(), after[:400])
    ui.shot("The branch after its author requested the review: in review and frozen")


@pytest.mark.scenario(
    scenario_id="L18",
    group="L",
    title="A Reviewer is given the decision controls on a branch in review, and no merge",
    feature="Branches · review controls",
    expected=(
        "The Reviewer sees Approve and Send back on a branch in review, together with the element "
        "types that must be approved, but Merge stays disabled because merging is not their action."
    ),
    role="reviewer",
    branch=BRANCH_NAME,
)
def test_branches_as_reviewer(ui, record):
    _as(ui, REVIEWER)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.check("the Reviewer is offered Approve", _usable(ui, "rv-approve"))
    ui.check("the Reviewer is offered Send back", _usable(ui, "rv-send-back"))
    ui.check("the Reviewer is offered the types to approve", ui.visible("rv-types"))
    ui.check("a Reviewer may not merge", _blocked(ui, "br-merge"))
    detail = _detail(ui)
    ui.check(
        "the merge button says who may merge instead",
        "only an architect" in detail and "or an admin may merge" in detail,
        detail[:600],
    )
    ui.check("a Reviewer may not create a branch from the page", _blocked(ui, "branch-new-open-page"))
    ui.check("a Reviewer may not abandon somebody else's branch", _blocked(ui, "br-abandon"))
    ui.check("the type the branch touches is named", "Data Entity" in detail, detail[:800])
    ui.shot("The branch in review as the Reviewer: approve or send back, but never merge")


@pytest.mark.scenario(
    scenario_id="L19",
    group="L",
    title="The Architect who wrote the branch is told somebody else approves it",
    feature="Branches · review controls",
    expected=(
        "Back on the branch in review, its author is offered no Approve and no Send back, and the "
        "review panel says in words that somebody else decides."
    ),
    role="architect",
    branch=BRANCH_NAME,
)
def test_branches_author_may_not_approve(ui, record):
    _as(ui, ARCHITECT)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.check("the author is offered no Approve", not _present(ui, "rv-approve"))
    ui.check("the author is offered no Send back", not _present(ui, "rv-send-back"))
    ui.check("the author may no longer request the review again", not _present(ui, "rv-request"))
    detail = _detail(ui)
    ui.check(
        "the panel says who decides instead",
        "somebody else approves it" in detail,
        detail[:600],
    )
    ui.check("merging is still refused to the author", _blocked(ui, "br-merge"))
    ui.shot("The branch in review, read by the Architect who wrote it")


@pytest.mark.scenario(
    scenario_id="L20",
    group="L",
    title="An Admin may merge a branch nobody has reviewed, and the page says so",
    feature="Branches · role gating",
    expected=(
        "The same branch read as an Admin offers Merge, with a sentence saying an admin may merge "
        "without a review and that the log will record it. Abandon is open to an Admin too."
    ),
    branch=BRANCH_NAME,
)
def test_branches_as_admin(ui, record):
    _as(ui, ADMIN)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.check("an Admin may merge without a review", _usable(ui, "br-merge"))
    detail = _detail(ui)
    ui.check(
        "the page says the merge will be recorded as unreviewed",
        "an admin may merge without a review" in detail,
        detail[:600],
    )
    ui.check("an Admin may abandon somebody else's branch", _usable(ui, "br-abandon"))
    ui.check("an Admin may create a branch from the page", _usable(ui, "branch-new-open-page"))
    ui.shot("The branch as an Admin: merge is open, and the page says at what cost")


# =========================================================================== metamodel


@pytest.mark.scenario(
    scenario_id="L21",
    group="L",
    title="An Architect may read the metamodel but save neither it nor the reviewers",
    feature="Metamodel · role gating",
    expected=(
        "The type graph, the grids and Export YAML are open to an Architect, while Save changes and "
        "Save reviewers are disabled — both are Admin actions."
    ),
    role="architect",
)
def test_metamodel_as_architect(ui, record, finding):
    _as(ui, ARCHITECT)
    ui.goto("/metamodel")
    ui.check("the metamodel is readable", ui.visible("mm-types-grid"))
    ui.check("an Architect may not save the metamodel", _blocked(ui, "mm-save"))
    ui.check("an Architect may still export the pack", _usable(ui, "mm-export"))
    _mm_tab(ui, "Reviewers")
    ui.check("the reviewers grid is readable", ui.visible("mm-reviewers-grid"))
    ui.check("an Architect may not save reviewer assignments", _blocked(ui, "mm-reviewers-save"))
    ui.check(
        "the reviewers tab says who may save it",
        "Only an admin saves this table." in _page(ui),
        _page(ui)[:200],
    )
    why = ui.text("mm-save-why")
    ui.check(
        "and Save changes says why it is off, naming the role",
        "Architect" in why and "only an admin saves it" in why,
        why or "(nothing beside the button)",
    )
    ui.shot("The Metamodel's Reviewers tab as an Architect: readable, not saveable")
    if not why.strip() and not _tooltip(ui, "#mm-save"):
        finding.append(
            _f(
                "L-4",
                "src/ea/ui/pages/metamodel.py — the Save changes button",
                "usability",
                "Metamodel's Save changes is disabled without a reason anywhere on the page",
                "The Reviewers tab does say 'Only an admin saves this table.', but the page-level "
                "Save changes button carries no tooltip and no sentence, so a non-admin who has just "
                "typed into a grid has no way to learn why saving is refused. Give it the same "
                "treatment the Reviewers grid already has.",
            )
        )


@pytest.mark.scenario(
    scenario_id="L22",
    group="L",
    title="The metamodel is Admin-only to save, and every other role is refused it",
    feature="Metamodel · role gating",
    expected=(
        "Save changes and Save reviewers are disabled for a Reader and a Reviewer as well as an "
        "Architect, and enabled only for an Admin."
    ),
)
def test_metamodel_per_persona(ui, record):
    ui.goto("/metamodel")
    for persona in (READER, REVIEWER):
        _as(ui, persona)
        ui.check(f"{_a(persona)} may not save the metamodel", _blocked(ui, "mm-save"))
        ui.check(f"{_a(persona)} may still export the pack", _usable(ui, "mm-export"))
        _mm_tab(ui, "Reviewers")
        ui.check(f"{_a(persona)} may not save reviewer assignments", _blocked(ui, "mm-reviewers-save"))
        ui.shot(f"The Metamodel as {_a(persona)}: both Save buttons refused")
    _as(ui, ADMIN)
    ui.check("an Admin may save the metamodel", _usable(ui, "mm-save"))
    _mm_tab(ui, "Reviewers")
    ui.check("an Admin may save reviewer assignments", _usable(ui, "mm-reviewers-save"))
    ui.shot("The Metamodel as an Admin: both Save buttons open")


# =========================================================================== read, ask, download


@pytest.mark.scenario(
    scenario_id="L23",
    group="L",
    title="Every persona can still read, ask and download",
    feature="Roles · what every role keeps",
    expected=(
        "Whatever the role, Browse lists elements, Health renders, the Ask page answers a question "
        "with a document, and that document downloads as Markdown — read, ask and download are the "
        "three actions every role in the table holds."
    ),
)
def test_every_persona_may_read_ask_and_download(ui, record):
    for persona in PERSONAS:
        _as(ui, persona)
        ui.goto("/browse")
        ui.check(f"{_a(persona)} sees the model on Browse", ui.grid_row_count("browse-grid") > 0)
        ui.goto("/health")
        ui.check(f"{_a(persona)} sees the health page", len(ui.text("health-body")) > 40)
        ui.goto("/ask")
        _ask(ui)
        ui.check(f"{_a(persona)} got an answer document", ui.page.locator(DOCUMENT).count() > 0)
        path = ui.download("ask-doc-md", ".md")
        ui.check(f"{_a(persona)} downloaded the answer", path.stat().st_size > 0, str(path))
        ui.shot(f"The answer document {DISPLAY[persona]} asked for, and downloaded as Markdown")


# ================================================================ the branch is not the role
#
# Everything above reads a Reader on main and an Architect on both. The other half of the
# first rule in the table — `edit_content` **and** (a branch, or `edit_main`) — is a Reader
# on a branch: the branch is where an Architect's write controls come back, and the
# scenarios below prove it gives a Reader nothing. The rest of the group then presses the
# buttons the pages disable, because a gate that only the browser holds is not a gate.


FORCED_ELEMENT_NAME = "CMS_Unit_Outline (forced past a disabled Save)"
FORCED_NEW_NAME = "L27forced Data Entity"
FORCED_IMPORT_MARKER = "l30forced"
FORCED_IMPORT_CSV = (
    "id,type,name,description\n"
    "L-DE-FORCED,data_entity,L Forced Import,"
    f"A row a Reader pressed a disabled Load for ({FORCED_IMPORT_MARKER}).\n"
)


def _force_click(ui, component_id: str, clicks: int = 1) -> None:
    """Press a control the page disabled, from the browser the reader is already holding.

    Taking the attribute off the button is not enough — the component keeps the prop and
    swallows the click — but the callback behind it is one line of script away, and anyone
    who can open a console has that line. Every gate in the table is drawn twice: the page
    disables the control, and the service behind it calls `require()`. This presses past
    the first to find out whether the second is there.
    """
    ui.page.evaluate(
        "([id, n]) => window.dash_clientside.set_props(id, {n_clicks: n})",
        [component_id, clicks],
    )
    ui.page.wait_for_timeout(300)
    ui.settle()


def _search(ui, text: str) -> tuple[str, int]:
    """Search Browse and wait out the box's 400 ms debounce; the count and the rows shown."""
    ui.fill("browse-text", text)
    ui.page.wait_for_timeout(700)
    ui.settle()
    return ui.text("browse-count"), ui.grid_row_count("browse-grid")


def _branch_list(ui) -> str:
    """Every branch the Branches page lists, whatever its status — one block of text.

    Opened on the group's own branch: the status control is wired through the store the
    branch detail carries, so a page with nothing selected does not filter at all.
    """
    _branches(ui)
    ui.segmented("br-status", "All")
    return ui.text("br-list")


def _rel_rows(ui) -> int:
    """How many relationships the Relationships tab is listing, incoming and outgoing."""
    return ui.page.locator("#el-rel-tables tbody tr").count()


def _mm_row(ui, row_id: str) -> int:
    """Whether a row is on the metamodel's type grid, which renders only what is in view."""
    body = ui.page.locator("#mm-types-grid .ag-body-viewport").first
    if body.count():
        body.evaluate("el => { el.scrollTop = el.scrollHeight; }")
        ui.page.wait_for_timeout(400)
    return ui.page.locator(f"#mm-types-grid .ag-row[row-id={json.dumps(row_id)}]").count()


def _mm_row_ids(ui) -> list[str]:
    """The last few row ids the type grid is rendering, for a failure to be readable."""
    ids = ui.page.locator("#mm-types-grid .ag-center-cols-container .ag-row").evaluate_all(
        "rows => rows.map(r => r.getAttribute('row-id'))"
    )
    return ids[-5:]


@pytest.mark.scenario(
    scenario_id="L24",
    group="L",
    title="A Reader put on a branch is still a Reader on it",
    feature="Roles · role and branch",
    expected=(
        "A Reader may switch onto a branch from the Branches page and read the draft it holds, and "
        "the branch opens nothing: Browse still refuses New element and still names the role rather "
        "than main, the Element page still says a Reader may not edit, and Import's Load is dead on "
        "the very branch its banner on main told the Reader to switch to."
    ),
    role="reader",
    branch=BRANCH_NAME,
)
def test_reader_on_a_branch(ui, record):
    _as(ui, ARCHITECT)
    _ensure_branch(ui)
    _as(ui, READER)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.must("a Reader may take a branch somebody else wrote", _usable(ui, "br-switch"))
    ui.click("br-switch")
    ui.check(
        "the header says the Reader is on the branch",
        "branch" in ui.branch_badge().lower(),
        ui.branch_badge(),
    )
    ui.goto("/browse")
    ui.check("a Reader may not add an element on a branch", _blocked(ui, "new-open"))
    ui.check("a Reader may not bulk-edit on a branch", _blocked(ui, "bulk-open"))
    page = _page(ui)
    ui.check("the page still names the role", READER_BANNER in page, _alerts(ui))
    ui.check("it no longer sends them to a branch they are on", MAIN_BANNER not in page, _alerts(ui))
    ui.shot("Browse on the L roles branch as a Reader: the branch changed nothing about the role")
    ui.goto(f"/element/{ELEMENT}")
    ui.check("a Reader reads what the branch holds", BRANCH_ELEMENT_NAME in _page(ui), _page(ui)[:200])
    _el_tab(ui, "Edit")
    ui.check("a Reader may not save on a branch either", _blocked(ui, "el-save"))
    ui.check(
        "the refusal is still the role, not the branch",
        "A Reader may not edit." in _page(ui),
        _page(ui)[-300:],
    )
    ui.shot("The element as a Reader on the branch: the branch's draft, and the same refusal")
    ui.goto("/import")
    ui.check(
        "the banner says the branch would take the import", "lands on the branch" in _page(ui), _alerts(ui)
    )
    ui.check("the advice Import gives on main does not enable Load", _blocked(ui, "im-load"))
    ui.shot("Import on the branch as a Reader: the advice was followed and Load is refused all the same")


# ======================================================= the gate behind the disabled button


@pytest.mark.scenario(
    scenario_id="L25",
    group="L",
    title="A Reader is not offered a bin on a relationship, any more than Add beside it",
    feature="Element · Relationships · role gating",
    expected=(
        "On the Relationships tab a Reader's Add is disabled and so is the bin on every row — the "
        "page offers only what the role may use — and the relationships are all still there."
    ),
    role="reader",
)
def test_relationship_bin_as_reader(ui, record):
    # This scenario used to require the opposite: a live bin, pressed, and refused by the
    # server. That was the finding — a bin that is offered and then refused is a broken
    # promise, and Add beside it was already gated.
    _as(ui, READER)
    ui.goto(f"/element/{ELEMENT}")
    _el_tab(ui, "Relationships")
    bins = ui.page.locator("#el-rel-tables button")
    ui.must("the element has a relationship a bin could remove", bins.count() > 0, f"{bins.count()} bins")
    before = _rel_rows(ui)
    ui.check("a Reader may not add a relationship", _blocked(ui, "el-rel-add"))
    live = [i for i in range(bins.count()) if bins.nth(i).is_enabled()]
    ui.check(
        "and no row offers a bin either",
        not live,
        f"{len(live)} of {bins.count()} bins are live",
    )
    ui.check(
        "each bin says what it would do, for a reader who cannot see the icon",
        bins.first.get_attribute("aria-label") == "Remove this relationship",
        bins.first.get_attribute("aria-label") or "(no name)",
    )
    ui.shot("The Relationships tab as a Reader: neither Add nor any row's bin is offered")
    ui.check("and every relationship is still there", _rel_rows(ui) == before, f"{_rel_rows(ui)} rows")


@pytest.mark.scenario(
    scenario_id="L26",
    group="L",
    title="A Reader may type into every field, and the server refuses the save they force",
    feature="Element · role gating",
    expected=(
        "The Edit tab's fields take a Reader's typing — only Save is disabled — and pressing Save "
        "past that is refused by the server, naming the role, with the element unchanged on main."
    ),
    role="reader",
)
def test_element_save_forced_by_a_reader(ui, record):
    _as(ui, READER)
    ui.goto(f"/element/{ELEMENT}")
    _el_tab(ui, "Edit")
    ui.must("Save is disabled for a Reader", _blocked(ui, "el-save"))
    ui.fill("el-name", FORCED_ELEMENT_NAME)
    ui.check(
        "the field itself takes a Reader's typing",
        ui.page.input_value("#el-name") == FORCED_ELEMENT_NAME,
        ui.page.input_value("#el-name"),
    )
    _force_click(ui, "el-save")
    feedback = ui.text("el-save-feedback")
    ui.check("the server refuses the save", "may not" in feedback.lower(), feedback or "no feedback")
    ui.check("the refusal names the role", "Reader" in feedback, feedback or "no feedback")
    ui.check("nothing reports a new version", "Saved version" not in feedback, feedback or "no feedback")
    ui.shot("A Reader who pressed Save past the disabled button, and the answer from the server")
    ui.goto(f"/element/{ELEMENT}")
    ui.check("the element kept its own name", FORCED_ELEMENT_NAME not in _page(ui), _page(ui)[:200])


@pytest.mark.scenario(
    scenario_id="L27",
    group="L",
    title="A Reader who forces the New element modal open still creates nothing",
    feature="Browse · role gating",
    expected=(
        "New element opens when its disabled state is taken off in the browser, and the Create "
        "inside it is refused by the server, naming the role; no element by that name is in the "
        "model afterwards."
    ),
    role="reader",
)
def test_new_element_forced_by_a_reader(ui, record):
    _as(ui, READER)
    ui.goto("/browse")
    ui.must("New element is disabled for a Reader", _blocked(ui, "new-open"))
    _force_click(ui, "new-open")
    ui.must("the modal opened once the browser let the click through", ui.visible("new-modal-body"))
    ui.select("new-type", "Data Entity", exact=True)
    ui.fill("new-name", FORCED_NEW_NAME)
    ui.click("new-save")
    feedback = ui.text("new-feedback")
    ui.check("the server refuses the creation", "may not" in feedback.lower(), feedback or "no feedback")
    ui.check("the refusal names the role", "Reader" in feedback, feedback or "no feedback")
    ui.shot("The New element modal a Reader forced open, and the refusal Create came back with")
    ui.check("the reader was not taken to a new element", "/browse" in ui.page.url, ui.page.url)
    ui.goto("/browse")
    count, rows = _search(ui, "l27forced")
    ui.check("nothing by that name is in the model", rows == 0 and count.startswith("0 of"), count)
    ui.shot("Browse finds no element for the name the Reader tried to create")


@pytest.mark.scenario(
    scenario_id="L28",
    group="L",
    title="The Metamodel lets a Reader fill the grid, and refuses what they save",
    feature="Metamodel · role gating",
    expected=(
        "Add type is offered to a Reader and puts a row on the grid; the save behind the disabled "
        "button is refused by the server, naming the role; and Reload from file, which replaces the "
        "stored pack for everybody, is refused for the same reason."
    ),
    role="reader",
)
def test_metamodel_write_paths_as_reader(ui, record, finding):
    _as(ui, READER)
    ui.goto("/metamodel")
    ui.must("the type grid is on the page", ui.visible("mm-types-grid"))
    ui.check("a Reader is offered Add type", _usable(ui, "mm-add-type"))
    _mm_tab(ui, "Relationship types")
    ui.check("a Reader is offered Add relationship type", _usable(ui, "mm-add-rel"))
    _mm_tab(ui, "Attributes")
    ui.check("a Reader is offered Add attribute", _usable(ui, "mm-add-attr"))
    _mm_tab(ui, "Element types")
    ui.click("mm-add-type")
    ui.check(
        "the row a Reader added is on the grid",
        _mm_row(ui, "new_type_1") > 0,
        f"the grid ends {_mm_row_ids(ui)}",
    )
    ui.must("Save changes is disabled for a Reader", _blocked(ui, "mm-save"))
    _force_click(ui, "mm-save")
    feedback = ui.text("mm-feedback")
    ui.check(
        "the server refuses the save", "may not edit the metamodel" in feedback, feedback or "no feedback"
    )
    ui.check("the refusal names the role", "Reader" in feedback, feedback or "no feedback")
    ui.shot("The Metamodel as a Reader: a row typed in, and the save refused by the server")
    # Reload from file is the page's other write: it reads the pack off disk and stores it,
    # discarding whatever an admin saved. It is offered to every role, with no reason beside it.
    ui.check("Reload from file is offered to a Reader", _usable(ui, "mm-reload"))
    ui.check("and it says nothing about who may press it", not _tooltip(ui, "#mm-reload"), "no tooltip")
    ui.click("mm-reload")
    reload_said = ui.text("mm-feedback")
    ui.check(
        "a Reader may not rewrite the stored metamodel from the pack file",
        "may not" in reload_said.lower(),
        reload_said or "no feedback",
    )
    ui.shot("Reload from file, pressed by a Reader, and what the page said about it")
    if "Reloaded" in reload_said:
        finding.append(
            _f(
                "L-6",
                "src/ea/ui/pages/metamodel.py — the `reload` callback (ids.MM_RELOAD)",
                "defect",
                "Reload from file rewrites the stored metamodel for every role, with no permission check",
                "`save` refuses a non-admin twice — the button is disabled and the callback checks "
                "`ctx.can('edit_metamodel')` — but `reload` beside it calls `load_pack` and then "
                "`ctx.backend.save_pack(pack)` with no `require()` and no disabled state, so any role, "
                f"a Reader included, can replace the stored pack: the page answered {reload_said!r}. "
                "That discards whatever an admin has saved into the metamodel since the file was "
                "written, for everybody. Gate it on `edit_metamodel` the way the save is gated.",
            )
        )


@pytest.mark.scenario(
    scenario_id="L29",
    group="L",
    title="Save reviewers forced past its disabled state is refused for an Architect",
    feature="Metamodel · Reviewers · role gating",
    expected=(
        "The Reviewers grid's Save is an admin action: pressing it as an Architect with the disabled "
        "state taken off is refused by the service, and the refusal names the role and the action in "
        "a sentence a reader can read."
    ),
    role="architect",
)
def test_save_reviewers_forced_by_an_architect(ui, record, finding):
    _as(ui, ARCHITECT)
    ui.goto("/metamodel")
    _mm_tab(ui, "Reviewers")
    ui.must("Save reviewers is disabled for an Architect", _blocked(ui, "mm-reviewers-save"))
    _force_click(ui, "mm-reviewers-save")
    feedback = ui.text("mm-reviewers-feedback")
    ui.check("the server refuses the assignment", "may not" in feedback.lower(), feedback or "no feedback")
    ui.check("the refusal names the role", "Architect" in feedback, feedback or "no feedback")
    ui.check("it says which action was refused", "assign reviewers" in feedback.lower(), feedback)
    ui.check("nothing reports a save", "saved" not in feedback.lower(), feedback or "no feedback")
    ui.check(
        "the refusal reads as a sentence",
        "an architect" in feedback.lower(),
        feedback or "no feedback",
    )
    ui.shot("Save reviewers, pressed by an Architect past its disabled state, and the refusal")
    if "a Architect" in feedback:
        finding.append(
            _f(
                "L-7",
                "src/ea/services/roles.py — the message `require()` raises",
                "consistency",
                "A refusal for a role whose name starts with a vowel reads 'a Architect', 'a Admin'",
                '`require()` builds its message as `f"a {LABELS.get(role, role)} may not …"`, so the '
                "two roles whose names begin with a vowel are handed to the reader ungrammatically: "
                f"this one came back as {feedback!r}. It is the sentence every refused write shows — "
                "the Element page, Browse, Import, the Branches page and this one all print what "
                "`require()` raised. Choose the article from the role's first letter, the way the "
                "pages that write their own sentences already do.",
            )
        )


@pytest.mark.scenario(
    scenario_id="L30",
    group="L",
    title="A Reader may validate a file and never load it",
    feature="Import · role gating",
    expected=(
        "A Reader's Validate only runs the file through the metamodel and says nothing was written; "
        "the Load behind the disabled button is refused by the server, naming the role, and none of "
        "the file's rows is in the model afterwards."
    ),
    role="reader",
)
def test_import_load_forced_by_a_reader(ui, record):
    _as(ui, READER)
    ui.goto("/import")
    path = ui.run_dir / "uploads" / "l30-elements.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FORCED_IMPORT_CSV, encoding="utf-8")
    ui.page.locator("#im-upload input[type=file]").first.set_input_files(str(path))
    ui.page.locator("#im-files").get_by_text(path.name, exact=False).first.wait_for(timeout=20_000)
    ui.settle()
    ui.click("im-validate")
    validated = ui.text("im-report")
    ui.check(
        "a Reader's validation reads the file and writes nothing",
        "nothing written" in validated.lower(),
        validated[:200] or "no report",
    )
    ui.shot("Import as a Reader: the file validates, and the report says nothing was written")
    ui.must("Load is disabled for a Reader", _blocked(ui, "im-load"))
    _force_click(ui, "im-load")
    loaded = ui.text("im-report")
    ui.check("the server refuses the load", "may not" in loaded.lower(), loaded[:200] or "no report")
    ui.check("the refusal names the role", "Reader" in loaded, loaded[:200] or "no report")
    ui.check("nothing says it was loaded", "Loaded." not in loaded, loaded[:200] or "no report")
    ui.shot("The Load a Reader pressed past its disabled state, and the refusal from the server")
    ui.goto("/browse")
    count, rows = _search(ui, FORCED_IMPORT_MARKER)
    ui.check("none of the file's rows reached the model", rows == 0 and count.startswith("0 of"), count)


@pytest.mark.scenario(
    scenario_id="L31",
    group="L",
    title="A Reader who forces Abandon and Merge changes neither the branch nor main",
    feature="Branches · role gating",
    expected=(
        "Both writes on the Branches page are refused by the service when their disabled state is "
        "taken off: each refusal names the role, the branch is still in review afterwards, and main "
        "still carries its own name for the element the branch changed."
    ),
    role="reader",
    branch=BRANCH_NAME,
)
def test_branch_writes_forced_by_a_reader(ui, record):
    _as(ui, READER)
    _branches(ui)
    ui.must("the branch's detail opened", BRANCH_NAME in _detail(ui), _detail(ui)[:200])
    ui.must("Abandon is disabled for a Reader", _blocked(ui, "br-abandon"))
    _force_click(ui, "br-abandon")
    abandoned = ui.text("br-feedback")
    ui.check(
        "the server refuses the abandon", "may not" in abandoned.lower(), abandoned[:200] or "no feedback"
    )
    ui.check("the refusal names the role", "Reader" in abandoned, abandoned[:200] or "no feedback")
    ui.shot("Abandon, pressed by a Reader past its disabled state, and the refusal")
    ui.must("Merge is disabled for a Reader", _blocked(ui, "br-merge"))
    _force_click(ui, "br-merge")
    merged = ui.text("br-feedback")
    ui.check("the server refuses the merge", "may not" in merged.lower(), merged[:200] or "no feedback")
    ui.check("the refusal names the role", "Reader" in merged, merged[:200] or "no feedback")
    ui.check("nothing says a row was merged", "Merged" not in merged, merged[:200] or "no feedback")
    ui.shot("Merge, pressed by a Reader past its disabled state, and the refusal")
    _branches(ui)
    detail = _detail(ui)
    ui.check("the branch is still there", BRANCH_NAME in detail, detail[:200])
    ui.check("and still in review", "in review" in detail.lower(), detail[:300])
    ui.goto(f"/element/{ELEMENT}")
    ui.check("main never took the branch's row", BRANCH_ELEMENT_NAME not in _page(ui), _page(ui)[:200])
    ui.shot("The branch and main after both forced writes were refused")


@pytest.mark.scenario(
    scenario_id="L32",
    group="L",
    title="A Reader may build the whole proposal and apply none of it",
    feature="Propose · role gating",
    expected=(
        "Add element row and Add relationship row are open to a Reader, so the merge log fills up "
        "under a role that may not apply it; the Apply behind the disabled button is refused, and no "
        "branch was created for it."
    ),
    role="reader",
)
def test_propose_apply_forced_by_a_reader(ui, record):
    _as(ui, READER)
    branches_before = _branch_list(ui)
    ui.goto("/propose")
    ui.must("a Reader may still analyse", _usable(ui, "pr-analyse"))
    ui.click("pr-analyse")
    ui.page.wait_for_selector("#pr-pushback", timeout=45_000)
    ui.settle()
    rows_before = ui.grid_row_count("pr-el-grid")
    ui.check("a Reader is offered Add element row", _usable(ui, "pr-add-el"))
    ui.check("a Reader is offered Add relationship row", _usable(ui, "pr-add-rel"))
    ui.click("pr-add-el")
    ui.check(
        "the row a Reader added is on the merge log",
        ui.grid_row_count("pr-el-grid") == rows_before + 1,
        f"{ui.grid_row_count('pr-el-grid')} rows now, {rows_before} before",
    )
    ui.must("Apply to branch is disabled for a Reader", _blocked(ui, "pr-apply"))
    _force_click(ui, "pr-apply")
    feedback = ui.text("pr-apply-feedback")
    ui.check("the forced apply is refused", "not applied" in feedback.lower(), feedback or "no feedback")
    ui.check("nothing says it was applied to a branch", "Applied to branch" not in feedback, feedback)
    ui.shot("Propose as a Reader: the rows fill in, and the forced Apply is refused")
    branches_after = _branch_list(ui)
    ui.check(
        "no branch was created for it",
        branches_after == branches_before,
        f"{branches_after[:300]} · was {branches_before[:300]}",
    )
