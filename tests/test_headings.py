"""Every screen's outline: one level-1 heading, the page's title, and no section heading more
than one level deeper than the heading before it.

A screen reader lists a page by its headings, and an outline that jumps from h1 to h3 tells
its reader a level is missing. The browser round reads the headings each screen draws; this
reads the component tree each page's `render()` returns, so a section headed a level too deep
fails here on every change rather than in the next round. A dialog, a drawer and a dropdown
are drawn outside the page and are left out, as the round leaves them out; the panels of a set
of tabs are read one at a time from where the tabs stand, since only one of them is shown.
"""

from __future__ import annotations

import importlib
import re

import dash_mantine_components as dmc
import pytest
from dash import dcc, html

from ea.services.roles import use_role

#: Every page the router draws, with what its address hands it.
PAGES = [
    ("home", ()),
    ("guide", ()),
    ("browse", (None,)),
    ("ask", (None,)),
    ("impact", (None,)),
    ("target", (None,)),
    ("branches", (None,)),
    ("import_page", ()),
    ("feeds", ()),
    ("propose", ()),
    ("metamodel", ()),
    ("organisations", (None,)),
    ("systems", ()),
    ("health", ()),
    ("users", ()),
]

#: Drawn in a layer of their own outside the page, so not part of its outline.
OUTSIDE = {"Modal", "Drawer", "PopoverDropdown", "MenuDropdown", "HoverCardDropdown"}
#: Shown one at a time.
ALTERNATIVES = {"TabsPanel", "AccordionPanel"}
#: Properties other than `children` a component may draw inside the page.
DRAWN = ("children", "label", "title", "description", "leftSection", "rightSection")

HTML_HEADING = re.compile(r"^H([1-6])$")
MD_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
MD_FENCE = re.compile(r"^ {0,3}(```|~~~)")


def _text(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return " ".join(_text(n) for n in node)
    return _text(getattr(node, "children", "") or "")


def _markdown_headings(source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    fenced = False
    for line in source.splitlines():
        if MD_FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and (m := MD_HEADING.match(line)):
            out.append((len(m.group(1)), m.group(2)))
    return out


def _heading(node) -> tuple[int, str] | None:
    if isinstance(node, dmc.Title):
        return (getattr(node, "order", None) or 1, _text(node.children))
    if getattr(node, "_namespace", "") == "dash_html_components" and (
        m := HTML_HEADING.match(type(node).__name__)
    ):
        return (int(m.group(1)), _text(node.children))
    return None


class Outline:
    """The headings a tree draws, read in document order, and every place the order breaks."""

    def __init__(self) -> None:
        self.tops: list[str] = []
        self.skips: list[str] = []

    def see(self, level: int, text: str, previous: int) -> int:
        if level == 1:
            self.tops.append(text)
        if level > previous + 1:
            self.skips.append(f"h{previous} → h{level} at {text[:48]!r}")
        return level

    def walk(self, node, previous: int) -> int:
        """Read `node` after a heading at level `previous` (0 before any); the level it leaves."""
        if node is None or isinstance(node, (str, int, float, bool)):
            return previous
        if isinstance(node, (list, tuple)):
            return self.alternatives(node, previous)
        name = type(node).__name__
        if name in OUTSIDE:
            return previous
        if (found := _heading(node)) is not None:
            return self.see(*found, previous)
        if isinstance(node, dcc.Markdown):
            for level, text in _markdown_headings(_text(node.children)):
                previous = self.see(level, text, previous)
            return previous
        # A tooltip's label floats in a layer of its own; what it wraps is on the page.
        for attribute in ("children",) if name == "Tooltip" else DRAWN:
            value = getattr(node, attribute, None)
            if value is not None and not isinstance(value, str):
                previous = self.walk(value, previous)
        return previous

    def alternatives(self, nodes, previous: int) -> int:
        """Siblings in order; the panels among them each from where they stand, and what follows
        them from the shallowest place any of them leaves, which is the strictest."""
        ends: list[int] = []
        for n in nodes:
            if type(n).__name__ in ALTERNATIVES:
                ends.append(self.walk(n, previous))
            else:
                previous = self.walk(n, min(ends) if ends else previous)
                ends = []
        return min(ends) if ends else previous


def outline(tree) -> Outline:
    o = Outline()
    o.walk(tree, 0)
    return o


def _assert_follows_on(where: str, o: Outline) -> None:
    assert len(o.tops) == 1, (
        f"{where}: {len(o.tops)} level-1 headings {o.tops[:4]}; the page title is the one"
    )
    assert not o.skips, f"{where}: a heading skips a level — {'; '.join(o.skips)}"


# ------------------------------------------------------------------ the reader


def test_the_reader_finds_a_skip_and_a_second_title():
    o = outline(
        html.Div([dmc.Title("Page", order=1), dmc.Paper(dmc.Title("Card", order=3)), html.H2("Next")])
    )
    assert o.tops == ["Page"] and o.skips == ["h1 → h3 at 'Card'"]
    assert outline([dmc.Title("A"), dmc.Title("B", order=1)]).tops == ["A", "B"], "a Title is h1 unless told"


def test_the_reader_reads_markdown_headings_but_not_a_fenced_hash():
    md = dcc.Markdown("## Why\n\n```bash\n# a comment\n```\n#### Deeper")
    o = outline([dmc.Title("Page", order=1), md])
    assert o.tops == ["Page"] and o.skips == ["h2 → h4 at 'Deeper'"]


def test_the_reader_leaves_dialogs_out_and_reads_each_tab_from_where_the_tabs_stand():
    tree = [
        dmc.Title("Page", order=1),
        dmc.Modal(dmc.Title("Dialog", order=4), id="m"),
        dmc.Tabs(
            [
                dmc.TabsList([dmc.TabsTab("A", value="a"), dmc.TabsTab("B", value="b")]),
                dmc.TabsPanel([dmc.Title("A", order=2), dmc.Title("A.1", order=3)], value="a"),
                dmc.TabsPanel(dmc.Title("B", order=3), value="b"),
            ]
        ),
    ]
    assert outline(tree).skips == ["h1 → h3 at 'B'"], "tab B is read after the page title, not after A.1"


# ------------------------------------------------------------------ the pages


@pytest.mark.parametrize("role", ["admin", "reader"])
@pytest.mark.parametrize("module, args", PAGES, ids=[m for m, _ in PAGES])
def test_every_screen_has_one_title_and_no_heading_skips_a_level(app_context, module, args, role):
    page = importlib.import_module(f"ea.ui.pages.{module}")
    with use_role(role):
        _assert_follows_on(f"{module} as {role}", outline(page.render(app_context, *args)))


@pytest.mark.parametrize("role", ["admin", "reader"])
def test_the_element_page_has_one_title_and_no_heading_skips_a_level(app_context, role):
    from ea.ui.pages import element

    with use_role(role):
        for e in app_context.repo.search(limit=5):
            _assert_follows_on(
                f"element {e.element_id} as {role}", outline(element.render(app_context, e.element_id))
            )
        _assert_follows_on("an element not found", outline(element.render(app_context, "NOPE-0")))


def test_impact_opened_on_an_element_has_one_title_and_no_heading_skips_a_level(app_context):
    """An address naming an element draws its result with the page, and the result's sections."""
    from ea.ui.pages import impact

    some = app_context.repo.search(limit=1)[0]
    with use_role("admin"):
        _assert_follows_on("impact", outline(impact.render(app_context, f"?element={some.element_id}")))
