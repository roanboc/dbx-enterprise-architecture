"""A draw.io drawing read as a proposal's source (initiative 26, decision 0026).

A drawing the application exported carries its stamp (`ea.views.drawio.document`): the file
says which export it is and what it drew, every cell the application drew carries
`ea_origin`, a shape its element and the name it was exported with, a line its relationship.
Read against the model as it is now:

- a stamped shape or line, moved or resized, is nothing;
- a stamped shape whose label a person edited is a row with a rename to ask about;
- a shape without the stamp is a new element, typed from its shape by the metamodel's own
  notation where one type is drawn that way, matched by name like a page's row; a text box is
  a note until the architect says it is an element;
- a line without the stamp between two elements is a new relationship;
- a stamped shape or line that is gone is asked about — out of the model, or only out of the
  picture — and changes nothing until answered;
- a copy of a stamped shape (a second shape with one identifier) is a shape a person added.

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

from ea.agent.proposal import ProposalResult, ProposedElement, ProposedRelationship
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


def _plain(label: str) -> str:
    """The first line of a label as a person reads it: markup, the state glyph and the identifier beneath dropped."""
    text = re.sub(r"<br\s*/?>|</(div|p)>", "\n", label or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return re.sub(r"^[^\w(\[]+", "", first).strip()


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


# ------------------------------------------------------------- the reading
def read_drawing(text: str, registry: Registry, backend: DatabaseBackend) -> ProposalResult:
    """A drawing as an unresolved proposal: rows for what changed, and what was taken out.

    Read on the branch the caller stands on, where the elements it names are looked up.
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
        pages = _pages(text)
    except (ValueError, zlib.error, ET.ParseError, UnicodeDecodeError) as exc:
        result.error = f"The drawing could not be read: {exc}"
        return result
    shapes = _Shapes(registry)
    for page_name, root in pages:
        _read_page(root, page_name, result, drawing, shapes, registry, backend)
        if result.error:
            return result
    result.title = drawing["title"]
    for n, el in enumerate(result.elements, start=1):
        el.row = n
    for n, rel in enumerate(result.relationships, start=1):
        rel.row = n
    return result


def _read_page(
    root: ET.Element,
    page_name: str,
    result: ProposalResult,
    drawing: dict[str, Any],
    shapes: _Shapes,
    registry: Registry,
    backend: DatabaseBackend,
) -> None:
    cells = _cells(root)
    stamp = next((c["data"] for c in cells if c["id"] == "0"), {})
    if stamp.get("ea_origin") == ORIGIN:
        org = stamp.get("ea_org", "")
        if org and org != current_org():
            result.error = (
                f"This drawing was exported from the organisation {org!r}, not the one you are in: "
                "hand it in there."
            )
            return
        drawing["export"] = drawing["export"] or stamp.get("ea_export", "")
        drawing["org"], drawing["branch"] = org, drawing["branch"] or stamp.get("ea_branch", "")
        drawing["title"] = drawing["title"] or stamp.get("ea_title", "")
    drawing["title"] = drawing["title"] or page_name
    edges = {c["id"] for c in cells if c["edge"]}
    stamped_ids = [
        c["data"].get("ea_id") for c in cells if c["vertex"] and c["data"].get("ea_origin") == ORIGIN
    ]
    held = {e.element_id: e for e in backend.elements_by_ids([i for i in dict.fromkeys(stamped_ids) if i])}

    ref_of: dict[str, str] = {}  # cell id -> how a relationship row names the element
    type_of: dict[str, str] = {}
    present: set[str] = set()
    for c in cells:
        if not c["vertex"] or c["parent"] in edges:
            continue
        style = _style(c["style"])
        if "edgeLabel" in style or "group" in style or style.get("shape") == "image":
            continue
        data, label = c["data"], _plain(c["label"])
        element_id = data.get("ea_id", "") if data.get("ea_origin") == ORIGIN else ""
        if data.get("ea_origin") == ORIGIN and not element_id:
            continue  # the application's own lanes, panels and captions
        if element_id and element_id in held and element_id not in present:
            present.add(element_id)
            e = held[element_id]
            ref_of[c["id"]], type_of[c["id"]] = element_id, e.type_id
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
        if not label:
            continue
        if "text" in style and not _stencil_key(style):
            result.elements.append(ProposedElement(row=0, type_label="", name=label, drawn="note"))
            continue
        candidates = shapes.types(c["style"])
        type_id = candidates[0] if len(candidates) == 1 else ""
        result.elements.append(
            ProposedElement(
                row=0,
                type_label=registry.types[type_id].name if type_id else "",
                name=label,
                drawn="shape",
                type_candidates=[] if type_id else candidates,
            )
        )
        ref_of[c["id"]], type_of[c["id"]] = label, type_id

    kept_rels: set[str] = set()
    for c in cells:
        if not c["edge"]:
            continue
        data = c["data"]
        src, dst = ref_of.get(c["source"], ""), ref_of.get(c["target"], "")
        if data.get("ea_origin") == ORIGIN:
            rel_id = data.get("ea_rel_id", "")
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

    if stamp.get("ea_origin") != ORIGIN:
        return
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
