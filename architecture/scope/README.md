# Project Scope Documents

_[← Repository README](../../README.md) · [Enterprise architecture](../README.md)_

One document per delivered (or in-flight) initiative, numbered
chronologically. While the [EA docs](../README.md) describe the
**current** state of the system, each scope document describes one
**change**: what plateau it started from, what it delivered, and what it
deliberately left out.

**ArchiMate viewpoint:** Implementation & Migration (Work Package,
Deliverable, Plateau, Gap).

## The EA-first change process

Every change in requirements follows the same order — the same order the EA
folders are numbered in:

1. **Align the EA first.** Walk the layers top-down and record what the
   change means for each: [1_strategy](../1_strategy/README.md) (does it
   serve an existing goal, or introduce a new driver?) → business (a `Gap`
   row on the front door today) → [3_information](../3_information/README.md)
   (new or changed data objects, flows, storage?) →
   [4_application](../4_application/README.md) (which services, components,
   interfaces change?) → technology (a `Gap` row today). Update the affected
   EA documents in the same change. If the change adds or modifies a
   stakeholder, driver, goal or principle, the initiative becomes strategy
   discovery first, ending at **Direction** approval; implementation follows
   as a separate initiative.
2. **Document the scope.** Add the next-numbered file to this folder
   describing plateaus, work packages, in and out of scope, gaps, and gate
   approvals — before implementation starts, refined as it proceeds.
3. **Pass the gate.** Before any code, the Requester approves the strategy
   and information changes (**Understanding**). At Depth 1 that is the only
   gate an ordinary change meets; **Direction** belongs to discovery and to
   the roadmap. Each gate granted is recorded in the scope document's
   Approvals table — who approved, when, and what was shown. One that was not
   granted gets no row: the table records what happened, not a census of what
   did not. An approval can be granted in the conversation or in a reply on
   the pull request.
4. **Implement.** Only then write the code, keeping the scope document and
   EA docs in sync with what is actually delivered.

An interpretation the agent adopted is recorded where it applies, in that
row's `Source` cell as `adopted — <the call>`, and the document stays `◐`: a
later word from the Requester overrides it, which an approved fact does not.
A question reaches the Requester only when the answer changes what gets built
now and nothing in the model settles it. Single consequential calls smaller
than an initiative are in [the decisions index](../decisions/README.md).

**A merged scope document is never rewritten**: it is the record of what was
approved on a date and against what information. When the current-state
documents drift from reality after a run of initiatives, restating them is
its own initiative with its own Understanding.

## Initiatives

| #   | Scope document | Delivered as | Summary |
| --- | --------------- | ------------ | ------- |
| 1   | [1_curriculum-poc.md](./1_curriculum-poc.md) | the working branch (in flight) | The PoC: generic metamodel-driven repository on DuckDB with the higher-education pack, CSV ingestion, browse and edit, metamodel manager and a grounded agent, on the curriculum slice of the institution's content |
| 2   | [2_generated-views.md](./2_generated-views.md) | the working branch (built, demo pending) | Generated architecture views in archreator-style Mermaid, agent answers as documents with diagrams, and a draft draw.io export over the same view model; no hand diagramming |
| 3   | [3_admin-notation-and-arrangeable-views.md](./3_admin-notation-and-arrangeable-views.md) | the working branch (built; demo pending) | Notation editor with live preview and domain colours as pack data; draggable shapes on generated views exported to draw.io without saving; the Ask page view-first with copyable Markdown; grouped, overlap-free graphs; roles documented, none enforced |
| 4   | [4_branches-and-target-state.md](./4_branches-and-target-state.md) | `main` (in flight) | Model branches as overlays merged with base versions; current versus target state on every artefact, analysed by work package |
| 5   | [5_propose.md](./5_propose.md) | `main` (in flight) | Propose: a document, file or link becomes a branch through an agent that links existing elements, adopts new ones and pushes back when the sources are insufficient; the Proposal Template |
| 6   | [6_search-bulk-edit-and-health.md](./6_search-bulk-edit-and-health.md) | `main` (built 2026-09-06; demo pending) | Word-by-word search over names, descriptions and attributes with ranking; bulk edit from Browse; the Health page with freshness per source and completeness per type |
| 7   | [7_roles-and-review.md](./7_roles-and-review.md) | `main` (built 2026-09-06; demo pending) | Roles enforced (Admin, Architect, Reviewer, Reader, Agent) with a debug persona switcher locally; review before merge with reviewers per element type; the business and technology layers written, views at the top of every layer document |
| 8   | [8_two-gates-and-readable-views.md](./8_two-gates-and-readable-views.md) | branch `claude/archreator-validation-feedback-gt00b7` | archreator 0.3 applied: two gates, no row for a gate that was not granted, the open-questions log retired. The glyphs distinguish the element types, so 273 nodes drop the stereotype and every document opens with a legend; nine documents stop stacking their diagrams ahead of their tables. **No claim about the repository changes** |
| 9   | [9_import-template.md](./9_import-template.md) | the working branch | Import page download of a generic CSV contract template archive for prospective adopters |
| 10  | [10_markdown-editor-and-preview.md](./10_markdown-editor-and-preview.md) | the working branch | Markdown authoring controls and preview for Markdown-capable fields, with Mermaid rendering in reader views |
| 11  | [11_gui-review-grey-theme-and-editor-modes.md](./11_gui-review-grey-theme-and-editor-modes.md) | the working branch | GUI review: editor Edit/Split/Preview modes, grey theme, process-ordered actions, one destination field each on Propose, current state as the one indicator, persona cleanup, reader-view Mermaid and Impact selector fixes |
| 12  | [12_navigation-flow-and-screenshot-order.md](./12_navigation-flow-and-screenshot-order.md) | the working branch | Navigation grouped into Home, Discover, Contribute and Manage, with README screenshots ordered to match |
