"""Application shell: header with the branch selector, navigation and the routed page container."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from ea.backend.branching import MAIN
from ea.services.roles import DESCRIPTIONS, LABELS
from ea.ui import ids
from ea.ui.components import icon, modal_title

ROLE_COLOURS = {"admin": "red", "architect": "indigo", "reviewer": "teal", "reader": "gray", "agent": "cyan"}

THEME = {
    "primaryColor": "indigo",
    "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    "defaultRadius": "md",
    "headings": {"fontWeight": "650"},
}

NAV_SECTIONS = [
    ("Home", [("Home", "/", "tabler:home")]),
    (
        "Discover",
        [
            ("Browse", "/browse", "tabler:list-search"),
            ("Ask", "/ask", "tabler:message-chatbot"),
            ("Impact", "/impact", "tabler:radar"),
            ("Target state", "/target", "tabler:target-arrow"),
        ],
    ),
    (
        "Contribute",
        [
            ("Propose", "/propose", "tabler:file-plus"),
            ("Import", "/import", "tabler:file-import"),
            ("Branches", "/branches", "tabler:git-branch"),
        ],
    ),
    (
        "Manage",
        [
            ("Metamodel", "/metamodel", "tabler:hierarchy-2"),
            ("Health", "/health", "tabler:heart-rate-monitor"),
        ],
    ),
]


def branch_badge(branch_id: str, changes: int | None = None) -> dmc.Badge:
    """What the header says about the branch the reader is on."""
    if branch_id == MAIN:
        return dmc.Badge(
            "main", variant="light", color="gray", size="lg", leftSection=icon("tabler:git-branch", 12)
        )
    label = f"branch · {changes} change{'s' if changes != 1 else ''}" if changes is not None else "branch"
    return dmc.Badge(
        label, variant="filled", color="orange", size="lg", leftSection=icon("tabler:git-branch", 12)
    )


def role_badge(role: str, display_name: str = "") -> dmc.Badge:
    """Who the reader is and in which role."""
    return dmc.Badge(
        f"{display_name or LABELS.get(role, role)}",
        variant="light",
        color=ROLE_COLOURS.get(role, "gray"),
        size="lg",
        leftSection=icon("tabler:user", 12),
    )


def persona_switcher(persona: str) -> dmc.Select:
    """The debug switcher of mock authentication: the four user roles a click away, Admin by default."""
    return dmc.Select(
        id=ids.PERSONA_SELECT,
        data=[
            {"value": r, "label": f"{LABELS[r]} \u2014 {DESCRIPTIONS[r][:48]}\u2026"}
            for r in LABELS
            if r != "agent"
        ],
        value=persona if persona != "agent" else "admin",
        w=200,
        size="sm",
        allowDeselect=False,
        leftSection=icon("tabler:user", 14),
        comboboxProps={"withinPortal": True, "width": 420, "position": "bottom-end"},
    )


def new_branch_modal(work_packages: list[dict[str, str]]) -> dmc.Modal:
    return dmc.Modal(
        id=ids.BRANCH_NEW_MODAL,
        title=modal_title("New branch", ids.BRANCH_NEW_MODAL),
        children=dmc.Stack(
            [
                dmc.Text(
                    "A branch starts from main as it is now. What you add, change or remove on it stays on the "
                    "branch until you merge it, item by item, on the Branches page.",
                    size="sm",
                    c="dimmed",
                ),
                dmc.TextInput(
                    id=ids.BRANCH_NEW_NAME, label="Name", required=True, placeholder="CMS upgrade phase 2"
                ),
                dmc.Textarea(id=ids.BRANCH_NEW_DESC, label="What it is for", autosize=True, minRows=2),
                dmc.Select(
                    id=ids.BRANCH_NEW_WP,
                    label="Work package",
                    data=work_packages,
                    searchable=True,
                    clearable=True,
                    placeholder="Optional",
                ),
                html.Div(id=ids.BRANCH_NEW_FEEDBACK),
                dmc.Group(
                    [
                        dmc.Button(
                            "Create and switch", id=ids.BRANCH_NEW_SAVE, leftSection=icon("tabler:git-branch")
                        )
                    ],
                    justify="flex-end",
                ),
            ]
        ),
    )


def shell(
    title: str,
    pack_name: str,
    branch_options: list[dict[str, str]],
    current: str = MAIN,
    changes: int | None = None,
    work_packages: list[dict[str, str]] | None = None,
    role: str = "admin",
    display_name: str = "",
    persona: str | None = None,
    can_create_branch: bool = True,
) -> dmc.MantineProvider:
    """`persona` is the debug persona to show in the switcher, or None on the platform (no switcher)."""
    return dmc.MantineProvider(
        theme=THEME,
        defaultColorScheme="light",
        children=[
            dcc.Location(id=ids.URL, refresh=False),
            dcc.Store(id=ids.NAV_VERSION, data=0),
            dcc.Store(id=ids.NAVBAR_OPEN, data=False),
            dcc.Download(id=ids.DOWNLOAD),
            dmc.NotificationContainer(id=ids.NOTIFY, position="top-right"),
            new_branch_modal(work_packages or []),
            dmc.AppShell(
                [
                    dmc.AppShellHeader(
                        dmc.Group(
                            [
                                html.Div(
                                    [
                                        dmc.Burger(
                                            id=ids.NAV_BURGER,
                                            opened=False,
                                            hiddenFrom="sm",
                                            size="sm",
                                        ),
                                        html.Div(
                                            icon("tabler:topology-star-3", 20), className="ea-brand-mark"
                                        ),
                                        dmc.Stack(
                                            [
                                                dmc.Title(title, order=4, style={"lineHeight": 1.1}),
                                                dmc.Text(
                                                    "model first · agent ready · DuckDB now, Databricks next",
                                                    size="xs",
                                                    c="dimmed",
                                                ),
                                            ],
                                            gap=0,
                                        ),
                                    ],
                                    className="ea-brand",
                                ),
                                dmc.Group(
                                    [
                                        html.Div(branch_badge(current, changes), id=ids.BRANCH_BADGE),
                                        dmc.Select(
                                            id=ids.BRANCH_SELECT,
                                            data=branch_options,
                                            value=current,
                                            w=240,
                                            size="sm",
                                            allowDeselect=False,
                                            leftSection=icon("tabler:git-branch", 14),
                                            comboboxProps={"withinPortal": True},
                                        ),
                                        dmc.Tooltip(
                                            dmc.ActionIcon(
                                                icon("tabler:plus", 16),
                                                id=ids.BRANCH_NEW_OPEN,
                                                variant="light",
                                                size="lg",
                                                disabled=not can_create_branch,
                                            ),
                                            label="New branch from main"
                                            if can_create_branch
                                            else "Your role may not create branches",
                                        ),
                                        html.Div(role_badge(role, display_name), id=ids.ROLE_BADGE),
                                        persona_switcher(persona) if persona else None,
                                        dmc.Badge(pack_name, variant="light", color="indigo", size="lg"),
                                    ],
                                    className="ea-header-controls",
                                    gap="xs",
                                ),
                            ],
                            className="ea-header-inner",
                            justify="space-between",
                            px="md",
                        )
                    ),
                    dmc.AppShellNavbar(
                        dmc.Stack(
                            [
                                item
                                for section, links in NAV_SECTIONS
                                for item in [
                                    dmc.Text(
                                        section, size="xs", fw=700, c="dimmed", className="ea-nav-section"
                                    ),
                                    *[
                                        dmc.NavLink(
                                            label=label,
                                            href=href,
                                            leftSection=icon(ic, 18),
                                            id=f"nav-{href.strip('/') or 'home'}",
                                            variant="light",
                                        )
                                        for label, href, ic in links
                                    ],
                                ]
                            ]
                            + [
                                dmc.Divider(my="sm"),
                                dmc.Text(
                                    "A generic, metamodel-driven EA repository. Local DuckDB now, Databricks next.",
                                    size="xs",
                                    c="dimmed",
                                    px="sm",
                                ),
                            ],
                            gap=2,
                            p="xs",
                        )
                    ),
                    dmc.AppShellMain(
                        html.Div(id=ids.PAGE, style={"padding": "1rem 1.5rem", "width": "100%"})
                    ),
                ],
                id=ids.APP_SHELL,
                header={"height": {"base": 204, "sm": 132, "xl": 56}},
                navbar={"width": 220, "breakpoint": "sm", "collapsed": {"mobile": True}},
                padding="md",
            ),
        ],
    )
