"""Users and roles (initiative 28, decision 0028): roles granted to workspace groups in the application.

A person's role is the highest that the deployment's grants (`EA_ROLE_GROUPS`, matched by a
group's name) or a grant kept in the store (matched by the workspace's identifier for the
group) gives them; a person no grant reaches is a Reader. An admin grants and removes, and
cannot lock the application out by accident: not their own Admin, not the last admin grant,
and never Admin to every person in the workspace. Every change is in the change log, filed
under no organisation.
"""

from __future__ import annotations

import logging

import pytest

from ea.backend.organisations import NO_ORG, use_org, validate_org_id
from ea.backend.sql import schema_of
from ea.config import Settings
from ea.models import Forbidden, GroupRef, NotFoundError, RoleGrant
from ea.services import HealthService, OrganisationService
from ea.services.access import AccessService, in_words
from ea.services.identity import DirectoryUnavailable, SampleDirectory
from ea.services.roles import allowed, use_role

ARCHITECTS = GroupRef(name="solution-architects", id="g-arch")
ADMINS = GroupRef(name="ea-admins", id="g-admins")
PLATFORM = GroupRef(name="platform-team", id="g-plat")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def service(backend, role_groups: str = "", **kw) -> AccessService:
    directory = kw.pop("directory", None) or SampleDirectory()
    settings = kw.pop("settings", None) or Settings(role_groups=role_groups)
    return AccessService(backend, settings, directory, **kw)


def grant(svc: AccessService, ref: GroupRef, role: str, actor: str = "ada", **kw) -> RoleGrant:
    with use_role("admin"):
        return svc.grant(ref.id, ref.name, role, kw.pop("note", ""), kw.pop("checked", True), actor, **kw)


# --------------------------------------------------------------------- the role a request is given
def test_the_highest_of_the_deployment_s_and_the_store_s_grants_wins(backend):
    svc = service(backend, "reviewer=ea-reviewers;admin=platform-admins")
    grant(svc, ARCHITECTS, "architect", note="they design the solutions")
    role, reasons = svc.resolve([GroupRef("ea-reviewers", "g-rev"), ARCHITECTS])
    assert role == "architect"
    assert (reasons[0].group, reasons[0].source, reasons[0].granted_by) == (
        "solution-architects",
        "grant",
        "ada",
    )
    assert [r.role for r in reasons] == ["architect", "reviewer"], "every reason, the highest first"
    assert svc.resolve([GroupRef("ea-reviewers")])[0] == "reviewer", "the deployment's, by name"
    assert svc.resolve([GroupRef("EA-Reviewers")])[0] == "reviewer", "whatever the case"
    assert svc.resolve([GroupRef("platform-admins", "g-9"), ARCHITECTS])[0] == "admin"
    assert svc.resolve([]) == ("reader", [])
    assert svc.resolve([GroupRef("staff", "g-staff")]) == ("reader", [])
    assert svc.resolve(["ea-reviewers"])[0] == "reviewer", "a plain name is a group known by name only"


def test_a_stored_grant_follows_its_group_by_identifier_never_by_name(backend):
    """A renamed group keeps its role; a new group given the old name does not inherit it."""
    svc = service(backend)
    grant(svc, ARCHITECTS, "architect")
    assert svc.resolve([GroupRef("renamed-architects", "g-arch")])[0] == "architect"
    assert svc.resolve([GroupRef("solution-architects", "g-other")])[0] == "reader"
    assert svc.resolve([GroupRef("solution-architects")])[0] == "reader", "no identifier, no match"


def test_a_grant_not_checked_is_matched_by_its_exact_name_until_it_is_picked(backend):
    """Where the directory could not be searched an exact name is granted, marked not checked."""
    svc = service(backend)
    with use_role("admin"):
        svc.grant("Data Team", "Data Team", "reviewer", "", False, "ada")
    assert svc.resolve([GroupRef("data team", "g-data")])[0] == "reviewer"
    assert svc.resolve([GroupRef("data team two", "g-data-2")])[0] == "reader"
    # a later search finds the group: granting it from the list replaces the typed name
    grant(svc, GroupRef("Data Team", "g-data"), "architect")
    held = backend.list_role_grants()
    assert [(g.group_id, g.checked, g.role) for g in held] == [("g-data", True, "architect")]


