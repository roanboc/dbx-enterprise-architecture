"""Group P — the screen audit: every screen read against the one usability checklist.

Eleven scenarios, one per screen, each calling the same `audit_screen`. The point of a
fixed list is comparison: two rounds put side by side show a regression in polish as
plainly as a regression in behaviour, and a screen that quietly grows an unlabelled
control is caught the round after it appears.

Seven of the twelve checkpoints are automated here — the navigation marking where the
reader is, heading hierarchy, labelling, disabled-with-a-reason, a card headed with
nothing under it, text contrast, and sideways scroll at 480 px — and with them a badge
whose label is clamped to an ellipsis at either width. The rest (error states, loading,
focus, alignment and terminology) are read from the two screenshots each scenario takes,
or proved by the groups that exercise those paths.

**A scenario in this group fails only when a screen does not load.** Everything the
checklist turns up is lodged as a finding instead, so the audit reports the whole state
of the application in one pass rather than stopping at the first blemish. The checks
recorded against each scenario therefore say what the audit found, not whether the
screen was perfect.
"""

from __future__ import annotations

import re

import pytest
from tests.ui.evidence import Finding

pytestmark = pytest.mark.gui

# The findings this module has already lodged, so a fault shared by eleven screens is
# one row in the report with eleven places, not eleven rows, and its detail is the union
# of what every screen contributed to it.
_LODGED: dict[str, Finding] = {}
_PLACES: dict[str, list[str]] = {}
_DETAILS: dict[str, list[str]] = {}
_ELEMENT_PATH: list[str] = []

MAX_DETAIL = 6  # offenders spelled out in a check detail before it is summarised
MAX_FINDING = 12  # and in a finding, which gathers them from every screen


def _some(items: list[str], limit: int) -> str:
    if len(items) <= limit:
        return "; ".join(items)
    return "; ".join(items[:limit]) + f"; and {len(items) - limit} more"


def _lodge(
    finding: list[Finding],
    key: str,
    where: str,
    severity: str,
    summary: str,
    details: list[str] | None = None,
) -> Finding:
    """Record something worth reporting without failing the scenario that found it."""
    places = _PLACES.setdefault(key, [])
    if where not in places:
        places.append(where)
    shown_where = ", ".join(places[:3]) + (f" and {len(places) - 3} more" if len(places) > 3 else "")
    gathered = _DETAILS.setdefault(key, [])
    for item in details or []:
        if item not in gathered:
            gathered.append(item)
    shown_detail = _some(gathered, MAX_FINDING)
    existing = _LODGED.get(key)
    if existing is not None:
        existing.where, existing.detail = shown_where, shown_detail
        return existing
    found = Finding(
        finding_id=f"P-{len(_LODGED) + 1:02d}",
        where=shown_where,
        severity=severity,
        summary=summary,
        detail=shown_detail,
    )
    _LODGED[key] = found
    finding.append(found)
    return found


# --------------------------------------------------------------------- the browser side

VISIBLE = """
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  };
  const where = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) return s + '#' + el.id;
    const cls = (typeof el.className === 'string' ? el.className : '').trim();
    if (cls) s += '.' + cls.split(/\\s+/).slice(0, 2).join('.');
    return s;
  };
"""

HEADINGS_JS = """
() => Array.from(document.querySelectorAll('#page h1,#page h2,#page h3,#page h4,#page h5,#page h6'))
  .filter(el => el.getClientRects().length > 0 && (el.innerText || '').trim())
  .map(el => ({level: Number(el.tagName.slice(1)), text: (el.innerText || '').trim().slice(0, 48)}))
"""

LABELS_JS = (
    """
() => {
"""
    + VISIBLE
    + """
  const named = (el) => {
    const a = (el.getAttribute('aria-label') || '').trim();
    if (a) return 'aria-label';
    const lb = el.getAttribute('aria-labelledby');
    if (lb && lb.split(/\\s+/).some(id => {
      const n = document.getElementById(id);
      return n && (n.innerText || n.textContent || '').trim();
    })) return 'aria-labelledby';
    if ((el.getAttribute('title') || '').trim()) return 'title';
    if (el.id) {
      const esc = (window.CSS && CSS.escape) ? CSS.escape(el.id) : el.id;
      const l = document.querySelector('label[for="' + esc + '"]');
      if (l && (l.innerText || '').trim()) return 'label';
    }
    const w = el.closest('label');
    if (w && (w.innerText || '').trim()) return 'wrapping label';
    if ((el.innerText || '').trim()) return 'own text';
    const img = el.querySelector('img[alt],svg title');
    if (img && (img.getAttribute('alt') || img.textContent || '').trim()) return 'image alt';
    return '';
  };
  const out = [];
  const seen = new Set();
  document.querySelectorAll(
    'input,select,textarea,button,[role="button"],[role="combobox"],[role="switch"],[role="checkbox"]'
  ).forEach(el => {
    if (el.type === 'hidden' || el.getAttribute('aria-hidden') === 'true') return;
    if (!vis(el)) return;
    if (named(el)) return;
    const key = where(el) + '|' + (el.getAttribute('placeholder') || '');
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      sel: where(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      placeholder: (el.getAttribute('placeholder') || '').slice(0, 42),
    });
  });
  return out;
}
"""
)

DISABLED_JS = (
    """
() => {
"""
    + VISIBLE
    + """
  const out = [];
  // Only a control a reader would try to use. A grid draws disabled wrappers around its
  // own decorations, and those owe nobody an explanation.
  const CONTROLS = 'button,input,select,textarea,a[href],[role="button"],[role="link"],[role="tab"]';
  document.querySelectorAll('[disabled],[aria-disabled="true"],[data-disabled]').forEach(el => {
    if (!el.matches(CONTROLS)) return;
    if (el.getAttribute('data-disabled') === 'false') return;
    if (!vis(el)) return;
    const title = (el.getAttribute('title') || '').trim();
    const db = el.getAttribute('aria-describedby');
    const described = !!(db && db.split(/\\s+/).some(id => {
      const n = document.getElementById(id);
      return n && (n.innerText || '').trim();
    }));
    const own = (el.innerText || '').trim();
    let near = '';
    const p = el.closest('.mantine-InputWrapper-root') || el.parentElement;
    if (p) near = (p.innerText || '').replace(own, '').replace(/\\s+/g, ' ').trim();
    out.push({
      sel: where(el),
      label: own.slice(0, 34) || (el.getAttribute('placeholder') || '').slice(0, 34),
      reason: title || (described ? 'aria-describedby' : ''),
      near: near.slice(0, 70),
    });
  });
  return out;
}
"""
)

CONTRAST_JS = """
() => {
  const parse = (s) => {
    const m = (s || '').match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(/[,\\s\\/]+/).filter(Boolean).map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const lum = (c) => {
    const s = [c.r, c.g, c.b].map(v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2];
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const hex = (c) => '#' + [c.r, c.g, c.b]
    .map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const background = (el) => {
    let node = el, gradient = false, acc = null;
    while (node && node.nodeType === 1) {
      const cs = getComputedStyle(node);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') gradient = true;
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) {
        acc = acc ? over(acc, c) : c;
        if (acc.a >= 0.99) return {colour: acc, gradient};
      }
      node = node.parentElement;
    }
    return {colour: acc && acc.a >= 0.99 ? acc : {r: 255, g: 255, b: 255, a: 1}, gradient};
  };
  const out = [];
  const nodes = document.querySelectorAll('body *');
  for (const el of nodes) {
    if (out.length > 400) break;
    if (el.closest('svg') || el.tagName === 'CANVAS' || el.tagName === 'SCRIPT') continue;
    // An inactive control is exempt (WCAG 1.4.3): reading as unavailable is the point of it.
    if (el.closest('[disabled],[aria-disabled="true"],[data-disabled]')) continue;
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && (n.textContent || '').trim())
      .map(n => n.textContent.trim()).join(' ');
    if (!own) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (Number(cs.opacity) < 0.95) continue;
    const fg = parse(cs.color);
    if (!fg || fg.a === 0) continue;
    const bgInfo = background(el);
    if (bgInfo.gradient) continue;
    const text = fg.a < 1 ? over(fg, bgInfo.colour) : fg;
    const l1 = lum(text), l2 = lum(bgInfo.colour);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(cs.fontSize) || 16;
    const weight = Number(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const floor = large ? 3 : 4.5;
    if (ratio + 0.005 < floor) {
      out.push({
        fg: hex(text),
        bg: hex(bgInfo.colour),
        ratio: Math.round(ratio * 100) / 100,
        floor: floor,
        size: Math.round(size * 10) / 10,
        weight: weight,
        cls: (typeof el.className === 'string' ? el.className : '').split(/\\s+/)[0] || el.tagName,
        text: own.slice(0, 34),
      });
    }
  }
  return out;
}
"""

