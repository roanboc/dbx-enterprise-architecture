"""The Feeds page: what it says about where a feed writes, and when it is meant to run.

Two things this page must not get wrong. A feed that writes to main skips the review every
other change goes through, so the page has to show that rather than leave it in a field
nobody opened. And a schedule shown without its zone is a time in somebody else's day.
"""

from __future__ import annotations

from datetime import datetime

from ea.models import SourceFeed
from ea.ui.pages.feeds import feed_row


def _texts(component) -> str:
    """Every string anywhere in a rendered component, flattened."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)
        for attribute in ("label", "description", "title"):
            value = getattr(node, attribute, None)
            if isinstance(value, str):
                out.append(value)

    walk(component)
    return " | ".join(out)


def test_a_feed_that_writes_to_main_says_so_on_the_row():
    """It is the one that lands without anybody reviewing it, so it is the one to show."""
    to_main = feed_row(SourceFeed(name="Reference model", elements_table="ref_elements"), "UTC", True, True)
    assert "→ main" in _texts(to_main)

    to_branch = feed_row(
        SourceFeed(name="CMDB", elements_table="cmdb_elements", target_branch="wip"),
        "UTC",
        True,
        True,
    )
    assert "→ wip" in _texts(to_branch)


def test_a_schedule_is_shown_with_the_zone_it_means():
    feed = SourceFeed(
        name="CMDB",
        elements_table="cmdb_elements",
        schedule="30 2 * * *",
        schedule_timezone="Australia/Brisbane",
    )
    shown = _texts(feed_row(feed, "UTC", True, True))
    assert "Every day at 02:30 (Australia/Brisbane)" in shown


def test_the_last_run_is_read_where_the_reader_is():
    feed = SourceFeed(
        name="CMDB",
        elements_table="cmdb_elements",
        last_run_at=datetime(2026, 9, 20, 16, 30),
        last_run_status="ok",
    )
    assert "2026-09-21 02:30 Australia/Brisbane" in _texts(feed_row(feed, "Australia/Brisbane", True, True))
    assert "Never run" in _texts(feed_row(SourceFeed(name="n", elements_table="t"), "UTC", True, True))


def test_a_feed_that_keeps_its_staging_tables_is_marked():
    """Because it is the exception: a feed normally empties what it loaded."""
    kept = feed_row(SourceFeed(name="Synced", elements_table="t", clear_after=False), "UTC", True, True)
    assert "keeps its staging tables" in _texts(kept)
    normal = feed_row(SourceFeed(name="Normal", elements_table="t"), "UTC", True, True)
    assert "keeps its staging tables" not in _texts(normal)


def test_a_disabled_feed_is_marked():
    off = feed_row(SourceFeed(name="Paused", elements_table="t", enabled=False), "UTC", True, True)
    assert "disabled" in _texts(off)


def test_the_buttons_are_off_for_a_role_that_may_not_use_them():
    """A reader sees what is configured and can press nothing."""
    row = feed_row(SourceFeed(name="n", elements_table="t"), "UTC", can_run=False, can_configure=False)

    def buttons(node, found=None):
        found = [] if found is None else found
        if isinstance(node, list):
            for item in node:
                buttons(item, found)
            return found
        if type(node).__name__ == "Button":
            found.append(node)
        children = getattr(node, "children", None)
        if children is not None:
            buttons(children, found)
        return found

    every = buttons(row)
    assert every and all(b.disabled for b in every)


def test_the_page_says_which_zone_it_shows_and_that_it_fires_nothing():
    """Saving a cron here makes nothing happen; a page that showed one without saying so would
    imply that it does. And a time without its zone is a time in somebody else's day."""
    from ea.ui.pages.feeds import schedule_notice

    notice = schedule_notice("Australia/Brisbane")
    assert "Australia/Brisbane" in notice
    assert "does not fire one" in notice
    assert "runs a feed on demand" in notice


# ------------------------------------------- what a run left, said briefly


def test_a_run_is_summarised_on_the_card_by_what_it_changed():
    """The report's own sentence is written for a terminal: the counts that stayed at zero
    crowd out the ones that did not, and four dense lines is what a card gets."""
    from ea.ui.pages.feeds import run_in_brief

    loaded = (
        "source=s elements 2/2 loaded (2 new, 0 updated, 0 unchanged, 0 retired, 0 skipped), "
        "relationships 1/1 loaded (1 new, 0 updated, 0 unchanged, 0 skipped), links 0/0; "
        "0 errors, 0 warnings"
    )
    # the kinds stay apart: '3 new' across elements and relationships names nothing to act on
    assert run_in_brief(loaded) == "elements 2 new · relationships 1 new"