def test_a_stored_role_outside_the_three_gives_nothing(backend):
    backend.set_role_grant(RoleGrant("g-x", "bots", role="agent"), "someone")
    backend.set_role_grant(RoleGrant("g-y", "owners", role="owner"), "someone")
    svc = service(backend, "agent=bots;reader=ea-admins")
    assert svc.resolve([GroupRef("bots", "g-x"), GroupRef("owners", "g-y")]) == ("reader", [])
    assert svc.resolve([GroupRef("ea-admins")]) == ("reader", [])


def test_the_grants_are_kept_a_minute_and_forgotten_at_once_by_the_process_that_writes(backend, monkeypatch):
    clock = Clock()
    writer, other = service(backend, clock=clock), service(backend, clock=clock)
    reads = []
    real = backend.list_role_grants

    def counted(lock=False):
        reads.append(lock)
        return real(lock)

    monkeypatch.setattr(backend, "list_role_grants", counted)
    assert other.resolve([ARCHITECTS])[0] == "reader"
    for _ in range(5):
        other.resolve([ARCHITECTS])
    assert reads == [False], "one read a minute, however many requests"
    grant(writer, ARCHITECTS, "architect")
    assert writer.resolve([ARCHITECTS])[0] == "architect", "the writer forgot what it kept"
    assert other.resolve([ARCHITECTS])[0] == "reader", "another process within its minute"
    clock.now = 61
    assert other.resolve([ARCHITECTS])[0] == "architect", "and within a minute it is felt"


def test_a_read_overtaken_by_a_write_is_not_kept(backend, monkeypatch):
    """A request that read the grants just before this process changed one must not put the old
    grants back for a minute after the writer forgot them."""
    svc = service(backend)
    real = backend.list_role_grants
    reads = []

    def overtaken(lock=False):
        held = real(lock)
        reads.append(1)
        if len(reads) == 1:
            grant(svc, ARCHITECTS, "architect")  # a write lands while the first read is in flight
        return held

    monkeypatch.setattr(backend, "list_role_grants", overtaken)
    assert svc.resolve([ARCHITECTS])[0] == "reader", "the read answers for what it read"
    assert svc.resolve([ARCHITECTS])[0] == "architect", "and what it read was not kept"


def test_a_store_that_cannot_be_read_leaves_the_deployment_s_grants_standing(backend, monkeypatch, caplog):
    """Never everyone a Reader because the store hiccupped: the deployment's admin group is the way in."""
    svc = service(backend, "admin=ea-admins")

    def down(lock=False):
        raise RuntimeError("the store is not answering")

    monkeypatch.setattr(backend, "list_role_grants", down)
    with caplog.at_level(logging.WARNING):
        assert svc.resolve([GroupRef("ea-admins")])[0] == "admin"
        assert svc.resolve([ARCHITECTS])[0] == "reader"
    assert "could not read the role grants" in caplog.text


# ------------------------------------------------------------------------- what an admin may not do
def test_only_the_three_roles_are_granted(backend):
    svc = service(backend)
    for role in ("reader", "agent", "owner", ""):
        with pytest.raises(ValueError, match="not a role a grant gives"):
            grant(svc, ARCHITECTS, role)
    with pytest.raises(ValueError, match="name the workspace group"):
        grant(svc, GroupRef("", ""), "architect")
    assert backend.list_role_grants() == []


def test_the_workspace_s_all_users_group_is_never_made_admin(backend):
    svc = service(backend)
    for name in ("users", "Account Users"):
        with pytest.raises(Forbidden, match="every person in the workspace"):
            grant(svc, GroupRef(name, f"g-{name}"), "admin")
        with pytest.raises(Forbidden, match="every person in the workspace"):
            grant(svc, GroupRef(name, name), "admin", checked=False)
    grant(svc, GroupRef("users", "g-users"), "reviewer")  # another role is the admin's to give
    assert [g.role for g in backend.list_role_grants()] == ["reviewer"]


