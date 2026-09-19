"""The element page's attributes: read and edited in the groups the metamodel declares.

An attribute's `group` is the section of the source metamodel's own document it is listed
under. Twenty common attributes in one undifferentiated table is a wall; the same twenty
under Identification, Governance, Classification and Standard dates is a page. The Edit tab
has always grouped its inputs — this is the page that only reads doing the same.
"""

from __future__ import annotations

from ea.models import Element
from ea.ui.pages.element import _attr_sections, _attr_values, _by_group


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _texts(parts: list) -> list[str]:
    out = []
    for part in parts:
        for node in _walk(part):
            children = getattr(node, "children", None)
            if isinstance(children, str):
                out.append(children)
    return out


def test_attributes_are_grouped_with_the_ungrouped_ones_first(registry):
    attrs = registry.attributes_for("information_asset")
    groups = list(_by_group(attrs))
    assert groups[0] == ""  # what the metamodel puts in no group comes first, unheaded
    assert groups[1:] == ["Identification", "Governance", "Classification", "Standard dates", "Risk ratings"]
    assert [a.name for a in _by_group(attrs)["Risk ratings"]] == [
        "confidentiality_risk_rating",
        "integrity_risk_rating",
        "availability_risk_rating",
    ]
    assert sum(len(v) for v in _by_group(attrs).values()) == len(attrs)


def test_only_the_attributes_that_carry_a_value_are_read_back(registry):
    attrs = registry.attributes_for("information_asset")
    values = {"alias": "CC", "owner": "Ada", "confidentiality_risk_rating": "High", "loose": "kept"}
    said = _texts(_attr_values(attrs, values))
    assert "Identification" in said and "Governance" in said and "Risk ratings" in said
    assert "Classification" not in said  # nothing in it carries a value, so it is not headed
    assert "Standard dates" not in said
    assert "Alias" in said and "Owner" in said
    assert "Confidentiality Risk Rating (restricted)" in said  # a restricted value is marked
    assert "Not in the metamodel" in said and "loose" in said
    assert _attr_values(attrs, {}) == []


def test_the_edit_form_is_grouped_the_same_way(registry):
    attrs = registry.attributes_for("information_asset")
    headings = _texts(_attr_sections(attrs, {}, "Type attributes"))
    assert headings[0] == "Type attributes"  # the ungrouped ones, under the form's own heading
    assert headings[1:6] == [
        "Identification",
        "Governance",
        "Classification",
        "Standard dates",
        "Risk ratings",
    ]


def test_an_element_with_no_attributes_says_nothing_rather_than_showing_empty_groups(registry):
    e = Element("X-1", "information_asset", "X")
    assert _attr_values(registry.attributes_for(e.type_id), e.attrs) == []
