"""A deep dive as a styled PDF, drawn in Python with ReportLab (decision 0025).

It reads from the top down, as the deep dive does: the cover, what the reader needs to know,
then the context and the overview drawn to be presented, the architecture and the detail in the
metamodel's notation, and last the findings, the inconsistencies, the references and how it was
answered. Every diagram is drawn from the same layout its draw.io file is written from, and
names that file. It is drawn from what the deep dive kept alone.

ReportLab's standard fonts write the Windows Western character set; anything outside it is
written as the nearest thing that set holds, so an unusual name never stops a PDF.
"""

from __future__ import annotations

import io
import math
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ea.models import MATURITY_LEVELS, DeepDive
from ea.views.deep_dive_layout import (
    INK,
    MATURITY_FILL,
    MUTED,
    PRESENT,
    RULE,
    SEVERITY_FILL,
    Layout,
    Shape,
    figure_filename,
    layout_figure,
    tint,
)
from ea.views.icons import ICONS
from ea.views.model import view_from_dict

ACCENT = "#1d4e89"
LEVEL_COLOUR = {
    1: PRESENT["strategy"],
    2: PRESENT["business"],
    3: PRESENT["application"],
    4: PRESENT["technology"],
}
CONFIDENCE_FILL = {"high": "#2f9e44", "medium": "#f08c00", "low": "#c92a2a"}
KIND_LABEL = {
    "impact": "Impact",
    "landscape": "Landscape",
    "transition": "Transition",
    "flow": "Information flow",
    "quality": "Model quality",
}
RULE_LABEL = {
    "names_unrelated": "Names an element nothing joins it to",
    "state": "A state contradicts its relationships",
    "status": "The status contradicts what is written",
    "link": "A link is malformed or repeated",
    "source_disagrees": "The page it links to disagrees with the model",
}
LEVEL_NOTE = {
    "presentation": "Drawn to be shared and presented: colour by layer, an icon for what each element is.",
    "architecture": "Drawn in the metamodel's notation, as the application draws a view: the layer is the fill.",
}
_SUBSTITUTE = {"→": "->", "←": "<-", "⇒": "=>", "Δ": "delta", "≤": "<=", "≥": ">=", "✓": "v", "★": "*"}


def safe(text: Any) -> str:
    """Text the standard fonts can write."""
    out = str(text if text is not None else "")
    for k, v in _SUBSTITUTE.items():
        out = out.replace(k, v)
    return out.encode("cp1252", errors="replace").decode("cp1252")


def _p(text: Any) -> str:
    return escape(safe(text))


def _hex(value: str) -> Any:
    return None if not value or value == "none" else colors.HexColor(value)


# ------------------------------------------------------------------ styles
BODY = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=colors.HexColor(INK)
)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, textColor=colors.HexColor(MUTED))
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.8, leading=9.8)
CELL_B = ParagraphStyle("cell_b", parent=CELL, fontName="Helvetica-Bold")
CAPTION = ParagraphStyle("caption", parent=SMALL, fontName="Helvetica-Oblique", fontSize=7.5, leading=9.5)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=4)
H2 = ParagraphStyle(
    "h2", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4
)
LEAD = ParagraphStyle("lead", parent=BODY, fontSize=12, leading=17)
TAG = ParagraphStyle(
    "tag", parent=BODY, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white
)


# ------------------------------------------------------------------ diagrams
def drawing(lay: Layout, max_w: float, max_h: float) -> Drawing:
    """A layout as a ReportLab drawing, scaled to fit and never enlarged."""
    s = min(max_w / max(lay.width, 1), max_h / max(lay.height, 1), 1.0)
    d = Drawing(lay.width * s, lay.height * s)
    g = Group()
    g.transform = (s, 0, 0, s, 0, 0)
    height = lay.height

    def Y(y: float) -> float:
        return height - y

    by_sid = {sh.sid: sh for sh in lay.shapes}
    behind = [sh for sh in lay.shapes if sh.kind in ("panel", "band")]
    front = [sh for sh in lay.shapes if sh.kind not in ("panel", "band")]
    for sh in behind:
        _shape(g, sh, Y)
    for line in lay.lines:
        a, b = by_sid.get(line.src), by_sid.get(line.dst)
        if a is not None and b is not None:
            _line(g, a, b, line, Y)
    for sh in front:
        _shape(g, sh, Y)
    d.add(g)
    return d


