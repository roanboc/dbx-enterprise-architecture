"""The platform forwards a user and no groups; the groups come from the workspace and decide the role."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace as NS

import pytest

from ea.config import Settings
from ea.models import GroupRef, RoleGrant
from ea.services.identity import (
    SEARCH_LIMIT,
    DirectoryUnavailable,
    SampleDirectory,
    WorkspaceDirectory,
    WorkspaceGroups,
    directory_for,
    forwarded_identity,
    lookup_workspace_groups,
)
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


def test_the_role_on_the_platform_comes_from_the_workspace_groups(backend):
    ctx = AppContext(
        Settings(
            auth="databricks", role_groups="admin=ea-admins;architect=ea-architects;reviewer=ea-reviewers"
        ),
        backend,
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


# --------------------------------------------------------------- group identifiers (initiative 28)
def test_a_lookup_carries_each_group_s_identifier_and_a_plain_name_is_a_name_alone():
    groups = WorkspaceGroups(lambda u, t: [GroupRef("ea-architects", "g1"), GroupRef("everyone", "g0")])
    assert groups.groups("ada@example.edu") == ["ea-architects", "everyone"], "callers of names keep them"
    assert groups.refs("ada@example.edu") == [GroupRef("ea-architects", "g1"), GroupRef("everyone", "g0")]
    names = WorkspaceGroups(lambda u, t: ["ea-architects"])
    assert names.refs("ada@example.edu") == [GroupRef("ea-architects", "")]
    assert names.refs("") == []


def _fake_sdk(monkeypatch, client):
    """A `databricks.sdk` whose WorkspaceClient is the one given, whether the SDK is installed or not."""
    sdk = types.ModuleType("databricks.sdk")
    sdk.WorkspaceClient = lambda *a, **kw: client
    config = types.ModuleType("databricks.sdk.config")
    config.Config = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "databricks", types.ModuleType("databricks"))
    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", config)


def test_the_workspace_lookup_reads_each_group_s_identifier(monkeypatch):
    """/Me and a user's record carry a group as its display name and its id (`value`)."""
    groups = [
        NS(display="ea-architects", value="123"),
        NS(display=None, value="9"),
        NS(display="all", value="7"),
    ]
    asked = {}

    def users_list(**kw):
        asked.update(kw)
        return iter([NS(user_name="ada@example.edu", groups=groups)])

    _fake_sdk(monkeypatch, NS(current_user=NS(me=lambda: NS(groups=groups)), users=NS(list=users_list)))
    expected = [GroupRef("all", "7"), GroupRef("ea-architects", "123")]
    assert lookup_workspace_groups("ada@example.edu", "tok") == expected
    assert lookup_workspace_groups("ada@example.edu", None) == expected
    assert asked["attributes"] == "id,userName,groups" and asked["filter"] == 'userName eq "ada@example.edu"'


class _Groups:
    """The workspace's groups API as the directory reads it, keeping what it was asked."""

    def __init__(self, names, fail=None):
        self.held = [NS(id=f"id-{n}", display_name=n) for n in names]
        self.asked: list[dict] = []
        self.fail = fail

    def list(self, **kw):
        self.asked.append(kw)
        if self.fail:
            raise self.fail
        text = kw["filter"]
        if text.startswith("displayName co"):
            wanted = text.split('"')[1].lower()
            return iter(g for g in self.held if wanted in g.display_name.lower())
        wanted_ids = set(text.split('"')[1::2])
        return iter(g for g in self.held if g.id in wanted_ids)


def test_the_directory_searches_the_workspace_s_groups_quickly_and_keeps_an_answer_a_minute():
    api = _Groups(["ea-architects", "solution-architects", "data-team"] + [f"arch-{i}" for i in range(40)])
    clock = [0.0]
    made = []

    def client():
        made.append(1)
        return NS(groups=api)

    directory = WorkspaceDirectory(client, clock=lambda: clock[0])
    found = directory.search_groups('  Arch"\\  ')
    assert len(found) == SEARCH_LIMIT == 20, "a page of twenty, never the whole directory"
    assert api.asked[0] == {"filter": 'displayName co "Arch"', "attributes": "id,displayName", "count": 20}
    assert directory.search_groups("a") == [] and len(api.asked) == 1, "two letters at least"
    directory.search_groups("arch")
    assert len(api.asked) == 1, "the same search within a minute is not asked again"
    clock[0] = 61
    directory.search_groups("Arch")
    assert len(api.asked) == 2
    assert directory.groups_by_id(["id-data-team", "id-gone"]) == {"id-data-team": "data-team"}
    assert len(made) == 1, "one client for the directory's life"


