"""The stylesheet's colours put every control's text, and its own, above the floor.

`assets/styles.css` darkens the component library's palette where the stock shades put text
below 4.5:1. What a browser paints is not one variable but a stack: a light button is its
colour's tint laid over whatever is under it, and inside an alert that is the alert's own
tint laid over the card or the canvas. So each pair here is measured the way a browser
composites it — every translucent layer laid over the next, down to an opaque surface — for
every colour a domain may be given, every variant, at rest and hovered, on every surface
the application paints and inside every alert. The colours the stylesheet writes for itself,
outside the block, are measured the same way on the grounds each is painted on.

This is the arithmetic of the colours, not the round's contrast checkpoint: that one reads
what a browser has painted, and scenario P32 of the round pins how it composites a stack.

The stock values are the component library's default palette at the shade the theme leaves
alone (6), with its hover one shade darker (7), and its tints that shade at 10 % and 12 %
(5 % for an outline's hover): what the library's own variables resolve to wherever the
block names nothing.
"""

from __future__ import annotations

import re

from tests.conftest import ROOT

from ea.ui.pages.metamodel import PALETTE

CSS = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

#: The component library's default palette, shades 6 and 7.
STOCK = {
    "gray": ("#868e96", "#495057"),
    "red": ("#fa5252", "#f03e3e"),
    "pink": ("#e64980", "#d6336c"),
    "grape": ("#be4bdb", "#ae3ec9"),
    "violet": ("#7950f2", "#7048e8"),
    "indigo": ("#4c6ef5", "#4263eb"),
    "blue": ("#228be6", "#1c7ed6"),
    "cyan": ("#15aabf", "#1098ad"),
    "teal": ("#12b886", "#0ca678"),
    "green": ("#40c057", "#37b24d"),
    "lime": ("#82c91e", "#74b816"),
    "yellow": ("#fab005", "#f59f00"),
    "orange": ("#fd7e14", "#f76707"),
}
WHITE = "#ffffff"
FLOOR = 4.5

Rgba = tuple[float, float, float, float]


def _block() -> dict[str, str]:
    """The declarations of the readable-colour block, by variable."""
    start = CSS.index(":root {", CSS.index("readable colour"))
    body = CSS[start : CSS.index("}", start)]
    return dict(re.findall(r"(--mantine-[\w-]+):\s*(#[0-9a-fA-F]{6})\s*!important", body))


BLOCK = _block()


#: The component library's own shades that the stylesheet names by variable outside the block.
LIBRARY = {
    "--mantine-color-gray-1": "#f1f3f5",
    "--mantine-color-indigo-0": "#edf2ff",
    "--mantine-color-orange-0": "#fff4e6",
}


def _colour(value: str) -> str:
    """A colour as the stylesheet writes it — a hex value or a variable — as six hex digits."""
    value = value.replace("!important", "").strip()
    named = re.fullmatch(r"var\((--[\w-]+)\)", value)
    if named:
        variable = named.group(1)
        found = BLOCK.get(variable) or LIBRARY.get(variable)
        assert found, f"{variable} is neither in the readable-colour block nor a shade this file knows"
        return found
    assert re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", value), (
        f"not a colour this file can read: {value}"
    )
    if len(value) == 4:
        value = "#" + "".join(c * 2 for c in value[1:])
    return value.lower()


def _rules() -> dict[str, dict[str, str]]:
    """Every rule of the stylesheet, by selector, with its declarations (the last one wins)."""
    text = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    rules: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
        declared = rules.setdefault(" ".join(selector.split()), {})
        declared.update((k, v.strip()) for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body))
    return rules


RULES = _rules()


def _surface(selector: str) -> str:
    """The background the stylesheet gives one of its rules."""
    declared = RULES.get(selector, {})
    value = declared.get("background") or declared.get("background-color")
    assert value, f"the stylesheet no longer gives {selector} a background"
    return _colour(value)


#: Every opaque surface text or a control sits on: a card or a modal, the canvas, the header
#: and navigation, and the two bands the stylesheet paints above a page's content — the stripe
#: that says the reader is on a branch, which carries a link, and a screen's tip, which carries
#: a light button and two subtle ones.
SURFACES = {
    "a card": WHITE,
    "the canvas": _surface(".mantine-AppShell-main"),
    "the header": _surface(".mantine-AppShell-header, .mantine-AppShell-navbar"),
    "the branch stripe": _surface(".ea-branch-stripe"),
    "a screen's tip": _surface(".ea-tip"),
}


