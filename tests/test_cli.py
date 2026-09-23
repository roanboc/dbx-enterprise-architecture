"""The command line refuses what it cannot do, in a sentence, before it does something worse.

These run the Typer application in-process against a database of their own, so the
refusals the browser round reads in a transcript are proved in the seconds `make check`
takes, on every change.
"""

from __future__ import annotations

import os
import sys

import pytest
from tests.conftest import PACK, SAMPLE
from typer.testing import CliRunner

from ea.backend.duckdb_backend import DuckDBBackend
from ea.cli import app, run
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack

runner = CliRunner()


@pytest.fixture(autouse=True)
def _scope_reset():
    """The command line sets the role, the branch and the organisation as context variables of
    the process, and the in-process runner never unwinds them: a scenario that ran `--as reader`
    would leave every later test a reader."""
    from ea.backend.branching import MAIN, set_branch
    from ea.backend.organisations import DEFAULT_ORG, set_org
    from ea.services.roles import DEFAULT_ROLE, set_role

    yield
    set_role(DEFAULT_ROLE)
    set_branch(MAIN)
    set_org(DEFAULT_ORG)


@pytest.fixture
def ea_env(tmp_path, monkeypatch):
    """A seeded DuckDB file the CLI finds through the environment, as a person's shell would."""
    db = tmp_path / "ea.duckdb"
    pack = load_pack(PACK)
    backend = DuckDBBackend(str(db))
    try:
        backend.save_pack(pack)
        report = import_directory(backend, Registry(pack), SAMPLE, "sample")
        assert report.ok, report.summary()
    finally:
        backend.close()
    monkeypatch.setenv("EA_DB_PATH", str(db))
    monkeypatch.setenv("EA_PACK", str(PACK))
    monkeypatch.setenv("EA_BACKEND", "duckdb")
    monkeypatch.setenv("EA_AGENT_PROVIDER", "stub")
    return tmp_path


def test_a_branch_named_on_the_command_line_has_to_exist(ea_env):
    """Writing to a branch nobody created used to land in an overlay no listing could reach."""
    result = runner.invoke(
        app, ["--branch", "nobody-made-this", "set", "DE-SRS-COURSE", "--status", "approved"]
    )
    assert result.exit_code == 1
    assert "no branch with id 'nobody-made-this'" in result.output and "ea branch create" in result.output


def test_a_search_that_matches_nothing_says_so(ea_env):
    result = runner.invoke(app, ["find", "zzqxnothinghere"])
    assert result.exit_code == 0 and "nothing matches 'zzqxnothinghere'" in result.output


def test_an_unknown_type_filter_is_refused_rather_than_ignored(ea_env):
    """Ignoring it would answer the unrestricted search and look like a narrow one."""
    result = runner.invoke(app, ["find", "course", "--type", "no_such_type"])
    assert result.exit_code == 1 and "no element type 'no_such_type'" in result.output


def test_set_with_nothing_to_set_is_refused(ea_env):
    result = runner.invoke(app, ["set", "DE-SRS-COURSE"])
    assert result.exit_code == 1 and "nothing to set" in result.output


def test_a_value_the_command_does_not_offer_is_refused_by_name(ea_env):
    fmt = runner.invoke(app, ["health", "--fmt", "xml"])
    assert fmt.exit_code == 1 and "--fmt is 'table' or 'md', not 'xml'" in fmt.output
    direction = runner.invoke(app, ["neighbours", "DE-SRS-COURSE", "--direction", "sideways"])
    assert direction.exit_code == 1 and "--direction is 'in', 'out' or 'both'" in direction.output


def test_export_pack_refuses_before_it_opens_the_destination(ea_env):
    """A pack id the database does not hold must not cost the reader the file they were writing over."""
    out = ea_env / "pack.yaml"
    out.write_text("the reader's own pack\n")
    result = runner.invoke(app, ["export-pack", str(out), "--pack-id", "no_such_pack"])
    assert result.exit_code == 1 and "no metamodel version 'no_such_pack'" in result.output
    assert out.read_text() == "the reader's own pack\n"


def test_import_says_which_of_three_things_is_wrong_with_a_directory(ea_env):
    missing = runner.invoke(app, ["import", str(ea_env / "nowhere")])
    assert missing.exit_code == 1 and "does not exist" in missing.output
    a_file = ea_env / "just-a-file.csv"
    a_file.write_text("id\n")
    not_dir = runner.invoke(app, ["import", str(a_file)])
    assert not_dir.exit_code == 1 and "is a file, not a directory" in not_dir.output


