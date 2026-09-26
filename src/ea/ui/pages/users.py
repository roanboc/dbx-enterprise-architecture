"""Users and roles: which Databricks workspace groups hold which role here (initiative 28, decision 0028).

An admin picks a group from the workspace's groups as its name is typed, gives it Reviewer,
Architect or Admin with a line of why, reads every grant — the deployment's own first, read-only
— removes one that no longer holds, checks which role a person gets and why, and reads the recent
changes. Everyone else reads their own role, the group it comes from and whom to ask. Groups
only: who is in a group, and who may open the application at all, stay in Databricks.

Every callback asks the service again, which requires `grant_roles`: a Reader who calls one
directly is refused, and is shown nothing of the grants or the workspace's groups.
"""

from __future__ import annotations

import json
from typing import Any

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, html, no_update
from dash import ctx as dash_ctx

from ea.importer.feeds import in_zone
from ea.models import GRANTABLE_ROLES, Forbidden, GroupRef, NotFoundError
from ea.services.access import GrantRow, change_in_words, in_words
from ea.services.identity import MIN_SEARCH
from ea.services.roles import DESCRIPTIONS, LABELS, a_role, require
from ea.ui import ids
from ea.ui.components import alert, icon, keep_selected_option, page_title
from ea.ui.context import AppContext, get_context
from ea.ui.layout import ROLE_COLOURS

REFUSED = (Forbidden, ValueError, NotFoundError)


def _sentence(said: object) -> str:
    """A refusal as the page shows it: a sentence, whatever case the service began it in."""
    text = str(said).strip()
    return f"{text[:1].upper()}{text[1:]}" + ("" if text.endswith((".", "!", "?")) else ".")


def _section(title: str) -> dmc.Title:
    return dmc.Title(title, order=2, size="h4", mt="md")


# ----------------------------------------------------------------------------- the group picked
def option_value(ref: GroupRef, checked: bool = True) -> str:
    """A group as the picker's value: its identifier, its name, and whether the directory gave it."""
    return json.dumps([ref.id if checked else ref.name, ref.name, bool(checked)])


def parse_option(value: str | None) -> tuple[str, str, bool] | None:
    """(identifier, name, checked) from a picked value; None for anything else."""
    try:
        group_id, name, checked = json.loads(value or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(group_id, str) or not isinstance(name, str) or not group_id:
        return None
    return group_id, name, bool(checked)


def _directory_note(ctx: AppContext) -> str:
    """What the picker says under itself when the directory answers: that locally it is a sample."""
    if getattr(ctx.access.directory, "sample", False):
        return "Locally these are sample groups; on the platform they are the workspace's."
    return ""


def group_options(
    ctx: AppContext, text: str | None, value: str | None, data: list[dict[str, str]] | None
) -> tuple[list[dict[str, str]], str, str]:
    """The picker's options for what was typed, what it says when there are none, and the line
    under it — why the directory cannot be searched when it cannot, in which case the exact name
    typed is offered, marked not checked. A Reader gets nothing: the service refuses them the
    directory, and the page asks it before anything else."""
    if not ctx.can("grant_roles"):
        return [], "", ""
    text = (text or "").strip()
    if len(text) < MIN_SEARCH:
        return (
            keep_selected_option([], value, data),
            "Type at least two letters of the group's name",
            _directory_note(ctx),
        )
    try:
        found, problem = ctx.access.search(text)
    except Forbidden:
        return [], "", ""
    if problem:
        typed = GroupRef(name=text)
        offered = [{"value": option_value(typed, checked=False), "label": f"{text} — not checked"}]
        note = (
            f"{problem[0].upper()}{problem[1:]}. The exact name typed can be granted instead: it is "
            "marked not checked and matched by that name until the group is granted again from the list."
        )
        return keep_selected_option(offered, value, data), "", note
    offered = [{"value": option_value(g), "label": g.name} for g in found]
    said = "" if offered else f"No group in {ctx.access.directory.label} holds '{text}'."
    return keep_selected_option(offered, value, data), said, _directory_note(ctx)


# ---------------------------------------------------------------------------------- the grants
def _mark(label: str, color: str) -> dmc.Badge:
    return dmc.Badge(label, color=color, variant="light", size="sm")


def _role_badge(role: str) -> dmc.Badge:
    return dmc.Badge(LABELS.get(role, role), color=ROLE_COLOURS.get(role, "gray"), variant="light")


def grant_row(ctx: AppContext, r: GrantRow, can_remove: bool) -> dmc.Paper:
    marks = []
    if r.source == "deployment":
        marks.append(_mark("set by the deployment", "gray"))
        detail = "Named in the deployment's EA_ROLE_GROUPS: it is changed with the deployment, never here."
    else:
        if not r.checked:
            marks.append(_mark("not checked", "yellow"))
        if r.missing:
            marks.append(_mark("no longer in the workspace", "red"))
        if r.now_called:
            marks.append(_mark(f"now called {r.now_called}", "blue"))
        if r.ignored:
            marks.append(_mark("not a role a grant gives: ignored", "gray"))
        detail = " · ".join(
            p
            for p in (
                f"Why: {r.note}" if r.note else "",
                f"granted by {r.granted_by or 'an admin'} on {in_zone(r.granted_at, ctx.settings.timezone)}",
                "matched by its exact name until it is granted again from the workspace's list"
                if not r.checked
                else "",
            )
            if p
        )
    right: list[Any] = [_role_badge(r.role)]
    if r.source == "grant":
        right.append(
            dmc.Button(
                "Remove",
                id={"type": ids.USR_REMOVE, "id": r.group_id},
                size="xs",
                variant="subtle",
                color="red",
                leftSection=icon("tabler:trash", 14),
                disabled=not can_remove,
                **{"aria-label": f"Remove the {LABELS.get(r.role, r.role)} grant of {r.group}"},
            )
        )
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(
                    [
                        dmc.Group([dmc.Text(r.group, fw=600), *marks], gap=6, wrap="wrap"),
                        dmc.Group(right, gap=6),
                    ],
                    justify="space-between",
                    wrap="wrap",
                    gap="xs",
                ),
                dmc.Text(detail, size="xs", c="dimmed"),
            ],
            gap=4,
        ),
        withBorder=True,
        p="xs",
    )


