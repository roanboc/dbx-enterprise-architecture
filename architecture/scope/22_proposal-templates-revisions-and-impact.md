# Project Scope — Proposal Templates, Revisions and Impact

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/great-franklin-30i81n`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 21.
**Target plateau:** `PLAT4` Governed change, its intake.
**Gap:** `GAP23` **A proposal is read in one shape, once, and nobody sees what
it touches**, opened by this initiative.

The Requester asked what to build next and named it: an architect proposes an
architectural change in a template of their own, and the application works out,
through its agent, which of the elements the proposal names already exist, which
are new, and how both land on the target branch, where the change is analysed
and specified further. The organisation's own templates are not available yet,
and the repository is public, so the Requester asked for **a standard ArchiMate
template as the reference**.

## What the assessment found

**Propose works, for one document shape and one pass.** A page in the Proposal
Template becomes a reviewed change set on a branch: elements are matched by
identifier, then by name, near names are flagged rather than linked, and
relationships are checked against the metamodel. Three things keep it from what
was asked.

1. **One shape.** The column words the reader understands are fixed in code
   (`ELEMENT_HEADERS` in `src/ea/agent/proposal.py`), every table needs a Type
   column, and the one template the application offers is typed in the
   higher-education pack's names. An organisation's own template, or a template
   in another framework, is readable only by the hosted model, and only as free
   text.
2. **One pass.** A proposal is applied once. Handing a revised page to the same
   branch is not an operation the application knows: nothing records that it
   revises the last one, a changed description on an element the last pass
   created is not carried, and a row the architect removed from the page stays
   on the branch without anyone being told.
3. **Nothing says what the change touches.** Plateau `PLAT4` promises change
   sets with *an impact assessment*; there is none. An element marked for
   decommissioning does not say what depends on it, a new element connected to
   nothing that exists is not flagged, and the reviewer reads rows in grids
   with neither the page the change came from nor a picture of it. The proposal
   record is written with the branch and never read back.

**Four defects were found with it and fixed directly**, each with a unit test
first, because each sits inside an element the model already names and none
changes what the model claims:

| Defect | Where | Fixed in |
| ------ | ----- | -------- |
| The hosted reader's list of what the sources do not say was cleared before anyone read it | `ProposalService.resolve` | `fix(propose)` — kept beside the pushback, shown, saved with the proposal |
| A revised page applied to the same branch created every new element a second time: it was matched on the branch the reader stood on, not the one it was written to | `ProposalService.apply` | `fix(propose)` — analysed, re-checked and applied on the target branch |
| Every reader of an organisation shared one Ask conversation: its history, its grounding record and its Reset | `AppContext.agent` | `fix(ask)` — one conversation per reader and session |
| A merge that failed part-way left half the change on `main` and gone from the branch | `merge_branch` | `fix(branches)` — one transaction on both engines |

## The calls made without asking

Under **Ask only what blocks the work now**, these were the agent's to take.
Each is written here so a later word from the Requester overrides it.

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Which ArchiMate?** | The ArchiMate 3.2 core, as the ArchiMate Core pack already carries it (adopted — the Requester's "standard ArchiMate template") | The reference template names that pack's types and relationships and nothing else. It ships beside the pack it is typed in, and the existing template moves beside the higher-education pack, so a template's type names stay with their framework (`P5`) |
| **How does a template say how it is read?** | **From the metamodel first, declared second** | A table under a heading that names a type — its name or its plural, *Application components* — holds that type, with no Type column needed; a column whose header names a field or an attribute of the metamodel — *Owner*, *Criticality* — fills it. A template declares, in its front matter, only what differs: *Systems* reads as Application component. A well-named template needs no declaration at all |
| **Where do an organisation's own templates live?** | In the store, per organisation, next to its proposals | An organisation's template is internal and never belongs in a public repository. The ones the repository ships are **starters**, offered the way initiative 21 offers a metamodel, and a copy is the organisation's to change |
| **What does a revision do?** | It **updates what the last pass wrote and never duplicates it** | A filled cell overwrites, a blank cell never empties a field (the rule initiative 20 set for bulk edit), and a row the new page no longer carries is **listed**, not deleted — the architect unticks it off the branch. Each pass is kept as a revision of the one before |
| **Does the impact stop Apply?** | **No.** It informs, like the reader's own finding | It is shown before Apply, stored with the proposal, and read by the reviewer. The pushback rule of initiative 5 stays the one thing that stops Apply |
| **Can a proposal retire a relationship?** | Yes: the Relationships table gains **Target state** | `decommission` on an existing relationship is written to the branch like any other change, and reviewed with it |

Five more were taken while building, after the gate, and are recorded the same way:

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Who keeps a template for the organisation?** | An admin (adopted — templates are the organisation's configuration, like its feeds and its reviewers) | A new role action, `manage_templates`. An architect needs no kept template to propose: a page's front matter travels with it |
| **The page names one template, the picker another** | The page wins | A template's reading is in its front matter, which travels with the document. The picker is for a page that names none — one exported from a wiki, where front matter does not survive |
| **Does a revision rewrite an existing element's description?** | Only one the proposal itself created on the branch | A template asks for a short description where an element exists; overwriting `main`'s text with it would lose what `main` holds. States, the work package, the note and filled attribute cells still apply |
| **How far does the impact walk?** | Two steps, upstream and downstream, each path in one direction | Mixing directions reaches everything that shares a platform with the element — every system one database realises — which buries what matters. The gap note on weighting stands |
| **Is a proposal's revision found by title?** | The latest applied proposal of the same title on the same branch | Two different designs on one branch stay two proposals; a renamed page starts a new one, which the architect sees in the preview |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `BPROC2.2` | **Hand in a proposal** | Takes a page in any template the organisation declares, is repeated onto the same branch as the design matures, and ends with the impact of the change in front of the architect |
| `BPROC2.4` | **Review a branch** | The reviewer reads the proposal the rows came from, its revisions, its impact and a generated view of the change, beside the merge log |
| `DOBJ3.6` | **Proposal** | Kept in revisions, each naming the template it was read with, the reader's own finding and the impact assessed when it was applied |
| `DOBJ3.9` | **Proposal template** | **New.** A Markdown document an architect fills in, and how the application reads it |
| `DOBJ3.10` | **Change impact** | **New.** What a change set touches beyond itself |
| `ASVC9` | **Propose** | Any template, revisions on the branch, the impact and the change drawn before Apply; `ea propose` and `ea templates` |
| `ASVC7` | **Branches and merge** | The reviewer reads the proposals, the impact and the change drawn beside the merge log; a merge is one transaction |
| `ACMP10` | **Proposal agent** | Reads with a template's reading, on the branch it is for; the template service beside it |
| `ACMP3` | **Repository and graph services** | Gains the change impact |
| `ACMP5` | **Agent** | One conversation per reader; tools for allowed relationships and a branch's changes, states in every element |
| `ACMP7` | **Command line** | `propose` and `templates list/keep/delete/check` |
| `ROLE1`, `ROLE4` | **Admin**, **Reader** | The admin keeps the organisation's templates; a reader downloads them |
| `GAP23` | **A proposal is read in one shape, once, and nobody sees what it touches** | Opened by this initiative under `PLAT4`. Defined in [1_target-state.md](../6_transition/1_target-state.md) |

No stakeholder, driver, goal or principle moves.

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change — aligned.** The change serves `G1` (impact is answered from the model rather than worked out by hand), `G2` and `G5` (a template is configuration, in any framework), and stays inside `P3` (the agent drafts, the architect ticks, a reviewer approves), `P5` (type names live with their pack, never in `src/`), `P6` (the reader cites identifiers the tools returned) and `P8` (the view of a change is generated). |
| 2_business | [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC2.2` and `BPROC2.4` re-worded as above. No new process, service or role. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.6` widened, `DOBJ3.9` and `DOBJ3.10` added. [2_conceptual-data-model.md](../3_information/2_conceptual-data-model.md): PROPOSAL TEMPLATE added. [3_logical-data-model.md](../3_information/3_logical-data-model.md): table `proposal_template`, and `proposal` gains `template_id` and `revises`. |
| 4_application | Aligned after Understanding: [1_application-services.md](../4_application/1_application-services.md) re-words `ASVC9` and `ASVC7`; [2_application-components.md](../4_application/2_application-components.md) re-words `ACMP3`, `ACMP5`, `ACMP7` and `ACMP10`, with `ACMP10` using the view generator (`ACMP8`) and the command line using `ACMP10`. No component is added: the template service sits with the proposal agent it serves, the change impact with the graph services. |
| 5_technology | **No change.** Same process, same store, one more table in `ea_governance`. |
| Transition | `GAP23` opens under `PLAT4` and is marked in flight. |

## Delivered

Built on 2026-09-24 on the branch named above, each work package with its unit tests first:

- **WP1.** `src/ea/services/templates.py`: the front matter, the reading against the
  metamodel, the check, the starters and `TemplateService`; table `proposal_template`
  per organisation, copied with an organisation and logged on every change;
  `packs/archimate_core/proposal-template.md`, the reference, and
  `packs/higher_education/proposal-template.md`, moved from `templates/`; the Propose page's
  template picker, and for an admin the templates the organisation keeps.
- **WP2.** A revision recognised on the branch and recorded as `proposal.revises`; what the
  page no longer carries listed; attribute columns written, blank cells ignored; relationship
  target states, `decommission` included; the page kept with the proposal;
  `ea propose` and `ea templates`.
- **WP3.** `src/ea/services/impact.py` and `ChangeImpact`: reached, dangling, isolated and
  reviewers, bounded; shown on the Propose preview and kept with the proposal.
- **WP4.** On the Branches page, beside the merge log: the proposals the branch came from,
  pass by pass, with the page as handed in; the change drawn; what it touches on `main`. The
  Propose preview draws the change before it exists (`view_of_change`).
- **WP5.** The hosted reader is given the template's reading and seven read tools, two of
  them new (`allowed_relationships`, `branch_changes`); every element a tool returns carries
  its states and work package; `propose_view` asks the store rather than the in-process graph.

Tests: `tests/test_templates.py`, `tests/test_change_impact.py`, and the revision,
attribute and retirement cases in `tests/test_proposal.py`, each on both engines.

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-24 | This document, the draft ArchiMate reference template (`packs/archimate_core/proposal-template.md`), `BPROC2.2` and `BPROC2.4` in [2_processes-and-services.md](../2_business/2_processes-and-services.md), `DOBJ3.6`, `DOBJ3.9` and `DOBJ3.10` in [1_data-objects.md](../3_information/1_data-objects.md) with the [conceptual](../3_information/2_conceptual-data-model.md) and [logical](../3_information/3_logical-data-model.md) models, `GAP23` and step 1l on the roadmap, and the strategy layer's "no change" — each linked on the branch, in the session. The calls made without asking were put to the Requester with them. The Requester's word was *"Yes, implement"* |

## Plateaus

| Plateau | State |
| ------- | ----- |
| **Baseline** (before) | A page in one template, typed in one pack's names, becomes rows on a branch once; nothing assesses what those rows touch, and the reviewer reads grids |
| **Target** | A page in any declared template — the ArchiMate reference, a pack's own, or the organisation's — becomes rows on a branch, and a revised page updates them; before Apply and again at review, the change says what depends on what it changes, what it leaves dangling and who must review it, with the page it came from and a generated view of it |

## Work packages and deliverables

### WP1 — Templates as data, and the ArchiMate reference

- **Deliverables:** `packs/archimate_core/proposal-template.md` (the reference:
  sections per ArchiMate layer, a Relationships table with target state, views,
  decisions and open points); the existing template moved to
  `packs/higher_education/proposal-template.md`; the reading of a template
  (headings and columns against the metamodel, then the front matter's
  declarations) replacing the fixed vocabulary in `src/ea/agent/proposal.py`;
  table `proposal_template`, a template stored per organisation, uploaded and
  downloaded on the Propose page, the shipped ones offered as starters; a
  template checked against the organisation's metamodel, naming every heading or
  column it cannot place.
- **Outcome:** an organisation proposes in its own document shape, and the stub
  reader — no model key — reads it completely.

### WP2 — Revisions on the branch

- **Deliverables:** a proposal applied to a branch that already holds one
  recorded as its revision (`proposal.revises`); a filled cell updating what the
  last pass created, a blank one never emptying it; rows the new page no longer
  carries listed on the preview; relationship target states; `ea propose <file>
  --branch <b> [--template <t>] [--apply]`.
- **Outcome:** the design is specified further on the branch, pass after pass,
  and the branch always matches the latest page.

### WP3 — The change impact

- **Deliverables:** a change-impact service over a change set (a proposal
  before Apply, or a branch): for every element it changes, decommissions or
  merges, what depends on it within two steps and is not itself in the change;
  every relationship left pointing at an element being decommissioned; every new
  element connected to nothing that exists; the reviewers the touched types
  need. Read by the store, paged (decision 0019). Shown on the Propose preview,
  kept with the proposal.
- **Outcome:** the architect sees what a change touches before applying it.

### WP4 — What the reviewer reads

- **Deliverables:** on the Branches page, the proposals a branch came from — the
  page as handed in, its revisions, the reader's finding and the impact — and a
  generated view of the change set with its state markers, on the Propose
  preview as well.
- **Outcome:** a reviewer judges the change against the design it came from,
  not only against its rows.

### WP5 — What the reader can ask

- **Deliverables:** the hosted reader given the template's reading, and the
  tools to place a new element — what may relate two types, an element's
  neighbours and impact, what the branch already changes; states and the work
  package in every element the tools return.
- **Outcome:** the reader proposes relationships the metamodel allows and
  links to what the design depends on, rather than only to what it names.

## In scope / out of scope

| In scope | Out of scope (gaps, candidate future work) |
| -------- | ------------------------------------------- |
| Markdown, text and CSV templates, pasted, uploaded or linked | Word, PDF and wiki pages read directly (`GAP20` — a source reached over a protocol) |
| Templates declared per organisation, and the two the repository ships | A template editor on a screen: a template is a document, edited where documents are |
| Revisions of a proposal on one branch | Moving a proposal between branches; a rebase of a branch behind `main` |
| Impact within two steps, of the elements a change set changes | Impact weighted by relationship type, criticality or cost |
| The reviewer's view of the proposal, its impact and a generated view | draw.io import of a proposal's diagram; the draw.io export is untouched |
| Relationship target states | A proposal that changes the metamodel |

## Gap notes

- **Word, PDF and wiki pages.** The organisation's templates are likely to live
  in one of them. Reading them is the connector work of `GAP20`; until then a
  page is pasted or saved as Markdown, and the template's reading is the same
  either way.
- **Impact by weight.** Two steps along every relationship is a blunt measure: a
  reference data change and a platform decommission read alike. Weighting needs
  the relationship types' direction of dependency declared in the pack, which
  no pack declares yet.
- **Rebase.** A branch a proposal is revised on can fall behind `main`; the
  staleness is shown (initiative 20), not repaired. Rebase remains on the
  branching list initiative 20 left.
