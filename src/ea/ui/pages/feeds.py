"""Feeds: the configured sources, what each one reads, and running one now.

A feed reads the landing schema of the store's own database (decision 0020). This page is
where a feed is configured and where somebody runs one without waiting for its schedule.

The page shows a schedule; it does not fire one. What fires a feed is outside the application,
so the screen says so rather than leaving a reader to assume that saving a schedule here makes
anything happen.
"""

from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.config import Settings
from ea.importer.feeds import in_zone, run_configured_feed, schedule_in_words
from ea.models import Forbidden, SourceFeed
from ea.services.roles import a_role
from ea.ui import ids
from ea.ui.components import alert, icon, issues_table, modal_title, page_title
from ea.ui.context import AppContext, get_context

ISSUE_LIMIT = 200


def schedule_notice(zone: str) -> str:
    """What the page says at the top about times and about what a schedule does.

    Saving a schedule here makes nothing happen — what fires a feed is outside the application
    (decision 0020) — and a page that showed one without saying so would imply that it does.
    """
    return (
        f"Times are shown in {zone}. The schedule is what a trigger outside the application "
        "honours — this page shows it and runs a feed on demand; it does not fire one."
    )


def _zone(ctx: AppContext) -> str:
    """The zone this deployment reads times in. A setting, because the repository is generic."""
    return Settings.from_env().timezone or "UTC"


def _why_not_run(ctx: AppContext) -> str:
    """Why Run is off, in the reader's own terms, or empty when it is not."""
    if not ctx.can("import"):
        return f"{a_role(ctx.role_label())} may not run a feed; an architect or an admin can."
    return ""


def _why_not_configure(ctx: AppContext) -> str:
    if not ctx.can("manage_feeds"):
        return (
            f"{a_role(ctx.role_label())} may not configure a feed: where content comes from, and "
            "whether a source lands on main without review, is an admin's decision."
        )
    return ""


def feed_row(feed: SourceFeed, zone: str, can_run: bool, can_configure: bool) -> Any:
    """One feed: what it reads, where it writes, when it is meant to run, and how it last went."""
    tables = ", ".join(t for t in (feed.elements_table, feed.relationships_table, feed.links_table) if t)
    where = feed.target_branch or "main"
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(
                    [
                        dmc.Text(feed.name or feed.source_system or feed.feed_id, fw=700),
                        dmc.Badge(
                            f"→ {where}",
                            variant="light",
                            # Landing on main is the one that skips review, so it is the one
                            # that has to look different from the rest.
                            color="orange" if feed.writes_to_main else "blue",
                        ),
                        dmc.Badge("disabled", variant="light", color="gray") if not feed.enabled else None,
                        dmc.Badge("keeps its landing tables", variant="light", color="gray", size="sm")
                        if not feed.clear_after
                        else None,
                    ],
                    gap="xs",
                ),
                dmc.Text(f"Reads {tables or 'no landing table yet'}", size="sm", c="dimmed"),
                dmc.Text(schedule_in_words(feed, zone), size="sm"),
                dmc.Text(
                    f"Last run {in_zone(feed.last_run_at, zone)} — {feed.last_run_status}"
                    if feed.last_run_at
                    else "Never run",
                    size="xs",
                    c="dimmed",
                ),
                dmc.Text(feed.last_run_summary, size="xs", c="dimmed") if feed.last_run_summary else None,
                dmc.Group(
                    [
                        dmc.Button(
                            "Run now",
                            id={"type": ids.FEED_RUN, "id": feed.feed_id},
                            leftSection=icon("tabler:player-play"),
                            size="xs",
                            disabled=not can_run,
                        ),
                        dmc.Button(
                            "Edit",
                            id={"type": ids.FEED_EDIT, "id": feed.feed_id},
                            variant="light",
                            size="xs",
                            disabled=not can_configure,
                        ),
                        dmc.Button(
                            "Delete",
                            id={"type": ids.FEED_DELETE, "id": feed.feed_id},
                            variant="subtle",
                            color="red",
                            size="xs",
                            disabled=not can_configure,
                        ),
                    ],
                    gap="xs",
                ),
            ],
            gap=6,
        ),
        p="md",
        withBorder=True,
    )


def feed_list(ctx: AppContext) -> Any:
    zone, can_run, can_configure = _zone(ctx), ctx.can("import"), ctx.can("manage_feeds")
    feeds = ctx.backend.list_feeds()
    if not feeds:
        return alert(
            "No feeds configured. A feed reads a table a source leaves in the landing schema of "
            "this store's own database, and loads it exactly as an uploaded file is loaded.",
            "blue",
        )
    return dmc.Stack([feed_row(f, zone, can_run, can_configure) for f in feeds], gap="sm")


