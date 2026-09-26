"""Connected systems: the enterprise's systems the assistant may read over the Model Context Protocol (initiative 26).

An admin says where a system answers, which of its tools — each a read — the assistant may
call, what it speaks for and as whom it is read. Everyone else reads the list, so a reader can
see what an answer may have consulted. What a system says is read when an answer needs it and
cited as the system's; nothing here writes to a system, and nothing a system says is written
into the model.
"""

from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, html, no_update
from dash import ctx as dash_ctx

from ea.models import CONNECTED_AUTH, ROLES, ConnectedSystem, Forbidden, ValidationError
from ea.services.roles import LABELS, a_role
from ea.ui import ids
from ea.ui.components import alert, icon, page_title
from ea.ui.context import AppContext, get_context

AUTH_LABELS = {
    "reader": "As the person asking (their own platform identity)",
    "credential": "With the organisation's credential, for the roles named",
    "none": "As nobody (a server open inside the network)",
}


def _csv(text: str | None) -> list[str]:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def system_from_form(
    name: str, url: str, tools: str, speaks_for: list[str] | None, pages: str, page_tool: str,
    auth: str, credential_env: str, roles: list[str] | None,
) -> ConnectedSystem:  # fmt: skip
    """The form as a connected system; the service says what is wrong with it."""
    return ConnectedSystem(
        name=name or "",
        url=url or "",
        tools=_csv(tools),
        speaks_for=list(speaks_for or []),
        link_prefixes=_csv(pages),
        page_tool=(page_tool or "").strip(),
        auth=auth or "reader",
        credential_env=(credential_env or "").strip(),
        roles=list(roles or []),
    )


def system_card(ctx: AppContext, s: ConnectedSystem, can_manage: bool) -> dmc.Paper:
    types = [ctx.registry.types[t].name if t in ctx.registry.types else t for t in s.speaks_for]
    rows = [
        ("Where", s.url),
        (
            "Read",
            AUTH_LABELS.get(s.auth, s.auth)
            + (f" — {', '.join(LABELS.get(r, r) for r in s.roles)}" if s.roles else ""),
        ),
        ("Tools the assistant may call", ", ".join(s.tools)),
        ("Speaks for", ", ".join(types) or "—"),
        ("Pages it reads", f"{', '.join(s.link_prefixes)} with {s.page_tool}" if s.link_prefixes else "—"),
    ]
    head = [
        dmc.Group(
            [
                dmc.Text(s.name, fw=650),
                dmc.Badge(
                    "on" if s.enabled else "off", color="green" if s.enabled else "gray", variant="light"
                ),
            ],
            gap="xs",
        )
    ]
    if can_manage:
        head.append(
            dmc.Button(
                "Disconnect",
                id={"type": ids.SYS_REMOVE, "id": s.system_id},
                size="xs",
                variant="subtle",
                color="red",
                leftSection=icon("tabler:trash", 14),
            )
        )
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(head, justify="space-between"),
                dmc.Table(
                    dmc.TableTbody([dmc.TableTr([dmc.TableTd(k, w=220), dmc.TableTd(v)]) for k, v in rows]),
                    fz="sm",
                ),
            ],
            gap="xs",
        ),
        withBorder=True,
        p="sm",
    )


def system_list(ctx: AppContext) -> Any:
    can_manage = ctx.can("connect_systems")
    held = ctx.connected.list()
    if not held:
        return dmc.Text("No system is connected: the assistant reads the model alone.", c="dimmed", size="sm")
    return dmc.Stack([system_card(ctx, s, can_manage) for s in held], gap="sm")