def _shape(g: Group, sh: Shape, Y) -> None:
    fill, stroke = _hex(sh.fill), _hex(sh.stroke)
    dash = [5, 3] if sh.dashed else None
    if sh.kind == "badge":
        g.add(
            Circle(
                sh.x + sh.w / 2,
                Y(sh.y + sh.h / 2),
                sh.w / 2,
                fillColor=fill,
                strokeColor=stroke,
                strokeWidth=1,
            )
        )
    elif sh.kind != "text" and (fill is not None or stroke is not None):
        g.add(
            Rect(
                sh.x,
                Y(sh.y + sh.h),
                sh.w,
                sh.h,
                rx=sh.rounded,
                ry=sh.rounded,
                fillColor=fill,
                strokeColor=stroke,
                strokeWidth=sh.stroke_width if stroke is not None else 0,
                strokeDashArray=dash,
            )
        )
    left, text_w = sh.x + 8, sh.w - 16
    if sh.icon:
        if sh.style == "architecture":
            size = 13.0
            _icon(g, sh.icon, sh.x + sh.w - size - 5, sh.y + 5, size, sh.icon_colour, Y)
            text_w = sh.w - 2 * (size + 8)
            left = sh.x + size + 8
        else:
            size = min(24.0, sh.h - 12) if sh.valign != "top" else 20.0
            top = sh.y + (sh.h - size) / 2 if sh.valign != "top" else sh.y + 4
            _icon(g, sh.icon, sh.x + 8, top, size, sh.icon_colour, Y)
            left, text_w = sh.x + size + 16, sh.w - size - 24
    _text(g, sh, left, text_w, Y)