def test_init_that_cannot_read_its_pack_leaves_no_database_behind(ea_env):
    bad_pack = ea_env / "broken.yaml"
    bad_pack.write_text("not: [a pack\n")
    fresh = ea_env / "fresh.duckdb"
    result = runner.invoke(app, ["init", "--db", str(fresh), "--pack", str(bad_pack)])
    assert result.exit_code != 0
    assert not fresh.exists()


def test_what_the_repository_refuses_reaches_the_reader_as_a_sentence(ea_env, monkeypatch, capsys):
    """The entry point turns a NotFoundError into its message and a failed exit, not a stack trace."""
    monkeypatch.setattr(sys, "argv", ["ea", "get", "DE-NOPE"])
    with pytest.raises(SystemExit) as exit_info:
        run()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "no element with id DE-NOPE"
    assert "Traceback" not in captured.err


def test_loading_a_pack_is_the_metamodel_owners_write(ea_env, monkeypatch, capsys):
    """`ea init` and `ea load-pack` replace the metamodel, which only an Admin may do in the app;
    the command line used to accept them from any role."""
    for role, sentence in (
        ("reader", "A Reader may not load a metamodel pack"),
        ("architect", "An Architect may not load a metamodel pack"),
        ("reviewer", "A Reviewer may not load a metamodel pack"),
    ):
        monkeypatch.setattr(sys, "argv", ["ea", "--as", role, "load-pack", str(PACK)])
        with pytest.raises(SystemExit) as exit_info:
            run()
        assert exit_info.value.code == 1 and capsys.readouterr().err.strip() == sentence
    monkeypatch.setattr(sys, "argv", ["ea", "--as", "architect", "init", "--pack", str(PACK)])
    with pytest.raises(SystemExit) as exit_info:
        run()
    assert (
        exit_info.value.code == 1 and "An Architect may not load a metamodel pack" in capsys.readouterr().err
    )
    assert runner.invoke(app, ["--as", "admin", "load-pack", str(PACK)]).exit_code == 0


def test_organisations_and_versions_from_the_command_line(ea_env):
    """The sandbox flow, end to end: copy the default, draft, apply, compare, check, publish."""
    assert "default" in runner.invoke(app, ["org", "list"]).output
    created = runner.invoke(app, ["org", "create", "Trial", "--copy-from", "default"])
    assert created.exit_code == 0 and "47 elements and 99 relationships copied from default" in created.output
    assert "47 elements" in runner.invoke(app, ["--org", "trial", "stats"]).output
    unknown = runner.invoke(app, ["--org", "nowhere", "stats"])
    assert unknown.exit_code == 1 and "no organisation with id 'nowhere'" in unknown.output
    draft = runner.invoke(app, ["metamodel", "draft", "higher_education@2026-08-11", "--version", "t1"])
    assert draft.exit_code == 0 and "draft higher_education@t1 created" in draft.output
    assert "higher_education@t1" in runner.invoke(app, ["metamodel", "versions"]).output
    applied = runner.invoke(app, ["org", "apply", "trial", "higher_education@t1"])
    assert applied.exit_code == 0 and "0 errors" in applied.output
    assert "trial-1" not in runner.invoke(app, ["org", "list"]).output
    diff = runner.invoke(app, ["metamodel", "diff", "higher_education@2026-08-11", "higher_education@t1"])
    assert diff.exit_code == 0 and "define the same metamodel" in diff.output
    check = runner.invoke(app, ["metamodel", "check", "higher_education@t1", "--org", "default"])
    assert check.exit_code == 0 and "0 errors" in check.output
    assert runner.invoke(app, ["metamodel", "publish", "higher_education@t1"]).exit_code == 0
    # A refusal the services raise reaches the shell as a sentence through `run()`; the in-process
    # runner hands the exception back instead, so it is read from there.
    retire = runner.invoke(app, ["metamodel", "retire", "higher_education@t1"])
    assert retire.exit_code == 1 and "applied by trial" in str(retire.exception)
    assert runner.invoke(app, ["org", "default", "trial"]).exit_code == 0
    assert runner.invoke(app, ["org", "rename", "trial", "Trial two"]).exit_code == 0
    deleted = runner.invoke(app, ["org", "delete", "default"])
    assert deleted.exit_code == 0
    assert runner.invoke(app, ["org", "delete", "trial"]).exit_code == 1  # the default stays
    as_reader = runner.invoke(app, ["--as", "reader", "org", "create", "No"])
    assert as_reader.exit_code == 1 and "A Reader may not create an organisation" in str(as_reader.exception)