OVERFLOW_JS = (
    """
() => {
"""
    + VISIBLE
    + """
  const doc = document.documentElement;
  const limit = doc.clientWidth;
  const clipped = (el) => {
    let n = el.parentElement;
    while (n && n !== doc) {
      const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') return true;
      n = n.parentElement;
    }
    return false;
  };
  const over = [];
  document.querySelectorAll('.mantine-AppShell-header *,#page *').forEach(el => {
    if (over.length > 20) return;
    if (!vis(el) || clipped(el)) return;
    const r = el.getBoundingClientRect();
    if (r.right > limit + 2) over.push({sel: where(el), right: Math.round(r.right)});
  });
  return {scroll: doc.scrollWidth, client: limit, over: over};
}
"""
)

EMPTY_CARDS_JS = """
() => {
  const out = [];
  document.querySelectorAll('#page .mantine-Card-root,#page .mantine-Paper-root').forEach(card => {
    if (card.querySelector('.mantine-Card-root,.mantine-Paper-root')) return;
    if (card.getClientRects().length === 0) return;
    const heads = card.querySelectorAll('h1,h2,h3,h4,h5,h6,.ea-section-title');
    if (!heads.length) return;
    let text = (card.innerText || '');
    heads.forEach(h => { text = text.replace((h.innerText || '').trim(), ''); });
    const body = text.replace(/\\s+/g, ' ').trim();
    const rich = card.querySelector(
      'table,canvas,svg,input,select,textarea,button,a,img,.ag-root,.ea-mermaid'
    );
    if (!body && !rich) out.push({heading: (heads[0].innerText || '').trim().slice(0, 44)});
  });
  return out;
}
"""

# A badge label is a name, not a paragraph, and it fails in two ways. Clamped, the name
# is cut to an ellipsis. Unclamped inside a pill that still clips, the same name is cut
# at both ends with no ellipsis at all, which is worse. The measurement that catches both
# is the text's own box against the pill's: a range over the label reports where the
# glyphs actually are, whatever the overflow rules did to the element around them.
CLIPPED_BADGES_JS = """
() => {
  const out = [];
  const range = document.createRange();
  document.querySelectorAll('#page .mantine-Badge-root').forEach(b => {
    if (b.getClientRects().length === 0) return;
    const label = b.querySelector('.mantine-Badge-label') || b;
    const pill = b.getBoundingClientRect();
    range.selectNodeContents(label);
    const text = range.getBoundingClientRect();
    if (text.width === 0) return;
    const clamped = label.scrollWidth > label.clientWidth + 1 || b.scrollWidth > b.clientWidth + 1;
    const spills = text.left < pill.left - 1 || text.right > pill.right + 1;
    if (!clamped && !spills) return;
    const name = (b.innerText || '').trim().slice(0, 26);
    const how = clamped && !spills ? 'cut to an ellipsis' : 'cut off at the edge of its pill';
    const entry = name + ' (' + how + ')';
    if (name && !out.includes(entry)) out.push(entry);
  });
  return out;
}
"""

# What the navigation should mark for each screen, and where the screen is built.
NAV_FOR = {
    "/": "nav-home",
    "/browse": "nav-browse",
    "/ask": "nav-ask",
    "/impact": "nav-impact",
    "/target": "nav-target",
    "/propose": "nav-propose",
    "/import": "nav-import",
    "/branches": "nav-branches",
    "/metamodel": "nav-metamodel",
    "/health": "nav-health",
}
NAV_IDS = sorted(set(NAV_FOR.values()))


def _nav_id(path: str) -> str:
    """The link the navigation should mark: an element belongs to Browse, which opened it."""
    if path.startswith("/element/"):
        return "nav-browse"
    return NAV_FOR.get(path, "")


def _marked(ui, nav_id: str) -> bool:
    link = ui.page.locator(f"#{nav_id}")
    if not link.count():
        return False
    el = link.first
    return el.get_attribute("data-active") is not None or el.get_attribute("aria-current") is not None


def _element_path(ui) -> str:
    """One real element to audit, taken from Browse so no other group's edit can strand it."""
    if _ELEMENT_PATH:
        return _ELEMENT_PATH[0]
    ui.goto("/browse")
    ids_seen = [rid for rid in ui.grid_row_ids("browse-grid") if rid]
    _ELEMENT_PATH.append(f"/element/{ids_seen[0]}" if ids_seen else "/element/LDC-CURR")
    return _ELEMENT_PATH[0]


def _brief(items: list[str]) -> str:
    return _some(items, MAX_DETAIL)