def _wrap(text: str, font: str, size: float, width: float, most: int) -> list[str]:
    words, lines, cur = safe(text).split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > most:
        lines = lines[:most]
        while lines[-1] and stringWidth(lines[-1] + "…", font, size) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _text(g: Group, sh: Shape, left: float, width: float, Y) -> None:
    if not sh.text and not sh.sub:
        return
    font = "Helvetica-Bold" if sh.bold else "Helvetica"
    size, sub_size = sh.font_size, max(5.5, sh.font_size - 2)
    centred = sh.align == "center" and sh.kind not in ("panel", "band")
    room = sh.h - 8 - (sub_size * 1.25 if sh.sub else 0)
    most = max(1, int(room // (size * 1.2))) if sh.kind not in ("panel",) else 1
    lines = _wrap(sh.text, font, size, max(20.0, width), most)
    block = len(lines) * size * 1.2 + (sub_size * 1.25 if sh.sub else 0)
    top = sh.y + 7 if sh.valign == "top" or sh.kind == "panel" else sh.y + (sh.h - block) / 2
    colour = colors.HexColor(sh.font)
    anchor = "middle" if centred else "start"
    x = left + width / 2 if centred else left
    for n, line in enumerate(lines):
        baseline = top + (n + 1) * size * 1.2 - size * 0.25
        g.add(String(x, Y(baseline), line, fontName=font, fontSize=size, fillColor=colour, textAnchor=anchor))
        if sh.strike and n == 0:
            w = stringWidth(line, font, size)
            x0 = x - w / 2 if centred else x
            g.add(
                Line(
                    x0,
                    Y(baseline - size * 0.3),
                    x0 + w,
                    Y(baseline - size * 0.3),
                    strokeColor=colour,
                    strokeWidth=1,
                )
            )
    if sh.sub:
        baseline = top + len(lines) * size * 1.2 + sub_size * 1.1
        g.add(
            String(
                x,
                Y(baseline),
                safe(sh.sub),
                fontName="Helvetica",
                fontSize=sub_size,
                fillColor=colour,
                textAnchor=anchor,
            )
        )


def _icon(g: Group, key: str, x: float, top: float, size: float, colour: str, Y) -> None:
    """The icon from its primitives: the same picture draw.io reads as an SVG."""
    col = colors.HexColor(colour)
    sw = max(0.8, size / 13)
    for p in ICONS.get(key, ICONS["element"]):
        if p[0] == "circle":
            _, cx, cy, r, filled = p
            g.add(
                Circle(
                    x + cx * size,
                    Y(top + cy * size),
                    r * size,
                    fillColor=col if filled else None,
                    strokeColor=col,
                    strokeWidth=sw,
                )
            )
        elif p[0] == "rect":
            _, rx, ry, w, h, r, filled = p
            g.add(
                Rect(
                    x + rx * size,
                    Y(top + (ry + h) * size),
                    w * size,
                    h * size,
                    rx=r * size,
                    ry=r * size,
                    fillColor=col if filled else None,
                    strokeColor=col,
                    strokeWidth=sw,
                )
            )
        elif p[0] == "line":
            _, x1, y1, x2, y2 = p
            g.add(
                Line(
                    x + x1 * size,
                    Y(top + y1 * size),
                    x + x2 * size,
                    Y(top + y2 * size),
                    strokeColor=col,
                    strokeWidth=sw,
                )
            )
        else:
            _, points, closed, filled = p
            flat = [v for px, py in points for v in (x + px * size, Y(top + py * size))]
            if closed:
                g.add(Polygon(flat, fillColor=col if filled else None, strokeColor=col, strokeWidth=sw))
            else:
                g.add(PolyLine(flat, strokeColor=col, strokeWidth=sw))


def _border(sh: Shape, tx: float, ty: float) -> tuple[float, float]:
    """Where the segment from a shape's centre towards (tx, ty) leaves the shape."""
    cx, cy = sh.x + sh.w / 2, sh.y + sh.h / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    scale = min(
        (sh.w / 2) / abs(dx) if dx else float("inf"),
        (sh.h / 2) / abs(dy) if dy else float("inf"),
    )
    return cx + dx * scale, cy + dy * scale


def _line(g: Group, a: Shape, b: Shape, line: Any, Y) -> None:
    ax, ay = _border(a, b.x + b.w / 2, b.y + b.h / 2)
    bx, by = _border(b, a.x + a.w / 2, a.y + a.h / 2)
    col = colors.HexColor(line.colour)
    g.add(
        Line(
            ax,
            Y(ay),
            bx,
            Y(by),
            strokeColor=col,
            strokeWidth=line.width,
            strokeDashArray=[5, 3] if line.dashed else None,
        )
    )
    if line.arrow:
        angle = math.atan2(by - ay, bx - ax)
        size = 6 + line.width
        left = (bx - size * math.cos(angle - 0.4), by - size * math.sin(angle - 0.4))
        right = (bx - size * math.cos(angle + 0.4), by - size * math.sin(angle + 0.4))
        g.add(
            PolyLine(
                [left[0], Y(left[1]), bx, Y(by), right[0], Y(right[1])],
                strokeColor=col,
                strokeWidth=line.width,
            )
        )
    if line.label:
        label = safe(line.label)
        size = 7.0
        w = stringWidth(label, "Helvetica", size) + 4
        mx, my = (ax + bx) / 2, (ay + by) / 2
        g.add(
            Rect(
                mx - w / 2,
                Y(my + size * 0.6),
                w,
                size * 1.3,
                fillColor=colors.white,
                strokeColor=None,
                strokeWidth=0,
            )
        )
        g.add(
            String(
                mx,
                Y(my + size * 0.3),
                label,
                fontName="Helvetica",
                fontSize=size,
                fillColor=colors.HexColor(MUTED),
                textAnchor="middle",
            )
        )


# ------------------------------------------------------------------ the document
class _Document(BaseDocTemplate):
    def __init__(self, buf: io.BytesIO, d: DeepDive, cover: dict[str, str], compress: bool):
        super().__init__(
            buf,
            pagesize=A4,
            leftMargin=17 * mm,
            rightMargin=17 * mm,
            topMargin=20 * mm,
            bottomMargin=17 * mm,
            title=safe(d.title),
            author="EA Repository",
            subject="Deep dive",
            creator="EA Repository",
            pageCompression=1 if compress else 0,
            invariant=1,
        )
        self.dive, self.cover = d, cover
        body = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        first = Frame(self.leftMargin, self.bottomMargin, self.width, self.height - 72 * mm, id="cover")
        self.addPageTemplates(
            [
                PageTemplate("cover", [first], onPage=self._on_cover),
                PageTemplate("body", [body], onPage=self._on_body),
            ]
        )

    def _on_cover(self, canvas, doc) -> None:
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(ACCENT))
        canvas.rect(0, h - 80 * mm, w, 80 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor(PRESENT["strategy"]))
        canvas.rect(0, h - 82 * mm, w, 2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(17 * mm, h - 22 * mm, safe(f"DEEP DIVE  ·  {self.cover['kind'].upper()}"))
        canvas.setFont("Helvetica-Bold", 24)
        y = h - 36 * mm
        for line in _wrap(self.dive.title, "Helvetica-Bold", 24, w - 34 * mm, 3):
            canvas.drawString(17 * mm, y, line)
            y -= 29
        canvas.setFont("Helvetica", 9.5)
        canvas.drawString(
            17 * mm,
            h - 74 * mm,
            safe(f"{self.cover['org']}  ·  read on {self.cover['branch']}  ·  {self.cover['when']}"),
        )
        canvas.restoreState()
        self._footer(canvas, doc)

    def _on_body(self, canvas, doc) -> None:
        w, h = A4
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(17 * mm, h - 12 * mm, safe(f"Deep dive  ·  {self.cover['kind']}"))
        title = _wrap(self.dive.title, "Helvetica", 7.5, 110 * mm, 1)[0]
        canvas.drawRightString(w - 17 * mm, h - 12 * mm, title)
        canvas.setStrokeColor(colors.HexColor(RULE))
        canvas.setLineWidth(0.6)
        canvas.line(17 * mm, h - 14 * mm, w - 17 * mm, h - 14 * mm)
        canvas.restoreState()
        self._footer(canvas, doc)

    def _footer(self, canvas, doc) -> None:
        w, _ = A4
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(
            17 * mm, 10 * mm, safe(f"Generated from the model as it stood on {self.cover['as_of']}")
        )
        canvas.drawRightString(w - 17 * mm, 10 * mm, f"{doc.page}")
        canvas.restoreState()


def _table(
    data: list[list[Any]], widths: list[float], header: bool = True, extra: list[tuple] | None = None
) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(MUTED)),
        ]
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def _chapter(title: str, tag: str, colour: str, note: str = "") -> list[Any]:
    head = Table(
        [[Paragraph(_p(tag), TAG), Paragraph(_p(title), H1)]],
        colWidths=[26 * mm, None],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(colour)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
            ]
        ),
    )
    out: list[Any] = [head, Spacer(1, 4)]
    if note:
        out.append(Paragraph(_p(note), SMALL))
    out.append(Spacer(1, 8))
    return out


