"""Every metamodel an admin may manage, not only the one the organisation applies.

The Metamodel page listed the versions the store held, and the store held only what some
organisation had applied: a metamodel the repository ships reached it only by starting a new
organisation on it. The catalogue lists every stored metamodel and every shipped one, and an
admin adds a shipped one to the repository without making an organisation for it.
"""

from __future__ import annotations

import pytest
from tests.test_feeds_page import _texts

from ea.models import Forbidden
from ea.services.roles import use_role


def _shipped(ctx):
    return [e for e in ctx.metamodels.catalogue() if e.shipped is not None]


def test_the_catalogue_lists_the_stored_metamodels_and_the_shipped_ones(app_context):
    entries = app_context.metamodels.catalogue()
    applied = app_context.organisation().pack_id
    held = next(e for e in entries if e.pack_id == applied)
    assert held.versions and app_context.organisation().org_id in held.applied_by
    others = [e for e in entries if e.pack_id != applied]
    assert others, "the repository ships a second metamodel"
    assert all(e.shipped is not None and not e.versions for e in others)
    assert len({e.pack_id for e in entries}) == len(entries)


def test_an_admin_adds_a_shipped_metamodel_without_an_organisation(app_context):
    other = next(e for e in _shipped(app_context) if not e.versions)
    orgs_before = [o.org_id for o in app_context.orgs.list()]
    with use_role("admin"):
        pack = app_context.metamodels.add_shipped(other.pack_id, "ada")
        again = app_context.metamodels.add_shipped(other.pack_id, "ada")
    assert pack.ref == again.ref
    entry = next(e for e in app_context.metamodels.catalogue() if e.pack_id == other.pack_id)
    assert [v.ref for v in entry.versions] == [pack.ref] and entry.applied_by == []
    assert [o.org_id for o in app_context.orgs.list()] == orgs_before


def test_only_an_admin_adds_one(app_context):
    other = _shipped(app_context)[-1]
    with use_role("architect"), pytest.raises(Forbidden):
        app_context.metamodels.add_shipped(other.pack_id, "ada")


def test_the_versions_tab_shows_every_metamodel_and_offers_to_add_a_shipped_one(app_context):
    from ea.ui.pages.metamodel import _metamodels_table

    with use_role("admin"):
        table = _metamodels_table(app_context, app_context.registry.pack.ref)
    said = _texts(table)
    for e in app_context.metamodels.catalogue():
        assert e.name in said
    assert "Add to the repository" in said
