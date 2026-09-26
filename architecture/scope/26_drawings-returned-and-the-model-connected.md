# Project Scope — Drawings Returned and the Model Connected

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/admiring-bell-wj7ocn`; drafted 2026-09-26 for **Understanding**.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 25, and the draw.io
stamp built the same day. **Target plateaus:** `PLAT1` The repository running locally, extended;
`PLAT4` Governed change, its intake; `PLAT5` Semantic front doors, its tool server.
**Gaps:** `GAP29` **A drawing that comes back is read by nobody**, opened; `GAP7` **No tool
server for external agents** and `GAP28` **What the enterprise's other systems say is not read**,
restated and brought forward to a step of their own (1o).

The Requester asked for the last changes before the application moves to Databricks and real
content. Architects keep the draw.io files the application exports and draw on them, so what
comes back should be read: what the application drew told apart from what a person added, and
the changes assessed. And the assistant should reach beyond the model — the enterprise's other
repositories, applications and documents — over the Model Context Protocol, because an
assistant with the enterprise's data and access to its systems is what other tools lack.

The stamp that makes a drawing readable is inside an element the model already names (`ACMP8`,
the view generator) and was built directly, on the same day: every cell the application draws
carries `ea_origin`, the export's identifier and draw.io's own tag; the file carries the export,
organisation, branch and time; a shape keeps the name it was exported with; an edge names its
relationship. This initiative is what reads it back, and what connects the model both ways.

## What changes

**1 — A drawing comes back as a proposal.** Propose accepts a draw.io file beside a page. The
file is read by its stamp against the model as it is now:

| In the drawing | What the assistant does |
| -------------- | ----------------------- |
| A stamped shape or line, unchanged, moved or resized | Nothing — arranging a picture is not a change |
| A stamped shape whose label a person edited | Asks: a rename, or only the drawing's label? |
| A shape without the stamp | A new element — typed from its shape by the metamodel's notation where one type is drawn that way, asked about where several are or none; matched by name to an element that exists, as a page's rows are; a plain text box is asked about as *a note, not an element* first |
| A line without the stamp between two elements | A new relationship — the one the metamodel allows between their types, asked about where it allows several |
| A stamped shape or line a person took out | Asks: out of the model, or only out of the picture? Never a deletion unless the architect says so, and then a retirement, as everywhere |
| Two shapes carrying one identifier (a copy) | The copy is read as a shape a person added |
| A file from another organisation | Refused, and said plainly |
| A file with no stamp at all | Read as a drawing from nothing: every shape matched by name and typed from its shape, as above |

The questions are the conversation Propose already holds (initiative 24): a few at a time, with
the choices the model allows. Everything after is Propose as it is — the impact, the merge log,
Apply to a branch, the review. The drawing is kept with the proposal as its source, as a page is,
and a revised drawing handed to the same branch is a revision. Decision
[0026](../decisions/0026-a-drawing-comes-back-as-a-proposal.md) records why the export stops
being one-way.

**2 — The model served to other agents (`GAP7`).** A tool server exposes the assistant's read
tools — types, search, an element, neighbours, trace, impact, target state, the deep dives kept —
over the Model Context Protocol. An architect's own agent, in their editor or on the platform,
connects and asks the model directly, with the identifiers the application gives. It acts as the
person who connected it: their organisation, the branch they choose, their role. It writes
nothing. On a laptop it runs from the command line; on Databricks it is served by the platform,
behind the same sign-in as the pages.

**3 — The assistant reads the enterprise's other systems (`GAP28`).** An admin connects, per
organisation, a system that answers the protocol — a code host, a wiki, a CMDB, the project
portfolio tool — saying what it speaks for (the element types it masters, the link addresses it
answers for) and which of its read-only tools the assistant may call. Ask, a deep dive and
Propose's questions may then read it, as the person they are answering:

| Where | What it reads |
| ----- | ------------- |
| **Ask** | What a connected system says about an element in the question, when the question needs it |
| **A deep dive** | The pages its key elements link to, where a connected system answers for their address, and what the system that masters an element says of it; its inconsistencies gain *the model and its source disagree* |
| **Propose** | What a connected system says about an element a draft changes — *the CMDB lists this server as retired* — offered as a choice, never applied by itself |

What a system says is cited as that system's — its name, its own reference, when it was read —
never as an element identifier, and never written into the model. A disagreement is a finding;
turning it into a change is an architect's proposal.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Is a drawing read without a model?** | Adopted — yes | The stamp, the notation and the metamodel's allowed relationships settle most of it; a hosted model only reads a label in a person's own words |
| **What does a shape taken out mean?** | Adopted — asked, and *only out of the picture* is offered first | A picture is a selection; leaving something out of one is not a decision about the enterprise |
| **Where does a new shape's type come from?** | Adopted — the metamodel's notation, read in reverse: the ArchiMate kind a type is drawn as | No type name enters the code (`P5`); a pack that draws two types the same way gets a question, not a guess |
| **Is the drawing kept?** | Adopted — with the proposal, as its source; never as a diagram of the model | `P8` holds: every diagram of the model is still generated |
| **Which tools does the tool server offer?** | Adopted — the read tools Ask uses, and the deep dives kept; nothing that writes | Writing through an outside agent is `P3`'s question, and a later one |
| **Whose identity does an outside agent carry?** | Adopted — the person who connected it | The same role, organisation and branch scoping the pages apply; an outside agent sees no more than its person |
| **Does `P6` hold for an outside agent?** | Adopted — every result carries the identifiers, and the server tells the agent to cite them | The application cannot check an answer it never sees; the identifiers are what it can guarantee |
| **Whose identity reaches a connected system?** | Adopted — the reader's own where the platform passes it on; otherwise a credential the platform holds, used only for the roles the admin names | A credential is never in the store; a system that trusts only the app sees one reader, and the admin decides who that serves |
| **Is what a system says trusted?** | Adopted — no: it is data, read and cited, never an instruction | The assistant's only write path is a draft an architect applies, so what a system says can mislead an answer but cannot change the model |
| **How much is read?** | Adopted — a bounded number of calls per answer and a bounded size per result, as every read is (decision [0019](../decisions/0019-the-size-the-application-declares.md)) | A slow or large system shortens an answer; it does not stall one |
| **Is `GAP20` closed?** | No | Reading a system for an answer is not loading it into the model. A connected system is the configuration a source reached over the protocol will use later |
| **Why now, rather than with step 5?** | The Requester's word — *"final changes before I move this to Databricks"* | Neither the tool server nor a connected system needs the projection or real content; both are proved on a laptop and served on the platform with `PLAT2` |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `BPROC2.2` | **Hand in a proposal** | A drawing is handed in as a page is, read by its stamp |
| `BPROC3` | **Answer an architecture question** | A deep dive reads the organisation's connected systems and cites them as theirs |
| `ACT6`, `ROLE5` | **Architecture assistant**, **Agent** | May read connected systems as the person answered; may not write to one or take what it says for the model's |
| `ROLE1` | **Admin** | Connects the organisation's systems |
| `ROLE4` | **Reader** | May read the model through an agent of their own, connected to the tool server |
| `DOBJ3.6` | **Proposal** | A drawing is one of its sources, kept whole |
| `DOBJ3.11` | **Deep dive** | Its references name what a connected system said |
| `DOBJ3.12` | **Connected system** | Added |
| `GAP7`, `GAP28`, `GAP29` | The three gaps above | `GAP7` and `GAP28` restated and brought forward; `GAP29` opened; step 1o on the sequence |
| decision 0026 | **A drawing comes back as a proposal, never as the store** | Proposed; supersedes one consequence of decision 0005 once adopted |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned — no change.** Serves `G6` **The model is served, not exported** (the tool server) and `G1` **Query the architecture sustainably** (answers that read the enterprise's systems), and prepares `G7` **A source is connected, not piped**. Stays inside `P3` (nothing from a drawing or a system lands without an architect), `P5` (a shape's type comes from the notation), `P6` (external facts cited as the system's, element identifiers checked as today) and `P8` (a drawing is a source, never a diagram of the model). **One stop, named:** decision 0005 says the draw.io export is one-way — a contradiction, resolved by [decision 0026](../decisions/0026-a-drawing-comes-back-as-a-proposal.md), which this gate adopts or refuses. When built, `ASM11` and `G6` are restated as half reached. |
| 2_business | [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC2.2`, `BPROC3`. [1_actors-and-roles.md](../2_business/1_actors-and-roles.md): `ACT6`, `ROLE1`, `ROLE4`, `ROLE5`. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.6`, `DOBJ3.11`; `DOBJ3.12` **Connected system** added, with what it speaks for, answers for and is cited by. [3_logical-data-model.md](../3_information/3_logical-data-model.md): table `connected_system` in the `ea_governance` schema, beside the feeds. No change to `proposal`: a drawing is one more entry in `sources_json`. |
| 4_application | To align after Understanding: `ASVC9` **Propose** reads a drawing; a service for the **tool server**; `ASVC5` and `ASVC14` read connected systems; `ACMP10` **Proposal agent** gains the drawing reader; `ACMP5` **Agent** gains the connected systems' tools beside its own and cites them apart; a component for the tool server; `ACMP6` gains the drawing on Propose and a Connected systems list under Manage; `ACMP7` gains `ea mcp`; `ACMP12` gains who may connect a system. |
| 5_technology | To align after Understanding: the Model Context Protocol's Python library in the runtime; on Databricks, the tool server behind the app's sign-in and a connected system reached through what the platform offers for it, with the reader's identity where it passes one on. Recorded as a decision when chosen. |
| Transition | [1_target-state.md](../6_transition/1_target-state.md): `GAP7` and `GAP28` restated, `GAP29` opened. [2_sequence.md](../6_transition/2_sequence.md): step 1o, before step 2; step 5 keeps `GAP6` and serves `GAP7` on the platform. |

## Approvals

**No gate has been granted.** This document stops at **Understanding**: it is shown to the
Requester with the business and information rows it changes, decision 0026 and the roadmap rows,
each linked on the branch. Nothing of work packages 1 to 3 is built until that word is given.

## Work packages

| WP | Delivers |
| -- | -------- |
| 0 — The stamp (built 2026-09-26, inside `ACMP8`) | Every cell of a view's and a deep dive's draw.io file stamped; the file's own data; the exported name on a shape; the relationship on an edge |
| 1 — The drawing read | The stamp read against the model; the table above as rules; shapes typed from the notation; the questions in Propose's conversation; the drawing kept as the proposal's source; a drawing handed in on the Propose page and on `ea propose` |
| 2 — The tool server | The read tools over the protocol, scoped by the caller's organisation, branch and role; `ea mcp` on a laptop; the same server on the platform behind the app's sign-in |
| 3 — Connected systems | The `connected_system` table on both engines; the admin's list; the systems' read-only tools offered to the assistant, bounded, as the reader; cited apart from element identifiers; read by Ask, a deep dive and Propose's questions |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| A draw.io drawing handed in on Propose, stamped or not | Other drawing formats — Visio, a picture of a whiteboard |
| The read tools over the protocol, as the person who connected | Writing through an outside agent — a proposal handed in by one |
| Reading a connected system for an answer, a deep dive or a question | Loading what a system says into the model (`GAP20`); writing to a system |
| Systems that answer the Model Context Protocol | A system that answers only its own API, until something puts the protocol in front of it |

## Gap notes

- **Loading from a connected system (`GAP20`).** A connected system already says what it masters;
  loading what it says through the feed pipeline — validation, provenance, a branch, review — is
  the step after, and waits on the source-of-record table as step 3 does.
- **An outside agent that proposes.** Handing in a proposal from an agent in an editor is Propose
  over the protocol; it needs a person's tick on the other side of it, and is left until an
  architect asks for it.
- **Proving it on the platform.** The tool server's and the connected systems' platform half —
  sign-in, the reader's identity passed on — waits with the rest of `PLAT2`'s workspace run.
