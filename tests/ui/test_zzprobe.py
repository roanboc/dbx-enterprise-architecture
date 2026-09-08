"""Temporary probe — measurements only, deleted before the module is finished."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.gui


@pytest.mark.scenario(scenario_id="Z01", group="A", title="probe", feature="probe", expected="probe")
def test_probe(ui, record):
    out = {}
    ui.goto("/")
    out["nav_link_html"] = ui.page.locator("#nav-browse").first.inner_html()[:600]
    out["nav_icons"] = ui.page.evaluate(
        """() => Array.from(document.querySelectorAll('.mantine-AppShell-navbar a')).map(a => {
             const spans = Array.from(a.querySelectorAll('span'));
             const masked = spans.filter(s => {
               const cs = getComputedStyle(s);
               return (cs.maskImage && cs.maskImage !== 'none') ||
                      (cs.webkitMaskImage && cs.webkitMaskImage !== 'none');
             });
             return {label: a.innerText.trim(), spans: spans.length, masked: masked.length,
                     mask: masked.length ? getComputedStyle(masked[0]).maskImage.slice(0, 40) : ''};
           })"""
    )
    out["brand_mark_masked"] = ui.page.evaluate(
        """() => {const s = document.querySelector('.ea-brand-mark span');
                  if (!s) return 'no span';
                  const cs = getComputedStyle(s);
                  return (cs.maskImage || cs.webkitMaskImage || 'none').slice(0, 40);}"""
    )
    # the + tooltip
    ui.page.locator("#branch-new-open").first.hover()
    ui.page.wait_for_timeout(900)
    tips = ui.page.locator("[role='tooltip'], .mantine-Tooltip-tooltip")
    out["tooltips"] = [tips.nth(i).inner_text() for i in range(tips.count())]
    out["aria_describedby"] = ui.page.locator("#branch-new-open").first.get_attribute("aria-describedby")
    out["aria_label"] = ui.page.locator("#branch-new-open").first.get_attribute("aria-label")
    out["title_attr"] = ui.page.locator("#branch-new-open").first.get_attribute("title")
    ui.page.mouse.move(1200, 600)
    ui.page.wait_for_timeout(400)
    out["tooltips_after_move"] = ui.page.locator("[role='tooltip'], .mantine-Tooltip-tooltip").count()

    # branch select options, read from the visible listbox only
    ui.page.locator("#branch-select").first.click()
    ui.page.wait_for_timeout(400)
    out["visible_options"] = ui.page.evaluate(
        """() => Array.from(document.querySelectorAll('[role="option"]'))
             .filter(o => o.getBoundingClientRect().width > 0)
             .map(o => o.innerText.slice(0, 40))"""
    )
    ui.page.keyboard.press("Escape")
    ui.settle()

    # element page heading level and what the element route renders
    ui.goto("/browse")
    ids_seen = [r for r in ui.grid_row_ids("browse-grid") if r]
    out["first_row_id"] = ids_seen[0] if ids_seen else ""
    ui.goto(f"/element/{ids_seen[0]}")
    out["el_h1"] = ui.page.locator("#page h1").first.inner_text()
    out["el_url"] = ui.page.url
    out["el_header_ok"] = ui.visible(".mantine-AppShell-header")

    # unknown address marking
    ui.goto("/no-such-page")
    out["unknown_marked"] = ui.page.evaluate(
        """() => Array.from(document.querySelectorAll('.mantine-AppShell-navbar a[href]'))
             .filter(a => a.getAttribute('data-active') !== null).map(a => a.id)"""
    )
    ui.goto("/")
    print("PROBE " + json.dumps(out, indent=1, default=str))
    ui.check("probe ran", True)
