"""The icons a presentation diagram draws, defined once and written into the PDF and the draw.io files.

An icon is a few primitives in a unit square — circles, rectangles, lines and polygons, `y`
downward — so the PDF draws them with its own graphics and draw.io reads them as a small SVG
image, and the two stay the same picture (decision 0025). Which icon an element gets is read
from what the metamodel's notation says it is: its ArchiMate kind, else its layer. No
framework's names are written here beyond ArchiMate's own element kinds, which the notation
already names (principle P5).
"""

from __future__ import annotations

import base64
from typing import Any

#: key → primitives. ("circle", cx, cy, r, filled), ("rect", x, y, w, h, rx, filled),
#: ("line", x1, y1, x2, y2), ("poly", [(x, y), ...], closed, filled).
ICONS: dict[str, list[tuple[Any, ...]]] = {
    "actor": [
        ("circle", 0.5, 0.2, 0.14, False),
        ("line", 0.5, 0.34, 0.5, 0.66),
        ("line", 0.22, 0.46, 0.78, 0.46),
        ("line", 0.5, 0.66, 0.28, 0.92),
        ("line", 0.5, 0.66, 0.72, 0.92),
    ],
    "role": [
        ("circle", 0.5, 0.28, 0.17, False),
        ("poly", [(0.16, 0.92), (0.2, 0.66), (0.36, 0.54), (0.64, 0.54), (0.8, 0.66), (0.84, 0.92)], True, False),
    ],
    "collaboration": [("circle", 0.38, 0.5, 0.24, False), ("circle", 0.62, 0.5, 0.24, False)],
    "process": [
        ("poly", [(0.08, 0.36), (0.6, 0.36), (0.6, 0.18), (0.92, 0.5), (0.6, 0.82), (0.6, 0.64), (0.08, 0.64)], True, False)
    ],
    "function": [("poly", [(0.2, 0.3), (0.5, 0.12), (0.8, 0.3), (0.8, 0.88), (0.5, 0.7), (0.2, 0.88)], True, False)],
    "interaction": [
        ("poly", [(0.46, 0.14), (0.2, 0.3), (0.2, 0.7), (0.46, 0.86)], False, False),
        ("poly", [(0.54, 0.14), (0.8, 0.3), (0.8, 0.7), (0.54, 0.86)], False, False),
    ],
    "event": [("poly", [(0.1, 0.24), (0.72, 0.24), (0.92, 0.5), (0.72, 0.76), (0.1, 0.76), (0.28, 0.5)], True, False)],
    "service": [("rect", 0.08, 0.3, 0.84, 0.4, 0.2, False)],
    "interface": [("circle", 0.66, 0.5, 0.2, False), ("line", 0.08, 0.5, 0.46, 0.5)],
    "object": [
        ("rect", 0.14, 0.14, 0.72, 0.72, 0.02, False),
        ("line", 0.14, 0.32, 0.86, 0.32),
        ("line", 0.26, 0.5, 0.74, 0.5),
        ("line", 0.26, 0.66, 0.74, 0.66),
    ],
    "document": [
        ("poly", [(0.2, 0.08), (0.62, 0.08), (0.8, 0.26), (0.8, 0.92), (0.2, 0.92)], True, False),
        ("poly", [(0.62, 0.08), (0.62, 0.26), (0.8, 0.26)], False, False),
        ("line", 0.32, 0.5, 0.68, 0.5),
        ("line", 0.32, 0.68, 0.68, 0.68),
    ],
    "component": [
        ("rect", 0.26, 0.14, 0.62, 0.72, 0.02, False),
        ("rect", 0.12, 0.28, 0.28, 0.14, 0.0, True),
        ("rect", 0.12, 0.58, 0.28, 0.14, 0.0, True),
    ],
    "node": [
        ("poly", [(0.12, 0.34), (0.66, 0.34), (0.66, 0.88), (0.12, 0.88)], True, False),
        ("poly", [(0.12, 0.34), (0.3, 0.14), (0.88, 0.14), (0.66, 0.34)], True, False),
        ("poly", [(0.66, 0.34), (0.88, 0.14), (0.88, 0.68), (0.66, 0.88)], True, False),
    ],
    "device": [
        ("rect", 0.1, 0.14, 0.8, 0.52, 0.04, False),
        ("line", 0.5, 0.66, 0.5, 0.82),
        ("line", 0.28, 0.86, 0.72, 0.86),
    ],
    "software": [("circle", 0.5, 0.5, 0.38, False), ("circle", 0.5, 0.5, 0.14, True)],
    "capability": [
        ("rect", 0.1, 0.62, 0.24, 0.26, 0.0, True),
        ("rect", 0.38, 0.38, 0.24, 0.5, 0.0, True),
        ("rect", 0.66, 0.12, 0.24, 0.76, 0.0, True),
    ],
    "value_stream": [
        ("poly", [(0.06, 0.26), (0.44, 0.26), (0.6, 0.5), (0.44, 0.74), (0.06, 0.74), (0.22, 0.5)], True, False),
        ("poly", [(0.5, 0.26), (0.78, 0.26), (0.94, 0.5), (0.78, 0.74), (0.5, 0.74), (0.66, 0.5)], True, True),
    ],
    "course": [
        ("circle", 0.66, 0.4, 0.24, False),
        ("circle", 0.66, 0.4, 0.08, True),
        ("line", 0.1, 0.9, 0.58, 0.48),
    ],
    "goal": [
        ("circle", 0.5, 0.5, 0.4, False),
        ("circle", 0.5, 0.5, 0.25, False),
        ("circle", 0.5, 0.5, 0.1, True),
    ],
    "outcome": [
        ("circle", 0.44, 0.56, 0.34, False),
        ("circle", 0.44, 0.56, 0.12, True),
        ("line", 0.44, 0.56, 0.9, 0.1),
        ("poly", [(0.9, 0.1), (0.74, 0.12), (0.88, 0.26)], True, True),
    ],
    "driver": [
        ("circle", 0.5, 0.5, 0.38, False),
        ("circle", 0.5, 0.5, 0.1, True),
        ("line", 0.5, 0.12, 0.5, 0.88),
        ("line", 0.12, 0.5, 0.88, 0.5),
        ("line", 0.23, 0.23, 0.77, 0.77),
        ("line", 0.77, 0.23, 0.23, 0.77),
    ],
    "assessment": [("circle", 0.42, 0.42, 0.26, False), ("line", 0.61, 0.61, 0.9, 0.9)],
    "principle": [
        ("rect", 0.18, 0.1, 0.64, 0.8, 0.06, False),
        ("rect", 0.45, 0.22, 0.1, 0.38, 0.0, True),
        ("rect", 0.45, 0.68, 0.1, 0.1, 0.0, True),
    ],
    "requirement": [("poly", [(0.26, 0.24), (0.94, 0.24), (0.74, 0.76), (0.06, 0.76)], True, False)],
    "constraint": [
        ("poly", [(0.26, 0.24), (0.94, 0.24), (0.74, 0.76), (0.06, 0.76)], True, False),
        ("line", 0.4, 0.24, 0.2, 0.76),
    ],
    "value": [("poly", [(0.5, 0.26), (0.84, 0.34), (0.94, 0.5), (0.84, 0.66), (0.5, 0.74), (0.16, 0.66), (0.06, 0.5), (0.16, 0.34)], True, False)],
    "work_package": [
        ("poly", [(0.82, 0.5), (0.76, 0.28), (0.6, 0.14), (0.4, 0.14), (0.24, 0.28), (0.18, 0.5), (0.24, 0.72), (0.4, 0.86), (0.6, 0.86)], False, False),
        ("poly", [(0.6, 0.72), (0.74, 0.86), (0.56, 0.98)], False, False),
    ],
    "gap": [
        ("circle", 0.5, 0.5, 0.36, False),
        ("line", 0.14, 0.42, 0.86, 0.42),
        ("line", 0.14, 0.58, 0.86, 0.58),
    ],
    "plateau": [
        ("line", 0.3, 0.26, 0.9, 0.26),
        ("line", 0.2, 0.5, 0.8, 0.5),
        ("line", 0.1, 0.74, 0.7, 0.74),
    ],
    "location": [
        ("poly", [(0.5, 0.94), (0.24, 0.52), (0.22, 0.34), (0.32, 0.16), (0.5, 0.08), (0.68, 0.16), (0.78, 0.34), (0.76, 0.52)], True, False),
        ("circle", 0.5, 0.36, 0.1, True),
    ],
    "product": [
        ("rect", 0.12, 0.3, 0.76, 0.58, 0.02, False),
        ("rect", 0.12, 0.14, 0.4, 0.16, 0.02, False),
    ],
    "resource": [
        ("rect", 0.08, 0.3, 0.74, 0.4, 0.04, False),
        ("rect", 0.82, 0.42, 0.08, 0.16, 0.0, True),
        ("rect", 0.14, 0.36, 0.3, 0.28, 0.0, True),
    ],
    "element": [("rect", 0.2, 0.2, 0.6, 0.6, 0.12, False)],
}  # fmt: skip

