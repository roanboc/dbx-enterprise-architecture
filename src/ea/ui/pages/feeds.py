"""Feeds: the configured sources, what each one reads, and running one now.

A feed reads the staging schema of the store's own database (decision 0020). This page is
where a feed is configured and where somebody runs one without waiting for its schedule.

The page shows a schedule; it does not fire one. What fires a feed is outside the application,
so the screen says so rather than leaving a reader to assume that saving a schedule here makes
anything happen.
"""

from __future__ import annotations

import re
from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.backend.sql import staging_schema
from ea.config import Settings
from ea.importer import schedule
from ea.importer.csv_export import contract_example
from ea.importer.feeds import in_zone, run_configured_feed, schedule_in_words
from ea.importer.mapping import mapping_from_text
from ea.importer.runs import counts_in_words, describe_inputs
from ea.models import Forbidden, ImportRun, SourceFeed
from ea.services.roles import a_role
from ea.ui import ids
from ea.ui.components import alert, icon, issues_table, modal_title, page_title
from ea.ui.context import AppContext, get_context

ISSUE_LIMIT = 200

#: How many runs the history shows before a reader asks for more. The history is never read
#: whole: this is a page of it, and `Show older` asks for the next one (decision 0019).
HISTORY_PAGE = 10

#: What each status is called and coloured on the page. `errors` is deliberately not red: the
#: run finished and wrote what it could, which is a different thing from one that stopped.
RUN_STATUS_COLOURS = {"ok": "green", "errors": "yellow", "failed": "red"}


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


_COUNTS = re.compile(r"(elements|relationships) \d+/\d+ loaded \(([^)]*)\)")
_CHANGE = re.compile(r"(\d+) (new|updated|retired|skipped)")


def run_in_brief(summary: str) -> str:
    """What a run changed, per kind, out of a summary written for a terminal.

    `ImportReport.summary()` says everything, which is right where a reader asked for a report
    and wrong on a card: the counts that stayed at zero crowd out the ones that did not. The
    kinds are kept apart because '3 new' across elements and relationships names nothing a
    reader could act on. The whole summary is still there, under the pointer.
    """
    if not summary:
        return ""
    parts: list[str] = []
    for kind, inner in _COUNTS.findall(summary):
        changes = [f"{n} {what}" for n, what in _CHANGE.findall(inner) if n != "0"]
        if changes:
            parts.append(f"{kind} {', '.join(changes)}")
    errors = "0 errors" not in summary
    if not parts:
        return "No rows loaded — see the errors" if errors else "Nothing changed"
    return " · ".join(parts) + (" — with errors" if errors else "")


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
                            # Staging on main is the one that skips review, so it is the one
                            # that has to look different from the rest.
                            color="orange" if feed.writes_to_main else "blue",
                        ),
                        dmc.Badge("disabled", variant="light", color="gray") if not feed.enabled else None,
                        dmc.Badge("keeps its staging tables", variant="light", color="gray", size="sm")
                        if not feed.clear_after
                        else None,
                    ],
                    gap="xs",
                ),
                dmc.Text(f"Reads {tables or 'no staging table yet'}", size="sm", c="dimmed"),
                dmc.Text(schedule_in_words(feed, zone), size="sm"),
                dmc.Text(
                    f"Last run {in_zone(feed.last_run_at, zone)} — {feed.last_run_status}"
                    if feed.last_run_at
                    else "Never run",
                    size="xs",
                    c="dimmed",
                ),
                dmc.Tooltip(
                    label=feed.last_run_summary,
                    multiline=True,
                    w=420,
                    withArrow=True,
                    children=dmc.Text(run_in_brief(feed.last_run_summary), size="xs", c="dimmed"),
                )
                if feed.last_run_summary
                else None,
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
            "No feeds configured. A feed reads a table a source leaves in the staging schema of "
            "this store's own database, and loads it exactly as an uploaded file is loaded.",
            "blue",
        )
    return dmc.Stack([feed_row(f, zone, can_run, can_configure) for f in feeds], gap="sm")


