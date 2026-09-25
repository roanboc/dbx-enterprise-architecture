"""A proposal settled in conversation (initiative 24): the questions the rules ask without a
model, top-down, and a picked choice applied to the draft; drafts kept between sittings."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ea.agent.proposal import AnswerError, ProposalService, result_from_payload
from ea.agent.questions import MAX_SHOWN, shown
from ea.backend.branching import use_branch
from ea.config import Settings
from ea.models import ElementFilter, Proposal
from ea.services import BranchService, RepositoryService, TargetStateService

HEAD = """# Proposal: Review portal

| | |
| --- | --- |
| **Work package** | WP-CMS-UPGRADE |

## Elements

| Type | Name | Existing id | Description | Current state | Target state |
| ---- | ---- | ----------- | ----------- | ------------- | ------------ |
"""
PORTAL = (
    "| Physical Application Component | Curriculum Review Portal | | A portal in which review boards "
    "read and approve unit proposals before publication. | proposed | new |\n"
)
CMS = "| Physical Application Component | Curriculum Management System | PAC-CMS | | live | change |\n"
RELS = """
## Relationships

| Source | Relationship | Target | Note |
| ------ | ------------ | ------ | ---- |
"""


def page(*rows: str, rels: str = "") -> str:
    return HEAD + "".join(rows) + RELS + rels


@pytest.fixture
def svc(loaded, registry):
    return ProposalService(
        loaded,
        registry,
        RepositoryService(loaded, registry),
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
    )


def read(svc, text: str, branch: str | None = None):
    return svc.analyse([{"kind": "text", "name": "page", "text": text}], branch)


def asked(result, kind: str) -> dict:
    return next(q for q in result.questions if q["kind"] == kind)


def kinds(questions) -> list[str]:
    return [q["kind"] for q in questions]


def test_the_context_is_asked_first_and_the_technical_rows_wait(svc):
    r = read(svc, page(PORTAL, CMS))
    # why and which business come first; the portal's own question is held until they are settled
    assert kinds(shown(r.questions))[:2] == ["why", "business"]
    trace = asked(r, "trace")
    assert trace["held"] and trace["blocking"] and trace["about"] == "element:1"
    assert "trace" not in kinds(shown(r.questions))
    # the choices come from the model: the capability the changing system already realises
    why = asked(r, "why")
    assert why["options"][0]["key"] == "link:CAP-CURR-DEV"
    assert {o["key"] for o in why["options"]} >= {"new", "words"}
    business = asked(r, "business")
    assert any(o["key"] == "link:IA-COURSE-CAT" for o in business["options"])
    assert any(o["key"] == "technical" for o in business["options"])
    # an open context question stops Apply
    assert any(p.startswith("Open question: What is this change for?") for p in r.pushback)
    assert any(p.startswith("Open question: Which part of the business") for p in r.pushback)


def test_a_picked_choice_settles_the_context_and_releases_the_rows(svc):
    r = read(svc, page(PORTAL, CMS))
    r, said = svc.answer(r, "why", "link:CAP-CURR-DEV", actor="ana")
    assert "Curriculum Development" in said
    cap = next(e for e in r.elements if e.element_id == "CAP-CURR-DEV")
    assert cap.action == "link" and cap.existing_id == "CAP-CURR-DEV"  # added as it is, states and all
    r, _ = svc.answer(r, "business", "technical", actor="ana")
    assert r.technical and r.answers["business"]["said"] == "A purely technical change."
    assert "why" not in kinds(r.questions) and "business" not in kinds(r.questions)
    trace = asked(r, "trace")
    assert not trace["held"]
    # the capability now on the page is offered, with the relationships the metamodel allows
    option = next(o for o in trace["options"] if o["key"] == "serve:CAP-CURR-DEV")
    assert option["choices"] == [
        {"key": "out:physical_application_component__realises__capability", "label": "realises"}
    ]
    r, said = svc.answer(r, trace["qid"], "serve:CAP-CURR-DEV", actor="ana")  # one choice: taken
    assert said == "Curriculum Review Portal realises CAP-CURR-DEV."
    assert "trace" not in kinds(r.questions)
    assert r.pushback == [], r.pushback


def test_the_reason_in_words_is_understood_without_a_model(svc):
    r = read(svc, page(PORTAL, CMS))
    r, said = svc.answer(r, "why", text="Review boards approve units in days, not weeks.")
    assert r.reason == "Review boards approve units in days, not weeks." and said.startswith("Why:")
    assert "why" not in kinds(r.questions)
    # a question that needs a choice refuses words without a model, and says so
    with pytest.raises(AnswerError, match="needs the assistant's model"):
        svc.answer(r, "business", text="the curriculum office")


def test_an_answer_that_does_not_fit_is_refused(svc):
    r = read(svc, page(PORTAL, CMS))
    with pytest.raises(AnswerError, match="not one of the choices"):
        svc.answer(r, "why", "link:NOPE")
    with pytest.raises(AnswerError, match="needed"):
        svc.answer(r, "why", "new", choice="goal")  # a new goal needs its name
    with pytest.raises(AnswerError, match="no longer open"):
        svc.answer(r, "boundary:nothing", "keep", "x")


def test_a_new_context_element_is_added_with_its_type(svc):
    r = read(svc, page(PORTAL, CMS))
    r, _ = svc.answer(r, "why", "new", "Faster unit approval", choice="goal")
    goal = next(e for e in r.elements if e.name == "Faster unit approval")
    assert (goal.type_id, goal.action, goal.target_state) == ("goal", "new", "new")
    # a new element still owes its description: asked, and in the pushback as a row issue
    assert asked(r, "description")["about"] == f"element:{goal.row}"
    r, _ = svc.answer(r, f"description:{'faster unit approval'}", text="Units are approved within ten days.")
    assert goal.description == "Units are approved within ten days."


def test_an_element_that_traces_to_nothing_can_be_left_out(svc):
    r = read(svc, page(PORTAL, CMS))
    r, _ = svc.answer(r, "why", text="Faster approval.")
    r, _ = svc.answer(r, "business", "technical")
    r, said = svc.answer(r, "trace:curriculum review portal", "drop")
    portal = next(e for e in r.elements if e.name == "Curriculum Review Portal")
    assert not portal.include and "left out" in said


def test_a_part_that_only_its_own_system_touches_is_linked_from_the_system(svc, loaded, registry):
    """P9: the comment store relates only to the portal — nothing outside the portal relates to
    it — so it is asked about, and linked from the portal rather than modelled."""
    comments = (
        "| Data Entity | Review comment | | A reviewer's comment on a unit proposal, kept with the proposal. "
        "| proposed | new |\n"
    )
    rels = (
        "| Curriculum Review Portal | processes | Review comment | |\n"
        "| Curriculum Review Portal | realises | Curriculum Development | |\n"
    )
    cap = "| Capability | Curriculum Development | CAP-CURR-DEV | | | |\n"
    r = read(svc, page(cap, PORTAL, comments, rels=rels))
    r, _ = svc.answer(r, "business", "technical")
    q = asked(r, "boundary")
    assert q["qid"] == "boundary:review comment" and q["blocking"]
    assert "relates only to Curriculum Review Portal" in q["text"]
    assert [o["key"] for o in q["options"]] == ["reference:new:curriculum review portal", "keep", "drop"]
    assert any(p.startswith("Open question: Review comment relates only") for p in r.pushback)
    with pytest.raises(AnswerError, match="web address"):
        svc.answer(r, q["qid"], "reference:new:curriculum review portal", "the wiki")
    r, said = svc.answer(
        r, q["qid"], "reference:new:curriculum review portal", "https://wiki.example.edu/crp/comments"
    )
    assert said.startswith("Review comment is linked from Curriculum Review Portal")
    row = next(e for e in r.elements if e.name == "Review comment")
    assert not row.include and row.referenced_from == "new:curriculum review portal"
    assert not next(x for x in r.relationships if x.target == "Review comment").include
    assert r.pushback == [], r.pushback
    # the edited rows carry it, and at Apply the page lands on the portal as a link
    BranchService(loaded, registry).create("crp", "ana")
    out = svc.apply(result_from_payload(r.to_dict()), "crp", "ana")
    assert out["referenced"][0]["url"] == "https://wiki.example.edu/crp/comments"
    with use_branch("crp"):
        portal = loaded.get_element(out["referenced"][0]["system"])
        assert portal.name == "Curriculum Review Portal"
        assert [(x.label, x.url) for x in portal.links] == [
            ("Review comment", "https://wiki.example.edu/crp/comments")
        ]
        assert not loaded.find_elements(ElementFilter(text="Review comment"))


def test_a_type_the_metamodel_places_below_the_line_is_asked_about(svc, registry, monkeypatch):
    # the registry is the run's: the change is undone when the test ends
    monkeypatch.setitem(
        registry.types, "data_entity", replace(registry.types["data_entity"], level="solution")
    )
    record = (
        "| Data Entity | Review record | | The record of a review, read by the curriculum system too. "
        "| proposed | new |\n"
    )
    rels = (
        "| Curriculum Review Portal | processes | Review record | |\n"
        "| Curriculum Management System | processes | Review record | |\n"
        "| Curriculum Review Portal | realises | CAP-CURR-DEV | |\n"
    )
    r = read(svc, page(PORTAL, CMS, record, rels=rels))
    q = next(q for q in r.questions if q["kind"] == "boundary")
    assert "a type the metamodel places below the enterprise level" in q["text"]
    r, said = svc.answer(r, q["qid"], "keep", "the curriculum system reads it as well", actor="ana")
    assert r.answers[q["qid"]]["holds"] and said.startswith("Kept:")
    assert not any(x["kind"] == "boundary" for x in r.questions)  # a kept answer is not asked again


def test_a_near_match_is_asked_and_new_is_an_answer(svc):
    mgr = (
        "| Position | Manager Curriculum System | | The manager of the curriculum systems. | live | keep |\n"
    )
    r = read(svc, page(mgr))
    q = asked(r, "match")
    assert q["options"][0]["key"] == "link:POS-CURR-MGR" and q["options"][-1]["key"] == "new"
    r, _ = svc.answer(r, q["qid"], "new")
    row = next(e for e in r.elements if e.name == "Manager Curriculum System")
    assert row.confirmed_new and not any("similar element" in i for i in row.issues)
    again = read(svc, page(mgr))
    again, said = svc.answer(again, q["qid"], "link:POS-CURR-MGR")
    row = next(e for e in again.elements if e.name == "Manager Curriculum System")
    assert row.action == "link" and row.element_id == "POS-CURR-MGR"


def test_an_unknown_type_is_asked_with_the_closest_types_first(svc):
    row = "| Data Entiti | Review record | | The record of a review of a unit proposal. | proposed | new |\n"
    r = read(svc, page(row))
    q = asked(r, "type")
    assert q["options"][0]["key"] == "type:data_entity"
    r, _ = svc.answer(r, q["qid"], "type:data_entity")
    assert next(e for e in r.elements if e.name == "Review record").type_id == "data_entity"


def test_a_relationship_the_metamodel_refuses_is_asked_with_what_it_allows(svc):
    cap = "| Capability | Curriculum Development | CAP-CURR-DEV | | | |\n"
    r = read(
        svc, page(cap, PORTAL, rels="| Curriculum Development | realises | Curriculum Review Portal | |\n")
    )
    q = asked(r, "relationship")
    assert "reverse:physical_application_component__realises__capability" in {o["key"] for o in q["options"]}
    r, said = svc.answer(r, q["qid"], "reverse:physical_application_component__realises__capability")
    assert said == "Curriculum Review Portal realises Curriculum Development."
    assert r.relationships[0].rel_type_id == "physical_application_component__realises__capability"


def test_what_a_retirement_leaves_behind_is_asked_and_can_be_retired_too(svc):
    cms = "| Physical Application Component | Curriculum Management System | PAC-CMS | | live | decommission |\n"
    cap = "| Capability | Curriculum Development | CAP-CURR-DEV | | | |\n"
    r = read(svc, page(cap, cms))
    r, _ = svc.answer(r, "business", "technical")
    left = [q for q in r.questions if q["kind"] == "dangling"]
    assert left and not left[0]["blocking"]
    before = len(r.relationships)
    r, _ = svc.answer(r, left[0]["qid"], "retire")
    assert len(r.relationships) == before + 1 and r.relationships[-1].target_state == "decommission"
    assert left[0]["qid"] not in {q["qid"] for q in r.questions}


def test_no_more_than_a_few_questions_are_shown_at_once(svc):
    rows = "".join(
        f"| Data Entiti | Record {n} | | The record number {n} of the review. | proposed | new |\n"
        for n in range(8)
    )
    r = read(svc, page(rows))
    assert len(r.questions) > MAX_SHOWN and len(shown(r.questions)) == MAX_SHOWN


def test_a_turn_without_a_model_applies_choices_and_says_what_it_cannot_read(svc):
    r, conversation = svc.start([{"kind": "text", "name": "review-portal.md", "text": page(PORTAL, CMS)}])
    assert [t["role"] for t in conversation] == ["architect", "assistant"]
    assert conversation[1]["questions"][:2] == ["why", "business"]
    r, conversation = svc.turn(r, conversation, [{"qid": "why", "key": "link:CAP-CURR-DEV"}], actor="ana")
    assert conversation[-2]["kind"] == "answer" and conversation[-2]["qid"] == "why"
    assert "why" not in conversation[-1]["questions"]
    r, conversation = svc.turn(r, conversation, message="It is for the review boards.", actor="ana")
    assert conversation[-1]["text"].startswith("No model is configured")


def test_a_draft_is_kept_per_architect_and_applied_with_its_conversation(svc, loaded, registry):
    r, conversation = svc.start([{"kind": "text", "name": "page", "text": page(PORTAL, CMS)}])
    kept = svc.save_draft(r, conversation, "ana")
    assert kept.status == "draft" and kept.branch_id == ""
    assert [d.proposal_id for d in svc.drafts("ana")] == [kept.proposal_id]
    assert svc.drafts("ben") == []
    with pytest.raises(PermissionError):
        svc.save_draft(r, conversation, "ben", proposal_id=kept.proposal_id)
    with pytest.raises(PermissionError):
        svc.discard_draft(kept.proposal_id, "ben")
    # picked up in a later sitting, settled, and applied: the same record, now applied
    held = svc.draft(kept.proposal_id)
    r = svc.resolve(result_from_payload(held.result))
    r, conversation = svc.turn(
        r, held.conversation, [{"qid": "why", "key": "link:CAP-CURR-DEV"}], actor="ana"
    )
    r, conversation = svc.turn(r, conversation, [{"qid": "business", "key": "technical"}], actor="ana")
    q = asked(r, "trace")
    r, conversation = svc.turn(r, conversation, [{"qid": q["qid"], "key": "serve:CAP-CURR-DEV"}], actor="ana")
    svc.save_draft(r, conversation, "ana", proposal_id=kept.proposal_id)
    BranchService(loaded, registry).create("review-portal", "ana")
    out = svc.apply(r, "review-portal", "ana", draft_id=kept.proposal_id)
    assert out["proposal_id"] == kept.proposal_id
    applied = loaded.get_proposal(kept.proposal_id)
    assert applied.status == "applied" and applied.branch_id == "review-portal"
    assert [t["kind"] for t in applied.conversation].count("answer") == 3
    assert applied.result["answers"]["business"]["said"] == "A purely technical change."
    assert svc.drafts("ana") == []


def test_a_draft_is_discarded_by_its_architect(svc):
    r, conversation = svc.start([{"kind": "text", "name": "page", "text": page(PORTAL, CMS)}])
    kept = svc.save_draft(r, conversation, "ana")
    svc.discard_draft(kept.proposal_id, "ana")
    assert svc.draft(kept.proposal_id) is None


def test_the_store_keeps_a_proposal_s_conversation(backend):
    p = backend.save_proposal(
        Proposal(
            proposal_id="",
            branch_id="",
            title="Draft",
            status="draft",
            created_by="ana",
            conversation=[{"role": "architect", "kind": "message", "text": "hello"}],
        )
    )
    again = backend.get_proposal(p.proposal_id)
    assert again.conversation == [{"role": "architect", "kind": "message", "text": "hello"}]
    assert again.updated_at is not None and again.status == "draft"
    p.title = "Draft, renamed"
    backend.save_proposal(p)  # saved again: one row, updated in place
    assert [x.title for x in backend.list_proposals(status="draft", created_by="ana")] == ["Draft, renamed"]
    assert backend.list_proposals(status="applied") == []
    backend.delete_proposal(p.proposal_id)
    assert backend.get_proposal(p.proposal_id) is None


def test_the_store_keeps_where_a_type_sits_against_the_line(backend, pack):
    """A type's level survives the store on both engines; a pack that says nothing is at the
    enterprise level throughout."""
    solution = replace(pack, version="p9-trial", status="draft")
    solution.element_types = [
        replace(t, level="solution") if t.id == "data_entity" else t for t in pack.element_types
    ]
    backend.save_pack(solution)
    held = backend.load_pack(pack.id, "p9-trial")
    assert {t.id: t.level for t in held.element_types}["data_entity"] == "solution"
    assert {t.level for t in held.element_types if t.id != "data_entity"} == {"enterprise"}
    assert {t.level for t in backend.load_pack(pack.id, pack.version).element_types} == {"enterprise"}
