"""The deep dives kept (initiative 25, ASVC14): the catalogue, on Ask's deep mode.

A deep dive is listed by what it is catalogued under — its kind, the domains and element types
of its subject, the work package it concerns — and by how the people who read it rated it, drawn
as stars. The catalogue opens one; whoever may read may rate it, one to five stars with a line of
why, one rating per person, and may clear their own; its author or an admin may withdraw it,
which keeps its row; anyone may run it again, which keeps a new one that names the one it came
from; and its pack downloads as one ZIP. It is a tab of Ask's deep mode rather than a page of its
own, so its address is Ask's: `/ask?mode=deep&tab=kept&open=<id>`. Every element a deep dive
cites lists it on its own page.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.agent.deep_dive import KINDS
from ea.models import DeepDive, Forbidden, NotFoundError
from ea.ui import ids
from ea.ui.components import alert, element_href, icon, simple_table
from ea.ui.context import AppContext, get_context
from ea.views.deep_dive_layout import pack_filename
from ea.views.deep_dive_pack import build_pack

PAGE = 50
SEVERITY_COLOUR = {"high": "red", "medium": "orange", "low": "blue"}
CONFIDENCE_COLOUR = {"high": "green", "medium": "yellow", "low": "red"}
RATING_OPTIONS = [
    {"value": "", "label": "Any rating"},
    {"value": "3", "label": "3 stars or more"},
    {"value": "4", "label": "4 stars or more"},
    {"value": "5", "label": "5 stars"},
]
#: Where the catalogue lives: a tab of Ask's deep mode.
KEPT = "/ask"
KEPT_TAB = {"mode": "deep", "tab": "kept"}


# ------------------------------------------------------------------ the logic
def narrow_from_search(search: str | None) -> dict[str, Any]:
    """What the address narrows the catalogue to, and the deep dive it opens."""
    q = parse_qs((search or "").lstrip("?"))

    def one(key: str) -> str:
        return (q.get(key) or [""])[0].strip()

    try:
        rating = int(one("min_rating")) if one("min_rating") else None
    except ValueError:
        rating = None
    return {
        "text": one("text"),
        "kind": one("kind") if one("kind") in KINDS else "",
        "domain_id": one("domain"),
        "type_id": one("type"),
        "work_package": one("wp"),
        "element_id": one("element"),
        "min_rating": rating if rating in (1, 2, 3, 4, 5) else None,
        "include_withdrawn": one("withdrawn") in ("1", "true", "yes"),
        "open": one("open"),
    }


def search_of(narrow: dict[str, Any], open_id: str = "") -> str:
    """The address on Ask that narrows the catalogue so and opens `open_id`."""
    params = {
        **KEPT_TAB,
        "text": narrow.get("text") or "",
        "kind": narrow.get("kind") or "",
        "domain": narrow.get("domain_id") or "",
        "type": narrow.get("type_id") or "",
        "wp": narrow.get("work_package") or "",
        "element": narrow.get("element_id") or "",
        "min_rating": str(narrow.get("min_rating") or ""),
        "withdrawn": "1" if narrow.get("include_withdrawn") else "",
        "open": open_id,
    }
    return "?" + urlencode({k: v for k, v in params.items() if v})


def href_of(deep_dive_id: str) -> str:
    """Where a deep dive is opened from anywhere in the application."""
    return f"{KEPT}{search_of({}, deep_dive_id)}"


def catalogue_rows(ctx: AppContext, narrow: dict[str, Any]) -> tuple[list[DeepDive], int]:
    return ctx.deep_dives.catalogue(
        kind=narrow.get("kind") or None,
        domain_id=narrow.get("domain_id") or None,
        type_id=narrow.get("type_id") or None,
        work_package=narrow.get("work_package") or None,
        element_id=narrow.get("element_id") or None,
        text=narrow.get("text") or None,
        min_rating=narrow.get("min_rating"),
        include_withdrawn=bool(narrow.get("include_withdrawn")),
        limit=PAGE,
        offset=0,
    )


def can_withdraw(ctx: AppContext, d: DeepDive) -> bool:
    return (
        d.status == "kept"
        and ctx.can("withdraw_deep_dive")
        and (ctx.role() == "admin" or d.created_by == ctx.actor)
    )


def rate(ctx: AppContext, deep_dive_id: str, stars: Any, why: str = "") -> tuple[bool, str]:
    try:
        stars = int(stars or 0)
    except (TypeError, ValueError):
        stars = 0
    if not 1 <= stars <= 5:
        return False, "Pick one to five stars first."
    try:
        ctx.deep_dives.rate(deep_dive_id, ctx.actor, stars, why)
    except (Forbidden, ValueError, NotFoundError) as exc:
        return False, str(exc)
    return True, f"Rated {stars} of 5. One rating per person: yours replaces any you gave before."


def clear_rating(ctx: AppContext, deep_dive_id: str) -> tuple[bool, str]:
    try:
        cleared = ctx.deep_dives.clear_rating(deep_dive_id, ctx.actor)
    except Forbidden as exc:
        return False, str(exc)
    if not cleared:
        return False, "You have given no rating to clear."
    return True, "Your rating is cleared; you may rate it again at any time."


def withdraw(ctx: AppContext, deep_dive_id: str) -> tuple[bool, str]:
    try:
        ctx.deep_dives.withdraw(deep_dive_id, ctx.actor)
    except (Forbidden, NotFoundError) as exc:
        return False, str(exc)
    return True, "Withdrawn: it leaves the catalogue and is not weighed again. Its row is kept."


def run_again(ctx: AppContext, deep_dive_id: str) -> DeepDive:
    """A new deep dive from the same brief, on the model as it is now; it names the one it came from."""
    source = ctx.deep_dives.get(deep_dive_id)
    if source is None:
        raise NotFoundError(deep_dive_id, "deep dive")
    a = ctx.analyst
    return ctx.deep_dives.keep(a.analyse(a.again(source)), ctx.actor)


def pack(ctx: AppContext, deep_dive_id: str) -> tuple[str, bytes]:
    """(file name, ZIP) of a kept deep dive: its PDF and its diagrams as draw.io files."""
    d = ctx.deep_dives.get(deep_dive_id)
    if d is None:
        raise NotFoundError(deep_dive_id, "deep dive")
    data = build_pack(
        d, org_name=ctx.organisation().name, pack_name=ctx.registry.pack.name, base_url=ctx.base_url()
    )
    return pack_filename(d), data


# ------------------------------------------------------------------ the parts
def stars(value: float | None, count: int = 0, size: str = "sm"):
    """A rating as stars, read-only, with how many rated it; 'not rated yet' when nobody has."""
    if not count:
        return dmc.Text("not rated yet", size="xs", c="dimmed")
    return dmc.Group(
        [
            dmc.Rating(value=float(value or 0), fractions=2, readOnly=True, size=size, count=5),
            dmc.Text(f"({count})", size="xs", c="dimmed"),
        ],
        gap=4,
        wrap="nowrap",
    )


def _kind(kind: str) -> str:
    return KINDS.get(kind, {}).get("label", kind)


def _subject(d: DeepDive) -> str:
    """What a deep dive is about, from its brief: a catalogue row carries no element roles."""
    brief = d.brief or {}
    return ", ".join(brief.get("subject") or []) or brief.get("work_package") or d.work_package or ""


def catalogue_table(ctx: AppContext, dives: list[DeepDive], narrow: dict[str, Any] | None = None):
    if not dives:
        return dmc.Text("No deep dive matches. Start one on the New deep dive tab.", c="dimmed", size="sm")
    narrow = narrow or {}
    rows = []
    for d in dives:
        rows.append(
            [
                dmc.Anchor(d.title, href=f"{KEPT}{search_of(narrow, d.deep_dive_id)}", size="sm"),
                _kind(d.kind),
                _subject(d),
                d.created_by,
                str(d.created_at or "")[:10],
                stars(d.rating_average, d.rating_count, "xs"),
                dmc.Badge("withdrawn", color="gray", size="xs") if d.status == "withdrawn" else "",
            ]
        )
    return simple_table(["Deep dive", "Kind", "About", "By", "When", "Rating", ""], rows)


def _work(c: dict[str, Any]):
    work = c.get("work_packages") or []
    if not work:
        return None
    return dmc.Stack(
        [
            dmc.Text("Work in flight", fw=600, size="sm"),
            dmc.Text("Work packages planned or under way that change what it read.", size="xs", c="dimmed"),
            *[
                dmc.Group(
                    [
                        dmc.Anchor(
                            f"{w['name']} [{w['element_id']}]", href=element_href(w["element_id"]), size="sm"
                        ),
                        dmc.Badge(
                            w["current_state"].replace("_", " "), color="grape", variant="light", size="xs"
                        ),
                        dmc.Text(f"changes {len(w['elements'])} element(s) it read", size="xs", c="dimmed"),
                    ],
                    gap="xs",
                )
                for w in work
            ],
        ],
        gap=4,
    )


def _rating_panel(ctx: AppContext, d: DeepDive, ratings: list) -> Any:
    mine = next((r for r in ratings if r.rated_by == ctx.actor), None)
    may = ctx.can("rate_deep_dive") and d.status == "kept"
    return dmc.Stack(
        [
            dmc.Group(
                [dmc.Text("Your rating", fw=600, size="sm"), stars(d.rating_average, d.rating_count)],
                justify="space-between",
            ),
            dmc.Text(
                "One to five stars for how far you would trust it and how useful it was — one rating per "
                "person; the next deep dive on these elements weighs it by its rating.",
                size="xs",
                c="dimmed",
            ),
            dmc.Group(
                [
                    dmc.Rating(
                        id=ids.DD_STARS, value=mine.stars if mine else 0, count=5, size="lg", readOnly=not may
                    ),
                    dmc.TextInput(
                        id=ids.DD_WHY,
                        placeholder="A line of why",
                        value=mine.comment if mine else "",
                        w=300,
                        disabled=not may,
                        **{"aria-label": "Why you rate it so"},
                    ),
                ],
                gap="sm",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Change my rating" if mine else "Rate it",
                        id=ids.DD_RATE,
                        size="compact-sm",
                        leftSection=icon("tabler:star", 14),
                        disabled=not may,
                    ),
                    # always rendered, so the rating callback always fires: a callback whose
                    # input is missing from the page never runs; hidden while there is none
                    dmc.Button(
                        "Clear my rating",
                        id=ids.DD_UNRATE,
                        size="compact-sm",
                        variant="subtle",
                        color="gray",
                        leftSection=icon("tabler:trash", 14),
                        style={} if mine else {"display": "none"},
                    ),
                ],
                gap="sm",
            ),
            dmc.Stack(
                [
                    dmc.Group(
                        [
                            dmc.Rating(value=r.stars, readOnly=True, size="xs", count=5),
                            dmc.Text(r.rated_by + (f" — {r.comment}" if r.comment else ""), size="xs"),
                        ],
                        gap="xs",
                        wrap="nowrap",
                    )
                    for r in ratings
                ],
                gap=2,
            )
            if ratings
            else None,
        ],
        gap=6,
    )


def detail_panel(ctx: AppContext, d: DeepDive | None, feedback: Any = None):
    """One deep dive opened: what it found, the work in flight, how it was rated, and what may be done with it."""
    if d is None:
        return dmc.Paper(
            dmc.Text("Open a deep dive from the list to read it here.", c="dimmed", size="sm"),
            p="md",
            withBorder=True,
        )
    c = d.content or {}
    conf = c.get("confidence") or {}
    findings = c.get("findings") or []
    ratings = ctx.deep_dives.ratings(d.deep_dive_id)
    subject = [e.element_id for e in d.elements if e.role == "subject"]
    return dmc.Paper(
        dmc.Stack(
            [
                html.Div(feedback, id=ids.DD_FEEDBACK),
                dmc.Group(
                    [
                        dmc.Title(d.title, order=2, size="h3"),
                        dmc.Badge("withdrawn", color="gray") if d.status == "withdrawn" else None,
                    ],
                    justify="space-between",
                    align="flex-start",
                ),
                dmc.Text(
                    f"{_kind(d.kind)} · kept {str(d.created_at or '')[:16]} by {d.created_by} · read on "
                    f"{d.branch_id or 'main'} · metamodel {d.pack_version}",
                    size="xs",
                    c="dimmed",
                ),
                dmc.Text(c.get("brief_sentence", ""), size="sm"),
                dmc.Group([dmc.Anchor(i, href=element_href(i), size="xs") for i in subject], gap="xs")
                if subject
                else None,
                dmc.Group(
                    [
                        dmc.Badge(
                            f"confidence: {conf.get('level', '')}",
                            color=CONFIDENCE_COLOUR.get(conf.get("level"), "gray"),
                            variant="light",
                        ),
                        stars(d.rating_average, d.rating_count),
                    ],
                    gap="sm",
                ),
                dmc.Group(
                    [
                        dmc.Button(
                            "Download the pack",
                            id=ids.DD_PACK,
                            leftSection=icon("tabler:file-zip"),
                            variant="light",
                        ),
                        dmc.Button(
                            "Run again",
                            id=ids.DD_AGAIN,
                            leftSection=icon("tabler:refresh"),
                            variant="light",
                            disabled=not ctx.can("keep_deep_dive"),
                        ),
                        dmc.Button(
                            "Withdraw",
                            id=ids.DD_WITHDRAW,
                            leftSection=icon("tabler:archive"),
                            variant="subtle",
                            color="red",
                        )
                        if can_withdraw(ctx, d)
                        else None,
                    ],
                    gap="sm",
                ),
                dmc.Text(c.get("summary", ""), size="sm"),
                _work(c),
                dmc.Text(f"Findings ({len(findings)})", fw=600, size="sm"),
                dmc.Stack(
                    [
                        dmc.Stack(
                            [
                                dmc.Group(
                                    [
                                        dmc.Badge(
                                            f["severity"],
                                            color=SEVERITY_COLOUR.get(f["severity"], "gray"),
                                            size="xs",
                                        ),
                                        dmc.Text(f"{f['id']} {f['title']}", size="sm", fw=500),
                                    ],
                                    gap="xs",
                                    wrap="nowrap",
                                ),
                                dmc.Text(f["text"], size="xs", c="dimmed"),
                            ],
                            gap=2,
                        )
                        for f in findings
                    ],
                    gap="xs",
                )
                if findings
                else dmc.Text("None.", size="sm", c="dimmed"),
                dmc.Text(
                    f"Where elements and their documentation disagree: {len(c.get('inconsistencies') or [])}; "
                    "the PDF lists each.",
                    size="xs",
                    c="dimmed",
                ),
                dmc.Divider(),
                _rating_panel(ctx, d, ratings),
            ],
            gap="sm",
        ),
        p="md",
        withBorder=True,
        className="ea-card",
    )


def deep_dives_card(ctx: AppContext, element_id: str) -> dmc.Paper:
    """The deep dives that cite an element, best rated first: what its page lists."""
    dives = ctx.deep_dives.on_element(element_id)
    body = (
        dmc.Stack(
            [
                dmc.Stack(
                    [
                        dmc.Anchor(d.title, href=href_of(d.deep_dive_id), size="sm"),
                        dmc.Group(
                            [
                                dmc.Text(
                                    f"{_kind(d.kind)} · {str(d.created_at or '')[:10]}", size="xs", c="dimmed"
                                ),
                                stars(d.rating_average, d.rating_count, "xs"),
                            ],
                            gap="sm",
                        ),
                    ],
                    gap=0,
                )
                for d in dives
            ],
            gap="xs",
        )
        if dives
        else dmc.Group(
            [
                dmc.Text("No deep dive cites this element yet.", c="dimmed", size="sm"),
                dmc.Anchor("Start one", href="/ask?mode=deep", size="sm"),
            ],
            gap="sm",
        )
    )
    return dmc.Paper(
        [
            dmc.Title("Deep dives", order=2, size="h5", mb="xs"),
            dmc.Text("Analyses kept that cite it, best rated first.", size="xs", c="dimmed", mb="xs"),
            body,
        ],
        p="md",
        withBorder=True,
    )


def catalogue(ctx: AppContext, search: str | None = None) -> html.Div:
    """The deep dives kept, as the Kept tab of Ask's deep mode shows them."""
    narrow = narrow_from_search(search)
    dives, total = catalogue_rows(ctx, narrow)
    opened = ctx.deep_dives.get(narrow["open"]) if narrow["open"] else None
    domains = [{"value": d.id, "label": d.name} for d in ctx.registry.pack.domains]
    types = [{"value": t.id, "label": t.name} for t in ctx.registry.concrete_types()]
    return html.Div(
        [
            alert(f"No deep dive {narrow['open']} is kept here.", "yellow")
            if narrow["open"] and opened is None
            else None,
            dmc.Paper(
                dmc.Group(
                    [
                        dmc.TextInput(
                            id=ids.DD_TEXT,
                            label="Title",
                            value=narrow["text"],
                            placeholder="Search titles",
                            w=200,
                        ),
                        dmc.Select(
                            id=ids.DD_KIND,
                            label="Kind",
                            data=[{"value": k, "label": v["label"]} for k, v in KINDS.items()],
                            value=narrow["kind"] or None,
                            clearable=True,
                            w=170,
                        ),
                        dmc.Select(
                            id=ids.DD_DOMAIN,
                            label="Domain",
                            data=domains,
                            value=narrow["domain_id"] or None,
                            clearable=True,
                            searchable=True,
                            w=180,
                        ),
                        dmc.Select(
                            id=ids.DD_TYPE,
                            label="Element type",
                            data=types,
                            value=narrow["type_id"] or None,
                            clearable=True,
                            searchable=True,
                            w=200,
                        ),
                        dmc.Select(
                            id=ids.DD_WP,
                            label="Work package",
                            data=ctx.work_package_options(),
                            value=narrow["work_package"] or None,
                            clearable=True,
                            searchable=True,
                            w=200,
                        ),
                        dmc.TextInput(
                            id=ids.DD_ELEMENT,
                            label="Cites element",
                            value=narrow["element_id"],
                            placeholder="Identifier",
                            w=150,
                        ),
                        dmc.Select(
                            id=ids.DD_RATING,
                            label="Rating",
                            data=RATING_OPTIONS,
                            value=str(narrow["min_rating"] or ""),
                            allowDeselect=False,
                            w=150,
                        ),
                        dmc.Switch(
                            id=ids.DD_WITHDRAWN, label="Show withdrawn", checked=narrow["include_withdrawn"]
                        ),
                    ],
                    gap="sm",
                    align="flex-end",
                ),
                p="md",
                withBorder=True,
                mb="md",
            ),
            dmc.Grid(
                [
                    dmc.GridCol(
                        [
                            dmc.Text(_count(len(dives), total), size="xs", c="dimmed", mb=4, id=ids.DD_COUNT),
                            html.Div(catalogue_table(ctx, dives, narrow), id=ids.DD_LIST),
                        ],
                        span={"base": 12, "lg": 6},
                    ),
                    dmc.GridCol(
                        html.Div(detail_panel(ctx, opened), id=ids.DD_DETAIL), span={"base": 12, "lg": 6}
                    ),
                ],
                gutter="md",
            ),
            dcc.Store(id=ids.DD_OPEN_STORE, data=opened.deep_dive_id if opened else None),
            dcc.Store(id=ids.DD_REFRESH, data=0),
        ]
    )


