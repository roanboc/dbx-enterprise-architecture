"""Dash application factory: shell, routing, the current branch, and page callbacks."""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import unquote

import dash
import dash_cytoscape as cyto
import dash_mantine_components as dmc
from dash import ALL, MATCH, Input, Output, State, ctx, no_update
from flask import session

from ea.backend.branching import MAIN, set_branch
from ea.backend.organisations import set_org
from ea.config import ROOT
from ea.models import ConflictError, Forbidden, NotFoundError
from ea.services.roles import set_role
from ea.ui import graph, ids, layout
from ea.ui.components import alert, register_markdown
from ea.ui.context import PERSONAS, get_context
from ea.ui.pages import (
    ask,
    branches,
    browse,
    element,
    health,
    home,
    impact,
    import_page,
    metamodel,
    organisations,
    propose,
    target,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

APP_TITLE = "EA Repository"
NAV_TARGETS = [href for _, links in layout.NAV_SECTIONS for _, href, _ in links]
NAV_LINK_IDS = [f"nav-{href.strip('/') or 'home'}" for href in NAV_TARGETS]
PAGES = {
    "browse",
    "metamodel",
    "organisations",
    "impact",
    "import",
    "ask",
    "branches",
    "target",
    "propose",
    "health",
}


def parse_path(pathname: str | None) -> tuple[str, str | None]:
    parts = [unquote(p) for p in (pathname or "/").split("/") if p]
    if not parts:
        return "home", None
    if parts[0] == "element" and len(parts) >= 2:
        return "element", parts[1]
    if parts[0] in PAGES:
        return parts[0], None
    return "home", None


def address_note(pathname: str | None) -> str:
    """What the router could not place in the address, or empty when it read all of it.

    Falling back is the right answer; doing it in silence is not. An address the router
    cannot place at all, one that names a page and then says more, and a half-written
    element address are all mistypes, and the reader is told which they made.
    """
    parts = [unquote(p) for p in (pathname or "/").split("/") if p]
    if not parts:
        return ""
    if parts[0] == "element":
        if len(parts) == 1:
            return f"There is no page at {pathname}: an element address carries its identifier, as /element/<id>."
        if len(parts) > 2:
            return f"There is no page at {pathname}: everything after the element identifier was ignored."
        return ""
    if parts[0] in PAGES:
        if len(parts) > 1:
            return f"There is no page at {pathname}: /{parts[0]} takes no address under it, so the rest was ignored."
        return ""
    return f"There is no page at {pathname}. This is the home page."


def session_branch() -> str:
    """The branch kept in the reader's session; main when none or when the branch is gone."""
    try:
        return session.get("branch") or MAIN
    except RuntimeError:  # outside a request
        return MAIN


def session_org(default: str) -> str:
    """The organisation kept in the reader's session; the default one when none is kept."""
    try:
        return session.get("org") or default
    except RuntimeError:  # outside a request
        return default


def _enter_session_org() -> str:
    """The organisation the request works in: the session's, falling back to the default one when
    the session names one that is gone. Set before the branch, which belongs to it."""
    ctx = get_context()
    default = ctx.orgs.default()
    default_id = default.org_id if default else "default"
    org = session_org(default_id)
    if ctx.backend.get_organisation(org) is None:
        org = default_id
    set_org(org)
    return org


def create_app() -> dash.Dash:
    cyto.load_extra_layouts()  # cose-bilkent and friends for the graph panel
    get_context()  # open the store and load the pack before the first request
    app = dash.Dash(
        __name__,
        title=APP_TITLE,
        external_stylesheets=dmc.styles.ALL,
        suppress_callback_exceptions=True,
        assets_folder=str(ROOT / "assets"),
        update_title=None,
    )
    # The document's language is the first thing assistive technology reads: without it a
    # screen reader guesses its voice from the reader's locale rather than from the page.
    app.index_string = app.index_string.replace("<html>", '<html lang="en">', 1)
    # The branch a reader is on lives in a signed session cookie. Set EA_SECRET_KEY so sessions
    # survive a restart; without it every restart puts everybody back on main.
    app.server.secret_key = os.environ.get("EA_SECRET_KEY") or secrets.token_hex(32)

    @app.server.before_request
    def _branch_and_role_from_session() -> None:
        ctx = get_context()
        _enter_session_org()
        branch = session_branch()
        if branch != MAIN and ctx.backend.get_branch(branch) is None:
            branch = MAIN
        set_branch(branch)
        set_role(ctx.current_user().role)

    def _shell():
        ctx = get_context()
        current = ctx.branch()
        b = ctx.backend.get_branch(current) if current != MAIN else None
        if b is not None and b.status in ("merged", "abandoned"):
            current = MAIN
        user = ctx.current_user()
        return layout.shell(
            APP_TITLE,
            ctx.pack_label(),
            ctx.branch_options(),
            current,
            b.changes if b is not None else None,
            ctx.work_package_options(),
            role=user.role,
            display_name=user.display_name,
            persona=ctx.persona() if ctx.debug_personas() else None,
            can_create_branch=ctx.can("create_branch"),
            org_options=ctx.org_options(),
            current_org=ctx.org(),
        )

    app.layout = _shell  # a function: the header reflects the session's branch on every page load

    @app.callback(
        Output(ids.NAVBAR_OPEN, "data"),
        Output(ids.NAV_BURGER, "opened"),
        Output(ids.APP_SHELL, "navbar"),
        Input(ids.NAV_BURGER_CLICK, "n_clicks"),
        Input(ids.URL, "pathname"),
        State(ids.NAVBAR_OPEN, "data"),
        prevent_initial_call=True,
    )
    def toggle_mobile_nav(_clicks, _pathname, opened):
        next_open = not bool(opened) if ctx.triggered_id == ids.NAV_BURGER_CLICK else False
        return (
            next_open,
            next_open,
            {"width": 220, "breakpoint": "sm", "collapsed": {"mobile": not next_open}},
        )

    @app.callback(
        [Output(link, "active") for link in NAV_LINK_IDS],
        Input(ids.URL, "pathname"),
    )
    def mark_current_page(pathname):
        """Say which page the reader is on. An element belongs to Browse, which opened it."""
        page, _ = parse_path(pathname)
        here = "/browse" if page == "element" else ("/" if page == "home" else f"/{page}")
        return [href == here for href in NAV_TARGETS]

    @app.callback(
        Output(ids.PAGE, "children"),
        Input(ids.URL, "pathname"),
        Input(ids.URL, "search"),
        Input(ids.NAV_VERSION, "data"),
    )
    def route(pathname, search, _version):
        ctx = get_context()
        page, arg = parse_path(pathname)
        try:
            if page == "element":
                body = element.render(ctx, arg or "")
            elif page == "browse":
                body = browse.render(ctx, search)
            elif page == "metamodel":
                body = metamodel.render(ctx)
            elif page == "organisations":
                body = organisations.render(ctx, search)
            elif page == "impact":
                body = impact.render(ctx, search)
            elif page == "import":
                body = import_page.render(ctx)
            elif page == "ask":
                body = ask.render(ctx)
            elif page == "branches":
                body = branches.render(ctx, search)
            elif page == "target":
                body = target.render(ctx, search)
            elif page == "propose":
                body = propose.render(ctx)
            elif page == "health":
                body = health.render(ctx)
            else:
                body = home.render(ctx)
            note = address_note(pathname)
            return dmc.Stack([alert(note, "yellow"), body], gap="sm") if note else body
        except Exception as exc:  # noqa: BLE001 — a page error must not blank the shell
            log.exception("page %s failed", page)
            return dmc.Alert(f"{type(exc).__name__}: {exc}", color="red", title="This page failed to render")

    # ---------------------------------------------------------- organisation
    @app.callback(
        Output(ids.NAV_VERSION, "data", allow_duplicate=True),
        Output(ids.ORG_SELECT, "value"),
        Output(ids.BRANCH_SELECT, "data", allow_duplicate=True),
        Output(ids.BRANCH_SELECT, "value", allow_duplicate=True),
        Output(ids.BRANCH_BADGE, "children", allow_duplicate=True),
        Output(ids.PACK_BADGE, "children"),
        Output(ids.BRANCH_NEW_WP, "data"),
        Input(ids.ORG_SELECT, "value"),
        Input({"type": ids.ORG_SWITCH, "id": ALL}, "n_clicks"),
        State(ids.NAV_VERSION, "data"),
        prevent_initial_call=True,
    )
    def switch_org(value, switch_clicks, version):
        """Keep the chosen organisation in the session, back on its main, and re-render the page in it."""
        app_ctx = get_context()
        trigger = ctx.triggered_id
        from_row = isinstance(trigger, dict) and trigger.get("type") == ids.ORG_SWITCH
        if from_row and not any(n for n in (switch_clicks or []) if n):
            return (no_update,) * 7
        default = app_ctx.orgs.default()
        default_id = default.org_id if default else "default"
        chosen = (trigger["id"] if from_row else value) or default_id
        if app_ctx.backend.get_organisation(chosen) is None:
            chosen = default_id
        changed = chosen != session_org(default_id)
        session["org"] = chosen
        session["branch"] = MAIN  # a branch belongs to its organisation; the other one starts on main
        set_org(chosen)
        set_branch(MAIN)
        return (
            int(version or 0) + 1 if changed else no_update,
            chosen if from_row else no_update,
            app_ctx.branch_options(),
            MAIN,
            layout.branch_badge(MAIN),
            layout.pack_badge(app_ctx.pack_label()),
            app_ctx.work_package_options(),
        )

    # ---------------------------------------------------------------- branch
    @app.callback(
        Output(ids.NAV_VERSION, "data"),
        Output(ids.BRANCH_BADGE, "children"),
        Input(ids.BRANCH_SELECT, "value"),
        State(ids.NAV_VERSION, "data"),
    )
    def switch_branch(value, version):
        """Keep the chosen branch in the session and re-render the page on it."""
        ctx = get_context()
        chosen = value or MAIN
        if chosen != MAIN and ctx.backend.get_branch(chosen) is None:
            chosen = MAIN
        changed = chosen != session_branch()
        session["branch"] = chosen
        set_branch(chosen)
        b = ctx.backend.get_branch(chosen) if chosen != MAIN else None
        badge = layout.branch_badge(chosen, b.changes if b else None)
        return (int(version or 0) + 1 if changed else no_update), badge

    @app.callback(
        Output(ids.BRANCH_NEW_MODAL, "opened"),
        Input(ids.BRANCH_NEW_OPEN, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_new_branch(n):
        return bool(n)

    if get_context().debug_personas():

        @app.callback(
            Output(ids.NAV_VERSION, "data", allow_duplicate=True),
            Output(ids.ROLE_BADGE, "children"),
            Output(ids.BRANCH_NEW_OPEN, "disabled"),
            Output(ids.BRANCH_NEW_TIP, "label"),
            Output(ids.BRANCH_NEW_WHY, "children"),
            Input(ids.PERSONA_SELECT, "value"),
            State(ids.NAV_VERSION, "data"),
            prevent_initial_call=True,
        )
        def switch_persona(value, version):
            """Debug only: impersonate a role, kept in the session; the page re-renders with its permissions."""
            persona = value if value in PERSONAS else "admin"
            changed = persona != (session.get("persona") or "admin")
            session["persona"] = persona
            user = PERSONAS[persona]
            set_role(user.role)
            can_create = get_context().can("create_branch")
            return (
                int(version or 0) + 1 if changed else no_update,
                layout.role_badge(user.role, user.display_name),
                not can_create,
                layout.new_branch_tip(can_create),
                layout.new_branch_tip(can_create),
            )

    @app.callback(
        Output(ids.BRANCH_NEW_FEEDBACK, "children"),
        Output(ids.BRANCH_NEW_MODAL, "opened", allow_duplicate=True),
        Output(ids.BRANCH_SELECT, "data"),
        Output(ids.BRANCH_SELECT, "value"),
        Input(ids.BRANCH_NEW_SAVE, "n_clicks"),
        State(ids.BRANCH_NEW_NAME, "value"),
        State(ids.BRANCH_NEW_DESC, "value"),
        State(ids.BRANCH_NEW_WP, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.BRANCH_NEW_SAVE, "loading"), True, False)],
    )
    def create_branch(n, name, desc, wp):
        if not n:
            return no_update, no_update, no_update, no_update
        ctx = get_context()
        if not (name or "").strip():
            return alert("A branch needs a name.", "yellow"), no_update, no_update, no_update
        try:
            b = ctx.branches.create(name.strip(), ctx.actor, desc or "", wp or "")
        except (ConflictError, NotFoundError, ValueError, Forbidden) as exc:
            return alert(str(exc), "red"), no_update, no_update, no_update
        return None, False, ctx.branch_options(), b.branch_id

    app.clientside_callback(
        """
        function(code, nReset) {
            const out = dash_clientside.callback_context.outputs_list;
            const target = JSON.stringify({id: out.id.id, type: 'mermaid-svg'});
            const posId = {id: out.id.id, type: 'mermaid-pos'};
            if (!window.eaViews) { return window.dash_clientside.no_update; }
            return window.eaViews.render(target, code || '', function (positions) {
                window.dash_clientside.set_props(posId, {data: positions});
            });
        }
        """,
        Output({"type": ids.MERMAID_POS, "id": MATCH}, "data"),
        Input({"type": ids.MERMAID_SRC, "id": MATCH}, "children"),
        Input({"type": ids.MERMAID_RESET, "id": MATCH}, "n_clicks"),
    )

    app.clientside_callback(
        """
        function(zoomOut, zoomIn, fit, full) {
            const trigger = dash_clientside.callback_context.triggered_id;
            if (!trigger || !window.eaViews) { return window.dash_clientside.no_update; }
            const target = JSON.stringify({id: trigger.id, type: 'mermaid-svg'});
            if (trigger.type === 'mermaid-zoom-out') { window.eaViews.zoom(target, 1 / 1.3); }
            else if (trigger.type === 'mermaid-zoom-in') { window.eaViews.zoom(target, 1.3); }
            else if (trigger.type === 'mermaid-fit') { window.eaViews.fit(target); }
            else if (trigger.type === 'mermaid-full') { window.eaViews.fullscreen(target); }
            return window.dash_clientside.no_update;
        }
        """,
        Output({"type": ids.MERMAID_VIEW, "id": MATCH}, "data"),
        Input({"type": ids.MERMAID_ZOOM_OUT, "id": MATCH}, "n_clicks"),
        Input({"type": ids.MERMAID_ZOOM_IN, "id": MATCH}, "n_clicks"),
        Input({"type": ids.MERMAID_FIT, "id": MATCH}, "n_clicks"),
        Input({"type": ids.MERMAID_FULL, "id": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )

    graph.register(app)
    register_markdown(app)
    for module in (
        browse,
        element,
        metamodel,
        organisations,
        impact,
        import_page,
        ask,
        branches,
        target,
        propose,
        health,
    ):
        module.register(app)
    return app
