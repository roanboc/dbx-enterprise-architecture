"""The deep dive catalogue in the store (initiative 25, decision 0024), on both engines.

A deep dive is kept per organisation with the elements it cites and the ratings people gave it.
These tests hold the store to what the catalogue promises: it reads back what was kept, narrows
by what it is catalogued under, ranks by rating, keeps a withdrawn deep dive's row, keeps one
rating per person, and never lets one organisation read another's — not even through a
reader's own SQL.
"""

from __future__ import annotations

import pytest

from ea.backend.organisations import use_org
from ea.models import DeepDive, DeepDiveElement, DeepDiveRating
from ea.services import OrganisationService


def _dive(title: str, kind: str = "impact", **over) -> DeepDive:
    d = DeepDive(
        title=title,
        kind=kind,
        brief={"question": f"{title}?", "subject": ["PAC-CMS"], "kind": kind, "reach": 2, "purpose": ""},
        content={"summary": f"What {title} found.", "findings": [{"severity": "high", "text": "one"}]},
        domain_ids=["integration"],
        type_ids=["physical_application_component"],
        work_package="",
        created_by="ada",
        elements=[
            DeepDiveElement("PAC-CMS", "subject", 4),
            DeepDiveElement("DE-SRS-COURSE", "drawn", 3),
        ],
    )
    for k, v in over.items():
        setattr(d, k, v)
    return d


def test_a_deep_dive_reads_back_as_it_was_kept(loaded):
    kept = loaded.save_deep_dive(_dive("CMS impact"))
    assert kept.deep_dive_id.startswith("dd-") and kept.status == "kept" and kept.created_at is not None
    got = loaded.get_deep_dive(kept.deep_dive_id)
    assert got is not None
    assert got.title == "CMS impact" and got.kind == "impact"
    assert got.brief["subject"] == ["PAC-CMS"] and got.content["findings"][0]["severity"] == "high"
    assert got.domain_ids == ["integration"] and got.type_ids == ["physical_application_component"]
    assert {(e.element_id, e.role, e.maturity) for e in got.elements} == {
        ("PAC-CMS", "subject", 4),
        ("DE-SRS-COURSE", "drawn", 3),
    }
    assert got.rating_count == 0 and got.rating_average is None
    assert got.branch_id == "" and got.pack_id and got.pack_version


def test_the_catalogue_narrows_by_what_a_deep_dive_is_catalogued_under(loaded):
    a = loaded.save_deep_dive(_dive("CMS impact"))
    b = loaded.save_deep_dive(
        _dive(
            "Curriculum landscape",
            kind="landscape",
            domain_ids=["enterprise", "information"],
            type_ids=["capability"],
            work_package="WP-CMS-UPGRADE",
            elements=[DeepDiveElement("CAP-CURR-DEV", "subject", 2)],
        )
    )

    def ids(**narrow) -> list[str]:
        rows, _ = loaded.list_deep_dives(**narrow)
        return [d.deep_dive_id for d in rows]

    assert set(ids()) == {a.deep_dive_id, b.deep_dive_id}
    assert ids(kind="landscape") == [b.deep_dive_id]
    assert ids(domain_id="information") == [b.deep_dive_id]
    assert ids(type_id="physical_application_component") == [a.deep_dive_id]
    assert ids(work_package="WP-CMS-UPGRADE") == [b.deep_dive_id]
    assert ids(element_id="DE-SRS-COURSE") == [a.deep_dive_id]
    assert ids(text="curriculum") == [b.deep_dive_id]
    rows, total = loaded.list_deep_dives(limit=1)
    assert len(rows) == 1 and total == 2


def test_one_rating_per_person_and_the_best_rated_first(loaded):
    a = loaded.save_deep_dive(_dive("First"))
    b = loaded.save_deep_dive(_dive("Second"))
    loaded.rate_deep_dive(DeepDiveRating(a.deep_dive_id, "ada", 2, "thin"))
    loaded.rate_deep_dive(DeepDiveRating(b.deep_dive_id, "ada", 4, "useful"))
    loaded.rate_deep_dive(DeepDiveRating(b.deep_dive_id, "bob", 5, ""))
    # ada changes her mind: still one rating from her, now a 3
    loaded.rate_deep_dive(DeepDiveRating(a.deep_dive_id, "ada", 3, "better on a second read"))
    got_a, got_b = loaded.get_deep_dive(a.deep_dive_id), loaded.get_deep_dive(b.deep_dive_id)
    assert (got_a.rating_count, got_a.rating_average) == (1, 3.0)
    assert (got_b.rating_count, got_b.rating_average) == (2, 4.5)
    assert [r.comment for r in loaded.deep_dive_ratings(a.deep_dive_id)] == ["better on a second read"]
    rows, _ = loaded.list_deep_dives()
    assert [d.deep_dive_id for d in rows] == [b.deep_dive_id, a.deep_dive_id]
    assert [d.deep_dive_id for d in loaded.list_deep_dives(min_rating=4)[0]] == [b.deep_dive_id]
    with pytest.raises(ValueError):
        loaded.rate_deep_dive(DeepDiveRating(a.deep_dive_id, "ada", 6, ""))


def test_the_deep_dives_on_an_element_are_best_rated_first_and_leave_out_the_withdrawn(loaded):
    a = loaded.save_deep_dive(_dive("First"))
    b = loaded.save_deep_dive(_dive("Second"))
    c = loaded.save_deep_dive(_dive("Third"))
    loaded.rate_deep_dive(DeepDiveRating(b.deep_dive_id, "ada", 5, ""))
    loaded.set_deep_dive_status(c.deep_dive_id, "withdrawn", "ada")
    on = [d.deep_dive_id for d in loaded.deep_dives_for_elements(["PAC-CMS"])]
    assert on[0] == b.deep_dive_id and set(on) == {a.deep_dive_id, b.deep_dive_id}
    assert loaded.deep_dives_for_elements(["NOPE"]) == []
    # withdrawn, not deleted: the row stays, and the catalogue shows it when asked to
    assert loaded.get_deep_dive(c.deep_dive_id).status == "withdrawn"
    assert c.deep_dive_id not in [d.deep_dive_id for d in loaded.list_deep_dives()[0]]
    assert c.deep_dive_id in [d.deep_dive_id for d in loaded.list_deep_dives(include_withdrawn=True)[0]]
    with pytest.raises(ValueError):
        loaded.set_deep_dive_status(a.deep_dive_id, "deleted", "ada")


def test_a_deep_dive_is_the_organisation_s_own(loaded, pack):
    orgs = OrganisationService(loaded)
    kept = loaded.save_deep_dive(_dive("Default's own"))
    orgs.create("Trial", "ada")
    with use_org("trial"):
        assert loaded.get_deep_dive(kept.deep_dive_id) is None
        assert loaded.list_deep_dives() == ([], 0)
        assert loaded.deep_dives_for_elements(["PAC-CMS"]) == []
        # a reader's own SQL answers inside the organisation too
        assert len(loaded.query("SELECT deep_dive_id FROM deep_dive", limit=10)) == 0
        theirs = loaded.save_deep_dive(_dive("Trial's own"))
    assert len(loaded.query("SELECT deep_dive_id FROM deep_dive", limit=10)) == 1
    orgs.delete("trial", "ada")
    with use_org("trial"):
        assert loaded.get_deep_dive(theirs.deep_dive_id) is None
    assert loaded.get_deep_dive(kept.deep_dive_id) is not None
