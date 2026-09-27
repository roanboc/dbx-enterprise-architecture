"""Guide: getting started, the help of every screen, and how to work in the repository by
role (initiatives 24 and 27).

The pages come from `docs/guide/` and each screen's help from `docs/guide/screens/`, the same
text the side panel beside a screen's title draws; the element types the organisation's
metamodel places on each side of the enterprise level are read from the metamodel as the
page is drawn."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from ea.services.guide import BOUNDARY_MARK, Boundary, GuideSection, GuideService, ScreenHelp, slug
from ea.ui import ids, layout
from ea.ui.components import empty, icon, markdown, page_title
from ea.ui.context import AppContext
from ea.ui.screen_help import demote
from ea.views.mermaid import LAYER_SWATCH, LAYER_TITLES

#: Anchors other screens link to by name, kept as they are.
KEPT_ANCHORS = {"the-boundary"}


def _markdown(text: str, section: str) -> list:
    """Markdown with an anchor before each second-level heading, so a link can land on it, and
    its diagrams drawn. An anchor carries its section's name, so two role pages that both say
    *How you work* do not give the page two elements with one id."""
    parts: list = []
    chunk: list[str] = []

    def flush() -> None:
        if "".join(chunk).strip():
            parts.append(markdown("".join(chunk), f"guide-{section}-{len(parts)}"))
        chunk.clear()

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            flush()
            anchor = slug(line[3:])
            parts.append(
                html.Span(
                    id=anchor if anchor in KEPT_ANCHORS else f"{section}-{anchor}", className="ea-anchor"
                )
            )
        chunk.append(line)
    flush()
    return parts


def _boundary(b: Boundary, metamodel: str):
    """The types on each side of the line, in this organisation's metamodel."""

    def side(title: str, groups: list[tuple[str, list[str]]], none: str):
        rows = [
            html.Tr(
                [
                    html.Td(f"{LAYER_SWATCH.get(layer, '⬜')} {LAYER_TITLES.get(layer, layer)}"),
                    html.Td(", ".join(names)),
                ]
            )
            for layer, names in groups
        ]
        return html.Div(
            [
                dmc.Text(title, fw=600, size="sm", mb=4),
                html.Table(html.Tbody(rows), className="ea-doc") if rows else dmc.Text(none, size="sm"),
            ]
        )

    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Text(f"In this organisation's metamodel — {metamodel}", size="xs", c="dimmed"),
                side("At the enterprise level", b.enterprise, "No type."),
                side(
                    "Below it: linked from the system, not modelled",
                    b.solution,
                    "No type is placed below the enterprise level. The assistant finds a system's "
                    "inside by its relationships: a new element that relates only to its own system.",
                ),
            ],
            gap="sm",
        ),
        p="md",
        withBorder=True,
        className="ea-card",
        my="sm",
    )


def _section(s: GuideSection, boundary) -> dmc.Paper:
    body: list = []
    for n, part in enumerate(s.markdown.split(BOUNDARY_MARK)):
        if n:
            body.append(boundary)
        body.extend(_markdown(part, s.slug))
    return dmc.Paper(
        [html.Span(id=s.slug, className="ea-anchor"), dmc.Title(s.title, order=2, mb="xs"), *body],
        p="lg",
        withBorder=True,
        className="ea-card ea-guide-persona",
    )


def screen_order(screens: dict[str, ScreenHelp]) -> list[tuple[str, list[ScreenHelp]]]:
    """The screens' help in the navigation's order and groups; the Element page after Browse,
    which leads to it; a page no navigation entry names, last."""
    placed: set[str] = set()
    out: list[tuple[str, list[ScreenHelp]]] = []
    for section, links in layout.NAV_SECTIONS:
        group: list[ScreenHelp] = []
        for _, href, _ in links:
            key = href.strip("/") or "home"
            for k in (key, "element") if key == "browse" else (key,):
                if k in screens and k not in placed:
                    group.append(screens[k])
                    placed.add(k)
        if group:
            out.append((section, group))
    rest = [h for k, h in screens.items() if k not in placed]
    if rest:
        out.append(("Other screens", rest))
    return out


