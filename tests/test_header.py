"""What the header says of the metamodel: the version, and the pack only where there is a choice.

The header carries the organisation, the branch and the version on one line, and the
organisation's name is the one a reader cannot abbreviate. Repeating a single pack's id
beside its version costs that width and says nothing the version selector does not.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.conftest import a_pack_id

from ea.backend.organisations import DEFAULT_ORG
from ea.config import Settings
from ea.ui.context import AppContext


@pytest.fixture
def ctx(loaded):
    return AppContext(Settings(), loaded)


def test_one_pack_in_the_store_is_named_by_its_version_alone(ctx):
    assert ctx.registry.pack.status == "published"
    assert ctx.pack_label() == ctx.registry.pack.version


def test_a_version_that_is_not_published_says_so(ctx, loaded):
    draft = replace(ctx.registry.pack, version="2026-09-20", status="draft")
    loaded.save_pack(draft, "ada")
    ctx.orgs.apply(DEFAULT_ORG, draft.ref, "ada", force=True)
    ctx.reload_registry()
    assert ctx.pack_label() == "2026-09-20 · draft"


def test_a_second_pack_in_the_store_brings_the_pack_name_back(ctx, loaded):
    """With one metamodel the header need not name it; with two it must, and by NAME.

    Never by identifier: it is opaque (decision 0021), so in the header it would be a string
    a reader cannot act on, in the width the organisation's own name needs.
    """
    second = replace(ctx.registry.pack, id=a_pack_id("second-framework"), name="Second Framework")
    loaded.save_pack(second, "ada")
    assert ctx.pack_label() == f"{ctx.registry.pack.name} · {ctx.registry.pack.version}"
    assert ctx.registry.pack.id not in ctx.pack_label()
