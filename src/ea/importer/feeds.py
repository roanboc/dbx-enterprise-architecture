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

import pandas as pd

from ea import capacity
from ea.backend.base import DatabaseBackend
from ea.importer.csv_import import import_frames
from ea.importer.mapping import Mapping
from ea.metamodel.registry import Registry
from ea.models import ImportReport, Issue

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
