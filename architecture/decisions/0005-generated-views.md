# 0005 — Generated views, not a diagram editor

_[← Decisions](./README.md)_

**Status:** Accepted, 2026-09-05; its one-way export superseded by [decision 0026](./0026-a-drawing-comes-back-as-a-proposal.md) (2026-09-26). **Touches:** `ACMP8`, `ASVC6`, `P8`.

## Context

The owner asked whether draw.io could be integrated so architects draw
diagrams that look like architecture diagrams, link shapes to elements, and
get suggestions of matching elements while drawing, to soften the entry
barrier for new architects. A second thought was to build basic diagramming
in the tool to avoid depending on an external library.

Facts checked against the draw.io source: it is Apache-2.0 and self-hostable
as static files; its embed mode is a client-side postMessage protocol (`init`,
`load`, `merge`, `autosave`, `configure` with custom libraries); ArchiMate 3
stencils are built in; Visio `.vsdx` imports in the browser. So the
integration was feasible.

## Decision

No diagram editor, embedded or home-built, and no hand-drawn diagrams in the
repository. Diagrams are **generated** from the model through one view model
and several renderers: Mermaid in the notation this repository's own
architecture documents use, embedded in answer documents and on the Element
and Impact pages; later a draft draw.io file with ArchiMate stencils that an
architect opens in their own tool to reuse and arrange. Every generated shape
carries its element identifier and a link, which is the linking contract an
import path would need if the question ever comes back.

## Why

- **The problem was never diagrams, it was diagrams as the store.** The current EA tool
  is a drawing tool with a repository behind it that nobody queries. An
  embedded editor with linking would reintroduce the same shape: a drawing
  first, a model as by-product. Generated views keep the model first and
  still give architects a picture (principle `P8`).
- **The entry-barrier argument is a hypothesis.** The people who produce
  content are few and skilled; the consumers want answers. An answer that
  arrives as a document with a proper diagram lowers the barrier for the
  many, at a fraction of the cost.
- **A diagram editor is a deep product.** Connectors, routing, containers,
  snapping, undo, export, stencils: building one is months, then maintenance
  forever. Vendoring draw.io was the sane way to have one, but the value
  sits in the linking and the views, not in the editor.
- **Independence comes from the format, not the tool.** Mermaid renders in
  any Markdown viewer and in the archreator portal; draw.io XML is open and
  Visio-convertible. Both outputs are files the architect owns.

## Alternatives

- **Embedded draw.io with linking and suggestions** — feasible (about ten
  days in three stages); declined because it makes drawing the entry point.
- **Home-built basic diagramming** — declined; if "basic" means generated
  views with light annotation, that is this decision.
- **Keep the force-directed graphs only** — declined; architects do not read
  them as architecture (assessment `ASM7`).

## Consequences

- Notation becomes data in the pack (glyph, stereotype, ArchiMate element per
  type), so a framework brings its own drawing convention.
- The Mermaid renderer is bundled with the app; no external request.
- The draw.io export is a one-way draft. Nothing imports it back, and no
  relationship is created from a drawing without a recorded human decision.
