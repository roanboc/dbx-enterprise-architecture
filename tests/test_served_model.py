"""The assistant's model on a Databricks Model Serving endpoint (decision 0023), proven against
a stand-in: a local server that speaks the chat completions API every model the platform serves
speaks, at `/serving-endpoints/<endpoint>/invocations`. No workspace is needed; the run on one
waits with PLAT2. The direct way for development is proven by what it sends, not by a call."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from ea.agent import llm
from ea.agent.agent import Agent, HostedProvider
from ea.agent.llm import (
    ModelUnavailable,
    chat_model,
    choice,
    provider_messages,
    reply_from_provider,
    served_model,
)
from ea.agent.proposal import HostedProposalProvider, ProposalService
from ea.agent.tools import ToolBox
from ea.config import Settings
from ea.services import BranchService, TargetStateService

ENDPOINT = "assistant-stand-in"
PATH = f"/serving-endpoints/{ENDPOINT}/invocations"


class StandIn:
    """A serving endpoint that answers from a script and remembers what it was sent."""

    def __init__(self):
        self.script: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 — the server's own name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stand_in.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, payload = stand_in.script.pop(0) if stand_in.script else (500, {"error": "empty"})
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):  # quiet
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.host = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def reply(self, text: str | None = None, calls: list[dict] | None = None) -> None:
        message: dict = {"role": "assistant", "content": text}
        if calls:
            message["tool_calls"] = calls
        self.script.append(
            (
                200,
                {
                    "id": f"chatcmpl-{len(self.script)}",
                    "object": "chat.completion",
                    "model": "whatever-the-workspace-serves",
                    "choices": [
                        {"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
        )

    def call(self, name: str, args: dict) -> dict:
        n = sum(
            len(b.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []) for _, b in self.script
        )
        return {
            "id": f"call_{name}_{n}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }

    def model(self):
        return served_model(ENDPOINT, self.host, lambda: {"Authorization": "Bearer platform-token"})


@pytest.fixture
def endpoint():
    s = StandIn()
    yield s
    s.server.shutdown()


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF", 0.0)


def test_ask_reaches_the_endpoint_signed_by_the_platform(endpoint, loaded, registry, repo, graph):
    endpoint.reply(calls=[endpoint.call("get_element", {"element_id": "PAC-CMS"})])
    endpoint.reply("The Curriculum Management System [PAC-CMS] realises it.")
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), HostedProvider(endpoint.model()))
    res = agent.ask("What does PAC-CMS realise?")
    assert res.error == "" and res.provider == "databricks"
    assert (
        res.model == "whatever-the-workspace-serves"
    )  # the workspace chose; the app named only the endpoint
    assert [c.name for c in res.tool_calls] == ["get_element"] and not res.ungrounded_ids
    first = endpoint.requests[0]
    assert first["path"] == PATH
    assert first["headers"]["Authorization"] == "Bearer platform-token"
    # the chat completions shape: the system prompt as the first message, tools as functions,
    # nothing that names a model or a vendor's own options
    body = first["body"]
    assert body["messages"][0]["role"] == "system" and body["messages"][-1] == {
        "role": "user",
        "content": "What does PAC-CMS realise?",
    }
    assert all(
        t["type"] == "function" and t["function"]["parameters"]["type"] == "object" for t in body["tools"]
    )
    assert "model" not in body and "thinking" not in body and body["max_tokens"] == 8192
    # the tool's answer went back as a tool message, after the call it answers
    again = endpoint.requests[1]["body"]["messages"]
    assert again[-2]["tool_calls"][0]["function"]["name"] == "get_element"
    assert again[-1]["role"] == "tool" and again[-1]["tool_call_id"] == again[-2]["tool_calls"][0]["id"]
    assert '"PAC-CMS"' in again[-1]["content"]


def test_a_refusal_by_the_endpoint_names_it_and_what_to_check(endpoint, loaded, registry, repo, graph):
    endpoint.script.append((403, {"error_code": "PERMISSION_DENIED", "message": "no CAN_QUERY"}))
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), HostedProvider(endpoint.model()))
    res = agent.ask("anything")
    assert ENDPOINT in res.error and "CAN_QUERY" in res.error
    assert len(endpoint.requests) == 1  # a refusal is not retried


def test_a_busy_endpoint_is_asked_again(endpoint, loaded, registry, repo, graph):
    endpoint.script.append((503, {"message": "the endpoint is scaling up"}))
    endpoint.reply("Nothing depends on it.")
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), HostedProvider(endpoint.model()))
    res = agent.ask("What depends on PAC-CMS?")
    assert res.error == "" and res.answer == "Nothing depends on it." and len(endpoint.requests) == 2


def test_arguments_that_are_not_json_are_sent_back_to_be_fixed(endpoint, loaded, registry, repo, graph):
    endpoint.reply(
        calls=[
            {"id": "call_1", "type": "function", "function": {"name": "get_element", "arguments": "{oops"}}
        ]
    )
    endpoint.reply("Sorry — PAC-CMS is the curriculum system.")
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), HostedProvider(endpoint.model()))
    res = agent.ask("What is PAC-CMS?")
    assert res.error == "" and "not a JSON object" in endpoint.requests[1]["body"]["messages"][-1]["content"]


def _proposals(loaded, registry, repo, graph, model) -> ProposalService:
    svc = ProposalService(
        loaded,
        registry,
        repo,
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
        toolbox=ToolBox(loaded, registry, repo, graph),
    )
    svc.provider = HostedProposalProvider(model)
    return svc


PORTAL = {
    "type": "Physical Application Component",
    "name": "Curriculum Review Portal",
    "description": "A portal in which review boards read and approve unit proposals.",
    "current_state": "proposed",
    "target_state": "new",
}


def test_a_proposal_is_read_asked_about_and_redrafted_in_conversation(
    endpoint, loaded, registry, repo, graph
):
    svc = _proposals(loaded, registry, repo, graph, endpoint.model())
    assert svc.converses
    # the first read: the model submits a draft and asks what it cannot settle
    endpoint.reply(
        calls=[
            endpoint.call(
                "submit_proposal",
                {
                    "title": "Review portal",
                    "work_package": "WP-CMS-UPGRADE",
                    "elements": [PORTAL],
                    "relationships": [],
                },
            ),
            endpoint.call(
                "ask_architect",
                {"question": "Which review boards will use it?", "about": "Curriculum Review Portal"},
            ),
        ]
    )
    endpoint.reply("Read.")
    r, conversation = svc.start([{"kind": "text", "name": "notes", "text": "A review portal for units."}])
    assert r.provider == "databricks" and r.elements[0].name == "Curriculum Review Portal"
    mine = next(q for q in r.questions if q["kind"] == "assistant")
    assert mine["qid"] == "ask:1" and mine["about"] == "element:1" and mine["free"]
    assert not mine["blocking"]  # the assistant's own questions inform; the rules' block
    # the rules still ask top-down: why comes first, whatever the model asked
    assert r.questions[0]["qid"] == "why"
    # both calls were answered, each by its own tool message
    answered = endpoint.requests[1]["body"]["messages"]
    assert [m["role"] for m in answered[-2:]] == ["tool", "tool"]
    # the architect answers in words; the model reads them and redrafts
    endpoint.reply(
        calls=[
            endpoint.call(
                "submit_proposal",
                {
                    "title": "Review portal",
                    "work_package": "WP-CMS-UPGRADE",
                    "elements": [
                        {
                            "type": "Capability",
                            "name": "Curriculum Development",
                            "existing_id": "CAP-CURR-DEV",
                        },
                        PORTAL,
                    ],
                    "relationships": [
                        {
                            "source": "Curriculum Review Portal",
                            "relationship": "realises",
                            "target": "Curriculum Development",
                        }
                    ],
                },
            )
        ]
    )
    endpoint.reply("The portal now realises Curriculum Development.")
    r, conversation = svc.turn(
        r,
        conversation,
        [{"qid": "ask:1", "text": "The faculty boards"}],
        message="It serves curriculum development.",
        actor="ana",
    )
    assert conversation[-1]["text"] == "The portal now realises Curriculum Development."
    assert any(e.element_id == "CAP-CURR-DEV" for e in r.elements)
    assert not any(q["kind"] in ("why", "trace") for q in r.questions)
    assert "ask:1" in r.answers and not any(q["qid"] == "ask:1" for q in r.questions)
    # what the model was handed: the draft, what is open, and the words to interpret
    sent = endpoint.requests[-2]["body"]["messages"][1]["content"]
    assert "The draft change set" in sent and "The faculty boards" in sent
    offered = {t["function"]["name"] for t in endpoint.requests[-2]["body"]["tools"]}
    assert offered >= {"submit_proposal", "ask_architect"}


def test_the_direct_way_is_handed_the_same_conversation_in_its_own_shape():
    """Development without a workspace: the neutral conversation translated, tool answers to one
    call grouped in one turn, and a turn the direct API wrote passed back as it wrote it."""
    kept = [SimpleNamespace(type="thinking", thinking="…"), SimpleNamespace(type="tool_use")]
    conversation = [
        {"role": "user", "content": "What does PAC-CMS realise?"},
        {
            "role": "assistant",
            "content": "Looking.",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_element", "arguments": '{"element_id": "PAC-CMS"}'},
                },
                {"id": "c2", "type": "function", "function": {"name": "impact", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "one"},
        {"role": "tool", "tool_call_id": "c2", "content": "two"},
        {"role": "assistant", "content": None, "_raw": kept},
        {"role": "tool", "tool_call_id": "c3", "content": "three"},
    ]
    out = provider_messages(conversation)
    assert [m["role"] for m in out] == ["user", "assistant", "user", "assistant", "user"]
    assert out[1]["content"][1] == {
        "type": "tool_use",
        "id": "c1",
        "name": "get_element",
        "input": {"element_id": "PAC-CMS"},
    }
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["c1", "c2"]
    assert out[3]["content"] is kept  # thinking and all, as the API needs it back


def test_the_direct_way_s_answer_reads_as_a_neutral_reply():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="…"),
            SimpleNamespace(type="text", text="Checking."),
            SimpleNamespace(type="tool_use", id="tu1", name="get_element", input={"element_id": "PAC-CMS"}),
        ],
        stop_reason="tool_use",
        model="the-direct-model",
    )
    reply = reply_from_provider(response, "configured")
    assert (reply.text, reply.stop, reply.model) == ("Checking.", "tools", "the-direct-model")
    assert reply.tool_uses[0].arguments == {"element_id": "PAC-CMS"}
    assert reply.message["_raw"] is response.content
    assert json.loads(reply.message["tool_calls"][0]["function"]["arguments"]) == {"element_id": "PAC-CMS"}


def test_without_the_sdk_auto_falls_back_and_a_named_endpoint_says_why(monkeypatch):
    monkeypatch.setitem(sys.modules, "databricks.sdk.core", None)  # as on a laptop without the extra
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert chat_model(Settings(agent_provider="auto", agent_endpoint=ENDPOINT)) is None
    with pytest.raises(ModelUnavailable, match="Databricks SDK"):
        chat_model(Settings(agent_provider="databricks", agent_endpoint=ENDPOINT))
    with pytest.raises(ModelUnavailable, match="EA_AGENT_ENDPOINT"):
        chat_model(Settings(agent_provider="databricks"))


def test_auto_prefers_the_served_endpoint(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert choice(Settings(agent_endpoint=ENDPOINT)) == "databricks"
    assert choice(Settings()) == "anthropic"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert choice(Settings()) == "stub"
    assert choice(Settings(agent_provider="stub", agent_endpoint=ENDPOINT)) == "stub"


def test_the_longest_reply_is_the_workspace_s_setting(monkeypatch):
    monkeypatch.setenv("EA_AGENT_MAX_TOKENS", "4096")
    assert Settings.from_env().agent_max_tokens == 4096
