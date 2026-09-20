# 0016 — A traversal is a walk over the graph, not an enumeration of its paths

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-20, for the Requester to confirm or override. **Touches:** `ASVC4`, `ACMP2`, `DOBJ2.2`.

## Context

`trace` and `impact` were answered by a recursive query that produced one row
per path and guarded a cycle by searching the path it had built so far, then
kept the shortest row per element. On a few thousand elements that is
invisible. The Requester asked what happens at a hundred thousand elements and
several hundred thousand relationships — and there the shape of a real estate
decides it: every element depends on a few shared platforms, and dependencies
come back on themselves, so the number of paths between two elements is bounded
by nothing. Measured on 100,000 elements and 600,000 relationships, a five-hop
walk out of such a hub took 36 seconds and 2.9 GB of memory, while the same
walk out of an ordinary element took 44 ms.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Enumerate every path, keep the shortest per element | What the store did. Correct, and unbounded: a hub and a cycle multiply the rows against each other |
| Walk with a visited set, then look up the edge that reached each element | Measured 1.4 to 12 seconds where the walk alone took 7 to 18 ms: a second pass over the relationships plans as a join against the whole table, and the planner cannot see how few elements it will be given |
| Walk with a visited set, carrying the edge that reached each element — **chosen** | 9 ms out of an ordinary element and 27 ms out of a hub, for the same answers; the path is rebuilt from the rows already returned |
| Precompute what each element reaches | A table to maintain on every write, for a question the walk now answers in milliseconds. It belongs to the batch tier, if the model ever outgrows a single node |

## Decision

One recursive query visits an element once rather than once per path that
reaches it, and each row carries the element one step nearer and the
relationship type between them. The caller rebuilds one shortest path per
element by following those edges back. Both ends of a relationship are indexed,
which is what makes a hop a lookup rather than a scan (decision
[0017](./0017-keys-indexed-references-not.md)). The walk never steps back onto
the element it started from: a cycle would otherwise hand that element back as
reached by way of itself, and anything beyond it is reachable from the start in
fewer hops anyway.

## Consequences

- An impact answer is a **set of elements, each with one shortest path**, not
  every path between two elements. Where two paths are equally short, one is
  chosen deterministically and the other is not shown. Nobody reading an impact
  page was reading every path; anybody who needs them is asking a different
  question, and would ask it of the batch tier.
- The cost of an answer is now the size of the answer. A hub that everything
  depends on reaches the whole model, and that takes about five seconds at a
  hundred thousand elements however the query is written. The fix for that is
  to bound what is asked for and what is shown, not to make the query faster —
  and the Impact page does not bound it yet.
- The indexes cost write time on a bulk import and space in the store, which at
  this size is a trade worth making many times over.
- An older store whose indexes could not be created still answers every
  question. It is slower, not wrong.
