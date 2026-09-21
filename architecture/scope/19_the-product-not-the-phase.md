# Project Scope — The Product, Not the Phase

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Motivation, and Implementation & Migration.
**Delivered as:** branch `claude/enterprise-arch-motivation-ilfgqo`, started
from `main` after initiative 18 merged.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 18.
**Kind:** **strategy discovery** — the change adds and modifies drivers,
assessments, goals and principles, which is the verdict step 1c of
`align-change-through-layers` reaches and hands to `discover-strategy`. The
whole initiative is therefore documents. **No code changes behaviour**; the two
source edits it does carry are comments and prose that had stopped being true.

The motivation layer said three things the Requester says are wrong. It called
enterprise architecture **a data-integration problem**, which is half of it and
the half that excuses a model nobody validated. It said nothing about **why a
standard EA product is not the answer**, although `ASM1`, `ASM2` and `ASM7`
each argued a piece of it. And it was written as the motivation of **a proof of
concept** — a goal to show something within a month, an outcome named after the
first slice of content loaded — when the architecture describes the product,
whatever phase the product is in. At the same time the model has to stop naming
the organisation it was built for, in every document outside the coded test
scenario.

## The calls the Requester made

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **What does the model claim about MCP and agents on the platform?** | **Serve and consume** | Two claims, not one. The model is *served* — a projection on the platform to join to, and a tool server an external agent connects to over the Model Context Protocol (`G6`). And sources are *consumed* over a protocol the platform already speaks, rather than through a pipeline written per source (`G7`) |
| **Do the new drivers open build work now?** | **Motivation and roadmap only** | The goals are stated and given gaps to live in — `GAP6` and `GAP7` under `PLAT5`, the new `GAP20` under `PLAT3`. Nothing is built in this initiative. Each still enters the change process and stops at its own Understanding |
| **How far does "no organisation named" reach?** | **Documents and stakeholders** | `architecture/`, `README.md` and `AGENTS.md` go sector-neutral, and the stakeholders and actors with them. `packs/higher_education/`, `data/sample/` and `tests/` keep their wording: they are the coded test scenario. Merged scope documents keep their text and their filenames, because a merged record is history |
| **What happens to the phase-framed goals?** | **Delete outright** | `G4`, `OUT1` and `OUT2` are retired rather than restated. Their identifiers stay retired. With both outcomes gone no Outcome remains, so the family's section and its legend node go with them — each goal's own `Measured by` cell carries the measure (adopted — the consequence of the call, not a second decision) |

## What changes in the model

| Identifier | Element | What it says, and why it is not an existing one |
| ---------- | ------- | ----------------------------------------------- |
| `DRV1` | **EA is a modelling problem and a data problem** — restated | Was *EA is a data-integration problem*. The identifier stays: a driver renamed is the same driver, and the evidence behind it did not change — what changed is that it now carries both halves and says why the answer is better ingesting and serving rather than a better drawing surface |
| `DRV5` | **The architecture has to be consumable where the enterprise already works** — added | `DRV2` is about an agent needing tools. This is about a data product, a pipeline or another solution reading the architecture as governed data on the platform. Different consumer, different mechanism, same complaint about exports |
| `STK6` | **Platform and agent builders** — added | Nobody in the stakeholder list held `DRV5`. `STK3` Solution architects read the model to design with it; `STK6` builds things that read it without a person in the loop |
| `ASM10` | **Standard EA solutions are not fit for purpose** — added | The one the Requester asked for. `ASM1` says the current tool cannot host integration, `ASM2` that a catalogue is not a graph, `ASM7` that a graph layout is not a diagram. The general statement — that the products on offer each solve one half of `DRV1` and leave the other outside the product — was never made, so the build-rather-than-buy decision rested on three particular observations |
| `ASM11` | **Nothing serves the model to another solution** — added | States the baseline `G6` is measured from: the model leaves only as a file a person downloads |
| `ASM12` | **Sources are reached by file, not by protocol** — added | States the baseline `G7` is measured from: after initiative 18, a source is still a table somebody else fills |
| `G6` | **The model is served, not exported** — added, **Pending** | `G1` is a person or an in-process agent asking the application. This is a consumer outside the application reading the model where it already works. Its gaps are `GAP6` and `GAP7` under `PLAT5` |
| `G7` | **A source is connected, not piped** — added, **half reached** | A staging feed is already configuration rather than code (initiative 18). A source reached over a protocol is not: `GAP20` |
| `P7` | **Every shortcut is a recorded gap** — restated | Was *Fail fast, keep the long-term goal — the PoC is allowed to be thrown away; the roadmap is not*. The test is unchanged; what went is the clause that made the principle about a phase |
| `G4`, `OUT1`, `OUT2` | **Retired** | `G4` *Show a working PoC within a month* is a phase of delivery, not a property of the product. `OUT1` made one organisation's first content slice the measure of the model. `OUT2` was the granting of a gate, written as an outcome of the architecture. All three sit in the motivation layer's `## Retired` section; their identifiers are never reused |
| `PLAT1` | **The repository running locally** — restated | Was *Local PoC on DuckDB*. A plateau is a state, not a project (`plan-the-transition`), and this one now names the state: the store, the application and the command line on one machine with no platform underneath. Same identifier, same dependencies |
| `PLAT5` | **Semantic front doors** — restated | The projection is said to be there so *any solution joins the architecture to its own data*, and the tool server is named as what it is: the same tools the in-process agent uses, over the Model Context Protocol |
| `GAP7` | **No tool server for external agents** — restated | Kept its name, gained what it costs and what closes it: the existing tools exposed over MCP, under the same roles and the same citation rule (`P3`, `P6`) |
| `GAP20` | **No source is reached over a protocol** — opened, **not started** | The gap `G7` is measured from. Between `PLAT1` and `PLAT3`, with a step of its own (3b) in the sequence, because a gap with no step is a gap with no home |
| `GAP3`, `GAP18` | Restated | `GAP3` said *no real institutional content*; `GAP18` said the services were *sized for the PoC*. Both are the same gap under a name that no longer describes the product |

