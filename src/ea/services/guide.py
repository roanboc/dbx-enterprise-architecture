"""The guide: what the repository is for and how to work in it, by role (initiative 24).

The pages are Markdown in `docs/guide/`, generic and shipped with the application. What
differs between organisations — which element types sit at the enterprise level and which
below it (principle P9) — is read from the organisation's metamodel when the page is drawn,
and stands where the overview marks it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ea.config import ROOT
from ea.metamodel.registry import Registry

GUIDE_DIR = ROOT / "docs" / "guide"
#: Where the overview takes the types the organisation's metamodel places on each side of the line.
BOUNDARY_MARK = "<!-- boundary -->"
LAYER_ORDER = (
    "motivation",
    "strategy",
    "business",
    "application",
    "technology",
    "physical",
    "implementation",
)


@dataclass
class GuideSection:
    slug: str  # the page's address fragment: `enterprise-architect`
    title: str
    markdown: str


@dataclass
class Boundary:
    """The metamodel's types by level, each list grouped by layer, top layer first."""

    enterprise: list[tuple[str, list[str]]] = field(default_factory=list)
    solution: list[tuple[str, list[str]]] = field(default_factory=list)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class GuideService:
    def __init__(self, registry: Registry, directory: Path = GUIDE_DIR):
        self.registry, self.directory = registry, directory

    def sections(self) -> list[GuideSection]:
        """The guide's pages in order: the overview, then one per role."""
        out = []
        for path in sorted(self.directory.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            text = path.read_text(encoding="utf-8")
            m = re.search(r"^#\s+(.+)$", text, re.M)
            title = m.group(1).strip() if m else path.stem
            body = text[m.end() :].lstrip("\n") if m else text
            out.append(GuideSection(re.sub(r"^\d+_", "", path.stem), title, body))
        return out

    def boundary(self) -> Boundary:
        """Which of the organisation's element types sit at the enterprise level, and which below it."""
        grouped: dict[str, dict[str, list[str]]] = {"enterprise": {}, "solution": {}}
        for t in self.registry.concrete_types():
            if not t.active:
                continue
            layer = self.registry.notation(t.id)["layer"]
            level = "solution" if t.level == "solution" else "enterprise"
            grouped[level].setdefault(layer, []).append(t.name)

        def ordered(by_layer: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
            rank = {layer: i for i, layer in enumerate(LAYER_ORDER)}
            return [
                (layer, sorted(names))
                for layer, names in sorted(by_layer.items(), key=lambda kv: rank.get(kv[0], 99))
            ]

        return Boundary(ordered(grouped["enterprise"]), ordered(grouped["solution"]))