def test_a_directory_that_cannot_be_reached_says_so_and_raises_nothing_else():
    down = WorkspaceDirectory(lambda: NS(groups=_Groups([], fail=TimeoutError("slow"))))
    with pytest.raises(DirectoryUnavailable, match="did not answer"):
        down.search_groups("arch")

    def unconfigured():
        raise ValueError("default auth: cannot configure default credentials")

    with pytest.raises(DirectoryUnavailable, match="no Databricks workspace is configured"):
        WorkspaceDirectory(unconfigured).search_groups("arch")

    def no_sdk():
        raise ImportError("No module named 'databricks'")

    with pytest.raises(DirectoryUnavailable, match="SDK is not installed"):
        WorkspaceDirectory(no_sdk).person_groups("ada@example.edu")


def test_the_directory_reads_a_person_s_groups_as_the_application():
    asked = {}

    def users_list(**kw):
        asked.update(kw)
        if "ada" not in kw["filter"]:
            return iter([])
        return iter([NS(user_name="ada@example.edu", groups=[NS(display="ea-admins", value="42")])])

    directory = WorkspaceDirectory(lambda: NS(users=NS(list=users_list)))
    assert directory.person_groups('ada@example.edu"') == [GroupRef("ea-admins", "42")]
    assert asked == {"filter": 'userName eq "ada@example.edu"', "attributes": "id,userName,groups"}
    assert directory.person_groups("ren@example.edu") is None, "nobody signs in by that name"


def test_locally_the_directory_is_the_sample_groups_and_the_personas_memberships():
    assert isinstance(directory_for(Settings(auth="mock")), SampleDirectory)
    assert isinstance(directory_for(Settings(auth="databricks")), WorkspaceDirectory)
    sample = SampleDirectory()
    assert [g.name for g in sample.search_groups("ea-")] == ["ea-admins", "ea-architects", "ea-reviewers"]
    assert [g.name for g in sample.person_groups("Admin@Example.edu")] == ["ea-admins", "users"]
    assert "users" in [g.name for g in sample.search_groups("users")]
    assert sample.person_groups("nobody@example.edu") is None


def test_the_role_on_the_platform_comes_from_the_store_s_grants_too(backend):
    """A grant kept in the store reaches a signed-in person through the identifier of their group."""
    ctx = AppContext(Settings(auth="databricks", role_groups="reviewer=ea-reviewers"), backend)
    backend.set_role_grant(RoleGrant("g-sa", "solution-architects", "architect"), "ada")
    ctx.identity = WorkspaceGroups(
        lambda u, t: [GroupRef("solution-architects", "g-sa"), GroupRef("ea-reviewers", "g-rev")]
    )
    user = ctx.user_from_headers({"X-Forwarded-Email": "arjun@example.edu"})
    assert (user.role, user.groups) == ("architect", ["ea-reviewers", "solution-architects"])
    ctx.identity = WorkspaceGroups(lambda u, t: [GroupRef("solution-architects", "g-new")])
    assert ctx.user_from_headers({"X-Forwarded-Email": "sam@example.edu"}).role == "reader"


def test_behind_a_trusted_proxy_a_group_picked_from_the_directory_reaches_its_people(backend):
    """The proxy's groups header carries names alone: a grant picked from the directory, kept by
    its identifier, is matched there by the name it was granted under."""
    ctx = AppContext(Settings(auth="databricks", trust_groups_header=True), backend)
    backend.set_role_grant(RoleGrant("g-arch-id", "solution-architects", "architect"), "ada")
    ctx.identity = WorkspaceGroups(lambda u, t: [])  # never asked: the header names the groups
    user = ctx.user_from_headers(
        {"X-Forwarded-Email": "arjun@example.edu", "X-Forwarded-Groups": "data-team, Solution-Architects"}
    )
    assert user.role == "architect"
    other = ctx.user_from_headers({"X-Forwarded-Email": "sam@example.edu", "X-Forwarded-Groups": "data-team"})
    assert other.role == "reader"
