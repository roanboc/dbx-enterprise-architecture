"""The layout of an architecture view: rows by layer, few crossings, lines that go around shapes.

Two steps, used together or apart:

- `arrange` places the boxes. One band per layer, top-down; inside a band whose elements are
  related to each other, a row per aspect (services above behaviour above active structure
  above passive structure), as ArchiMate draws a layer. The order inside a row is the one that
  crosses fewest lines, and each box is then moved towards what it is related to, so a line
  runs straight down wherever it can.
- `route` draws every relationship as a line of right angles, from a port on one box to a port
  on the other: through the channel between two rows, through a gutter between boxes when it
  has rows to pass, never across a box. Lines that share a channel take a track each. The label
  sits on its own line, where it covers no box and no other label.

A view the reader arranged by hand keeps the reader's positions and is only routed. The result
is geometry alone, so the draw.io file and the PDF are written from the same plan.
"""

from __future__ import annotations

import math
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise

MARGIN = 20.0
GAP_X = 48.0  # between two boxes in a row: room for a gutter
ROW_GAP = 44.0  # the least channel between two rows of one band
BAND_GAP = 56.0  # the least channel between two bands
TRACK = 10.0  # between two lines sharing a channel or a gutter
CLEAR = 12.0  # how close a line passes a box it does not touch
PORT_INSET = 10.0  # how close a port comes to a box's corner
LABEL_CHAR_W, LABEL_H = 5.2, 13.0

Point = tuple[float, float]


@dataclass
class Box:
    """A shape to place. `band` is the layer's rank; `tier` the row inside the band."""

    id: str
    w: float
    h: float
    band: int = 0
    tier: int = 0
    x: float = 0.0  # top-left
    y: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Link:
    key: str
    src: str
    dst: str
    label: str = ""


@dataclass
class Route:
    """A line from the source's border to the target's, and where its label sits."""

    points: list[Point]
    label_at: Point | None = None
    exit: Point = (0.5, 0.5)  # the port on the source, relative to its box
    entry: Point = (0.5, 0.5)

    def fraction(self, at: Point) -> float:
        """How far along the line a point on it is, from 0 at the source to 1 at the target."""
        total = sum(_seg_len(a, b) for a, b in pairwise(self.points))
        if not total:
            return 0.5
        run = 0.0
        for a, b in pairwise(self.points):
            if _on_segment(at, a, b):
                return (run + _seg_len(a, at)) / total
            run += _seg_len(a, b)
        return 0.5


@dataclass
class Plan:
    boxes: dict[str, Box]
    routes: dict[str, Route] = field(default_factory=dict)
    width: float = 0.0
    height: float = 0.0
    bands: dict[int, tuple[float, float]] = field(default_factory=dict)  # a band's top and bottom

    def shift(self, dx: float, dy: float) -> None:
        for b in self.boxes.values():
            b.x += dx
            b.y += dy
        for r in self.routes.values():
            r.points = [(x + dx, y + dy) for x, y in r.points]
            if r.label_at:
                r.label_at = (r.label_at[0] + dx, r.label_at[1] + dy)
        self.bands = {k: (a + dy, b + dy) for k, (a, b) in self.bands.items()}


# ------------------------------------------------------------------ sizes and tiers
def fit_box(
    text: str,
    sub: str = "",
    char_w: float = 6.6,
    pad: float = 44.0,
    least: float = 150.0,
    most: float = 240.0,
) -> tuple[float, float]:
    """A box wide enough for its name in at most three lines, beside the notation's icon.

    `pad` is the room left and right of the text, where a stencil draws its icon.
    """
    best = None
    for width in range(int(least), int(most) + 1, 10):
        chars = max(8, int((width - pad) / char_w))
        lines = textwrap.wrap(text, chars) or [text]
        if len(lines) <= 2 or width >= most:
            best = (float(width), min(len(lines), 3))
            break
    width, lines = best or (most, 3)
    height = 22 + lines * 15 + (12 if sub else 0)
    return width, float(max(58, height))


def aspect_tier(archimate: str) -> int:
    """The row an element takes inside its layer, as ArchiMate draws a layer: what it offers
    (services, events) above what does the work (active structure and behaviour) above what the
    work is done on (passive structure)."""
    if archimate.endswith(("Service", "Event")):
        return 0
    if archimate.endswith(("Object", "Artifact", "Contract", "Representation", "Material")):
        return 2
    return 1


