"""The export is the import's inverse: what it writes, the importer reads back unchanged."""

from __future__ import annotations

import csv
import zipfile
from io import BytesIO
from pathlib import Path

from ea.importer import export_archive, export_directory, import_directory

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


def _snapshot(backend):
    """Everything a round trip has to preserve, for every element and every edge."""
    elements = {
        e.element_id: (
            e.type_id,
            e.name,
            e.key,
            e.description_md,
            e.status,
            e.lifecycle_status,
            e.current_state,
            e.target_state,
            e.target_work_package,
            e.target_note,
            e.source_system,
            e.source_ref,
            e.origin,
            tuple(sorted((e.attrs or {}).items())),
            tuple((ln.url, ln.label or "") for ln in backend.get_links(e.element_id)),
        )
        for e in backend.find_elements(limit=10_000)
    }
    relationships = {
        r.relationship_id: (
            r.rel_type_id,
            r.src_id,
            r.dst_id,
            r.qualifier,
            r.status,
            r.current_state,
            r.target_state,
            r.source_system,
        )
        for r in backend.find_relationships(limit=10_000)
    }
    return elements, relationships


def test_an_export_reimports_onto_the_same_model(loaded, registry, fresh_backend, tmp_path):
    """Sample in, exported out, imported into an empty store: the same model, not a copy beside it.

    The relationship ids matching is the part worth stating: identity is derived from the source
    system, so without `source_system` on the row a re-import would duplicate every edge.
    """
    counts = export_directory(loaded, registry, tmp_path / "out")
    assert (counts["elements"], counts["relationships"], counts["links"]) == (47, 99, 6)
    assert counts["schema"] > 0  # the reference file, which is not itself imported back

    report = import_directory(fresh_backend, registry, tmp_path / "out", "", actor="t")
    assert report.ok and report.elements_loaded == 47 and report.relationships_loaded == 99

    assert _snapshot(loaded) == _snapshot(fresh_backend)


def test_a_markdown_description_with_a_mermaid_diagram_survives(backend, registry, fresh_backend, tmp_path):
    """A description holding a fenced Mermaid diagram is commas, quotes, braces and newlines in
    one cell — the shape a CSV is most often accused of mangling."""
    description = (
        "Curriculum, the logical area.\n\n"
        'It has commas, "quotes" and a fence.\n\n'
        "```mermaid\ngraph TD\n"
        '  A["Course [DE-COURSE]"] --> B["Offering, v2"]\n'
        '  B --> C{"Decision?"}\n'
        "```"
    )
    d = tmp_path / "in"
    d.mkdir()
    import csv as _csv

    with open(d / "elements.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["id", "type", "name", "description"])
        w.writerow(["E1", "logical_data_component", "Curriculum", description])
    import_directory(backend, registry, d, "s", actor="t")
    assert backend.get_element("E1").description_md == description

    export_directory(backend, registry, tmp_path / "out")
    import_directory(fresh_backend, registry, tmp_path / "out", "", actor="t")
    assert fresh_backend.get_element("E1").description_md == description


def test_the_wide_file_carries_every_type_s_attributes(loaded, registry, tmp_path):
    """One file for every type, so a column belongs to the types that declare it and is blank elsewhere."""
    export_directory(loaded, registry, tmp_path / "out")
    rows = (tmp_path / "out" / "elements.csv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",")
    assert header[:3] == ["id", "type", "name"]
    # an attribute of one type and an attribute of another, both present as columns
    assert "level" in header and "includes_pii" in header
    assert "source_system" in header  # what keeps a relationship's identity on re-import


def test_an_attribute_the_pack_never_declared_still_comes_back(backend, registry, fresh_backend, tmp_path):
    """The importer keeps undeclared columns as text, so an export that dropped them would lose data."""
    d = tmp_path / "in"
    d.mkdir()
    (d / "elements.csv").write_text(
        "id,type,name,a_column_no_pack_declares\nE1,logical_data_component,One,kept\n"
    )
    import_directory(backend, registry, d, "s", actor="t")
    export_directory(backend, registry, tmp_path / "out")
    import_directory(fresh_backend, registry, tmp_path / "out", "", actor="t")
    assert fresh_backend.get_element("E1").attrs["a_column_no_pack_declares"] == "kept"


def test_the_archive_holds_the_contract_files_and_the_schema(loaded, registry):
    with zipfile.ZipFile(BytesIO(export_archive(loaded, registry))) as archive:
        assert sorted(archive.namelist()) == [
            "elements.csv",
            "links.csv",
            "relationships.csv",
            "schema.csv",
        ]
        assert archive.read("elements.csv").decode("utf-8").startswith("id,type,name")


def test_a_link_stated_twice_lands_once(backend, registry, tmp_path):
    """An export writes each link both inline and in the links file; two identical rows is not
    what either file meant, and the labelled one is the one worth keeping."""
    d = tmp_path / "in"
    d.mkdir()
    (d / "elements.csv").write_text("id,type,name,links\nE1,logical_data_component,One,https://a.example/1\n")
    (d / "links.csv").write_text("element_id,url,label\nE1,https://a.example/1,The label\n")
    import_directory(backend, registry, d, "s", actor="t")
    stored = backend.get_links("E1")
    assert [(ln.url, ln.label) for ln in stored] == [("https://a.example/1", "The label")]


def test_the_schema_file_says_what_every_column_is(loaded, registry, tmp_path):
    """The reference an adopter builds a feed from: each column with its parent, type and meaning."""
    from ea.importer.csv_export import EVERY_ELEMENT_TYPE, SCHEMA_FILE

    export_directory(loaded, registry, tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / SCHEMA_FILE).open(encoding="utf-8")))
    by_column = {(r["file"], r["column"]): r for r in rows}

    # a contract column, with the vocabulary the engine fixes
    status = by_column[("elements.csv", "status")]
    assert status["kind"] == "core" and status["allowed_values"] == "draft|approved|retired"

    # a common attribute, said once and parented to every type rather than to one of them
    alias = by_column[("elements.csv", "alias")]
    assert alias["kind"] == "attribute" and alias["applies_to"] == EVERY_ELEMENT_TYPE

    # a typed attribute of one element type, with its group and data type
    level = by_column[("elements.csv", "level")]
    assert level["data_type"] == "integer" and level["applies_to"] == "logical_data_component"

    # a date, which is what a feed most often gets wrong
    created = by_column[("elements.csv", "standard_creation_date")]
    assert created["data_type"] == "date"


def test_the_schema_file_describes_whichever_pack_is_applied(tmp_path):
    """It is written from the applied version, so it never describes a pack this org does not use."""
    import io

    from ea.importer.csv_export import write_schema
    from ea.metamodel import Registry, load_pack

    out = io.StringIO()
    write_schema(Registry(load_pack("packs/archimate_core/metamodel.yaml")), out)
    text = out.getvalue()
    assert "logical_data_component" not in text  # a type of the other pack
    assert "id,elements.csv,core" in text  # the contract's own columns are always there


def test_the_schema_file_is_not_imported_back(loaded, registry, fresh_backend, tmp_path):
    """It sits in the export directory; the importer must not read it as content."""
    export_directory(loaded, registry, tmp_path / "out")
    report = import_directory(fresh_backend, registry, tmp_path / "out", "", actor="t")
    assert report.ok
    assert fresh_backend.count_elements() == 47  # not 47 plus a row per schema line
