"""The metamodel as a draw.io shape library (initiative 26): a palette an architect draws from.

Every shape in it is one active concrete element type, drawn the way a view export draws it and
stamped so the drawing reader types it exactly (`ea.agent.drawing`), whatever its stencil is
also drawn for. The library is the metamodel's, read from the pack and its notation, so the
second pack the repository ships gets a library of its own without a line of code (P5).
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from dataclasses import replace

import pytest
from tests.conftest import PACK, ROOT, SAMPLE
from typer.testing import CliRunner

from ea.backend.duckdb_backend import DuckDBBackend
from ea.cli import app
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.ui.pages.metamodel import palette_download
from ea.views.drawio import node_size, node_style, palette_library
from ea.views.model import ViewNode, layer_rank

ARCHIMATE_PACK = ROOT / "packs" / "archimate_core" / "metamodel.yaml"
CONTRACT = {"ea_origin": "ea-repository", "ea_palette": "1"}

runner = CliRunner()


def entries(library: str) -> list[dict]:
    root = ET.fromstring(library)
    assert root.tag == "mxlibrary"
    return json.loads(root.text)


def model(entry: dict) -> ET.Element:
    """An entry's graph model, inflated the way the drawing reader inflates a compressed page."""
    raw = zlib.decompress(base64.b64decode(entry["xml"]), -15).decode("utf-8")
    return ET.fromstring(urllib.parse.unquote(raw))


def shape(entry: dict) -> ET.Element:
    objects = model(entry).findall("./root/object")
    assert len(objects) == 1
    return objects[0]


def reading_order(registry: Registry) -> list[str]:
    return [
        t.name
        for t in sorted(
            registry.concrete_types(),
            key=lambda t: (layer_rank(registry.notation(t.id).get("layer", "other")), t.sort_order, t.name),
        )
    ]


@pytest.fixture(params=["higher_education", "archimate_core"])
def any_registry(request, registry):
    return registry if request.param == "higher_education" else Registry(load_pack(ARCHIMATE_PACK))


def test_the_library_holds_every_type_an_element_may_be_in_reading_order(any_registry):
    library = entries(palette_library(any_registry))
    assert [e["title"] for e in library] == reading_order(any_registry)
    assert library and all(e["aspect"] == "fixed" for e in library)


def test_every_shape_is_one_the_drawing_reader_types_exactly(any_registry):
    """The reader's contract: stamped, of the library, typed, and standing for no element."""
    for entry in entries(palette_library(any_registry)):
        obj = shape(entry)
        t = any_registry.resolve_type(obj.get("ea_type"))
        assert t is not None and t.name == entry["title"]
        assert {k: obj.get(k) for k in CONTRACT} == CONTRACT
        assert (obj.get("label"), obj.get("ea_type_name")) == (t.name, t.name)
        assert obj.get("ea_id") is None
        # a shape dragged from the library is the person's, not the application's: hiding what
        # the application drew by its draw.io tag must not hide it
        assert obj.get("tags") is None
        cell = obj.find("mxCell")
        assert (cell.get("vertex"), cell.get("parent")) == ("1", "1")
        n = any_registry.notation(t.id)
        node = ViewNode(
            id=t.id,
            name=t.name,
            type_id=t.id,
            type_name=t.name,
            layer=n["layer"],
            glyph=n["glyph"],
            stereotype=n["stereotype"],
            shape=n["shape"],
            archimate=n["archimate"],
        )
        # drawn exactly as a view export draws an element of the type
        assert cell.get("style") == node_style(node)
        geometry = cell.find("mxGeometry")
        assert (int(geometry.get("width")), int(geometry.get("height"))) == node_size(node)
        assert (entry["w"], entry["h"]) == node_size(node)


def test_a_type_nobody_may_use_is_not_in_the_library(registry, pack):
    retired = replace(
        pack,
        element_types=[replace(t, active=False) if t.id == "data_entity" else t for t in pack.element_types],
    )
    titles = [e["title"] for e in entries(palette_library(Registry(retired)))]
    assert "Data Entity" in [e["title"] for e in entries(palette_library(registry))]
    assert "Data Entity" not in titles
    assert all(not t.abstract for t in registry.pack.element_types if t.name in titles)


def test_the_page_names_the_library_for_the_metamodel(registry):
    sent = palette_download(registry)
    assert sent["filename"].endswith("-shapes.xml") and " " not in sent["filename"]
    assert sent["content"] == palette_library(registry)


# ----------------------------------------------------------------- the command line
@pytest.fixture(autouse=True)
def _scope_reset():
    """The command line sets the role, the branch and the organisation as context variables of
    the process, and the in-process runner never unwinds them."""
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


def test_the_command_line_writes_the_same_library(ea_env, registry):
    printed = runner.invoke(app, ["metamodel", "palette"])
    assert printed.exit_code == 0, printed.output
    assert [e["title"] for e in entries(printed.output)] == reading_order(registry)
    out = ea_env / "shapes.xml"
    written = runner.invoke(app, ["metamodel", "palette", "--out", str(out)])
    assert written.exit_code == 0, written.output
    assert str(out) in written.output
    assert [e["title"] for e in entries(out.read_text(encoding="utf-8"))] == reading_order(registry)
