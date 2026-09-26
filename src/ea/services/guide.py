"""The guide: what the repository is for and how to work in it, by role (initiative 24), and
the help of every screen with getting started before it (initiative 27).

The pages are Markdown in `docs/guide/`, generic and shipped with the application: the role
pages beside this module's reader, and one page per screen in `docs/guide/screens/`, which
the side panel beside a screen's title and the Guide page both draw. What differs between
organisations — which element types sit at the enterprise level and which below it
(principle P9) — is read from the organisation's metamodel when the page is drawn, and
stands where the overview marks it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ea.config import ROOT
from ea.metamodel.registry import Registry

GUIDE_DIR = ROOT / "docs" / "guide"
SCREENS = "screens"  # the folder, under the guide's, of one help page per screen
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


@dataclass
class ScreenHelp:
    """One screen's help: its title, the one-line tip a first visit shows, and the rest —
    why, what you see, how, the flow drawn and tips — as Markdown."""

    key: str  # the page's key: `browse`, `element`, `users`
    title: str
    tip: str
    markdown: str
    related: list[str] = field(default_factory=list)  # other screens' keys


_RELATED = re.compile(r"<!--\s*related:\s*(.*?)\s*-->", re.S)


def parse_screen(key: str, text: str) -> ScreenHelp:
    """A screen's page read into its parts: `<!-- related: … -->`, `# Title`, `> tip`, the body."""
    m = _RELATED.search(text)
    related = m.group(1).split() if m else []
    text = _RELATED.sub("", text).strip()
    heading = re.search(r"^#\s+(.+)$", text, re.M)
    title = heading.group(1).strip() if heading else key
    rest = text[heading.end() :] if heading else text
    lines = rest.strip("\n").splitlines()
    tip: list[str] = []
    while lines and lines[0].startswith(">"):
        tip.append(lines.pop(0).lstrip("> ").strip())
    return ScreenHelp(key, title, " ".join(tip).strip(), "\n".join(lines).strip(), related)


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

    def screens(self) -> dict[str, ScreenHelp]:
        """Every screen's help, by the page's key."""
        folder = self.directory / SCREENS
        return {
            path.stem: parse_screen(path.stem, path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("*.md"))
            if path.name.lower() != "readme.md"
        }

    def screen(self, key: str) -> ScreenHelp | None:
        """One screen's help, or None when the screen has none."""
        path = self.directory / SCREENS / f"{key}.md"
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", key or "") or not path.is_file():
            return None
        return parse_screen(key, path.read_text(encoding="utf-8"))

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