Nothing else is added. In particular **no new principle**: the new claims are
drivers, assessments and goals, and a ninth principle that only restated `P2`,
`P6` or `P8` would make the set harder to check a change against without
catching anything the set misses.

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares. The request fits it: the
subject is still one application, and its strategy layer stays light.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **The change.** [1_motivation.md](../1_strategy/1_motivation.md): `DRV1` and `P7` restated, `DRV5`, `STK6`, `ASM10` to `ASM12`, `G6` and `G7` added, `G4`, `OUT1` and `OUT2` retired, the Outcome family gone with them, and every stakeholder de-organisation-ed. [README.md](../1_strategy/README.md): the element list and the sentence about whose capabilities these are. [2_value-stream.md](../1_strategy/2_value-stream.md): **no change** — `CAP1` *Architecture management as a data product* and the five stages already describe the product rather than a phase, and `VS1.5` **Answer** already covers a consumer outside the application. |
| 2_business | **Wording only, no element added, removed or re-related.** `ACT1` and `ACT5` said *the university's data and analytics unit* and *the IT division's owners of the institution's metamodel*; `ACT1`'s concern was a demonstration that sells it. Rows that had stopped being true, edited in the same commit. |
| 3_information | **Wording only.** `DOBJ1`'s and `DOBJ2`'s owner cells, the size figure on `DOBJ2`, the classification note that said *the PoC shows them to every signed-in user*, and the layer README's sentence about whose information this is. No data object changes. |
| 4_application | **No change.** `G6` and `G7` are Pending against gaps; no application service or component is added, because nothing is built here. `ASVC12` Source feeds and `ACMP14` Feed runner, from initiative 18, are what `G7`'s reached half already names. |
| 5_technology | **Wording only.** `NODE1` said *the machine where the PoC runs*. No node, runtime or artifact changes. |
| Transition | **The second half of the change.** `PLAT1` and `PLAT5` restated, `GAP3`, `GAP7` and `GAP18` restated, `GAP20` opened and not started, step 3b added to the sequence, and `PLAT3` given the protocol half of how a mirrored type is fed. The two restated rows return to **Direction**, which is the gate this folder passes. |

## Plateaus

| Plateau | State |
| ------- | ----- |
| **Baseline** (before) | A motivation layer that named a phase, argued half of `DRV1`, never said why a bought product does not answer it, and named the organisation it was built for in six documents |
| **Target** (delivered) | A motivation layer that describes the product: why the products on offer do not fit, what the model must be able to do about ingesting and serving, and nothing about who asked for it; a roadmap whose plateaus are states and whose gaps include the two protocols |