def run_row(run: ImportRun, zone: str) -> Any:
    """One run of the history: a line that says how it went, opening onto what it did.

    The line is the whole of what most readers want — when, from where, how it went — and the
    panel is for the one run in fifty that needs explaining.
    """
    when = in_zone(run.started_at, zone) or "—"
    who = run.feed_name or run.source_system or "an upload"
    return dmc.AccordionItem(
        [
            dmc.AccordionControl(
                dmc.Group(
                    [
                        dmc.Badge(
                            run.status or "unknown",
                            variant="light",
                            color=RUN_STATUS_COLOURS.get(run.status, "gray"),
                        ),
                        dmc.Text(when, size="sm", fw=600),
                        dmc.Text(who, size="sm"),
                        dmc.Badge(
                            f"→ {run.branch_id or 'main'}",
                            variant="light",
                            # The same colouring the feed cards use: a run that landed on main
                            # is a run nobody reviewed, and it reads that way here too.
                            color="orange" if (run.branch_id or "main") == "main" else "blue",
                            size="sm",
                        ),
                    ],
                    gap="xs",
                )
            ),
            dmc.AccordionPanel(
                dmc.Stack(
                    [
                        dmc.Text(f"Read {describe_inputs(run)}", size="sm", c="dimmed"),
                        dmc.Text(run.message if run.status == "failed" else counts_in_words(run), size="sm"),
                        dmc.Text(
                            f"Started by {run.actor or 'somebody'} ({run.trigger or 'unknown'})"
                            + (f" · run {run.run_id}" if run.run_id else ""),
                            size="xs",
                            c="dimmed",
                        ),
                        dmc.Text(
                            f"{run.error_count} errors, {run.warning_count} warnings",
                            size="xs",
                            c="dimmed",
                        )
                        if run.error_count or run.warning_count
                        else None,
                        issues_table(run.issues) if run.issues else None,
                        # A run keeps a sample of its issues; the counts beside it are the whole
                        # of what it found. Saying so is what stops the sample passing for the total.
                        dmc.Text(
                            f"The run kept the first {len(run.issues)} of "
                            f"{sum(run.issue_counts.values())} issues it found.",
                            size="xs",
                            c="dimmed",
                        )
                        if run.truncated
                        else None,
                    ],
                    gap=6,
                )
            ),
        ],
        value=run.run_id or when,
    )


def history_list(ctx: AppContext, offset: int = 0) -> Any:
    """One page of the history, newest first.

    A page, not a growing list: `Older` asks the store for the *next* page rather than for a
    longer one, so however far back a reader goes, one request reads `HISTORY_PAGE` rows
    (decision 0019). The command line pages the same way, with the same offset.
    """
    total = ctx.backend.count_runs()
    if not total:
        return alert(
            "No imports have been recorded yet. Every load — a feed's, a file uploaded on the "
            "Import page, or one run from the command line — appears here once it has run.",
            "blue",
        )
    offset = max(0, min(int(offset or 0), max(0, total - 1)))
    runs = ctx.backend.runs(HISTORY_PAGE, offset)
    return dmc.Stack(
        [
            dmc.Accordion(
                [run_row(r, _zone(ctx)) for r in runs], chevronPosition="left", variant="separated"
            ),
            dmc.Group(
                [
                    dmc.Text(
                        f"{offset + 1}–{offset + len(runs)} of {total}, newest first",
                        size="xs",
                        c="dimmed",
                    ),
                    dmc.Button("Newer", id=ids.RUNS_NEWER, variant="subtle", size="xs", disabled=offset == 0),
                    dmc.Button(
                        "Older",
                        id=ids.RUNS_OLDER,
                        variant="subtle",
                        size="xs",
                        disabled=offset + len(runs) >= total,
                    ),
                ],
                gap="xs",
            ),
        ],
        gap="xs",
    )


#: What a mapping is for, shown where it is asked for rather than in a document elsewhere.
#: Most feeds need none: a source that already writes the contract's own column names is read
#: as it is, and the box stays empty.
MAPPING_HELP = (
    "Leave this empty if the staging table already uses the contract's column names "
    "(id, type, name, description, …). Fill it in when the source calls things something else, "
    "numbers its rows the same way another source does, or is known by a key rather than an id."
)

MAPPING_EXAMPLE = """# Only the lines you need — every key is optional.
id_prefix: "CMDB-"        # put in front of every identifier, so two sources cannot collide
elements:
  match_on: id            # or: key, when the source knows its rows by DT007 rather than an id
  columns:                # the source's column name: the contract's
    CI_ID: id
    CI_NAME: name
    CI_TYPE: type
  type_names:             # the source's word for a type: the pack's
    Server: physical_technology_component
relationships:
  columns:
    FROM_CI: src_id
    TO_CI: dst_id
    REL: rel_type
"""


