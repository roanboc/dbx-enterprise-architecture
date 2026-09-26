"""A deep dive's pack: the PDF and a draw.io file per diagram, in one ZIP (initiative 25, decision 0025).

The draw.io files are written from the same layout the PDF draws (`deep_dive_layout`), numbered
in the order the deep dive reads — level first — so the folder reads top-down as the PDF does
on paper. Every shape that stands for an element is an `object` carrying its identifier and a
link to its page, as every draw.io export here does; the architecture shapes are the ArchiMate
stencils the view export uses, the presentation shapes carry the icon the PDF draws. Every cell
carries the export's stamp, as the view export's do (`drawio.document`). Nothing is written in
Markdown.
"""

from __future__ import annotations

import html
import io
import xml.etree.ElementTree as ET
import zipfile

from ea.models import DeepDive
from ea.views.deep_dive_layout import (
    MUTED,
    Layout,
    Shape,
    figure_filename,
    figures,
    layout_figure,
    pack_filename,
)
from ea.views.deep_dive_pdf import deep_dive_pdf
from ea.views.drawio import _label, _object, document, node_style, stamped
from ea.views.icons import icon_data_uri
from ea.views.model import ViewNode

ICON_SIZE = 24
__all__ = ["build_pack", "diagram_files", "figure_filename", "layout_to_drawio", "pack_filename"]


# ------------------------------------------------------------------ draw.io
def _style(s: Shape) -> str:
    """The draw.io style of a shape the notation does not draw."""
    if s.kind == "text":
        style = "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;overflow=hidden;"
    elif s.kind == "badge":
        style = "ellipse;html=1;whiteSpace=wrap;"
    else:
        style = "html=1;whiteSpace=wrap;"
        if s.rounded:
            style += f"rounded=1;absoluteArcSize=1;arcSize={round(2 * s.rounded)};"
    style += f"fillColor={s.fill if s.fill != 'none' else 'none'};strokeColor={s.stroke};"
    style += f"fontColor={s.font};fontSize={round(s.font_size)};"
    if s.stroke_width != 1:
        style += f"strokeWidth={s.stroke_width};"
    if s.dashed:
        style += "dashed=1;dashPattern=6 3;"
    style += f"align={s.align};verticalAlign={s.valign};"
    if s.icon and s.style == "presentation":
        style += f"spacingLeft={ICON_SIZE + 14};"
    elif s.align == "left":
        style += "spacingLeft=8;"
    if s.valign == "top":
        style += "spacingTop=4;"
    if s.bold and not s.element_id:
        style += "fontStyle=1;"
    return style


def _html(s: Shape) -> str:
    """The label of a presentation shape: the name, and the identifier in small type beneath it (P8)."""
    name = html.escape(s.text)
    if s.bold:
        name = f"<b>{name}</b>"
    if s.sub:
        name += f'<br><span style="font-size:{max(6, round(s.font_size - 2))}px">{html.escape(s.sub)}</span>'
    return name


def layout_to_drawio(lay: Layout, base_url: str = "") -> str:
    """One layout as an uncompressed `.drawio` file, shape for shape."""
    mxfile, root, export_id = document(
        lay.title,
        "ea-repository deep dive",
        round(lay.width),
        round(lay.height),
        diagram_id="figure",
        elements=[s.element_id for s in lay.shapes if s.element_id],
        relationships=[line.relationship_id for line in lay.lines],
    )
    by_sid = {s.sid: s for s in lay.shapes}
    for s in lay.shapes:
        parent = s.parent if s.parent in by_sid else "1"
        ox, oy = (by_sid[parent].x, by_sid[parent].y) if parent != "1" else (0.0, 0.0)
        if s.element_id and s.style == "architecture" and s.node:
            node = ViewNode(**s.node)
            obj = _object(root, node, base_url, export_id, s.marked)
            obj.set(
                "label",
                f'{_label(node, s.marked)}<br><span style="font-size:8px">{html.escape(s.sub)}</span>',
            )
            cell = ET.SubElement(obj, "mxCell", style=node_style(node, s.marked), vertex="1", parent=parent)
        elif s.element_id:
            obj = stamped(root, s.sid, export_id, _html(s), ea_id=s.element_id, ea_name=s.text)
            if base_url:
                obj.set("link", f"{base_url}/element/{s.element_id}")
            cell = ET.SubElement(obj, "mxCell", style=_style(s), vertex="1", parent=parent)
        else:
            obj = stamped(root, s.sid, export_id, _html(s))
            cell = ET.SubElement(obj, "mxCell", style=_style(s), vertex="1", parent=parent)
        ET.SubElement(
            cell,
            "mxGeometry",
            x=str(round(s.x - ox)),
            y=str(round(s.y - oy)),
            width=str(round(s.w)),
            height=str(round(s.h)),
            **{"as": "geometry"},
        )
        if s.icon and s.style == "presentation":
            size = min(ICON_SIZE, s.h - 8)
            icon = ET.SubElement(
                stamped(root, f"{s.sid}__icon", export_id),
                "mxCell",
                style=f"shape=image;html=1;imageAspect=1;aspect=fixed;image={icon_data_uri(s.icon, s.icon_colour)};",
                vertex="1",
                parent=s.sid,
            )
            top = 6 if s.valign == "top" else (s.h - size) / 2
            ET.SubElement(
                icon,
                "mxGeometry",
                x="8",
                y=str(round(top)),
                width=str(round(size)),
                height=str(round(size)),
                **{"as": "geometry"},
            )
    for line in lay.lines:
        style = (
            f"endArrow={'open' if line.arrow else 'none'};endFill=0;html=1;rounded=0;edgeStyle=none;"
            f"strokeColor={line.colour};strokeWidth={line.width};fontSize=9;fontColor={MUTED};"
            "labelBackgroundColor=#ffffff;"
        )
        if line.dashed:
            style += "dashed=1;"
        data = {"ea_rel_id": line.relationship_id} if line.relationship_id else {}
        obj = stamped(root, line.lid, export_id, line.label, **data)
        cell = ET.SubElement(
            obj, "mxCell", style=style, edge="1", parent="1", source=line.src, target=line.dst
        )
        ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode")


def diagram_files(d: DeepDive, base_url: str = "") -> list[tuple[str, str]]:
    """(file name, draw.io document) for every figure, in reading order."""
    rows = d.content.get("elements") or {}
    return [
        (figure_filename(n, fig), layout_to_drawio(layout_figure(fig, rows), base_url))
        for n, fig in enumerate(figures(d.content), 1)
    ]


# ------------------------------------------------------------------ the pack
def build_pack(d: DeepDive, org_name: str = "", pack_name: str = "", base_url: str = "") -> bytes:
    """The ZIP a reader downloads: the PDF, and the diagrams it draws as draw.io files."""
    folder = pack_filename(d).removesuffix(".zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            f"{folder}/deep-dive.pdf",
            deep_dive_pdf(d, org_name=org_name, pack_name=pack_name, base_url=base_url),
        )
        for name, xml in diagram_files(d, base_url):
            z.writestr(f"{folder}/diagrams/{name}", xml)
    return buf.getvalue()
