"""Help where the work is done (initiative 27): a screen's help in a side panel, opened only
when asked; a welcome on a person's first visit; a one-line tip on a screen's first visit.

What a person has closed is remembered by their browser (`ids.HELP_SEEN`, local storage),
never by the store: nothing about a person is kept, and a second browser shows the welcome
once more. The help's text is the screen's page in `docs/guide/screens/`, the same text the
Guide page draws, so the two cannot disagree.

The record changes only in the browser, by a patch merged into what it holds at that moment
(`assets/ea-help.js`): a press the moment it is made, and a first visit's patch when the
server's answer lands. An answer written back whole was built from the record as it stood
when the request left, and undid a press made while it was on its way.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, ctx, html, no_update

from ea.services.guide import GuideService, ScreenHelp
from ea.services.roles import ACTIONS, LABELS, RANK, allowed
from ea.ui import ids, layout
from ea.ui.components import icon, markdown
from ea.ui.context import AppContext, get_context

#: What each screen lets a role do beyond reading it, in the words the side panel uses. The
#: rule is `allowed()`, so what the panel says is what the application enforces.
SCREEN_ACTIONS: dict[str, list[tuple[str, str]]] = {
    "browse": [
        ("edit_content", "add and edit elements on a branch"),
        ("bulk_edit", "edit many elements at once"),
        ("edit_main", "edit directly on main"),
    ],
    "element": [
        ("edit_content", "edit the element, its relationships and links on a branch"),
        ("edit_main", "edit it directly on main"),
    ],
    "ask": [
        ("ask", "ask the assistant"),
        ("keep_deep_dive", "keep a deep dive"),
        ("rate_deep_dive", "rate a deep dive"),
    ],
    "branches": [
        ("create_branch", "create a branch"),
        ("request_review", "ask for a branch to be reviewed"),
        ("review", "approve a branch or send it back"),
        ("merge", "merge an approved branch"),
        ("merge_without_review", "merge a branch without a review"),
    ],
    "import": [("import", "import files onto a branch"), ("edit_main", "import onto main")],
    "feeds": [("import", "run a feed"), ("manage_feeds", "set up, change and delete feeds")],
    "propose": [
        ("propose", "hand in a proposal and apply it to a branch"),
        ("manage_templates", "keep the organisation's proposal templates"),
    ],
    "metamodel": [
        ("edit_metamodel", "edit a draft of the metamodel"),
        ("publish_metamodel", "publish or retire a version"),
        ("assign_reviewers", "assign reviewers to element types"),
    ],
    "organisations": [
        ("manage_organisations", "create, rename, copy and delete organisations"),
        ("apply_metamodel", "apply a metamodel version to an organisation"),
    ],
    "systems": [("connect_systems", "connect and disconnect systems")],
    "users": [("grant_roles", "grant roles to workspace groups and remove them")],
}

#: Where each role starts, in the welcome and in the side panel's link to its guide.
ROLE_START = {
    "reader": ("reader", "Start with Browse or Ask."),
    "reviewer": ("reviewer-and-steward", "Start with Branches: the reviews waiting for you are there."),
    "architect": ("solution-architect", "Start with Branches, or hand in a design on Propose."),
    "admin": ("metamodel-owner", "Start with the Metamodel, Organisations and Users and roles."),
}

SEEN_DEFAULT: dict[str, Any] = {"v": 1, "welcome": False, "tips": True, "screens": []}


def seen_state(seen: Any) -> dict[str, Any]:
    """The browser's record, read defensively: a record from elsewhere, or none, starts afresh."""
    out = dict(SEEN_DEFAULT, screens=[])
    if isinstance(seen, dict):
        out["welcome"] = bool(seen.get("welcome"))
        out["tips"] = seen.get("tips") is not False
        screens = seen.get("screens")
        out["screens"] = [s for s in screens if isinstance(s, str)] if isinstance(screens, list) else []
    return out


