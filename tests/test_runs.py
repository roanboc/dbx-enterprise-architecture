"""Import history: what a run was, kept after the request that ran it has gone (`DOBJ3.7`).

Every test here runs on both engines. A run is recorded by the importer rather than by each of
the three things that start one, so what is proved on one path holds on all three.

What these tests are careful about is the difference between a run's *sample* of issues and its
*counts* of them. The sample is bounded because a run is kept forever; the counts are complete.
A test that read the totals off the sample would pass while the screen lied.
"""

from __future__ import annotations

import pandas as pd
import pytest
from tests.conftest import SAMPLE

from ea.backend.branching import MAIN, use_branch
from ea.backend.organisations import use_org
from ea.backend.sql import staging_schema
from ea.importer import Feed, Mapping, import_directory, run_feed
from ea.importer.csv_import import import_frames
from ea.importer.feeds import run_configured_feed
from ea.importer.runs import counts_in_words, describe_inputs, issue_sample, recorded
from ea.models import Forbidden, ImportReport, Issue, SourceFeed
from ea.services import BranchService, OrganisationService
from ea.services.roles import use_role


def _land(backend, table: str, columns: str, *rows: str) -> None:
    """Rows where a source would leave them — in the schema this store actually uses."""
    where = f"{staging_schema(backend.schema_prefix)}.{table}"
    backend._execute(f"CREATE TABLE {where} ({columns})")
    for row in rows:
        backend._execute(f"INSERT INTO {where} VALUES ({row})")


#: The three columns the contract needs of an elements table, and nothing else.
COLUMNS = "id VARCHAR, type VARCHAR, name VARCHAR"


def _an_element(eid: str = "E1") -> str:
    return f"'{eid}','data_entity','{eid}'"


def _empty(source: str) -> ImportReport:
    return ImportReport(source_system=source)


# ---------------------------------------------------------- what a run records
def test_a_directory_import_is_recorded_with_what_it_read_and_what_it_did(backend, registry):
    report = import_directory(backend, registry, SAMPLE, "sample", actor="alice")

    runs = backend.runs(10, 0)
    assert len(runs) == 1
    run = runs[0]
    assert run.trigger == "command" and run.actor == "alice" and run.source_system == "sample"
    assert run.status == "ok" and run.branch_id == MAIN
    assert run.elements_created == report.elements_created
    assert run.relationships_created == report.relationships_created
    assert run.links_loaded == report.links_loaded
    # What it read is named, not counted: a reader wants to know which files these numbers are of.
    assert run.inputs and all(name.endswith(".csv") for name in run.inputs)
    assert run.summary == report.summary()
    assert run.started_at is not None and run.finished_at is not None


def test_a_dry_run_records_nothing(backend, registry):
    """It wrote nothing. A history of things that did not happen is a history nobody can read."""
    import_directory(backend, registry, SAMPLE, "sample", dry_run=True)
    assert backend.count_runs() == 0 and backend.runs(10, 0) == []


def test_a_run_that_was_refused_is_recorded_as_stopped(backend, registry):
    """The run a reader most wants to find is the one that failed, so it is the one kept hardest."""
    with use_role("reader"), pytest.raises(Forbidden):
        import_directory(backend, registry, SAMPLE, "sample", actor="rita")

    runs = backend.runs(10, 0)
    assert len(runs) == 1
    assert runs[0].status == "failed" and "may not" in runs[0].message
    assert runs[0].elements_created == 0 and runs[0].summary == ""


def test_the_run_of_a_frozen_branch_says_why_it_stopped(backend, registry):
    branch = BranchService(backend, registry).create("frozen", "t")
    backend.set_branch_status(branch.branch_id, "in_review", "t")
    with use_branch(branch.branch_id), pytest.raises(Forbidden):
        import_directory(backend, registry, SAMPLE, "sample")

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and run.branch_id == branch.branch_id
    assert "frozen" in run.message


