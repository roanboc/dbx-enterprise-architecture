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
    assert forwarded_identity({}) == ("", None, None)


def test_a_groups_header_counts_only_where_the_deployment_trusts_it():
    """The platform passes a client's headers through: a believed groups header would let a
    signed-in Reader name their own role, so it is off unless a proxy of ours is declared."""
    headers = {"X-Forwarded-Email": "a@b", "X-Forwarded-Groups": "ea-admins, y,"}
    assert forwarded_identity(headers) == ("a@b", None, None)
    assert forwarded_identity(headers, trust_groups_header=True) == ("a@b", ["ea-admins", "y"], None)


def test_concurrent_misses_cost_one_directory_call():
    import threading
    import time

    calls = []

    def slow_lookup(username, token):
        calls.append(username)
        time.sleep(0.2)
        return ["ea-architects"]

    groups = WorkspaceGroups(slow_lookup)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(groups.groups("ada@example.edu"))) for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [["ea-architects"]] * 8 and calls == ["ada@example.edu"]


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
    # a groups header the client could have sent is not believed: the workspace decides
    forged = ctx.user_from_headers(
        {"X-Forwarded-Email": "ren@example.edu", "X-Forwarded-Groups": "ea-admins"}
    )
    assert forged.role == "reader"
    ctx.settings.trust_groups_header = True  # only behind a proxy of ours
    proxied = ctx.user_from_headers(
        {"X-Forwarded-Email": "rae@example.edu", "X-Forwarded-Groups": "ea-reviewers"}
    )
    assert proxied.role == "reviewer"
    assert ctx.debug_personas() is False
