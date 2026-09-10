"""The command line refuses what it cannot do, in a sentence, before it does something worse.

These run the Typer application in-process against a database of their own, so the
refusals the browser round reads in a transcript are proved in the seconds `make check`
takes, on every change.
"""

from __future__ import annotations

import sys

import pytest
from tests.conftest import PACK, SAMPLE
from typer.testing import CliRunner

from ea.backend.duckdb_backend import DuckDBBackend
from ea.cli import app, run
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack

runner = CliRunner()


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
    assert result.exit_code == 0 and "no elements match 'zzqxnothinghere'" in result.output


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
    assert result.exit_code == 1 and "no pack with id 'no_such_pack'" in result.output
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
