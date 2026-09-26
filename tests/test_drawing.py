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


# ------------------------------------------------ shapes as architects draw them
DATA_OBJECT = "html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.businessObject;overflow=fill;fillColor=#99ffff;"


def _add_object(cells: ET.Element, cid: str, label: str, style: str, **data: str) -> ET.Element:
    """A shape kept in an `object`, the way draw.io keeps one that carries data of its own."""
    obj = ET.SubElement(cells, "object", id=cid, label=label, **data)
    cell = ET.SubElement(obj, "mxCell", style=style, vertex="1", parent="1")
    ET.SubElement(cell, "mxGeometry", x="10", y="10", width="120", height="60", **{"as": "geometry"})
    return obj


def _add_palette(cells: ET.Element, cid: str, label: str, type_id: str, type_name: str, style: str) -> None:
    """A shape dragged from the metamodel's shape library: stamped, typed, standing for no element."""
    _add_object(
        cells,
        cid,
        label,
        style,
        ea_origin="ea-repository",
        ea_palette="1",
        ea_type=type_id,
        ea_type_name=type_name,
    )


def _copy(cells: ET.Element, original: ET.Element, cid: str, label: str | None = None, before: bool = False):
    copy = ET.fromstring(ET.tostring(original))
    copy.set("id", cid)
    if label is not None:
        copy.set("label", label)
    if before:
        cells.insert(list(cells).index(original), copy)
    else:
        cells.append(copy)
    return copy


def _read(svc, root: ET.Element):
    return svc.analyse([{"kind": "file", "name": "v.drawio", "text": ET.tostring(root, encoding="unicode")}])


def _row(result, name: str):
    return next(e for e in result.elements if e.name == name)


def _type_asked(result, el) -> bool:
    return any(q["about"] == f"element:{el.row}" for q in _by_kind(result, "type"))


def test_a_copy_takes_the_type_it_was_exported_with(svc, view, loaded):
    """A data object's stencil is drawn for two types: the copy says which it was copied from."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    _copy(cells, _shape(cells, FOCUS), "copy-1", "Curriculum Archive")
    r = _read(svc, root)
    el = _row(r, "Curriculum Archive")
    assert (el.action, el.type_id, el.type_candidates, el.drawn) == (
        "new",
        loaded.get_element(FOCUS).type_id,
        [],
        "shape",
    )
    assert not _type_asked(r, el)
    assert not r.drawing["renamed"]


def test_the_original_is_the_shape_that_still_carries_its_name(svc, view):
    """A copy placed before the shape it was copied from is still the copy."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    _copy(cells, _shape(cells, FOCUS), "copy-1", "Curriculum Archive", before=True)
    r = _read(svc, root)
    assert not r.drawing["renamed"] and not _by_kind(r, "drawn_rename")
    assert _row(r, "Curriculum Archive").action == "new"
    assert FOCUS not in {q["about"].split(":", 1)[1] for q in _by_kind(r, "drawn_removed")}


def test_a_copied_line_joining_other_ends_is_a_line_a_person_drew(svc, view, registry, loaded):
    root = _root(to_drawio(view))
    cells = _cells(root)
    edge = next(e for e in view.edges if e.src == FOCUS and e.relationship_id)
    _copy(cells, _shape(cells, edge.dst), "copy-1", "Timetable Records")
    line = next(o for o in cells.findall("object") if o.get("ea_rel_id") == edge.relationship_id)
    _copy(cells, line, "copy-line").find("mxCell").set("target", "copy-1")
    part = read_drawing(ET.tostring(root, encoding="unicode"), registry, loaded)
    drawn = [(x.source, x.target) for x in part.relationships if x.drawn]
    assert drawn == [(FOCUS, "Timetable Records")]
    # the line it was copied from is still there: nothing is asked about it
    assert not part.drawing["removed_relationships"]


@pytest.mark.parametrize(
    "label",
    [
        "«Physical Application Component»<br>Timetable Engine",
        "<<Physical Application Component>> Timetable Engine",
        "&lt;&lt;Physical Application Component&gt;&gt;<br>Timetable Engine",
        "&laquo;Physical Application Component&raquo; Timetable Engine",
        "<div>«physical_application_component»</div><div>Timetable Engine</div>",
    ],
)
def test_a_type_said_in_the_label_is_the_shape_s_type(svc, view, label):
    root = _root(to_drawio(view))
    _add_vertex(_cells(root), "c1", label, COMPONENT)
    r = _read(svc, root)
    el = _row(r, "Timetable Engine")
    assert (el.type_id, el.type_candidates) == ("physical_application_component", [])
    assert not _type_asked(r, el)