def _name(rows: dict[str, dict[str, Any]], i: str) -> str:
    r = rows.get(i)
    return f"{r['name']} [{i}]" if r else i


def _maturity_cell(level: int) -> str:
    return f"{level} — {MATURITY_LEVELS.get(level, '')}"


STAR_FILL, STAR_EMPTY = "#f5b301", "#dde2e8"


def _star(cx: float, cy: float, r: float) -> list[float]:
    points: list[float] = []
    for n in range(10):
        radius = r if n % 2 == 0 else r * 0.45
        angle = math.pi / 2 + n * math.pi / 5
        points += [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
    return points


def stars(value: float | None, count: int = 0, size: float = 9.0) -> Drawing:
    """A rating as five stars, filled to the half, with how many rated it beside them."""
    value = max(0.0, min(5.0, round((value or 0) * 2) / 2))
    label = f"({count})" if count else ""
    step = size * 1.2
    d = Drawing(5 * step + (stringWidth(label, "Helvetica", size * 0.9) + 3 if label else 0), size + 2)
    g = Group()
    for n in range(5):
        cx, cy, r = n * step + size / 2, size / 2 + 1, size / 2
        whole = n + 1 <= value
        g.add(
            Polygon(
                _star(cx, cy, r),
                fillColor=colors.HexColor(STAR_FILL if whole else STAR_EMPTY),
                strokeColor=None,
            )
        )
        if not whole and n + 0.5 <= value:  # half a star: its left side, over the empty one
            half = _star(cx, cy, r)
            half = [min(v, cx) if i % 2 == 0 else v for i, v in enumerate(half)]
            g.add(Polygon(half, fillColor=colors.HexColor(STAR_FILL), strokeColor=None))
    if label:
        g.add(
            String(
                5 * step + 2,
                1.5,
                label,
                fontName="Helvetica",
                fontSize=size * 0.9,
                fillColor=colors.HexColor(MUTED),
            )
        )
    d.add(g)
    return d


def _finding_card(f: dict[str, Any], rows: dict[str, dict[str, Any]], width: float) -> Table:
    level = {1: "Context", 2: "Overview", 3: "Architecture", 4: "Detail"}.get(f.get("level"), "")
    rests = ", ".join(_name(rows, i) for i in f["elements"][:12]) + (
        " and more" if len(f["elements"]) > 12 else ""
    )
    body = [
        Paragraph(f"<b>{_p(f['id'])}</b>  ·  {_p(f['severity'].upper())}  ·  {_p(level)}", SMALL),
        Paragraph(f"<b>{_p(f['title'])}</b>", BODY),
        Paragraph(_p(f["text"]), BODY),
        Paragraph(f"<b>Rests on:</b> {_p(rests)}", SMALL),
        Paragraph(f"<b>Why it matters:</b> {_p(f['why'])}", SMALL),
    ]
    return Table(
        [["", body]],
        colWidths=[3 * mm, width - 3 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(SEVERITY_FILL.get(f["severity"], MUTED))),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f8f9fb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING", (1, 0), (1, 0), 5),
                ("BOTTOMPADDING", (1, 0), (1, 0), 6),
            ]
        ),
    )


