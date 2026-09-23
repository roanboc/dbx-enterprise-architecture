# 0023 — A viewpoint is pack data, and the reader picks it

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-23 (initiative 22), at the Requester's word — it extends [0003](./0003-metamodel-as-data.md) and [0005](./0005-generated-views.md) rather than reopening either. **Touches:** `DOBJ1.8`, `DOBJ1.2`, `DOBJ2.4`, `ASVC6`, `ACMP8`, `ART2`.

## Context

A generated view was exported the same way whatever it was for: one band per
architecture layer, every element the query returned, every relationship as
the same line. A solution architect wanting an application cooperation
diagram, a swimlane per role, or a band per delivery stage got the same grid
and redrew it. The Requester asked that the reader say what the diagram is
for, so the drawing comes from that.

What a diagram admits, what its bands are, and which relationships are drawn
as a line, as one shape inside another or as a bar across several, is
knowledge of the framework. ArchiMate publishes it as example viewpoints; the
higher-education metamodel carries it as the diagram names on its
relationship types. Neither belongs in `src/` under `P5`.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Viewpoints in code, one module per framework | The obvious place to write a layout rule, and a breach of `P5` the day the second framework arrives. Rejected |
| A viewpoint stored per organisation, edited on a screen | Closer to what a diagram tool offers. Rejected for now: a viewpoint says what a *framework's* diagrams are, so it belongs with the framework's types; an organisation-specific viewpoint is a variant of a pack, which is what a draft version is for |
| The agent decides the viewpoint from the question | Tempting for the Ask page. Rejected as the default: a reader who cannot see why the picture is the shape it is cannot correct it. The agent may *suggest* a viewpoint; the reader picks |
| **A `viewpoints:` section of the pack, picked by the reader at export — chosen** | Frozen with the version it belongs to, compared by the version diff, and carried by the pack file wherever the pack goes. The application knows the grammar of a viewpoint and no viewpoint by name |

## Decision

**A pack declares its viewpoints, and a reader picks one when a view is
exported.** A viewpoint names the element types and relationship types it
admits (none named means all), how it bands — by architecture layer, by
element type, or by a related element of a named type reached through named
relationship types — which relationship types are drawn as nesting, which as a
bar spanning the elements they relate, and the band that takes whatever the
rule cannot place. A relationship type also names, in a `notation` block, the
ArchiMate relationship it is drawn as, so the file carries the right
arrowhead.

The reader names the viewpoint, the focus, the depth and the layers in the
export dialogue and on the command line. The page suggests values from where
the reader is; nothing is decided for them.

## Consequences

- A viewpoint is part of what a version *defines*: a published version's
  viewpoints are frozen with its types, a draft's are edited in place, and the
  version diff reports a change to them. One exception, once: a version stored
  before drawing rules existed holds none, and the next load of its file gives
  it them, logged like a rename, because a viewpoint and an arrowhead govern
  drawings and nothing content validates against. A file that also changes a
  type is refused whole.
- Every pack the repository ships carries four, and a pack with none exports
  the layered drawing, which is what every pack did before.
- The application's own architecture documents keep drawing with Mermaid; the
  viewpoint governs the exported file only. The on-screen diagram is not
  filtered by it yet, which scope document 22 names as left.
- A viewpoint that names an element type or a relationship type the version
  does not declare is a validation error on load, like a relationship type
  whose ends do not exist.
