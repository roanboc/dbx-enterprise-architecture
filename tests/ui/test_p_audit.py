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
  document.querySelectorAll('[disabled],[aria-disabled="true"],[data-disabled]').forEach(el => {
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