def grants_list(ctx: AppContext) -> Any:
    """Every grant, the deployment's first; to an admin only."""
    try:
        rows, problem = ctx.access.grants()
    except Forbidden as exc:
        return alert(_sentence(exc), "gray", dismissible=False)
    can_remove = not ctx.access.local_persona_refusal()
    out: list[Any] = [grant_row(ctx, r, can_remove) for r in rows]
    if not any(r.source == "grant" for r in rows):
        out.append(
            dmc.Text(
                "No group has been granted a role here yet"
                + ("; every person is a Reader until one is." if not rows else "."),
                c="dimmed",
                size="sm",
            )
        )
    if problem:
        out.append(
            dmc.Text(f"Whether these groups still exist is not known: {problem}.", c="dimmed", size="xs")
        )
    return dmc.Stack(out, gap="xs")


def history_list(ctx: AppContext) -> Any:
    """The latest changes to the grants, newest first; to an admin only."""
    try:
        changes = ctx.access.history()
    except Forbidden as exc:
        return alert(_sentence(exc), "gray", dismissible=False)
    if not changes:
        return dmc.Text("No role has been granted or removed here yet.", c="dimmed", size="sm")
    return dmc.Stack(
        [
            dmc.Text(
                [
                    dmc.Text(in_zone(c.when, ctx.settings.timezone), span=True, c="dimmed"),
                    " · ",
                    change_in_words(c),
                ],
                size="sm",
            )
            for c in changes
        ],
        gap=4,
    )


# --------------------------------------------------------------------------- what the page does
def do_grant(ctx: AppContext, value: str | None, role: str | None, note: str | None) -> tuple[bool, Any]:
    """Grant the picked group the chosen role; whether it was granted, and what to say."""
    picked = parse_option(value)
    try:
        require("grant_roles", what="grant a role")  # before anything else is said; the service asks again
        if picked is None:
            return False, alert("Pick the workspace group the role is granted to.", "yellow")
        if not role:
            return False, alert("Pick the role to grant: Reviewer, Architect or Admin.", "yellow")
        group_id, name, checked = picked
        kept = ctx.access.grant(group_id, name, role, note or "", checked, ctx.actor, acting=ctx.group_refs())
    except REFUSED as exc:
        return False, alert(_sentence(exc), "red")
    how = "" if kept.checked else " It is not checked: it is matched by that exact name."
    return True, alert(
        f"{LABELS.get(kept.role, kept.role)} granted to {kept.group_name}: its people hold it within a minute.{how}",
        "green",
    )