#: The icon for each kind the metamodel's notation may name.
ARCHIMATE_ICON = {
    "BusinessActor": "actor",
    "Stakeholder": "role",
    "BusinessRole": "role",
    "BusinessCollaboration": "collaboration",
    "ApplicationCollaboration": "collaboration",
    "BusinessInterface": "interface",
    "ApplicationInterface": "interface",
    "TechnologyInterface": "interface",
    "BusinessProcess": "process",
    "ApplicationProcess": "process",
    "TechnologyProcess": "process",
    "BusinessFunction": "function",
    "ApplicationFunction": "function",
    "TechnologyFunction": "function",
    "BusinessInteraction": "interaction",
    "ApplicationInteraction": "interaction",
    "BusinessEvent": "event",
    "ApplicationEvent": "event",
    "ImplementationEvent": "event",
    "BusinessService": "service",
    "ApplicationService": "service",
    "TechnologyService": "service",
    "BusinessObject": "object",
    "DataObject": "object",
    "Contract": "document",
    "Representation": "document",
    "Artifact": "document",
    "ApplicationComponent": "component",
    "Node": "node",
    "Device": "device",
    "SystemSoftware": "software",
    "Capability": "capability",
    "ValueStream": "value_stream",
    "CourseOfAction": "course",
    "Goal": "goal",
    "Outcome": "outcome",
    "Driver": "driver",
    "Assessment": "assessment",
    "Principle": "principle",
    "Requirement": "requirement",
    "Constraint": "constraint",
    "Meaning": "value",
    "Value": "value",
    "WorkPackage": "work_package",
    "Deliverable": "document",
    "Gap": "gap",
    "Plateau": "plateau",
    "Location": "location",
    "Product": "product",
    "Resource": "resource",
}
#: Where the notation names no kind, the layer picks the icon.
LAYER_ICON = {
    "motivation": "goal",
    "strategy": "capability",
    "business": "process",
    "application": "component",
    "technology": "node",
    "physical": "device",
    "implementation": "work_package",
    "other": "element",
}