def _rgba(hex_colour: str, alpha: float = 1.0) -> Rgba:
    h = hex_colour.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _over(front: Rgba, back: Rgba) -> Rgba:
    """One layer painted over another, either of them translucent (source-over)."""
    fa, ba = front[3], back[3]
    a = fa + ba * (1 - fa)
    if a == 0:
        return (0, 0, 0, 0)
    mix = [(front[i] * fa + back[i] * ba * (1 - fa)) / a for i in range(3)]
    return (mix[0], mix[1], mix[2], a)


def _paint(*layers: Rgba) -> Rgba:
    """The colour a stack of layers, top first, paints once it reaches an opaque one."""
    painted = layers[0]
    for layer in layers[1:]:
        painted = _over(painted, layer)
    assert painted[3] >= 0.999, "a stack must end on an opaque surface"
    return painted


def _luminance(c: Rgba) -> float:
    channels = []
    for v in c[:3]:
        v /= 255
        channels.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(fg: Rgba, bg: Rgba) -> float:
    a, b = _luminance(fg), _luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _hex(c: Rgba) -> str:
    return "#" + "".join(f"{round(v):02x}" for v in c[:3])


def _var(colour: str, family: str) -> str:
    """What `--mantine-color-<colour>-<family>` resolves to: the block's value, else the stock one."""
    six, seven = STOCK[colour]
    stock = {"light-color": six, "outline": six, "filled": six, "filled-hover": seven}[family]
    return BLOCK.get(f"--mantine-color-{colour}-{family}", stock)


def _tint(colour: str, alpha: float) -> Rgba:
    """A light variant's background: the raw shade, translucent, whatever the block says."""
    return _rgba(STOCK[colour][0], alpha)


def _grounds() -> dict[str, list[Rgba]]:
    """Every ground a control's own layers are painted on: each opaque surface, and each alert
    colour's tint laid over it — a light button or badge inside an alert is a tint over a tint."""
    grounds: dict[str, list[Rgba]] = {}
    for where, surface in SURFACES.items():
        grounds[where] = [_rgba(surface)]
        for alert in PALETTE:
            grounds[f"inside a {alert} alert on {where}"] = [_tint(alert, 0.1), _rgba(surface)]
    return grounds


def _worst(failures: list[tuple[str, str, float]]) -> list[str]:
    """One line per control and state, at its worst ground, so a failure reads as a list to fix."""
    worst: dict[str, tuple[str, float]] = {}
    for what, where, ratio in failures:
        if what not in worst or ratio < worst[what][1]:
            worst[what] = (where, ratio)
    return [f"{what} {where}: {ratio:.2f}:1" for what, (where, ratio) in sorted(worst.items())]


def test_every_colour_the_application_names_is_one_the_block_makes_readable():
    """A domain may be given any colour of the palette, and every page names colours of its
    own; a colour the block does not cover is drawn in the stock shade, which is where the
    round found text at 1.66:1."""
    named = set()
    for path in (ROOT / "src" / "ea").rglob("*.py"):
        named |= set(re.findall(r"[\"']([a-z]+)[\"']", path.read_text(encoding="utf-8"))) & set(STOCK)
    for pack in (ROOT / "packs").glob("*/metamodel.yaml"):
        named |= set(re.findall(r"colour:\s*([a-z]+)", pack.read_text(encoding="utf-8")))
    assert named <= set(PALETTE), f"named but not offered as a domain colour: {sorted(named - set(PALETTE))}"
    assert set(PALETTE) <= set(STOCK)
    missing = [
        f"--mantine-color-{c}-{family}"
        for c in PALETTE
        for family in ("light-color", "outline", "filled", "filled-hover")
        if f"--mantine-color-{c}-{family}" not in BLOCK
    ]
    assert not missing, f"the readable-colour block leaves these at the stock shade: {missing}"


