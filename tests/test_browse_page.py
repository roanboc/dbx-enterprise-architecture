"""The Browse page's own logic: what the address says, what the count means, what narrows.

The page had no unit test at all — every claim about it rested on the browser round, which
runs on demand. These cover the parts that are pure functions of a filter and a store: the
address round-trip, the honest count behind a page, and the Health drill-down that used to
rewrite the total to the size of what survived a limit.
"""

from __future__ import annotations

from datetime import datetime

from ea.models import AttributeFilter, ElementFilter
from ea.ui.pages import browse


def test_the_address_carries_every_filter_and_reads_back_the_same(loaded):
    filt = ElementFilter(
        text="curriculum data",
        type_ids=["physical_application_component", "logical_data_component"],
        statuses=["approved"],
        current_states=["live"],
        target_states=["keep"],
        work_packages=["WP-CMS-UPGRADE"],
        sources=["sample"],
        lifecycle_statuses=["Live"],
        attributes=[AttributeFilter("owner", "curriculum office")],
        updated_since=datetime(2026, 1, 31),
        sort="updated",
        descending=True,
    )
    again, _ = browse.filter_from_query(browse.query_from_filter(filt))
    assert again.text == filt.text
    assert again.type_ids == filt.type_ids and again.statuses == filt.statuses
    assert again.current_states == filt.current_states and again.target_states == filt.target_states
    assert again.work_packages == filt.work_packages and again.sources == filt.sources
    assert again.lifecycle_statuses == filt.lifecycle_statuses
    assert [(a.name, a.value) for a in again.attributes] == [("owner", "curriculum office")]
    assert again.updated_since == datetime(2026, 1, 31)
    assert again.sort == "updated" and again.descending is True


def test_an_empty_filter_writes_an_empty_address(loaded):
    assert browse.query_from_filter(ElementFilter()) == ""
    filt, _ = browse.filter_from_query("")
    assert not filt.narrows()


def test_an_address_nobody_can_parse_narrows_nothing_rather_than_failing(loaded):
    """An address is typed and pasted, so it is never trusted."""
    filt, _ = browse.filter_from_query("?sort=sideways&since=last-tuesday&desc=maybe")
    assert filt.sort == "relevance", "an unknown sort falls back rather than raising"
    assert filt.updated_since is None
    assert filt.descending is False


def test_the_count_is_the_result_set_and_the_rows_are_one_page(app_context):
    ctx = app_context
    rows, total, _ = browse._load(ctx, ElementFilter(sort="name"), None, page=0)
    assert total == ctx.search.count(ElementFilter()), "the total is every matching row"
    assert len(rows) <= browse.PAGE_SIZE

    second, total_again, _ = browse._load(ctx, ElementFilter(sort="name"), None, page=1)
    assert total_again == total, "the total does not change with the page"
    assert not ({r["element_id"] for r in rows} & {r["element_id"] for r in second})


def test_a_health_drill_down_reports_the_whole_of_what_it_filtered(app_context):
    """The facet used to be applied after the row limit, and the total rewritten to what survived.

    The screen then read 'N of N' — a filtered list that looked like the whole answer, with
    matching rows past the limit silently dropped.
    """
    ctx = app_context
    facet = {"facet": "description", "source": "", "days": 90}
    rows, total, applied = browse._load(ctx, ElementFilter(sort="name"), facet, page=0)
    expected = len(ctx.health.ids_for("description", None, None, 90))
    assert total == expected, "the count is every element the facet names"
    assert applied.only_ids is not None, "the facet narrows in the store, not after the limit"
    assert len(rows) <= browse.PAGE_SIZE
    assert all(r["element_id"] in set(applied.only_ids) for r in rows)


def test_a_facet_that_names_nothing_shows_nothing_and_says_so(app_context):
    ctx = app_context
    filt = ElementFilter(type_ids=["no_such_type"])
    rows, total, _ = browse._load(ctx, filt, None, page=0)
    assert rows == [] and total == 0
    note = browse._filter_note(ctx, filt, {})
    assert "does not hold" in note


def test_the_chips_name_every_criterion_in_force(app_context):
    ctx = app_context
    filt = ElementFilter(
        text="curriculum",
        type_ids=["physical_application_component"],
        current_states=["live"],
        attributes=[AttributeFilter("owner")],
    )
    described = dict(browse.describing(ctx, filt))
    assert "words 'curriculum'" in described["q"]
    assert "Physical Application Component" in described["type"], "the type's name, not its id"
    assert described["current"] == "current state live"
    assert described["attr"] == "owner is set"


def test_the_empty_state_says_what_is_narrowing_the_list(app_context):
    ctx = app_context
    alert = browse._no_rows(ctx, ElementFilter(text="nothingmatchesthis", statuses=["retired"]))
    text = str(alert)
    assert "nothingmatchesthis" in text and "retired" in text


def test_only_the_columns_a_reader_chose_are_built(loaded):
    chosen = ["element_id", "name", "status"]
    fields = [c.get("field") for c in browse._columns(False, chosen)]
    assert fields == chosen
    with_ticks = [c.get("field") for c in browse._columns(True, chosen)]
    assert with_ticks[0] == "sel", "a role that can write gets the tick column"
    assert [c.get("field") for c in browse._columns(False, None)] == browse.DEFAULT_COLUMNS


def test_the_health_drill_down_source_is_not_also_a_store_predicate(app_context):
    """Health's `source=` names a bucket of its own, not a value the store holds.

    Health labels an element with no source system `(authored)`, so a drill-down link reads
    `?missing=never_updated&source=(authored)`. Once `source` became a filter criterion in
    its own right the one key meant two things at once: the store was asked for rows whose
    `source_system` is the literal `(authored)`, which is nothing, so every authored figure
    opened a grid reading `0 of 0` beside a page that had just said 1.
    """
    ctx = app_context
    filt, q = browse.filter_from_query("?missing=never_updated&source=(authored)")
    assert filt.sources == [], "the drill-down's bucket is not a source_system predicate"
    assert q.get("missing") == ["never_updated"]

    facet = {"facet": "never_updated", "source": "(authored)", "days": 90}
    rows, total, applied = browse._load(ctx, filt, facet, page=0)
    expected = ctx.health.ids_for("never_updated", None, "(authored)", 90)
    assert applied.only_ids is not None
    assert set(applied.only_ids) == expected
    assert total == len(expected), "the count is the figure the reader clicked"


def test_a_source_filter_still_narrows_when_no_drill_down_is_on(app_context):
    """The criterion itself is unharmed: it is only the drill-down's key that is not it."""
    filt, _ = browse.filter_from_query("?source=sample")
    assert filt.sources == ["sample"]
    rows, total, _ = browse._load(app_context, filt, None, page=0)
    assert total > 0 and all(r["source_system"] == "sample" for r in rows)


def test_the_drill_down_and_a_source_filter_can_both_be_in_the_address(app_context):
    """They are different questions, so they get different keys and narrow together."""
    filt, q = browse.filter_from_query("?missing=never_updated&facetsource=(authored)&source=sample")
    assert filt.sources == ["sample"], "the reader's own filter"
    assert q.get("facetsource") == ["(authored)"], "and the figure they came from"
