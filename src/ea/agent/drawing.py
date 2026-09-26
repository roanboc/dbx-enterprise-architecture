"""A draw.io drawing read as a proposal's source (initiative 26, decision 0026).

A drawing the application exported carries its stamp (`ea.views.drawio.document`): the file
says which export it is and what it drew, every cell the application drew carries
`ea_origin`, a shape its element and the name it was exported with, a line its relationship.
Read against the model as it is now:

- a stamped shape or line, moved or resized, is nothing;
- a stamped shape whose label a person edited is a row with a rename to ask about;
- a shape without the stamp is a new element, matched by name like a page's row; a text box
  is a note until the architect says it is an element;
- a copy of a stamped shape (a second shape with one identifier) is a shape a person added,
  of the type it was copied with; the original is the one still labelled with its name;
- a shape dragged from the metamodel's shape library (stamped with a type, standing for no
  element) is a shape a person added, of the library's type, and asks for a name until given one;
- a type said in a shape's label (`«Type» Name`) or in its `type` property is its type, before
  anything the drawing implies (`_typed` weighs it);
- a line without the stamp between two elements, or a copy of a stamped one joining other
  ends, is a new relationship;
- a stamped shape or line that is gone is asked about — out of the model, or only out of the
  picture — and changes nothing until answered.

A drawing with no stamp at all is read the same way, every shape as one a person added. What
the reader cannot settle becomes a question in Propose's conversation (`QuestionRules`); nothing
is written until the architect applies the draft. No language model is needed.
"""

from __future__ import annotations

import base64
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from typing import Any

from ea.agent.proposal import ROW_REF, ProposalResult, ProposedElement, ProposedRelationship
from ea.backend.base import DatabaseBackend
from ea.backend.organisations import current_org
from ea.metamodel.registry import Registry
from ea.views.drawio import LAYER_FILL, ORIGIN, STENCIL

#: How much of a drawing Propose takes: a deep dive's figure carries its icons inline.
MAX_DRAWING_CHARS = 2_000_000

__all__ = ["MAX_DRAWING_CHARS", "is_drawing", "read_drawing"]


def is_drawing(source: dict[str, Any]) -> bool:
    """Whether a source is a draw.io file rather than a page."""
    name = (source.get("name") or "").lower()
    head = (source.get("text") or "").lstrip()[:400].lower()
    return name.endswith(".drawio") or (head.startswith(("<?xml", "<mxfile")) and "<mxfile" in head)


# ---------------------------------------------------------------- the file
def _pages(text: str) -> list[tuple[str, ET.Element]]:
    """(name, the page's `root`) for every page of the file, compressed or not."""
    try:
        mxfile = ET.fromstring(text.strip())
    except ET.ParseError as exc:
        raise ValueError(f"not a draw.io file: {exc}") from exc
    diagrams = [mxfile] if mxfile.tag == "mxGraphModel" else mxfile.findall("diagram")
    out = []
    for d in diagrams:
        model = d if d.tag == "mxGraphModel" else d.find("mxGraphModel")
        if model is None and (d.text or "").strip():
            raw = zlib.decompress(base64.b64decode(d.text.strip()), -15).decode("utf-8")
            model = ET.fromstring(urllib.parse.unquote(raw))
        root = model.find("root") if model is not None else None
        if root is not None:
            out.append((d.get("name") or "", root))
    return out


def _cells(root: ET.Element) -> list[dict[str, Any]]:
    """Every cell of a page with its data: an `object` (or `UserObject`) is where draw.io keeps it."""
    out = []
    for node in root:
        if node.tag in ("object", "UserObject"):
            cell = node.find("mxCell")
            if cell is None:
                cell = ET.Element("mxCell")
            data = dict(node.attrib)
            label = data.pop("label", "")
        elif node.tag == "mxCell":
            cell, data, label = node, {}, node.get("value", "")
        else:
            continue
        out.append(
            {
                "id": node.get("id") or cell.get("id") or "",
                "data": data,
                "label": label or "",
                "style": cell.get("style") or "",
                "vertex": cell.get("vertex") == "1",
                "edge": cell.get("edge") == "1",
                "parent": cell.get("parent") or "",
                "source": cell.get("source") or "",
                "target": cell.get("target") or "",
            }
        )
    return out