def icon_for(archimate: str, layer: str) -> str:
    """The icon an element is drawn with: its kind's, else its layer's."""
    return ARCHIMATE_ICON.get(archimate or "") or LAYER_ICON.get(layer or "", "element")


def icon_svg(key: str, colour: str = "#ffffff", size: int = 24, stroke: float = 1.8) -> str:
    """The icon as a small SVG, the way draw.io draws it."""
    s = size
    parts: list[str] = []
    for p in ICONS.get(key, ICONS["element"]):
        if p[0] == "circle":
            _, cx, cy, r, filled = p
            fill = colour if filled else "none"
            parts.append(f'<circle cx="{cx * s:.2f}" cy="{cy * s:.2f}" r="{r * s:.2f}" fill="{fill}"/>')
        elif p[0] == "rect":
            _, x, y, w, h, rx, filled = p
            fill = colour if filled else "none"
            parts.append(
                f'<rect x="{x * s:.2f}" y="{y * s:.2f}" width="{w * s:.2f}" height="{h * s:.2f}" '
                f'rx="{rx * s:.2f}" fill="{fill}"/>'
            )
        elif p[0] == "line":
            _, x1, y1, x2, y2 = p
            parts.append(f'<line x1="{x1 * s:.2f}" y1="{y1 * s:.2f}" x2="{x2 * s:.2f}" y2="{y2 * s:.2f}"/>')
        else:
            _, points, closed, filled = p
            pts = " ".join(f"{x * s:.2f},{y * s:.2f}" for x, y in points)
            tag = "polygon" if closed else "polyline"
            parts.append(f'<{tag} points="{pts}" fill="{colour if filled else "none"}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">'
        f'<g stroke="{colour}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        + "".join(parts)
        + "</g></svg>"
    )


def icon_data_uri(key: str, colour: str = "#ffffff") -> str:
    """The icon as draw.io's style reads an image: base64 after the comma, no `;base64`, which a
    style would read as the end of the value."""
    return "data:image/svg+xml," + base64.b64encode(icon_svg(key, colour).encode()).decode()
