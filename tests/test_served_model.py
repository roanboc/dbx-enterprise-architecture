"""The assistant's model on a Databricks Model Serving endpoint (decision 0023), proven against
a stand-in: a local server that speaks the platform's Anthropic-compatible Messages API at
`/serving-endpoints/anthropic`. No workspace is needed; the run on one waits with PLAT2."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ea.agent.agent import Agent, AnthropicProvider
from ea.agent.llm import ModelUnavailable, choice, model_client, served_client
from ea.agent.proposal import AnthropicProposalProvider, ProposalService
from ea.agent.tools import ToolBox
from ea.config import Settings
from ea.services import BranchService, TargetStateService

ENDPOINT = "databricks-claude-stand-in"


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

    def reply(self, content: list[dict], stop: str = "end_turn") -> None:
        self.script.append(
            (
                200,
                {
                    "id": f"msg_{len(self.script)}",
                    "type": "message",
                    "role": "assistant",
                    "model": ENDPOINT,
                    "content": content,
                    "stop_reason": stop,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )
        )

    def tool(self, name: str, args: dict, n: int = 1) -> dict:
        return {"type": "tool_use", "id": f"tu_{name}_{n}_{len(self.script)}", "name": name, "input": args}

    def client(self):
        return served_client(ENDPOINT, self.host, lambda: {"Authorization": "Bearer platform-token"})


@pytest.fixture
def endpoint():
    s = StandIn()
    yield s
    s.server.shutdown()


def test_ask_reaches_the_endpoint_signed_by_the_platform(endpoint, loaded, registry, repo, graph):
    endpoint.reply([endpoint.tool("get_element", {"element_id": "PAC-CMS"})], stop="tool_use")
    endpoint.reply([{"type": "text", "text": "The Curriculum Management System [PAC-CMS] realises it."}])
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), AnthropicProvider(endpoint.client()))
    res = agent.ask("What does PAC-CMS realise?")
    assert res.error == "" and res.provider == "databricks" and res.model == ENDPOINT
    assert [c.name for c in res.tool_calls] == ["get_element"] and not res.ungrounded_ids
    first = endpoint.requests[0]
    assert first["path"] == "/serving-endpoints/anthropic/v1/messages"
    assert first["headers"]["Authorization"] == "Bearer platform-token"
    assert "x-api-key" not in {k.lower() for k in first["headers"]}  # the placeholder key never leaves
    # the model named is the endpoint, and none of the direct API's newer options are sent
    assert first["body"]["model"] == ENDPOINT
    assert "thinking" not in first["body"] and "output_config" not in first["body"]
    # the tool's answer went back to the endpoint in the second request
    assert endpoint.requests[1]["body"]["messages"][-1]["content"][0]["type"] == "tool_result"


def test_a_refusal_by_the_endpoint_names_it_and_what_to_check(endpoint, loaded, registry, repo, graph):
    endpoint.script.append((403, {"error": {"type": "permission_error", "message": "no CAN_QUERY"}}))
    agent = Agent(ToolBox(loaded, registry, repo, graph), Settings(), AnthropicProvider(endpoint.client()))
    res = agent.ask("anything")
    assert ENDPOINT in res.error and "CAN_QUERY" in res.error


def _proposals(loaded, registry, repo, graph, mc) -> ProposalService:
    svc = ProposalService(
        loaded,
        registry,
        repo,
        BranchService(loaded, registry),
        TargetStateService(loaded, registry),
        Settings(agent_provider="stub"),
        toolbox=ToolBox(loaded, registry, repo, graph),
    )
    svc.provider = AnthropicProposalProvider(mc)
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
    svc = _proposals(loaded, registry, repo, graph, endpoint.client())
    assert svc.converses
    # the first read: the model submits a draft and asks what it cannot settle
    endpoint.reply(
        [
            endpoint.tool(
                "submit_proposal",
                {
                    "title": "Review portal",
                    "work_package": "WP-CMS-UPGRADE",
                    "elements": [PORTAL],
                    "relationships": [],
                },
            ),
            endpoint.tool(
                "ask_architect",
                {"question": "Which review boards will use it?", "about": "Curriculum Review Portal"},
            ),
        ],
        stop="tool_use",
    )
    endpoint.reply([{"type": "text", "text": "Read."}])
    r, conversation = svc.start([{"kind": "text", "name": "notes", "text": "A review portal for units."}])
    assert r.provider == "databricks" and r.elements[0].name == "Curriculum Review Portal"
    mine = next(q for q in r.questions if q["kind"] == "assistant")
    assert mine["qid"] == "ask:1" and mine["about"] == "element:1" and mine["free"]
    assert not mine["blocking"]  # the assistant's own questions inform; the rules' block
    # the rules still ask top-down: why comes first, whatever the model asked
    assert r.questions[0]["qid"] == "why"
    # the architect answers in words; the model reads them and redrafts
    endpoint.reply(
        [
            endpoint.tool(
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
        ],
        stop="tool_use",
    )
    endpoint.reply([{"type": "text", "text": "The portal now realises Curriculum Development."}])
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
    sent = endpoint.requests[-2]["body"]["messages"][0]["content"]
    assert "The draft change set" in sent and "The faculty boards" in sent
    assert {t["name"] for t in endpoint.requests[-2]["body"]["tools"]} >= {"submit_proposal", "ask_architect"}


def test_without_the_sdk_auto_falls_back_and_a_named_endpoint_says_why(monkeypatch):
    monkeypatch.setitem(sys.modules, "databricks.sdk.core", None)  # as on a laptop without the extra
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert model_client(Settings(agent_provider="auto", agent_endpoint=ENDPOINT)) is None
    with pytest.raises(ModelUnavailable, match="Databricks SDK"):
        model_client(Settings(agent_provider="databricks", agent_endpoint=ENDPOINT))
    with pytest.raises(ModelUnavailable, match="EA_AGENT_ENDPOINT"):
        model_client(Settings(agent_provider="databricks"))


def test_auto_prefers_the_served_endpoint(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert choice(Settings(agent_endpoint=ENDPOINT)) == "databricks"
    assert choice(Settings()) == "anthropic"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert choice(Settings()) == "stub"
    assert choice(Settings(agent_provider="stub", agent_endpoint=ENDPOINT)) == "stub"
