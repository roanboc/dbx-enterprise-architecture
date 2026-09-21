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


def test_a_caller_who_may_not_import_at_all_writes_no_history(backend, registry):
    """A refusal at the door is not a run.

    Recording it would make the history the one thing the one principal `allowed()` denies
    every write to could fill at will, a row of free text at a time."""
    for _ in range(3):
        with use_role("reader"), pytest.raises(Forbidden):
            import_directory(backend, registry, SAMPLE, "sample", actor="mallory")

    assert backend.count_runs() == 0


def test_the_run_of_a_frozen_branch_says_why_it_stopped(backend, registry):
    branch = BranchService(backend, registry).create("frozen", "t")
    backend.set_branch_status(branch.branch_id, "in_review", "t")
    with use_branch(branch.branch_id), pytest.raises(Forbidden):
        import_directory(backend, registry, SAMPLE, "sample")

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and run.branch_id == branch.branch_id
    assert "frozen" in run.message


def test_a_refusal_of_state_is_recorded_because_the_caller_may_import(backend, registry):
    """`main` refused to an architect is not the same as a reader refused everything.

    The architect may load content; what stopped them is where they were pointing. That is a
    run, and the history is where they find out it did not land."""
    with use_role("architect"), pytest.raises(Forbidden):
        import_directory(backend, registry, SAMPLE, "sample", actor="alex")

    runs = backend.runs(10, 0)
    assert len(runs) == 1
    assert runs[0].status == "failed" and runs[0].actor == "alex"
    assert "main" in runs[0].message and runs[0].branch_id == MAIN


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


def test_an_organisations_history_goes_with_the_organisation(backend):
    """Kept rows would come back as the next organisation's own.

    An org_id is free to be taken again once its organisation is deleted, and every read of the
    history scopes by org_id alone. A run carries the actor names, the file names, the issue
    messages and the whole mapping of the organisation that is gone, so keeping it would hand
    all of that to whoever takes the identifier next."""
    orgs = OrganisationService(backend)
    other = orgs.create("second", "t")
    with use_org(other.org_id):
        with recorded(backend, trigger="command", actor="t", source_system="gone") as run:
            run.report = _empty("gone")
        backend.save_feed(SourceFeed(name="Gone", source_system="gone"), "t")
        assert backend.count_runs() == 1 and len(backend.list_feeds()) == 1

    orgs.delete(other.org_id, "t")

    with use_org(other.org_id):
        assert backend.count_runs() == 0
        # the feed goes too: it used to be left behind, because it was in no table group
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


# --------------------------------------------------- what a run says when it stopped
def test_a_load_that_stops_half_way_is_recorded_with_what_it_had_already_written(
    backend, registry, monkeypatch
):
    """Elements land, then relationships, then links, with no transaction around the three.

    A recorder waiting for the return value would record zeros over rows that are in the store,
    which is the one thing an account of a run must not do."""

    def fall_over(*_args, **_kwargs):
        raise RuntimeError("the connection went away")

    monkeypatch.setattr(backend, "upsert_relationships", fall_over)
    with pytest.raises(RuntimeError):
        import_directory(backend, registry, SAMPLE, "sample", actor="t")

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and "the connection went away" in run.message
    # the elements the first step wrote are in the store, and the run says so
    assert run.elements_created > 0
    assert len(backend.elements_by_ids([e.element_id for e in backend.find_elements(limit=5)])) > 0


def test_a_run_interrupted_by_hand_is_recorded(backend):
    """Ctrl-C during a long import leaves whatever had landed. That is a run, not a non-event."""
    with pytest.raises(KeyboardInterrupt):
        with recorded(backend, trigger="command", actor="t", source_system="s"):
            raise KeyboardInterrupt

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and "KeyboardInterrupt" in run.message