def test_a_tinted_control_reads_on_every_surface_and_inside_every_alert():
    """Light, subtle and outline buttons, badges and alerts, at rest and hovered: their text
    is the colour's `-light-color` or `-outline`, their background a tint of the raw shade."""
    failures = []
    for colour in PALETTE:
        text, outline = _rgba(_var(colour, "light-color")), _rgba(_var(colour, "outline"))
        for where, ground in _grounds().items():
            pairs = {
                f"{colour} light": (text, _paint(_tint(colour, 0.1), *ground)),
                f"{colour} light, hovered": (text, _paint(_tint(colour, 0.12), *ground)),
                f"{colour} subtle": (text, _paint(*ground)),
                f"{colour} outline": (outline, _paint(*ground)),
                f"{colour} outline, hovered": (outline, _paint(_tint(colour, 0.05), *ground)),
            }
            for what, (fg, bg) in pairs.items():
                ratio = _ratio(fg, bg)
                if ratio < FLOOR:
                    failures.append((what, where, ratio))
    assert not failures, "below 4.5:1:\n" + "\n".join(_worst(failures))


def test_white_on_a_filled_control_reads_at_rest_and_hovered():
    """A filled badge, button or segmented control puts white on `-filled`, and a filled button
    goes to `-filled-hover` under the pointer. Darkening the resting fill alone leaves the hover
    at the stock shade 7, which is lighter than the fill it replaces: the label fades as the
    pointer reaches it."""
    failures = []
    for colour in PALETTE:
        rest, hover = _rgba(_var(colour, "filled")), _rgba(_var(colour, "filled-hover"))
        for what, bg in ((f"{colour} filled", rest), (f"{colour} filled, hovered", hover)):
            ratio = _ratio(_rgba(WHITE), bg)
            if ratio < FLOOR:
                failures.append((what, f"({_hex(bg)})", ratio))
        if _luminance(hover) > _luminance(rest):
            failures.append((f"{colour} filled, lighter hovered than at rest", f"({_hex(hover)})", 0.0))
    assert not failures, "below 4.5:1, or lighter under the pointer:\n" + "\n".join(_worst(failures))


def test_captions_links_and_the_error_colour_read_on_every_surface_and_inside_every_alert():
    failures = []
    for name in ("dimmed", "anchor", "error"):
        fg = _rgba(BLOCK[f"--mantine-color-{name}"])
        for where, ground in _grounds().items():
            ratio = _ratio(fg, _paint(*ground))
            if ratio < FLOOR:
                failures.append((name, where, ratio))
    assert not failures, "below 4.5:1:\n" + "\n".join(_worst(failures))


def test_the_compositing_here_agrees_with_a_pixel_the_browser_painted():
    """The sweeps above are only as good as `_paint`. One stack was photographed in Chromium:
    the default-colour light button inside the blue alert on the canvas (a draft's Resume
    button on Propose), whose label's ground is #c6d6ed on screen. `_paint` lands within two
    levels of it, and the label reads above 6:1 there. This checks the arithmetic of this file,
    not the audit: how the round's contrast checkpoint composites a stack in the browser is
    pinned by scenario P32 of the round."""
    ground = _paint(_tint("indigo", 0.1), _tint("blue", 0.1), _rgba(SURFACES["the canvas"]))
    assert all(abs(a - b) <= 2 for a, b in zip(ground[:3], _rgba("#c6d6ed")[:3], strict=True)), _hex(ground)
    assert _ratio(_rgba(_var("indigo", "light-color")), ground) > 6


#: What the data grid paints under a cell, read from the running grid: its accent colour at
#: 8 % under the pointer and 12 % on a ticked row, each a layer of its own over the row, and a
#: ticked row under the pointer is the one laid over the other. The merge log ticks every
#: clean row as it opens, so a ticked row is where its 'changed' and 'deleted' labels sit.
#: The editable cell's own background is painted above the row's, whatever the row is doing.
GRID_ACCENT = "#2196f3"
GRID = {
    "a grid row": [_rgba(WHITE)],
    "a hovered grid row": [_rgba(GRID_ACCENT, 0.08), _rgba(WHITE)],
    "a ticked grid row": [_rgba(GRID_ACCENT, 0.12), _rgba(WHITE)],
    "a ticked grid row, hovered": [_rgba(GRID_ACCENT, 0.12), _rgba(GRID_ACCENT, 0.08), _rgba(WHITE)],
    "the editable cell": [_rgba(_surface(".ag-theme-alpine .ea-editable"))],
}

