# 0024 — The layout is the application's own code

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-23 (initiative 22), at the Requester's word — it extends [0005](./0005-generated-views.md). **Touches:** `ACMP8`, `ASVC6`, `NODE1.1`.

## Context

A file exported from a page can carry the arrangement the browser gave the
diagram. A file exported from the command line or by the agent cannot: there
is no browser. So the layered drawing initiative 22 asks for has to be laid
out on the server, deterministically, and the question was whether to take a
graph-layout library for it or write it.

The Requester's criterion was maintainability: a dependency is better when it
brings enough capability, and worse when it breaks the application with a
change nobody here made.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| A layered-layout library with a compiled extension (two candidates, one Rust-backed, one with a C extension per interpreter version) | Both under a year old at version 0.x, each shipping one wheel per platform and interpreter. A wheel missing for the platform's next interpreter, or an architecture the platform moves to, stops every export with nothing in this repository to fix. Both solve rank assignment and cycle breaking, which the bands already decide, and neither does what is actually needed: order within a band, nesting, spanning, a port per edge, a page that fits |
| A pure-Python layout library under a copyleft licence | Incompatible with this repository's licence. Rejected outright |
| The browser's layout, captured and reused | Only exists where a page is open; the command line and the agent have none. And it is the layout the Requester called unreadable |
| **The application's own layout, on the graph library it already ships — chosen** | About two hundred and fifty lines: bands from the viewpoint, a barycentre sweep for the order within a band, placement and compaction, nesting, spanning, a port and waypoints per edge. Deterministic, so a golden file per viewpoint pins it. One function, `layout(view, viewpoint)`, behind which a library could be put later without touching a caller |

## Decision

**The layered layout is written in `src/ea/views/layout.py`, on the graph
library the application already depends on, and no layout dependency is
added.** It is deterministic: the same view and the same viewpoint give the
same file, and the golden files under `tests/golden/drawio/` hold it to that.

## Consequences

- The quality ceiling is the application's own: a general graph without bands
  is not laid out well by it, and a viewpoint that needs one is the moment to
  reconsider, behind the same function.
- A change to the layout is a change to every golden file, on purpose: the
  test round shows what moved, and a reviewer sees the drawing rather than a
  diff of coordinates.
- The screens keep the browser's layout. Two layouts exist for one view — one
  on screen, one in the file — and the file's is the one the reader takes
  away.