def deep_dive_pdf(
    d: DeepDive, org_name: str = "", pack_name: str = "", base_url: str = "", compress: bool = True
) -> bytes:
    """The deep dive as a PDF, from what it kept."""
    c = d.content or {}
    rows: dict[str, dict[str, Any]] = c.get("elements") or {}
    brief = d.brief or {}
    kind = KIND_LABEL.get(d.kind, d.kind)
    cover = {
        "kind": kind,
        "org": org_name or "The organisation",
        "branch": f"branch {d.branch_id}" if d.branch_id else "main",
        "when": str(d.created_at or c.get("as_of") or "")[:16].replace("T", " "),
        "as_of": c.get("as_of", "")[:16].replace("T", " "),
    }
    buf = io.BytesIO()
    doc = _Document(buf, d, cover, compress)
    width = doc.width
    story: list[Any] = [Paragraph(_p(c.get("brief_sentence", "")), LEAD), Spacer(1, 10)]

    # ---- the cover
    conf = c.get("confidence") or {}
    layers = ", ".join(brief.get("layers") or []) or "every layer"
    facts = [
        ["Organisation", cover["org"]],
        ["Read on", cover["branch"]],
        [
            "Metamodel",
            f"{pack_name or d.pack_id} {('version ' + d.pack_version) if d.pack_version else ''}".strip(),
        ],
        ["Asked by", d.created_by or "—"],
        ["When", cover["when"]],
        ["Kind of analysis", kind],
        ["Reach", f"{brief.get('reach', '')} step(s), across {layers}"],
        ["What it is for", brief.get("purpose") or "No particular decision"],
        ["The question", brief.get("question") or "—"],
    ]
    story.append(
        _table(
            [[Paragraph(f"<b>{_p(k)}</b>", CELL), Paragraph(_p(v), CELL)] for k, v in facts],
            [38 * mm, width - 38 * mm],
            header=False,
        )
    )
    story.append(Spacer(1, 12))
    badge = Table(
        [
            [
                Paragraph(f"<b>{_p('Confidence: ' + str(conf.get('level', '')).upper())}</b>", TAG),
                Paragraph(_p(conf.get("text", "")), BODY),
            ]
        ],
        colWidths=[38 * mm, width - 38 * mm],
        style=TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, 0),
                    colors.HexColor(CONFIDENCE_FILL.get(conf.get("level"), MUTED)),
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
            ]
        ),
    )
    story += [badge, NextPageTemplate("body"), PageBreak()]

    # ---- what you need to know
    findings = c.get("findings") or []
    by_id = {f["id"]: f for f in findings}
    story += _chapter("What you need to know", "FIRST", ACCENT)
    story.append(Paragraph(_p(c.get("summary", "")), BODY))
    story.append(Spacer(1, 10))
    read = c.get("read") or {}
    severities = {s: sum(1 for f in findings if f["severity"] == s) for s in ("high", "medium", "low")}
    stats = [
        (str(read.get("elements", 0)), "elements read"),
        (str(read.get("relationships", 0)), "relationships among them"),
        (str(conf.get("average", "")), "average maturity, of 5"),
        (
            f"{severities['high']} / {severities['medium']} / {severities['low']}",
            "findings: high / medium / low",
        ),
        (str(len(c.get("inconsistencies") or [])), "inconsistencies"),
    ]
    story.append(
        Table(
            [
                [Paragraph(f"<font size=16><b>{_p(v)}</b></font>", BODY) for v, _ in stats],
                [Paragraph(_p(label), SMALL) for _, label in stats],
            ],
            colWidths=[width / len(stats)] * len(stats),
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f4f8")),
                    ("LINEAFTER", (0, 0), (-2, -1), 2, colors.white),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ]
            ),
        )
    )
    story.append(Spacer(1, 12))
    headline = [by_id[h["id"]] for h in c.get("headline") or [] if h["id"] in by_id]
    if headline:
        story.append(Paragraph("The findings that matter most", H2))
        for f in headline:
            story += [_finding_card(f, rows, width), Spacer(1, 6)]
    else:
        story.append(Paragraph("The rules found nothing to report in what was read.", BODY))
    work = c.get("work_packages") or []
    if work:
        story.append(Paragraph("Work in flight", H2))
        story.append(
            Paragraph(
                "Work packages planned or under way that change elements this deep dive read: what the "
                "model shows may not be what is there when a decision lands.",
                SMALL,
            )
        )
        story.append(
            _table(
                [[Paragraph(f"<b>{h}</b>", CELL) for h in ("Work package", "State", "What it changes")]]
                + [
                    [
                        Paragraph(_p(f"{w['name']} [{w['element_id']}]"), CELL),
                        Paragraph(_p(w["current_state"].replace("_", " ")), CELL),
                        Paragraph(_p(", ".join(_name(rows, i) for i in w["elements"])), CELL),
                    ]
                    for w in work
                ],
                [width * 0.34, width * 0.14, width * 0.52],
            )
        )
    if read.get("truncated"):
        story.append(
            Paragraph(
                "It stopped at the most one analysis may read; narrow the reach or the layers to see the rest.",
                SMALL,
            )
        )

    # ---- the four levels, top-down
    number = 0
    for level in c.get("levels") or []:
        story += [
            PageBreak(),
            *_chapter(
                level["title"],
                f"LEVEL {level['level']}",
                LEVEL_COLOUR.get(level["level"], ACCENT),
                LEVEL_NOTE.get(level["style"], ""),
            ),
        ]
        charts: list[list[Any]] = []
        for fig in level.get("figures") or []:
            number += 1
            if fig["kind"].startswith("chart_"):  # charts stand side by side, two to a row
                charts.append(_figure_block(fig, number, rows, width / 2 - 4 * mm, 70 * mm))
                continue
            block = _figure_block(fig, number, rows, width, 175 * mm)
            story += [CondPageBreak(60 * mm), KeepTogether(block[:4]), *block[4:]]
            if fig["kind"] == "view":
                story += [Spacer(1, 6), _elements_table(fig, rows, width)]
            story.append(Spacer(1, 12))
        for n in range(0, len(charts), 2):
            pair = charts[n : n + 2] + ([[]] if len(charts[n : n + 2]) == 1 else [])
            story.append(
                KeepTogether(
                    [
                        Table(
                            [pair],
                            colWidths=[width / 2] * 2,
                            style=TableStyle(
                                [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]
                            ),
                        )
                    ]
                )
            )

    # ---- findings
    story += [
        PageBreak(),
        *_chapter(
            "Findings",
            "RULES",
            ACCENT,
            "Each finding comes from a rule the application already applies; it cites the elements it rests on.",
        ),
    ]
    if not findings:
        story.append(Paragraph("None.", BODY))
    for f in findings:
        story += [KeepTogether([_finding_card(f, rows, width)]), Spacer(1, 6)]

    # ---- inconsistencies
    story += [
        Spacer(1, 10),
        *_chapter(
            "Inconsistencies",
            "RECORD",
            PRESENT["implementation"],
            "Where an element and what the repository holds about it disagree.",
        ),
    ]
    inconsistencies = c.get("inconsistencies") or []
    if inconsistencies:
        story.append(
            _table(
                [[Paragraph("<b>Kind</b>", CELL), Paragraph("<b>What disagrees</b>", CELL)]]
                + [
                    [
                        Paragraph(_p(RULE_LABEL.get(x["rule"], x["rule"])), CELL),
                        Paragraph(_p(x["text"]), CELL),
                    ]
                    for x in inconsistencies
                ],
                [50 * mm, width - 50 * mm],
            )
        )
    else:
        story.append(Paragraph("None found in what was read.", BODY))

    # ---- references
    refs = c.get("references") or {}
    story += [PageBreak(), *_chapter("References", "SOURCES", ACCENT)]
    story.append(Paragraph("Earlier deep dives on the same elements, best rated first", H2))
    dives = refs.get("deep_dives") or []
    if dives:
        story.append(
            _table(
                [[Paragraph(f"<b>{h}</b>", CELL) for h in ("Deep dive", "Kind", "By, when", "Rating")]]
                + [
                    [
                        Paragraph(
                            _p(x["title"])
                            + (" <i>(run again from this one)</i>" if x.get("run_again_from") else ""),
                            CELL,
                        ),
                        Paragraph(_p(KIND_LABEL.get(x.get("kind", ""), x.get("kind", ""))), CELL),
                        Paragraph(_p(f"{x.get('created_by', '')}, {x.get('created_at', '')}"), CELL),
                        stars(x["rating_average"], x["rating_count"])
                        if x.get("rating_count")
                        else Paragraph("Not rated yet", CELL),
                    ]
                    for x in dives
                ],
                [width * 0.46, width * 0.16, width * 0.2, width * 0.18],
            )
        )
    else:
        story.append(Paragraph("None: this is the first deep dive on these elements.", BODY))
    links = refs.get("links") or []
    if links:
        story.append(Paragraph("Documentation the key elements link to", H2))
        read = [x for x in links if x.get("read")]
        story.append(
            Paragraph(
                f"{len(read)} read through the organisation's connected systems, as the reader, and cited as "
                "theirs; the rest listed, not read."
                if read
                else "Listed, not read: the analysis rests on what the repository holds.",
                SMALL,
            )
        )
        story.append(
            _table(
                [[Paragraph(f"<b>{h}</b>", CELL) for h in ("Element", "Link", "Read")]]
                + [
                    [
                        Paragraph(_p(_name(rows, x["element_id"])), CELL),
                        Paragraph(_p(f"{x.get('label') or ''} {x['url']}".strip()), CELL),
                        Paragraph(
                            _p(
                                f"from {x.get('system')}, {str(x.get('read_at') or '')[:16]}"
                                if x.get("read")
                                else "not read"
                            ),
                            CELL,
                        ),
                    ]
                    for x in links
                ],
                [width * 0.3, width * 0.45, width * 0.25],
            )
        )
    story.append(Paragraph("The elements it cites", H2))
    cited = [r for r in rows.values()]
    story.append(
        _table(
            [[Paragraph(f"<b>{h}</b>", CELL) for h in ("Element", "Type", "Layer", "Maturity", "Why")]]
            + [
                [
                    Paragraph(
                        _p(f"{r['name']} [{r['element_id']}]")
                        + (
                            f"<br/><font color='{MUTED}'>{_p(base_url + '/element/' + r['element_id'])}</font>"
                            if base_url
                            else ""
                        ),
                        CELL,
                    ),
                    Paragraph(_p(r.get("type_name", "")), CELL),
                    Paragraph(_p(r.get("layer", "").capitalize()), CELL),
                    Paragraph(_p(_maturity_cell(int(r.get("maturity") or 1))), CELL),
                    Paragraph(_p(r.get("maturity_why", "")), CELL),
                ]
                for r in cited
            ],
            [width * 0.27, width * 0.17, width * 0.15, width * 0.13, width * 0.28],
            extra=_maturity_backgrounds(cited, 3),
        )
    )

    # ---- how it was answered
    trace = c.get("trace") or {}
    story += [PageBreak(), *_chapter("How it was answered", "TRACE", MUTED)]
    who = (
        "the rules alone"
        if trace.get("provider") == "rules"
        else f"the rules, and a model ({trace.get('provider')}, {trace.get('model')}) for the summary"
    )
    story.append(
        Paragraph(
            _p(f"Answered by {who}. Every read was bounded; the analysis wrote nothing to the model."), BODY
        )
    )
    if trace.get("model_error"):
        story.append(
            Paragraph(
                _p(f"The model could not write the summary ({trace['model_error']}); the rules wrote it."),
                SMALL,
            )
        )
    ungrounded = trace.get("ungrounded") or []
    story.append(
        Paragraph(
            _p(
                "Identifiers the summary cites that the analysis did not read: " + ", ".join(ungrounded)
                if ungrounded
                else "Every identifier the summary cites is one the analysis read."
            ),
            BODY,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        _table(
            [[Paragraph("<b>Step</b>", CELL), Paragraph("<b>What it read</b>", CELL)]]
            + [
                [Paragraph(_p(s.get("tool", "")), CELL), Paragraph(_p(s.get("detail", "")), CELL)]
                for s in trace.get("steps") or []
            ],
            [35 * mm, width - 35 * mm],
        )
    )
    doc.build(story)
    return buf.getvalue()


def _figure_block(
    fig: dict[str, Any], number: int, rows: dict[str, dict[str, Any]], max_w: float, max_h: float
) -> list[Any]:
    """A figure's title, its drawing, the draw.io file that opens it, and a short reading of it."""
    return [
        Paragraph(f"{_p(fig['fid'])}  {_p(fig['title'])}", H2),
        drawing(layout_figure(fig, rows), max_w, max_h),
        Spacer(1, 3),
        Paragraph(f"Figure {_p(fig['fid'])}  ·  diagrams/{_p(figure_filename(number, fig))}", CAPTION),
        Spacer(1, 4),
        Paragraph(_p(fig.get("reading", "")), BODY),
    ]


def _maturity_backgrounds(rows: list[dict[str, Any]], column: int) -> list[tuple]:
    out = []
    for n, r in enumerate(rows, 1):
        fill = MATURITY_FILL.get(int(r.get("maturity") or 1), MATURITY_FILL[1])
        out.append(("BACKGROUND", (column, n), (column, n), colors.HexColor(tint(fill, 0.55))))
    return out


def _elements_table(fig: dict[str, Any], rows: dict[str, dict[str, Any]], width: float) -> Table:
    """What a view draws, with each element's maturity and its states."""
    nodes = [n for n in view_from_dict(fig["view"]).nodes if n.id in rows]
    data = [[Paragraph(f"<b>{h}</b>", CELL) for h in ("Element", "Type", "Maturity", "Now, and as targeted")]]
    listed = []
    for n in nodes:
        r = rows[n.id]
        listed.append(r)
        data.append(
            [
                Paragraph(_p(f"{r['name']} [{n.id}]"), CELL_B if n.focus else CELL),
                Paragraph(_p(r.get("type_name", "")), CELL),
                Paragraph(_p(_maturity_cell(int(r.get("maturity") or 1))), CELL),
                Paragraph(
                    _p(f"{r.get('current_state', '')}, {r.get('target_state', '')}".replace("_", " ")), CELL
                ),
            ]
        )
    return _table(
        data, [width * 0.42, width * 0.24, width * 0.16, width * 0.18], extra=_maturity_backgrounds(listed, 2)
    )
