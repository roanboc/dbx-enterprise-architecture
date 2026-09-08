"""Health: freshness per source system and completeness per element type, every figure a link to its rows."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import dash
import dash_mantine_components as dmc
from dash import Input, Output, html, no_update

from ea.services.health import COMPLETENESS_FACETS, STALE_DAYS
from ea.ui import ids
from ea.ui.components import domain_colour, icon, page_title
from ea.ui.context import AppContext, get_context

FACET_TITLES = {
    "description": "Description",
    "links": "Link",
    "relationships": "Relationship",
    "attributes": "Required attributes",
    "target": "Target decided",
}


def _pct_cell(pct: int, missing: int, href: str | None):
    colour = "green" if pct >= 90 else "yellow" if pct >= 60 else "red"
    bar = dmc.Progress(value=pct, color=colour, size="sm", w=90)
    label = (
        dmc.Anchor(f"{missing} missing", href=href, size="xs")
        if missing and href
        else dmc.Text("complete", size="xs", c="dimmed")
    )
    return dmc.Stack([dmc.Group([bar, dmc.Text(f"{pct}%", size="xs", w=36)], gap="xs"), label], gap=2)


def _count_link(n: int, href: str, colour: str = "orange"):
    if not n:
        return dmc.Text("0", size="sm", c="dimmed")
    return dmc.Anchor(dmc.Badge(str(n), color=colour, variant="light"), href=href, underline="never")


def _freshness(ctx: AppContext) -> html.Div:
    fresh = ctx.health.freshness()
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh(h) for h in ("source", "elements", "relationships", "first loaded", "last updated")]
            + [dmc.TableTh(f"stale {d} d") for d in STALE_DAYS]
            + [dmc.TableTh("never updated")]
        )
    )
    body = []
    for r in fresh["sources"]:
        src = r["source"]
        # Every row carries its source into the link, `(authored)` included: without it the
        # figure for the rows nobody imported opened the rows everybody did.
        q = f"&source={quote(src)}"
        body.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(src, fw=500, size="sm")),
                    dmc.TableTd(str(r["elements"])),
                    dmc.TableTd(str(r["relationships"])),
                    dmc.TableTd(dmc.Text(r["first_loaded"], size="xs", c="dimmed")),
                    dmc.TableTd(dmc.Text(r["last_updated"], size="xs")),
                ]
                + [
                    dmc.TableTd(
                        _count_link(
                            r[f"stale_{d}"],
                            f"/browse?missing=stale&days={d}{q}",
                            "orange" if d < 180 else "red",
                        )
                    )
                    for d in STALE_DAYS
                ]
                + [dmc.TableTd(_count_link(r["never_updated"], f"/browse?missing=never_updated{q}", "gray"))]
            )
        )
    weeks = fresh["activity"]
    peak = max((w["total"] for w in weeks), default=0) or 1
    bars = dmc.Group(
        [
            dmc.Tooltip(
                dmc.Stack(
                    [
                        html.Div(
                            style={
                                "height": f"{max(4, int(60 * w['total'] / peak))}px",
                                "width": "22px",
                                "background": "#4c6ef5" if w["total"] else "#e9ecef",
                                "borderRadius": "3px",
                                "alignSelf": "flex-end",
                            }
                        ),
                        dmc.Text(w["week"][-3:], size="xs", c="dimmed"),
                    ],
                    gap=2,
                    align="center",
                    justify="flex-end",
                    h=84,
                ),
                label=f"{w['week']}: {w['total']} change(s) "
                + ", ".join(f"{k} {v}" for k, v in w["by_op"].items()),
            )
            for w in weeks
        ],
        gap=6,
        align="flex-end",
    )
    return html.Div(
        [
            dmc.Text(f"Freshness · as of {fresh['as_of']}", className="ea-section-title"),
            dmc.Text(
                "Per source system: when it was first loaded, when any of its rows last moved, how many rows have not "
                "been updated for 30, 90 and 180 days, and how many were never touched since the import. A number opens the rows.",
                size="xs",
                c="dimmed",
                mb="xs",
            ),
            dmc.TableScrollContainer(
                dmc.Table(
                    [head, dmc.TableTbody(body)],
                    withTableBorder=True,
                    striped=True,
                    verticalSpacing="xs",
                    fz="sm",
                ),
                minWidth=560,
            ),
            dmc.Text("Change activity, last 12 weeks", className="ea-section-title", mt="md"),
            dmc.Text(
                "Change-log entries per week on this branch, every kind of write counted.",
                size="xs",
                c="dimmed",
                mb="xs",
            ),
            bars,
        ]
    )


def _completeness(ctx: AppContext) -> html.Div:
    comp = ctx.health.completeness()
    head = dmc.TableThead(
        dmc.TableTr(
            [dmc.TableTh("type"), dmc.TableTh("elements")]
            + [dmc.TableTh(FACET_TITLES[f]) for f in COMPLETENESS_FACETS]
        )
    )
    body = []
    for r in comp["types"]:
        cells: list[Any] = [
            dmc.TableTd(
                dmc.Group(
                    [
                        dmc.Anchor(r["type"], href=f"/browse?type={r['type_id']}", size="sm", fw=500),
                        dmc.Badge(
                            r["domain"],
                            size="xs",
                            variant="light",
                            color=domain_colour(ctx.registry, r["domain"]),
                        ),
                    ],
                    gap="xs",
                )
            ),
            dmc.TableTd(str(r["elements"])),
        ]
        for f in COMPLETENESS_FACETS:
            href = f"/browse?type={r['type_id']}&missing={f}" if r[f"{f}_missing"] else None
            cells.append(dmc.TableTd(_pct_cell(r[f"{f}_pct"], r[f"{f}_missing"], href)))
        body.append(dmc.TableTr(cells))
    totals = comp["missing"]
    empty_rels = ctx.health.relationship_coverage()
    return html.Div(
        [
            dmc.Text(f"Completeness · {comp['elements']} elements", className="ea-section-title"),
            dmc.Group(
                [
                    dmc.Badge(
                        f"{totals[f]} {FACET_TITLES[f].lower()} missing",
                        color="orange" if totals[f] else "green",
                        variant="light",
                    )
                    for f in COMPLETENESS_FACETS
                ],
                gap="xs",
                mb="xs",
            ),
            dmc.Text(
                "Per element type: the share with a description, at least one link, at least one relationship, every "
                "required attribute filled, and a decided target state. A count opens the rows that lack it.",
                size="xs",
                c="dimmed",
                mb="xs",
            ),
            dmc.TableScrollContainer(
                dmc.Table(
                    [head, dmc.TableTbody(body)],
                    withTableBorder=True,
                    striped=True,
                    verticalSpacing="xs",
                    fz="sm",
                ),
                minWidth=560,
            ),
            dmc.Text(
                f"Relationship types with no instance ({len(empty_rels)})",
                className="ea-section-title",
                mt="md",
            ),
            dmc.Text(
                "Declared in the metamodel, never used in the content. Either the content is incomplete or the type is unused.",
                size="xs",
                c="dimmed",
                mb="xs",
            ),
            dmc.Group(
                [
                    dmc.Badge(
                        f"{e['name']} ({e['source']} → {e['target']})",
                        variant="outline",
                        color="gray",
                        size="sm",
                    )
                    for e in empty_rels[:60]
                ],
                gap=4,
            )
            if empty_rels
            else dmc.Text("Every relationship type has at least one instance.", size="sm", c="dimmed"),
        ]
    )


def body(ctx: AppContext) -> html.Div:
    return html.Div(
        [
            dmc.Paper(_freshness(ctx), p="md", withBorder=True, className="ea-card", mb="md"),
            dmc.Paper(_completeness(ctx), p="md", withBorder=True, className="ea-card"),
        ]
    )


def render(ctx: AppContext) -> html.Div:
    return html.Div(
        [
            page_title(
                "Health",
                f"How fresh and how complete the model is on {ctx.branch()}. Every number is a link to the rows behind it, where a steward can search, open or bulk-edit them.",
                dmc.Button(
                    "Recompute", id=ids.HEALTH_REFRESH, variant="light", leftSection=icon("tabler:refresh")
                ),
            ),
            html.Div(body(ctx), id=ids.HEALTH_BODY),
        ]
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.HEALTH_BODY, "children"), Input(ids.HEALTH_REFRESH, "n_clicks"), prevent_initial_call=True
    )
    def refresh(n):
        return body(get_context()) if n else no_update
