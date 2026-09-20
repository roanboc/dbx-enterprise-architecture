"""The export is the import's inverse: what it writes, the importer reads back unchanged."""

from __future__ import annotations

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
    assert counts == {"elements": 47, "relationships": 99, "links": 6}

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


def test_the_archive_holds_the_three_contract_files(loaded, registry):
    with zipfile.ZipFile(BytesIO(export_archive(loaded, registry))) as archive:
        assert sorted(archive.namelist()) == ["elements.csv", "links.csv", "relationships.csv"]
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
