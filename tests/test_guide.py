"""The guide (initiatives 24 and 27): getting started, one page for everyone and one per role,
shipped with the application, and the boundary of principle P9 drawn from the organisation's
own metamodel; then every screen's help between getting started and the roles."""

from __future__ import annotations

from dataclasses import replace

from tests.test_feeds_page import _texts

from ea.metamodel import Registry
from ea.services.guide import BOUNDARY_MARK, GuideService, slug
from ea.ui.pages.guide import render

ROLES = ["enterprise-architect", "solution-architect", "reviewer-and-steward", "reader", "metamodel-owner"]


def test_the_guide_opens_with_getting_started_then_what_belongs_then_a_page_per_role(registry):
    sections = GuideService(registry).sections()
    assert [s.slug for s in sections] == ["getting-started", "what-belongs", *ROLES]
    overview = sections[1]
    assert overview.markdown.count(BOUNDARY_MARK) == 1
    assert "## The boundary" in overview.markdown and slug("The boundary") == "the-boundary"
    assert all(s.markdown.strip() and not s.markdown.startswith("# ") for s in sections)


def test_the_boundary_is_read_from_the_organisation_s_metamodel(registry, pack):
    shipped = GuideService(registry).boundary()
    assert shipped.solution == []  # both packs the repository ships keep every type at the enterprise level
    layers = [layer for layer, _ in shipped.enterprise]
    assert layers.index("strategy") < layers.index("business") < layers.index("application")
    drawn = replace(
        pack,
        element_types=[
            replace(t, level="solution") if t.id == "data_entity" else t for t in pack.element_types
        ],
    )
    below = GuideService(Registry(drawn)).boundary()
    assert below.solution == [("application", ["Data Entity"])]
    assert "Data Entity" not in dict(below.enterprise).get("application", [])


def test_the_page_puts_the_boundary_where_the_overview_marks_it(app_context):
    text = _texts(render(app_context))
    assert "What belongs in the repository" in text and "Solution architect" in text
    assert "At the enterprise level" in text and "No type is placed below the enterprise level" in text
    assert BOUNDARY_MARK not in text


def _anchors(component) -> list[str]:
    out: list[str] = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if node is None or isinstance(node, (str, int, float)):
            return
        if isinstance(getattr(node, "id", None), str):
            out.append(node.id)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return out


def test_the_page_opens_with_getting_started_then_the_screens_then_the_roles(app_context):
    page = render(app_context)
    anchors = _anchors(page)
    order = [a for a in anchors if a in ("getting-started", "the-screens", "what-belongs", "reader")]
    assert order == ["getting-started", "the-screens", "what-belongs", "reader"]
    assert "screen-browse" in anchors and "screen-element" in anchors
    assert anchors.index("screen-browse") < anchors.index("screen-element") < anchors.index("screen-ask")


def test_every_anchor_on_the_page_is_its_own(app_context):
    """Two role pages both say *How you work*: an anchor per heading gave the page two elements
    with one id, which a link lands on at random and assistive technology reads as one."""
    anchors = _anchors(render(app_context))
    assert len(anchors) == len(set(anchors)), sorted({a for a in anchors if anchors.count(a) > 1})
    assert "the-boundary" in anchors  # Propose links to it by that name


def test_the_guide_brings_the_welcome_and_tips_back(app_context):
    assert "Show the welcome and tips again" in _texts(render(app_context))
