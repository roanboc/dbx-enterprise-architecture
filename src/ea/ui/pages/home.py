"""Home: what is loaded, by type and by domain."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from ea.ui.components import domain_colour, icon, page_title, simple_table
from ea.ui.context import AppContext


def _stat(label: str, value: str | int, ic: str) -> dmc.Paper:
    """One figure, its icon and what it counts.

    The row does not wrap and the tile does not shrink to its content: with a wrapping row
    a two-line label pushed the figure underneath its own icon, so the six tiles read as
    two different designs and no two figures sat on the same line.
    """
    return dmc.Paper(
        dmc.Group(
            [
                dmc.ThemeIcon(icon(ic, 22), size=44, radius="md", variant="light", color="indigo"),
                dmc.Stack(
                    [dmc.Text(str(value), fw=700, fz=26, lh=1), dmc.Text(label, size="sm", c="dimmed")], gap=2
                ),
            ],
            gap="md",
            wrap="nowrap",
            align="flex-start",
        ),
        p="md",
        withBorder=True,
        radius="md",
        h="100%",
    )


def render(ctx: AppContext) -> html.Div:
    s = ctx.repo.stats()
    reg = ctx.registry
    populated = [r for r in s["by_type"] if r["count"]]
    rel_rows = sorted([r for r in s["by_rel_type"] if r["count"]], key=lambda r: -r["count"])[:15]
    type_rows = []
    for r in sorted(populated, key=lambda r: -r["count"]):
        type_rows.append(
            [
                dmc.Anchor(r["name"], href=f"/browse?type={r['type_id']}", size="sm", fw=500),
                dmc.Badge(
                    reg.domains[r["domain"]].name if r["domain"] in reg.domains else r["domain"],
                    color=domain_colour(ctx.registry, r["domain"]),
                    variant="light",
                    size="xs",
                ),
                r["count"],
                "" if r["active"] else dmc.Badge("inactive", color="gray", size="xs"),
            ]
        )
    return html.Div(
        [
            page_title(
                f"{reg.pack.name}",
                f"Pack `{reg.pack.id}` version {reg.pack.version}. Everything below is derived from the metamodel and the content loaded into it.",
            ),
            dmc.SimpleGrid(
                [
                    _stat("elements", s["elements"], "tabler:box"),
                    _stat("relationships", s["relationships"], "tabler:arrows-exchange"),
                    _stat("element types with content", len(populated), "tabler:category"),
                    _stat(
                        "relationship types with content",
                        len([r for r in s["by_rel_type"] if r["count"]]),
                        "tabler:vector-triangle",
                    ),
                    _stat("open branches", len(ctx.branches.open()), "tabler:git-branch"),
                    _stat("elements that change", ctx.target.summary()["changes"], "tabler:target-arrow"),
                ],
                cols={"base": 2, "md": 3, "lg": 6},
                spacing="md",
                mb="lg",
            ),
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        [
                            dmc.Title("Elements by type", order=2, size="h4"),
                            simple_table(["type", "domain", "count", "status"], type_rows)
                            if type_rows
                            else dmc.Text(
                                "Nothing loaded yet — use Import, or `make seed`.", c="dimmed", size="sm"
                            ),
                        ],
                        p="md",
                        withBorder=True,
                        radius="md",
                    ),
                    dmc.Paper(
                        [
                            dmc.Title("Most used relationships", order=2, size="h4"),
                            simple_table(
                                ["relationship", "from", "to", "count"],
                                [
                                    [
                                        r["name"],
                                        reg.types[r["source"]].name
                                        if r["source"] in reg.types
                                        else r["source"],
                                        reg.types[r["target"]].name
                                        if r["target"] in reg.types
                                        else r["target"],
                                        r["count"],
                                    ]
                                    for r in rel_rows
                                ],
                            )
                            if rel_rows
                            else dmc.Text("No relationships yet.", c="dimmed", size="sm"),
                        ],
                        p="md",
                        withBorder=True,
                        radius="md",
                    ),
                ],
                cols={"base": 1, "lg": 2},
                spacing="md",
            ),
        ]
    )