def staging_note(prefix: str) -> str:
    """Where a source puts its rows, named rather than assumed.

    The schema is the deployment's, not the application's: `EA_SCHEMA` sets the prefix and the
    staging schema follows from it. A form that asked for three table names without saying
    which schema they live in would be asking half a question.
    """
    return (
        f"Name the tables only — they are read from the {staging_schema(prefix)} schema of this "
        "store's own database, which the deployment names through EA_SCHEMA. A source writes "
        "its rows there; the application never reaches outside it."
    )


def _tables_field() -> Any:
    """The three table names, with the schema they live in and the example that shows their shape."""
    prefix = Settings.from_env().store_schema or "ea"
    return dmc.Stack(
        [
            dmc.Text("Staging tables", fw=500, size="sm"),
            dmc.Text(staging_note(prefix), size="xs", c="dimmed"),
            dmc.SimpleGrid(
                [
                    dmc.TextInput(
                        id=ids.FEED_EL_TABLE,
                        label="Elements table",
                        placeholder=f"{prefix}_elements",
                    ),
                    dmc.TextInput(
                        id=ids.FEED_REL_TABLE,
                        label="Relationships table",
                        placeholder=f"{prefix}_relationships",
                    ),
                    dmc.TextInput(
                        id=ids.FEED_LINK_TABLE,
                        label="Links table",
                        placeholder=f"{prefix}_links",
                    ),
                ],
                cols={"base": 1, "sm": 3},
                spacing="sm",
            ),
            dmc.Group(
                [
                    dmc.Text(
                        "A staging table has the columns of the CSV contract — the same ones an "
                        "uploaded file has.",
                        size="xs",
                        c="dimmed",
                    ),
                    # A button rather than a link: this produces a file, and an anchor does not
                    # report a click to the callback that would make one.
                    dmc.Button(
                        "Download the example and the column reference",
                        id=ids.FEED_EXAMPLE,
                        variant="subtle",
                        size="compact-xs",
                        leftSection=icon("tabler:download", 14),
                    ),
                ],
                gap="xs",
            ),
        ],
        gap=4,
    )


