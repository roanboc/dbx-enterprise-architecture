"""The Organisations page: what the compatibility verdict tells the architect.

Applying a metamodel version to an organisation is the gate the whole versioning idea
rests on, so the clean verdict has to say as much as the unhappy one: what was checked,
not only that nothing broke.
"""

from __future__ import annotations

from tests.conftest import HIGHER_ED

from ea.models import CompatibilityReport, Issue
from ea.ui.pages.organisations import report_view


def _texts(component) -> str:
    """Every string anywhere in a rendered component, flattened."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if hasattr(node, "children"):
            walk(node.children)

    walk(component)
    return " ".join(out)


def test_a_clean_verdict_says_how_much_it_checked():
    report = CompatibilityReport(
        org_id="q-sandbox", pack_id=HIGHER_ED, version="2026-09-20", elements=47, relationships=99
    )
    said = _texts(report_view(report, applied=True))
    assert "Applied." in said
    assert "47 elements and 99 relationships checked" in said
    assert "nothing would be left invalid" in said


def test_a_verdict_with_findings_is_the_report_s_own_summary():
    report = CompatibilityReport(
        org_id="q-sandbox",
        pack_id=HIGHER_ED,
        version="2026-09-20",
        elements=47,
        relationships=99,
        issues=[Issue(level="error", code="unknown_type", message="no such type", entity="PAC-CMS")],
    )
    said = _texts(report_view(report, applied=False))
    assert report.summary() in said
    assert "Applied." not in said


# ------------------------------------------------------------------ renaming (ASVC11)


def _buttons(component, action: str) -> list:
    """The row actions of one kind anywhere in a rendered table."""
    out: list = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        if node is None or isinstance(node, (str, int, float)):
            return
        nid = getattr(node, "id", None)
        if isinstance(nid, dict) and nid.get("action") == action:
            out.append(node)
        for attribute in ("children", "leftSection"):
            value = getattr(node, attribute, None)
            if value is not None and not isinstance(value, str):
                walk(value)

    walk(component)
    return out


def test_an_admin_is_offered_to_rename_every_organisation_and_a_reader_is_not(app_context):
    """The model says an admin renames an organisation on this page; the page had no way to."""
    from ea.services.roles import use_role
    from ea.ui.pages.organisations import organisations_table

    with use_role("admin"):
        offered = _buttons(organisations_table(app_context), "rename")
    assert offered and all(not b.disabled for b in offered)
    assert {b.id["org"] for b in offered} == {o.org_id for o in app_context.orgs.list()}
    with use_role("reader"):
        refused = _buttons(organisations_table(app_context), "rename")
    assert refused and all(b.disabled for b in refused)


def test_renaming_changes_the_name_and_keeps_the_identifier(app_context):
    from ea.services.roles import use_role
    from ea.ui.pages.organisations import rename

    default = app_context.orgs.default()
    with use_role("admin"):
        ok, said = rename(app_context, default.org_id, "  Example University  ", "Our architecture")
    assert ok and "Example University" in _texts(said)
    after = app_context.orgs.get(default.org_id)
    assert (after.org_id, after.name, after.description) == (
        default.org_id,
        "Example University",
        "Our architecture",
    )
    assert after.is_default


def test_a_rename_needs_a_name_and_an_admin(app_context):
    from ea.services.roles import use_role
    from ea.ui.pages.organisations import rename

    default = app_context.orgs.default()
    with use_role("admin"):
        ok, said = rename(app_context, default.org_id, "   ", "")
    assert not ok and "needs a name" in _texts(said)
    with use_role("architect"):
        ok, said = rename(app_context, default.org_id, "Somewhere else", "")
    assert not ok and "may not" in _texts(said)
    assert app_context.orgs.get(default.org_id).name == default.name
