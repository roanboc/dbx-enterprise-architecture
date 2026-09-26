"""A deep dive's pack (initiative 25, decision 0025): a styled PDF and a draw.io file per diagram, in a ZIP.

Both formats are written from one layout, so what is printed is what opens in draw.io. The
high level is drawn to be presented, the detail in the metamodel's notation; every shape that
stands for an element carries its identifier (P8), and a chart carries none. The pack is drawn
from what the deep dive kept alone — no store, no metamodel — so it can be drawn again later.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from ea.agent.deep_dive import Brief, DeepDiveAnalyst
from ea.backend.duckdb_backend import DuckDBBackend
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.models import DeepDive
from ea.services import OrganisationService
from ea.views.deep_dive_layout import figures, layout_figure
from ea.views.deep_dive_pack import build_pack, diagram_files, pack_filename
from ea.views.deep_dive_pdf import deep_dive_pdf
from ea.views.drawio import STENCIL
from ea.views.icons import ARCHIMATE_ICON, ICONS, LAYER_ICON, icon_for, icon_svg
from ea.views.model import layer_rank

ROOT = Path(__file__).resolve().parents[1]
PACKS = [
    ROOT / "packs" / "higher_education" / "metamodel.yaml",
    ROOT / "packs" / "archimate_core" / "metamodel.yaml",
]


@pytest.fixture(scope="module")
def dives() -> dict[str, DeepDive]:
    """One deep dive of each shape the pack draws, from the sample model. The pack reads no store,
    so these are made once for the module, on one engine."""
    pack = load_pack(PACKS[0])
    registry = Registry(pack)
    b = DuckDBBackend(":memory:")
    b.save_pack(pack)
    OrganisationService(b).ensure_default(pack)
    assert import_directory(b, registry, ROOT / "data" / "sample", "sample").ok
    analyst = DeepDiveAnalyst(b, registry)
    out = {
        "impact": analyst.analyse(Brief(subject=["PAC-CMS"], kind="impact", purpose="replace it")),
        "transition": analyst.analyse(Brief(work_package="WP-CMS-UPGRADE", kind="transition")),
        "quality": analyst.analyse(Brief(subject=["PAC-CMS"], kind="quality")),
    }
    for d in out.values():
        d.deep_dive_id, d.created_by = "dd-test", "ada"
    b.close()
    return out


def _all(dives):
    for name, d in dives.items():
        for fig in figures(d.content):
            yield name, d, fig


# ---------------------------------------------------------------------- icons
def test_every_icon_is_defined_once_and_draws_as_svg():
    assert set(ARCHIMATE_ICON.values()) | set(LAYER_ICON.values()) <= set(ICONS)
    for key in ICONS:
        ET.fromstring(icon_svg(key, "#123456"))


def test_the_icon_comes_from_the_notation_s_kind_else_the_layer():
    assert icon_for("BusinessActor", "business") == "actor"
    assert icon_for("", "technology") == "node"
    assert icon_for("SomethingNew", "strategy") == "capability"
    for path in PACKS:
        registry = Registry(load_pack(path))
        kinds = {registry.notation(t.id).get("archimate") for t in registry.pack.element_types} - {""}
        assert kinds <= set(ARCHIMATE_ICON), f"{path.parent.name}: {sorted(kinds - set(ARCHIMATE_ICON))}"


# --------------------------------------------------------------------- layout
def test_every_shape_standing_for_an_element_carries_its_identifier(dives):
    for _, d, fig in _all(dives):
        lay = layout_figure(fig, d.content["elements"])
        for s in lay.elements():
            assert s.element_id in d.content["elements"], (fig["fid"], s.element_id)
            assert s.sub == s.element_id and s.text, (fig["fid"], s.sid)
        if fig["kind"].startswith("chart_"):
            assert not lay.elements(), fig["fid"]
        else:
            assert lay.elements(), fig["fid"]


def test_a_layout_holds_together(dives):
    for _, d, fig in _all(dives):
        lay = layout_figure(fig, d.content["elements"])
        sids = [s.sid for s in lay.shapes]
        assert len(sids) == len(set(sids)), fig["fid"]
        for line in lay.lines:
            assert line.src in sids and line.dst in sids, (fig["fid"], line.lid)
        for s in lay.shapes:
            assert -12 <= s.x and s.x + s.w <= lay.width + 1, (fig["fid"], s.sid)
            assert -12 <= s.y and s.y + s.h <= lay.height + 1, (fig["fid"], s.sid)
        boxes = lay.elements()
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                apart = a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
                assert apart, (fig["fid"], a.sid, b.sid)


def test_the_architecture_reads_top_down_by_layer_in_the_notation(dives):
    for _, d, fig in _all(dives):
        if fig["kind"] != "view":
            continue
        lay = layout_figure(fig, d.content["elements"])
        assert lay.style == "architecture"
        ranked = sorted(lay.elements(), key=lambda s: s.y)
        ranks = [layer_rank(s.node["layer"]) for s in ranked]
        assert ranks == sorted(ranks), fig["fid"]


def test_the_context_puts_the_subject_at_the_centre(dives):
    d = dives["impact"]
    fig = figures(d.content)[0]
    lay = layout_figure(fig, d.content["elements"])
    core = lay.shape("_panel_centre")
    inside = [
        s.element_id
        for s in lay.elements()
        if core.x <= s.x and s.x + s.w <= core.x + core.w and core.y <= s.y
    ]
    assert "PAC-CMS" in inside
    assert {line.dst for line in lay.lines} | {line.src for line in lay.lines} >= {
        "_panel_centre",
        "_panel_serves",
    }


def test_the_context_shows_the_work_in_flight_beside_the_subject(dives):
    d = dives["impact"]
    lay = layout_figure(figures(d.content)[0], d.content["elements"])
    panel = lay.shape("_panel_work")
    assert panel is not None and panel.text == "Work in flight"
    inside = [
        s.element_id
        for s in lay.elements()
        if panel.x <= s.x and s.x + s.w <= panel.x + panel.w and panel.y <= s.y <= panel.y + panel.h
    ]
    assert inside == ["WP-CMS-UPGRADE"]
    assert any(line.src == "_panel_work" and line.dst == "_panel_centre" for line in lay.lines)


# --------------------------------------------------------------------- draw.io
def test_a_draw_io_file_per_figure_numbered_top_down(dives):
    d = dives["impact"]
    files = diagram_files(d)
    assert len(files) == len(figures(d.content))
    names = [n for n, _ in files]
    assert [int(n[:2]) for n in names] == list(range(1, len(names) + 1))
    levels = [int(re.match(r"\d\d-level-(\d)-", n).group(1)) for n in names]
    assert levels == sorted(levels) and levels[0] == 1 and levels[-1] == 4
    assert all(n.endswith(".drawio") for n in names)


def test_the_draw_io_file_is_drawn_from_the_same_layout_as_the_pdf(dives):
    for _, d, fig in _all(dives):
        lay = layout_figure(fig, d.content["elements"])
        (name, xml), *_ = diagram_files(
            DeepDive(
                title=d.title, content={"levels": [{"figures": [fig]}], "elements": d.content["elements"]}
            ),
            "https://ea.example",
        )
        root = ET.fromstring(xml)
        objects = {o.get("ea_id"): o for o in root.iter("object")}
        assert set(objects) == {s.element_id for s in lay.elements()}, fig["fid"]
        cells = {c.get("id") for c in root.iter("mxCell")} | set(objects)
        for s in lay.elements():
            o = objects[s.element_id]
            assert o.get("link") == f"https://ea.example/element/{s.element_id}"
            assert s.element_id in o.get("label")  # P8: the identifier is in the shape, not only behind it
            geo = o.find("mxCell/mxGeometry")
            assert (float(geo.get("x")), float(geo.get("y"))) == (round(s.x), round(s.y)), (fig["fid"], s.sid)
            style = o.find("mxCell").get("style")
            if s.style == "architecture" and s.node["archimate"] in STENCIL:
                assert "mxgraph.archimate3" in style
        for edge in (c for c in root.iter("mxCell") if c.get("edge") == "1"):
            assert edge.get("source") in cells and edge.get("target") in cells


def test_a_presentation_shape_carries_its_icon_into_draw_io(dives):
    d = dives["impact"]
    fig = figures(d.content)[0]
    (_, xml), *_ = diagram_files(
        DeepDive(title=d.title, content={"levels": [{"figures": [fig]}], "elements": d.content["elements"]})
    )
    root = ET.fromstring(xml)
    icons = [c for c in root.iter("mxCell") if "shape=image" in (c.get("style") or "")]
    chips = {o.get("id") for o in root.iter("object")}
    assert icons and {c.get("parent") for c in icons} & chips
    assert all("data:image/svg+xml," in c.get("style") for c in icons)


# ------------------------------------------------------------------------ PDF
SECTIONS = [
    "What you need to know",
    "Context",
    "Overview",
    "Architecture",
    "Detail",
    "Findings",
    "Inconsistencies",
    "References",
    "How it was answered",
]


def test_the_pdf_reads_top_down_from_the_cover_to_how_it_was_answered(dives):
    d = dives["impact"]
    raw = deep_dive_pdf(d, org_name="Default organisation", pack_name="Higher education", compress=False)
    assert raw.startswith(b"%PDF")
    at = [raw.find(f"({s})".encode()) for s in SECTIONS]
    assert all(p > 0 for p in at), dict(zip(SECTIONS, at, strict=True))
    assert at == sorted(at)
    assert raw.count(b"/Type /Page\n") + raw.count(b"/Type /Page ") >= 8
    for name, _ in diagram_files(d):  # every figure names the draw.io file that opens it
        assert name.encode() in raw


def test_what_you_need_to_know_names_the_work_in_flight(dives):
    raw = deep_dive_pdf(dives["impact"], compress=False)
    assert b"(Work in flight)" in raw and b"WP-CMS-UPGRADE" in raw


def test_a_rating_is_drawn_as_stars():
    from ea.views.deep_dive_pdf import stars

    drawing = stars(3.5, count=2)
    shapes = drawing.contents[0].contents
    filled = [
        x for x in shapes if getattr(x, "fillColor", None) is not None and x.fillColor.hexval() == "0xf5b301"
    ]
    assert len([x for x in shapes if type(x).__name__ == "Polygon"]) >= 5
    assert 3 < len(filled) <= 4  # three whole stars and half of the fourth


def test_the_cover_says_what_was_read_and_for_whom(dives):
    d = dives["impact"]
    raw = deep_dive_pdf(d, org_name="Default organisation", pack_name="Higher education", compress=False)
    for text in (b"Default organisation", b"Higher education", b"ada", b"main"):
        assert text in raw


def test_a_name_the_standard_fonts_cannot_write_does_not_stop_the_pdf(dives):
    d = dives["quality"]
    rows = {k: dict(v) for k, v in d.content["elements"].items()}
    rows["PAC-CMS"]["name"] = "Système → ☃ Δ"
    odd = DeepDive(title="Odd → names", kind=d.kind, brief=d.brief, content=dict(d.content, elements=rows))
    assert deep_dive_pdf(odd, compress=False).startswith(b"%PDF")


# ------------------------------------------------------------------------ ZIP
def test_the_pack_is_one_pdf_and_the_diagrams_and_nothing_in_markdown(dives):
    d = dives["transition"]
    data = build_pack(d, org_name="Default organisation", pack_name="Higher education")
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    folder = pack_filename(d).removesuffix(".zip")
    assert f"{folder}/deep-dive.pdf" in names
    diagrams = [n for n in names if n.startswith(f"{folder}/diagrams/")]
    assert [n.rsplit("/", 1)[1] for n in diagrams] == [n for n, _ in diagram_files(d)]
    assert len(names) == 1 + len(diagrams) and not any(n.endswith(".md") for n in names)
    assert pack_filename(d).endswith("-dd-test.zip")