def _count(shown: int, total: int) -> str:
    return f"{total} deep dive(s)" + (f", the first {shown} shown" if shown < total else "")


def _narrow(text, kind, domain, type_id, wp, element, rating, withdrawn) -> dict[str, Any]:
    return {
        "text": (text or "").strip(),
        "kind": kind or "",
        "domain_id": domain or "",
        "type_id": type_id or "",
        "work_package": wp or "",
        "element_id": (element or "").strip(),
        "min_rating": int(rating) if rating else None,
        "include_withdrawn": bool(withdrawn),
        "open": "",
    }


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.DD_LIST, "children"),
        Output(ids.DD_COUNT, "children"),
        Input(ids.DD_TEXT, "value"),
        Input(ids.DD_KIND, "value"),
        Input(ids.DD_DOMAIN, "value"),
        Input(ids.DD_TYPE, "value"),
        Input(ids.DD_WP, "value"),
        Input(ids.DD_ELEMENT, "value"),
        Input(ids.DD_RATING, "value"),
        Input(ids.DD_WITHDRAWN, "checked"),
        Input(ids.DD_REFRESH, "data"),
        prevent_initial_call=True,
    )
    def narrow_list(text, kind, domain, type_id, wp, element, rating, withdrawn, _refresh):
        ctx = get_context()
        narrow = _narrow(text, kind, domain, type_id, wp, element, rating, withdrawn)
        dives, total = catalogue_rows(ctx, narrow)
        return catalogue_table(ctx, dives, narrow), _count(len(dives), total)

    @app.callback(
        Output(ids.DD_DETAIL, "children"),
        Output(ids.DD_REFRESH, "data"),
        Input(ids.DD_RATE, "n_clicks"),
        Input(ids.DD_UNRATE, "n_clicks"),
        State(ids.DD_STARS, "value"),
        State(ids.DD_WHY, "value"),
        State(ids.DD_OPEN_STORE, "data"),
        State(ids.DD_REFRESH, "data"),
        prevent_initial_call=True,
    )
    def rate_it(n_rate, n_clear, value, why, deep_dive_id, refresh):
        if not deep_dive_id or not (n_rate or n_clear):
            return no_update, no_update
        ctx = get_context()
        if dash.ctx.triggered_id == ids.DD_UNRATE:
            ok, message = clear_rating(ctx, deep_dive_id)
        else:
            ok, message = rate(ctx, deep_dive_id, value, why or "")
        panel = detail_panel(
            ctx, ctx.deep_dives.get(deep_dive_id), alert(message, "green" if ok else "yellow")
        )
        return panel, (refresh or 0) + 1

    @app.callback(
        Output(ids.DD_DETAIL, "children", allow_duplicate=True),
        Output(ids.DD_REFRESH, "data", allow_duplicate=True),
        Input(ids.DD_WITHDRAW, "n_clicks"),
        State(ids.DD_OPEN_STORE, "data"),
        State(ids.DD_REFRESH, "data"),
        prevent_initial_call=True,
    )
    def withdraw_it(n, deep_dive_id, refresh):
        if not n or not deep_dive_id:
            return no_update, no_update
        ctx = get_context()
        ok, message = withdraw(ctx, deep_dive_id)
        panel = detail_panel(ctx, ctx.deep_dives.get(deep_dive_id), alert(message, "green" if ok else "red"))
        return panel, (refresh or 0) + 1

    @app.callback(
        Output(ids.URL, "search", allow_duplicate=True),
        Output(ids.DD_FEEDBACK, "children"),
        Input(ids.DD_AGAIN, "n_clicks"),
        State(ids.DD_OPEN_STORE, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.DD_AGAIN, "loading"), True, False)],
    )
    def again(n, deep_dive_id):
        if not n or not deep_dive_id:
            return no_update, no_update
        ctx = get_context()
        try:
            d = run_again(ctx, deep_dive_id)
        except (Forbidden, NotFoundError, ValueError) as exc:
            return no_update, alert(str(exc), "red")
        return search_of({}, d.deep_dive_id), no_update

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.DD_PACK, "n_clicks"),
        State(ids.DD_OPEN_STORE, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.DD_PACK, "loading"), True, False)],
    )
    def download(n, deep_dive_id):
        if not n or not deep_dive_id:
            return no_update
        name, data = pack(get_context(), deep_dive_id)
        return dcc.send_bytes(data, name)