def _luminance(hex_colour: str) -> float:
    """WCAG relative luminance, so a colour pair can be sorted into how it is being used."""
    h = hex_colour.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        v = int(h[i : i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# Three ways this application puts text below the contrast floor, so the report carries
# three findings a designer can act on rather than forty colour pairs.
CONTRAST_BUCKETS = {
    "dimmed": (
        "Mantine's dimmed text (#868e96) is below the 4.5:1 floor on every background it is "
        "used on — page subtitles, helper lines, table captions and the tagline in the header"
    ),
    "tinted": (
        "A palette colour used as text on its own pale tint — light-variant badges, alerts "
        "and anchors — falls below the 4.5:1 floor, worst for the yellow and green states"
    ),
    "filled": (
        "White text on a filled badge or a primary button falls below the 4.5:1 floor: the "
        "fills are chosen for the eye, not measured against the label on them"
    ),
}


def _contrast_bucket(fg: str, bg: str) -> str:
    if fg.lower() in ("#868e96", "#909296", "#adb5bd"):
        return "dimmed"
    return "filled" if _luminance(fg) > _luminance(bg) else "tinted"


# ------------------------------------------------------------------------ the audit


def _clipped_badges(ui, finding, name: str, width: str) -> None:
    """A badge whose label does not fit inside it has stopped saying what it is."""
    clipped = ui.page.evaluate(CLIPPED_BADGES_JS)
    if clipped:
        _lodge(
            finding,
            "clipped-badge",
            name,
            "usability",
            "A badge does not fit its own label: the name of a state, a type, a status or a "
            "role is cut to an ellipsis, or cut off at both edges of the pill with no "
            "ellipsis to say so, when that name is the whole point of the badge",
            [f"{name} at {width}: {_brief(clipped)}"],
        )


def audit_screen(ui, record, finding, name: str, path: str, source: str = "") -> None:
    """Run every automatable checkpoint over one screen and photograph it twice.

    The screen has to load — that is the only thing a scenario in this group fails for.
    Everything else is lodged with the `finding` fixture and reaches the report's
    Findings table, so one pass over the application reports all of it. The checks
    below therefore all read `ok`: what they carry is the verdict, in their detail.
    """
    ui.goto(path)
    body = ui.body()
    ui.must(f"{name} loads", "This page failed to render" not in body, body[:200].replace("\n", " · "))
    ui.must(f"{name} renders something", len(body.strip()) > 40, f"{len(body.strip())} characters")
    ui.check("the checklist was applied to", True, f"{name} at {path}" + (f" ({source})" if source else ""))

    # ---- 1. the navigation marks the current page
    nav_id = _nav_id(path)
    if nav_id:
        here = _marked(ui, nav_id)
        elsewhere = [other for other in NAV_IDS if other != nav_id and _marked(ui, other)]
        if not here or elsewhere:
            _lodge(
                finding,
                "nav-not-marked",
                name,
                "usability",
                "The navigation does not say which page the reader is on",
                [f"{path} should mark #{nav_id}; marked instead: {elsewhere or 'nothing'}"],
            )
        ui.check(
            "checkpoint 1 · the navigation marks the current page",
            True,
            f"clean — #{nav_id} is marked and nothing else is"
            if here and not elsewhere
            else f"#{nav_id} not marked; also marked: {elsewhere}",
        )
    else:
        ui.check(
            "checkpoint 1 · the navigation marks the current page",
            True,
            "no navigation entry covers this screen",
        )

    # ---- 2. heading hierarchy: one page title, no level skipped
    heads = ui.page.evaluate(HEADINGS_JS)
    levels = [h["level"] for h in heads]
    if not heads:
        _lodge(
            finding,
            "no-headings",
            name,
            "accessibility",
            "The screen renders no heading at all, so nothing names it for a screen reader",
            [f"{path} has no h1–h6 inside #page"],
        )
        ui.check("checkpoint 2 · heading hierarchy", True, "no heading at all")
    else:
        top = min(levels)
        titles = [h["text"] for h in heads if h["level"] == top]
        problems: list[str] = []
        if len(titles) != 1:
            problems.append(f"{len(titles)} headings share the top level h{top}: {titles[:4]}")
            _lodge(
                finding,
                "several-page-titles",
                name,
                "accessibility",
                "Several headings share the screen's top heading level, so none of them is the "
                "page title and the outline has no single root",
                [f"{name}: {len(titles)} at h{top} — {titles[:4]}"],
            )
        if 1 not in levels:
            problems.append(f"no h1; the page title is an h{top}")
            _lodge(
                finding,
                "no-h1",
                name,
                "accessibility",
                "No screen renders an h1: page_title() writes the page title as an h2, so every "
                "document starts at level 2 and assistive technology finds no title for it",
                ["src/ea/ui/components.py page_title() uses dmc.Title(title, order=2)"],
            )
        skips: list[str] = []
        previous = None
        for h in heads:
            if previous is not None and h["level"] > previous + 1:
                skips.append(f"h{previous} → h{h['level']} at {h['text']!r}")
            previous = h["level"]
        if skips:
            problems.append(_brief(skips))
            _lodge(
                finding,
                "heading-skip",
                name,
                "accessibility",
                "Section headings skip levels: a card headed with order=5 follows the h2 page "
                "title directly, so the outline jumps h2 → h5 and the structure is lost",
                [f"{name}: {s}" for s in skips],
            )
        ui.check(
            "checkpoint 2 · heading hierarchy",
            True,
            "; ".join(problems) if problems else f"clean — one h{top} page title, no level skipped",
        )

    # ---- 3. labelling: every control has a visible label or an accessible name
    unlabelled = ui.page.evaluate(LABELS_JS)
    if unlabelled:
        described = [
            u["sel"]
            + (f" (placeholder {u['placeholder']!r})" if u["placeholder"] else "")
            + (f" [role={u['role']}]" if u["role"] else "")
            for u in unlabelled
        ]
        _lodge(
            finding,
            "unlabelled-controls",
            name,
            "accessibility",
            "Controls carry no visible label and no accessible name — icon-only action buttons "
            "whose only wording is a tooltip, which names nothing until it is hovered, and "
            "inputs that rely on a placeholder, which is not a label and goes the moment "
            "anything is typed into it",
            described,
        )
        ui.check(
            "checkpoint 3 · labelling",
            True,
            f"{len(unlabelled)} controls have no accessible name: {_brief(described)}",
        )
    else:
        ui.check("checkpoint 3 · labelling", True, "clean — every control has a name")

    # ---- 4. disabled with a reason. A title or a description is a reason a reader can
    # find; nearby text may be one (ag-Grid's pager sits beside "Page 1 of 1") so it is
    # counted apart rather than lodged, and a control with neither is the finding.
    disabled = ui.page.evaluate(DISABLED_JS)
    silent = [d for d in disabled if not d["reason"] and not d["near"]]
    implied = [d for d in disabled if not d["reason"] and d["near"]]
    verdict: list[str] = []
    if silent:
        described = [f"{d['sel']} {d['label']!r}" for d in silent]
        _lodge(
            finding,
            "disabled-without-reason",
            name,
            "usability",
            "A disabled control says nothing about why it is disabled: no title, no "
            "description and nothing beside it a reader could use to learn what would "
            "enable it",
            [f"{name}: {d}" for d in described],
        )
        verdict.append(f"{len(silent)} of {len(disabled)} give no reason at all: {_brief(described)}")
    if implied:
        verdict.append(
            f"{len(implied)} rely on nearby text alone, e.g. "
            + _brief([f"{d['sel']} near {d['near']!r}" for d in implied[:2]])
        )
    if not disabled:
        verdict.append("nothing on this screen is disabled")
    elif not verdict:
        verdict.append(f"clean — {len(disabled)} disabled controls, each with a reason")
    ui.check("checkpoint 4 · disabled with a reason", True, "; ".join(verdict))

    # ---- 5. empty states: a card with a heading and nothing under it
    hollow = ui.page.evaluate(EMPTY_CARDS_JS)
    if hollow:
        _lodge(
            finding,
            "empty-card",
            name,
            "usability",
            "A card carries a heading and nothing at all under it, so the reader is told a "
            "section exists but not what is in it or what to do to fill it",
            [f"{name}: {h['heading']!r}" for h in hollow],
        )
    ui.check(
        "checkpoint 5 · a headed card has something under it",
        True,
        f"{len(hollow)} cards are headed but empty: {_brief([h['heading'] for h in hollow])}"
        if hollow
        else "clean — every headed card has content",
    )

    # ---- 8. contrast, sorted into the three ways this application falls below the floor
    poor = ui.page.evaluate(CONTRAST_JS)
    combos: dict[tuple[str, str], dict] = {}
    for p in poor:
        seen = combos.get((p["fg"], p["bg"]))
        if seen is None or p["ratio"] < seen["ratio"]:
            combos[(p["fg"], p["bg"])] = p
    if combos:
        described = [
            f"{v['fg']} on {v['bg']} at {v['ratio']}:1 (needs {v['floor']}) — "
            f"{v['size']}px {v['cls']}, {v['text']!r}"
            for v in combos.values()
        ]
        for (fg, bg), v in combos.items():
            bucket = _contrast_bucket(fg, bg)
            _lodge(
                finding,
                f"contrast-{bucket}",
                name,
                "accessibility",
                CONTRAST_BUCKETS[bucket],
                [f"{fg} on {bg} at {v['ratio']}:1 ({v['size']}px, e.g. {v['text']!r} on {name})"],
            )
        ui.check(
            "checkpoint 8 · contrast",
            True,
            f"{len(poor)} text nodes in {len(combos)} colour pairs below the floor: {_brief(described)}",
        )
    else:
        ui.check("checkpoint 8 · contrast", True, "clean — every text node meets its floor")

    _clipped_badges(ui, finding, name, "1600 px")
    ui.shot(f"{name} as a reader sees it on a wide screen, the whole page")

    # ---- 10. the narrow viewport
    ui.narrow()
    try:
        ui.settle()
        flow = ui.page.evaluate(OVERFLOW_JS)
        fits = flow["scroll"] <= flow["client"] + 2
        detail = f"scrollWidth {flow['scroll']} vs clientWidth {flow['client']}"
        if not fits:
            _lodge(
                finding,
                "narrow-overflow",
                name,
                "usability",
                "At 480 px the page scrolls sideways: the content is wider than the viewport, "
                "so part of every row is off-screen and the reader has to pan the whole page "
                "to read one line of it",
                [f"{name}: {detail} — {_brief([o['sel'] for o in flow['over']])}"],
            )
            detail += f" — {_brief([o['sel'] for o in flow['over']])}"
        ui.check(
            "checkpoint 10 · nothing is clipped at 480 px",
            True,
            detail if not fits else f"clean — {detail}",
        )
        _clipped_badges(ui, finding, name, "480 px")
        ui.shot(f"{name} at 480 px, the width the checklist requires it to be usable at")
    finally:
        ui.wide()
        ui.settle()


# ------------------------------------------------------------------------ scenarios


@pytest.mark.scenario(
    scenario_id="P01",
    group="P",
    title="Home against the usability checklist",
    feature="Screen audit · Home",
    expected="Home loads, and the seven automated checkpoints are applied to it: one page title with "
    "no level skipped, every control named, every disabled control giving a reason, the navigation "
    "marking Home, no sideways scroll at 480 px, text above the contrast floor, and no headed card "
    "left empty.",
)
def test_home_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Home", "/", "src/ea/ui/pages/home.py")


@pytest.mark.scenario(
    scenario_id="P02",
    group="P",
    title="Browse against the usability checklist",
    feature="Screen audit · Browse",
    expected="Browse loads with its filters and grid, and the seven automated checkpoints are applied "
    "to it, including the type filter and the search box that carry only a placeholder.",
)
def test_browse_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Browse", "/browse", "src/ea/ui/pages/browse.py")


@pytest.mark.scenario(
    scenario_id="P03",
    group="P",
    title="Element against the usability checklist",
    feature="Screen audit · Element",
    expected="An element opened from Browse loads with its five tabs, and the seven automated "
    "checkpoints are applied to it — including whether the navigation marks Browse, which opened it.",
)
def test_element_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Element", _element_path(ui), "src/ea/ui/pages/element.py")


@pytest.mark.scenario(
    scenario_id="P04",
    group="P",
    title="Impact against the usability checklist",
    feature="Screen audit · Impact",
    expected="Impact loads before anything is run, and the seven automated checkpoints are applied "
    "to it, including the depth spinner that is built with no label.",
)
def test_impact_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Impact", "/impact", "src/ea/ui/pages/impact.py")


@pytest.mark.scenario(
    scenario_id="P05",
    group="P",
    title="Target state against the usability checklist",
    feature="Screen audit · Target state",
    expected="Target state loads with its work-package picker and the current-by-target matrix, and "
    "the seven automated checkpoints are applied to it.",
)
def test_target_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Target state", "/target", "src/ea/ui/pages/target.py")


@pytest.mark.scenario(
    scenario_id="P06",
    group="P",
    title="Ask against the usability checklist",
    feature="Screen audit · Ask",
    expected="Ask loads before a question is put to it, and the seven automated checkpoints are "
    "applied to it, including its empty state.",
)
def test_ask_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Ask", "/ask", "src/ea/ui/pages/ask.py")


@pytest.mark.scenario(
    scenario_id="P07",
    group="P",
    title="Propose against the usability checklist",
    feature="Screen audit · Propose",
    expected="Propose loads with its sources, its branch and work-package pickers and its analyse "
    "button, and the seven automated checkpoints are applied to it.",
)
def test_propose_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Propose", "/propose", "src/ea/ui/pages/propose.py")


@pytest.mark.scenario(
    scenario_id="P08",
    group="P",
    title="Import against the usability checklist",
    feature="Screen audit · Import",
    expected="Import loads with its upload area, mapping picker and the validate and load buttons, "
    "and the seven automated checkpoints are applied to it.",
)
def test_import_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Import", "/import", "src/ea/ui/pages/import_page.py")


@pytest.mark.scenario(
    scenario_id="P09",
    group="P",
    title="Branches against the usability checklist",
    feature="Screen audit · Branches",
    expected="Branches loads with its status filter and branch list, and the seven automated "
    "checkpoints are applied to it.",
)
def test_branches_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Branches", "/branches", "src/ea/ui/pages/branches.py")


@pytest.mark.scenario(
    scenario_id="P10",
    group="P",
    title="Metamodel against the usability checklist",
    feature="Screen audit · Metamodel",
    expected="Metamodel loads with its type graph and editable grids, and the seven automated "
    "checkpoints are applied to it.",
)
def test_metamodel_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Metamodel", "/metamodel", "src/ea/ui/pages/metamodel.py")


@pytest.mark.scenario(
    scenario_id="P11",
    group="P",
    title="Health against the usability checklist",
    feature="Screen audit · Health",
    expected="Health loads with its freshness and completeness figures, and the seven automated "
    "checkpoints are applied to it.",
)
def test_health_audit(ui, record, finding):
    audit_screen(ui, record, finding, "Health", "/health", "src/ea/ui/pages/health.py")


# ------------------------------------------------- the states an address does not reach

# A screen has more states than it has addresses. A tab moved, a dialog opened, a refusal
# returned or a role changed puts controls, headings and colours on the screen that the
# eleven audits above never see, and the checklist applies to those exactly as it does to
# the screen they came from. What follows runs the same probes on the screen as it stands,
# lodging under the same keys, so a fault a state reveals joins the row the screens wrote
# rather than opening a second one for the same cause.

# The wording used when a state is the first to lodge a cause, matching what the audit
# above lodges it under so the report reads the same whichever found it first.
LODGE_SUMMARY = {
    "heading-skip": (
        "Section headings skip levels: a card headed with order=5 follows the h2 page "
        "title directly, so the outline jumps h2 → h5 and the structure is lost"
    ),
    "unlabelled-controls": (
        "Controls carry no visible label and no accessible name — icon-only action buttons "
        "whose only wording is a tooltip, which names nothing until it is hovered, and "
        "inputs that rely on a placeholder, which is not a label and goes the moment "
        "anything is typed into it"
    ),
    "disabled-without-reason": (
        "A disabled control says nothing about why it is disabled: no title, no "
        "description and nothing beside it a reader could use to learn what would "
        "enable it"
    ),
    "narrow-overflow": (
        "At 480 px the page scrolls sideways: the content is wider than the viewport, "
        "so part of every row is off-screen and the reader has to pan the whole page "
        "to read one line of it"
    ),
}

# Checkpoint 9, which the eleven screen audits leave to the screenshots: the keyboard has to
# reach a control and the control has to show that it has it. What "shows" means differs by
# control — an outline on a button, a border colour on an input, a background on a link — so
# the probe does not look for one particular ring. It photographs the control's computed
# style while it has the keyboard, and again once nothing has it, and asks whether anything
# about it changed at all.
FOCUS_PROPERTIES = (
    "outline-style",
    "outline-width",
    "outline-colour",
    "box-shadow",
    "border-colour",
    "border-width",
    "background",
    "colour",
    "underline",
)

FOCUS_STOP_JS = (
    """
(index) => {
"""
    + VISIBLE
    + """
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  el.setAttribute('data-p-focus-stop', String(index));
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  return {
    stop: index,
    sel: where(el),
    name: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '')
      .trim().replace(/\\s+/g, ' ').slice(0, 34),
    visible: vis(el),
    inPage: !!el.closest('#page'),
    onScreen: r.bottom > -2 && r.top < innerHeight + 2 && r.right > -2 && r.left < innerWidth + 2,
    style: [cs.outlineStyle, cs.outlineWidth, cs.outlineColor, cs.boxShadow, cs.borderColor,
            cs.borderWidth, cs.backgroundColor, cs.color, cs.textDecorationLine],
  };
}
"""
)

# The same controls read again with nothing focused, and the marks taken back off.
FOCUS_RESTING_JS = """
() => {
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  const out = {};
  document.querySelectorAll('[data-p-focus-stop]').forEach(el => {
    const cs = getComputedStyle(el);
    out[el.getAttribute('data-p-focus-stop')] = [cs.outlineStyle, cs.outlineWidth, cs.outlineColor,
      cs.boxShadow, cs.borderColor, cs.borderWidth, cs.backgroundColor, cs.color,
      cs.textDecorationLine];
    el.removeAttribute('data-p-focus-stop');
  });
  return out;
}
"""


def audit_current(ui, finding, name: str, state: str, headings: bool = True) -> None:
    """Run the checkpoints a state can change, on the screen as it stands now.

    `audit_screen` reads a screen as an address renders it, and the two checkpoints that
    belong to the address rather than to the state — the navigation marking the page, and
    the narrow viewport — are not repeated here. `headings` is off for a dialog, whose
    title is not part of the page's own outline.
    """
    where = f"{name} · {state}"

    if headings:
        heads = ui.page.evaluate(HEADINGS_JS)
        skips: list[str] = []
        previous = None
        for h in heads:
            if previous is not None and h["level"] > previous + 1:
                skips.append(f"h{previous} → h{h['level']} at {h['text']!r}")
            previous = h["level"]
        if skips:
            _lodge(
                finding,
                "heading-skip",
                where,
                "accessibility",
                LODGE_SUMMARY["heading-skip"],
                [f"{where}: {s}" for s in skips],
            )
        ui.check(
            f"checkpoint 2 · heading hierarchy · {state}",
            True,
            _brief(skips) if skips else f"clean — {len(heads)} headings, no level skipped",
        )

    unlabelled = ui.page.evaluate(LABELS_JS)
    described = [
        u["sel"] + (f" (placeholder {u['placeholder']!r})" if u["placeholder"] else "") for u in unlabelled
    ]
    if described:
        _lodge(
            finding,
            "unlabelled-controls",
            where,
            "accessibility",
            LODGE_SUMMARY["unlabelled-controls"],
            described,
        )
    ui.check(
        f"checkpoint 3 · labelling · {state}",
        True,
        f"{len(described)} controls have no accessible name: {_brief(described)}"
        if described
        else "clean — every control on screen has a name",
    )

    disabled = ui.page.evaluate(DISABLED_JS)
    silent = [f"{d['sel']} {d['label']!r}" for d in disabled if not d["reason"] and not d["near"]]
    implied = [d for d in disabled if not d["reason"] and d["near"]]
    if silent:
        _lodge(
            finding,
            "disabled-without-reason",
            where,
            "usability",
            LODGE_SUMMARY["disabled-without-reason"],
            [f"{where}: {s}" for s in silent],
        )
    if silent:
        verdict = f"{len(silent)} of {len(disabled)} give no reason at all: {_brief(silent)}"
    elif disabled:
        verdict = f"clean — {len(disabled)} disabled, {len(implied)} explained by the text beside them"
    else:
        verdict = "nothing in this state is disabled"
    ui.check(f"checkpoint 4 · disabled with a reason · {state}", True, verdict)

    poor = ui.page.evaluate(CONTRAST_JS)
    combos: dict[tuple[str, str], dict] = {}
    for p in poor:
        seen = combos.get((p["fg"], p["bg"]))
        if seen is None or p["ratio"] < seen["ratio"]:
            combos[(p["fg"], p["bg"])] = p
    for (fg, bg), v in combos.items():
        bucket = _contrast_bucket(fg, bg)
        _lodge(
            finding,
            f"contrast-{bucket}",
            where,
            "accessibility",
            CONTRAST_BUCKETS[bucket],
            [f"{fg} on {bg} at {v['ratio']}:1 ({v['size']}px, e.g. {v['text']!r} on {where})"],
        )
    ui.check(
        f"checkpoint 8 · contrast · {state}",
        True,
        (
            f"{len(poor)} text nodes in {len(combos)} colour pairs below the floor: "
            + _brief([f"{v['fg']} on {v['bg']} at {v['ratio']}:1 — {v['text']!r}" for v in combos.values()])
        )
        if combos
        else "clean — every text node meets its floor",
    )
    _clipped_badges(ui, finding, where, "1600 px")


def narrow_pass(ui, finding, name: str, caption: str) -> None:
    """Checkpoint 10 on a state: what a reader at 480 px is given, and a photograph of it."""
    ui.narrow()
    try:
        ui.settle()
        flow = ui.page.evaluate(OVERFLOW_JS)
        detail = f"scrollWidth {flow['scroll']} vs clientWidth {flow['client']}"
        if flow["scroll"] > flow["client"] + 2:
            widest = _brief([o["sel"] for o in flow["over"]])
            _lodge(
                finding,
                "narrow-overflow",
                name,
                "usability",
                LODGE_SUMMARY["narrow-overflow"],
                [f"{name}: {detail} — {widest}"],
            )
            detail += f" — {widest}"
        else:
            detail = f"clean — {detail}"
        ui.check("checkpoint 10 · nothing is clipped at 480 px", True, detail)
        _clipped_badges(ui, finding, name, "480 px")
        ui.shot(caption)
    finally:
        ui.wide()
        ui.settle()


def _open_tab(ui, root: str, label: str) -> bool:
    """Click a tab by the name it wears, and say whether its own panel came forward."""
    tab = ui.page.locator(f"{root} [role='tab']").filter(has_text=re.compile(re.escape(label)))
    if not tab.count():
        return False
    tab.first.click()
    ui.settle()
    return tab.first.get_attribute("aria-selected") == "true"


def _panel_text(ui, root: str) -> str:
    """What the tab panel now on show actually holds."""
    panels = ui.page.locator(f"{root} [role='tabpanel']")
    for i in range(panels.count()):
        panel = panels.nth(i)
        if panel.is_visible():
            return (panel.inner_text() or "").strip()
    return ""


# What each Element tab has to put on the screen: that a panel opened is not proof the right
# one did. History's single sentence is its own empty state — an element nobody has edited
# since the import has no versions to list, and says so rather than showing a blank.
EL_TAB_PROOF = {
    "Edit": lambda ui, text: ui.visible("el-save"),
    "Relationships": lambda ui, text: ui.visible("el-rel-add"),
    "Graph": lambda ui, text: ui.page.locator(".ea-graph-canvas canvas").count() > 0,
    "History": lambda ui, text: "No changes recorded" in text or "version" in text.lower(),
}


def _element_id(ui) -> str:
    """The identifier of the element the group audits, from the same first row of Browse."""
    return _element_path(ui).rsplit("/", 1)[-1]


_WORK_PACKAGE: list[str] = []  # one work package, resolved once from the model itself


def _work_package(ui) -> str:
    """A work package the model really carries, read off Target state's own links."""
    if _WORK_PACKAGE:
        return _WORK_PACKAGE[0]
    ui.goto("/target")
    hrefs = ui.page.locator('#tg-body a[href^="/target?wp="]').evaluate_all(
        "links => links.map(a => a.getAttribute('href'))"
    )
    ids_seen = [h.split("wp=", 1)[1] for h in hrefs if h and "wp=" in h]
    _WORK_PACKAGE.append(ids_seen[0] if ids_seen else "WP-CMS-UPGRADE")
    return _WORK_PACKAGE[0]


def _ask_box(ui):
    """The question box: Mantine may put the id on the field or on the wrapper around it."""
    field = ui.page.locator("textarea#ask-input")
    return field.first if field.count() else ui.page.locator("#ask-input textarea").first


def _focus_walk(ui, presses: int, caption: str = "", shot_at: int = 3) -> list[dict]:
    """Tab through a screen and report where the keyboard went and whether it showed.

    Each stop is marked as it is reached and read a second time at the end with nothing
    focused, so `ring` is what actually changed about the control rather than a guess at
    which property a design uses to draw one.
    """
    stops: list[dict] = []
    for i in range(presses):
        ui.page.keyboard.press("Tab")
        ui.page.wait_for_timeout(30)
        stop = ui.page.evaluate(FOCUS_STOP_JS, i)
        if stop:
            stops.append(stop)
        if caption and i == shot_at:
            ui.shot(caption)
    resting = ui.page.evaluate(FOCUS_RESTING_JS)
    for stop in stops:
        was = resting.get(str(stop["stop"]))
        changed = (
            [name for name, a, b in zip(FOCUS_PROPERTIES, stop["style"], was, strict=False) if a != b]
            if was
            else []
        )
        # A control the second read could not find is not reported either way: it was
        # measured once and the evidence for it is incomplete.
        stop["ring"] = bool(changed) or was is None
        stop["how"] = ", ".join(changed) if changed else ("not measured twice" if was is None else "nothing")
    return stops


@pytest.mark.scenario(
    scenario_id="P12",
    group="P",
    title="Browse as a Health figure opens it, against the usability checklist",
    feature="Screen audit · Browse from an address",
    expected="The address behind a Health figure renders Browse narrowed to the rows that figure counts, "
    "says in words which rows it is showing and offers the way back to the whole list, and the automated "
    "checkpoints are applied to it in that state.",
)
def test_browse_from_health_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "Browse filtered from Health",
        "/browse?missing=description",
        "src/ea/ui/pages/browse.py · _filter_note",
    )
    note = ui.text("browse-filter-note")
    ui.check(
        "checkpoint 5 · the filter note says which rows the address asked for",
        "without a description" in note.lower(),
        note or "nothing is said about the filter",
    )
    ui.check(
        "and offers the way back to the whole list",
        "Show all elements" in note,
        note or "nothing is said about the filter",
    )
    filtered = ui.grid_row_count("browse-grid")
    ui.goto("/browse")
    everything = ui.grid_row_count("browse-grid")
    ui.check(
        "the address really narrowed the grid rather than only saying so",
        filtered < everything,
        f"{filtered} rows filtered against {everything} unfiltered",
    )


@pytest.mark.scenario(
    scenario_id="P13",
    group="P",
    title="Browse with a search that matches nothing, against the usability checklist",
    feature="Screen audit · Browse with nothing to show",
    expected="A search nothing matches leaves Browse with an empty grid; the count says 0 of 0, the words "
    "that matched nothing are still in the box, and what the screen offers a reader in that state is read "
    "against checkpoint 5 and lodged when it is only the grid's stock overlay.",
)
def test_browse_with_nothing_to_show_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "Browse with nothing to show",
        "/browse?q=zzzqqqmatchesnothing",
        "src/ea/ui/pages/browse.py",
    )
    count = ui.text("browse-count")
    ui.check("the count says the search matched nothing", count.startswith("0 of 0"), count or "(no count)")
    typed = ui.page.locator("#browse-text").first.input_value() or ""
    ui.check(
        "the words that matched nothing are still in the box, so the reader can edit them",
        "zzzqqqmatchesnothing" in typed,
        f"the box holds {typed!r}",
    )
    overlay = ui.page.locator("#browse-grid .ag-overlay-no-rows-center")
    said = overlay.first.inner_text().strip() if overlay.count() else ""
    stock = not said or said.lower().startswith("no rows to show")
    if stock:
        _lodge(
            finding,
            "empty-result-says-nothing",
            "Browse with nothing to show",
            "usability",
            "A search that matches nothing is answered by the grid's own stock overlay and nothing "
            "else: the screen does not say what was searched for, that the type and status filters "
            "above are still narrowing the list, or what to try instead",
            [f"the grid says {said or '(nothing at all)'}; the only other word is the count {count!r}"],
        )
    ui.check(
        "checkpoint 5 · the empty result says what it is",
        True,
        f"the grid says {said or '(nothing at all)'}; the count reads {count!r}",
    )


