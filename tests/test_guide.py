"""The guide (initiative 24): one page for everyone and one per role, shipped with the
application, and the boundary of principle P9 drawn from the organisation's own metamodel."""

from __future__ import annotations

from dataclasses import replace

from tests.test_feeds_page import _texts

from ea.metamodel import Registry
from ea.services.guide import BOUNDARY_MARK, GuideService, slug
from ea.ui.pages.guide import render

ROLES = ["enterprise-architect", "solution-architect", "reviewer-and-steward", "reader", "metamodel-owner"]


def test_the_guide_opens_with_what_belongs_then_a_page_per_role(registry):
    sections = GuideService(registry).sections()
    assert [s.slug for s in sections] == ["what-belongs", *ROLES]
    overview = sections[0]
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