def test_a_run_that_changed_nothing_says_so_in_two_words():
    from ea.ui.pages.feeds import run_in_brief

    quiet = (
        "source=s elements 0/0 loaded (0 new, 0 updated, 0 unchanged, 0 retired, 0 skipped), "
        "relationships 0/0 loaded (0 new, 0 updated, 0 unchanged, 0 skipped), links 0/0; "
        "0 errors, 0 warnings"
    )
    assert run_in_brief(quiet) == "Nothing changed"
    assert run_in_brief("") == ""


def test_a_run_with_errors_says_so_however_much_it_changed():
    from ea.ui.pages.feeds import run_in_brief

    partial = (
        "source=s elements 1/3 loaded (0 new, 1 updated, 0 unchanged, 1 retired, 2 skipped), "
        "relationships 0/0 loaded (0 new, 0 updated, 0 unchanged, 0 skipped), links 0/0; "
        "3 errors, 0 warnings"
    )
    assert run_in_brief(partial) == "elements 1 updated, 1 retired, 2 skipped — with errors"

    nothing = (
        "source=s elements 0/2 loaded (0 new, 0 updated, 0 unchanged, 0 retired, 2 skipped), "
        "relationships 0/0 loaded (0 new, 0 updated, 0 unchanged, 0 skipped), links 0/0; "
        "2 errors, 0 warnings"
    )
    assert "with errors" in run_in_brief(nothing)


def test_the_whole_summary_is_still_reachable_from_the_card():
    """Brief is not the same as gone: the report's own sentence stays, under the pointer."""
    feed = SourceFeed(
        name="n",
        elements_table="t",
        last_run_at=datetime(2026, 9, 20, 16, 30),
        last_run_status="ok",
        last_run_summary="source=s elements 2/2 loaded (2 new, 0 updated, 0 unchanged, 0 retired, 0 skipped); 0 errors, 0 warnings",
    )
    shown = _texts(feed_row(feed, "UTC", True, True))
    assert "elements 2 new" in shown  # the brief
    assert "2/2 loaded" in shown  # and the whole of it, as the tooltip's label


def test_the_mapping_field_says_what_it_is_for_and_shows_an_example():
    """A box labelled only 'Mapping (YAML)' asks a question without saying what an answer is."""
    from ea.ui.pages.feeds import MAPPING_EXAMPLE, MAPPING_HELP

    assert "Leave this empty" in MAPPING_HELP  # most feeds need none, and that is said first
    assert "id_prefix" in MAPPING_EXAMPLE and "match_on" in MAPPING_EXAMPLE
    assert "columns" in MAPPING_EXAMPLE and "type_names" in MAPPING_EXAMPLE


def test_the_example_mapping_is_one_the_importer_can_actually_read():
    """An example that does not parse teaches the wrong thing."""
    from ea.importer import mapping_from_text
    from ea.ui.pages.feeds import MAPPING_EXAMPLE

    mapping = mapping_from_text(MAPPING_EXAMPLE)
    assert mapping.id_prefix == "CMDB-"
    assert mapping.match_on == "id"
    assert mapping.element_columns["CI_ID"] == "id"
    assert mapping.type_names["Server"] == "physical_technology_component"
    assert mapping.relationship_columns["FROM_CI"] == "src_id"


# ------------------------------------- where the tables live, and their shape


def test_the_form_names_the_schema_the_tables_are_read_from():
    """A form asking for three table names without saying which schema they live in is asking
    half a question. The schema is the deployment's, through EA_SCHEMA."""
    from ea.ui.pages.feeds import staging_note

    note = staging_note("ea")
    assert "ea_staging" in note
    assert "EA_SCHEMA" in note  # and that the deployment is what names it
    assert "never reaches outside it" in note

    # a deployment that renames the prefix gets its own schema named back
    assert "acme_staging" in staging_note("acme")


def test_the_example_is_the_contract_by_example_with_its_schema_beside_it(backend, registry):
    """Somebody filling the form in should not have to go and find what the columns are."""
    import io
    import zipfile

    from ea.importer.csv_export import contract_example

    with zipfile.ZipFile(io.BytesIO(contract_example(backend, registry))) as archive:
        assert sorted(archive.namelist()) == [
            "README.md",
            "elements.csv",
            "links.csv",
            "relationships.csv",
            "schema.csv",
        ]
        elements = archive.read("elements.csv").decode("utf-8").splitlines()
        assert elements[0].startswith("id,type,name")
        assert len(elements) > 1, "an example with no row shows nothing"
        # the schema is generated from the applied version, not shipped
        schema = archive.read("schema.csv").decode("utf-8")
        assert "logical_data_component" in schema