## Work packages and deliverables

### WP1 — The motivation layer restated

- **Deliverables:** [`architecture/1_strategy/1_motivation.md`](../1_strategy/1_motivation.md)
  (`DRV1`, `P7` restated; `DRV5`, `STK6`, `ASM10`–`ASM12`, `G6`, `G7` added;
  `G4`, `OUT1`, `OUT2` in a new `## Retired` section),
  [`architecture/1_strategy/README.md`](../1_strategy/README.md).
- **Outcome:** a change can be checked against what the product must be, rather
  than against what a proof of concept had to show by a date.

### WP2 — The roadmap bound to the new goals

- **Deliverables:** [`architecture/6_transition/1_target-state.md`](../6_transition/1_target-state.md)
  (`PLAT1`, `PLAT3`, `PLAT5`, `GAP3`, `GAP7`, `GAP18` restated; `GAP20` opened),
  [`architecture/6_transition/2_sequence.md`](../6_transition/2_sequence.md)
  (step 3b, and step 1 renamed after the state it reaches).
- **Outcome:** `G6` and `G7` each have somewhere their unbuilt half lives, so
  neither reads as a claim about today.

### WP3 — Nothing names the organisation

- **Deliverables:** [`architecture/README.md`](../README.md),
  [`architecture/2_business/1_actors-and-roles.md`](../2_business/1_actors-and-roles.md),
  [`architecture/3_information/README.md`](../3_information/README.md),
  [`architecture/3_information/1_data-objects.md`](../3_information/1_data-objects.md),
  [`architecture/5_technology/1_runtime.md`](../5_technology/1_runtime.md),
  `README.md`, `AGENTS.md`, `src/ea/capacity.py` (a comment).
- **Outcome:** every document outside the coded test scenario reads as the
  product's, and the public repository names no organisation, no sector scope
  and no phase.

## In scope / out of scope

| In scope | Out of scope (gaps, candidate future work) |
| -------- | ------------------------------------------ |
| The motivation layer restated for the product | Building any of `G6` or `G7` |
| The roadmap's plateaus and gaps bound to the new goals | `packs/higher_education/`, `data/sample/` and `tests/` |
| Every document outside the coded test scenario de-organisation-ed | Merged scope documents and decision records |
| `P7` restated without the phase clause | The archreator validators, two minor versions behind the plugin |

## Gap notes

- **`GAP20` opens and stays open.** Nothing is built for it here. Closing it
  needs a source reached over a protocol the platform speaks, put through
  initiative 18's pipeline unchanged — the same validation, report, branch
  targeting, provenance and review — plus the source-of-record table, so a
  connected source knows which types it masters. That table is agreed outside
  this repository and gates the rest of `PLAT3` already.
- **`G6` has two gaps and no initiative.** `GAP6` (the projection and the
  glossary) and `GAP7` (the tool server over MCP) are step 5 of the sequence
  and depend on `PLAT2`, which waits on a workspace run. Naming `G6` does not
  move either forward; it stops the model implying that a downloadable file is
  what serving means.
- **The scope documents still carry the old names.** A merged scope document is
  history and is not rewritten, so initiative 1's filename and the index row
  that quotes it still name a phase and a content scope. The layer documents
  that linked to it now use the initiative's number as the link text, so the
  words do not appear in the model — the file path does. Renaming the file is
  possible and is its own initiative: it rewrites a record, and every merged
  document that links to it would need its target corrected.
- **One example prompt on the Ask page names a sample topic.** It is one of four
  example questions and each names an element of the seeded sample model, which
  is the coded test scenario. Changing it would make the examples not match what
  `make seed` loads.
- **The validators are two minor versions behind the plugin** (`scripts/` are
  copies of archreator 0.4.0's scaffold; the plugin is at 0.6.0, whose document
  shape drops the legend and the `## Relationships` section). This initiative
  follows the shape the repository's own validators and `AGENTS.md` require, and
  does not upgrade either. Upgrading goes upstream first and is its own change.

## Approvals

**No gate has been granted.** This initiative stops at **Direction**: it names
a destination — the model served to other solutions and to external agents, and
sources connected rather than piped — and the order it is reached in. That is
the gate `1_strategy/` and `6_transition/` pass, and it commits the Requester to
a direction rather than to work. Every step on the sequence still enters the
change process and stops at its own Understanding before anything is built.
