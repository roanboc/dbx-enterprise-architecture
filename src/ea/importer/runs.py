"""Keeping what an import did, after the request that did it has gone.

An `ImportReport` is what a run said to whoever was watching. Most runs have nobody watching:
a feed fires at a quarter past two and reports to a screen nobody has open. So every import
that writes is bracketed by a recorder, and what it did is kept as an `ImportRun` (`DOBJ3.7`).

**A recorded run is an account, not an undo.** Reversing a run needs the before-image of every
row it changed, which is a different and much larger thing to store — and the reason it is not
stored is worth saying rather than implying: a feed may be configured onto `main`, and a run on
`main` cannot be undone by abandoning a branch the way every other change can (`GAP19`).

Three things start an import and all three are recorded the same way: somebody on the Import
page, `ea import` on the command line, and a feed. The recorder is a context manager so that a
run which *stops* is recorded too — a refused branch, a frozen review, a mapping that would not
read, a store that went away mid-load. A run that vanished because it failed is the one a
reader most wants to find.

The one thing not recorded is an attempt by somebody who may not import at all. That is not a
run; it is a refusal at the door, and writing it would make the history a place the one
principal `allowed()` denies every write to could fill at will.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from ea.backend.base import DatabaseBackend
from ea.backend.branching import current_branch
from ea.models import MAX_RUN_ISSUES, ImportReport, ImportRun, Issue, SourceFeed
from ea.services.roles import allowed

log = logging.getLogger(__name__)

#: Errors first, then warnings, then everything else. A run that found five errors behind five
#: hundred warnings would otherwise keep a sample of nothing but warnings, and the sample is
#: what a reader opens the run to see.
_BY_SEVERITY = {"error": 0, "warning": 1}


def _utc_now() -> datetime:
    """The instant a run happened, kept in UTC. Only what a person reads is converted."""
    return datetime.now(UTC).replace(tzinfo=None)


def issue_sample(issues: Sequence[Issue], keep: int = MAX_RUN_ISSUES) -> list[Issue]:
    """At most `keep` issues, the most serious first, in the order they were found within a level.

    The report a screen shows keeps thousands because it is thrown away afterwards. A run is
    kept forever, so it keeps a sample — and `issue_counts` stays complete beside it, so the
    totals a reader compares are never the sample's.
    """
    ranked = sorted(enumerate(issues), key=lambda pair: (_BY_SEVERITY.get(pair[1].level, 2), pair[0]))
    return [issue for _, issue in ranked[:keep]]


@dataclass
class Recording:
    """The run being recorded, while it happens.

    A caller sets `report` when it has one and calls `failed()` when it handled a refusal
    itself rather than letting it out. An exception that escapes needs neither: it is recorded
    on its way past.
    """

    run: ImportRun
    report: ImportReport | None = None
    #: Set by `failed()`, read by the recorder on the way out. Empty means nothing stopped it.
    failure: str = ""

    def failed(self, message: str) -> None:
        """Record this run as stopped, with why — for a caller that catches its own refusal."""
        self.failure = message or "the import was refused"

    @property
    def run_id(self) -> str:
        return self.run.run_id


def _fill(run: ImportRun, report: ImportReport) -> None:
    run.summary = report.summary()
    run.source_system = run.source_system or report.source_system
    run.elements_created = report.elements_created
    run.elements_updated = report.elements_updated
    run.elements_unchanged = report.elements_unchanged
    run.elements_retired = report.elements_retired
    run.relationships_created = report.relationships_created
    run.relationships_updated = report.relationships_updated
    run.relationships_unchanged = report.relationships_unchanged
    run.relationships_retired = report.relationships_retired
    run.links_loaded = report.links_loaded
    run.error_count = report.error_count
    run.warning_count = report.warning_count
    run.issues = issue_sample(report.issues)
    run.issue_counts = dict(report.counts)
    # The report's own truncation, plus this sample's. Either way more was found than is kept.
    run.truncated = report.truncated or len(run.issues) < len(report.issues)


@contextmanager
def recorded(
    backend: DatabaseBackend,
    *,
    trigger: str,
    actor: str,
    source_system: str = "",
    inputs: Sequence[str] = (),
    feed: SourceFeed | None = None,
    mapping_yaml: str = "",
    dry_run: bool = False,
) -> Iterator[Recording]:
    """Bracket an import and keep what it did.

    The branch is read **on the way in**, because a feed runs inside `use_branch` and would
    otherwise be recorded against whatever branch the caller happened to be on.

    A dry run records nothing. It wrote nothing, and a history of things that did not happen is
    a history nobody can read.
    """
    run = ImportRun(
        source_system=source_system or (feed.source_system or feed.name if feed else ""),
        trigger=trigger,
        feed_id=feed.feed_id if feed else "",
        # A copy of a name the feed owns, kept so deleting the feed does not delete its history.
        feed_name=feed.name if feed else "",
        actor=actor,
        branch_id=current_branch(),
        inputs=list(inputs),
        mapping_yaml=mapping_yaml or (feed.mapping_yaml if feed else ""),
        started_at=_utc_now(),
    )
    recording = Recording(run)
    try:
        yield recording
    except GeneratorExit:
        # The generator was closed without the body finishing. Nothing ran, so nothing happened.
        raise
    except BaseException as exc:
        # `BaseException`, not `Exception`: a Ctrl-C during a long import leaves whatever the
        # load had already written, and that is exactly the run a reader has to be able to find.
        if not dry_run:
            run.status, run.message = "failed", f"{type(exc).__name__}: {exc}"
            # Failing to record a failure must not replace it. What the caller needs to see is
            # the import's own exception; a store that could not take the row is a second
            # problem, logged rather than raised over the top of the first.
            try:
                _close(backend, recording)
            except Exception:  # noqa: BLE001 — the original exception is the one that matters
                log.warning("could not record the run that failed with %s", exc, exc_info=True)
        raise
    if dry_run:
        return
    if recording.failure:
        run.status, run.message = "failed", recording.failure
    elif recording.report is None:
        # Nothing set a report and nothing raised: the caller returned without importing.
        # Saying so is better than a run that looks like it loaded nothing on purpose.
        run.status, run.message = "failed", "the import returned without a report"
    else:
        run.status = "ok" if recording.report.ok else "errors"
    _close(backend, recording)


def _close(backend: DatabaseBackend, recording: Recording) -> None:
    if not allowed("import"):
        # The one write on the store's contract with no `require()` above it, because it is
        # reached *by* a refusal: the import gate raises, and the recorder catches it on the way
        # past. So the gate is read here instead. A caller the application would never let write
        # content does not get to write the history of trying — otherwise the one principal
        # `allowed()` denies every write to is the one who can grow the store without bound.
        # A refusal of *state* — a frozen branch, `main` when the role may not edit it — is a
        # different thing and is still recorded: those callers may import.
        log.info("not recording a run: %s", recording.run.message or "the caller may not import")
        return
    if recording.report is not None:
        _fill(recording.run, recording.report)
    recording.run.finished_at = _utc_now()
    backend.record_run(recording.run)


def in_words(run: ImportRun) -> str:
    """What a run did, as a line. The summary when there is one, the failure when there is not."""
    if run.status == "failed":
        return run.message or "the run stopped"
    return run.summary or "nothing was loaded"


def describe_inputs(run: ImportRun, limit: int = 3) -> str:
    """What it read, short enough for a row in a list."""
    if not run.inputs:
        return "nothing named"
    shown = ", ".join(run.inputs[:limit])
    rest = len(run.inputs) - limit
    return f"{shown} and {rest} more" if rest > 0 else shown


def counts_in_words(run: ImportRun) -> str:
    """The numbers a reader scans for: what changed, leaving out what did not."""
    parts: list[tuple[str, int]] = [
        ("new", run.elements_created),
        ("updated", run.elements_updated),
        ("retired", run.elements_retired),
        ("unchanged", run.elements_unchanged),
    ]
    said = ", ".join(f"{n} {word}" for word, n in parts if n)
    edges = run.relationships_created + run.relationships_updated + run.relationships_retired
    extra: list[str] = []
    if edges:
        extra.append(f"{edges} relationships")
    if run.links_loaded:
        extra.append(f"{run.links_loaded} links")
    head = f"elements: {said}" if said else "no element changed"
    return "; ".join([head, *extra])
