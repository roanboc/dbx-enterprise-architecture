"""A drawing handed back on Propose (initiative 26, decision 0026): read by its stamp.

What the application drew is known by the element or relationship it stands for; what a person
added is proposed, typed from its shape or asked about; a rename and a shape taken out are asked
about; moving a shape is nothing; nothing is applied until the architect says so.
"""

from __future__ import annotations

import base64
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import pytest

from ea.agent.drawing import is_drawing, read_drawing
from ea.agent.proposal import ProposalService
from ea.backend.branching import use_branch
from ea.backend.organisations import use_org
from ea.config import Settings
from ea.services import BranchService, RepositoryService, TargetStateService
from ea.views import view_from_neighbourhood
from ea.views.drawio import to_drawio

FOCUS = "LDC-CURR"
PROCESS = "html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.application;appType=proc;archiType=rounded;fillColor=#ffff99;"
COMPONENT = "html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.application;appType=comp;archiType=square;fillColor=#99ffff;"


@pytest.fixture
def svc(loaded, registry):
    return ProposalService(
        loaded,
        registry,
        RepositoryService(loaded, registry),
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
    )


@pytest.fixture
def view(registry, graph):
    return view_from_neighbourhood(registry, graph, FOCUS, 1)


def _root(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _cells(root: ET.Element) -> ET.Element:
    return root.find("./diagram/mxGraphModel/root")


def _shape(cells: ET.Element, element_id: str) -> ET.Element:
    return next(o for o in cells.findall("object") if o.get("ea_id") == element_id)


def _add_vertex(cells: ET.Element, cid: str, label: str, style: str) -> None:
    cell = ET.SubElement(cells, "mxCell", id=cid, value=label, style=style, vertex="1", parent="1")
    ET.SubElement(cell, "mxGeometry", x="10", y="10", width="120", height="60", **{"as": "geometry"})


def _add_edge(cells: ET.Element, cid: str, src: str, dst: str, label: str = "") -> None:
    cell = ET.SubElement(
        cells,
        "mxCell",
        id=cid,
        value=label,
        style="endArrow=open;",
        edge="1",
        parent="1",
        source=src,
        target=dst,
    )
    ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})


def _edited(view) -> tuple[str, dict[str, str]]:
    """The exported view as an architect hands it back, and what they did to it."""
    ids = view.ids()
    degree = {i: sum(1 for e in view.edges if i in (e.src, e.dst)) for i in ids}
    others = [i for i in ids if i != FOCUS]
    taken_out = next(i for i in others if degree[i] == 1)
    renamed = next(i for i in others if i != taken_out)
    edge_out = next(
        e for e in view.edges if taken_out not in (e.src, e.dst) and renamed not in (e.src, e.dst)
    )
    moved = next(i for i in others if i not in (taken_out, renamed))
    root = _root(to_drawio(view, "http://x"))
    cells = _cells(root)
    _shape(cells, renamed).set("label", "Curriculum Hub")
    geo = _shape(cells, moved).find("mxCell/mxGeometry")
    geo.set("x", str(float(geo.get("x")) + 400))  # moved: nothing
    cells.remove(_shape(cells, taken_out))
    for o in [o for o in cells.findall("object") if taken_out in (o.get("ea_src"), o.get("ea_dst"))]:
        cells.remove(o)  # draw.io takes a shape's lines with it
    cells.remove(next(o for o in cells.findall("object") if o.get("ea_rel_id") == edge_out.relationship_id))
    _add_vertex(cells, "p1", "Approve unit proposals", PROCESS)
    _add_vertex(cells, "t1", "Ask the board about timing", "text;html=1;strokeColor=none;fillColor=none;")
    _add_edge(cells, "l1", "p1", renamed)
    copy = ET.fromstring(ET.tostring(_shape(cells, moved)))
    copy.set("id", "copy-1")
    cells.append(copy)
    return ET.tostring(root, encoding="unicode"), {
        "renamed": renamed,
        "taken_out": taken_out,
        "edge_out": edge_out.relationship_id,
        "moved": moved,
    }


def _by_kind(result, kind: str) -> list[dict]:
    return [q for q in result.questions if q["kind"] == kind]


def test_a_drawing_is_told_from_a_page():
    assert is_drawing({"name": "view.drawio", "text": "<mxfile/>"})
    assert is_drawing({"name": "x.xml", "text": '<?xml version="1.0"?>\n<mxfile><diagram/></mxfile>'})
    assert not is_drawing({"name": "page.md", "text": "# A page"})


