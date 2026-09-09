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
