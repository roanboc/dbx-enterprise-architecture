"""The Connected systems page (initiative 26): everyone reads the list; only an admin connects or disconnects."""

from __future__ import annotations

from ea.models import ConnectedSystem
from ea.services.roles import use_role
from ea.ui import ids
from ea.ui.pages.systems import (
    connection_fill,
    connection_picker,
    render,
    system_card,
    system_from_form,
    system_list,
)


def _texts(component) -> str:
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
        elif node is not None:
            for attr in ("children", "label", "description", "placeholder"):
                walk(getattr(node, attr, None))

    walk(component)
    return " ".join(out)


def test_the_form_becomes_a_system_the_service_checks():
    s = system_from_form(
        "Wiki", "https://wiki.example.org/mcp", "read_page, search", ["capability"], "https://wiki.example.org/",
        "read_page", "none", "", None,
    )  # fmt: skip
    assert s.tools == ["read_page", "search"] and s.link_prefixes == ["https://wiki.example.org/"]
    assert s.speaks_for == ["capability"] and s.auth == "none"


def test_a_reader_sees_the_list_and_why_they_cannot_change_it(app_context):
    with use_role("admin"):
        app_context.connected.save(
            ConnectedSystem(name="CMDB", url="https://cmdb.example.org/mcp", tools=["lookup"], auth="none"),
            "ana",
        )
    with use_role("reader"):
        page = _texts(render(app_context))
    assert "CMDB" in page and "may not connect a system" in page and "Connect a system" not in page
    with use_role("admin"):
        page = _texts(render(app_context))
        assert "Connect a system" in page
        assert "Disconnect" in _texts(system_list(app_context))


def test_with_nothing_connected_the_page_says_the_assistant_reads_the_model_alone(app_context):
    with use_role("reader"):
        assert "reads the model alone" in _texts(system_list(app_context))


def test_the_form_takes_a_page_pattern_and_the_arguments_the_page_tool_is_given():
    s = system_from_form(
        "Wiki", "https://w.example.org/api/2.0/mcp/external/wiki", "getConfluencePage", [],
        "https://example.atlassian.net/wiki/", "getConfluencePage", "app", "", ["architect"],
        page_pattern=r" /pages/(?P<page_id>\d+) ", page_arguments='{"pageId": "{page_id}"}',
    )  # fmt: skip
    assert s.auth == "app" and s.roles == ["architect"]
    assert s.page_pattern == r"/pages/(?P<page_id>\d+)" and s.page_arguments == '{"pageId": "{page_id}"}'


def test_a_workspace_connection_picked_fills_the_name_and_the_address():
    offered = [
        {"name": "wiki", "url": "https://w.example.org/api/2.0/mcp/external/wiki", "comment": "The wiki"}
    ]
    picker = connection_picker(offered, "").children[0]
    assert picker.id == ids.SYS_CONNECTION and picker.data == [
        {"value": offered[0]["url"], "label": "wiki — The wiki"}
    ]
    assert connection_fill(offered[0]["url"]) == ("wiki", offered[0]["url"])
    assert connection_fill(None) is None
    none = connection_picker([], "the Databricks SDK is not installed")
    assert (
        none.children[0].data == []
        and none.children[0].disabled
        and "the Databricks SDK is not installed" in _texts(none)
    )


def test_the_card_shows_the_page_pattern_and_its_arguments(app_context):
    s = ConnectedSystem(
        name="Wiki", url="https://w.example.org/mcp", tools=["getConfluencePage"], auth="app",
        link_prefixes=["https://example.atlassian.net/wiki/"], page_tool="getConfluencePage",
        page_pattern=r"/pages/(?P<page_id>\d+)", page_arguments={"cloudId": "abc-123", "pageId": "{page_id}"},
    )  # fmt: skip
    card = _texts(system_card(app_context, s, False))
    assert "/pages/(?P<page_id>" in card and '"pageId": "{page_id}"' in card
    assert "application's own identity" in card


def test_an_admin_is_offered_the_workspace_connections_and_the_new_fields(app_context):
    with use_role("admin"):
        page = render(app_context)
    found = set()

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
        elif node is not None and not isinstance(node, str):
            found.add(getattr(node, "id", None))
            walk(getattr(node, "children", None))

    walk(page)
    assert {
        ids.SYS_CONNECTION,
        ids.SYS_CONNECTIONS_NOTE,
        ids.SYS_PAGE_PATTERN,
        ids.SYS_PAGE_ARGUMENTS,
    } <= found


def test_a_picked_connection_fills_a_name_nobody_typed_and_keeps_one_somebody_did():
    wiki = "https://w.example.org/api/2.0/mcp/external/wiki"
    jira = "https://w.example.org/api/2.0/mcp/external/jira"
    assert connection_fill(wiki, "", "") == ("wiki", wiki)  # an empty name is filled
    assert connection_fill(wiki, "The wiki", "") == ("The wiki", wiki)  # a typed one is kept
    # a second pick replaces the name the first pick filled in, never one the admin typed
    assert connection_fill(jira, "wiki", wiki) == ("jira", jira)
    assert connection_fill(jira, "The wiki", wiki) == ("The wiki", jira)
    assert connection_fill(None, "wiki", wiki) is None  # clearing the picker leaves the form alone


class _Workspace:
    def __init__(self, names):
        from types import SimpleNamespace

        self.config = SimpleNamespace(host="https://w.example.org")
        conns = [
            SimpleNamespace(name=n, connection_type="HTTP", options={"is_mcp_connection": "true"}, comment="")
            for n in names
        ]
        self.connections = SimpleNamespace(list=lambda **_: iter(conns))


def _picker(page):
    found = {}

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
        elif node is not None and not isinstance(node, str):
            if getattr(node, "id", None) in (ids.SYS_CONNECTION, ids.SYS_CONNECTIONS_NOTE):
                found[node.id] = node
            walk(getattr(node, "children", None))

    walk(page)
    return found


def test_the_picker_offers_the_workspace_s_connections_and_says_why_when_there_is_none(app_context):
    app_context.connected.workspace = lambda: _Workspace(["wiki"])
    with use_role("admin"):
        found = _picker(render(app_context))
    assert [c["label"] for c in found[ids.SYS_CONNECTION].data] == ["wiki"]

    def unconfigured():
        raise ValueError("default auth: cannot configure")

    app_context.connected.workspace = unconfigured
    with use_role("admin"):
        found = _picker(render(app_context))
    assert found[ids.SYS_CONNECTION].data == []
    assert "no Databricks workspace is configured here" in found[ids.SYS_CONNECTIONS_NOTE].children


def test_a_page_test_never_reaches_a_real_workspace(app_context):
    """The fixture's context lists no workspace's connections, whatever the machine is signed in to."""
    with use_role("admin"):
        offered, reason = app_context.connected.workspace_connections()
    assert offered == [] and reason == "no Databricks workspace is configured here"