def test_loading_a_file_stores_a_version_and_applies_it(ea_env, tmp_path):
    from ea.metamodel import dump_pack, load_pack

    pack = load_pack(PACK)
    pack.version, pack.status, pack.notes = "from-file", "draft", "edited outside"
    path = tmp_path / "next.yaml"
    dump_pack(pack, path)
    result = runner.invoke(app, ["load-pack", str(path)])
    assert result.exit_code == 0 and "now applies higher_education@from-file" in result.output
    assert "from-file" in runner.invoke(app, ["org", "list"]).output
    exported = tmp_path / "out.yaml"
    assert (
        runner.invoke(app, ["export-pack", str(exported), "-v", "higher_education@from-file"]).exit_code == 0
    )
    assert "edited outside" in exported.read_text()
    # the published version cannot be replaced by a file that differs from it
    pack.version, pack.status = "2026-08-11", "published"
    pack.element_types[0].description = "changed"
    dump_pack(pack, path)
    refused = runner.invoke(app, ["load-pack", str(path)])
    assert refused.exit_code == 1 and "frozen" in str(refused.exception)


def test_every_command_group_is_registered_before_the_entry_point():
    """`python -m ea.cli` runs the module top to bottom, so a group declared after the
    `__main__` block does not exist by the time the arguments are read.

    That is not theoretical: `feed` was added at the end of the file and vanished from
    `python -m ea.cli` while still working through the console script, which is the kind of
    difference nothing else here would have caught.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "ea" / "cli.py"
    text = source.read_text(encoding="utf-8")
    guard = text.index('if __name__ == "__main__":')
    after = text[guard:]
    assert "add_typer" not in after, "a command group is registered after the entry point"
    assert "@app.command" not in after, "a command is declared after the entry point"


def test_the_feed_commands_are_reachable_as_a_module():
    """The way the command-line scenarios invoke it, which is not the console script."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "ea.cli", "feed", "--help"],
        cwd=root,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for command in ("list", "save", "run", "delete"):
        assert command in proc.stdout, command


