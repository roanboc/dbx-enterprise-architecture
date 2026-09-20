"""A feed: rows a source left in the landing schema, put through the import the app already has.

The landing schema is the boundary (decision 0020). What puts rows there is outside the
application — a platform job writing Postgres, or a catalogue table replicated into it — and
the contract with a source is the *shape of the table*, which is the CSV contract's columns.
Nothing here reaches into a catalogue, and a feed needs no dependency, resource or identity the
store does not already have.

Because the boundary is a table rather than a platform API, a feed works the same on DuckDB as
on Lakebase, which is what lets the suite cover it on both.

The order of a run is deliberate: **read, load, then clear**. Stopping between the load and the
clear re-reads the same rows next time, and loading them again is idempotent; stopping between
a clear and a load would have lost them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.backend.branching import MAIN, use_branch
from ea.importer.csv_import import import_frames
from ea.importer.mapping import Mapping, mapping_from_text
from ea.metamodel.registry import Registry
from ea.models import ImportReport, Issue, NotFoundError, SourceFeed


def _utc_now() -> datetime:
    """The instant a run happened, kept in UTC. Only what a person reads is converted."""
    return datetime.now(UTC).replace(tzinfo=None)


KINDS = ("elements", "relationships", "links")


@dataclass
class Feed:
    """A configured source: which landing tables are its, and how they are read.

    `mapping` is the same object a file import uses, so everything a source's shape needs —
    its column names, its identity column, its prefix, its deletion mode — is said once and in
    one place, whether the rows arrive as a file or as a table.
    """

    source_system: str
    #: Landing table per kind. A feed that only ever sends elements names only that one.
    tables: dict[str, str] = field(default_factory=dict)
    mapping: Mapping = field(default_factory=Mapping)
    #: Whether the landing tables are emptied once their rows are loaded. A feed reading a
    #: table something else maintains — a replicated catalogue table — leaves it alone.
    clear_after: bool = True

    def table_for(self, kind: str) -> str:
        return self.tables.get(kind, "")


def frames_from_landing(
    backend: DatabaseBackend, feed: Feed, report: ImportReport | None = None
) -> dict[str, list[tuple[str, pd.DataFrame]]]:
    """Every landing table the feed names, read a page at a time and joined per kind.

    The read is paged so no single statement asks the store for a whole table. The frame handed
    to the importer is whole, because that is what the importer takes — a landing table is the
    same size class as an uploaded file and is held the same way. That is the bound worth
    knowing: a feed costs what a file of the same size costs, not less.
    """
    out: dict[str, list[tuple[str, pd.DataFrame]]] = {k: [] for k in KINDS}
    held = set(backend.landing_tables())
    for kind in KINDS:
        table = feed.table_for(kind)
        if not table:
            continue
        if table not in held:
            if report is not None:
                report.add_issue(
                    Issue(
                        "warning",
                        "no_landing_table",
                        f"the feed names {table!r} for its {kind}, and the landing schema "
                        "holds no such table",
                        file=table,
                    )
                )
            continue
        out[kind].append((table, _read_whole(backend, table)))
    return out


def _read_whole(backend: DatabaseBackend, table: str) -> pd.DataFrame:
    """A landing table, a page at a time, as one frame of text.

    Everything is read as text because that is what a CSV gives the importer, and the importer
    is what decides a value's type from the metamodel. A feed that skipped that would type its
    values differently from a file saying the same thing.
    """
    pages: list[pd.DataFrame] = []
    offset = 0
    while True:
        page = backend.read_landing(table, capacity.READ_CHUNK, offset)
        if page.empty:
            break
        pages.append(page.astype(str))
        if len(page) < capacity.READ_CHUNK:
            break
        offset += len(page)
    if not pages:
        return backend.read_landing(table, 0, 0).astype(str)  # the header, with no rows
    return pages[0] if len(pages) == 1 else pd.concat(pages, ignore_index=True)


def run_feed(
    backend: DatabaseBackend,
    registry: Registry,
    feed: Feed,
    actor: str = "feed",
    dry_run: bool = False,
) -> ImportReport:
    """Read the feed's landing tables, load them, then clear what was loaded.

    Clearing last is what makes a stopped run safe: the rows are still there, and loading them
    again changes nothing that the first load did not already change.
    """
    report = ImportReport(source_system=feed.source_system or feed.mapping.source_system or "feed")
    frames = frames_from_landing(backend, feed, report)
    if not any(frames.values()):
        return report
    loaded = import_frames(backend, registry, frames, report.source_system, feed.mapping, actor, dry_run)
    # The landing read's own issues were raised against `report`; keep them ahead of the
    # import's so a reader sees what was not read before what was.
    loaded.issues = report.issues + loaded.issues
    for code, count in report.counts.items():
        loaded.counts[code] = loaded.counts.get(code, 0) + count
    loaded.warning_count += report.warning_count
    if not dry_run and feed.clear_after and loaded.ok:
        for kind in KINDS:
            table = feed.table_for(kind)
            if table and frames.get(kind):
                backend.clear_landing(table)
    return loaded


def feed_from_config(stored: SourceFeed) -> Feed:
    """The runnable feed a stored configuration describes.

    The mapping travels with the feed as YAML rather than as a path, so what a source's columns
    mean cannot change underneath it between one run and the next.
    """
    mapping = mapping_from_text(stored.mapping_yaml) if stored.mapping_yaml else Mapping()
    tables = {
        "elements": stored.elements_table,
        "relationships": stored.relationships_table,
        "links": stored.links_table,
    }
    return Feed(
        source_system=stored.source_system or stored.name,
        tables={k: v for k, v in tables.items() if v},
        mapping=mapping,
        clear_after=stored.clear_after,
    )


def run_configured_feed(
    backend: DatabaseBackend,
    registry: Registry,
    feed_id: str,
    actor: str = "feed",
    dry_run: bool = False,
) -> ImportReport:
    """Run a stored feed, on the branch it names, and record how it went.

    The branch is the feed's own: a feed configured onto a branch writes there and is reviewed
    before it reaches main, and one configured onto main writes directly. That is the choice the
    Requester made per source, and it is honoured here rather than by whoever presses the button.
    """
    stored = backend.get_feed(feed_id)
    if stored is None:
        raise NotFoundError(feed_id, "feed")
    with use_branch(stored.target_branch or MAIN):
        report = run_feed(backend, registry, feed_from_config(stored), actor, dry_run)
    if not dry_run:
        stored.last_run_at = _utc_now()
        stored.last_run_status = "ok" if report.ok else "errors"
        stored.last_run_summary = report.summary()
        backend.save_feed(stored, actor)
    return report


def in_zone(moment: Any, zone: str) -> str:
    """An instant kept in UTC, written where the reader is.

    Times are stored in UTC and read in a zone, because an instant is the same everywhere and
    only its name changes. The zone is named in the text, so nobody has to remember which one
    a screen is using.
    """
    if moment is None:
        return ""
    name = zone or "UTC"
    try:
        here = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return f"{moment:%Y-%m-%d %H:%M} UTC (the zone {name!r} is not one this system knows)"
    aware = moment if getattr(moment, "tzinfo", None) else moment.replace(tzinfo=UTC)
    return f"{aware.astimezone(here):%Y-%m-%d %H:%M} {name}"


def schedule_in_words(feed: SourceFeed, fallback_zone: str = "UTC") -> str:
    """What a feed's schedule says, and the zone it says it in.

    The expression is kept in the zone it was written in rather than converted to UTC, because
    a person who says half past two means half past two where they are — and a platform
    scheduler takes a zone alongside its expression for that reason. So there is nothing to
    convert to show it correctly, and nothing drifts when a zone's offset changes.

    The application does not fire it. What fires it is outside (decision 0020); this is what a
    trigger honours and what the screen shows beside `Run now`.
    """
    if not feed.schedule:
        return "No schedule — this feed runs when somebody runs it"
    zone = feed.schedule_timezone or fallback_zone or "UTC"
    daily = _daily_at(feed.schedule)
    when = f"{feed.schedule} ({daily} {zone})" if daily else f"{feed.schedule} ({zone})"
    return when if feed.enabled else f"{when} — disabled"


def _daily_at(cron: str) -> str:
    """`30 2 * * *` as `02:30`, when the expression is a plain daily one; else empty.

    Deliberately narrow. A five-field expression whose day, month and weekday are all `*` is a
    time of day and can be read as one; anything else is shown as written rather than guessed
    at, because a wrong rendering of a schedule is worse than none.
    """
    parts = cron.split()
    if len(parts) != 5:
        return ""
    minute, hour, day, month, weekday = parts
    if (day, month, weekday) != ("*", "*", "*") or not (minute.isdigit() and hour.isdigit()):
        return ""
    if not (0 <= int(minute) < 60 and 0 <= int(hour) < 24):
        return ""
    return f"{int(hour):02d}:{int(minute):02d} daily"
