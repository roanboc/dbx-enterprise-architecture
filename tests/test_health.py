"""Search, bulk edit and the model's health figures."""

from __future__ import annotations

from datetime import datetime, timedelta

from ea.backend.branching import use_branch
from ea.models import Element
from ea.services import BranchService, HealthService, RepositoryService, SearchService


def test_search_needs_every_word_and_ranks_names_first(loaded, registry):
    svc = SearchService(loaded, registry)
    hits = svc.search("curriculum")
    assert hits[0].element.name.lower().startswith("curriculum") and hits[0].rank == 0
    assert svc.count("curriculum") == len(svc.search("curriculum", limit=1000))
    # a word from a description alone finds the element and says where it matched
    hits = svc.search("paper-like approval forms")
    assert [h.element.element_id for h in hits] == ["PTC-FORMS"]
    assert hits[0].matched_in == "description" and "forms" in hits[0].snippet.lower()
    # every word must match: an unrelated word empties the result
    assert svc.search("paper-like approval nonsenseword") == []
    # attribute values count too
    hits = svc.search("Reference data model v3")
    assert hits and all(h.matched_in.startswith("attribute:") or h.matched_in for h in hits)
    rows = SearchService.rows(svc.search("paper-like"), registry)
    assert rows[0]["snippet"] and rows[0]["matched_in"] == "description"
    assert svc.search("")[0].rank == 3  # no query: the plain listing


def test_bulk_update_applies_one_change_to_many(loaded, registry):
    repo = RepositoryService(loaded, registry)
    BranchService(loaded, registry).create("bulk", "ada")
    with use_branch("bulk"):
        out = repo.bulk_update(
            ["PAC-CMS", "PAC-SRS", "NOPE", "DE-SRS-COURSE"],
            "ada",
            {"target_state": "keep", "target_work_package": "WP-CMS-UPGRADE", "note": None},
            ("owner", "Curriculum office"),
        )
        assert out["updated"] == ["PAC-CMS", "PAC-SRS", "DE-SRS-COURSE"]
        assert out["refused"][0]["element_id"] == "NOPE"
        e = loaded.get_element("DE-SRS-COURSE")
        assert (
            e.target_state == "keep"
            and e.target_work_package == "WP-CMS-UPGRADE"
            and e.attrs["owner"] == "Curriculum office"
        )
    assert loaded.get_element("DE-SRS-COURSE").target_state == "undecided"  # main untouched
    with use_branch("bulk"):
        out = repo.bulk_update(["PAC-CMS"], "ada", {"target_state": "delete"})
        assert out["updated"] == [] and "target_state" in out["refused"][0]["reason"]


def test_freshness_counts_per_source(loaded, registry):
    now = datetime(2027, 6, 1)
    svc = HealthService(loaded, registry, now=now)
    fresh = svc.freshness()
    sample = next(r for r in fresh["sources"] if r["source"] == "sample")
    assert sample["elements"] == 47 and sample["relationships"] == 99
    assert sample["stale_30"] == 47 and sample["stale_180"] == 47  # loaded well before 'now'
    assert sample["never_updated"] == 47 and len(sample["never_updated_ids"]) == 47
    assert svc.ids_for("stale", source="sample", days=90) == set(sample["stale_90_ids"])
    # an edit today is fresh
    svc_now = HealthService(loaded, registry)
    repo = RepositoryService(loaded, registry)
    cms = repo.element("PAC-CMS")
    repo.update_element("PAC-CMS", "ada", cms.version, target_note="touched")
    sample = next(r for r in svc_now.freshness()["sources"] if r["source"] == "sample")
    assert sample["stale_30"] == 0 and sample["never_updated"] == 46
    weeks = svc_now.activity(4)
    assert len(weeks) >= 4 and weeks[-1]["total"] >= 1


def test_completeness_per_type(loaded, registry):
    svc = HealthService(loaded, registry)
    comp = svc.completeness()
    by_type = {r["type_id"]: r for r in comp["types"]}
    pac = by_type["physical_application_component"]
    assert pac["elements"] == 5 and pac["description_pct"] == 100
    assert pac["links_missing"] == 3 and "PAC-CMS" not in pac["links_ids"]
    assert pac["relationships_pct"] == 100
    assert pac["target_missing"] == 2 and set(pac["target_ids"]) == {"PAC-EDW", "PAC-LMS"}
    assert comp["missing"]["target"] == sum(r["target_missing"] for r in comp["types"])
    assert svc.ids_for("links", "physical_application_component") == set(pac["links_ids"])
    loaded.insert_element(Element("CAP-EMPTY", "capability", "Empty capability"), "ada")
    comp = svc.completeness()
    cap = next(r for r in comp["types"] if r["type_id"] == "capability")
    assert "CAP-EMPTY" in cap["description_ids"] and "CAP-EMPTY" in cap["relationships_ids"]
    assert any(r["name"] for r in svc.relationship_coverage())


def _days_ago(n: int) -> datetime:
    return datetime.now() - timedelta(days=n)


def test_health_measures_the_moment_it_is_asked(loaded, registry):
    """Built once for the life of the process, the service must not freeze the clock at start-up."""
    import time

    svc = HealthService(loaded, registry)
    first = svc.now
    time.sleep(0.01)
    assert svc.now > first
    pinned = HealthService(loaded, registry, now=datetime(2026, 9, 8, 12, 0))
    assert pinned.now == datetime(2026, 9, 8, 12, 0)


def test_twelve_weeks_means_twelve_bars(loaded, registry):
    """Whatever weekday 'now' falls on, the activity chart draws exactly the weeks it is headed with."""
    for day in range(7, 14):  # a Monday through the following Sunday
        svc = HealthService(loaded, registry, now=datetime(2026, 9, day, 9, 30))
        weeks = [r["week"] for r in svc.activity(12)]
        assert len(weeks) == 12 and len(set(weeks)) == 12, (day, weeks)
        assert (
            weeks[-1]
            == f"{datetime(2026, 9, day).isocalendar()[0]}-W{datetime(2026, 9, day).isocalendar()[1]:02d}"
        )
