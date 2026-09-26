"""The Users and roles page (initiative 28): an admin decides which workspace groups hold which role;
everyone else reads their own role, where it comes from and whom to ask. Every callback asks the
service again, so a Reader who calls one directly is refused, and is shown nothing."""

from __future__ import annotations

import dash
import flask

from ea.config import Settings
from ea.models import GroupRef, RoleGrant
from ea.services.identity import DirectoryUnavailable, SampleDirectory, WorkspaceGroups
from ea.services.roles import DESCRIPTIONS, use_role
from ea.ui import ids
from ea.ui.context import AppContext
from ea.ui.pages.users import (
    do_check,
    do_grant,
    do_remove,
    grants_list,
    group_options,
    history_list,
    option_value,
    parse_option,
    register,
    render,
)

ARCHITECTS = RoleGrant("sample-solution-architects", "solution-architects", "architect", note="they design")


def _walk(component, visit) -> None:
    if isinstance(component, (list, tuple)):
        for c in component:
            _walk(c, visit)
    elif component is not None and not isinstance(component, (str, int, float)):
        visit(component)
        for attr in ("children", "label", "description", "leftSection"):
            _walk(getattr(component, attr, None), visit)


def _texts(component) -> str:
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
        elif node is not None and not isinstance(node, (int, float)):
            for attr in ("children", "label", "description", "placeholder", "title"):
                walk(getattr(node, attr, None))

    walk(component)
    return " ".join(out)


def _ids(component) -> list:
    found: list = []
    _walk(component, lambda node: found.append(getattr(node, "id", None)))
    return [i for i in found if i is not None]


def _node(component, wanted):
    found = []
    _walk(component, lambda node: found.append(node) if getattr(node, "id", None) == wanted else None)
    return found[0] if found else None


def test_an_admin_reads_the_form_the_grants_the_check_and_the_recent_changes(app_context):
    app_context.settings.role_groups = "admin=platform-admins"
    app_context.backend.set_role_grant(RoleGrant(**vars(ARCHITECTS)), "ada")
    with use_role("admin"):
        page = render(app_context)
    text = _texts(page)
    for section in ("Grant a role", "Grants", "Check a person", "Recent changes"):
        assert section in text, section
    assert text.index("platform-admins") < text.index("solution-architects"), "the deployment's first"
    assert "set by the deployment" in text and "they design" in text and "granted by ada" in text
    assert all(DESCRIPTIONS[r] in text for r in ("reviewer", "architect", "admin")), (
        "each role says what it gives"
    )
    assert "ada granted Architect to solution-architects — they design" in text, "the recent changes"
    found = _ids(page)
    for wanted in (ids.USR_GROUP, ids.USR_ROLE, ids.USR_NOTE, ids.USR_GRANT, ids.USR_GRANTS, ids.USR_CHECK_EMAIL,
                   ids.USR_CHECK, ids.USR_CHECK_RESULT, ids.USR_HISTORY, ids.USR_FEEDBACK):  # fmt: skip
        assert wanted in found, wanted
    removes = [i for i in found if isinstance(i, dict) and i.get("type") == ids.USR_REMOVE]
    assert removes == [{"type": ids.USR_REMOVE, "id": ARCHITECTS.group_id}], "the deployment's have none"
    button = _node(page, removes[0])
    assert (
        button.children == "Remove"
        and "solution-architects" in button.to_plotly_json()["props"]["aria-label"]
    )
    links = []
    _walk(page, lambda n: links.append(getattr(n, "href", None)))
    assert "/metamodel" in links, "who reviews which type is on the Metamodel page's Reviewers tab"
    titles = []
    _walk(page, lambda n: titles.append(n.order) if type(n).__name__ == "Title" else None)
    assert titles.count(1) == 1 and set(titles) <= {1, 2}, "one h1, and the sections at h2"


def test_everyone_else_reads_their_own_role_where_it_comes_from_and_whom_to_ask(app_context):
    app_context.settings.admin_contact = "the architecture team (ea@example.org)"
    with use_role("reader"):
        page = render(app_context)
    text = _texts(page)
    assert "Grant a role" not in text and "Check a person" not in text and "Recent changes" not in text
    assert "Reader" in text and "the architecture team (ea@example.org)" in text
    assert "debug persona" in text, "locally the persona is the role, and the page says so"
    assert ids.USR_MINE in _ids(page) and ids.USR_GRANTS not in _ids(page)