def _text(label: str) -> str:
    """A label as a person reads it, line by line: markup dropped, entities read.

    A stereotype typed as `<<Type>>` is kept as `«Type»` before the markup goes, so it is not
    read as a tag; draw.io may save one escaped once more than the rest of the label.
    """
    text = re.sub(r"<<([^<>]+)>>", r"«\1»", label or "")
    text = re.sub(r"<br\s*/?>|</(div|p)>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    if re.search(r"&(lt|gt|laquo|raquo|amp);", text):
        text = html.unescape(text)
    return re.sub(r"<<([^<>]+)>>", r"«\1»", text)


def _first_line(text: str) -> str:
    """The first line of a label's text, the state glyph before it dropped."""
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return re.sub(r"^[^\w(\[]+", "", first).strip()


def _plain(label: str) -> str:
    """The first line of a label as a person reads it: markup, the state glyph and the identifier beneath dropped."""
    return _first_line(_text(label))


def _stated(label: str) -> tuple[str, str]:
    """(the type a label states, the name after it): `«Type Name» Name`, or ("", the name).

    An empty `« »` states no type, so a `type` property or the shape still can.
    """
    text = _text(label)
    m = re.match(r"\s*«([^»\n]*)»(.*)", text, flags=re.S)
    if not m:
        return "", _first_line(text)
    return m.group(1).strip(), _first_line(m.group(2))


def _named(label: str) -> str:
    """The name a label gives, after any type it states: a stereotype is never part of a name."""
    return _stated(label)[1]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _style(style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in style.split(";"):
        key, eq, value = part.partition("=")
        out[key.strip()] = value.strip() if eq else ""
    return out


def _stencil_key(style: dict[str, str]) -> str:
    shape = style.get("shape", "")
    if not shape.startswith("mxgraph.archimate3."):
        return ""
    name = shape.rsplit(".", 1)[1]
    return style.get("appType", "") if name == "application" else name


# ------------------------------------------------------------ the notation
class _Shapes:
    """The metamodel's notation read in reverse: which types are drawn as a given shape."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.kinds: dict[str, list[str]] = {}
        for kind, fragment in STENCIL.items():
            key = _stencil_key(_style("shape=mxgraph.archimate3." + fragment))
            self.kinds.setdefault(key, []).append(kind)
        # a fill is a layer where one layer is drawn in it; the few kinds with a fill of their
        # own (a location, a plateau, a gap) say nothing about the layer
        self.layer_of_fill = {v.lower(): k for k, v in LAYER_FILL.items()}

    def types(self, style_text: str) -> list[str]:
        style = _style(style_text)
        kinds = self.kinds.get(_stencil_key(style)) or []
        if not kinds:
            return []
        layer = self.layer_of_fill.get(style.get("fillColor", "").lower(), "")
        drawn = [
            t.id
            for t in self.registry.concrete_types()
            if t.active and self.registry.notation(t.id).get("archimate") in kinds
        ]
        in_layer = [t for t in drawn if layer and self.registry.notation(t).get("layer") == layer]
        return in_layer or drawn


def _is_shape(cell: dict[str, Any], edges: set[str]) -> bool:
    """A vertex that could stand for an element: not a line's label, a group or a picture."""
    if not cell["vertex"] or cell["parent"] in edges:
        return False
    style = _style(cell["style"])
    return not ("edgeLabel" in style or "group" in style or style.get("shape") == "image")


def _originals(vertices: list[tuple[int, dict[str, Any]]]) -> dict[str, tuple[int, str]]:
    """element id -> (page, cell) of the application's own shape for it; any other is a copy.

    draw.io copies a shape with everything it carries, identifier and all, and a person who
    copies one usually renames the copy, on the same page or on another. So the original is
    the one, anywhere in the file, whose label is still the name it was exported with; where
    none or several are, the first in the drawing.
    """
    seen: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for page, c in vertices:
        if c["data"].get("ea_origin") == ORIGIN and c["data"].get("ea_id"):
            seen.setdefault(c["data"]["ea_id"], []).append((page, c))
    out = {}
    for element_id, same in seen.items():
        named = [(p, c) for p, c in same if _norm(_named(c["label"])) == _norm(c["data"].get("ea_name", ""))]
        page, c = named[0] if len(named) == 1 else same[0]
        out[element_id] = (page, c["id"])
    return out


def _typed(
    stated: str, carried: str, carried_name: str, style: str, shapes: _Shapes, registry: Registry
) -> tuple[str, str, list[str]]:
    """(type id, type label, types the stencil is drawn for) of a shape a person added.

    The one place the evidence is weighed, in this order. What a person states — a stereotype
    in the label, or a `type` property added with Edit Data — wins, because it is the most
    deliberate thing in the drawing; a type stated that the metamodel does not have is kept
    as the row's label, so the type question asks with the closest types first rather than
    the stencil quietly deciding. Then the exact type a copy or a library shape carries, which
    the application wrote; one this metamodel lacks or retired (a library made from a draft, or
    from another organisation) is asked about like a stated one, never left to the stencil. Then
    the stencil, read through the metamodel's notation, which is only a guess where several
    types are drawn alike. Then nothing, and the question asks.
    """
    if stated:
        t = registry.resolve_type(stated)
        return (t.id, t.name, []) if t is not None else ("", stated, [])
    candidates = shapes.types(style)
    if carried:
        t = registry.types.get(carried)
        if t is not None and t.active:
            return t.id, t.name, []
        return "", carried_name or carried, candidates
    if len(candidates) == 1:
        return candidates[0], registry.types[candidates[0]].name, []
    return "", "", candidates


# ------------------------------------------------------------- the reading
def read_drawing(text: str, registry: Registry, backend: DatabaseBackend) -> ProposalResult:
    """A drawing as an unresolved proposal: rows for what changed, and what was taken out.

    Read on the branch the caller stands on, where the elements it names are looked up. Which
    shape is the application's own, and what is still in the drawing, is decided across the
    whole file: a person may copy a shape onto another page, or move one there.
    """
    result = ProposalResult()
    drawing: dict[str, Any] = {
        "title": "",
        "export": "",
        "org": "",
        "branch": "",
        "renamed": [],
        "removed_elements": [],
        "removed_relationships": [],
    }
    result.drawing = drawing
    try:
        pages = [(name, _cells(root)) for name, root in _pages(text)]
    except (ValueError, zlib.error, ET.ParseError, UnicodeDecodeError) as exc:
        result.error = f"The drawing could not be read: {exc}"
        return result
    stamps = []
    for page_name, cells in pages:
        stamp = next((c["data"] for c in cells if c["id"] == "0"), {})
        if stamp.get("ea_origin") == ORIGIN:
            org = stamp.get("ea_org", "")
            if org and org != current_org():
                result.error = (
                    f"This drawing was exported from the organisation {org!r}, not the one you are in: "
                    "hand it in there."
                )
                return result
            stamps.append(stamp)
            drawing["export"] = drawing["export"] or stamp.get("ea_export", "")
            drawing["org"], drawing["branch"] = org, drawing["branch"] or stamp.get("ea_branch", "")
            drawing["title"] = drawing["title"] or stamp.get("ea_title", "")
        drawing["title"] = drawing["title"] or page_name

    vertices = []
    for _name, cells in pages:
        edges = {c["id"] for c in cells if c["edge"]}
        vertices.append([c for c in cells if _is_shape(c, edges)])
    original = _originals([(n, c) for n, shapes_of in enumerate(vertices) for c in shapes_of])
    stamped_ids = [
        c["data"].get("ea_id")
        for shapes_of in vertices
        for c in shapes_of
        if c["data"].get("ea_origin") == ORIGIN
    ]
    held = {e.element_id: e for e in backend.elements_by_ids([i for i in dict.fromkeys(stamped_ids) if i])}

    shapes = _Shapes(registry)
    kept_rels: set[str] = set()
    for n, (_name, cells) in enumerate(pages):
        ref_of = _read_shapes(n, vertices[n], original, held, result, drawing, shapes, registry)
        kept_rels |= _read_lines(cells, ref_of, result)
    present = {i for i in original if i in held}
    for stamp in stamps:
        _taken_out(stamp, present, kept_rels, drawing, registry, backend)
    result.title = drawing["title"]
    for n, el in enumerate(result.elements, start=1):
        el.row = n
    for n, rel in enumerate(result.relationships, start=1):
        rel.row = n
    return result


def _read_shapes(
    page: int,
    vertices: list[dict[str, Any]],
    original: dict[str, tuple[int, str]],
    held: dict[str, Any],
    result: ProposalResult,
    drawing: dict[str, Any],
    shapes: _Shapes,
    registry: Registry,
) -> dict[str, str]:
    """The rows a page's shapes give; returns cell id -> how a relationship row names its element."""
    ref_of: dict[str, str] = {}
    for c in vertices:
        style = _style(c["style"])
        data = c["data"]
        stamped = data.get("ea_origin") == ORIGIN
        element_id = data.get("ea_id", "") if stamped else ""
        carried = data.get("ea_type", "") if stamped else ""
        if stamped and not element_id and not carried and data.get("ea_palette") != "1":
            continue  # the application's own lanes, panels and captions
        if element_id and element_id in held and original.get(element_id) == (page, c["id"]):
            e = held[element_id]
            ref_of[c["id"]] = element_id
            label = _named(c["label"])
            if label and _norm(label) != _norm(data.get("ea_name") or e.name):
                result.elements.append(
                    ProposedElement(
                        row=0,
                        type_label=registry.types[e.type_id].name if e.type_id in registry.types else "",
                        name=e.name,
                        existing_id=element_id,
                        drawn="renamed",
                        drawn_label=label,
                    )
                )
                drawing["renamed"].append({"element_id": element_id, "name": e.name, "label": label})
            continue
        # a shape a person added: drawn fresh, a copy of the application's, or from its library
        stated, label = _stated(c["label"])
        stated = stated or (data.get("type") or "").strip()
        from_library = bool(carried) and not element_id
        type_names = {
            _norm(data.get("ea_type_name", "")),
            _norm(getattr(registry.types.get(carried), "name", "")),
        }
        if from_library and _norm(label) in type_names:
            label = ""  # a library shape still named for its type: nobody has named it yet
        if not label and not (stated or from_library):
            continue
        if not (stated or carried) and "text" in style and not _stencil_key(style):
            result.elements.append(ProposedElement(row=0, type_label="", name=label, drawn="note"))
            continue
        type_id, type_label, candidates = _typed(
            stated, carried, data.get("ea_type_name", ""), c["style"], shapes, registry
        )
        result.elements.append(
            ProposedElement(
                row=0,
                type_label=type_label,
                name=label,
                drawn="shape",
                type_candidates=candidates,
            )
        )
        # a shape nobody has named yet is named by its row, which the reading numbers in this
        # order, so a line to it is kept until it is named, and after
        ref_of[c["id"]] = label or f"{ROW_REF}{len(result.elements)}"
    return ref_of


def _read_lines(cells: list[dict[str, Any]], ref_of: dict[str, str], result: ProposalResult) -> set[str]:
    """The rows a page's lines give; returns the relationships still drawn between their own ends."""
    kept_rels: set[str] = set()
    for c in cells:
        if not c["edge"]:
            continue
        data = c["data"]
        src, dst = ref_of.get(c["source"], ""), ref_of.get(c["target"], "")
        if data.get("ea_origin") == ORIGIN:
            rel_id = data.get("ea_rel_id", "")
            # a line joining other ends than it was exported with — moved, or a copy of it that
            # draw.io took along with a copied shape — is one a person drew; the relationship it
            # names is kept by whichever line still joins its own ends
            moved = data.get("ea_src") and (src, dst) != (data.get("ea_src"), data.get("ea_dst"))
            if rel_id and not moved:
                kept_rels.add(rel_id)
                continue
            if not rel_id:
                continue  # a line the application drew that stands for no relationship
        if not (src and dst) or src == dst:
            continue
        result.relationships.append(
            ProposedRelationship(
                row=0,
                source=src,
                relationship=_plain(c["label"]),
                target=dst,
                target_state="new",
                drawn=True,
            )
        )
    return kept_rels


def _taken_out(
    stamp: dict[str, str],
    present: set[str],
    kept_rels: set[str],
    drawing: dict[str, Any],
    registry: Registry,
    backend: DatabaseBackend,
) -> None:
    """What an export drew that the file no longer holds, on any of its pages: asked about."""
    gone = [i for i in (stamp.get("ea_elements") or "").split() if i not in present]
    removed = {e.element_id: e for e in backend.elements_by_ids(gone)}
    for i in gone:
        if i in removed:
            e = removed[i]
            drawing["removed_elements"].append({"element_id": i, "name": e.name, "type_id": e.type_id})
    for rel_id in (stamp.get("ea_relationships") or "").split():
        if rel_id in kept_rels:
            continue
        r = backend.get_relationship(rel_id)
        if r is None or r.src_id in removed or r.dst_id in removed:
            continue  # gone with the shape it hung off, which is asked about on its own
        rt = registry.rel_types.get(r.rel_type_id)
        names = {e.element_id: e.name for e in backend.elements_by_ids([r.src_id, r.dst_id])}
        drawing["removed_relationships"].append(
            {
                "relationship_id": rel_id,
                "src": r.src_id,
                "dst": r.dst_id,
                "relationship": rt.name if rt else r.rel_type_id,
                "src_name": names.get(r.src_id, r.src_id),
                "dst_name": names.get(r.dst_id, r.dst_id),
            }
        )