def _form(ctx: AppContext) -> Any:
    if not ctx.can("connect_systems"):
        return alert(
            f"{a_role(ctx.role_label())} may not connect a system: which of the enterprise's systems the "
            "assistant reads, and as whom, is an admin's decision.",
            "gray",
            dismissible=False,
        )
    types = [{"value": t.id, "label": t.name} for t in ctx.registry.concrete_types() if t.active]
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Title("Connect a system", order=3),
                dmc.SimpleGrid(
                    [
                        dmc.TextInput(id=ids.SYS_NAME, label="Name", placeholder="The CMDB"),
                        dmc.TextInput(
                            id=ids.SYS_URL, label="Where it answers the protocol", placeholder="https://…/mcp"
                        ),
                        dmc.TextInput(
                            id=ids.SYS_TOOLS,
                            label="Tools the assistant may call",
                            description="Comma-separated; each one must only read",
                        ),
                        dmc.MultiSelect(
                            id=ids.SYS_SPEAKS_FOR,
                            label="Element types it masters",
                            data=types,
                            searchable=True,
                        ),
                        dmc.TextInput(
                            id=ids.SYS_PAGES,
                            label="Pages it answers for",
                            description="Address prefixes of the pages elements link to, comma-separated",
                        ),
                        dmc.TextInput(id=ids.SYS_PAGE_TOOL, label="The tool that reads a page"),
                        dmc.Select(
                            id=ids.SYS_AUTH,
                            label="Read",
                            data=[{"value": a, "label": AUTH_LABELS[a]} for a in CONNECTED_AUTH],
                            value="reader",
                        ),
                        dmc.TextInput(
                            id=ids.SYS_CREDENTIAL,
                            label="The credential's environment variable",
                            description="With the organisation's credential only; the platform holds the secret",
                        ),
                        dmc.MultiSelect(
                            id=ids.SYS_ROLES,
                            label="Read with the credential for",
                            data=[{"value": r, "label": LABELS.get(r, r)} for r in ROLES if r != "agent"],
                        ),
                    ],
                    cols={"base": 1, "md": 2},
                ),
                dmc.Group(
                    dmc.Button("Connect", id=ids.SYS_SAVE, leftSection=icon("tabler:link-plus", 16)),
                    justify="flex-end",
                ),
            ]
        ),
        withBorder=True,
        p="md",
    )


def render(ctx: AppContext) -> Any:
    return dmc.Stack(
        [
            page_title(
                "Connected systems",
                "The enterprise's systems the assistant may read over the Model Context Protocol — as the person "
                "asking, cited as the system's, and never written into the model.",
            ),
            html.Div(id=ids.SYS_FEEDBACK),
            html.Div(system_list(ctx), id=ids.SYS_LIST),
            _form(ctx),
        ],
        gap="md",
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.SYS_LIST, "children"),
        Output(ids.SYS_FEEDBACK, "children"),
        Input(ids.SYS_SAVE, "n_clicks"),
        State(ids.SYS_NAME, "value"),
        State(ids.SYS_URL, "value"),
        State(ids.SYS_TOOLS, "value"),
        State(ids.SYS_SPEAKS_FOR, "value"),
        State(ids.SYS_PAGES, "value"),
        State(ids.SYS_PAGE_TOOL, "value"),
        State(ids.SYS_AUTH, "value"),
        State(ids.SYS_CREDENTIAL, "value"),
        State(ids.SYS_ROLES, "value"),
        prevent_initial_call=True,
    )
    def connect(n, name, url, tools, speaks_for, pages, page_tool, auth, credential, roles):
        if not n:
            return no_update, no_update
        ctx = get_context()
        try:
            kept = ctx.connected.save(
                system_from_form(name, url, tools, speaks_for, pages, page_tool, auth, credential, roles),
                ctx.actor,
            )
        except (ValidationError, Forbidden) as exc:
            issues = getattr(exc, "issues", None)
            said = "; ".join(i.message for i in issues) if issues else str(exc)
            return no_update, alert(said, "red")
        return system_list(ctx), alert(
            f"Connected {kept.name}: the assistant may read it from the next answer.", "green"
        )

    @app.callback(
        Output(ids.SYS_LIST, "children", allow_duplicate=True),
        Output(ids.SYS_FEEDBACK, "children", allow_duplicate=True),
        Input({"type": ids.SYS_REMOVE, "id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def disconnect(clicks):
        trigger = dash_ctx.triggered_id
        if not trigger or not any(clicks or []):
            return no_update, no_update
        ctx = get_context()
        held = ctx.connected.get(trigger["id"])
        try:
            ctx.connected.delete(trigger["id"], ctx.actor)
        except Forbidden as exc:
            return no_update, alert(str(exc), "red")
        return system_list(ctx), alert(f"Disconnected {held.name if held else trigger['id']}.", "green")
