"""The size the application is assessed for, and the reads that honour it (decision 0019).

`ASM6` is true at the content this repository holds today. These tests are what keeps it
from being re-assumed silently: every service that once read the whole model is held to a
page, the traversal is held to the store, and the declared figures are held to one place.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ea import capacity
from ea.backend.organisations import use_org
from ea.models import Element
from ea.services import GraphService, HealthService, MetamodelService, TargetStateService
from ea.services.graph import TooLargeToHold


def test_the_figures_are_declared_in_one_place():
    """Nothing reads a size from anywhere else; a measurement moves the figure here."""
    assert capacity.ASSESSED_ELEMENTS == 100_000
    assert capacity.ASSESSED_RELATIONSHIPS == 600_000
    assert 0 < capacity.GRAPH_MAX_ELEMENTS < capacity.ASSESSED_ELEMENTS
    assert 0 < capacity.READ_CHUNK <= capacity.GRAPH_MAX_ELEMENTS


def test_headroom_says_how_full_the_model_is():
    h = capacity.headroom(25_000, 150_000)
    assert h["elements_pct"] == 25.0 and h["relationships_pct"] == 25.0
    assert h["graph_held"] is False  # 25,000 is past the graph's budget
    assert capacity.headroom(100, 200)["graph_held"] is True


def test_pages_stops_on_the_first_short_page():
    """A store says 'no more' with a short page; the helper never asks again after one."""
    seen: list[tuple[int, int]] = []

    def fetch(limit, offset):
        seen.append((limit, offset))
        return list(range(limit)) if offset < 2 * limit else ["last"]

    out = list(capacity.pages(fetch, chunk=10))
    assert [len(p) for p in out] == [10, 10, 1]
    assert seen == [(10, 0), (10, 10), (10, 20)]


def test_pages_stops_on_an_empty_first_page():
    assert list(capacity.pages(lambda limit, offset: [], chunk=10)) == []


# ------------------------------------------------------- the traversal is the store's
def test_a_trace_never_builds_the_in_process_graph(loaded, registry, monkeypatch):
    """The walk decision 0016 put in the store used to be wrapped by the graph it replaced."""
    svc = GraphService(loaded, registry)
    centre = loaded.find_elements(limit=1)[0].element_id

    def refuse():
        raise AssertionError("a traversal built the whole in-process graph")

    monkeypatch.setattr(svc, "graph", refuse)
    svc.trace(centre, "out", 3)
    svc.impact(centre, 2)
    svc.neighbours(centre, 1, "both")
    svc.node(centre)
    svc.edges_among([centre])


def test_the_graph_refuses_past_its_budget(loaded, registry, monkeypatch):
    svc = GraphService(loaded, registry)
    assert svc.graph() is not None  # the sample is far below the budget
    monkeypatch.setattr(loaded, "count_elements", lambda *a, **k: capacity.GRAPH_MAX_ELEMENTS + 1)
    svc.invalidate()
    with pytest.raises(TooLargeToHold) as caught:
        svc.graph()
    assert "assessed to hold" in str(caught.value)


def test_the_graph_cache_tells_two_organisations_apart(loaded, registry):
    """A copied organisation has the same counts as its source, so counts alone cannot be the key."""
    from ea.services import OrganisationService

    orgs = OrganisationService(loaded)
    orgs.create("Copy", "tester", copy_from="default", org_id="copy")
    svc = GraphService(loaded, registry)
    here = {n for n in svc.graph().nodes}
    with use_org("copy"):
        there = {n for n in svc.graph().nodes}
        assert there == here  # same content, but read again rather than served from the other org
        loaded.insert_element(
            Element(element_id="copy_only", type_id="information_asset", name="Only in the copy"),
            "tester",
        )
        assert "copy_only" in {n for n in svc.graph().nodes}
    assert "copy_only" not in {n for n in svc.graph().nodes}


# ------------------------------------------------------------ the whole-model reads
def _no_unbounded_read(backend, monkeypatch):
    """Hold every whole-model read to a page, and fail the ones that ask for everything."""
    real_elements, real_rels = backend.find_elements, backend.find_relationships

    def elements(*args, **kwargs):
        limit = kwargs.get("limit", args[3] if len(args) > 3 else 200)
        assert limit <= capacity.READ_CHUNK, f"find_elements(limit={limit}) reads past a page"
        return real_elements(*args, **kwargs)

    def relationships(*args, **kwargs):
        limit = kwargs.get("limit", args[1] if len(args) > 1 else 500)
        assert limit <= capacity.READ_CHUNK, f"find_relationships(limit={limit}) reads past a page"
        return real_rels(*args, **kwargs)

    monkeypatch.setattr(backend, "find_elements", elements)
    monkeypatch.setattr(backend, "find_relationships", relationships)


def test_health_reads_the_model_in_pages(loaded, registry, monkeypatch):
    _no_unbounded_read(loaded, monkeypatch)
    svc = HealthService(loaded, registry)
    assert svc.freshness()["sources"]
    assert svc.completeness()["elements"] > 0


def test_target_state_reads_the_model_in_pages(loaded, registry, monkeypatch):
    _no_unbounded_read(loaded, monkeypatch)
    svc = TargetStateService(loaded, registry)
    assert svc.summary()["elements"] > 0
    svc.elements()
    svc.relationships()


def test_the_compatibility_check_reads_the_model_in_pages(loaded, registry, monkeypatch, pack):
    _no_unbounded_read(loaded, monkeypatch)
    report = MetamodelService(loaded).compatibility("default", pack)
    assert report.elements > 0 and report.ok


def test_the_proposal_index_reads_the_model_in_pages(loaded, registry, monkeypatch):
    """It reads every element on purpose — a shortlist would change what it matches — in pages."""
    from ea.agent.proposal import ProposalService
    from ea.config import Settings
    from ea.services import BranchService, RepositoryService

    _no_unbounded_read(loaded, monkeypatch)
    svc = ProposalService(
        loaded,
        registry,
        RepositoryService(loaded, registry),
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
    )
    index = svc._index()
    assert index["by_id"] and index["names"]


def test_the_target_summary_counts_past_what_a_page_shows(loaded, registry, monkeypatch):
    """The summary counts every row; only the listed rows are capped."""
    svc = TargetStateService(loaded, registry)
    monkeypatch.setattr(TargetStateService, "MAX_ROWS", 2)
    assert len(svc.elements()) == 2
    assert svc.summary()["elements"] > 2


def test_the_import_history_is_read_a_page_at_a_time_however_far_back_it_goes(loaded, monkeypatch):
    """`Older` asks for the *next* page, never for a longer one.

    A history that grew its own read would pass every test on a young store and fail on an old
    one — which is the failure decision 0019 exists to make impossible rather than unlikely.
    """
    from ea.ui.pages.feeds import HISTORY_PAGE, history_list

    asked: list[tuple[int, int]] = []
    real = loaded.runs

    def runs(limit, offset, feed_id=""):
        asked.append((limit, offset))
        return real(limit, offset, feed_id)

    monkeypatch.setattr(loaded, "runs", runs)
    # Only what `history_list` reads off a context: the store. The zone is a setting.
    ctx = SimpleNamespace(backend=loaded)
    for offset in (0, HISTORY_PAGE, 10 * HISTORY_PAGE, 10_000):
        history_list(ctx, offset)
    assert asked and all(limit == HISTORY_PAGE for limit, _ in asked), asked
    assert all(limit <= capacity.READ_CHUNK for limit, _ in asked)
