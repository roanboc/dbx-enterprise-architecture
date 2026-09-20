# 0019 — The application declares the size it is built for

_[← Decisions](./README.md)_

**Status:** Proposed 2026-09-20, with initiative 16 at the Understanding gate.
**Touches:** `ASM6`, `ASVC4`, `ACMP3`, `DOBJ2`, `GAP18`.

## Context

Decisions 0016 to 0018 re-sized the **store** for the figure the Requester
named — a hundred thousand elements and several hundred thousand relationships
— and measured it. The **services above it** were never re-sized. Six call
sites read every element and every relationship of the organisation into one
request: the in-process graph, the metamodel compatibility check, the two
Health answers, the target-state service and the proposal matcher. One of them
is worse than unbounded: `GraphService._node()` builds the whole graph, and
`trace()` calls it once for the centre and once per row, so the SQL walk that
decision 0016 introduced is wrapped by the enumeration it replaced.

None of this is felt today. At 4,600 elements every one of those reads costs
milliseconds, which is why they were written that way and why they survived.
The Requester's instruction of 2026-09-20 is that `ASM6` stays true for several
months, and that the preparation is made now rather than when it is urgent.
So the call is not *how* to make the services fast; it is what stops a
PoC-sized assumption from being re-made silently as the model grows.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Leave it: `ASM6` is true, revisit when it hurts | What "revisit when it hurts" means in practice is a demo on real content where the first element page takes seven seconds. The assumption is invisible in the code — nothing names it — so nothing would surface it until then |
| Re-architect now: no whole-model read anywhere, the graph gone | Against the Requester's posture and against principle `P7`. The in-process graph is the right answer at today's size, and a rewrite now spends the PoC's remaining time on a problem it does not have |
| Cap every read with a hard-coded limit | A limit per call site is the same assumption re-made six times, in six numbers nobody can find. The next service written makes it a seventh |
| **Declare the size in one place, read it everywhere, and hold it with a test** (chosen) | One figure the code reads, the Health page shows and the suite asserts. A whole-model read becomes a named exception with a stated cost rather than an accident, and a new one has to argue with a test |

## Decision

The application declares the size it is built for — two figures, because they
differ: what the **store** holds and answers, and the smaller size below which
the **in-process graph** may be built at all. Both live in one module the
services read. Every whole-model read is then either bounded by that figure or
declared deliberate with its cost written down, and the suite holds the figure
with a seeded fixture rather than a memory of one measurement.

`ASM6` is restated rather than corrected: it says what is true today, and the
size at which it stops being true.

## Consequences

- A service that needs the whole model has to say so, and say what it costs.
  That is the point; it is also friction on every future service.
- The graph's budget is adopted from initiative 15's measurement (about 470 MB
  and seven seconds at the Requester's figure, against the 6 GB an app on the
  platform gets by default), not measured on this hardware. The scale fixture
  is what turns it into a measurement, and the figure moves when it does.
- A declared figure nobody revisits is a new way to be wrong. `GAP18` carries
  the horizon, because a roadmap row is revisited and a constant is not.
- The in-process graph survives, below its budget. Nothing about the PoC's
  behaviour at today's size changes.