def test_the_runs_commands_are_reachable_as_a_module():
    """`runs` was added after `feed`, at the same end of the same file, for the same reason."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "ea.cli", "runs", "--help"],
        cwd=root,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for command in ("list", "show"):
        assert command in proc.stdout, command


def test_the_history_lists_the_import_that_seeded_this_store(ea_env):
    """The fixture seeds by importing a directory, so there is exactly one run to find."""
    listed = runner.invoke(app, ["runs", "list"])
    assert listed.exit_code == 0, listed.output
    assert "sample" in listed.output and "command" in listed.output
    assert "elements.csv" in listed.output


def test_one_run_is_read_in_full_by_its_identifier(ea_env):
    listed = runner.invoke(app, ["runs", "list"])
    run_id = listed.output.split()[0]
    shown = runner.invoke(app, ["runs", "show", run_id])
    assert shown.exit_code == 0, shown.output
    assert run_id in shown.output and "branch  : main" in shown.output
    assert "read    :" in shown.output and "did     :" in shown.output


def test_a_run_nobody_made_is_refused_by_name(ea_env):
    shown = runner.invoke(app, ["runs", "show", "run-nothing"])
    assert shown.exit_code == 1 and "no run 'run-nothing'" in shown.output


def test_an_empty_history_says_so_rather_than_printing_nothing(ea_env, tmp_path, monkeypatch):
    """A blank answer reads as a broken command; 'nothing has run yet' reads as an answer."""
    empty = tmp_path / "empty.duckdb"
    backend = DuckDBBackend(str(empty))
    try:
        backend.save_pack(load_pack(PACK))
    finally:
        backend.close()
    monkeypatch.setenv("EA_DB_PATH", str(empty))

    listed = runner.invoke(app, ["runs", "list"])
    assert listed.exit_code == 0 and "No imports have been recorded yet." in listed.output


def test_a_silent_history_says_which_silence_it_is(ea_env):
    """'Nothing has ever run' and 'this feed has not run' are different answers."""
    for_a_feed = runner.invoke(app, ["runs", "list", "--feed", "no-such-feed"])
    assert for_a_feed.exit_code == 0
    assert "No runs recorded for feed 'no-such-feed'" in for_a_feed.output

    past_the_end = runner.invoke(app, ["runs", "list", "--offset", "500"])
    assert past_the_end.exit_code == 0 and "No runs on this page" in past_the_end.output


def test_the_history_holds_one_page_a_request_however_much_is_asked_for(ea_env):
    """A history only grows, so `--limit 1000000` is answered with a page and an offset."""
    from ea import capacity

    big = runner.invoke(app, ["runs", "list", "--limit", "1000000"])
    assert big.exit_code == 0
    assert f"--limit is held to {capacity.READ_CHUNK} a request" in big.output
    assert "--offset" in big.output


def test_what_a_run_kept_and_what_was_printed_are_not_reported_as_the_same_thing(ea_env):
    listed = runner.invoke(app, ["runs", "list"])
    run_id = listed.output.split()[0]
    shown = runner.invoke(app, ["runs", "show", run_id, "--issues", "0"])
    assert shown.exit_code == 0
    # the seeded import is clean, so there is nothing to miscount — the line must not appear
    assert "not kept with the run" not in shown.output


def test_a_directory_import_keeps_the_mapping_it_was_given(ea_env, tmp_path):
    """A run says what the columns meant then; the file is free to say something else later."""
    mapping = tmp_path / "m.yaml"
    mapping.write_text('id_prefix: "MX-"\n', encoding="utf-8")
    loaded = runner.invoke(app, ["import", str(SAMPLE), "--source", "mapped", "--mapping", str(mapping)])
    assert loaded.exit_code in (0, 1), loaded.output

    listed = runner.invoke(app, ["runs", "list", "--limit", "1"])
    shown = runner.invoke(app, ["runs", "show", listed.output.split()[0]])
    assert shown.exit_code == 0 and "MX-" in shown.output


def test_find_narrows_by_every_criterion_and_says_when_it_cut_the_list(ea_env):
    """The command offered two of the criteria its own service accepted."""
    result = runner.invoke(
        app, ["find", "--type", "physical_application_component", "--current-state", "live"]
    )
    assert result.exit_code == 0 and "PAC-CMS" in result.output
    # a criterion the rows do not meet empties it, rather than being ignored
    narrowed = runner.invoke(
        app, ["find", "--type", "physical_application_component", "--current-state", "non_existent"]
    )
    assert narrowed.exit_code == 0 and "those filters" in narrowed.output
    # a cut list says it was cut and how to read on
    paged = runner.invoke(app, ["find", "--limit", "3"])
    assert "--offset 3 reads on" in paged.output


def test_find_writes_json_and_csv_for_a_script(ea_env):
    import json as _json

    as_json = runner.invoke(app, ["find", "curriculum", "--limit", "2", "--json"])
    assert as_json.exit_code == 0
    rows = _json.loads(as_json.output)
    assert rows and {"element_id", "name", "type_id", "matched_in"} <= set(rows[0])

    as_csv = runner.invoke(app, ["find", "curriculum", "--limit", "2", "--csv"])
    assert as_csv.exit_code == 0 and as_csv.output.splitlines()[0].startswith("element_id,name,type")


def test_find_refuses_an_unreadable_date_rather_than_ignoring_it(ea_env):
    result = runner.invoke(app, ["find", "--updated-since", "last tuesday"])
    assert result.exit_code == 1 and "--updated-since must be an ISO date" in result.output


def test_set_exits_non_zero_when_every_element_was_refused(ea_env):
    """Exit 0 with nothing updated tells a script the edit was applied."""
    result = runner.invoke(app, ["set", "NO-SUCH-1", "--status", "approved"])
    assert result.exit_code == 1 and "updated 0, refused 1" in result.output


def test_configuring_a_feed_needs_the_role_the_page_needs(ea_env):
    """The page hid the form from a Reader; the command line offered the same write to anybody."""
    result = runner.invoke(app, ["--as", "reader", "feed", "save", "Nightly", "--source", "cmdb"])
    assert result.exit_code == 1 and "A Reader may not configure a feed" in str(result.exception)
    gone = runner.invoke(app, ["--as", "reader", "feed", "delete", "whatever"])
    assert gone.exit_code == 1 and "A Reader may not delete a feed" in str(gone.exception)


def test_clearing_an_attribute_says_so_rather_than_writing_a_blank(ea_env):
    blank = runner.invoke(app, ["set", "PAC-CMS", "--attr", "owner"])
    assert blank.exit_code == 1 and "--clear-attr" in blank.output