def test_an_admin_cannot_remove_or_lower_the_grant_their_own_admin_rests_on(backend):
    svc = service(backend)
    grant(svc, ADMINS, "admin")
    grant(svc, PLATFORM, "admin")  # a second admin grant: the last-admin rule is not what refuses
    with use_role("admin"):
        with pytest.raises(Forbidden, match="their own Admin"):
            svc.revoke(ADMINS.id, "ada", acting=[ADMINS])
        with pytest.raises(Forbidden, match="their own Admin"):
            svc.grant(ADMINS.id, ADMINS.name, "architect", "", True, "ada", acting=[ADMINS])
        # another admin may, and so may one whose Admin also rests on another grant
        svc.revoke(ADMINS.id, "pat", acting=[PLATFORM])
        grant(svc, ADMINS, "admin")
        svc.revoke(ADMINS.id, "ada", acting=[ADMINS, PLATFORM])
    assert [g.group_id for g in backend.list_role_grants()] == [PLATFORM.id]
    # an admin whose Admin the deployment gives may change the store's grants to their groups
    deployed = service(backend, "admin=ea-admins")
    grant(deployed, ADMINS, "admin")
    with use_role("admin"):
        deployed.revoke(ADMINS.id, "ada", acting=[ADMINS])


def test_the_last_admin_grant_stays_unless_the_deployment_names_an_admin_group(backend):
    svc = service(backend)
    grant(svc, ADMINS, "admin")
    with use_role("admin"):
        with pytest.raises(Forbidden, match="last admin grant"):
            svc.revoke(ADMINS.id, "cli")  # the command line acts with no groups of its own
        with pytest.raises(Forbidden, match="last admin grant"):
            svc.grant(ADMINS.id, ADMINS.name, "reviewer", "", True, "cli")
        with pytest.raises(NotFoundError):
            svc.revoke("g-nobody", "cli")
    deployed = service(backend, "admin=platform-admins")
    with use_role("admin"):
        deployed.revoke(ADMINS.id, "cli")
    assert backend.list_role_grants() == []


def test_the_lockout_check_reads_the_grants_afresh_under_the_store_s_lock(backend, monkeypatch):
    """A minute-old copy could let two changes each think another admin grant remains."""
    svc = service(backend)
    grant(svc, ADMINS, "admin")
    grant(svc, PLATFORM, "admin")
    svc.resolve([ADMINS])  # two admin grants are now kept for a minute
    backend.delete_role_grant(PLATFORM.id, "elsewhere")  # one removed by another process
    locked = []
    real = backend.list_role_grants

    def watched(lock=False):
        locked.append(lock)
        return real(lock)

    monkeypatch.setattr(backend, "list_role_grants", watched)
    with use_role("admin"), pytest.raises(Forbidden, match="last admin grant"):
        svc.revoke(ADMINS.id, "cli")
    assert locked == [True]


def test_only_an_admin_reads_or_changes_the_grants(backend):
    svc = service(backend)
    grant(svc, ARCHITECTS, "architect")
    assert allowed("grant_roles", "admin")
    for role in ("reader", "reviewer", "architect", "agent"):
        assert not allowed("grant_roles", role)
        with use_role(role):
            for attempt in (
                lambda: svc.grant(ADMINS.id, ADMINS.name, "admin", "", True, "x"),
                lambda: svc.revoke(ARCHITECTS.id, "x"),
                svc.grants,
                svc.history,
                lambda: svc.search("ea"),
                lambda: svc.check_person("admin@example.edu"),
                lambda: svc.find("solution-architects"),
            ):
                with pytest.raises(Forbidden):
                    attempt()
            assert svc.my_role([ARCHITECTS])[0] == "architect", "a person always reads their own"
    assert [g.role for g in backend.list_role_grants()] == ["architect"]


def test_a_local_persona_never_writes_grants_into_the_platform_s_store(backend):
    """Locally the debug persona is the role (decision 0008): one pointed at the platform's store
    must not grant there. The command line, and the app where the platform signs people in, may."""
    web = service(backend, settings=Settings(auth="mock"), web=True)
    if backend.engine == "lakebase":
        with pytest.raises(Forbidden, match="debug persona"):
            grant(web, ARCHITECTS, "architect")
    else:
        grant(web, ARCHITECTS, "architect")
    signed_in = service(backend, settings=Settings(auth="databricks"), web=True)
    grant(signed_in, ARCHITECTS, "reviewer")
    command_line = service(backend, settings=Settings(auth="mock"))
    with use_role("admin"):
        command_line.revoke(ARCHITECTS.id, "cli")
    assert backend.list_role_grants() == []