def test_a_type_data_property_is_the_shape_s_type(svc, view):
    """What draw.io's Edit Data adds to a shape is read as a type said in the label."""
    root = _root(to_drawio(view))
    _add_object(_cells(root), "c1", "Timetable Engine", COMPONENT, type="Logical Application Component")
    el = _row(_read(svc, root), "Timetable Engine")
    assert (el.type_id, el.type_candidates) == ("logical_application_component", [])


def test_a_type_said_in_the_label_wins_over_the_type_a_copy_carries(svc, view):
    root = _root(to_drawio(view))
    cells = _cells(root)
    _copy(cells, _shape(cells, FOCUS), "copy-1", "«Data Entity» Unit approval record")
    el = _row(_read(svc, root), "Unit approval record")
    assert el.type_id == "data_entity"


def test_a_type_the_metamodel_does_not_have_is_asked_about_never_the_stencil_s(svc, view):
    root = _root(to_drawio(view))
    _add_vertex(_cells(root), "p1", "«Proccess» Approve unit proposals", PROCESS)
    r = _read(svc, root)
    el = _row(r, "Approve unit proposals")
    assert (el.type_id, el.type_label) == ("", "Proccess")
    assert any("not in the metamodel" in i for i in el.issues)
    q = next(q for q in _by_kind(r, "type") if q["about"] == f"element:{el.row}")
    assert q["options"][0]["key"] == "type:process"  # the closest type first


def test_a_palette_shape_is_typed_by_the_library(svc, view):
    """The library's shape is exact where its stencil is drawn for several types, or for another."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    _add_palette(
        cells,
        "s1",
        "Timetable Engine",
        "logical_application_component",
        "Logical Application Component",
        COMPONENT,
    )
    _add_palette(cells, "s2", "Approve unit proposals", "business_service", "Business Service", PROCESS)
    r = _read(svc, root)
    engine, approve = _row(r, "Timetable Engine"), _row(r, "Approve unit proposals")
    assert (engine.type_id, engine.type_candidates, engine.drawn) == (
        "logical_application_component",
        [],
        "shape",
    )
    assert approve.type_id == "business_service"
    assert not _type_asked(r, engine) and not _type_asked(r, approve)


def test_a_palette_shape_nobody_named_asks_for_a_name(svc, view, registry, loaded):
    root = _root(to_drawio(view))
    cells = _cells(root)
    _add_palette(
        cells,
        "s1",
        "Goal",
        "goal",
        "Goal",
        "shape=mxgraph.archimate3.application;appType=goal;archiType=oct;",
    )
    part = read_drawing(ET.tostring(root, encoding="unicode"), registry, loaded)
    assert [(e.name, e.type_label) for e in part.elements if e.drawn == "shape"] == [("", "Goal")]
    r = _read(svc, root)
    el = next(e for e in r.elements if e.drawn == "shape")
    assert el.type_id == "goal" and "name is missing" in el.issues


def test_the_application_s_lanes_are_still_not_shapes(registry, loaded, graph):
    """A stamped lane carries neither an element nor a type: it is the application's own."""
    v = view_from_neighbourhood(registry, graph, FOCUS, 1)
    xml = to_drawio(v)
    assert "ea_layer" in xml
    part = read_drawing(xml, registry, loaded)
    assert not part.elements and not part.relationships


def test_a_text_box_that_says_its_type_is_an_element_not_a_note(svc, view):
    root = _root(to_drawio(view))
    _add_vertex(
        _cells(root),
        "t1",
        "«Goal» Units are approved in a week",
        "text;html=1;strokeColor=none;fillColor=none;",
    )
    el = _row(_read(svc, root), "Units are approved in a week")
    assert (el.drawn, el.type_id) == ("shape", "goal")


def test_a_stamped_shape_with_a_type_and_no_element_is_one_a_person_added(svc, view):
    """Whatever stamps a typed shape without an element — the library, or a later one — is read alike."""
    root = _root(to_drawio(view))
    _add_object(
        _cells(root),
        "s1",
        "Timetable Engine",
        COMPONENT,
        ea_origin="ea-repository",
        ea_type="logical_application_component",
    )
    assert _row(_read(svc, root), "Timetable Engine").type_id == "logical_application_component"


