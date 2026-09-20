"""The Organisations page: what the compatibility verdict tells the architect.

Applying a metamodel version to an organisation is the gate the whole versioning idea
rests on, so the clean verdict has to say as much as the unhappy one: what was checked,
not only that nothing broke.
"""

from __future__ import annotations

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
        org_id="q-sandbox", pack_id="higher_education", version="2026-09-20", elements=47, relationships=99
    )
    said = _texts(report_view(report, applied=True))
    assert "Applied." in said
    assert "47 elements and 99 relationships checked" in said
    assert "nothing would be left invalid" in said


def test_a_verdict_with_findings_is_the_report_s_own_summary():
    report = CompatibilityReport(
        org_id="q-sandbox",
        pack_id="higher_education",
        version="2026-09-20",
        elements=47,
        relationships=99,
        issues=[Issue(level="error", code="unknown_type", message="no such type", entity="PAC-CMS")],
    )
    said = _texts(report_view(report, applied=False))
    assert report.summary() in said
    assert "Applied." not in said
