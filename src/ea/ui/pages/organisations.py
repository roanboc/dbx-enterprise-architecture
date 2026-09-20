"""Organisations: which enterprise the content describes, which one is the default, which
metamodel version each applies, and where a version is tried before it is applied to the default.

An organisation is a partition of the one store (decision 0014): its elements, relationships,
branches and reviews are its own. The default one is what the application opens. To try a
metamodel version, create an organisation copied from the default, apply the version to it
and work there; when the version is right, publish it and apply it to the default.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, html, no_update
from dash import ctx as dash_ctx

from ea.models import CompatibilityReport, ConflictError, Forbidden, NotFoundError
from ea.services.roles import a_role
from ea.ui import ids, layout
from ea.ui.components import alert, icon, issues_table, modal_title, page_title, simple_table
from ea.ui.context import AppContext, get_context

STATUS_COLOUR = {"draft": "orange", "published": "green", "retired": "gray"}


def _query(search: str | None) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs((search or "").lstrip("?")).items() if v}


def _version_options(ctx: AppContext, usable_only: bool = True) -> list[dict[str, str]]:
    return [
        {"value": v.ref, "label": f"{v.ref} ({v.status})"}
        for v in ctx.metamodels.versions()
        if not usable_only or v.status != "retired"
    ]


def _org_options(ctx: AppContext) -> list[dict[str, str]]:
    return [{"value": o.org_id, "label": o.name} for o in ctx.orgs.list()]


def _action(label: str, action: str, org_id: str, enabled: bool, colour: str = "gray", ic: str = "") -> Any:
    return dmc.Button(
        label,
        id={"type": ids.ORGS_ACTION, "action": action, "org": org_id},
        size="compact-xs",
        variant="light",
        color=colour,
        disabled=not enabled,
        leftSection=icon(ic, 12) if ic else None,
    )


def organisations_table(ctx: AppContext) -> Any:
    here = ctx.org()
    can_manage = ctx.can("manage_organisations")
    statuses = {v.ref: v.status for v in ctx.metamodels.versions()}
    rows = []
    for o in ctx.orgs.list():
        rows.append(
            [
                dmc.Group(
                    [
                        dmc.Text(o.name, fw=600, size="sm"),
                        dmc.Badge("default", color="indigo", size="xs") if o.is_default else None,
                        dmc.Badge("you are here", color="teal", variant="outline", size="xs")
                        if o.org_id == here
                        else None,
                    ],
                    gap=6,
                ),
                # an identifier broken across two lines reads as two words
                dmc.Code(o.org_id, style={"whiteSpace": "nowrap"}),
                dmc.Group(
                    [
                        dmc.Code(o.pack_ref or "none"),
                        dmc.Badge(
                            statuses.get(o.pack_ref, "unknown"),
                            color=STATUS_COLOUR.get(statuses.get(o.pack_ref, ""), "red"),
                            variant="light",
                            size="xs",
                        ),
                    ],
                    gap=6,
                ),
                o.elements,
                o.relationships,
                o.branches,
                "; ".join(
                    x for x in (f"copied from {o.copied_from}" if o.copied_from else "", o.description) if x
                ),
                dmc.Group(
                    [
                        dmc.Button(
                            "Switch to",
                            id={"type": ids.ORG_SWITCH, "id": o.org_id},
                            size="compact-xs",
                            variant="light",
                            color="indigo",
                            disabled=o.org_id == here,
                            leftSection=icon("tabler:building", 12),
                        ),
                        _action(
                            "Make default",
                            "default",
                            o.org_id,
                            can_manage and not o.is_default,
                            "indigo",
                            "tabler:star",
                        ),
                        _action(
                            "Delete",
                            "delete",
                            o.org_id,
                            can_manage and not o.is_default and o.org_id != here,
                            "red",
                            "tabler:trash",
                        ),
                    ],
                    gap=4,
                ),
            ]
        )
    return simple_table(
        ["organisation", "id", "applies", "elements", "relationships", "open branches", "about", ""], rows
    )


def report_view(report: CompatibilityReport, applied: bool) -> Any:
    counts = report.by_code()
    verdict = (
        f"{report.pack_id}@{report.version} fits {report.org_id}: {report.elements} elements and "
        f"{report.relationships} relationships checked, nothing would be left invalid."
        if not report.issues
        else report.summary()
    )
    colour = "green" if report.ok and not report.warnings else ("yellow" if report.ok else "red")
    return dmc.Stack(
        [
            alert(("Applied. " if applied else "") + verdict, colour, dismissible=False),
            dmc.Group(
                [
                    dmc.Badge(f"{code} × {n}", variant="light", color="gray", size="xs")
                    for code, n in counts.items()
                ],
                gap=4,
            )
            if counts
            else None,
            issues_table(report.issues[:200]) if report.issues else None,
            dmc.Text(f"{len(report.issues) - 200} more findings not shown.", size="xs", c="dimmed")
            if len(report.issues) > 200
            else None,
        ],
        gap="xs",
    )


def render(ctx: AppContext, search: str | None = None) -> html.Div:
    q = _query(search)
    can_manage = ctx.can("manage_organisations")
    can_apply = ctx.can("apply_metamodel")
    default = ctx.orgs.default()
    versions = _version_options(ctx)
    preselected = q.get("version") if any(v["value"] == q.get("version") for v in versions) else None
    why_manage = (
        "" if can_manage else f"{a_role(ctx.role_label())} may not manage organisations; only an admin does."
    )
    return html.Div(
        [
            page_title(
                "Organisations",
                "The enterprises whose architecture this store holds, each applying one version of the "
                "metamodel. The default one is what the application opens; another is where a version is "
                "tried on a copy of the content before it is applied to the default. Switch with the "
                "selector in the header or a row's button.",
            ),
            html.Div(id=ids.ORGS_FEEDBACK),
            dmc.Paper(html.Div(organisations_table(ctx), id=ids.ORGS_LIST), p="md", withBorder=True, mb="md"),
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        [
                            dmc.Title("New organisation", order=2, size="h5", mb="xs"),
                            dmc.Text(
                                "A sandbox to try a metamodel version starts as a copy of the default "
                                "organisation's content; an enterprise of its own starts empty.",
                                size="sm",
                                c="dimmed",
                                mb="xs",
                            ),
                            dmc.Stack(
                                [
                                    dmc.TextInput(
                                        id=ids.ORGS_NEW_NAME,
                                        label="Name",
                                        required=True,
                                        placeholder="Trial: lean information domain",
                                    ),
                                    dmc.Textarea(
                                        id=ids.ORGS_NEW_DESC,
                                        label="What it is for",
                                        autosize=True,
                                        minRows=2,
                                    ),
                                    dmc.Select(
                                        id=ids.ORGS_NEW_VERSION,
                                        allowDeselect=False,
                                        label="Metamodel version it applies",
                                        data=versions,
                                        value=preselected or (default.pack_ref if default else None),
                                        searchable=True,
                                        comboboxProps={"withinPortal": True},
                                    ),
                                    dmc.Select(
                                        id=ids.ORGS_NEW_COPY,
                                        allowDeselect=False,
                                        label="Copy the content of",
                                        data=[{"value": "", "label": "Nobody: start empty"}]
                                        + _org_options(ctx),
                                        value=default.org_id if default else "",
                                        comboboxProps={"withinPortal": True},
                                    ),
                                    dmc.Group(
                                        [
                                            dmc.Button(
                                                "Create",
                                                id=ids.ORGS_NEW_SAVE,
                                                leftSection=icon("tabler:plus"),
                                                disabled=not can_manage,
                                            ),
                                            dmc.Text(why_manage, id=ids.ORGS_NEW_WHY, size="xs", c="dimmed"),
                                        ],
                                        gap="sm",
                                        align="center",
                                    ),
                                ],
                                gap="xs",
                            ),
                        ],
                        p="md",
                        withBorder=True,
                    ),
                    dmc.Paper(
                        [
                            dmc.Title("Apply a metamodel version", order=2, size="h5", mb="xs"),
                            dmc.Text(
                                "Check first: every element and relationship of the organisation's main is "
                                "validated against the version, and the findings are listed. Apply refuses "
                                "on errors unless forced; warnings never block.",
                                size="sm",
                                c="dimmed",
                                mb="xs",
                            ),
                            dmc.Stack(
                                [
                                    dmc.Select(
                                        id=ids.ORGS_APPLY_ORG,
                                        allowDeselect=False,
                                        label="Organisation",
                                        data=_org_options(ctx),
                                        value=ctx.org(),
                                        comboboxProps={"withinPortal": True},
                                    ),
                                    dmc.Select(
                                        id=ids.ORGS_APPLY_VERSION,
                                        allowDeselect=False,
                                        label="Version",
                                        data=versions,
                                        value=preselected or ctx.registry.pack.ref,
                                        searchable=True,
                                        comboboxProps={"withinPortal": True},
                                    ),
                                    dmc.Checkbox(
                                        id=ids.ORGS_APPLY_FORCE,
                                        label="Apply even when the check finds errors",
                                        checked=False,
                                    ),
                                    dmc.Group(
                                        [
                                            dmc.Button(
                                                "Check",
                                                id=ids.ORGS_APPLY_CHECK,
                                                variant="light",
                                                leftSection=icon("tabler:checklist"),
                                            ),
                                            dmc.Button(
                                                "Apply",
                                                id=ids.ORGS_APPLY_RUN,
                                                leftSection=icon("tabler:rocket"),
                                                disabled=not can_apply,
                                            ),
                                            dmc.Text(
                                                ""
                                                if can_apply
                                                else f"{a_role(ctx.role_label())} may check, not apply.",
                                                size="xs",
                                                c="dimmed",
                                            ),
                                        ],
                                        gap="sm",
                                        align="center",
                                    ),
                                ],
                                gap="xs",
                            ),
                            html.Div(id=ids.ORGS_APPLY_RESULT, style={"marginTop": "0.75rem"}),
                        ],
                        p="md",
                        withBorder=True,
                    ),
                ],
                cols={"base": 1, "lg": 2},
                spacing="md",
            ),
            dmc.Modal(
                id=ids.ORGS_CONFIRM_MODAL,
                title=modal_title("Are you sure?", ids.ORGS_CONFIRM_MODAL),
                closeButtonProps={"aria-label": "Close this dialog"},
                children=dmc.Stack(
                    [
                        html.Div(id=ids.ORGS_CONFIRM_TEXT),
                        dmc.Group(
                            [dmc.Button("Yes, delete it", id=ids.ORGS_CONFIRM_YES, color="red")],
                            justify="flex-end",
                        ),
                    ]
                ),
            ),
            html.Div(id=ids.ORGS_CONFIRM_STORE, hidden=True),
        ]
    )


def register(app: dash.Dash) -> None:
    list_outputs = [
        Output(ids.ORGS_FEEDBACK, "children", allow_duplicate=True),
        Output(ids.ORGS_LIST, "children", allow_duplicate=True),
        Output(ids.ORG_SELECT, "data", allow_duplicate=True),
        Output(ids.ORGS_APPLY_ORG, "data", allow_duplicate=True),
        Output(ids.ORGS_NEW_COPY, "data", allow_duplicate=True),
        Output(ids.PACK_BADGE, "children", allow_duplicate=True),
    ]

    def refreshed(ctx: AppContext, message: Any) -> tuple:
        return (
            message,
            organisations_table(ctx),
            ctx.org_options(),
            _org_options(ctx),
            [{"value": "", "label": "Nobody: start empty"}] + _org_options(ctx),
            layout.pack_badge(ctx.pack_label()),
        )

    @app.callback(
        *list_outputs,
        Input(ids.ORGS_NEW_SAVE, "n_clicks"),
        State(ids.ORGS_NEW_NAME, "value"),
        State(ids.ORGS_NEW_DESC, "value"),
        State(ids.ORGS_NEW_VERSION, "value"),
        State(ids.ORGS_NEW_COPY, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.ORGS_NEW_SAVE, "loading"), True, False)],
    )
    def create(n, name, desc, version, copy_from):
        if not n:
            return (no_update,) * 6
        ctx = get_context()
        if not (name or "").strip():
            return (alert("An organisation needs a name.", "yellow"),) + (no_update,) * 5
        try:
            o = ctx.orgs.create(name, ctx.actor, desc or "", version or "", copy_from or None)
        except (ConflictError, Forbidden, NotFoundError, ValueError) as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 5
        ctx.reload_registry()
        return refreshed(
            ctx,
            alert(
                f"Organisation {o.name} created, applying {o.pack_ref}"
                + (
                    f", with {o.elements} elements and {o.relationships} relationships copied from {o.copied_from}"
                    if o.copied_from
                    else ""
                )
                + ". Switch to it with the selector in the header.",
                "green",
            ),
        )

    @app.callback(
        *list_outputs,
        Output(ids.ORGS_CONFIRM_MODAL, "opened"),
        Output(ids.ORGS_CONFIRM_TEXT, "children"),
        Output(ids.ORGS_CONFIRM_STORE, "children"),
        Input({"type": ids.ORGS_ACTION, "action": ALL, "org": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def action(clicks):
        trigger = dash_ctx.triggered_id
        if not isinstance(trigger, dict) or not any(n for n in (clicks or []) if n):
            return (no_update,) * 9
        ctx = get_context()
        what, org_id = trigger.get("action"), trigger.get("org")
        try:
            if what == "default":
                o = ctx.orgs.set_default(org_id, ctx.actor)
                return refreshed(ctx, alert(f"{o.name} is the default organisation.", "green")) + (
                    no_update,
                    no_update,
                    no_update,
                )
            if what == "delete":
                o = ctx.orgs.get(org_id)
                return (no_update,) * 6 + (
                    True,
                    dmc.Text(
                        f"Delete {o.name} ({o.org_id})? Its {o.elements} elements, {o.relationships} "
                        "relationships, branches, reviews and proposals are removed for good.",
                        size="sm",
                    ),
                    org_id,
                )
        except (ConflictError, Forbidden, NotFoundError) as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 8
        return (no_update,) * 9

    @app.callback(
        *list_outputs,
        Output(ids.ORGS_CONFIRM_MODAL, "opened", allow_duplicate=True),
        Input(ids.ORGS_CONFIRM_YES, "n_clicks"),
        State(ids.ORGS_CONFIRM_STORE, "children"),
        prevent_initial_call=True,
    )
    def confirmed(n, org_id):
        if not n or not org_id:
            return (no_update,) * 7
        ctx = get_context()
        try:
            ctx.orgs.delete(org_id, ctx.actor)
        except (ConflictError, Forbidden, NotFoundError) as exc:
            return (alert(str(exc), "red"),) + (no_update,) * 5 + (False,)
        ctx.reload_registry()
        return refreshed(ctx, alert(f"Organisation {org_id} deleted.", "green")) + (False,)

    @app.callback(
        *list_outputs,
        Output(ids.ORGS_APPLY_RESULT, "children"),
        Input(ids.ORGS_APPLY_CHECK, "n_clicks"),
        Input(ids.ORGS_APPLY_RUN, "n_clicks"),
        State(ids.ORGS_APPLY_ORG, "value"),
        State(ids.ORGS_APPLY_VERSION, "value"),
        State(ids.ORGS_APPLY_FORCE, "checked"),
        prevent_initial_call=True,
        running=[
            (Output(ids.ORGS_APPLY_CHECK, "loading"), True, False),
            (Output(ids.ORGS_APPLY_RUN, "loading"), True, False),
        ],
    )
    def check_or_apply(n_check, n_apply, org_id, ref, force):
        trigger = dash_ctx.triggered_id
        if (trigger == ids.ORGS_APPLY_CHECK and not n_check) or (
            trigger == ids.ORGS_APPLY_RUN and not n_apply
        ):
            return (no_update,) * 7
        ctx = get_context()
        if not org_id or not ref:
            return (no_update,) * 6 + (alert("Pick an organisation and a version.", "yellow"),)
        try:
            if trigger == ids.ORGS_APPLY_CHECK:
                report = ctx.orgs.check(org_id, ref)
                return (no_update,) * 6 + (report_view(report, applied=False),)
            report = ctx.orgs.apply(org_id, ref, ctx.actor, force=bool(force))
        except (ConflictError, Forbidden, NotFoundError) as exc:
            return (no_update,) * 6 + (alert(str(exc), "red"),)
        ctx.reload_registry()
        return refreshed(ctx, alert(f"{ctx.orgs.get(org_id).name} now applies {ref}.", "green")) + (
            report_view(report, applied=True),
        )