# ------------------------------------------------------------------ arrange
def arrange(
    boxes: list[Box],
    links: list[Link],
    max_cols: int = 5,
    band_header: float = 0.0,
    lane_pad: float = 0.0,
) -> Plan:
    """Place and route: one band per layer, few crossings, straight lines where they can be.

    With `band_header`, each band keeps room above its first row for a lane's title, and
    `lane_pad` round its rows, so a lane drawn from `Plan.bands` holds its shapes.
    """
    by_id = {b.id: b for b in boxes}
    links = [lk for lk in links if lk.src in by_id and lk.dst in by_id]
    rows = _rows(boxes, links, max_cols)
    row_band = [by_id[r[0]].band for r in rows]
    adj: dict[str, list[str]] = defaultdict(list)
    for lk in links:
        if lk.src != lk.dst:
            adj[lk.src].append(lk.dst)
            adj[lk.dst].append(lk.src)
    rows = _order(rows, by_id, adj)
    _place_x(rows, by_id, adj)

    # Two passes: the first counts the tracks each channel needs, the second leaves room for them.
    needs: dict[int, int] = {}
    plan = Plan(by_id)
    for _ in range(2):
        zones = _place_y(rows, row_band, by_id, needs, band_header, lane_pad, plan)
        plan.routes, needs = _route(rows, by_id, links, zones)
    _normalise(plan)
    return plan


def _rows(boxes: list[Box], links: list[Link], max_cols: int) -> list[list[str]]:
    by_id = {b.id: b for b in boxes}
    related_inside = {
        by_id[lk.src].band for lk in links if lk.src != lk.dst and by_id[lk.src].band == by_id[lk.dst].band
    }
    groups: dict[tuple[int, int], list[str]] = defaultdict(list)
    for b in boxes:
        groups[(b.band, b.tier if b.band in related_inside else 0)].append(b.id)
    rows: list[list[str]] = []
    for key in sorted(groups):
        ids = groups[key]
        count = math.ceil(len(ids) / max_cols)
        size = math.ceil(len(ids) / count)
        rows.extend(ids[i : i + size] for i in range(0, len(ids), size))
    return rows


def _packed(rows: list[list[str]], by_id: dict[str, Box]) -> dict[str, float]:
    """Each box's centre when every row is packed and centred on zero."""
    out: dict[str, float] = {}
    for row in rows:
        total = sum(by_id[i].w for i in row) + GAP_X * (len(row) - 1)
        x = -total / 2
        for i in row:
            out[i] = x + by_id[i].w / 2
            x += by_id[i].w + GAP_X
    return out


def _cost(rows: list[list[str]], by_id: dict[str, Box], adj: dict[str, list[str]]) -> float:
    """Lines crossing between rows, plus boxes standing between two related boxes of one row."""
    xs = _packed(rows, by_id)
    ri = {i: r for r, row in enumerate(rows) for i in row}
    pos = {i: k for row in rows for k, i in enumerate(row)}
    segs, cost = [], 0.0
    seen = set()
    for a, ns in adj.items():
        for b in ns:
            if (b, a) in seen or (a, b) in seen:
                continue
            seen.add((a, b))
            if ri[a] == ri[b]:
                cost += abs(pos[a] - pos[b]) - 1
            else:
                segs.append((xs[a], ri[a], xs[b], ri[b], a, b))
    for n, s in enumerate(segs):
        for t in segs[n + 1 :]:
            if {s[4], s[5]} & {t[4], t[5]}:
                continue
            if _cross((s[0], s[1]), (s[2], s[3]), (t[0], t[1]), (t[2], t[3])):
                cost += 1
    return cost


