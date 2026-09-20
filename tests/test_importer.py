from __future__ import annotations

from pathlib import Path

from ea.importer import Mapping, import_directory


def test_sample_loads_cleanly(loaded, registry):
    assert loaded.count_elements() == 47
    assert loaded.count_relationships() == 99
    assert loaded.get_element("LDC-CURR").attrs["level"] == 2
    assert loaded.get_element("DE-SRS-ENROLMENT").attrs["includes_pii"] is True
    assert [ln.url for ln in loaded.get_links("LDC-CURR")] == ["https://example.edu/bim/curriculum"]
    # states: given columns win, the lifecycle text fills the rest
    caw = loaded.get_element("PAC-CAW")
    assert (caw.current_state, caw.target_state, caw.target_work_package) == (
        "proposed",
        "new",
        "WP-CMS-UPGRADE",
    )
    assert loaded.get_element("LDC-CURR").current_state == "live"
    assert loaded.get_element("IF-CMS-SRS").current_state == "planned"
    rel = next(r for r in loaded.relationships_of("PTC-FORMS", "out"))
    assert rel.target_state == "decommission" and rel.target_work_package == "WP-CMS-UPGRADE"


def test_reimport_updates_not_duplicates(loaded, registry):
    report = import_directory(
        loaded, registry, Path(__file__).resolve().parents[1] / "data" / "sample", "sample"
    )
    assert report.ok
    assert loaded.count_elements() == 47 and loaded.count_relationships() == 99


def test_broken_files_are_reported(backend, registry, tmp_path):
    (tmp_path / "elements.csv").write_text(
        "id,type,name,description\n"
        "E1,Data Entity,Good entity,\n"
        "E2,Unknown Type,Bad type,\n"
        "E3,Data Entity,,\n"
        "E4,Attribute,An attribute,inactive type\n"
        "E5,Information Asset,Asset,\n"
    )
    (tmp_path / "relationships.csv").write_text(
        "src_id,rel_type,dst_id,qualifier\n"
        "E1,owns,E5,\n"  # no such relationship between these types
        "E1,processes,E9,\n"  # dangling
        "E5,is associated with,E1,\n"  # wrong target type for this name
    )
    report = import_directory(backend, registry, tmp_path, "test", dry_run=True)
    codes = {i.code for i in report.issues}
    assert {
        "unknown_type",
        "missing_name",
        "inactive_type",
        "unknown_relationship_type",
        "dangling_relationship",
    } <= codes
    assert not report.ok
    assert backend.count_elements() == 0  # dry run wrote nothing
    report = import_directory(backend, registry, tmp_path, "test")
    assert backend.count_elements() == 3  # E1, E4 (flagged), E5
    assert report.elements_skipped == 2


def test_mapping_renames_columns_and_types(backend, registry, tmp_path):
    (tmp_path / "objects.csv").write_text(
        "ID,Object Type,Name,Level of Logical Data Component\nDT007,Logical Data Component,Curriculum,2\n"
    )
    m = Mapping.from_dict(
        {
            "source_system": "ea-tool",
            "files": {"elements": ["objects.csv"]},
            "elements": {
                "columns": {
                    "ID": "id",
                    "Object Type": "type",
                    "Name": "name",
                    "Level of Logical Data Component": "level",
                }
            },
        }
    )
    report = import_directory(backend, registry, tmp_path, mapping=m)
    assert report.ok and report.source_system == "ea-tool"
    e = backend.get_element("DT007")
    assert e.type_id == "logical_data_component" and e.attrs["level"] == 2 and e.source_system == "ea-tool"


def test_current_state_is_derived_from_lifecycle_text():
    from ea.importer import derive_current_state

    assert derive_current_state("Live") == "live"
    assert derive_current_state("In Production") == "live"
    assert derive_current_state("Planned") == "planned"
    assert derive_current_state("Retired 2024") == "retired"
    assert derive_current_state("Proposed") == "proposed"
    assert derive_current_state("Being built") == "live"  # unknown text: the default
    assert derive_current_state("Being built", {"Being built": "in_implementation"}) == "in_implementation"
    assert derive_current_state("") == "live"