def first_visit(seen: Any, screen: str | None) -> tuple[str | None, dict[str, Any]]:
    """What a screen shows unasked, and the record after it: the welcome once, in the first
    screen a browser opens; then each screen's tip once, while tips are on; else nothing.

    Each is recorded as it is shown rather than when it is closed, so neither comes back
    however the person leaves it: once is the promise.
    """
    state = seen_state(seen)
    if not screen:
        return None, state
    if not state["welcome"]:
        state["welcome"] = True
        state["screens"] = sorted({*state["screens"], screen})
        return "welcome", state
    if state["tips"] and screen not in state["screens"]:
        state["screens"] = [*state["screens"], screen]
        return "tip", state
    return None, state


def patch_for(kind: str | None, screen: str | None) -> dict[str, Any] | None:
    """What a first visit tells the browser it showed, for the browser to merge into its record
    (None: nothing shown). It says only that: whatever else the record holds by the time the
    answer lands — tips turned off meanwhile, say — is the browser's, and stays.

    Each patch is new, so one that repeats an earlier one still reaches the browser.
    """
    if kind not in ("welcome", "tip") or not screen:
        return None
    return {"op": "shown", "screen": screen, "welcome": kind == "welcome", "stamp": uuid.uuid4().hex}


def after_action(action: str | None) -> tuple[dict[str, Any] | None, bool]:
    """A press on the welcome, a tip or the Guide: the patch it makes to the record (None:
    unchanged), and whether the slot says the welcome and tips will come again.

    The browser applies the patch itself, the moment the button is pressed. An answer from the
    server may never arrive: the renderer drops a call to a pattern-matched callback that is
    still on its way when the next screen draws or removes that callback's buttons.
    """
    if action == "tips-off":
        return {"op": "tips-off"}, False
    if action == "reset":
        return {"op": "reset"}, True
    return None, False


#: The patch each button on the welcome, a tip or the Guide makes to the record, by its action:
#: handed to the browser, which applies it when the button is pressed.
PRESS_PATCHES = {a: p for a in ("close", "tips-off", "reset") if (p := after_action(a)[0])}


def pressed(triggered: Any, clicks: list | None, spec: list[dict]) -> bool:
    """Whether the control that fired was pressed. A pattern-matched input fires when a page
    draws its controls, each with no clicks yet, and that is not a press."""
    if not isinstance(triggered, dict):
        return False
    return any(n for n, s in zip(clicks or [], spec, strict=False) if s.get("id") == triggered)


def lowest_role(action: str) -> str:
    """The first role, from Reader up, that may do this."""
    holders = [r for r in RANK if r in ACTIONS.get(action, ())]
    return LABELS[min(holders, key=RANK.get)] if holders else LABELS["admin"]


def role_block(screen: str, role: str) -> dmc.Paper:
    """What the reader's own role may do on this screen, read from the rule that enforces it."""
    actions = [(a, words) for a, words in SCREEN_ACTIONS.get(screen, []) if a in ACTIONS]
    label = LABELS.get(role, role)
    lines: list[Any] = [dmc.Text(["Your role: ", html.B(label)], size="sm")]
    if not actions:
        lines.append(dmc.Text("Every role may read and use this screen.", size="sm"))
    else:
        can = [words for a, words in actions if allowed(a, role)]
        cannot = [(words, lowest_role(a)) for a, words in actions if not allowed(a, role)]
        if can:
            lines.append(dmc.Text("You may " + "; ".join(can) + ".", size="sm"))
        if cannot:
            lines.append(
                dmc.Text(
                    "Another role is needed to " + "; ".join(f"{w} ({r})" for w, r in cannot) + ".",
                    size="sm",
                    c="dimmed",
                )
            )
    return dmc.Paper(dmc.Stack(lines, gap=4), p="sm", withBorder=True, radius="md", className="ea-help-role")


def demote(text: str, levels: int) -> str:
    """Headings pushed down, so a page's own `##` sits under the heading that holds it."""
    return re.sub(r"^(#{1,5})\s", lambda m: "#" * min(6, len(m.group(1)) + levels) + " ", text, flags=re.M)


def screen_links() -> dict[str, tuple[str, str]]:
    """Every screen of the navigation by its key: its label and its address."""
    return {
        (href.strip("/") or "home"): (label, href)
        for _, links in layout.NAV_SECTIONS
        for label, href, _ in links
    }


