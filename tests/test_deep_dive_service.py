"""The deep dive catalogue as a service: who may keep, rate and withdraw, and what it is filed under."""

from __future__ import annotations

import pytest

from ea.models import DeepDive, DeepDiveElement, Forbidden
from ea.services import DeepDiveService, use_role


@pytest.fixture
def dives(loaded, registry):
    return DeepDiveService(loaded, registry)


def _dive(subject: list[str], title: str = "A deep dive") -> DeepDive:
    return DeepDive(
        title=title,
        kind="impact",
        brief={"question": title, "subject": subject},
        content={"summary": "found"},
        elements=[DeepDiveElement(i, "subject", 3) for i in subject],
    )


def test_a_deep_dive_is_filed_under_its_subject_s_types_and_domains(dives, registry):
    with use_role("reader"):
        kept = dives.keep(_dive(["PAC-CMS", "DE-SRS-COURSE"]), "ada")
    assert kept.created_by == "ada"
    assert kept.type_ids == ["data_entity", "physical_application_component"]
    expected = sorted({registry.get_type(t).domain for t in kept.type_ids})
    assert kept.domain_ids == expected and "integration" in expected
    assert dives.get(kept.deep_dive_id).domain_ids == expected


def test_the_assistant_may_not_keep_or_rate_a_deep_dive(dives):
    with use_role("reader"):
        kept = dives.keep(_dive(["PAC-CMS"]), "ada")
    with use_role("agent"):
        with pytest.raises(Forbidden):
            dives.keep(_dive(["PAC-CMS"]), "assistant")
        with pytest.raises(Forbidden):
            dives.rate(kept.deep_dive_id, "assistant", 5)


def test_a_rating_is_one_to_five_stars_and_one_per_person(dives):
    with use_role("reader"):
        kept = dives.keep(_dive(["PAC-CMS"]), "ada")
        dives.rate(kept.deep_dive_id, "bob", 4, "clear")
        dives.rate(kept.deep_dive_id, "bob", 2, "on reflection, thin")
        with pytest.raises(ValueError):
            dives.rate(kept.deep_dive_id, "bob", 0)
    got = dives.get(kept.deep_dive_id)
    assert (got.rating_count, got.rating_average) == (1, 2.0)


def test_only_the_author_or_an_admin_withdraws_a_deep_dive(dives):
    with use_role("reader"):
        mine = dives.keep(_dive(["PAC-CMS"], "Mine"), "ada")
        theirs = dives.keep(_dive(["PAC-CMS"], "Theirs"), "bob")
        with pytest.raises(Forbidden):
            dives.withdraw(theirs.deep_dive_id, "ada")
        dives.withdraw(mine.deep_dive_id, "ada")
    with use_role("admin"):
        dives.withdraw(theirs.deep_dive_id, "carol")
    assert dives.get(mine.deep_dive_id).status == "withdrawn"
    assert dives.get(theirs.deep_dive_id).status == "withdrawn"


def test_the_earlier_deep_dives_on_the_same_elements_come_best_rated_first(dives):
    with use_role("reader"):
        low = dives.keep(_dive(["PAC-CMS"], "Low"), "ada")
        high = dives.keep(_dive(["PAC-CMS", "DE-SRS-COURSE"], "High"), "ada")
        other = dives.keep(_dive(["CAP-CURR-DEV"], "Elsewhere"), "ada")
        dives.rate(low.deep_dive_id, "bob", 1)
        dives.rate(high.deep_dive_id, "bob", 5)
    earlier = [d.title for d in dives.earlier(["DE-SRS-COURSE", "PAC-CMS"])]
    assert earlier == ["High", "Low"]
    assert other.deep_dive_id not in [d.deep_dive_id for d in dives.earlier(["PAC-CMS"])]
    assert [d.title for d in dives.on_element("CAP-CURR-DEV")] == ["Elsewhere"]


def test_a_reader_clears_their_rating_and_the_assistant_may_not(dives):
    with use_role("reader"):
        kept = dives.keep(_dive(["PAC-CMS"]), "ada")
        dives.rate(kept.deep_dive_id, "bob", 3, "")
        assert dives.clear_rating(kept.deep_dive_id, "bob") is True
    assert dives.get(kept.deep_dive_id).rating_count == 0
    with use_role("agent"), pytest.raises(Forbidden):
        dives.clear_rating(kept.deep_dive_id, "assistant")