def test_state_columns_are_validated(backend, registry, tmp_path):
    (tmp_path / "elements.csv").write_text(
        "id,type,name,description,current_state,target_state,target_work_package\n"
        "E1,Data Entity,Good entity,,live,keep,\n"
        "E2,Data Entity,Odd states,,alive,delete,WP-NOPE\n"
    )
    report = import_directory(backend, registry, tmp_path, "test")
    codes = sorted(i.code for i in report.issues)
    assert codes == ["unknown_current_state", "unknown_target_state", "unknown_work_package"]
    e = backend.get_element("E2")
    assert (e.current_state, e.target_state, e.target_work_package) == ("live", "undecided", "WP-NOPE")


def test_a_ragged_row_refuses_the_whole_file(backend, registry, tmp_path):
    """A row with more fields than the header shifts every field; the parser must not read it short."""
    (tmp_path / "elements.csv").write_text(
        "id,type,name,description\nE1,Data Entity,Good entity,fine\nE2,Data Entity,Shifted,one,two\n"
    )
    report = import_directory(backend, registry, tmp_path, "test")
    assert [i.code for i in report.issues] == ["ragged_row"]
    assert "does not match the header" in report.issues[0].message
    assert not report.ok and backend.count_elements() == 0


def test_an_empty_file_is_refused_and_named(backend, registry, tmp_path):
    (tmp_path / "elements.csv").write_text("")
    report = import_directory(backend, registry, tmp_path, "test")
    assert report.issues and report.issues[0].code == "ragged_row"
    assert "empty" in report.issues[0].message and report.issues[0].file == "elements.csv"


def test_a_ragged_upload_is_refused_the_same_way():
    """The upload page reads text rather than a path, through the same strict reader."""
    import pytest

    from ea.importer.csv_import import CsvShapeError, read_csv_text

    with pytest.raises(CsvShapeError):
        read_csv_text("id,name\nE1,one,extra\n", "elements.csv")


def test_a_links_file_on_its_own_finds_the_model(loaded, registry, tmp_path):
    """A second pass adding documentation to elements imported earlier must not call them unknown."""
    (tmp_path / "links.csv").write_text(
        "element_id,url,label\nLDC-CURR,https://example.edu/handbook,Handbook\nNOWHERE,https://example.edu/x,Lost\n"
    )
    report = import_directory(loaded, registry, tmp_path, "docs")
    assert report.ok, report.summary()
    assert [i.code for i in report.issues] == ["dangling_link"] and report.issues[0].entity == "NOWHERE"
    assert "https://example.edu/handbook" in [ln.url for ln in loaded.get_links("LDC-CURR")]


def test_a_link_that_is_not_a_web_address_is_refused_by_name(loaded, registry, tmp_path):
    """A javascript: line waiting for a click is not a link to a source, wherever it arrives from."""
    (tmp_path / "links.csv").write_text(
        "element_id,url,label\nLDC-CURR,javascript:alert(1),Trap\nLDC-CURR,mailto:owner@example.edu,Owner\n"
    )
    report = import_directory(loaded, registry, tmp_path, "docs")
    assert [i.code for i in report.issues] == ["bad_link"]
    assert "javascript:alert(1)" in report.issues[0].message
    urls = [ln.url for ln in loaded.get_links("LDC-CURR")]
    assert "mailto:owner@example.edu" in urls and not any(u.startswith("javascript:") for u in urls)


def test_a_dry_run_reports_in_the_language_of_a_check(backend, registry):
    """'0/47 loaded' reads as a shortfall; a run that never writes says what it checked."""
    report = import_directory(
        backend, registry, Path(__file__).resolve().parents[1] / "data" / "sample", "sample", dry_run=True
    )
    assert report.ok and report.dry_run
    assert "checked elements 47" in report.summary() and "loaded" not in report.summary()
    assert backend.count_elements() == 0


def test_a_links_file_adds_to_what_an_element_already_has(backend, registry, tmp_path):
    """A links file loaded on its own is a second pass, and a second pass must not delete the first.

    `set_links` replaces an element's links wholesale, so a one-row links file used to leave the
    element with that one row and nothing else — silently, and reported as a clean load.
    """
    first = tmp_path / "first"
    first.mkdir()
    (first / "elements.csv").write_text(
        "id,type,name,links\nE1,logical_data_component,One,https://a.example/1|https://a.example/2\n"
    )
    import_directory(backend, registry, first, "src", actor="t")
    assert [ln.url for ln in backend.get_links("E1")] == ["https://a.example/1", "https://a.example/2"]

    later = tmp_path / "later"
    later.mkdir()
    (later / "links.csv").write_text("element_id,url,label\nE1,https://b.example/doc,Doc\n")
    report = import_directory(backend, registry, later, "src", actor="t")
    assert report.ok
    assert [ln.url for ln in backend.get_links("E1")] == [
        "https://a.example/1",
        "https://a.example/2",
        "https://b.example/doc",
    ]