@pytest.mark.scenario(
    scenario_id="P14",
    group="P",
    title="Browse as a Reader against the usability checklist",
    feature="Screen audit · a role that may not write",
    expected="A Reader is shown the same screen with its two writing buttons off; the page says in words "
    "why, the checkpoints are applied to the refusal, and the header's new-branch button — whose only "
    "wording is a tooltip a disabled control never opens — is read against checkpoint 6.",
    role="reader",
)
def test_browse_as_a_reader_audit(ui, record, finding):
    ui.goto("/browse")
    ui.persona("Reader")
    audit_screen(ui, record, finding, "Browse as a Reader", "/browse", "src/ea/ui/pages/browse.py")
    ui.check(
        "the header says which role the screen is being read as",
        "reader" in ui.role_badge().lower(),
        ui.role_badge(),
    )
    page = ui.text("page")
    ui.check(
        "checkpoint 6 · the page says in words what a Reader may not do here",
        "You are a Reader on this page" in page,
        page[:160].replace("\n", " · "),
    )
    ui.check("Bulk edit is off for a Reader", ui.disabled("bulk-open"))
    ui.check("New element is off for a Reader", ui.disabled("new-open"))
    ui.check("and so is the header's new-branch button", ui.disabled("branch-new-open"))
    ui.page.locator("#branch-new-open").first.hover(force=True)
    ui.page.wait_for_timeout(500)
    tooltip = ui.page.locator(".mantine-Tooltip-tooltip")
    shown = bool(tooltip.count()) and tooltip.first.is_visible()
    if not shown:
        _lodge(
            finding,
            "refusal-only-in-a-tooltip",
            "The header's new-branch button, as a Reader",
            "usability",
            "The reason a role may not create a branch is written only in a tooltip on the disabled "
            "button, and a disabled control takes no pointer events, so hovering it opens nothing: "
            "the refusal 'Your role may not create branches' cannot be read at all",
            ["src/ea/ui/layout.py wraps the disabled ActionIcon in dmc.Tooltip; hovering shows nothing"],
        )
    ui.check(
        "checkpoint 6 · the header's refusal can be read",
        True,
        "the tooltip opens on hover" if shown else "hovering the disabled button opens no tooltip at all",
    )
    ui.shot("Browse as a Reader: the writing controls are off and the page says why")