def help_body(context: AppContext, screen: str) -> list[Any]:
    """The side panel: the tip, why, what, how, the flow drawn, tips, the reader's role, and on."""
    help_ = GuideService(context.registry).screen(screen)
    role = context.current_user().role
    guide_slug, _ = ROLE_START.get(role, ROLE_START["reader"])
    more = [
        dmc.Anchor("Getting started", href="/guide#getting-started", size="sm"),
        dmc.Anchor("The guide for your role", href=f"/guide#{guide_slug}", size="sm"),
    ]
    if help_ is None:
        return [
            dmc.Text("This screen has no help of its own yet.", size="sm"),
            dmc.Group(more, gap="md"),
        ]
    links = screen_links()
    related = [
        dmc.Anchor(links[k][0], href=links[k][1], size="sm")
        for k in help_.related
        if k in links and k != screen
    ]
    return [
        dmc.Text(help_.tip, fw=600, size="sm"),
        markdown(demote(help_.markdown, 1), f"help-{screen}"),
        role_block(screen, role),
        dmc.Stack(
            [
                dmc.Group([dmc.Text("Related:", size="sm", fw=600), *related], gap="md") if related else None,
                dmc.Group([dmc.Text("More:", size="sm", fw=600), *more], gap="md"),
            ],
            gap=4,
        ),
    ]


def help_title(context: AppContext, screen: str) -> str:
    help_ = GuideService(context.registry).screen(screen)
    return f"Help — {help_.title}" if help_ else "Help"


def welcome(role: str, screen: str) -> dmc.Paper:
    """What the repository is for, how the navigation follows the work, and where to start.

    No heading, no grid and no table: it stands above a page whose own structure the
    reader came for, and it is shown once.
    """
    _, start = ROLE_START.get(role, ROLE_START["reader"])
    groups = [
        ("tabler:list-search", "Discover", "Find elements, ask questions, and see impact and target state."),
        (
            "tabler:git-branch",
            "Contribute",
            "Change the model on a branch: edit, import or hand in a proposal.",
        ),
        ("tabler:hierarchy-2", "Manage", "Shape the metamodel, the organisations and who holds which role."),
    ]
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Text("Welcome to the EA Repository", fw=700, size="lg"),
                dmc.Text(
                    "It holds the enterprise's architecture as a model you can search, question and change "
                    "safely: every change is made on a branch and reviewed before it reaches main.",
                    size="sm",
                ),
                html.Div(
                    [
                        dmc.Group(
                            [
                                dmc.ThemeIcon(icon(ic, 16), variant="light", size="md", radius="md"),
                                dmc.Stack(
                                    [
                                        dmc.Text(name, fw=600, size="sm"),
                                        dmc.Text(what, size="xs", c="dimmed"),
                                    ],
                                    gap=0,
                                ),
                            ],
                            gap="xs",
                            wrap="nowrap",
                            align="flex-start",
                            className="ea-welcome-group",
                        )
                        for ic, name, what in groups
                    ],
                    className="ea-welcome-groups",
                ),
                dmc.Text(f"You are signed in as {LABELS.get(role, role)}. {start}", size="sm"),
                dmc.Group(
                    [
                        dmc.Anchor(
                            dmc.Button("Getting started", size="xs", leftSection=icon("tabler:rocket", 14)),
                            href="/guide#getting-started",
                            underline="never",
                        ),
                        dmc.Button(
                            "Help for this screen",
                            id={"type": ids.HELP_OPEN, "screen": screen, "place": "welcome"},
                            size="xs",
                            variant="light",
                            leftSection=icon("tabler:help-circle", 14),
                        ),
                        dmc.Button(
                            "Got it",
                            id={"type": ids.HELP_ACTION, "action": "close"},
                            size="xs",
                            variant="subtle",
                        ),
                    ],
                    gap="xs",
                ),
            ],
            gap="xs",
        ),
        p="md",
        withBorder=True,
        radius="md",
        mb="md",
        className="ea-welcome",
    )