def test_a_signed_in_person_reads_the_group_that_gives_their_role(backend):
    ctx = AppContext(Settings(auth="databricks", role_groups="reviewer=ea-reviewers"), backend)
    backend.set_role_grant(RoleGrant("g-sa", "solution-architects", "architect"), "ada")
    ctx.identity = WorkspaceGroups(lambda u, t: [GroupRef("solution-architects", "g-sa")])
    with flask.Flask(__name__).test_request_context(headers={"X-Forwarded-Email": "arjun@example.edu"}):
        with use_role(ctx.current_user().role):
            text = _texts(render(ctx))
    assert "Architect" in text and "solution-architects (granted by ada)" in text
    assert "an admin of this application" in text, "with no contact configured, whom to ask in words"


def test_a_reader_who_calls_a_callback_directly_is_refused_and_shown_nothing(app_context):
    app_context.backend.set_role_grant(RoleGrant(**vars(ARCHITECTS)), "ada")
    with use_role("reader"):
        options, message, note = group_options(app_context, "arch", None, [])
        assert options == [] and note == ""
        ok, said = do_grant(
            app_context, option_value(GroupRef("ea-admins", "sample-ea-admins")), "admin", "me"
        )
        assert not ok and "may not grant a role" in _texts(said)
        ok, said = do_remove(app_context, ARCHITECTS.group_id)
        assert not ok and "may not remove a role grant" in _texts(said)
        assert "may not check another person" in _texts(do_check(app_context, "admin@example.edu"))
        assert "solution-architects" not in _texts(grants_list(app_context))
        assert "solution-architects" not in _texts(history_list(app_context))
    assert [g.role for g in app_context.backend.list_role_grants()] == ["architect"]


def test_an_admin_picks_a_group_as_its_name_is_typed_and_grants_it(app_context):
    with use_role("admin"):
        options, message, note = group_options(app_context, "arch", None, [])
        assert [o["label"] for o in options] == ["ea-architects", "solution-architects"]
        assert group_options(app_context, "a", None, [])[1] == "Type at least two letters of the group's name"
        picked = options[1]["value"]
        # picking puts the label in the search box, which is searched again: the pick is kept
        again, *_ = group_options(app_context, "zz-nothing", picked, options)
        assert again[0]["value"] == picked
        assert parse_option(picked) == ("sample-solution-architects", "solution-architects", True)
        ok, said = do_grant(app_context, picked, "architect", "they design")
    if app_context.backend.engine == "lakebase":  # a local persona never writes into the platform's store
        assert not ok and "debug persona" in _texts(said)
        return
    assert ok and "Architect granted to solution-architects" in _texts(said)
    with use_role("admin"):
        assert "admin@example.edu granted Architect to solution-architects" in _texts(
            history_list(app_context)
        )
        assert "Architect — from the group solution-architects" in _texts(
            do_check(app_context, "architect@example.edu")
        )
        assert "Reader — none of their groups" in _texts(do_check(app_context, "reader@example.edu"))
        assert "Nobody signs in as" in _texts(do_check(app_context, "nobody@example.edu"))
        ok, said = do_grant(app_context, picked, "", "")
        assert not ok and "Pick the role" in _texts(said)
        ok, said = do_grant(app_context, None, "reviewer", "")
        assert not ok and "Pick the workspace group" in _texts(said)
        ok, said = do_remove(app_context, "sample-solution-architects")
        assert ok and "Removed the Architect grant of solution-architects" in _texts(said)


def test_where_the_directory_cannot_be_searched_the_exact_name_is_offered_not_checked(app_context):
    class Down(SampleDirectory):
        def search_groups(self, text):
            raise DirectoryUnavailable("the workspace did not answer (Timeout)")

    app_context.access.directory = Down()
    with use_role("admin"):
        options, message, note = group_options(app_context, "Data Office", None, [])
    assert "cannot be searched" in note and "exact name" in note
    assert [o["label"] for o in options] == ["Data Office — not checked"]
    assert parse_option(options[0]["value"]) == ("Data Office", "Data Office", False)


def test_the_page_s_callbacks_are_registered_with_their_controls():
    app = dash.Dash(__name__)
    register(app)
    inputs = " ".join(str(i["id"]) for cb in app.callback_map.values() for i in cb["inputs"])
    assert all(wanted in inputs for wanted in (ids.USR_GROUP, ids.USR_GRANT, ids.USR_REMOVE, ids.USR_CHECK))
    assert parse_option("not json") is None and parse_option(None) is None