@pytest.mark.scenario(
    scenario_id="P15",
    group="P",
    title="An element that is not there, against the usability checklist",
    feature="Screen audit · Element not found",
    expected="An identifier nothing carries renders a Not found screen that names the identifier, says "
    "why that can happen and offers two ways on, and the automated checkpoints are applied to it.",
)
def test_missing_element_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "An element that is not there",
        "/element/P-NO-SUCH-ELEMENT",
        "src/ea/ui/pages/element.py · render()",
    )
    page = ui.text("page")
    ui.check(
        "checkpoint 6 · the refusal names the identifier that was not found",
        "P-NO-SUCH-ELEMENT" in page,
        page[:200].replace("\n", " · "),
    )
    ui.check(
        "and says why an identifier can go missing",
        "renamed or removed" in page,
        page[:240].replace("\n", " · "),
    )
    ui.check(
        "and offers a way on rather than a dead end",
        ui.page.locator('#page a[href="/browse"]').count() > 0
        and ui.page.locator('#page a[href="/"]').count() > 0,
        f"{ui.page.locator('#page a').count()} links on the screen",
    )


@pytest.mark.scenario(
    scenario_id="P16",
    group="P",
    title="The Element tabs behind Overview, against the usability checklist",
    feature="Screen audit · Element tabs",
    expected="Edit, Relationships, Graph and History each open their own panel, and the checkpoints that a "
    "state can change — headings, labelling, disabled-with-a-reason, contrast and badge fit — are applied "
    "to each of them, because a hidden panel's controls are invisible to the screen audit.",
)
def test_element_tabs_audit(ui, record, finding):
    ui.goto(_element_path(ui))
    for label in ("Edit", "Relationships", "Graph", "History"):
        opened = _open_tab(ui, "#el-tabs", label)
        ui.check(f"the {label} tab opens its own panel", opened, f"aria-selected is {opened}")
        if label == "Graph":
            try:
                ui.wait_graph()
            except Exception:  # noqa: BLE001 — a graph that never paints is the audit's finding
                pass
        text = _panel_text(ui, "#el-tabs")
        ui.check(f"the {label} panel has something in it", bool(text.strip()), f"{len(text)} characters")
        ui.check(
            f"and it is the {label} panel, not another one under its name",
            EL_TAB_PROOF[label](ui, text),
            text[:90].replace("\n", " · ") or "(nothing at all)",
        )
        audit_current(ui, finding, "Element", f"the {label} tab")
        ui.shot(f"The Element screen's {label} tab, which no address of its own reaches")


