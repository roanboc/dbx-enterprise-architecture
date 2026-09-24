"""The Ask agent holds one conversation per reader, never one per organisation.

The agent keeps what a follow-up question needs — the messages so far, the identifiers
its tools returned, the views it asked for. It used to be built once per organisation,
so every reader of an organisation added to one conversation: a question was answered
in the context of somebody else's, a Reset cleared everybody's, and an identifier one
reader's tools had returned counted as grounded in another reader's answer.
"""

from __future__ import annotations

import pytest
from flask import Flask, session

from ea.config import Settings
from ea.ui.context import CONVERSATIONS_KEPT, AppContext


@pytest.fixture
def ctx(loaded):
    settings = Settings.from_env()
    settings.agent_provider = "stub"
    return AppContext(settings, loaded)


@pytest.fixture
def web():
    app = Flask(__name__)
    app.secret_key = "test"
    return app


def _agent_as(web, ctx, persona: str, conversation: str | None = None):
    with web.test_request_context():
        session["persona"] = persona
        if conversation:
            session["conversation"] = conversation
        return ctx.agent, session.get("conversation")


def test_two_readers_hold_two_conversations(web, ctx):
    ada, _ = _agent_as(web, ctx, "admin")
    arjun, _ = _agent_as(web, ctx, "architect")
    assert ada is not arjun
    assert ada.history is not arjun.history and ada.toolbox is not arjun.toolbox
    ada.history.append({"role": "user", "content": "What does DE-SRS-COURSE feed?"})
    assert arjun.history == []
    arjun.reset()
    assert ada.history, "a Reset clears only the conversation of the reader who pressed it"


def test_one_reader_keeps_their_conversation_from_request_to_request(web, ctx):
    first, conversation = _agent_as(web, ctx, "architect")
    again, _ = _agent_as(web, ctx, "architect", conversation)
    assert conversation and again is first


def test_two_sessions_of_one_reader_are_two_conversations(web, ctx):
    one, _ = _agent_as(web, ctx, "architect")
    two, _ = _agent_as(web, ctx, "architect")
    assert one is not two


def test_the_conversations_kept_are_bounded(web, ctx):
    first, conversation = _agent_as(web, ctx, "reader")
    for _ in range(CONVERSATIONS_KEPT):
        _agent_as(web, ctx, "reader")
    again, _ = _agent_as(web, ctx, "reader", conversation)
    assert again is not first and again.history == []


def test_outside_a_request_there_is_one_conversation(ctx):
    assert ctx.agent is ctx.agent