def do_remove(ctx: AppContext, group_id: str) -> tuple[bool, Any]:
    """Remove a group's grant; whether it was removed, and what to say."""
    try:
        gone = ctx.access.revoke(group_id, ctx.actor, acting=ctx.group_refs())
    except REFUSED as exc:
        return False, alert(_sentence(exc), "red")
    return True, alert(
        f"Removed the {LABELS.get(gone.role, gone.role)} grant of {gone.group_name}: its people keep what "
        "their other groups give, within a minute.",
        "green",
    )


def do_check(ctx: AppContext, email: str | None) -> Any:
    """The role a person gets, and which of their groups gives it."""
    try:
        said = ctx.access.check_person(email or "")
    except REFUSED as exc:
        return alert(_sentence(exc), "red")
    if not said.found:
        return alert(f"{said.problem[0].upper()}{said.problem[1:]}.", "yellow")
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Text(in_words(said.role, said.reasons), fw=600),
                dmc.Text(
                    f"{said.email} is in {', '.join(g.name for g in said.groups) or 'no group'}. "
                    "A change to who is in a group is felt within five minutes.",
                    size="xs",
                    c="dimmed",
                ),
            ],
            gap=2,
        ),
        withBorder=True,
        p="xs",
    )


# ------------------------------------------------------------------------------------ the views
def _whom_to_ask(ctx: AppContext) -> str:
    contact = (ctx.settings.admin_contact or "").strip()
    return (
        f"For another role, ask {contact}."
        if contact
        else "For another role, ask an admin of this application: they grant roles to the workspace's groups here."
    )


def mine(ctx: AppContext) -> Any:
    """A person's own role, where it comes from, what it lets them do and whom to ask."""
    role = ctx.role()
    refs = ctx.group_refs()
    granted, reasons = ctx.access.my_role(refs)
    lines: list[Any] = [
        dmc.Group(
            [dmc.Text("Your role", fw=600), _role_badge(role)],
            gap="xs",
        ),
        dmc.Text(DESCRIPTIONS.get(role, ""), size="sm"),
    ]
    if ctx.settings.auth == "databricks":
        top = [r for r in reasons if r.role == role]
        lines.append(
            dmc.Text(
                "It comes from the group"
                + ("s " if len(top) > 1 else " ")
                + " and ".join(f"{r.group} ({r.how()})" for r in top)
                + "."
                if top
                else "None of your groups holds a role, so you read, search, ask and download like everyone.",
                size="sm",
            )
        )
    else:
        names = ", ".join(g.name for g in refs) or "none"
        lines.append(
            dmc.Text(
                "Locally, the role is the debug persona chosen in the header. On the platform, the groups "
                f"here ({names}) would give: {in_words(granted, reasons, 'your')}.",
                size="sm",
            )
        )
    lines.append(
        dmc.Text(
            _whom_to_ask(ctx) + " Joining a group is done in the workspace itself.",
            size="sm",
            c="dimmed",
        )
    )
    return dmc.Paper(dmc.Stack(lines, gap="xs"), withBorder=True, p="md", id=ids.USR_MINE)


def _grant_form(ctx: AppContext, refusal: str) -> dmc.Paper:
    return dmc.Paper(
        dmc.Stack(
            [
                _section("Grant a role"),
                dmc.Select(
                    id=ids.USR_GROUP,
                    label="Workspace group",
                    description="Type two letters of its name and pick it: it is kept by the workspace's "
                    "identifier, so a renamed group keeps its role",
                    placeholder="Search the workspace's groups…",
                    searchable=True,
                    clearable=True,
                    data=[],
                    nothingFoundMessage="Type at least two letters of the group's name",
                    comboboxProps={"withinPortal": True},
                ),
                dmc.Text(
                    _directory_note(ctx),
                    id=ids.USR_SEARCH_NOTE,
                    c="dimmed",
                    size="xs",
                ),
                dmc.RadioGroup(
                    dmc.Stack(
                        [
                            dmc.Radio(label=LABELS[r], value=r, description=DESCRIPTIONS[r])
                            for r in GRANTABLE_ROLES
                        ],
                        gap="xs",
                    ),
                    id=ids.USR_ROLE,
                    label="Role",
                    size="sm",
                ),
                dmc.TextInput(
                    id=ids.USR_NOTE,
                    label="Why",
                    description="A line the next admin reads: what the group does that needs the role",
                    placeholder="They draft the architecture of new solutions",
                ),
                dmc.Group(
                    dmc.Button(
                        "Grant",
                        id=ids.USR_GRANT,
                        leftSection=icon("tabler:check", 16),
                        disabled=bool(refusal),
                    ),
                    justify="flex-end",
                ),
            ],
            gap="sm",
        ),
        withBorder=True,
        p="md",
    )