def test_a_feed_whose_mapping_will_not_read_is_recorded_and_its_card_says_so(backend, registry):
    """A mapping is stored without being parsed, so a feed can be configured with YAML that
    will not read. The nightly run that has been failing since Tuesday is the one to find."""
    feed = backend.save_feed(
        SourceFeed(name="Broken", source_system="broken", mapping_yaml="id_prefix: [unclosed\n"), "t"
    )
    with pytest.raises(Exception, match="(?i)yaml|mapping|scan|pars"):
        run_configured_feed(backend, registry, feed.feed_id, actor="scheduler")

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and run.feed_id == feed.feed_id
    # and the card cannot go on saying nothing while the history says it failed
    assert backend.get_feed(feed.feed_id).last_run_status == "failed"


def test_a_feed_that_ran_cleanly_says_ok_on_its_card(backend, registry):
    _land(backend, "ok_elements", COLUMNS, _an_element())
    feed = backend.save_feed(SourceFeed(name="Fine", source_system="fine", elements_table="ok_elements"), "t")
    run_configured_feed(backend, registry, feed.feed_id, actor="t")
    assert backend.get_feed(feed.feed_id).last_run_status == "ok"


# ------------------------------------------------------------- reading a row back
def test_a_file_name_with_a_newline_in_it_is_one_file_on_the_way_back(backend):
    """A separator would have turned one file into two. POSIX allows the newline."""
    with recorded(backend, trigger="command", actor="t", inputs=["elements\n-final.csv", "links.csv"]) as run:
        run.report = _empty("s")

    assert backend.runs(10, 0)[0].inputs == ["elements\n-final.csv", "links.csv"]


def test_one_unreadable_row_does_not_take_the_whole_history_with_it(backend):
    """A row written by a version whose `Issue` had one more field must still read."""
    with recorded(backend, trigger="command", actor="t", source_system="older") as run:
        report = _empty("older")
        report.add_issue(Issue("error", "c", "m"))
        run.report = report
    run_id = backend.runs(1, 0)[0].run_id
    backend._execute(
        "UPDATE import_run SET issues_json = ?, issue_counts_json = ? WHERE run_id = ?",
        ['[{"level":"error","code":"c","message":"m","severity":"high"}]', '{"c": "not a number"}', run_id],
    )

    kept = backend.get_run(run_id)
    assert [i.code for i in kept.issues] == ["c"]  # the field it does not know is dropped
    assert kept.issue_counts == {}  # and a count that is not one is skipped, not raised over
    assert len(backend.runs(10, 0)) == 1


def test_a_feed_that_stops_half_way_is_recorded_with_what_it_had_already_written(
    backend, registry, monkeypatch
):
    """The file paths hand a report in so partial counts survive; a feed has to do the same."""
    _land(backend, "half_elements", COLUMNS, _an_element("H1"), _an_element("H2"))
    _land(
        backend,
        "half_relationships",
        "src_id VARCHAR, rel_type VARCHAR, dst_id VARCHAR",
        "'H1','encapsulates','H2'",
    )
    feed = backend.save_feed(
        SourceFeed(
            name="Half",
            source_system="half",
            elements_table="half_elements",
            relationships_table="half_relationships",
        ),
        "t",
    )

    def fall_over(*_args, **_kwargs):
        raise RuntimeError("the connection went away")

    monkeypatch.setattr(backend, "upsert_relationships", fall_over)
    with pytest.raises(RuntimeError):
        run_configured_feed(backend, registry, feed.feed_id, actor="scheduler")

    run = backend.runs(10, 0)[0]
    assert run.status == "failed" and run.feed_id == feed.feed_id
    assert run.elements_created == 2, "the elements the first step wrote are not in the run"


def test_a_feed_that_names_a_table_that_is_not_there_still_reports_it(backend, registry):
    """The staging read's own issues have to survive the report being handed in, not replaced."""
    feed = backend.save_feed(
        SourceFeed(name="Absent", source_system="absent", elements_table="never_created"), "t"
    )
    report = run_configured_feed(backend, registry, feed.feed_id, actor="t")

    assert [i.code for i in report.issues] == ["no_staging_table"]
    assert backend.runs(10, 0)[0].issue_counts == {"no_staging_table": 1}
