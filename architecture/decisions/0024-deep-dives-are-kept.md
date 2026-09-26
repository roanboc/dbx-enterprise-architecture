# 0024 — A deep dive is kept, catalogued and rated; an answer is not

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-25 (initiative 25, its Understanding granted), at the Requester's word — *"this deep analysis can
be valuable to the tool and should be catalogued (domain, type, etc) and stored in the platform …
the user can set later the level of confidence, quality and usefulness (with a single star rating
1 to 5)"*. **Touches:** `DOBJ3.5`, `DOBJ3.11`,
`BPROC3`, `BSVC1`, `ROLE4`, `GAP27`.

## Context

When answers became documents (initiative 2), whether to keep them was an open question, and
the answer was no: an answer to one question is cheap to ask again, and a store of stale
answers would be read as if it were the model. A deep dive is different in kind. It is an
analysis a reader settled with the assistant, with several views and findings that took a
conversation to reach; asked again, it would not come out the same, and what the reader
concluded from it is exactly what the next architect on the same elements needs. The
Requester asked for it to be kept, catalogued, rated and linked from the elements it covers.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Keep nothing, as for an answer | Every deep dive starts from a blank page, and nothing tells a good analysis from a poor one — the gap the Requester named |
| Keep the files — the PDF and the diagrams | A file cannot be searched, catalogued or linked from an element, and its diagrams could not be drawn again in another notation or at another size |
| Keep it in a volume of the platform's catalogue | A second store with its own grants, outside the organisation and branch every other row is scoped by |
| **Keep the analysis as it was read, in the store; generate the pack from it** | Chosen: one row per deep dive in the organisation's own store, catalogued by domain, element type and kind of analysis, with the elements it cites and the ratings it was given; the PDF and the draw.io files are generated from what is kept whenever it is downloaded |

## Decision

A deep dive is kept in the store, per organisation, as the analysis it was when it was read —
its brief, catalogue entry, the maturity of the elements it rests on, its views, findings and
references — and every element it cites lists it. Each person rates it once, one to five stars,
and may change or clear their rating; later deep dives on the same elements weigh it by that rating. A
quick answer stays unkept.

## Consequences

The catalogue grows with use and nothing prunes it; its author or an admin withdraws a deep dive
rather than deleting it, and a withdrawn one is not weighed again. What a deep dive says is what
was true when it was read: the model moves on and the deep dive does not, so every listing shows
its date, the branch it read and the version it was read in, and the next deep dive re-reads the
model rather than trusting an old finding. A rating is a person's judgement, never the
assistant's (principle `P3`).