@pytest.mark.scenario(
    scenario_id="P17",
    group="P",
    title="The Metamodel tabs behind Element types, against the usability checklist",
    feature="Screen audit · Metamodel tabs",
    expected="Relationship types, Attributes, Notation and Reviewers each open their own panel, and the "
    "checkpoints that a state can change are applied to each — four grids and a notation preview that the "
    "screen audit never sees, because the panels behind the first tab are hidden.",
)
def test_metamodel_tabs_audit(ui, record, finding):
    ui.goto("/metamodel")
    for label in ("Relationship types", "Attributes", "Notation", "Reviewers"):
        opened = _open_tab(ui, "#page", label)
        ui.check(f"the {label} tab opens its own panel", opened, f"aria-selected is {opened}")
        text = _panel_text(ui, "#page")
        ui.check(f"the {label} panel has something in it", len(text) > 20, f"{len(text)} characters")
        audit_current(ui, finding, "Metamodel", f"the {label} tab")
        ui.shot(f"The Metamodel screen's {label} tab, which no address of its own reaches")


@pytest.mark.scenario(
    scenario_id="P18",
    group="P",
    title="Impact with a result on it, against the usability checklist",
    feature="Screen audit · Impact answered",
    expected="An address naming an element runs the trace and renders the summary, the completeness "
    "caveat, the two tables, the graph and the generated view with its downloads enabled — the state the "
    "screen audit of the empty Impact page cannot reach — and the checkpoints are applied to all of it.",
)
def test_impact_with_a_result_audit(ui, record, finding):
    element_id = _element_id(ui)
    audit_screen(
        ui,
        record,
        finding,
        "Impact with a result",
        f"/impact?element={element_id}",
        "src/ea/ui/pages/impact.py · _result",
    )
    page = ui.text("page")
    ui.check(
        "the address ran the trace it names rather than only filling the picker",
        "depend on it within" in page,
        page[:200].replace("\n", " · "),
    )
    at = page.find("Completeness:")
    ui.check(
        "the answer says how complete it is",
        at >= 0,
        page[at : at + 140].replace("\n", " · ") if at >= 0 else "no completeness caveat",
    )
    ui.check(
        "the view can be exported once there is one",
        not ui.disabled("imp-view-md") and not ui.disabled("imp-view-drawio"),
        f"Markdown disabled={ui.disabled('imp-view-md')}, draw.io disabled={ui.disabled('imp-view-drawio')}",
    )


