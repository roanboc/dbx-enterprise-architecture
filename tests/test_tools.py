"""The read tools an agent is given: what they add for a reader placing a proposed change."""

from __future__ import annotations

import json

from ea.agent.tools import ToolBox
from ea.backend.branching import use_branch
from ea.services import BranchService, RepositoryService


def test_allowed_relationships_names_what_may_join_two_types(loaded, registry, repo, graph):
    tb = ToolBox(loaded, registry, repo, graph)
    out = tb.tool_allowed_relationships("Physical Application Component", "data_entity")
    assert out["source_type"] == "physical_application_component" and out["target_type"] == "data_entity"
    assert "processes" in {r["name"] for r in out["relationships"]}
    assert "error" in tb.tool_allowed_relationships("Spaceship", "data_entity")


def test_branch_changes_says_what_the_branch_already_holds(loaded, registry, repo, graph):
    tb = ToolBox(loaded, registry, repo, graph)
    assert tb.tool_branch_changes()["changes"] == []  # on main there is nothing to compare
    BranchService(loaded, registry).create("draft", "ana")
    with use_branch("draft"):
        made = RepositoryService(loaded, registry).create_element(
            "data_entity", "Unit proposal", "ana", description_md="A proposed unit."
        )
        text = tb.call("branch_changes", {})
    rows = json.loads(text)["changes"]
    assert [(r["change"], r["element_id"], r["name"]) for r in rows] == [
        ("added", made.element_id, "Unit proposal")
    ]
    assert made.element_id in tb.seen_ids  # a branch's own identifiers count as grounded


def test_every_element_a_tool_returns_carries_its_states(loaded, registry, repo, graph):
    tb = ToolBox(loaded, registry, repo, graph)
    hit = tb.tool_search_elements("Curriculum Management")["matches"][0]
    assert {"current_state", "target_state", "target_work_package"} <= set(hit)


def test_propose_view_asks_the_store_not_the_whole_graph(loaded, registry, repo, graph, monkeypatch):
    tb = ToolBox(loaded, registry, repo, graph)
    monkeypatch.setattr(graph, "graph", lambda: (_ for _ in ()).throw(AssertionError("built the graph")))
    out = tb.tool_propose_view("x", ["PAC-CMS", "NOPE-1"])
    assert out["accepted"] == ["PAC-CMS"] and out["unknown"] == ["NOPE-1"]
