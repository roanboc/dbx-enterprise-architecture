"""The Connected systems page (initiative 26): everyone reads the list; only an admin connects or disconnects."""

from __future__ import annotations

from ea.models import ConnectedSystem
from ea.services.roles import use_role
from ea.ui.pages.systems import render, system_from_form, system_list


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