# ------------------------------------------------ the shape library, end to end
def _from_library(registry, type_name: str) -> ET.Element:
    """The shape the metamodel's library holds for a type, as draw.io drops it on a page."""
    import json

    from ea.views.drawio import palette_library

    entry = next(
        e for e in json.loads(ET.fromstring(palette_library(registry)).text) if e["title"] == type_name
    )
    raw = zlib.decompress(base64.b64decode(entry["xml"]), -15).decode("utf-8")
    return ET.fromstring(urllib.parse.unquote(raw)).find("./root/object")


def _drop(cells: ET.Element, shape: ET.Element, cid: str, label: str | None = None) -> None:
    """The library's shape pasted into a drawing: draw.io gives it a fresh identifier."""
    pasted = ET.fromstring(ET.tostring(shape))
    pasted.set("id", cid)
    if label is not None:
        pasted.set("label", label)
    cells.append(pasted)


def test_a_shape_from_the_library_is_proposed_with_the_library_s_type(svc, view, registry):
    """A logical application component is drawn with the stencil other types share: the library says which."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    _drop(cells, _from_library(registry, "Logical Application Component"), "lib-1", "Timetable Engine")
    _drop(cells, _from_library(registry, "Goal"), "lib-2")
    r = _read(svc, root)
    engine = _row(r, "Timetable Engine")
    assert (engine.action, engine.type_id, engine.type_candidates, engine.drawn) == (
        "new",
        "logical_application_component",
        [],
        "shape",
    )
    assert not _type_asked(r, engine)
    unnamed = next(e for e in r.elements if e.drawn == "shape" and e.type_id == "goal")
    assert unnamed.name == "" and "name is missing" in unnamed.issues
    assert not _type_asked(r, unnamed)


# ------------------------------------------------ what review found
@pytest.mark.parametrize(
    "label",
    [
        "<<Data Entity>> Curriculum",
        "&lt;&lt;Data Entity&gt;&gt; Curriculum",
        "<<Data Entity>><br>Curriculum",
        "«Data Entity» Curriculum",
    ],
)
def test_a_stereotype_on_the_application_s_shape_is_not_a_rename(svc, view, label):
    root = _root(to_drawio(view))
    _shape(_cells(root), FOCUS).set("label", label)
    r = _read(svc, root)
    assert not r.drawing["renamed"] and not _by_kind(r, "drawn_rename")


def test_a_stereotyped_rename_proposes_the_name_alone(svc, view):
    root = _root(to_drawio(view))
    _shape(_cells(root), FOCUS).set("label", "<<Data Entity>> Curriculum Hub")
    r = _read(svc, root)
    assert [x["label"] for x in r.drawing["renamed"]] == ["Curriculum Hub"]


def test_the_original_still_named_under_a_stereotype_is_not_taken_for_a_copy(svc, view):
    root = _root(to_drawio(view))
    cells = _cells(root)
    original = _shape(cells, FOCUS)
    _copy(cells, original, "copy-1", "Curriculum Archive", before=True)
    original.set("label", "<<Data Entity>> Curriculum")
    r = _read(svc, root)
    assert not r.drawing["renamed"] and _row(r, "Curriculum Archive").action == "new"
    assert "Curriculum" not in {e.name for e in r.elements if e.drawn == "shape"}


def test_a_line_to_a_shape_nobody_named_is_kept_and_follows_the_row(svc, view, registry, loaded):
    """An unnamed shape's lines name its row, so they survive until it is named, and after."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    goal = _from_library(registry, "Goal")
    _drop(cells, goal, "lib-1", "Fast approvals")
    _drop(cells, goal, "lib-2")
    _add_vertex(cells, "g3", "«Goal»", "rounded=1;")
    for n, shape in enumerate(("lib-1", "lib-2", "g3")):
        _add_edge(cells, f"l{n}", shape, FOCUS)
    part = read_drawing(ET.tostring(root, encoding="unicode"), registry, loaded)
    assert len([x for x in part.relationships if x.drawn]) == 3
    r = _read(svc, root)
    unnamed = [e for e in r.elements if e.drawn == "shape" and not e.name]
    assert len(unnamed) == 2 and unnamed[0].ref != unnamed[1].ref
    ends = {x.src_ref for x in r.relationships if x.drawn}
    assert ends == {_row(r, "Fast approvals").ref, *(e.ref for e in unnamed)}
    assert not any(q["about"] in {f"element:{e.row}" for e in unnamed} for q in _by_kind(r, "isolated"))
    # the row named later on the Propose page keeps its line
    from ea.agent.proposal import result_from_payload
    from ea.ui.pages.propose import _el_rows, _payload_from_rows, _rel_rows, _stored

    els, rels = _el_rows(r), _rel_rows(r)
    next(e for e in els if e["key"] == f"e{r.elements.index(unnamed[0])}")["name"] = "Short waits"
    again = svc.resolve(result_from_payload(_payload_from_rows(els, els, rels, rels, _stored(r), "")))
    assert _row(again, "Short waits").ref in {x.src_ref for x in again.relationships if x.drawn}