@pytest.mark.scenario(
    scenario_id="P19",
    group="P",
    title="Impact addressed with an element that is not there, against the usability checklist",
    feature="Screen audit · Impact refusing an address",
    expected="An address naming an element nothing carries is refused rather than answered with an empty "
    "page, the picker is left empty, and the refusal is read against checkpoint 6 — whether it names what "
    "was refused and what to do instead.",
)
def test_impact_unknown_element_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "Impact refusing an address",
        "/impact?element=P-NO-SUCH-ELEMENT",
        "src/ea/ui/pages/impact.py · render()",
    )
    result = ui.text("imp-result")
    ui.check(
        "the address is refused rather than answered with an empty page",
        "Unknown element" in result,
        result[:160] or "(nothing at all)",
    )
    chosen = ui.page.locator("#imp-element").first.input_value() or ""
    ui.check(
        "the picker is left empty, because there is nothing to select",
        chosen.strip() == "",
        f"the picker holds {chosen!r}",
    )
    if "P-NO-SUCH-ELEMENT" not in result:
        _lodge(
            finding,
            "refusal-names-nothing",
            "Impact refusing an address",
            "usability",
            "A refusal does not name what was refused or what to do instead: the screen says only "
            "'Unknown element.', with neither the identifier the address carried nor a way on — the "
            "Not found screen for an element does both",
            [f"the whole refusal reads {result[:80]!r} for /impact?element=P-NO-SUCH-ELEMENT"],
        )
    ui.check("checkpoint 6 · the refusal names what was refused", True, f"the refusal reads {result[:80]!r}")


@pytest.mark.scenario(
    scenario_id="P20",
    group="P",
    title="The answer document against the usability checklist",
    feature="Screen audit · Ask answered",
    expected="A question put to the stub provider returns the document — a generated view, the answer, the "
    "elements table and the trace — and the checkpoints are applied to the longest screen the application "
    "renders, at both widths.",
)
def test_ask_answered_audit(ui, record, finding):
    ui.goto("/ask")
    ui.click("ask-button")
    ui.page.wait_for_selector("#ask-answer .ea-document", timeout=30_000)
    ui.settle()
    try:
        ui.wait_mermaid()
    except Exception:  # noqa: BLE001 — an answer that drew no view is still a screen to audit
        pass
    answer = ui.text("ask-answer")
    ui.must("the question was answered as a document", len(answer) > 200, f"{len(answer)} characters")
    ui.check(
        "the document says how it was answered",
        "how this was answered" in answer.lower(),
        answer[:160].replace("\n", " · "),
    )
    audit_current(ui, finding, "Ask", "answered")
    ui.shot("The answer document as a reader sees it on a wide screen")
    narrow_pass(ui, finding, "Ask answered", "The answer document at 480 px")


@pytest.mark.scenario(
    scenario_id="P21",
    group="P",
    title="Ask with the question cleared, against the usability checklist",
    feature="Screen audit · Ask refusing an empty question",
    expected="Clearing the box turns Ask off and puts the reason beside it, which is checkpoint 4 met on a "
    "control that is genuinely disabled, and the checkpoints are applied to the screen in that state.",
)
def test_ask_empty_question_audit(ui, record, finding):
    ui.goto("/ask")
    box = _ask_box(ui)
    box.click()
    box.fill("")
    ui.settle()
    off = ui.disabled("ask-button")
    ui.check(
        "Ask cannot be pressed on an empty box",
        off,
        "the button is off" if off else "the button is still live",
    )
    hint = ui.text("ask-hint")
    ui.check(
        "checkpoint 4 · and the reason stands beside it",
        "Type a question" in hint,
        hint or "nothing is said beside the button",
    )
    audit_current(ui, finding, "Ask", "the question cleared")
    ui.shot("Ask with the question cleared: the button is off and the reason is beside it")


@pytest.mark.scenario(
    scenario_id="P22",
    group="P",
    title="Import asked to validate nothing, against the usability checklist",
    feature="Screen audit · Import refusing",
    expected="Pressing Validate with no file uploaded is refused in words that say what to do, and the "
    "checkpoints are applied to the screen carrying that refusal.",
)
def test_import_refusal_audit(ui, record, finding):
    ui.goto("/import")
    ui.click("im-validate")
    report = ui.text("im-report")
    ui.check(
        "checkpoint 6 · validating nothing is refused in words that say what to do",
        "Upload at least one CSV file first." in report,
        report[:160] or "(nothing at all)",
    )
    audit_current(ui, finding, "Import", "asked to validate with no file")
    ui.shot("Import refusing to validate with nothing uploaded")


@pytest.mark.scenario(
    scenario_id="P23",
    group="P",
    title="Branches with a status nothing matches, against the usability checklist",
    feature="Screen audit · Branches empty state",
    expected="A status filter that matches no branch says so and says what to do about it, and the "
    "checkpoints are applied to the screen in that state.",
)
def test_branches_empty_status_audit(ui, record, finding):
    ui.goto("/branches")
    empty_status, listed = "", ""
    for label in ("Abandoned", "Merged", "Approved", "In review", "Open"):
        ui.segmented("br-status", label)
        listed = ui.text("br-list")
        if listed.lower().startswith("no "):
            empty_status = label
            break
    ui.check(
        "a status with no branches under it can be reached",
        bool(empty_status),
        f"{empty_status} has none"
        if empty_status
        else f"every status had branches; the last read {listed[:80]!r}",
    )
    if empty_status:
        ui.check(
            f"checkpoint 5 · {empty_status} says there is nothing under it",
            listed.lower().startswith("no "),
            listed[:120],
        )
        ui.check(
            "and says what to do next rather than leaving a blank",
            "Pick another status" in listed or "Create one" in listed,
            listed[:120],
        )
        audit_current(ui, finding, "Branches", f"the {empty_status} filter, which matches nothing")
        ui.shot(f"Branches filtered to {empty_status}, with nothing under it")


@pytest.mark.scenario(
    scenario_id="P24",
    group="P",
    title="Branches addressed with a branch that is not there, against the usability checklist",
    feature="Screen audit · Branches refusing an address",
    expected="An address naming a branch that does not exist is refused by name, the list above it still "
    "renders, and the automated checkpoints are applied to that screen.",
)
def test_branches_unknown_branch_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "Branches refusing an address",
        "/branches?branch=p-no-such-branch",
        "src/ea/ui/pages/branches.py · _detail",
    )
    detail = ui.text("br-detail")
    ui.check(
        "checkpoint 6 · the refusal names the branch that was asked for",
        "p-no-such-branch" in detail,
        detail[:160] or "(nothing at all)",
    )
    listed = ui.text("br-list")
    ui.check(
        "and the rest of the screen still renders, so the reader can pick another branch",
        len(listed) > 10,
        listed[:100].replace("\n", " · "),
    )


