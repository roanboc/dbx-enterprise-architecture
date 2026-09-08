"""Dash application factory: shell, routing, the current branch, and page callbacks."""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import unquote

import dash
import dash_cytoscape as cyto
import dash_mantine_components as dmc
from dash import MATCH, Input, Output, State, ctx, no_update
from flask import session

from ea.backend.branching import MAIN, set_branch
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
    propose,
    target,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

APP_TITLE = "EA Repository"
NAV_TARGETS = [href for _, links in layout.NAV_SECTIONS for _, href, _ in links]
NAV_LINK_IDS = [f"nav-{href.strip('/') or 'home'}" for href in NAV_TARGETS]
PAGES = {"browse", "metamodel", "impact", "import", "ask", "branches", "target", "propose", "health"}


def parse_path(pathname: str | None) -> tuple[str, str | None]:
    parts = [unquote(p) for p in (pathname or "/").split("/") if p]
    if not parts:
        return "home", None
    if parts[0] == "element" and len(parts) >= 2:
        return "element", parts[1]
    if parts[0] in PAGES:
        return parts[0], None
    return "home", None


def session_branch() -> str:
    """The branch kept in the reader's session; main when none or when the branch is gone."""
    try:
        return session.get("branch") or MAIN
    except RuntimeError:  # outside a request
        return MAIN


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
    # The branch a reader is on lives in a signed session cookie. Set EA_SECRET_KEY so sessions
    # survive a restart; without it every restart puts everybody back on main.
    app.server.secret_key = os.environ.get("EA_SECRET_KEY") or secrets.token_hex(32)

    @app.server.before_request
    def _branch_and_role_from_session() -> None:
        ctx = get_context()
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
            ctx.registry.pack.name,
            ctx.branch_options(),
            current,
            b.changes if b is not None else None,
            ctx.work_package_options(),
            role=user.role,
            display_name=user.display_name,
            persona=ctx.persona() if ctx.debug_personas() else None,
            can_create_branch=ctx.can("create_branch"),
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
                return element.render(ctx, arg or "")
            if page == "browse":
                return browse.render(ctx, search)
            if page == "metamodel":
                return metamodel.render(ctx)
            if page == "impact":
                return impact.render(ctx, search)
            if page == "import":
                return import_page.render(ctx)
            if page == "ask":
                return ask.render(ctx)
            if page == "branches":
                return branches.render(ctx, search)
            if page == "target":
                return target.render(ctx, search)
            if page == "propose":
                return propose.render(ctx)
            if page == "health":
                return health.render(ctx)
            if (pathname or "/").rstrip("/") not in ("", None):
                # Falling back to Home is the right answer; doing it in silence is not.
                # A reader who mistyped, or followed a stale link, is told which it was.
                return dmc.Stack(
                    [
                        alert(f"There is no page at {pathname}. This is the home page.", "yellow"),
                        home.render(ctx),
                    ],
                    gap="sm",
                )
            return home.render(ctx)
        except Exception as exc:  # noqa: BLE001 — a page error must not blank the shell
            log.exception("page %s failed", page)
            return dmc.Alert(f"{type(exc).__name__}: {exc}", color="red", title="This page failed to render")

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
    for module in (browse, element, metamodel, impact, import_page, ask, branches, target, propose, health):
        module.register(app)
    return app