def _modal(ctx: AppContext) -> Any:
    zone = _zone(ctx)
    return dmc.Modal(
        id=ids.FEED_MODAL,
        title=modal_title("Configure a feed", ids.FEED_MODAL),
        closeButtonProps={"aria-label": "Close this dialog"},
        size="lg",
        children=dmc.Stack(
            [
                dmc.TextInput(id=ids.FEED_NAME, label="Name", required=True),
                dmc.TextInput(
                    id=ids.FEED_SOURCE,
                    label="Source system",
                    description="Recorded on every row it loads; a relationship's identity is derived from it.",
                ),
                dmc.SimpleGrid(
                    [
                        dmc.TextInput(id=ids.FEED_EL_TABLE, label="Elements table"),
                        dmc.TextInput(id=ids.FEED_REL_TABLE, label="Relationships table"),
                        dmc.TextInput(id=ids.FEED_LINK_TABLE, label="Links table"),
                    ],
                    cols={"base": 1, "sm": 3},
                    spacing="sm",
                ),
                dmc.TextInput(
                    id=ids.FEED_BRANCH,
                    label="Writes to",
                    placeholder="a branch id; leave empty for main",
                    description="A feed on a branch is reviewed before it reaches main. One on main is not.",
                ),
                dmc.SimpleGrid(
                    [
                        dmc.TextInput(
                            id=ids.FEED_SCHEDULE,
                            label="Schedule",
                            placeholder="30 2 * * *",
                            description="A cron expression, as whatever triggers this feed writes them.",
                        ),
                        dmc.TextInput(
                            id=ids.FEED_TZ,
                            label="Schedule timezone",
                            value=zone,
                            description="The zone the expression is written in.",
                        ),
                    ],
                    cols={"base": 1, "sm": 2},
                    spacing="sm",
                ),
                dmc.Textarea(
                    id=ids.FEED_MAPPING,
                    label="Mapping (YAML)",
                    description="Stored with the feed, so a source's columns cannot change underneath it. Empty means the contract as written.",
                    minRows=4,
                    autosize=True,
                ),
                dmc.Group(
                    [
                        dmc.Checkbox(
                            id=ids.FEED_CLEAR,
                            label="Empty the landing tables once they are loaded",
                            checked=True,
                        ),
                        dmc.Checkbox(id=ids.FEED_ENABLED, label="Enabled", checked=True),
                    ],
                    gap="lg",
                ),
                html.Div(id=ids.FEED_MODAL_FEEDBACK),
                dmc.Group([dmc.Button("Save", id=ids.FEED_SAVE)], justify="flex-end"),
            ],
            gap="sm",
        ),
    )


def render(ctx: AppContext) -> html.Div:
    why_run, why_configure = _why_not_run(ctx), _why_not_configure(ctx)
    return html.Div(
        [
            page_title(
                "Feeds",
                "A source leaves rows in the landing schema of this store's own database and a feed "
                "loads them through the same validation, report and branch rules an uploaded file gets.",
            ),
            # Saving a schedule here does not make anything happen, and a page that showed one
            # without saying so would imply that it does.
            alert(schedule_notice(_zone(ctx)), "blue", dismissible=False),
            alert(why_configure, "blue", dismissible=False) if why_configure else None,
            alert(why_run, "blue", dismissible=False) if why_run and not why_configure else None,
            dmc.Group(
                [
                    dmc.Button(
                        "New feed",
                        id=ids.FEED_NEW,
                        leftSection=icon("tabler:plus"),
                        variant="light",
                        disabled=not ctx.can("manage_feeds"),
                    )
                ],
                mb="md",
            ),
            dcc.Store(id=ids.FEED_ID, data=""),
            html.Div(id=ids.FEED_FEEDBACK),
            html.Div(feed_list(ctx), id=ids.FEED_LIST),
            _modal(ctx),
        ]
    )


