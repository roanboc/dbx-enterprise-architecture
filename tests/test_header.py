"""What the header says of the metamodel: the version, and the pack only where there is a choice.

The header carries the organisation, the branch and the version on one line, and the
organisation's name is the one a reader cannot abbreviate. Repeating a single pack's id
beside its version costs that width and says nothing the version selector does not.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

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


def test_a_second_pack_in_the_store_brings_the_pack_id_back(ctx, loaded):
    second = replace(ctx.registry.pack, id="second_framework")
    loaded.save_pack(second, "ada")
    assert ctx.pack_label() == f"{ctx.registry.pack.id} · {ctx.registry.pack.version}"