# ------------------------------------------------------------------------------------- the record
def test_every_change_is_logged_under_no_organisation(backend, registry):
    with pytest.raises(ValueError):
        validate_org_id(NO_ORG)  # no organisation can ever be given it
    activity = HealthService(backend, registry).activity()
    svc = service(backend)
    grant(svc, ARCHITECTS, "reviewer", note="they review")
    grant(svc, ARCHITECTS, "architect", actor="bea")
    with use_role("admin"):
        svc.revoke(ARCHITECTS.id, "cy")
        changes = svc.history()
    assert [(c.op, c.actor, c.group, c.role) for c in changes] == [
        ("revoke", "cy", "solution-architects", "architect"),
        ("change", "bea", "solution-architects", "architect"),
        ("grant", "ada", "solution-architects", "reviewer"),
    ]
    assert changes[1].was == "reviewer" and changes[2].note == "they review"
    assert [c for c in backend.history(None, 100) if c["entity_kind"] == "role_grant"] == []
    assert HealthService(backend, registry).activity() == activity, "no organisation's activity counts them"
    filed = backend.query(
        "select distinct org_id from change_log where entity_kind = 'role_grant'", scoped=False
    )
    assert list(filed["org_id"]) == [NO_ORG]


def test_the_grants_belong_to_the_application_not_to_an_organisation(backend):
    """A role holds in every organisation; copying or deleting one neither takes nor leaves a grant."""
    orgs = OrganisationService(backend)
    svc = service(backend)
    grant(svc, ARCHITECTS, "architect")
    with use_role("admin"):
        orgs.create("Trial", "ada", copy_from="default")
    with use_org("trial"):
        assert svc.resolve([ARCHITECTS])[0] == "architect"
        assert [c for c in backend.history(None, 100) if c["entity_kind"] == "role_grant"] == []
        with use_role("admin"):
            assert len(svc.history()) == 1
    with use_role("admin"):
        orgs.delete("trial", "ada")
        assert len(svc.history()) == 1
    assert [g.group_id for g in backend.list_role_grants()] == [ARCHITECTS.id]


def test_a_reader_s_own_sql_never_sees_the_grants(backend):
    backend.set_role_grant(RoleGrant(ARCHITECTS.id, ARCHITECTS.name, "architect"), "ada")
    assert int(backend.query("select count(*) as n from role_grant")["n"][0]) == 0
    assert int(backend.query("with g as (select * from role_grant) select count(*) as n from g")["n"][0]) == 0
    assert (
        int(backend.query("select count(*) as n from change_log where entity_kind = 'role_grant'")["n"][0])
        == 0
    )
    where = schema_of("role_grant", backend.schema_prefix)
    with pytest.raises(ValueError, match="name the table on its own"):
        backend.query(f"select * from {where}.role_grant")
    assert int(backend.query("select count(*) as n from role_grant", scoped=False)["n"][0]) == 1


# ------------------------------------------------------------------------------ the store itself
def test_a_grant_is_one_row_per_group_rewritten_when_its_role_changes(backend):
    first = backend.set_role_grant(RoleGrant("g-1", "one", "reviewer", note="first", checked=False), "ada")
    assert first.granted_by == "ada" and first.granted_at is not None
    backend.set_role_grant(RoleGrant("g-1", "one", "admin", note="second"), "bea")
    backend.set_role_grant(RoleGrant("g-0", "zero", "architect"), "bea")
    held = backend.list_role_grants()  # by the group's name
    assert [(g.group_id, g.role, g.note, g.checked, g.granted_by) for g in held] == [
        ("g-1", "admin", "second", True, "bea"),
        ("g-0", "architect", "", True, "bea"),
    ]
    assert backend.delete_role_grant("g-1", "cy").role == "admin"
    assert backend.delete_role_grant("g-1", "cy") is None
    assert [g.group_id for g in backend.list_role_grants()] == ["g-0"]
    logged = backend.role_grant_history(10)
    assert [(e["op"], e["actor"]) for e in logged] == [
        ("revoke", "cy"),
        ("grant", "bea"),
        ("change", "bea"),
        ("grant", "ada"),
    ]
    assert len(backend.role_grant_history(2)) == 2


