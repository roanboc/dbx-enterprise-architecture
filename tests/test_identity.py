"""The platform forwards a user and no groups; the groups come from the workspace and decide the role."""

from __future__ import annotations

from ea.config import Settings
from ea.metamodel import Registry
from ea.services.identity import WorkspaceGroups, forwarded_identity
from ea.ui.context import AppContext


def test_the_forwarded_headers_are_read_as_the_platform_sends_them():
    headers = {"X-Forwarded-Email": " ada@example.edu ", "X-Forwarded-Access-Token": "tok"}
    assert forwarded_identity(headers) == ("ada@example.edu", None, "tok")
    assert forwarded_identity({"X-Forwarded-Preferred-Username": "ada"}) == ("ada", None, None)
    assert forwarded_identity({"X-Forwarded-Email": "a@b", "X-Forwarded-Groups": "x, y,"}) == (
        "a@b",
        ["x", "y"],
        None,
    )
    assert forwarded_identity({}) == ("", None, None)


def test_groups_are_looked_up_once_per_user_and_kept_for_a_while():
    calls = []

    def lookup(username, token):
        calls.append((username, token))
        return ["ea-architects", "everyone"]

    clock = [0.0]
    groups = WorkspaceGroups(lookup, ttl=300, clock=lambda: clock[0])
    assert groups.groups("ada@example.edu", "tok") == ["ea-architects", "everyone"]
    assert groups.groups("ada@example.edu", "tok") == ["ea-architects", "everyone"]
    assert calls == [("ada@example.edu", "tok")]
    clock[0] = 301
    groups.groups("ada@example.edu", None)
    assert len(calls) == 2 and calls[1] == ("ada@example.edu", None)
    groups.forget("ada@example.edu")
    groups.groups("ada@example.edu", None)
    assert len(calls) == 3
    assert groups.groups("", None) == [] and len(calls) == 3


def test_a_directory_that_fails_makes_a_reader_not_an_error():
    def lookup(username, token):
        raise RuntimeError("SCIM is down")

    groups = WorkspaceGroups(lookup)
    assert groups.groups("ada@example.edu") == []


def test_the_role_on_the_platform_comes_from_the_workspace_groups(backend, pack):
    ctx = AppContext(
        Settings(
            auth="databricks", role_groups="admin=ea-admins;architect=ea-architects;reviewer=ea-reviewers"
        ),
        backend,
        Registry(pack),
    )
    ctx.identity = WorkspaceGroups(lambda u, t: ["ea-architects"] if u == "arjun@example.edu" else [])
    user = ctx.user_from_headers({"X-Forwarded-Email": "arjun@example.edu", "X-Forwarded-Access-Token": "t"})
    assert (user.username, user.role, user.groups) == ("arjun@example.edu", "architect", ["ea-architects"])
    nobody = ctx.user_from_headers({"X-Forwarded-Email": "ren@example.edu"})
    assert nobody.role == "reader" and nobody.groups == []
    anonymous = ctx.user_from_headers({})
    assert (anonymous.username, anonymous.role) == ("anonymous", "reader")
    # a proxy that forwards groups is believed without a lookup
    proxied = ctx.user_from_headers(
        {"X-Forwarded-Email": "rae@example.edu", "X-Forwarded-Groups": "ea-reviewers"}
    )
    assert proxied.role == "reviewer"
    assert ctx.debug_personas() is False