def test_a_returned_drawing_reads_what_a_person_changed(svc, view, loaded):
    xml, did = _edited(view)
    r = svc.analyse([{"kind": "file", "name": "view.drawio", "text": xml}])
    assert r.drawing["title"] == view.title and r.title
    rows = {e.existing_id or e.name: e for e in r.elements}
    # a label edited on the application's shape is asked about, never taken as a rename
    renamed = rows[did["renamed"]]
    assert renamed.action == "link" and renamed.rename_to == ""
    q = next(q for q in _by_kind(r, "drawn_rename") if q["about"] == f"element:{renamed.row}")
    assert "Curriculum Hub" in q["text"] and [o["key"] for o in q["options"]] == ["rename", "label"]
    # a shape a person added is new, typed from its stencil by the metamodel's notation
    new = rows["Approve unit proposals"]
    assert (new.action, new.type_id, new.target_state) == ("new", "process", "new")
    # a line a person drew is a new relationship between the two
    line = next(x for x in r.relationships if x.drawn)
    assert (line.src_ref, line.dst_ref, line.target_state) == (new.ref, did["renamed"], "new")
    # a text box is asked about as a note first, and nothing else is asked about it
    note = rows["Ask the board about timing"]
    assert any(q["about"] == f"element:{note.row}" for q in _by_kind(r, "drawn_note"))
    assert not any(q["about"] == f"element:{note.row}" for q in _by_kind(r, "type"))
    # a shape and a line taken out are asked about, and change nothing until answered
    removed = {q["about"] for q in _by_kind(r, "drawn_removed")}
    assert f"element:{did['taken_out']}" in removed and f"relationship:{did['edge_out']}" in removed
    assert did["taken_out"] not in rows
    # a moved shape is nothing, and the copy of it is read as what a person added: its name
    # is the element's, so it links to it rather than adding a second
    copies = [e for e in r.elements if e.element_id == did["moved"]]
    assert len(copies) == 1 and copies[0].action == "link" and copies[0].drawn == "shape"
    assert copies[0].target_state != "decommission"
    # the drawing is kept whole as the source
    assert r.sources[0]["text"] == xml


def test_the_answers_to_a_drawing_are_what_is_applied(svc, view, loaded, registry):
    xml, did = _edited(view)
    r = svc.analyse([{"kind": "file", "name": "view.drawio", "text": xml}])
    renamed = next(e for e in r.elements if e.existing_id == did["renamed"])
    note = next(e for e in r.elements if e.name == "Ask the board about timing")
    r, said = svc.answer(r, f"drawn_rename:{did['renamed']}", "rename")
    assert "Curriculum Hub" in said
    r, _ = svc.answer(r, f"drawn_note:{note.row}", "note")
    r, _ = svc.answer(r, f"drawn_removed:element:{did['taken_out']}", "retire")
    r, _ = svc.answer(r, f"drawn_removed:relationship:{did['edge_out']}", "picture")
    assert not _by_kind(r, "drawn_rename") and not _by_kind(r, "drawn_note")
    assert not _by_kind(r, "drawn_removed")
    retiring = next(e for e in r.elements if e.element_id == did["taken_out"])
    assert retiring.target_state == "decommission"
    assert not next(e for e in r.elements if e.name == "Ask the board about timing").include
    assert not any(x.relationship_id == did["edge_out"] and x.include for x in r.relationships)
    # what is still open is what any new element owes: a description and a work package
    new = next(e for e in r.elements if e.name == "Approve unit proposals")
    r, _ = svc.answer(
        r, "description:approve unit proposals", text="Review boards approve a unit before it is published."
    )
    r.work_package = "WP-CMS-UPGRADE"
    r.reason = "Units are approved in one place."
    r = svc.resolve(r)
    for _ in range(6):  # whatever the rules still ask, answered the way an architect would
        q = next((q for q in r.questions if q.get("blocking") and not q.get("held")), None)
        if q is None:
            break
        serve = next((o for o in q["options"] if o["key"].startswith(("serve:", "rel:"))), None)
        keys = [o["key"] for o in q["options"]]
        if serve is not None:
            choice = serve["choices"][0]["key"] if serve.get("choices") else ""
            r, _ = svc.answer(r, q["qid"], serve["key"], choice=choice)
        elif "technical" in keys:
            r, _ = svc.answer(r, q["qid"], "technical")
        else:
            r, _ = svc.answer(r, q["qid"], keys[-1])
    assert not r.pushback, r.pushback
    BranchService(loaded, registry).create("From the drawing", "ana", work_package="WP-CMS-UPGRADE")
    out = svc.apply(r, "from-the-drawing", "ana")
    with use_branch("from-the-drawing"):
        assert loaded.get_element(did["renamed"]).name == "Curriculum Hub"
        assert loaded.get_element(did["taken_out"]).target_state == "decommission"
        assert any(loaded.get_element(i).name == "Approve unit proposals" for i in out["created"])
    assert loaded.get_element(did["renamed"]).name != "Curriculum Hub"  # main untouched
    assert renamed and new


