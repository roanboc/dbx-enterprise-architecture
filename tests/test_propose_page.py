"""The Propose page's own logic (initiative 24): the conversation beside the draft, what a
question offers, and what the page carries between turns — provable without a browser."""

from __future__ import annotations

import pytest
from tests.test_feeds_page import _texts
from tests.test_questions import CMS, PORTAL, page

from ea.agent.proposal import result_from_payload
from ea.agent.questions import MAX_SHOWN
from ea.ui.pages.propose import (
    WORDS,
    _conversation_panel,
    _el_rows,
    _payload_from_rows,
    _preview,
    _question_options,
    _rel_rows,
    _stored,
)


@pytest.fixture
def ctx(app_context):
    app_context.settings.agent_provider = "stub"
    return app_context


def _read(ctx, text):
    return ctx.proposals.start([{"kind": "text", "name": "page", "text": text}])


def test_words_are_offered_only_when_the_assistant_can_read_them():
    q = {"qid": "business", "options": [{"key": "technical", "label": "None: a purely technical change"}]}
    assert [o["key"] for o in _question_options(q, converses=False)] == ["technical"]
    assert [o["key"] for o in _question_options(q, converses=True)] == ["technical", WORDS]
    # a question that already takes words keeps its own way of saying them
    why = {"qid": "why", "options": [{"key": "words", "label": "Say why in words", "needs": "text"}]}
    assert [o["key"] for o in _question_options(why, converses=True)] == ["words"]


def test_the_conversation_shows_the_first_questions_and_says_what_waits(ctx):
    result, conversation = _read(ctx, page(PORTAL, CMS))
    panel = _conversation_panel(ctx, result, conversation)
    text = _texts(panel)
    assert "What is this change for?" in text and "Which part of the business" in text
    assert "wait until the context is settled" in text
    shown = [q for q in result.questions if not q.get("held")][:MAX_SHOWN]
    assert all(q["text"] in text for q in shown)
    assert "What business or strategy does Curriculum Review Portal serve?" not in text  # held back
    assert "The draft holds 2 elements and 0 relationships." in text  # the first turn


def test_the_page_carries_what_the_conversation_settled_between_turns(ctx):
    result, conversation = _read(ctx, page(PORTAL, CMS))
    result, _ = ctx.proposals.answer(result, "why", text="Review boards approve units faster.")
    result, _ = ctx.proposals.answer(result, "business", "technical")
    result.elements[0].referenced_from, result.elements[0].reference_url = "PAC-CMS", "https://wiki.example/x"
    el_rows, rel_rows = _el_rows(result), _rel_rows(result)
    payload = _payload_from_rows(
        el_rows,
        [r for r in el_rows if r["include"]],
        rel_rows,
        [r for r in rel_rows if r["include"]],
        _stored(result),
        result.work_package,
    )
    again = result_from_payload(payload)
    assert again.reason == "Review boards approve units faster." and again.technical
    assert set(again.answers) == {"why", "business"}
    assert (again.elements[0].referenced_from, again.elements[0].reference_url) == (
        "PAC-CMS",
        "https://wiki.example/x",
    )


def test_the_preview_renders_the_conversation_beside_the_rows(ctx):
    result, conversation = _read(ctx, page(PORTAL, CMS))
    text = _texts(_preview(ctx, result, conversation))
    assert "Conversation" in text and "Elements" in text and "Apply to branch" in text
    assert "Open question: What is this change for?" in text  # in what stops Apply, too


def test_the_reviewer_reads_how_each_row_was_settled():
    from ea.ui.pages.branches import _how_it_was_settled

    assert _how_it_was_settled({}) is None
    shown = _texts(
        _how_it_was_settled(
            {
                "answers": {
                    "business": {
                        "question": "Which part of the business?",
                        "said": "A purely technical change.",
                    }
                }
            }
        )
    )
    assert "How it was settled: 1 answer" in shown and "A purely technical change." in shown
