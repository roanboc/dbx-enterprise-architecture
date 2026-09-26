"""The tool server (initiative 26, `GAP7`): the model's read tools served to an outside agent over MCP, as its person."""

from __future__ import annotations

import json

import anyio
import pytest
from mcp import Client

from ea.backend.branching import use_branch
from ea.tool_server import SERVED, Caller, Refused, build_server, call, caller_for, caller_from_request


def _default(ctx) -> str:
    return ctx.orgs.default().org_id


def _session(ctx, caller: Caller, steps):
    """Run `steps(client)` against the server in-process, acting as `caller`."""
    server = build_server(ctx, lambda _rctx: caller)
    out = {}

    async def main():
        async with Client(server) as client:
            out["value"] = await steps(client)

    anyio.run(main)
    return out["value"]


def test_an_agent_is_given_the_read_tools_and_nothing_that_writes(app_context):
    caller = caller_for(app_context, "ana@example.org", "reader")

    async def steps(client):
        return [t.name for t in (await client.list_tools()).tools]

    names = _session(app_context, caller, steps)
    assert set(names) == {*SERVED, "deep_dives"}
    assert "propose_view" not in names
    assert not any(w in n for n in names for w in ("create", "update", "delete", "apply", "merge"))


def test_an_agent_reads_the_model_with_the_identifiers_the_application_gives(app_context):
    caller = caller_for(app_context, "ana@example.org", "reader")

    async def steps(client):
        found = await client.call_tool("search_elements", {"text": "curriculum management"})
        element = await client.call_tool("get_element", {"element_id": "PAC-CMS"})
        return found, element

    found, element = _session(app_context, caller, steps)
    assert not found.is_error and "PAC-CMS" in found.content[0].text
    assert json.loads(element.content[0].text)["element"]["element_id"] == "PAC-CMS"


def test_a_tool_the_server_does_not_serve_is_refused(app_context):
    caller = caller_for(app_context, "ana@example.org", "reader")
    text, failed = call(app_context, caller, "propose_view", {"title": "x", "element_ids": []})
    assert failed and "no tool" in text


def test_the_agent_reads_the_branch_its_person_named(app_context, loaded, registry):
    from ea.services import BranchService, RepositoryService

    BranchService(loaded, registry).create("Tool server trial", "ana")
    with use_branch("tool-server-trial"):
        e = RepositoryService(loaded, registry).element("PAC-CMS")
        RepositoryService(loaded, registry).update_element("PAC-CMS", "ana", e.version, name="Curriculum Hub")
    on_branch = caller_for(app_context, "ana@example.org", "architect", branch="tool-server-trial")
    on_main = caller_for(app_context, "ana@example.org", "architect")
    text, _ = call(app_context, on_branch, "get_element", {"element_id": "PAC-CMS"})
    assert json.loads(text)["element"]["name"] == "Curriculum Hub"
    text, _ = call(app_context, on_main, "get_element", {"element_id": "PAC-CMS"})
    assert json.loads(text)["element"]["name"] != "Curriculum Hub"


def test_a_caller_names_only_what_exists(app_context):
    with pytest.raises(Refused, match="no organisation"):
        caller_for(app_context, "ana", "reader", org="nowhere")
    with pytest.raises(Refused, match="no branch"):
        caller_for(app_context, "ana", "reader", branch="no-such-branch")
    with pytest.raises(Refused, match="unknown role"):
        caller_for(app_context, "ana", "owner")


def test_an_http_caller_is_the_person_the_platform_forwarded(app_context, monkeypatch):
    """Nobody signed in reads as a Reader; the organisation and branch come from the request."""
    app_context.settings.auth = "databricks"
    monkeypatch.setattr(app_context.identity, "groups", lambda *_a, **_k: [])
    who = caller_from_request(app_context, {"X-Forwarded-Email": "ana@example.org"}, {})
    assert (who.username, who.role, who.org, who.branch) == (
        "ana@example.org",
        "reader",
        _default(app_context),
        "main",
    )
    nobody = caller_from_request(app_context, {}, {})
    assert nobody.role == "reader" and nobody.username == "anonymous"
    with pytest.raises(Refused):
        caller_from_request(app_context, {"X-EA-Org": "nowhere"}, {})


def test_deep_dives_kept_are_served(app_context):
    caller = caller_for(app_context, "ana@example.org", "reader")
    text, failed = call(app_context, caller, "deep_dives", {"element_id": "PAC-CMS"})
    assert not failed and "deep_dives" in json.loads(text)


def test_over_http_each_request_acts_as_its_forwarded_person(app_context, monkeypatch):
    """The platform's half: streamable HTTP at /mcp, the person read from the forwarded identity."""
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    from ea.tool_server import http_app

    app_context.settings.auth = "databricks"
    monkeypatch.setattr(app_context.identity, "groups", lambda *_a, **_k: ["ea-architects"])
    app_context.settings.role_groups = "architect=ea-architects"
    app = http_app(app_context)
    out = {}

    async def main():
        async with app.router.lifespan_context(app):
            http = httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="http://ea.test",
                headers={"X-Forwarded-Email": "ana@example.org", "X-EA-Org": _default(app_context)},
            )
            async with http, Client(streamable_http_client("http://ea.test/mcp", http_client=http)) as client:
                out["tools"] = [t.name for t in (await client.list_tools()).tools]
                out["found"] = await client.call_tool("get_element", {"element_id": "PAC-CMS"})

    anyio.run(main)
    assert "get_element" in out["tools"]
    assert not out["found"].is_error and "PAC-CMS" in out["found"].content[0].text
