"""The tool server: the model's read tools served to other agents over the Model Context Protocol (initiative 26, `GAP7`).

An architect's own agent — in an editor, on a laptop, or on the platform — connects here and
asks the model what the Ask page's assistant asks it, through the same tools and with the same
identifiers (principle `P6`). The server acts as the person who connected it: their
organisation, the branch they name, their role, every read scoped by all three as a page's is
(decision 0014). It writes nothing: the tools that draw or propose stay the application's
(principle `P3`).

- **On a laptop** `ea mcp` serves over standard input and output, as the person `--as`,
  `--org` and `--branch` name, which is how an editor starts a local server.
- **On Databricks** `ea mcp --http` serves the protocol's streamable HTTP at `/mcp`, as its
  own app behind the workspace's sign-in: the person is read from the identity the platform
  forwards, their role from their workspace groups, as the web application reads them; the
  organisation and branch from the `X-EA-Org` and `X-EA-Branch` headers, or `?org=` and
  `?branch=`, the default organisation and `main` when neither is given.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
import mcp_types as types
from mcp.server import Server

from ea.agent.tools import ToolBox
from ea.backend.branching import MAIN, use_branch
from ea.backend.organisations import use_org
from ea.models import ROLES
from ea.services.roles import allowed, use_role

if TYPE_CHECKING:
    from ea.ui.context import AppContext

#: The assistant's tools an outside agent is given: every one that reads the model. The two it
#: is not given draw a view on the application's page (`propose_view`) or answer only the app.
SERVED = (
    "list_types",
    "search_elements",
    "get_element",
    "neighbours",
    "trace",
    "impact",
    "allowed_relationships",
    "branch_changes",
    "run_sql",
)
DEEP_DIVES = {
    "name": "deep_dives",
    "description": (
        "The deep dives kept on the model — analyses readers settled with the application's assistant, "
        "rated by the people who read them — best rated first; about one element when `element_id` is given."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "element_id": {"type": "string", "description": "only the deep dives that cite this element"},
            "limit": {"type": "integer", "default": 10},
        },
        "additionalProperties": False,
    },
}
INSTRUCTIONS = (
    "The enterprise architecture repository: its elements, relationships, states and the deep dives "
    "kept on them, read as the person who connected you, in their organisation and branch. Cite the "
    "element identifiers the tools return (for example [PAC-CMS]) for every claim; an identifier no "
    "tool returned is not the repository's. Nothing here writes: a change is proposed in the application."
)
HEADER_ORG = "X-EA-Org"
HEADER_BRANCH = "X-EA-Branch"


@dataclass(frozen=True)
class Caller:
    """Who the server acts as, and where: every call is scoped by all four."""

    username: str
    role: str
    org: str
    branch: str = MAIN


class Refused(ValueError):
    """A caller the server will not act for, said plainly."""


def tool_specs(ctx: AppContext) -> list[dict[str, Any]]:
    """The tools served, described as the assistant's are."""
    with use_org(_default_org(ctx)):
        box = ToolBox(ctx.backend, ctx.registry, ctx.repo, ctx.graph)
        specs = [s for s in box.specs() if s["name"] in SERVED]
    return [*specs, DEEP_DIVES]


def caller_for(ctx: AppContext, username: str, role: str, org: str = "", branch: str = "") -> Caller:
    """A caller checked against the store: an organisation that exists, a branch in it, a role."""
    if role not in ROLES:
        raise Refused(f"unknown role {role!r}")
    org = org or _default_org(ctx)
    if org not in {o.org_id for o in ctx.orgs.list()}:
        raise Refused(f"there is no organisation {org!r}")
    branch = branch or MAIN
    if branch != MAIN:
        with use_org(org):
            try:
                ctx.branches.get(branch)
            except Exception as exc:  # noqa: BLE001 — said, not raised
                raise Refused(f"there is no branch {branch!r} in {org!r}") from exc
    return Caller(username=username or "anonymous", role=role, org=org, branch=branch)


def _default_org(ctx: AppContext) -> str:
    default = ctx.orgs.default()
    if default is None:
        raise Refused("the store holds no organisation yet")
    return default.org_id


def caller_from_request(ctx: AppContext, headers: Any, query: Any = None) -> Caller:
    """The caller of one HTTP request: the person the platform forwarded, where they asked to read."""
    user = ctx.user_from_headers(headers)
    query = query or {}
    org = headers.get(HEADER_ORG) or query.get("org") or ""
    branch = headers.get(HEADER_BRANCH) or query.get("branch") or ""
    return caller_for(ctx, user.username, user.role, org, branch)


def call(ctx: AppContext, caller: Caller, name: str, args: dict[str, Any] | None) -> tuple[str, bool]:
    """One tool call as the caller: (the result as JSON, whether it failed)."""
    with use_org(caller.org), use_branch(caller.branch), use_role(caller.role):
        if not allowed("read"):
            return json.dumps({"error": f"a {caller.role} may not read the model"}), True
        if name == DEEP_DIVES["name"]:
            text = json.dumps(_deep_dives(ctx, **(args or {})), ensure_ascii=False, default=str)
        elif name in SERVED:
            text = ToolBox(ctx.backend, ctx.registry, ctx.repo, ctx.graph).call(name, args or {})
        else:
            return json.dumps(
                {"error": f"no tool {name!r}; the tools are {', '.join((*SERVED, 'deep_dives'))}"}
            ), True
    failed = text.startswith('{"error"')
    return text, failed


def _deep_dives(ctx: AppContext, element_id: str = "", limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(int(limit or 10), 50))
    if element_id:
        kept = ctx.deep_dives.on_element(element_id, limit)
    else:
        kept, _ = ctx.deep_dives.catalogue(limit=limit)
    return {
        "deep_dives": [
            {
                "deep_dive_id": d.deep_dive_id,
                "title": d.title,
                "kind": d.kind,
                "summary": str((d.content or {}).get("summary") or "")[:600],
                "elements": [e.element_id for e in d.elements][:20],
                "rating": d.rating_average,
                "ratings": d.rating_count,
                "created_by": d.created_by,
                "created_at": d.created_at,
            }
            for d in kept
        ]
    }


def build_server(ctx: AppContext, who) -> Server:
    """The protocol server. `who(request_context)` says whom a request acts for, or raises `Refused`."""
    specs = tool_specs(ctx)

    async def list_tools(_rctx, _params) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(name=s["name"], description=s["description"], input_schema=s["input_schema"])
                for s in specs
            ]
        )

    async def call_tool(rctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            caller = who(rctx)
        except Refused as exc:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))], is_error=True
            )
        text, failed = await anyio.to_thread.run_sync(
            functools.partial(call, ctx, caller, params.name, dict(params.arguments or {}))
        )
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=failed)

    return Server(
        "ea-repository",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def serve_stdio(ctx: AppContext, caller: Caller) -> None:
    """Serve one agent over standard input and output, as `caller` — how an editor starts a local server."""
    from mcp.server.stdio import stdio_server

    server = build_server(ctx, lambda _rctx: caller)

    async def main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


def http_app(ctx: AppContext):
    """The streamable HTTP app at `/mcp`, each request acting as the person the platform forwarded."""

    def who(rctx) -> Caller:
        request = getattr(rctx, "request", None)
        if request is None:
            raise Refused("no request to read the caller from")
        return caller_from_request(ctx, request.headers, request.query_params)

    return build_server(ctx, who).streamable_http_app(host="0.0.0.0", stateless_http=True)  # noqa: S104