def test_only_the_label_changes_nothing(svc, view):
    xml, did = _edited(view)
    r = svc.analyse([{"kind": "file", "name": "view.drawio", "text": xml}])
    r, said = svc.answer(r, f"drawn_rename:{did['renamed']}", "label")
    assert next(e for e in r.elements if e.existing_id == did["renamed"]).rename_to == ""
    assert "only" in said.lower()


def test_an_ambiguous_shape_is_asked_about_with_its_likely_types_first(svc, view):
    root = _root(to_drawio(view))
    _add_vertex(_cells(root), "c1", "Timetable Engine", COMPONENT)
    r = svc.analyse([{"kind": "file", "name": "v.drawio", "text": ET.tostring(root, encoding="unicode")}])
    el = next(e for e in r.elements if e.name == "Timetable Engine")
    assert el.type_id == "" and set(el.type_candidates) == {
        "logical_application_component",
        "physical_application_component",
    }
    q = next(q for q in _by_kind(r, "type") if q["about"] == f"element:{el.row}")
    assert {o["key"] for o in q["options"][:2]} == {
        "type:logical_application_component",
        "type:physical_application_component",
    }


def test_a_drawing_from_another_organisation_is_refused(svc, view):
    with use_org("elsewhere"):
        xml = to_drawio(view)
    r = svc.analyse([{"kind": "file", "name": "v.drawio", "text": xml}])
    assert "elsewhere" in r.error and r.pushback


def test_a_drawing_from_nothing_and_a_compressed_one_are_read(svc, registry, loaded):
    model = ET.Element("mxGraphModel")
    cells = ET.SubElement(model, "root")
    ET.SubElement(cells, "mxCell", id="0")
    ET.SubElement(cells, "mxCell", id="1", parent="0")
    _add_vertex(cells, "a", "Curriculum Management System", COMPONENT)
    _add_vertex(cells, "b", "Approve unit proposals", PROCESS)
    _add_edge(cells, "e", "a", "b")
    raw = urllib.parse.quote(ET.tostring(model, encoding="unicode"), safe="")
    packed = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = base64.b64encode(packed.compress(raw.encode()) + packed.flush()).decode()
    xml = f'<mxfile host="app.diagrams.net"><diagram id="d" name="Sketch">{body}</diagram></mxfile>'
    part = read_drawing(xml, registry, loaded)
    assert {e.name for e in part.elements} == {"Curriculum Management System", "Approve unit proposals"}
    r = svc.analyse([{"kind": "file", "name": "sketch.drawio", "text": xml}])
    cms = next(e for e in r.elements if e.name == "Curriculum Management System")
    assert cms.action == "link" and cms.element_id == "PAC-CMS"  # matched by name, as a page's rows are
    assert r.relationships and r.relationships[0].drawn


def test_a_drawing_and_a_page_are_read_together(svc, view):
    xml, _ = _edited(view)
    page = (
        "# Proposal: Unit approval\n\n## Elements\n\n| Type | Name | Existing id | Description | Current state | Target state |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| Data Entity | Unit approval record | | The record of one approval of a unit by its board. | proposed | new |\n"
    )
    r = svc.analyse(
        [{"kind": "text", "name": "page", "text": page}, {"kind": "file", "name": "view.drawio", "text": xml}]
    )
    names = {e.name for e in r.elements}
    assert {"Unit approval record", "Approve unit proposals"} <= names
    assert r.title == "Unit approval"


def test_a_drawing_s_draft_survives_the_page(svc, view):
    """The Propose page rebuilds a draft from its grids: what the drawing said rides along."""
    from ea.agent.proposal import result_from_payload
    from ea.ui.pages.propose import _el_rows, _payload_from_rows, _rel_rows, _stored

    xml, did = _edited(view)
    r = svc.analyse([{"kind": "file", "name": "view.drawio", "text": xml}])
    els, rels = _el_rows(r), _rel_rows(r)
    payload = _payload_from_rows(els, els, rels, rels, _stored(r), r.work_package)
    again = svc.resolve(result_from_payload(payload))
    assert {q["qid"] for q in again.questions} == {q["qid"] for q in r.questions}
    assert any(x.drawn for x in again.relationships)