def test_an_empty_stereotype_states_no_type(svc, view):
    from ea.agent.drawing import _stated

    assert _stated("« » Name") == ("", "Name") and _stated("«  »<br>Name") == ("", "Name")
    root = _root(to_drawio(view))
    _add_object(_cells(root), "c1", "« » Timetable Engine", COMPONENT, type="Logical Application Component")
    r = _read(svc, root)
    el = _row(r, "Timetable Engine")
    assert el.type_id == "logical_application_component" and not _type_asked(r, el)


def test_a_library_type_the_metamodel_lacks_is_asked_about_never_the_stencil_s(svc, view):
    """A library made from a draft carries a type the organisation's metamodel does not have."""
    root = _root(to_drawio(view))
    goal = "shape=mxgraph.archimate3.application;appType=goal;archiType=oct;"
    _add_palette(_cells(root), "s1", "Grow research income", "strategic_goal", "Strategic Goal", goal)
    r = _read(svc, root)
    el = _row(r, "Grow research income")
    assert (el.type_id, el.type_label) == ("", "Strategic Goal")
    q = next(q for q in _by_kind(r, "type") if q["about"] == f"element:{el.row}")
    assert q["options"][0]["key"] == "type:goal"


def test_a_copy_on_another_page_is_a_shape_a_person_added(svc, view):
    """Which shape is the original is decided across the whole file, not page by page."""
    root = _root(to_drawio(view))
    page = ET.SubElement(ET.SubElement(root, "diagram", name="Page-2", id="p2"), "mxGraphModel")
    cells2 = ET.SubElement(page, "root")
    ET.SubElement(cells2, "mxCell", id="0")
    ET.SubElement(cells2, "mxCell", id="1", parent="0")
    copy = _copy(cells2, _shape(_cells(root), FOCUS), "copy-x", "Curriculum Archive")
    copy.find("mxCell").set("parent", "1")
    r = _read(svc, root)
    assert not r.drawing["renamed"] and not _by_kind(r, "drawn_rename")
    assert _row(r, "Curriculum Archive").action == "new"
    assert FOCUS not in {x["element_id"] for x in r.drawing["removed_elements"]}


def test_a_line_to_an_unnamed_shape_follows_its_row_below_a_page_s_rows(svc, view, registry):
    """A drawing's rows come after a page's: the row a line names moves down with them."""
    root = _root(to_drawio(view))
    cells = _cells(root)
    _drop(cells, _from_library(registry, "Goal"), "lib-1")
    _add_edge(cells, "l1", "lib-1", FOCUS)
    page = (
        "# Proposal: Unit approval\n\n## Elements\n\n| Type | Name | Existing id | Description | Current state | Target state |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| Data Entity | Unit approval record | | The record of one approval of a unit by its board. | proposed | new |\n"
    )
    r = svc.analyse(
        [
            {"kind": "text", "name": "page", "text": page},
            {"kind": "file", "name": "v.drawio", "text": ET.tostring(root, encoding="unicode")},
        ]
    )
    unnamed = next(e for e in r.elements if e.drawn == "shape" and not e.name)
    line = next(x for x in r.relationships if x.drawn)
    assert unnamed.row > 1 and line.source == f"#{unnamed.row}" and line.src_ref == unnamed.ref


def test_a_text_box_is_asked_about_once_until_it_is_said_to_be_an_element(svc, view):
    """While the drawing's 'a note or an element?' question is open, the text box is not also
    asked what it serves, nor listed as lacking a type and a description; the pushback names the
    one thing to answer. Said to be an element, it owes what any new element owes."""
    xml, _ = _edited(view)
    r = svc.analyse([{"kind": "file", "name": "view.drawio", "text": xml}])
    note = next(e for e in r.elements if e.name == "Ask the board about timing")
    about = [q["kind"] for q in r.questions if q["about"] == f"element:{note.row}"]
    assert about == ["drawn_note"]
    said = [p for p in r.pushback if "Ask the board about timing" in p]
    assert len(said) == 1 and "note or an element" in said[0]
    r, _ = svc.answer(r, f"drawn_note:{note.row}", "element")
    kinds = {q["kind"] for q in r.questions if q["about"] == f"element:{note.row}"}
    assert "type" in kinds and "drawn_note" not in kinds
