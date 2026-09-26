# 0026 — A drawing comes back as a proposal, never as the store

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-26 (initiative 26, its Understanding granted), at the Requester's word.
It supersedes one consequence of [decision 0005](./0005-generated-views.md) — *"the draw.io export
is a one-way draft; nothing imports it back"* — and keeps the rest of it. **Touches:** `BPROC2.2`,
`DOBJ3.6`, `ACMP8`, `ACMP10`, `P8`, `GAP29`.

## Context

Decision 0005 made the draw.io export one-way so that drawing would never become the entry
point to the model again. Since then the application draws more than it did: views, target
states and every figure of a deep dive come out as draw.io files, and architects keep them,
arrange them and draw on them — the Requester's own observation. What they add there is lost
or retyped. Decision 0005 already left the door open: every shape carries its element
identifier, *"which is the linking contract an import path would need if the question ever
comes back"*. It has come back.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| **Keep the export one-way** | What an architect draws on a kept file is retyped as a proposal page or lost; the model falls behind the pictures people actually present |
| **Import a drawing straight into a branch** | Makes the drawing a writer: a line drawn by habit becomes a relationship nobody decided, which is what `P8` exists to stop |
| **Embed draw.io and link as people draw** | Declined by 0005 for reasons that still hold: it makes drawing the entry point and the editor a product to maintain |
| **A drawing is one more thing Propose reads** (chosen) | The drawing goes where a design page goes: read into a draft, questions asked about what is unclear, nothing applied until the architect ticks it, and the reviewer reads it beside the merge log |

## Decision

A draw.io drawing is a source Propose reads, as a page is. What the application drew is known
by its stamp; everything else is proposed, typed from its shape by the metamodel's notation or
asked about; a shape taken out of a drawing is never a deletion unless the architect says so.
The drawing is kept with the proposal as its source, and never as a diagram of the model.

## Consequences

- The export is no longer one-way, and `P8` holds unchanged: every diagram of the model is
  still generated, and a relationship comes from a drawing only through a recorded human decision.
- The stamp (built 2026-09-26) becomes a contract: its attributes may be added to, never
  renamed, or a drawing kept today stops being read tomorrow.
- A drawing from nothing — no stamp at all — is read too, every shape matched by name as a
  page's rows are, so an architect can start a proposal from a picture.