def _screens(groups: list[tuple[str, list[ScreenHelp]]]) -> dmc.Paper:
    blocks: list = [
        html.Span(id="the-screens", className="ea-anchor"),
        dmc.Title("The screens", order=2, mb="xs"),
        dmc.Text(
            "What each screen is for and how it is used: the same help its button opens beside the "
            "screen's title.",
            size="sm",
            c="dimmed",
        ),
    ]
    for section, helps in groups:
        blocks.append(dmc.Text(section, size="xs", fw=700, c="dimmed", tt="uppercase", mt="md"))
        for h in helps:
            blocks.append(
                html.Div(
                    [
                        html.Span(id=f"screen-{h.key}", className="ea-anchor"),
                        dmc.Title(h.title, order=3, size="h4"),
                        dmc.Text(h.tip, size="sm", fw=500),
                        markdown(demote(h.markdown, 2), f"guide-screen-{h.key}"),
                    ],
                    className="ea-guide-screen",
                )
            )
    return dmc.Paper(blocks, p="lg", withBorder=True, className="ea-card ea-guide-persona")


def _link(title: str, anchor: str) -> html.A:
    """A link to a section of this page, left to the browser: it scrolls to the section itself.

    A Mantine anchor takes the click, changes the address and puts the page back at its top,
    which on a page this long left the reader where they were."""
    return html.A(title, href=f"#{anchor}", className="mantine-focus-auto ea-guide-link")


def _contents(start: list[GuideSection], groups, roles: list[GuideSection]) -> dmc.Paper:
    def column(title: str, links: list) -> dmc.Stack:
        return dmc.Stack([dmc.Text(title, size="xs", fw=700, c="dimmed", tt="uppercase"), *links], gap=2)

    screens = [_link(h.title, f"screen-{h.key}") for _, helps in groups for h in helps]
    return dmc.Paper(
        dmc.Stack(
            [
                html.Div(
                    [
                        column("Start here", [_link(s.title, s.slug) for s in start]),
                        column("The screens", screens),
                        column("By role", [_link(s.title, s.slug) for s in roles]),
                    ],
                    className="ea-guide-contents",
                ),
                dmc.Group(
                    [
                        dmc.Button(
                            "Show the welcome and tips again",
                            id={"type": ids.HELP_ACTION, "action": "reset"},
                            size="xs",
                            variant="light",
                            leftSection=icon("tabler:bulb", 14),
                        ),
                        dmc.Text(
                            "Each screen's help is also one click away: the button at its top right, or the ? key.",
                            size="xs",
                            c="dimmed",
                        ),
                    ],
                    gap="sm",
                ),
            ],
            gap="md",
        ),
        p="md",
        withBorder=True,
        className="ea-card",
        mb="md",
    )


def render(ctx: AppContext) -> html.Div:
    guide = GuideService(ctx.registry)
    sections = guide.sections()
    if not sections:
        return html.Div(
            [page_title("Guide", help="guide"), empty("The guide's pages are not installed with this copy.")]
        )
    boundary = _boundary(guide.boundary(), ctx.registry.pack.name)
    start = [s for s in sections if s.slug == "getting-started"]
    roles = [s for s in sections if s.slug != "getting-started"]
    groups = screen_order(guide.screens())
    blocks = [_section(s, boundary) for s in start]
    if groups:
        blocks.append(_screens(groups))
    blocks += [_section(s, boundary) for s in roles]
    return html.Div(
        [
            page_title(
                "Guide",
                "Getting started, what each screen is for and how it is used, and how each role works "
                "in the repository.",
                help="guide",
            ),
            _contents(start, groups, roles),
            dmc.Stack(blocks, gap="md"),
        ],
        className="ea-guide",
    )
