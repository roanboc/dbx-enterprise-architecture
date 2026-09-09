"""Roles: what each role may do, derived from groups, enforced in the services."""

from __future__ import annotations

import pytest
from tests.conftest import SAMPLE

from ea.backend.branching import use_branch
from ea.importer import import_directory
from ea.models import Forbidden
from ea.services import BranchService, RepositoryService, use_role
from ea.services.roles import allowed, current_role, parse_role_groups, role_from_groups


def test_roles_from_groups():
    mapping = parse_role_groups(
        "admin=ea-admins, platform-admins; architect=ea-architects;reviewer=ea-reviewers"
    )
    assert mapping == {
        "admin": {"ea-admins", "platform-admins"},
        "architect": {"ea-architects"},
        "reviewer": {"ea-reviewers"},
    }
    assert role_from_groups(["staff"], mapping) == "reader"
    assert role_from_groups(["ea-reviewers"], mapping) == "reviewer"
    assert role_from_groups(["ea-reviewers", "ea-architects"], mapping) == "architect"
    assert role_from_groups(["platform-admins", "ea-architects"], mapping) == "admin"
    assert role_from_groups([], {}) == "reader"


def test_default_role_is_admin_and_the_matrix_is_cumulative():
    assert current_role() == "admin"
    assert allowed("edit_metamodel")
    with use_role("reader"):
        assert allowed("read") and allowed("ask") and not allowed("edit_content") and not allowed("review")
    with use_role("reviewer"):
        assert allowed("review") and not allowed("edit_content") and not allowed("merge")
    with use_role("architect"):
        assert allowed("edit_content") and allowed("merge") and allowed("propose")
        assert not allowed("edit_main") and not allowed("review") and not allowed("merge_without_review")
    with use_role("agent"):
        assert allowed("read") and not allowed("edit_content")
    with pytest.raises(ValueError):
        with use_role("owner"):
            pass


def test_readers_and_reviewers_cannot_write(loaded, registry):
    repo = RepositoryService(loaded, registry)
    branches = BranchService(loaded, registry)
    branches.create("wp-roles", "ana")
    for role in ("reader", "reviewer", "agent"):
        with use_role(role), use_branch("wp-roles"):
            with pytest.raises(Forbidden):
                repo.create_element("capability", "Nope", "x")
            cms = loaded.get_element("PAC-CMS")
            with pytest.raises(Forbidden):
                repo.update_element("PAC-CMS", "x", cms.version, name="No")
            with pytest.raises(Forbidden):
                repo.bulk_update(["PAC-CMS"], "x", {"target_state": "keep"})
            with pytest.raises(Forbidden):
                branches.create("another", "x")
    with use_role("reader"):
        with pytest.raises(Forbidden):
            import_directory(loaded, registry, SAMPLE, "sample")
        report = import_directory(loaded, registry, SAMPLE, "sample", dry_run=True)  # validating is reading
        assert report.ok


def test_architects_write_on_branches_not_on_main(loaded, registry):
    repo = RepositoryService(loaded, registry)
    branches = BranchService(loaded, registry)
    with use_role("architect"):
        with pytest.raises(Forbidden):
            repo.create_element("capability", "On main", "arjun")
        with pytest.raises(Forbidden):
            import_directory(loaded, registry, SAMPLE, "sample")
        b = branches.create("wp-arch", "arjun")
        with use_branch(b.branch_id):
            e = repo.create_element("capability", "On a branch", "arjun")
            assert e.element_id
            assert import_directory(loaded, registry, SAMPLE, "sample").ok
        # an architect may abandon only their own branch
        other = None
        with use_role("admin"):
            other = branches.create("someone-elses", "ada")
        with pytest.raises(Forbidden):
            branches.abandon(other.branch_id, "arjun")
        branches.abandon(b.branch_id, "arjun")
    # an admin writes anywhere
    e = repo.create_element("capability", "On main by admin", "ada")
    assert loaded.get_element(e.element_id) is not None


def test_a_refusal_begins_like_a_sentence():
    """'a Architect may not' is not English; the refusal stands on its own, so it reads as one."""
    from ea.services.roles import require

    with use_role("architect"):
        with pytest.raises(Forbidden, match=r"^An Architect may not assign reviewers"):
            require("assign_reviewers")
    with use_role("reader"):
        with pytest.raises(Forbidden, match=r"^A Reader may not load a file"):
            require("import", what="load a file")