def tip(help_: ScreenHelp) -> html.Div:
    """A screen's one line on its first visit, with the way to its help and the way to stop tips.

    Polite rather than an alert: it waits for a screen reader to finish what it is saying.
    """
    return html.Div(
        dmc.Group(
            [
                dmc.Group(
                    [icon("tabler:bulb", 16), dmc.Text(help_.tip, size="sm")],
                    gap="xs",
                    wrap="nowrap",
                    className="ea-tip-text",
                ),
                dmc.Group(
                    [
                        dmc.Button(
                            "Show me how",
                            id={"type": ids.HELP_OPEN, "screen": help_.key, "place": "tip"},
                            size="compact-xs",
                            variant="light",
                        ),
                        dmc.Button(
                            "Got it",
                            id={"type": ids.HELP_ACTION, "action": "close"},
                            size="compact-xs",
                            variant="subtle",
                        ),
                        dmc.Button(
                            "Turn off tips",
                            id={"type": ids.HELP_ACTION, "action": "tips-off"},
                            size="compact-xs",
                            variant="subtle",
                            color="gray",
                        ),
                    ],
                    gap=4,
                ),
            ],
            justify="space-between",
            gap="xs",
        ),
        role="status",
        className="ea-tip",
    )


def register(app) -> None:
    @app.callback(
        Output(ids.HELP_DRAWER, "opened"),
        Output(ids.HELP_BODY, "children"),
        Output(ids.HELP_TITLE, "children"),
        Input({"type": ids.HELP_OPEN, "screen": ALL, "place": ALL}, "n_clicks"),
        Input(ids.URL, "pathname"),
        Input(ids.URL, "hash"),
        prevent_initial_call=True,
    )
    def open_help(clicks, _pathname, _hash):
        """A help button opens its screen's help; following a link closes it — to another
        screen, or to a section of the Guide while the Guide is the screen."""
        button = ctx.triggered_id
        if not isinstance(button, dict):
            return False, no_update, no_update
        if not pressed(button, clicks, ctx.inputs_list[0]):
            return no_update, no_update, no_update
        context = get_context()
        screen = button.get("screen", "")
        return True, help_body(context, screen), help_title(context, screen)

    @app.callback(
        Output(ids.HELP_HINT, "children"),
        Output(ids.HELP_PATCH, "data"),
        Input(ids.HELP_SCREEN, "data"),
        State(ids.HELP_SEEN, "data"),
    )
    def show_first_visit(screen, seen):
        """What the screen shows unasked, and the patch saying so; never the record itself."""
        kind, _ = first_visit(seen, screen)
        patch = patch_for(kind, screen)
        if kind == "welcome":
            return welcome(get_context().current_user().role, screen), patch
        if kind == "tip":
            help_ = GuideService(get_context().registry).screen(screen)
            return (tip(help_) if help_ and help_.tip else None), patch
        return None, no_update

    @app.callback(
        Output(ids.HELP_HINT, "children", allow_duplicate=True),
        Input({"type": ids.HELP_ACTION, "action": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def help_action(clicks):
        """The slot after a press: closed, or saying the welcome and tips will come again. The
        record is the browser's, and it has changed already."""
        if not pressed(ctx.triggered_id, clicks, ctx.inputs_list[0]):
            return no_update
        _, again = after_action(ctx.triggered_id.get("action"))
        return (
            dmc.Text(
                "Done: the welcome and each screen's tip will show again, once each.",
                size="sm",
                className="ea-tip",
            )
            if again
            else None
        )

    # The record's only writers, both in the browser and both merging a patch into the record as
    # it stands when they run: what a first visit showed, when the server's answer lands, and a
    # press on the welcome, a tip or the Guide, when it is made.
    app.clientside_callback(
        """
        function(patch, seen) {
            if (!patch || !window.eaHelp) { return window.dash_clientside.no_update; }
            return window.eaHelp.merge(seen, patch);
        }
        """,
        Output(ids.HELP_SEEN, "data"),
        Input(ids.HELP_PATCH, "data"),
        State(ids.HELP_SEEN, "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        f"""
        function(clicks, seen) {{
            const action = window.eaHelp && window.eaHelp.pressed(clicks);
            const patch = action && {json.dumps(PRESS_PATCHES)}[action];
            return patch ? window.eaHelp.merge(seen, patch) : window.dash_clientside.no_update;
        }}
        """,
        Output(ids.HELP_SEEN, "data", allow_duplicate=True),
        Input({"type": ids.HELP_ACTION, "action": ALL}, "n_clicks"),
        State(ids.HELP_SEEN, "data"),
        prevent_initial_call=True,
    )