# ------------------------------------------------------------------ a feed's run
def test_a_feed_run_carries_the_feed_and_the_branch_the_feed_names(backend, registry):
    _land(backend, "cmdb_elements", COLUMNS, _an_element("1001"))
    branch = BranchService(backend, registry).create("cmdb-intake", "t")
    feed = backend.save_feed(
        SourceFeed(
            name="CMDB",
            source_system="cmdb",
            elements_table="cmdb_elements",
            target_branch=branch.branch_id,
        ),
        "t",
    )

    run_configured_feed(backend, registry, feed.feed_id, actor="scheduler")

    run = backend.runs(10, 0)[0]
    assert run.trigger == "feed" and run.feed_id == feed.feed_id and run.feed_name == "CMDB"
    assert run.actor == "scheduler" and run.elements_created == 1
    # The branch is the feed's own, not whatever the caller happened to be on.
    assert run.branch_id == branch.branch_id
    assert run.inputs == ["cmdb_elements"]


def test_the_history_outlives_the_feed_that_made_it(backend, registry):
    """A feed deleted six months from now must not take the account of its loads with it."""
    _land(backend, "cmdb_elements", COLUMNS, _an_element())
    feed = backend.save_feed(
        SourceFeed(name="CMDB", source_system="cmdb", elements_table="cmdb_elements"), "t"
    )
    run_configured_feed(backend, registry, feed.feed_id, actor="t")

    backend.delete_feed(feed.feed_id, "t")

    assert backend.get_feed(feed.feed_id) is None
    run = backend.runs(10, 0)[0]
    assert run.feed_id == feed.feed_id and run.feed_name == "CMDB"


def test_a_feeds_own_history_is_asked_for_by_itself(backend, registry):
    for name in ("a", "b"):
        _land(backend, f"{name}_elements", COLUMNS, _an_element(name.upper()))
    a = backend.save_feed(SourceFeed(name="A", source_system="a", elements_table="a_elements"), "t")
    b = backend.save_feed(SourceFeed(name="B", source_system="b", elements_table="b_elements"), "t")
    run_configured_feed(backend, registry, a.feed_id, actor="t")
    run_configured_feed(backend, registry, b.feed_id, actor="t")

    assert backend.count_runs() == 2
    assert backend.count_runs(a.feed_id) == 1
    assert [r.feed_name for r in backend.runs(10, 0, a.feed_id)] == ["A"]
    assert backend.count_runs("no-such-feed") == 0


# ------------------------------------------------------------------ issues kept
def test_the_sample_keeps_the_errors_and_the_counts_keep_everything(backend):
    """Five errors behind five hundred warnings must not fall off the end of the sample."""
    report = _empty("s")
    for i in range(20):
        report.add_issue(Issue("warning", "soft", f"warning {i}", row=i))
    report.add_issue(Issue("error", "hard", "the one that matters", row=99))

    with recorded(backend, trigger="command", actor="t") as run:
        run.report = report

    kept = backend.runs(10, 0)[0]
    assert kept.status == "errors"
    assert kept.issues[0].level == "error" and kept.issues[0].message == "the one that matters"
    assert kept.error_count == 1 and kept.warning_count == 20
    assert kept.issue_counts == {"soft": 20, "hard": 1}


def test_the_sample_is_bounded_and_the_totals_are_not(backend):
    report = _empty("s")
    for i in range(300):
        report.add_issue(Issue("warning", "soft", f"warning {i}", row=i))

    with recorded(backend, trigger="command", actor="t") as run:
        run.report = report

    kept = backend.runs(10, 0)[0]
    assert len(kept.issues) == 200 and kept.truncated is True
    assert kept.warning_count == 300 and sum(kept.issue_counts.values()) == 300


def test_issue_sample_orders_by_level_then_by_when_it_was_found():
    issues = [
        Issue("warning", "w", "first warning"),
        Issue("error", "e", "first error"),
        Issue("info", "i", "a note"),
        Issue("error", "e", "second error"),
    ]
    assert [i.message for i in issue_sample(issues, keep=3)] == [
        "first error",
        "second error",
        "first warning",
    ]


