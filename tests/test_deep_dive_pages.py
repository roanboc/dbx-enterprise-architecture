"""The deep dive on the pages (initiative 25, WP7): Ask's deep mode, the Deep dives page, the element page.

What a page decides — which brief a reader's words start, whether the deep dive can be
written yet, whose name it is kept under, who may withdraw it, what the catalogue's address
narrows it to, what a download holds — is a function of the context, proven here rather than
only in the browser round.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from ea.models import Forbidden
from ea.services import use_role
from ea.ui.pages import ask_deep, deep_dives


def _walk(node, out: list, hrefs: list) -> None:
    if isinstance(node, str):
        out.append(node)
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, out, hrefs)
        return
    children = getattr(node, "children", None)
    if children is not None:
        _walk(children, out, hrefs)
    for attribute in ("label", "description", "title", "placeholder"):
        value = getattr(node, attribute, None)
        if isinstance(value, str):
            out.append(value)
        elif value is not None and not isinstance(value, (bool, int, float)):
            _walk(value, out, hrefs)
    href = getattr(node, "href", None)
    if isinstance(href, str):
        hrefs.append(href)


def _texts(component) -> str:
    out: list[str] = []
    _walk(component, out, [])
    return " | ".join(out)


def _hrefs(component) -> list[str]:
    hrefs: list[str] = []
    _walk(component, [], hrefs)
    return hrefs


def _written(ctx, question: str = "What happens if PAC-CMS is decommissioned?", actor_role: str = "reader"):
    brief = ask_deep.start(ctx, question)
    with use_role(actor_role):
        return ask_deep.write(ctx, brief)


# --------------------------------------------------------------- Ask, deep mode
def test_a_deep_dive_starts_from_the_reader_s_words(app_context):
    brief = ask_deep.start(app_context, "What happens if PAC-CMS is decommissioned?")
    assert brief["subject"] == ["PAC-CMS"] and brief["kind"] == "impact"
    text = _texts(ask_deep.brief_panel(app_context, brief))
    assert "An impact analysis of Curriculum Management System [PAC-CMS]" in text
    assert "What should the analysis be about?" in text and "Which kind of analysis?" in text


def test_the_deep_dive_is_written_only_once_the_brief_says_what_and_which_kind(app_context):
    brief = ask_deep.start(app_context, "PAC-CMS")
    disabled, reason = ask_deep.write_state(app_context, brief)
    assert disabled and "kind" in reason
    brief = ask_deep.answer(app_context, brief, "kind", "landscape", "")
    assert brief["kind"] == "landscape"
    assert ask_deep.write_state(app_context, brief) == (False, "")


def test_an_answer_the_question_does_not_offer_is_said_not_applied(app_context):
    brief = ask_deep.start(app_context, "PAC-CMS")
    after = ask_deep.answer(app_context, brief, "subject", "other", "zzzz nothing like it")
    assert after["subject"] == ["PAC-CMS"] and "Nothing in the model" in after["note"]


def test_a_deep_dive_is_kept_under_the_reader_s_name_when_written(app_context):
    d = _written(app_context)
    kept = app_context.deep_dives.get(d.deep_dive_id)
    assert kept is not None and kept.created_by == app_context.actor
    text = _texts(ask_deep.result_card(app_context, d))
    assert d.title in text and "Download the pack" in text
    assert f"/deep-dives?open={d.deep_dive_id}" in _hrefs(ask_deep.result_card(app_context, d))


def test_the_assistant_may_not_keep_a_deep_dive(app_context):
    brief = ask_deep.start(app_context, "What happens if PAC-CMS is decommissioned?")
    with use_role("agent"), pytest.raises(Forbidden):
        ask_deep.write(app_context, brief)


def test_the_brief_lists_the_earlier_deep_dives_on_its_subject(app_context):
    earlier = _written(app_context)
    brief = ask_deep.start(app_context, "What happens if PAC-CMS is decommissioned?")
    panel = ask_deep.brief_panel(app_context, brief)
    assert earlier.title in _texts(panel)
    assert f"/deep-dives?open={earlier.deep_dive_id}" in _hrefs(panel)


# ----------------------------------------------------------- the Deep dives page
def test_the_catalogue_reads_what_narrows_it_from_the_address():
    n = deep_dives.narrow_from_search(
        "?kind=impact&element=PAC-CMS&min_rating=4&withdrawn=1&text=cms&open=dd-1"
    )
    assert n["kind"] == "impact" and n["element_id"] == "PAC-CMS" and n["min_rating"] == 4
    assert n["include_withdrawn"] is True and n["text"] == "cms" and n["open"] == "dd-1"
    assert deep_dives.narrow_from_search("") == deep_dives.narrow_from_search(None)
    assert deep_dives.narrow_from_search("?min_rating=nine")["min_rating"] is None


def test_the_catalogue_lists_narrows_and_opens_a_deep_dive(app_context):
    impact = _written(app_context)
    landscape = _written(app_context, "the landscape around PAC-SRS")
    rows, total = deep_dives.catalogue_rows(app_context, deep_dives.narrow_from_search("?kind=impact"))
    assert [d.deep_dive_id for d in rows] == [impact.deep_dive_id] and total == 1
    listed, _ = deep_dives.catalogue_rows(app_context, deep_dives.narrow_from_search(""))
    text = _texts(deep_dives.catalogue_table(app_context, listed))
    assert impact.title in text and landscape.title in text
    assert "PAC-CMS" in text and "PAC-SRS" in text  # what each is about, as the catalogue reads it
    detail = _texts(deep_dives.detail_panel(app_context, app_context.deep_dives.get(impact.deep_dive_id)))
    assert impact.content["brief_sentence"] in detail
    assert impact.content["findings"][0]["title"] in detail


def test_a_reader_rates_a_deep_dive_from_the_page(app_context):
    d = _written(app_context)
    with use_role("reader"):
        ok, _ = deep_dives.rate(app_context, d.deep_dive_id, 4, "useful for the board paper")
        refused, why = deep_dives.rate(app_context, d.deep_dive_id, 0, "")
    assert ok and not refused and "star" in why
    got = app_context.deep_dives.get(d.deep_dive_id)
    assert (got.rating_count, got.rating_average) == (1, 4.0)
    assert app_context.deep_dives.ratings(d.deep_dive_id)[0].rated_by == app_context.actor


def test_withdraw_is_offered_to_the_author_or_an_admin_only(app_context):
    mine = _written(app_context)
    with use_role("reader"):
        theirs = app_context.deep_dives.keep(
            ask_deep.analyst(app_context).analyse(ask_deep.brief_of(mine)), "bob"
        )
        assert deep_dives.can_withdraw(app_context, mine)
        assert not deep_dives.can_withdraw(app_context, theirs)
        ok, _ = deep_dives.withdraw(app_context, theirs.deep_dive_id)
        assert not ok
    with use_role("admin"):
        assert deep_dives.can_withdraw(app_context, theirs)
        ok, _ = deep_dives.withdraw(app_context, theirs.deep_dive_id)
    assert ok and app_context.deep_dives.get(theirs.deep_dive_id).status == "withdrawn"


def test_running_a_deep_dive_again_keeps_a_new_one_that_names_the_first(app_context):
    first = _written(app_context)
    with use_role("reader"):
        again = deep_dives.run_again(app_context, first.deep_dive_id)
    assert again.deep_dive_id != first.deep_dive_id
    assert again.content["references"]["deep_dives"][0]["deep_dive_id"] == first.deep_dive_id


def test_the_pack_downloads_as_one_zip(app_context):
    d = _written(app_context)
    name, data = deep_dives.pack(app_context, d.deep_dive_id)
    assert name.endswith(".zip")
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert any(n.endswith("/deep-dive.pdf") for n in names)
    assert any(n.endswith(".drawio") for n in names)


# ----------------------------------------------------------- the element page
def test_the_element_page_lists_the_deep_dives_that_cite_it(app_context):
    d = _written(app_context)
    card = deep_dives.deep_dives_card(app_context, "PAC-CMS")
    assert d.title in _texts(card) and f"/deep-dives?open={d.deep_dive_id}" in _hrefs(card)
    assert "No deep dive" in _texts(deep_dives.deep_dives_card(app_context, "ORG-REG"))


def test_the_deep_dives_page_is_routed_and_in_the_navigation():
    from ea.ui.app import NAV_TARGETS, PAGES, parse_path

    assert "deep-dives" in PAGES and "/deep-dives" in NAV_TARGETS
    assert parse_path("/deep-dives")[0] == "deep-dives"