def test_an_elements_row_still_declares_its_own_links(backend, registry, tmp_path):
    """The other half of the rule: an element whose own row is in the import declares its links,
    so re-importing it with one link leaves it with one, not with both."""
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text(
        "id,type,name,links\nE1,logical_data_component,One,https://a.example/1|https://a.example/2\n"
    )
    import_directory(backend, registry, d, "src", actor="t")
    (d / "elements.csv").write_text("id,type,name,links\nE1,logical_data_component,One,https://a.example/1\n")
    import_directory(backend, registry, d, "src", actor="t")
    assert [ln.url for ln in backend.get_links("E1")] == ["https://a.example/1"]


def test_the_report_says_what_is_new_and_what_is_overwritten(backend, registry, tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text(
        "id,type,name\nE1,logical_data_component,One\nE2,logical_data_component,Two\n"
    )
    first = import_directory(backend, registry, d, "src", actor="t")
    assert (first.elements_created, first.elements_updated) == (2, 0)

    (d / "elements.csv").write_text(
        "id,type,name\nE1,logical_data_component,One renamed\nE3,logical_data_component,Three\n"
    )
    second = import_directory(backend, registry, d, "src", actor="t")
    assert (second.elements_created, second.elements_updated) == (1, 1)
    assert "1 new, 1 updated" in second.summary()


def test_a_file_written_with_another_separator_is_named_as_such(backend, registry, tmp_path):
    """A semicolon export used to parse as one column, so every row was blamed for having no id."""
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text("id;type;name\nE9;logical_data_component;Nine\n")
    report = import_directory(backend, registry, d, "semi", actor="t", dry_run=True)
    detail = " ".join(i.message for i in report.issues)
    assert "semicolon" in detail and "delimiter" in detail
    assert "missing_id" not in {i.code for i in report.issues}


def test_a_mapping_may_name_the_separator(backend, registry, tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text("id;type;name\nE9;logical_data_component;Nine\n")
    report = import_directory(backend, registry, d, "semi", Mapping(delimiter=";"), actor="t")
    assert report.ok and backend.get_element("E9").name == "Nine"


def test_issues_are_counted_in_full_and_kept_in_part(backend, registry, tmp_path):
    """A wrong header makes one issue per row; the report keeps a readable number and counts the rest,
    so `ok` and the summary stay true when the kept list is cut."""
    from ea.models import MAX_IMPORT_ISSUES

    rows = MAX_IMPORT_ISSUES + 25
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text(
        "id,type,name\n" + "".join(f"E{i},no_such_type,Name {i}\n" for i in range(rows))
    )
    report = import_directory(backend, registry, d, "src", actor="t", dry_run=True)
    assert len(report.issues) == MAX_IMPORT_ISSUES
    assert report.truncated is True
    assert report.counts["unknown_type"] == rows
    assert report.error_count == rows
    assert not report.ok
    assert f"{rows} errors" in report.summary()


def test_a_refresh_that_changes_nothing_says_so(backend, registry, tmp_path):
    """A feed re-sending its whole source every night must not read as having rewritten it.

    `upsert_elements` counts a row identical to what the branch holds as unchanged, not as
    updated, and writes nothing for it — which is also why the version does not move.
    """
    d = tmp_path / "d"
    d.mkdir()
    (d / "elements.csv").write_text(
        "id,type,name\nE1,logical_data_component,One\nE2,logical_data_component,Two\n"
    )
    first = import_directory(backend, registry, d, "src", actor="t")
    assert (first.elements_created, first.elements_updated, first.elements_unchanged) == (2, 0, 0)

    again = import_directory(backend, registry, d, "src", actor="t")
    assert (again.elements_created, again.elements_updated, again.elements_unchanged) == (0, 0, 2)
    assert again.elements_loaded == 2  # every row accounted for, none of them written
    assert "0 new, 0 updated, 2 unchanged" in again.summary()
    assert backend.get_element("E1").version == 1