@pytest.mark.scenario(
    scenario_id="P25",
    group="P",
    title="Target state scoped to a work package, against the usability checklist",
    feature="Screen audit · Target state scoped",
    expected="The address behind a work-package link scopes the whole screen to that work package, turns "
    "off the only-what-changes switch because a work package shows everything it touches, and the "
    "checkpoints are applied to the matrix, the marked view and the two tables in that state.",
)
def test_target_scoped_audit(ui, record, finding):
    work_package = _work_package(ui)
    audit_screen(
        ui,
        record,
        finding,
        "Target state scoped to a work package",
        f"/target?wp={work_package}",
        "src/ea/ui/pages/target.py · _body",
    )
    shown = ui.page.locator("#tg-wp").first.input_value() or ""
    ui.check(
        "the picker holds the work package the address named",
        work_package in shown,
        f"the picker holds {shown!r} for wp={work_package}",
    )
    checked = ui.page.locator("#tg-only-changes").first.is_checked()
    ui.check(
        "and the only-what-changes switch is off, so the scope shows everything it touches",
        not checked,
        f"the switch is {'on' if checked else 'off'}",
    )
    scoped = ui.text("tg-body")
    ui.check(
        "the elements in the scope are listed",
        "elements (" in scoped.lower(),
        scoped[:140].replace("\n", " · ") or "(nothing at all)",
    )


@pytest.mark.scenario(
    scenario_id="P26",
    group="P",
    title="Target state addressed with a work package that is not there",
    feature="Screen audit · Target state ignoring an address",
    expected="An address naming a work package the model does not carry falls back to every work package. "
    "The screen loads, and whether it says so is read against checkpoint 6 — Impact refuses the same "
    "mistake by name.",
)
def test_target_unknown_work_package_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "Target state ignoring an address",
        "/target?wp=P-NO-SUCH-WORK-PACKAGE",
        "src/ea/ui/pages/target.py · render()",
    )
    shown = (ui.page.locator("#tg-wp").first.input_value() or "").strip()
    ui.check(
        "the scope falls back to every work package rather than failing",
        shown == "All work packages",
        f"the picker holds {shown!r}",
    )
    said = "P-NO-SUCH-WORK-PACKAGE" in ui.body()
    if not said:
        _lodge(
            finding,
            "address-ignored-in-silence",
            "Target state ignoring an address",
            "usability",
            "A work package an address names that the model does not carry is dropped in silence: the "
            "screen shows every work package as though that had been asked for, and a reader who "
            "followed a stale link reads the whole model believing it is one initiative",
            ["/target?wp=P-NO-SUCH-WORK-PACKAGE renders the unscoped page with no word about the address"],
        )
    ui.check(
        "checkpoint 6 · an address naming nothing says so",
        True,
        "the screen names the work package it could not find"
        if said
        else "the address is dropped without a word, unlike Impact, which refuses one by name",
    )


@pytest.mark.scenario(
    scenario_id="P27",
    group="P",
    title="An address that is not a page, against the usability checklist",
    feature="Screen audit · the fallback to Home",
    expected="An address nobody recognises renders Home under a warning that names the address, the "
    "navigation marks Home because that is what was rendered, and the checkpoints are applied to it.",
)
def test_unknown_address_audit(ui, record, finding):
    audit_screen(
        ui,
        record,
        finding,
        "An address that is not a page",
        "/p-no-such-page",
        "src/ea/ui/app.py · route()",
    )
    page = ui.text("page")
    ui.check(
        "checkpoint 6 · the warning names the address that was not found",
        "/p-no-such-page" in page,
        page[:200].replace("\n", " · "),
    )
    ui.check(
        "and says where the reader has landed instead",
        "This is the home page" in page,
        page[:200].replace("\n", " · "),
    )
    ui.check(
        "Home itself is rendered under the warning",
        "elements by type" in page.lower(),
        page[:240].replace("\n", " · "),
    )
    ui.check("the navigation marks Home, which is what was rendered", _marked(ui, "nav-home"))


@pytest.mark.scenario(
    scenario_id="P28",
    group="P",
    title="The three dialogs against the usability checklist",
    feature="Screen audit · dialogs",
    expected="New element, Bulk edit with nothing ticked and the header's New branch each open, say what "
    "they are for, and have their controls read against labelling, disabled-with-a-reason and contrast — "
    "controls no screen audit reaches, because a closed dialog renders nothing.",
)
def test_dialogs_audit(ui, record, finding):
    ui.goto("/browse")
    ui.click("new-open")
    ui.must("the New element dialog opened", ui.visible("new-modal-body"))
    titled = ui.text(".mantine-Modal-content")
    ui.check("it says what it is for", titled.startswith("New element"), titled[:60])
    audit_current(ui, finding, "Browse", "the New element dialog", headings=False)
    ui.shot("The New element dialog, whose controls no screen audit reaches")
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("Escape closes it", not ui.page.locator("#new-modal-body").count())

    ui.click("bulk-open")
    ui.must("the Bulk edit dialog opened", ui.visible("bulk-modal-body"))
    feedback = ui.text("bulk-feedback")
    ui.check(
        "checkpoint 5 · with nothing ticked it says why there is nothing to change",
        "Nothing is ticked" in feedback,
        feedback[:120] or "(nothing at all)",
    )
    audit_current(ui, finding, "Browse", "the Bulk edit dialog with nothing ticked", headings=False)
    ui.shot("The Bulk edit dialog opened with nothing ticked, saying so")
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(400)
    ui.settle()

    ui.click("branch-new-open")
    ui.must("the New branch dialog opened", ui.visible("branch-new-modal-body"))
    ui.check(
        "it says what a branch is before asking for a name",
        "A branch starts from main" in ui.text("branch-new-modal-body"),
        ui.text("branch-new-modal-body")[:120],
    )
    audit_current(ui, finding, "The header", "the New branch dialog", headings=False)
    ui.shot("The header's New branch dialog")
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_timeout(400)
    ui.settle()
    ui.check("Escape closes that one too", not ui.page.locator("#branch-new-modal-body").count())


@pytest.mark.scenario(
    scenario_id="P29",
    group="P",
    title="Checkpoint 9 · tabbing reaches the controls and shows where it is",
    feature="Screen audit · focus",
    expected="On Home, Browse and Ask the keyboard moves through the screen, reaches the page's own "
    "controls and not only the header, and every control it lands on draws something — an outline or a "
    "ring — to say it has the keyboard; a control that draws nothing is lodged.",
)
def test_focus_audit(ui, record, finding):
    for name, path in (("Home", "/"), ("Browse", "/browse"), ("Ask", "/ask")):
        ui.goto(path)
        stops = _focus_walk(ui, 20, f"{name}: where the keyboard is after four Tab presses")
        ui.must(f"tabbing moves the keyboard through {name}", len(stops) >= 3, f"{len(stops)} stops")
        ringless: list[str] = []
        for stop in stops:
            entry = f"{stop['sel']} {stop['name']!r}"
            if stop["visible"] and not stop["ring"] and entry not in ringless:
                ringless.append(entry)  # a walk that wraps meets the same control twice
        drawn = next(
            (f"{s['sel']} by {s['how']}" for s in stops if s["visible"] and s["ring"] and s["how"]),
            "nothing was measured twice",
        )
        unseen = sorted({s["sel"] for s in stops if not s["visible"]})
        in_page = [s for s in stops if s["inPage"]]
        if ringless:
            _lodge(
                finding,
                "focus-not-visible",
                name,
                "accessibility",
                "A control takes the keyboard without showing that it has it: tabbing to it changes "
                "nothing on the screen, so a reader working without a mouse cannot tell where they are "
                "or what pressing Enter would do",
                [f"{name}: {r}" for r in ringless],
            )
        if not in_page:
            _lodge(
                finding,
                "focus-never-reaches-the-page",
                name,
                "accessibility",
                "Twenty Tab presses from the top of the screen never reach the page's own controls: "
                "everything the keyboard finds is header and navigation, so the screen cannot be "
                "worked without a mouse",
                [f"{name}: {len(stops)} stops, none of them inside the page"],
            )
        if unseen:
            _lodge(
                finding,
                "focus-on-something-invisible",
                name,
                "accessibility",
                "The keyboard lands on a control that is not visible, so the focus disappears while "
                "tabbing and the reader cannot see what would take their next keystroke",
                [f"{name}: {_brief(unseen)}"],
            )
        ui.check(
            f"checkpoint 9 · focus · {name}",
            True,
            f"{len(stops)} tab stops, {len(in_page)} of them inside the page; "
            + (
                f"{len(ringless)} draw nothing: {_brief(ringless)}"
                if ringless
                else "every one changes as it takes the keyboard, e.g. " + drawn
            )
            + (f"; {len(unseen)} are invisible" if unseen else ""),
        )
