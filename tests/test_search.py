"""Search and filtering: what narrows a list, how it is ranked, and how it pages.

The Browse page had one test between it and a regression, in another file. These are the
edges that matter once the model is larger than a screen: that ranking sees every matching
row rather than the alphabetical first few, that a count says what it means, that a page
boundary neither repeats nor loses a row, and that a `%` a person types is a `%`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ea.backend.branching import use_branch
from ea.models import AttributeFilter, Element, ElementFilter
from ea.services import BranchService, RepositoryService, SearchService


@pytest.fixture
def search(loaded, registry):
    return SearchService(loaded, registry)


def test_the_best_match_is_found_however_late_it_sorts(loaded, search):
    """Ranking used to happen after an alphabetical cut at 5,000 rows.

    A model larger than the cut hid its own best answer: the row whose *name* starts with
    the query could not be in the page unless it also sorted early. The store ranks now, so
    the cut is by rank and the answer is first.
    """
    loaded.upsert_elements(
        [
            Element(f"GEN-{i:05d}", "capability", f"aaa filler {i:05d}", description_md="mentions zebra")
            for i in range(6000)
        ],
        "t",
    )
    loaded.upsert_elements([Element("GEN-BEST", "capability", "zebra crossing register")], "t")

    f = ElementFilter(text="zebra")
    assert search.count(f) == 6001, "the count is the whole result set, not the page"
    assert search.search(f, limit=3)[0].element.element_id == "GEN-BEST"


def test_a_page_is_the_rows_after_the_page_before_it(loaded, search):
    f = ElementFilter(sort="name")
    first = [h.element.element_id for h in search.search(f, limit=10)]
    second = [h.element.element_id for h in search.search(f, limit=10, offset=10)]
    assert len(set(first) & set(second)) == 0, "a row shown twice across a page boundary"
    whole = [h.element.element_id for h in search.search(f, limit=20)]
    assert first + second == whole


def test_a_percent_a_person_types_is_a_percent(loaded, search):
    loaded.upsert_elements(
        [Element("PCT-1", "capability", "50% complete"), Element("PCT-2", "capability", "50 units")],
        "t",
    )
    hits = [h.element.element_id for h in search.search(ElementFilter(text="50%"))]
    assert hits == ["PCT-1"], "the wildcard matched every row holding '50'"


def test_every_criterion_narrows_and_they_narrow_together(loaded, registry, search):
    repo = RepositoryService(loaded, registry)
    repo.create_element(
        "physical_application_component",
        "Filter subject",
        "t",
        element_id="PAC-F",
        current_state="planned",
        target_state="change",
        status="draft",
    )
    subject = loaded.get_element("PAC-F")
    subject.source_system = "cmdb"
    subject.lifecycle_status = "Production"
    loaded.update_element(subject, "t")

    def ids(**kw):
        return [h.element.element_id for h in search.search(ElementFilter(**kw), limit=500)]

    assert "PAC-F" in ids(current_states=["planned"])
    assert "PAC-F" in ids(target_states=["change"])
    assert "PAC-F" in ids(sources=["cmdb"])
    assert "PAC-F" in ids(lifecycle_statuses=["Production"])
    assert "PAC-F" in ids(type_ids=["physical_application_component"], statuses=["draft"])
    # they narrow together: a criterion it does not meet takes it out
    assert "PAC-F" not in ids(current_states=["planned"], target_states=["keep"])
    # several values of one criterion widen it
    assert set(ids(current_states=["planned", "live"])) >= {"PAC-F"}


def test_an_attribute_can_be_asked_for_by_name_and_by_value(loaded, registry, search):
    repo = RepositoryService(loaded, registry)
    repo.create_element(
        "logical_data_component", "Attributed", "t", element_id="LDC-A", attrs={"owner": "the registry team"}
    )

    def ids(*attrs):
        return [h.element.element_id for h in search.search(ElementFilter(attributes=list(attrs)), limit=500)]

    assert "LDC-A" in ids(AttributeFilter("owner")), "set to anything"
    assert "LDC-A" in ids(AttributeFilter("owner", "registry team")), "and to this"
    assert "LDC-A" not in ids(AttributeFilter("owner", "somebody else"))
    assert "LDC-A" not in ids(AttributeFilter("no_such_attribute"))


def test_a_hit_says_which_field_carried_the_words(loaded, registry, search):
    """A row in the list with no stated reason reads as a bug in the search."""
    repo = RepositoryService(loaded, registry)
    repo.create_element(
        "logical_data_component", "Reasoned", "t", element_id="LDC-R", attrs={"owner": "marsupial"}
    )
    hit = next(h for h in search.search(ElementFilter(text="marsupial")) if h.element.element_id == "LDC-R")
    assert hit.matched_in == "attribute:owner" and hit.snippet


def test_the_sort_is_the_store_s_and_it_can_be_reversed(loaded, search):
    names = [h.element.name for h in search.search(ElementFilter(sort="name"), limit=5)]
    assert names == sorted(names, key=str.lower) or names == sorted(names)
    reverse = [h.element.name for h in search.search(ElementFilter(sort="name", descending=True), limit=5)]
    assert reverse[0] >= names[0]


def test_a_filter_sees_the_branch_it_is_read_on(loaded, registry, search):
    BranchService(loaded, registry).create("Search branch", "ana")
    repo = RepositoryService(loaded, registry)
    with use_branch("search-branch"):
        repo.create_element("logical_data_component", "Only on the branch", "ana", element_id="LDC-BR")
        on_branch = [h.element.element_id for h in search.search(ElementFilter(text="Only on the branch"))]
    on_main = [h.element.element_id for h in search.search(ElementFilter(text="Only on the branch"))]
    assert on_branch == ["LDC-BR"] and on_main == []


def test_an_updated_window_narrows_by_time(loaded, registry, search):
    repo = RepositoryService(loaded, registry)
    repo.create_element("logical_data_component", "Recent", "t", element_id="LDC-T")
    now = loaded.get_element("LDC-T").updated_at
    assert isinstance(now, datetime)
    within = ElementFilter(updated_since=now - timedelta(minutes=5))
    assert "LDC-T" in [h.element.element_id for h in search.search(within, limit=500)]
    before = ElementFilter(updated_before=now - timedelta(minutes=5))
    assert "LDC-T" not in [h.element.element_id for h in search.search(before, limit=500)]


def test_only_ids_narrows_to_a_set_and_an_empty_set_is_empty(loaded, search):
    some = [h.element.element_id for h in search.search(ElementFilter(sort="name"), limit=3)]
    assert [h.element.element_id for h in search.search(ElementFilter(only_ids=some))] == some
    assert search.search(ElementFilter(only_ids=[])) == []
    assert search.count(ElementFilter(only_ids=[])) == 0


def test_the_options_on_a_filter_come_from_the_rows(loaded, search):
    assert isinstance(search.values("source_system"), list)
    with pytest.raises(ValueError, match="not a filterable column"):
        search.values("attrs")
