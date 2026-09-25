"""Guide: what the repository is for and how to work in it, by role — conceptual and
procedural, not a manual of the screens (initiative 24).

The pages come from `docs/guide/`; the element types the organisation's metamodel places on
each side of the enterprise level are read from the metamodel as the page is drawn."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from ea.services.guide import BOUNDARY_MARK, Boundary, GuideService, slug
from ea.ui.components import empty, page_title
from ea.ui.context import AppContext
from ea.views.mermaid import LAYER_SWATCH, LAYER_TITLES


def _markdown(text: str) -> list:
    """Markdown with an anchor before each second-level heading, so a link can land on it."""
    parts: list = []
    chunk: list[str] = []

    def flush() -> None:
        if "".join(chunk).strip():
            parts.append(dcc.Markdown("".join(chunk), className="ea-doc"))
        chunk.clear()

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            flush()
            parts.append(html.Span(id=slug(line[3:]), className="ea-anchor"))
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


def render(ctx: AppContext) -> html.Div:
    guide = GuideService(ctx.registry)
    sections = guide.sections()
    if not sections:
        return html.Div([page_title("Guide"), empty("The guide's pages are not installed with this copy.")])
    boundary = _boundary(guide.boundary(), ctx.registry.pack.name)
    blocks = []
    for s in sections:
        body: list = []
        for n, part in enumerate(s.markdown.split(BOUNDARY_MARK)):
            if n:
                body.append(boundary)
            body.extend(_markdown(part))
        blocks.append(
            dmc.Paper(
                [html.Span(id=s.slug, className="ea-anchor"), dmc.Title(s.title, order=2, mb="xs"), *body],
                p="lg",
                withBorder=True,
                className="ea-card ea-guide-persona",
            )
        )
    return html.Div(
        [
            page_title(
                "Guide",
                "What the repository is for and how to work in it, for each role that uses it. "
                "It says what to do and why, not which button to press.",
            ),
            dmc.Group(
                [dmc.Anchor(s.title, href=f"#{s.slug}", size="sm") for s in sections],
                gap="md",
                mb="md",
            ),
            dmc.Stack(blocks, gap="md"),
        ]
    )