def _mapping_field() -> Any:
    """The mapping, with what it is for and a worked example beside it.

    A field labelled only 'Mapping (YAML)' asks a question without saying what an answer looks
    like. Most feeds need no mapping at all, so the first thing it says is that leaving it empty
    is a real answer, and the example is folded away for the feeds that do need one.
    """
    return dmc.Stack(
        [
            dmc.Text("Mapping (YAML)", fw=500, size="sm"),
            dmc.Text(MAPPING_HELP, size="xs", c="dimmed"),
            dmc.Accordion(
                children=[
                    dmc.AccordionItem(
                        value="example",
                        children=[
                            dmc.AccordionControl("Show an example, and what each key does"),
                            dmc.AccordionPanel(
                                dmc.Stack(
                                    [
                                        dmc.Code(MAPPING_EXAMPLE, block=True),
                                        dmc.Text(
                                            "Every key is optional and the whole contract is "
                                            "documented in connectors/README.md.",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                    ],
                                    gap="xs",
                                )
                            ),
                        ],
                    )
                ],
                value=None,
                chevronPosition="left",
                variant="contained",
            ),
            dmc.Textarea(
                id=ids.FEED_MAPPING,
                placeholder="Empty — the staging table uses the contract's own column names",
                minRows=4,
                autosize=True,
                **{"aria-label": "The feed's mapping, as YAML"},
            ),
            html.Div(id=ids.FEED_MAPPING_SAID),
        ],
        gap=4,
    )


def _schedule_picker(zone: str) -> Any:
    """When a feed runs, chosen the way a person says it rather than typed as cron.

    The expression is still what is stored and what a trigger takes — the picker writes it, the
    sentence underneath reads it back, and `Show the cron expression` reveals it for anyone who
    would rather write one. An expression the picker cannot hold is not overwritten by it: the
    box stays authoritative and the sentence shows it as written.
    """
    return dmc.Stack(
        [
            dmc.Text("Schedule", fw=500, size="sm"),
            dmc.Group(
                [
                    dmc.Text("Every", size="sm"),
                    dmc.Select(
                        id=ids.FEED_EVERY,
                        allowDeselect=False,
                        data=[{"value": e, "label": e.capitalize()} for e in schedule.EVERY],
                        value="day",
                        w=140,
                        **{"aria-label": "How often the feed runs"},
                    ),
                    dmc.Select(
                        id=ids.FEED_WEEKDAY,
                        allowDeselect=False,
                        data=[{"value": str(i), "label": d} for i, d in enumerate(schedule.WEEKDAYS)],
                        value="1",
                        w=140,
                        style={"display": "none"},
                        **{"aria-label": "Which day of the week"},
                    ),
                    dmc.Select(
                        id=ids.FEED_MONTHDAY,
                        allowDeselect=False,
                        data=[{"value": str(d), "label": schedule.ordinal(d)} for d in range(1, 32)],
                        value="1",
                        w=110,
                        style={"display": "none"},
                        **{"aria-label": "Which day of the month"},
                    ),
                    dmc.Text("at", size="sm"),
                    dmc.Select(
                        id=ids.FEED_HOUR,
                        allowDeselect=False,
                        data=[{"value": str(h), "label": f"{h:02d}"} for h in range(24)],
                        value="2",
                        w=90,
                        **{"aria-label": "Hour"},
                    ),
                    dmc.Text(":", size="sm"),
                    dmc.Select(
                        id=ids.FEED_MINUTE,
                        allowDeselect=False,
                        data=[{"value": str(m), "label": f"{m:02d}"} for m in range(60)],
                        value="30",
                        w=90,
                        **{"aria-label": "Minute"},
                    ),
                ],
                gap="xs",
                align="flex-end",
            ),
            dmc.Text(id=ids.FEED_SCHEDULE_SAID, size="sm", c="dimmed"),
            dmc.Checkbox(id=ids.FEED_SHOW_CRON, label="Show the cron expression", checked=False),
            dmc.TextInput(
                id=ids.FEED_SCHEDULE,
                placeholder="30 2 * * *",
                description=(
                    "What is stored, and what a trigger outside the application takes. Editing it "
                    "here overrides the picker above."
                ),
                style={"display": "none"},
                **{"aria-label": "The cron expression"},
            ),
            dmc.Select(
                id=ids.FEED_TZ,
                allowDeselect=False,
                label="Timezone",
                data=schedule.zone_options(),
                value=zone,
                searchable=True,
                description="The zone the schedule is written in, and the one its times mean.",
                comboboxProps={"withinPortal": False},
            ),
        ],
        gap="xs",
    )


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
                _tables_field(),
                dmc.TextInput(
                    id=ids.FEED_BRANCH,
                    label="Writes to",
                    placeholder="a branch id; leave empty for main",
                    description="A feed on a branch is reviewed before it reaches main. One on main is not.",
                ),
                _schedule_picker(zone),
                _mapping_field(),
                dmc.Group(
                    [
                        dmc.Checkbox(
                            id=ids.FEED_CLEAR,
                            label="Empty the staging tables once they are loaded",
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
                "A source leaves rows in the staging schema of this store's own database and a feed "
                "loads them through the same validation, report and branch rules an uploaded file gets.",
            ),
            # Saving a schedule here does not make anything happen, and a page that showed one
            # without saying so would imply that it does.
            alert(schedule_notice(_zone(ctx)), "blue", dismissible=False),
            # A role that may do neither is told about both: being told why the dialog is shut
            # says nothing about why Run now is, and they are different permissions.
            alert(why_configure, "blue", dismissible=False) if why_configure else None,
            alert(why_run, "blue", dismissible=False) if why_run else None,
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
            # Every import is here, not only a feed's: a file somebody uploaded on the Import
            # page and a run from the command line are the same kind of event, and splitting
            # them across two screens would make neither of them the history.
            dmc.Title("Import history", order=2, size="h4", mt="xl", mb="xs"),
            dmc.Text(
                "Every run, whoever or whatever started it: what it read, where it wrote and how "
                "it went. A run is an account of what happened — nothing here undoes one.",
                size="sm",
                c="dimmed",
                mb="sm",
            ),
            dcc.Store(id=ids.RUNS_OFFSET, data=0),
            html.Div(history_list(ctx), id=ids.RUNS_LIST),
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
        Output(ids.FEED_WEEKDAY, "style"),
        Output(ids.FEED_MONTHDAY, "style"),
        Output(ids.FEED_HOUR, "style"),
        Output(ids.FEED_SCHEDULE, "value", allow_duplicate=True),
        Output(ids.FEED_SCHEDULE_SAID, "children"),
        Input(ids.FEED_EVERY, "value"),
        Input(ids.FEED_HOUR, "value"),
        Input(ids.FEED_MINUTE, "value"),
        Input(ids.FEED_WEEKDAY, "value"),
        Input(ids.FEED_MONTHDAY, "value"),
        State(ids.FEED_TZ, "value"),
        prevent_initial_call=True,
    )
    def build(every, hour, minute, weekday, monthday, zone):
        """The picker writes the expression, and says in words what it just wrote.

        Only the parts a recurrence uses are shown: an hourly schedule has no hour to choose,
        a weekly one needs a day of the week, a monthly one a date. A control that does not
        apply is hidden rather than left to be filled in and ignored.
        """
        hidden, shown = {"display": "none"}, {"display": "block"}
        cron = schedule.to_cron(
            every or "day",
            int(hour or 0),
            int(minute or 0),
            weekday=int(weekday or 0),
            day_of_month=int(monthday or 1),
        )
        said = f"{schedule.in_words(cron)} ({zone or 'UTC'})"
        return (
            shown if every == "week" else hidden,
            shown if every == "month" else hidden,
            hidden if every == "hour" else shown,
            cron,
            said,
        )

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.FEED_EXAMPLE, "n_clicks"),
        prevent_initial_call=True,
    )
    def example(n):
        """The contract's own example files, from the form that asks for tables shaped like them.

        A staging table has the columns an uploaded file has, so the example is the same one the
        Import page hands out — the three files with a row apiece, and the schema file naming
        every column, its parent and its type. Somebody filling this form in should not have to
        go and find it.
        """
        if not n:
            return no_update
        ctx = get_context()
        return dcc.send_bytes(
            contract_example(ctx.backend, ctx.registry), "ea-staging-example.zip", type="application/zip"
        )

    @app.callback(
        Output(ids.FEED_MAPPING_SAID, "children"),
        Input(ids.FEED_MAPPING, "value"),
        prevent_initial_call=True,
    )
    def say_mapping(text):
        """What the mapping typed there would actually do, in a sentence.

        A YAML box gives no sign that it was understood until a run goes wrong, so this reads
        the mapping back as the rules it sets — and says plainly when it could not be read at
        all, which is the mistake worth catching before the feed is saved.
        """
        if not (text or "").strip():
            return None
        try:
            mapping = mapping_from_text(text)
        except Exception as exc:  # noqa: BLE001 — any YAML fault is the reader's to see
            return alert(f"This is not YAML that can be read: {exc}", "red")
        said = []
        if mapping.id_prefix:
            said.append(f"every identifier gets {mapping.id_prefix!r} in front of it")
        if mapping.match_on != "id":
            said.append(f"rows are matched on their {mapping.match_on}")
        if mapping.delimiter != ",":
            said.append(f"columns are separated by {mapping.delimiter!r}")
        for what, columns in (
            ("element", mapping.element_columns),
            ("relationship", mapping.relationship_columns),
            ("link", mapping.link_columns),
        ):
            if columns:
                said.append(f"{len(columns)} {what} column(s) renamed")
        if mapping.type_names:
            said.append(f"{len(mapping.type_names)} type name(s) translated")
        if mapping.deletion_mode != "retire":
            said.append(f"deletion mode {mapping.deletion_mode}")
        if not said:
            return alert(
                "Read, and it changes nothing — the staging table is taken as the contract writes it.",
                "blue",
            )
        return alert("Read: " + "; ".join(said) + ".", "green")

    @app.callback(
        Output(ids.FEED_SCHEDULE, "style"),
        Input(ids.FEED_SHOW_CRON, "checked"),
        prevent_initial_call=True,
    )
    def reveal_cron(checked):
        """Cron is exact and some people would rather write it. It is a click away, not the default."""
        return {"display": "block"} if checked else {"display": "none"}

    @app.callback(
        Output(ids.FEED_SCHEDULE_SAID, "children", allow_duplicate=True),
        Input(ids.FEED_SCHEDULE, "value"),
        State(ids.FEED_TZ, "value"),
        prevent_initial_call=True,
    )
    def say_typed_cron(cron, zone):
        """An expression typed by hand is read back in words too, so a mistake shows up here."""
        if not cron:
            return "No schedule — this feed will run when somebody runs it"
        said = schedule.in_words(cron)
        if said == cron:
            return f"{cron} ({zone or 'UTC'}) — too detailed to say in words, and kept as written"
        return f"{said} ({zone or 'UTC'})"

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
        Output(ids.FEED_EVERY, "value"),
        Output(ids.FEED_HOUR, "value"),
        Output(ids.FEED_MINUTE, "value"),
        Output(ids.FEED_WEEKDAY, "value"),
        Output(ids.FEED_MONTHDAY, "value"),
        Output(ids.FEED_SHOW_CRON, "checked"),
        Input(ids.FEED_NEW, "n_clicks"),
        Input({"type": ids.FEED_EDIT, "id": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_modal(new_clicks, edit_clicks):
        """One dialog for both: a new feed starts empty, an existing one starts as it is.

        A stored expression the picker can hold puts the picker where it left off. One it
        cannot is shown as written, with the expression revealed — because the picker would
        otherwise sit on a default that says something the feed does not.
        """
        ctx = get_context()
        trigger = dash.ctx.triggered_id
        zone = _zone(ctx)
        blank = (
            True,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            zone,
            "",
            True,
            True,
            "day",
            "2",
            "30",
            "1",
            "1",
            False,
        )
        if trigger == ids.FEED_NEW and new_clicks:
            return blank
        if isinstance(trigger, dict) and any(edit_clicks or []):
            feed = ctx.backend.get_feed(trigger["id"])
            if feed is None:
                return (no_update,) * 19
            picked = schedule.from_cron(feed.schedule) if feed.schedule else None
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
                picked["every"] if picked else "day",
                str(picked["hour"]) if picked else "2",
                str(picked["minute"]) if picked else "30",
                str(picked["weekday"]) if picked else "1",
                str(picked["day_of_month"]) if picked else "1",
                # An expression the picker cannot hold is shown rather than hidden behind one
                # that would misdescribe it.
                bool(feed.schedule) and picked is None,
            )
        return (no_update,) * 19

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
                alert("A feed needs at least one staging table to read.", "yellow"),
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
        Output(ids.RUNS_LIST, "children", allow_duplicate=True),
        Input({"type": ids.FEED_RUN, "id": dash.ALL}, "n_clicks"),
        Input({"type": ids.FEED_DELETE, "id": dash.ALL}, "n_clicks"),
        State(ids.RUNS_OFFSET, "data"),
        prevent_initial_call=True,
    )
    def run_or_delete(run_clicks, delete_clicks, offset):
        """Run one feed now, or forget one. Running honours the branch the feed names."""
        trigger = dash.ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update, no_update, no_update
        ctx = get_context()
        feed_id = trigger["id"]
        if trigger.get("type") == ids.FEED_DELETE:
            if not any(delete_clicks or []):
                return no_update, no_update, no_update
            if not ctx.can("manage_feeds"):
                return alert(_why_not_configure(ctx), "red"), no_update, no_update
            ctx.backend.delete_feed(feed_id, ctx.actor)
            # The feed goes; its history does not. What it loaded happened, and a run that
            # named a feed nobody kept still says what it did.
            return (
                alert(
                    "Feed deleted. Nothing it loaded was touched, and its runs stay in the history.", "blue"
                ),
                feed_list(ctx),
                history_list(ctx, offset),
            )
        if not any(run_clicks or []):
            return no_update, no_update, no_update
        feed = ctx.backend.get_feed(feed_id)
        try:
            report = run_configured_feed(ctx.backend, ctx.registry, feed_id, ctx.actor)
        except Forbidden as exc:
            # The run was recorded as it failed, so the history is refreshed here too.
            return alert(str(exc), "red"), no_update, history_list(ctx, offset)
        ctx.graph.invalidate()
        return (
            _report_view(report, feed.name if feed else feed_id),
            feed_list(ctx),
            history_list(ctx, offset),
        )

    @app.callback(
        Output(ids.RUNS_OFFSET, "data"),
        Output(ids.RUNS_LIST, "children", allow_duplicate=True),
        Input(ids.RUNS_OLDER, "n_clicks"),
        Input(ids.RUNS_NEWER, "n_clicks"),
        State(ids.RUNS_OFFSET, "data"),
        prevent_initial_call=True,
    )
    def page_the_history(older, newer, offset):
        """A page further back or a page nearer. The store is asked for it; nothing is held here."""
        if dash.ctx.triggered_id == ids.RUNS_OLDER and older:
            moved = int(offset or 0) + HISTORY_PAGE
        elif dash.ctx.triggered_id == ids.RUNS_NEWER and newer:
            moved = max(0, int(offset or 0) - HISTORY_PAGE)
        else:
            return no_update, no_update
        ctx = get_context()
        return moved, history_list(ctx, moved)