def _report_view(report: Any, name: str) -> Any:
    colour = "green" if report.ok else "red"
    found = sum(report.counts.values())
    return html.Div(
        [
            alert(f"{name}: {report.summary()}", colour),
            dmc.Title(f"Issues ({found})", order=2, size="h5", my="sm") if found else None,
            issues_table(report.issues[:ISSUE_LIMIT]) if report.issues else None,
        ]
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.FEED_MODAL, "opened"),
        Output(ids.FEED_ID, "data"),
        Output(ids.FEED_NAME, "value"),
        Output(ids.FEED_SOURCE, "value"),
        Output(ids.FEED_EL_TABLE, "value"),
        Output(ids.FEED_REL_TABLE, "value"),
        Output(ids.FEED_LINK_TABLE, "value"),
        Output(ids.FEED_BRANCH, "value"),
        Output(ids.FEED_SCHEDULE, "value"),
        Output(ids.FEED_TZ, "value"),
        Output(ids.FEED_MAPPING, "value"),
        Output(ids.FEED_CLEAR, "checked"),
        Output(ids.FEED_ENABLED, "checked"),
        Input(ids.FEED_NEW, "n_clicks"),
        Input({"type": ids.FEED_EDIT, "id": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_modal(new_clicks, edit_clicks):
        """One dialog for both: a new feed starts empty, an existing one starts as it is."""
        ctx = get_context()
        trigger = dash.ctx.triggered_id
        zone = _zone(ctx)
        if trigger == ids.FEED_NEW and new_clicks:
            return True, "", "", "", "", "", "", "", "", zone, "", True, True
        if isinstance(trigger, dict) and any(edit_clicks or []):
            feed = ctx.backend.get_feed(trigger["id"])
            if feed is None:
                return (no_update,) * 13
            return (
                True,
                feed.feed_id,
                feed.name,
                feed.source_system,
                feed.elements_table,
                feed.relationships_table,
                feed.links_table,
                feed.target_branch,
                feed.schedule,
                feed.schedule_timezone or zone,
                feed.mapping_yaml,
                feed.clear_after,
                feed.enabled,
            )
        return (no_update,) * 13

    @app.callback(
        Output(ids.FEED_MODAL, "opened", allow_duplicate=True),
        Output(ids.FEED_LIST, "children"),
        Output(ids.FEED_MODAL_FEEDBACK, "children"),
        Input(ids.FEED_SAVE, "n_clicks"),
        State(ids.FEED_ID, "data"),
        State(ids.FEED_NAME, "value"),
        State(ids.FEED_SOURCE, "value"),
        State(ids.FEED_EL_TABLE, "value"),
        State(ids.FEED_REL_TABLE, "value"),
        State(ids.FEED_LINK_TABLE, "value"),
        State(ids.FEED_BRANCH, "value"),
        State(ids.FEED_SCHEDULE, "value"),
        State(ids.FEED_TZ, "value"),
        State(ids.FEED_MAPPING, "value"),
        State(ids.FEED_CLEAR, "checked"),
        State(ids.FEED_ENABLED, "checked"),
        prevent_initial_call=True,
    )
    def save(n, feed_id, name, source, el, rel, link, branch, schedule, tz, mapping, clear, enabled):
        if not n:
            return no_update, no_update, no_update
        ctx = get_context()
        if not ctx.can("manage_feeds"):
            return no_update, no_update, alert(_why_not_configure(ctx), "red")
        if not (name or "").strip():
            return no_update, no_update, alert("A feed needs a name.", "yellow")
        if not any((el, rel, link)):
            return (
                no_update,
                no_update,
                alert("A feed needs at least one landing table to read.", "yellow"),
            )
        feed = SourceFeed(
            feed_id=feed_id or "",
            name=name.strip(),
            source_system=(source or name).strip(),
            elements_table=(el or "").strip(),
            relationships_table=(rel or "").strip(),
            links_table=(link or "").strip(),
            mapping_yaml=mapping or "",
            target_branch=(branch or "").strip(),
            clear_after=bool(clear),
            enabled=bool(enabled),
            schedule=(schedule or "").strip(),
            schedule_timezone=(tz or "").strip(),
        )
        try:
            ctx.backend.save_feed(feed, ctx.actor)
        except Forbidden as exc:
            return no_update, no_update, alert(str(exc), "red")
        return False, feed_list(ctx), None

    @app.callback(
        Output(ids.FEED_FEEDBACK, "children"),
        Output(ids.FEED_LIST, "children", allow_duplicate=True),
        Input({"type": ids.FEED_RUN, "id": dash.ALL}, "n_clicks"),
        Input({"type": ids.FEED_DELETE, "id": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def run_or_delete(run_clicks, delete_clicks):
        """Run one feed now, or forget one. Running honours the branch the feed names."""
        trigger = dash.ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update, no_update
        ctx = get_context()
        feed_id = trigger["id"]
        if trigger.get("type") == ids.FEED_DELETE:
            if not any(delete_clicks or []):
                return no_update, no_update
            if not ctx.can("manage_feeds"):
                return alert(_why_not_configure(ctx), "red"), no_update
            ctx.backend.delete_feed(feed_id, ctx.actor)
            return alert("Feed deleted. Nothing it loaded was touched.", "blue"), feed_list(ctx)
        if not any(run_clicks or []):
            return no_update, no_update
        feed = ctx.backend.get_feed(feed_id)
        try:
            report = run_configured_feed(ctx.backend, ctx.registry, feed_id, ctx.actor)
        except Forbidden as exc:
            return alert(str(exc), "red"), no_update
        ctx.graph.invalidate()
        return _report_view(report, feed.name if feed else feed_id), feed_list(ctx)