def test_an_older_store_gains_the_grants_table_on_its_next_start(backend):
    backend._execute("DROP TABLE role_grant")
    backend.init_schema()
    assert backend.list_role_grants() == []
    backend.set_role_grant(RoleGrant("g-1", "one", "reviewer"), "ada")
    assert len(backend.list_role_grants()) == 1


# ---------------------------------------------------------------------------- the directory's part
def test_a_person_is_checked_against_the_grants_as_the_platform_would_apply_them(backend):
    svc = service(backend, "reviewer=ea-reviewers")
    grant(svc, GroupRef("solution-architects", "sample-solution-architects"), "architect")
    with use_role("admin"):
        arjun = svc.check_person("architect@example.edu")
        rae = svc.check_person(" Reviewer@Example.edu ")
        ren = svc.check_person("reader@example.edu")
        nobody = svc.check_person("nobody@example.edu")
    assert arjun.found and arjun.role == "architect"
    assert (
        in_words(arjun.role, arjun.reasons)
        == "Architect — from the group solution-architects (granted by ada)"
    )
    assert in_words(rae.role, rae.reasons) == "Reviewer — from the group ea-reviewers (set by the deployment)"
    assert in_words(ren.role, ren.reasons) == "Reader — none of their groups holds a role"
    assert not nobody.found and "nobody@example.edu" in nobody.problem


def test_the_directory_is_searched_for_an_admin_and_says_when_it_cannot_be(backend):
    svc = service(backend)
    with use_role("admin"):
        found, problem = svc.search("arch")
        assert [g.name for g in found] == ["ea-architects", "solution-architects"] and problem == ""
        assert svc.search("a") == ([], ""), "two letters at least"

    class Down(SampleDirectory):
        def search_groups(self, text):
            raise DirectoryUnavailable("the workspace did not answer (Timeout)")

        def person_groups(self, email):
            raise DirectoryUnavailable("the workspace did not answer (Timeout)")

    down = service(backend, directory=Down())
    with use_role("admin"):
        found, problem = down.search("arch")
        assert found == [] and problem.startswith("the workspace's groups cannot be searched")
        checked = down.check_person("architect@example.edu")
        assert not checked.found and checked.problem.startswith("the workspace's groups cannot be searched")


def test_the_grants_list_puts_the_deployment_first_and_marks_what_needs_a_look(backend):
    svc = service(backend, "admin=ea-admins;reviewer=ea-reviewers")
    grant(svc, GroupRef("solution-architects", "sample-solution-architects"), "architect", note="design")
    grant(svc, GroupRef("gone-team", "sample-gone"), "reviewer")
    grant(svc, GroupRef("renamed", "sample-data-team"), "reviewer")
    with use_role("admin"):
        svc.grant("Typed Team", "Typed Team", "reviewer", "", False, "ada")
        rows, problem = svc.grants()
    assert problem == ""
    assert [(r.source, r.group, r.role) for r in rows[:2]] == [
        ("deployment", "ea-admins", "admin"),
        ("deployment", "ea-reviewers", "reviewer"),
    ]
    by_group = {r.group: r for r in rows[2:]}
    assert (
        by_group["solution-architects"].note == "design"
        and by_group["solution-architects"].granted_by == "ada"
    )
    assert by_group["gone-team"].missing and not by_group["solution-architects"].missing
    assert by_group["renamed"].now_called == "data-team"
    assert not by_group["Typed Team"].checked and not by_group["Typed Team"].missing
    with use_role("admin"):
        assert svc.find("typed team").group_id == "Typed Team"
        assert svc.find("SOLUTION-ARCHITECTS").group_id == "sample-solution-architects"
        assert svc.find("sample-gone").group_name == "gone-team"
        assert svc.find("nobody") is None
