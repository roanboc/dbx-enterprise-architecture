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
    _ensure_branch(ui)
    if BRANCH_NAME not in ui.text("branch-select"):
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
    ui.check("the page states the refusal", READER_BANNER in page or MAIN_BANNER in page, _alerts(ui))
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
    ui.shot("Import as a Reader: Load refused, template and validation still open")
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
    ui.shot("Propose as a Reader: the analysis runs, Apply to branch does not")
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
    ui.shot("The Metamodel's Reviewers tab as an Architect: readable, not saveable")
    if not _tooltip(ui, "#mm-save"):
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