#: A rendered document (an answer, a view's Markdown, the Guide): the card it is on, and the
#: grounds the stylesheet gives the parts of it.
DOCUMENT = {
    "a document": [_rgba(WHITE)],
    "a document's hovered table row": [_rgba(_surface(".ea-doc tr:hover td"))],
    "a document's table heading": [_rgba(_surface(".ea-doc th"))],
    "a document's code": [_rgba(_surface(".ea-doc code"))],
    "a document's code block": [_rgba(_surface(".ea-doc pre"))],
}


def _own(selector: str) -> dict[str, list[Rgba]]:
    return {f"its own background ({selector})": [_rgba(_surface(selector))]}


def _on_every_surface() -> dict[str, list[Rgba]]:
    return {where: [_rgba(surface)] for where, surface in SURFACES.items()}


def _inside_every_alert() -> dict[str, list[Rgba]]:
    return {where: ground for where, ground in _grounds().items() if where.startswith("inside")}


#: Where each text colour the stylesheet declares is painted, by the rule that declares it.
#: A rule the stylesheet gains with a `color:` of its own has to say here where it is painted,
#: or the test below fails: that is the point at which a colour is chosen, and the point at
#: which it is cheapest to measure.
PAINTED_ON = {
    ".ea-section-title": _on_every_surface,
    ".ea-doc": lambda: DOCUMENT,
    ".ea-doc a": lambda: DOCUMENT,
    ".ea-doc blockquote": lambda: DOCUMENT,
    ".ea-doc th": lambda: _own(".ea-doc th"),
    ".ea-chip:hover": lambda: _own(".ea-chip-wrap:hover .ea-chip"),
    ".ea-copy": lambda: {**_own(".ea-copy"), **_own(".ea-copy:hover")},
    ".ea-clipboard": lambda: {**_own(".ea-copy"), **_own(".ea-copy:hover")},
    ".mantine-NavLink-root[data-active]": lambda: _own(".mantine-NavLink-root[data-active]"),
    ".ag-theme-alpine .ea-added": lambda: GRID,
    ".ag-theme-alpine .ea-changed": lambda: GRID,
    ".ag-theme-alpine .ea-deleted": lambda: GRID,
    ".ag-theme-alpine .ea-conflict": lambda: GRID,
    ".ag-theme-alpine .ea-link": lambda: GRID,
    ".ag-theme-alpine .ea-snippet": lambda: GRID,
    ".mantine-Slider-markLabel": _on_every_surface,
    ".ea-skip-link": lambda: _own(".ea-skip-link"),
    '[class*="Alert-root"] a': _inside_every_alert,
    ".ea-branch-stripe": lambda: _own(".ea-branch-stripe"),
    ".ea-guide-link": _on_every_surface,
}

#: A text colour no floor applies to, and why.
EXEMPT = {
    # WCAG 1.4.3 asks nothing of a logo, and this one is an icon on a gradient, not text.
    ".ea-brand-mark": "the brand mark",
}


def test_every_text_colour_the_stylesheet_declares_reads_where_it_is_painted():
    """The block above darkens the library's palette; the stylesheet also writes colours of its
    own — the merge log's change labels, the stripe on a branch, a document's links. Each is
    measured on every ground it is painted on, the data grid's ticked and hovered rows among
    them, where the merge log's orange 'changed' read 3.8:1 and the stripe's text 3.96:1."""
    declared = {selector: d["color"] for selector, d in RULES.items() if "color" in d}
    unplaced = sorted(set(declared) - set(PAINTED_ON) - set(EXEMPT))
    assert not unplaced, f"say where these are painted, in PAINTED_ON or EXEMPT: {unplaced}"
    failures = []
    for selector, grounds in PAINTED_ON.items():
        assert selector in declared, f"{selector} no longer declares a colour; take it out of PAINTED_ON"
        fg = _rgba(_colour(declared[selector]))
        for where, ground in grounds().items():
            ratio = _ratio(fg, _paint(*ground))
            if ratio < FLOOR:
                failures.append((f"{selector} ({_hex(fg)})", f"on {where}", ratio))
    assert not failures, "below 4.5:1:\n" + "\n".join(_worst(failures))