# ------------------------------------------------------------ reading the history
def test_the_history_reads_newest_first_a_page_at_a_time(backend):
    for i in range(5):
        with recorded(backend, trigger="command", actor="t", source_system=f"s{i}") as run:
            run.report = _empty(f"s{i}")

    assert backend.count_runs() == 5
    first = backend.runs(2, 0)
    assert [r.source_system for r in first] == ["s4", "s3"]
    assert [r.source_system for r in backend.runs(2, 2)] == ["s2", "s1"]
    assert len(backend.runs(2, 4)) == 1
    assert backend.get_run(first[0].run_id).source_system == "s4"
    assert backend.get_run("no-such-run") is None


def test_a_run_belongs_to_its_organisation(backend, registry):
    orgs = OrganisationService(backend)
    other = orgs.create("second", "t")
    import_directory(backend, registry, SAMPLE, "sample")

    with use_org(other.org_id):
        assert backend.count_runs() == 0
    assert backend.count_runs() == 1


def test_the_history_survives_the_organisation_it_belonged_to(backend):
    """The audit trail answers what happened, and it did happen."""
    orgs = OrganisationService(backend)
    other = orgs.create("second", "t")
    with use_org(other.org_id):
        with recorded(backend, trigger="command", actor="t", source_system="gone") as run:
            run.report = _empty("gone")
        assert backend.count_runs() == 1

    orgs.delete(other.org_id, "t")

    # `use_org` is the context variable, not a check that the organisation is still there —
    # which is what makes the audit trail readable after the organisation has gone.
    with use_org(other.org_id):
        assert backend.count_runs() == 1
        assert backend.list_feeds() == []


# ------------------------------------------------------------------ what it read
def test_an_upload_records_the_files_it_was_given(backend, registry):
    frame = pd.DataFrame([{"id": "U1", "type": "data_entity", "name": "By hand"}])
    frames = {"elements": [("elements.csv", frame)], "relationships": [], "links": []}
    with recorded(
        backend, trigger="upload", actor="bob", source_system="hand", inputs=["elements.csv"]
    ) as run:
        run.report = import_frames(backend, registry, frames, "hand", Mapping(), "bob")

    kept = backend.runs(10, 0)[0]
    assert kept.trigger == "upload" and kept.inputs == ["elements.csv"] and kept.actor == "bob"
    assert kept.elements_created == 1


def test_an_ad_hoc_feed_run_is_not_a_configured_one_and_records_nothing(backend, registry):
    """`run_feed` takes a feed nobody stored. What is recorded is a *configured* source's run."""
    _land(backend, "loose_elements", COLUMNS, _an_element())
    run_feed(backend, registry, Feed("loose", tables={"elements": "loose_elements"}), actor="t")
    assert backend.count_runs() == 0


# --------------------------------------------------------------- what it reads as
def test_what_a_run_did_is_said_without_the_numbers_that_are_zero(backend):
    with recorded(backend, trigger="command", actor="t", source_system="s", inputs=["a.csv"]) as run:
        report = _empty("s")
        report.elements_created, report.elements_unchanged, report.links_loaded = 3, 1, 2
        run.report = report

    kept = backend.runs(10, 0)[0]
    said = counts_in_words(kept)
    assert "3 new" in said and "1 unchanged" in said and "2 links" in said
    assert "updated" not in said and "retired" not in said
    assert describe_inputs(kept) == "a.csv"


def test_many_inputs_are_named_up_to_a_point_and_then_counted():
    from ea.models import ImportRun

    run = ImportRun(inputs=["a.csv", "b.csv", "c.csv", "d.csv", "e.csv"])
    assert describe_inputs(run) == "a.csv, b.csv, c.csv and 2 more"
    assert describe_inputs(ImportRun()) == "nothing named"


def test_a_store_that_cannot_take_the_row_does_not_replace_the_failure_it_was_recording(backend):
    """The caller needs the import's own exception, not the one the audit trail raised over it."""

    def refuse(_run):
        raise RuntimeError("the store is not taking rows")

    backend.record_run = refuse
    with pytest.raises(ValueError, match="what the caller must see"):
        with recorded(backend, trigger="command", actor="t"):
            raise ValueError("what the caller must see")