def _cross(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    def orient(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _order(rows: list[list[str]], by_id: dict[str, Box], adj: dict[str, list[str]]) -> list[list[str]]:
    """Sort each row by where its boxes' neighbours stand, sweeping down and up; keep the best."""
    best, best_cost = [list(r) for r in rows], _cost(rows, by_id, adj)
    current = [list(r) for r in rows]
    for sweep in range(12):
        sequence = range(len(current)) if sweep % 2 == 0 else range(len(current) - 1, -1, -1)
        for r in sequence:
            xs = _packed(current, by_id)
            row = current[r]
            key = {}
            for i in row:
                ns = [xs[n] for n in adj.get(i, [])]
                key[i] = sum(ns) / len(ns) if ns else xs[i]
            current[r] = sorted(row, key=lambda i: key[i])
        c = _cost(current, by_id, adj)
        if c < best_cost:
            best, best_cost = [list(r) for r in current], c
        if best_cost == 0:
            break
    return best


def _place_x(rows: list[list[str]], by_id: dict[str, Box], adj: dict[str, list[str]]) -> None:
    """Move each box towards the median of its neighbours, keeping the order and the gaps."""
    cx = _packed(rows, by_id)
    for sweep in range(8):
        sequence = range(len(rows)) if sweep % 2 == 0 else range(len(rows) - 1, -1, -1)
        for r in sequence:
            row = rows[r]
            want: list[float | None] = []
            for i in row:
                ns = sorted(cx[n] for n in adj.get(i, []) if n not in row)
                # a box related only inside its row keeps close to what it is related to
                ns = ns or sorted(cx[n] for n in adj.get(i, []) if n in row)
                want.append(_median(ns) if ns else None)
            want = _follow(want, [by_id[i].w for i in row], [cx[i] for i in row])
            placed = _fit(want, [by_id[i].w for i in row])
            for i, x in zip(row, placed, strict=True):
                cx[i] = x
    for i, b in by_id.items():
        b.x = cx[i] - b.w / 2


def _follow(want: list[float | None], widths: list[float], current: list[float]) -> list[float]:
    """A box that pulls nowhere stands beside its row's nearest box that does, not where it was."""
    if all(w is None for w in want):
        return current
    out: list[float | None] = list(want)
    for i in range(1, len(out)):
        if out[i] is None and out[i - 1] is not None:
            out[i] = out[i - 1] + (widths[i - 1] + widths[i]) / 2 + GAP_X
    for i in range(len(out) - 2, -1, -1):
        if out[i] is None and out[i + 1] is not None:
            out[i] = out[i + 1] - (widths[i] + widths[i + 1]) / 2 - GAP_X
    return [float(x) for x in out]


def _median(values: list[float]) -> float:
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def _fit(want: list[float], widths: list[float]) -> list[float]:
    """The centres closest to `want` that keep the row's order and its gaps."""
    n = len(want)
    sep = [(widths[i - 1] + widths[i]) / 2 + GAP_X for i in range(1, n)]
    left = list(want)
    for i in range(1, n):
        left[i] = max(want[i], left[i - 1] + sep[i - 1])
    right = list(want)
    for i in range(n - 2, -1, -1):
        right[i] = min(want[i], right[i + 1] - sep[i])
    out = [(a + b) / 2 for a, b in zip(left, right, strict=True)]
    for i in range(1, n):
        out[i] = max(out[i], out[i - 1] + sep[i - 1])
    return out


def _place_y(
    rows: list[list[str]],
    row_band: list[int],
    by_id: dict[str, Box],
    needs: dict[int, int],
    band_header: float,
    lane_pad: float,
    plan: Plan,
) -> dict[int, tuple[float, float]]:
    """Set each row's top; return the band of y each channel's tracks may use."""
    zones: dict[int, tuple[float, float]] = {}
    plan.bands = {}
    y = 0.0
    for r, row in enumerate(rows):
        if r == 0 or row_band[r] != row_band[r - 1]:
            band_top = y
            y += band_header + lane_pad
            plan.bands[row_band[r]] = (band_top, band_top)
        height = max(by_id[i].h for i in row)
        for i in row:
            by_id[i].y = y + (height - by_id[i].h) / 2
        y += height
        last_of_band = r == len(rows) - 1 or row_band[r + 1] != row_band[r]
        tracks = needs.get(r, 0)
        room = (tracks + 1) * TRACK
        if last_of_band:
            y += lane_pad
            plan.bands[row_band[r]] = (plan.bands[row_band[r]][0], y)
            gap = max(BAND_GAP - band_header - 2 * lane_pad, room, TRACK * 2)
        else:
            gap = max(ROW_GAP, room)
        zones[r] = (y, y + gap)
        y += gap
    return zones


def _normalise(plan: Plan) -> None:
    xs, ys = [], []
    for b in plan.boxes.values():
        xs += [b.x, b.right]
        ys += [b.y, b.bottom]
    for r in plan.routes.values():
        xs += [p[0] for p in r.points]
        ys += [p[1] for p in r.points]
        if r.label_at and r.points:
            xs += [r.label_at[0] - 40, r.label_at[0] + 40]
    for top, bottom in plan.bands.values():
        ys += [top, bottom]
    if not xs:
        return
    plan.shift(MARGIN - min(xs), MARGIN - min(ys))
    plan.width = max(xs) - min(xs) + 2 * MARGIN
    plan.height = max(ys) - min(ys) + 2 * MARGIN


# ------------------------------------------------------------------ route
def route(boxes: list[Box], links: list[Link]) -> dict[str, Route]:
    """Route over boxes placed by someone else: the rows are read from where the boxes stand."""
    by_id = {b.id: b for b in boxes}
    rows: list[list[str]] = []
    bottom = -math.inf
    for b in sorted(boxes, key=lambda b: (b.y, b.x)):
        if rows and b.y < bottom - 4:
            rows[-1].append(b.id)
            bottom = max(bottom, b.bottom)
        else:
            rows.append([b.id])
            bottom = b.bottom
    rows = [sorted(r, key=lambda i: by_id[i].x) for r in rows]
    zones: dict[int, tuple[float, float]] = {}
    for r, row in enumerate(rows):
        lo = max(by_id[i].bottom for i in row)
        hi = min(by_id[i].y for i in rows[r + 1]) if r + 1 < len(rows) else lo + ROW_GAP
        zones[r] = (lo, max(hi, lo + 2 * TRACK) if r + 1 == len(rows) else hi)
    return _route(rows, by_id, [lk for lk in links if lk.src in by_id and lk.dst in by_id], zones)[0]


@dataclass
class _Leg:
    """A horizontal stretch of one line, in one channel; its y is set once tracks are dealt."""

    key: str
    channel: int
    a: float  # where the line comes into the channel
    b: float  # where it leaves
    u_turn: bool = False
    y: float = 0.0


def _route(
    rows: list[list[str]], by_id: dict[str, Box], links: list[Link], zones: dict[int, tuple[float, float]]
) -> tuple[dict[str, Route], dict[int, int]]:
    ri = {i: r for r, row in enumerate(rows) for i in row}
    pos = {i: k for row in rows for k, i in enumerate(row)}

    # 1. which side of each box every line leaves or reaches
    ends: dict[tuple[str, str], list[tuple[float, str, str]]] = defaultdict(
        list
    )  # (box, side) -> (key, link, end)
    kind: dict[str, str] = {}
    for lk in links:
        a, b = by_id[lk.src], by_id[lk.dst]
        if lk.src == lk.dst:
            continue
        ra, rb = ri[lk.src], ri[lk.dst]
        if ra == rb and abs(pos[lk.src] - pos[lk.dst]) == 1 and _v_overlap(a, b) > 12:
            kind[lk.key] = "side"
            left, right = (a, b) if a.x < b.x else (b, a)
            ends[(left.id, "right")].append((right.cy, lk.key, "l"))
            ends[(right.id, "left")].append((left.cy, lk.key, "r"))
        elif ra == rb:
            kind[lk.key] = "u"
            ends[(a.id, "bottom")].append((b.cx, lk.key, "s"))
            ends[(b.id, "bottom")].append((a.cx, lk.key, "d"))
        else:
            kind[lk.key] = "down"
            upper, lower = (a, b) if ra < rb else (b, a)
            ends[(upper.id, "bottom")].append((lower.cx, lk.key, "up"))
            ends[(lower.id, "top")].append((upper.cx, lk.key, "lo"))

    # 2. ports spread along each side, in the order of what they lead to
    port: dict[tuple[str, str], float] = {}
    for (bid, side), items in ends.items():
        box = by_id[bid]
        items.sort()
        if side in ("top", "bottom"):
            lo, hi = box.x + PORT_INSET, box.right - PORT_INSET
        else:
            lo, hi = box.y + PORT_INSET, box.bottom - PORT_INSET
        for k, (_, key, end) in enumerate(items):
            port[(key, end)] = lo + (hi - lo) * (k + 1) / (len(items) + 1)
    # lines between two neighbours in a row run level, spread over the height the two share
    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for lk in links:
        if kind.get(lk.key) == "side":
            pairs[tuple(sorted((lk.src, lk.dst)))].append(lk.key)
    for (p, q), keys in pairs.items():
        lo = max(by_id[p].y, by_id[q].y) + 6
        hi = min(by_id[p].bottom, by_id[q].bottom) - 6
        for k, key in enumerate(keys):
            port[(key, "l")] = port[(key, "r")] = lo + (hi - lo) * (k + 1) / (len(keys) + 1)
    # a line alone on both its sides runs straight down when its boxes overlap
    for lk in links:
        if kind.get(lk.key) != "down":
            continue
        a, b = by_id[lk.src], by_id[lk.dst]
        upper, lower = (a, b) if ri[a.id] < ri[b.id] else (b, a)
        if len(ends[(upper.id, "bottom")]) == 1 and len(ends[(lower.id, "top")]) == 1:
            lo = max(upper.x, lower.x) + PORT_INSET
            hi = min(upper.right, lower.right) - PORT_INSET
            if hi - lo > 0:
                port[(lk.key, "up")] = port[(lk.key, "lo")] = (lo + hi) / 2

    # two ports a few points apart meet halfway, so the line runs straight instead of jogging
    taken: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (key, end), x in port.items():
        lk = next(lk for lk in links if lk.key == key)
        if kind.get(key) == "down":
            upper, lower = sorted((lk.src, lk.dst), key=lambda i: ri[i])
            taken[(upper if end == "up" else lower, "h")].append(x)
    for lk in links:
        if kind.get(lk.key) != "down" or abs(ri[lk.src] - ri[lk.dst]) != 1:
            continue
        xa, xb = port[(lk.key, "up")], port[(lk.key, "lo")]
        if not 0.5 < abs(xa - xb) < 16:
            continue
        upper, lower = sorted((by_id[lk.src], by_id[lk.dst]), key=lambda b: ri[b.id])
        mid = (xa + xb) / 2
        inside = all(b.x + PORT_INSET <= mid <= b.right - PORT_INSET for b in (upper, lower))
        clear = all(
            abs(mid - x) >= 8
            for side, own in (((upper.id, "h"), xa), ((lower.id, "h"), xb))
            for x in taken[side]
            if x != own
        )
        if inside and clear:
            port[(lk.key, "up")] = port[(lk.key, "lo")] = mid

    # 3. the legs through channels, and the gutter a line takes past the rows between
    legs: list[_Leg] = []
    gutters: dict[str, tuple[float, float, float, int, int]] = {}  # key -> (x, lo, hi, first row, last row)
    for lk in links:
        k = kind.get(lk.key)
        if k == "u":
            legs.append(_Leg(lk.key, ri[lk.src], port[(lk.key, "s")], port[(lk.key, "d")], u_turn=True))
        elif k == "down":
            ra, rb = sorted((ri[lk.src], ri[lk.dst]))
            xa, xb = port[(lk.key, "up")], port[(lk.key, "lo")]
            if rb == ra + 1:
                if abs(xa - xb) > 0.5:
                    legs.append(_Leg(lk.key, ra, xa, xb))
                continue
            gx, lo, hi = _gutter([rows[r] for r in range(ra + 1, rb)], by_id, xa, xb)
            gutters[lk.key] = (gx, lo, hi, ra, rb)
    _spread_gutters(gutters)
    for lk in links:
        if lk.key not in gutters:
            continue
        gx, _, _, ra, rb = gutters[lk.key]
        xa, xb = port[(lk.key, "up")], port[(lk.key, "lo")]
        if abs(gx - xa) > 0.5:
            legs.append(_Leg(lk.key, ra, xa, gx))
        if abs(gx - xb) > 0.5:
            legs.append(_Leg(lk.key, rb - 1, gx, xb))

    # 4. a track each for the legs that share a channel
    needs = _deal_tracks(legs, zones)
    by_key: dict[str, list[_Leg]] = defaultdict(list)
    for leg in legs:
        by_key[leg.key].append(leg)

    # 5. the points, from the source's border to the target's
    routes: dict[str, Route] = {}
    for lk in links:
        k = kind.get(lk.key)
        if k is None:
            continue
        a, b = by_id[lk.src], by_id[lk.dst]
        if k == "side":
            left, right = (a, b) if a.x < b.x else (b, a)
            y = port[(lk.key, "l")]
            pts = [(left.right, y), (right.x, y)]
            if left is not a:
                pts.reverse()
        elif k == "u":
            (leg,) = by_key[lk.key]
            xa, xb = port[(lk.key, "s")], port[(lk.key, "d")]
            pts = [(xa, a.bottom), (xa, leg.y), (xb, leg.y), (xb, b.bottom)]
        else:
            upper, lower = (a, b) if ri[a.id] < ri[b.id] else (b, a)
            xa, xb = port[(lk.key, "up")], port[(lk.key, "lo")]
            pts = [(xa, upper.bottom)]
            for leg in sorted(by_key[lk.key], key=lambda leg: leg.channel):
                pts += [(leg.a, leg.y), (leg.b, leg.y)]
            pts.append((xb, lower.y))
            if upper is not a:
                pts.reverse()
        pts = _tidy(pts)
        routes[lk.key] = Route(pts, exit=_relative(a, pts[0]), entry=_relative(b, pts[-1]))

    _place_labels(routes, links, by_id)
    return routes, needs


def _v_overlap(a: Box, b: Box) -> float:
    return min(a.bottom, b.bottom) - max(a.y, b.y)


def _gutter(
    between: list[list[str]], by_id: dict[str, Box], xa: float, xb: float
) -> tuple[float, float, float]:
    """Where a line passes the rows between its ends: a free column nearest its two ports."""
    free: list[tuple[float, float]] = [(-math.inf, math.inf)]
    for row in between:
        for i in row:
            b = by_id[i]
            lo, hi = b.x - CLEAR, b.right + CLEAR
            nxt = []
            for f0, f1 in free:
                if hi <= f0 or lo >= f1:
                    nxt.append((f0, f1))
                    continue
                if lo > f0:
                    nxt.append((f0, lo))
                if hi < f1:
                    nxt.append((hi, f1))
            free = nxt
    best, best_score = (xa, xa, xa), math.inf
    mid = (xa + xb) / 2
    for f0, f1 in free:
        for x, bonus in ((xa, -1.0), (xb, -1.0), (min(max(mid, f0), f1), 0.0)):
            if not (f0 <= x <= f1) or math.isinf(x):
                continue
            score = abs(x - xa) + abs(x - xb) + bonus
            if score < best_score:
                best, best_score = (x, f0, f1), score
    return best


def _spread_gutters(gutters: dict[str, tuple[float, float, float, int, int]]) -> None:
    """Lines taking the same gutter past the same rows run side by side, a track apart."""
    keys = sorted(gutters, key=lambda k: gutters[k][0])
    done: set[str] = set()
    for k in keys:
        if k in done:
            continue
        x, lo, hi, ra, rb = gutters[k]
        group = [
            j
            for j in keys
            if j not in done and abs(gutters[j][0] - x) < 1 and gutters[j][3] < rb and ra < gutters[j][4]
        ]
        done.update(group)
        if len(group) < 2:
            continue
        for n, j in enumerate(group):
            if math.isinf(lo) and math.isinf(hi):
                gx = x + (n - (len(group) - 1) / 2) * TRACK
            elif math.isinf(hi):  # the open side of the drawing: spread outwards from the last box
                gx = lo + n * TRACK
            elif math.isinf(lo):
                gx = hi - n * TRACK
            else:
                gx = min(max(x + (n - (len(group) - 1) / 2) * TRACK, lo + 2), hi - 2)
            gutters[j] = (gx, *gutters[j][1:])


def _deal_tracks(legs: list[_Leg], zones: dict[int, tuple[float, float]]) -> dict[int, int]:
    """Give each leg a track in its channel so that no two legs overlap on one track.

    Legs are dealt top-first in the order that crosses least: a leg that runs right is placed
    above one that starts to its left; a U-turn nests inside a longer one.
    """
    needs: dict[int, int] = {}
    by_channel: dict[int, list[_Leg]] = defaultdict(list)
    for leg in legs:
        by_channel[leg.channel].append(leg)
    for channel, items in by_channel.items():

        def priority(leg: _Leg) -> tuple[float, ...]:
            if leg.u_turn:
                return (2, abs(leg.b - leg.a))
            if leg.b >= leg.a:
                return (0, -leg.a)
            return (1, leg.a)

        tracks: list[list[tuple[float, float]]] = []
        dealt: list[tuple[_Leg, int]] = []
        for leg in sorted(items, key=priority):
            lo, hi = sorted((leg.a, leg.b))
            for t, spans in enumerate(tracks):
                if all(hi + 6 < s0 or lo - 6 > s1 for s0, s1 in spans):
                    spans.append((lo, hi))
                    dealt.append((leg, t))
                    break
            else:
                tracks.append([(lo, hi)])
                dealt.append((leg, len(tracks) - 1))
        needs[channel] = len(tracks)
        top, bottom = zones.get(channel, (0.0, 2 * TRACK))
        step = min(TRACK, (bottom - top) / (len(tracks) + 1))
        first = (top + bottom) / 2 - step * (len(tracks) - 1) / 2
        for leg, t in dealt:
            leg.y = first + t * step
    return needs


def _tidy(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1:  # a step under a point is a straight run
            p = (out[-1][0], p[1])
        elif out and abs(out[-1][1] - p[1]) < 1:
            p = (p[0], out[-1][1])
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        if len(out) >= 2 and _collinear(out[-2], out[-1], p):
            out[-1] = p
            continue
        out.append(p)
    return out


def _collinear(a: Point, b: Point, c: Point) -> bool:
    return (abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01) or (
        abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01
    )


def _relative(box: Box, p: Point) -> Point:
    return (
        round(min(max((p[0] - box.x) / box.w, 0.0), 1.0), 4),
        round(min(max((p[1] - box.y) / box.h, 0.0), 1.0), 4),
    )


def _seg_len(a: Point, b: Point) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    return (
        min(a[0], b[0]) - 0.5 <= p[0] <= max(a[0], b[0]) + 0.5
        and min(a[1], b[1]) - 0.5 <= p[1] <= max(a[1], b[1]) + 0.5
    )


# ------------------------------------------------------------------ labels
def label_size(text: str) -> tuple[float, float]:
    return len(text) * LABEL_CHAR_W + 8, LABEL_H


def _place_labels(routes: dict[str, Route], links: list[Link], by_id: dict[str, Box]) -> None:
    """Each label on its own line, where it covers no box, no other label and fewest lines."""
    boxes = [(b.x - 3, b.y - 3, b.right + 3, b.bottom + 3) for b in by_id.values()]
    placed: list[tuple[float, float, float, float]] = []
    segments = [(key, a, b) for key, r in routes.items() for a, b in pairwise(r.points)]
    for lk in sorted(links, key=lambda lk: _length(routes.get(lk.key))):
        r = routes.get(lk.key)
        if r is None or not lk.label or len(r.points) < 2:
            continue
        w, h = label_size(lk.label)
        total = _length(r)
        best, best_cost = None, math.inf
        run = 0.0
        for a, b in pairwise(r.points):
            length = _seg_len(a, b)
            horizontal = abs(a[1] - b[1]) < 0.01
            for t in (0.5, 0.3, 0.7, 0.15, 0.85):
                at = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                rect = (at[0] - w / 2, at[1] - h / 2, at[0] + w / 2, at[1] + h / 2)
                cost = sum(_area(rect, bx) for bx in boxes) * 10
                cost += sum(_area(rect, lb) for lb in placed) * 10
                cost += 150 * sum(1 for key, p, q in segments if key != lk.key and _hits(rect, p, q))
                cost += abs((run + length * t) / (total or 1) - 0.5) * 40
                if horizontal and length < w + 6:
                    cost += 60  # a label longer than its stretch hides the bends
                if not horizontal and length < h + 10:
                    cost += 60
                if cost < best_cost:
                    best, best_cost = at, cost
            run += length
        if best:
            r.label_at = best
            placed.append((best[0] - w / 2, best[1] - h / 2, best[0] + w / 2, best[1] + h / 2))


def _length(r: Route | None) -> float:
    return sum(_seg_len(a, b) for a, b in pairwise(r.points)) if r else 0.0


def _area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _hits(rect: tuple[float, float, float, float], p: Point, q: Point) -> bool:
    """Whether an upright or level segment passes through a rectangle."""
    x0, y0, x1, y1 = rect
    if abs(p[1] - q[1]) < 0.01:
        return y0 < p[1] < y1 and min(p[0], q[0]) < x1 and max(p[0], q[0]) > x0
    return x0 < p[0] < x1 and min(p[1], q[1]) < y1 and max(p[1], q[1]) > y0