def render(ctx: AppContext) -> Any:
    title = page_title(
        "Users and roles",
        "Which Databricks workspace groups hold which role here. A person's role is the highest any of "
        "their groups gives; a person in none is a Reader.",
    )
    if not ctx.can("grant_roles"):
        return dmc.Stack(
            [
                title,
                mine(ctx),
                alert(
                    f"{a_role(ctx.role_label())} may not see or change who holds which role: that is an admin's "
                    "decision.",
                    "gray",
                    dismissible=False,
                ),
            ],
            gap="md",
        )
    refusal = ctx.access.local_persona_refusal()
    return dmc.Stack(
        [
            title,
            alert(f"{refusal[0].upper()}{refusal[1:]}.", "yellow", dismissible=False) if refusal else None,
            html.Div(id=ids.USR_FEEDBACK),
            _grant_form(ctx, refusal),
            _section("Grants"),
            html.Div(grants_list(ctx), id=ids.USR_GRANTS),
            _section("Check a person"),
            dmc.Group(
                [
                    dmc.TextInput(
                        id=ids.USR_CHECK_EMAIL,
                        label="E-mail",
                        placeholder="someone@example.org",
                        style={"flex": "1 1 16rem"},
                    ),
                    dmc.Button(
                        "Check", id=ids.USR_CHECK, variant="light", leftSection=icon("tabler:search", 16)
                    ),
                ],
                align="flex-end",
                wrap="wrap",
            ),
            html.Div(id=ids.USR_CHECK_RESULT),
            _section("Recent changes"),
            html.Div(history_list(ctx), id=ids.USR_HISTORY),
            dmc.Text(
                [
                    "Who reviews which element type is decided per organisation, on the ",
                    # underlined: inside a sentence a link must not be told apart by its colour alone
                    dmc.Anchor("Metamodel page's Reviewers tab", href="/metamodel", underline="always"),
                    ". Creating a group, changing who is in it, and who may open the application at all "
                    "are done in Databricks.",
                ],
                size="sm",
                c="dimmed",
                mt="md",
            ),
        ],
        gap="sm",
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.USR_GROUP, "data"),
        Output(ids.USR_GROUP, "nothingFoundMessage"),
        Output(ids.USR_SEARCH_NOTE, "children"),
        Input(ids.USR_GROUP, "searchValue"),
        State(ids.USR_GROUP, "value"),
        State(ids.USR_GROUP, "data"),
        prevent_initial_call=True,
    )
    def search(text, value, data):
        options, message, note = group_options(get_context(), text, value, data)
        return options, message or "Type at least two letters of the group's name", note

    @app.callback(
        Output(ids.USR_GRANTS, "children"),
        Output(ids.USR_HISTORY, "children"),
        Output(ids.USR_FEEDBACK, "children"),
        Output(ids.USR_GROUP, "value"),
        Output(ids.USR_NOTE, "value"),
        Input(ids.USR_GRANT, "n_clicks"),
        State(ids.USR_GROUP, "value"),
        State(ids.USR_ROLE, "value"),
        State(ids.USR_NOTE, "value"),
        prevent_initial_call=True,
    )
    def grant(n, value, role, note):
        if not n:
            return (no_update,) * 5
        ctx = get_context()
        ok, said = do_grant(ctx, value, role, note)
        if not ok:
            return no_update, no_update, said, no_update, no_update
        return grants_list(ctx), history_list(ctx), said, None, ""

    @app.callback(
        Output(ids.USR_GRANTS, "children", allow_duplicate=True),
        Output(ids.USR_HISTORY, "children", allow_duplicate=True),
        Output(ids.USR_FEEDBACK, "children", allow_duplicate=True),
        Input({"type": ids.USR_REMOVE, "id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def remove(clicks):
        trigger = dash_ctx.triggered_id
        if not trigger or not any(clicks or []):
            return no_update, no_update, no_update
        ctx = get_context()
        ok, said = do_remove(ctx, trigger["id"])
        if not ok:
            return no_update, no_update, said
        return grants_list(ctx), history_list(ctx), said

    @app.callback(
        Output(ids.USR_CHECK_RESULT, "children"),
        Input(ids.USR_CHECK, "n_clicks"),
        Input(ids.USR_CHECK_EMAIL, "n_submit"),
        State(ids.USR_CHECK_EMAIL, "value"),
        prevent_initial_call=True,
    )
    def check(n, submitted, email):
        if not (n or submitted):
            return no_update
        return do_check(get_context(), email)
