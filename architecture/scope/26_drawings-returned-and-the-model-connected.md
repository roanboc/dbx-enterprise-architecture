# Project Scope — Drawings Returned and the Model Connected

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/admiring-bell-wj7ocn`; drafted 2026-09-26, Understanding granted and built the same day; the platform half waits with `PLAT2`'s run on a workspace.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 25, and the draw.io
stamp built the same day. **Target plateaus:** `PLAT1` The repository running locally, extended;
`PLAT4` Governed change, its intake; `PLAT5` Semantic front doors, its tool server.
**Gaps:** `GAP29` **A drawing that comes back is read by nobody**, opened and closed; `GAP7`
**No tool server for external agents** and `GAP28` **What the enterprise's other systems say is
not read**, restated, brought forward to a step of their own (1o) and closed — `GAP7` in code,
`GAP28` for systems reached over the protocol.

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
| **How does a returned file say what was taken out?** | Adopted, while building — the export lists the elements and relationships it drew on the file's own data | A file carries no memory of the export otherwise; a drawing exported before 2026-09-26 is read as additions only |
| **A question left unanswered about a shape taken out?** | Adopted — it does not stop Apply, and changes nothing | Leaving something out of a picture is the likelier meaning; the rename and the note questions do stop Apply, because the drawing says something changed |
| **Where does the tool server run on the platform?** | Adopted — an app of its own in the bundle, on the same store and sign-in ([decision 0027](../decisions/0027-the-protocol-served-by-an-app-of-its-own.md)) | The web application's server stays as it is; an agent connects to the tool server's own address |
| **How much may one answer read from the systems?** | Adopted — eight reads (listing what a system offers counts), twenty seconds each, eight thousand characters of each result | Enough for a question about a few elements; a larger need is a deep dive's, which reads pages the same way |
| **A system that reads as the person, on a laptop?** | Adopted — it is not read, and the answer says why | Only the platform passes a person's identity on; the organisation's credential is the admin's choice for a system that must be read locally |
| **Which pages does a deep dive read?** | Adopted — the ones its subject links to, through the system that answers for each address | The subject is what the reader asked about; the reads are bounded as an answer's are |
| **Is what a system masters compared without a model?** | Adopted — no: a page is compared by the rule that finds a named element nothing joins to; a system's record is read and weighed by the hosted model on Ask and Propose | A record's fields mean what its system says they mean; a rule written for one CMDB would be wrong for the next (`P5`) |

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
| 4_application | [1_application-services.md](../4_application/1_application-services.md): `ASVC9` reads a drawing; `ASVC5` and `ASVC14` read connected systems; `ASVC15` **Tool server** and `ASVC16` **Connected systems** added. [2_application-components.md](../4_application/2_application-components.md): `ACMP10` gains the drawing reader, `ACMP5` the connected systems' tools, `ACMP6` the Connected systems page, `ACMP7` `ea mcp` and `ea systems`, `ACMP12` who may connect a system; `ACMP16` **Tool server** and `ACMP17` **Connected-system reader** added. |
| 5_technology | [1_runtime.md](../5_technology/1_runtime.md): `TSVC8` **Protocol serving and reading** added; `NODE2` hosts a second app, `ART4` carries the protocol's library, `ART6` deploys the tool server. Recorded as [decision 0027](../decisions/0027-the-protocol-served-by-an-app-of-its-own.md). |
| Transition | [1_target-state.md](../6_transition/1_target-state.md): `GAP7` and `GAP28` restated and closed, `GAP29` opened and closed. [2_sequence.md](../6_transition/2_sequence.md): step 1o built, before step 2; step 5 keeps `GAP6` and serves `GAP7` on the platform. [1_motivation.md](../1_strategy/1_motivation.md): `G6` and `ASM11` half reached — the rows kept true, not changed. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-26 | This document; `BPROC2.2` and `BPROC3` in [2_processes-and-services.md](../2_business/2_processes-and-services.md); `ACT6`, `ROLE1`, `ROLE4` and `ROLE5` in [1_actors-and-roles.md](../2_business/1_actors-and-roles.md); `DOBJ3.6`, `DOBJ3.11` and `DOBJ3.12` in [1_data-objects.md](../3_information/1_data-objects.md) and the `connected_system` table in [3_logical-data-model.md](../3_information/3_logical-data-model.md); [decision 0026](../decisions/0026-a-drawing-comes-back-as-a-proposal.md), with the contradiction of decision 0005 it resolves; `GAP7`, `GAP28` and `GAP29` and step 1o on the roadmap — each linked on the branch, in the session. The word was *"Approved"* |

## Work packages

| WP | Delivers |
| -- | -------- |
| 0 — The stamp (built, inside `ACMP8`) | Every cell of a view's and a deep dive's draw.io file stamped; the file's own data, with what it drew; the exported name on a shape; the relationship on an edge — `src/ea/views/drawio.py`, `src/ea/views/deep_dive_pack.py` |
| 1 — The drawing read (built) | `src/ea/agent/drawing.py`: the stamp read against the model, compressed files and drawings from nothing too; a new shape typed from its stencil by the notation read in reverse; the drawing's questions in `src/ea/agent/questions.py`; a rename applied by `ProposalService.apply`; a `.drawio` file taken by the Propose page and `ea propose` |
| 2 — The tool server (built) | `src/ea/tool_server.py`: the read tools and the deep dives over the protocol, scoped by the caller's organisation, branch and role; `ea mcp` on stdio; `ea mcp --http` as the `ea-tool-server` app in `databricks.yml`, started by `make deploy-run` |
| 3 — Connected systems (built) | Table `connected_system` on both engines; `src/ea/services/connected.py` and the `connect_systems` action; `src/ea/agent/connected.py`, offered through each answer's toolbox to Ask and Propose's hosted reader; a deep dive's linked pages read and compared; the Connected systems page (`src/ea/ui/pages/systems.py`) and `ea systems` |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| A draw.io drawing handed in on Propose, stamped or not | Other drawing formats — Visio, a picture of a whiteboard |
| The read tools over the protocol, as the person who connected | Writing through an outside agent — a proposal handed in by one |
| Reading a connected system for an answer, a deep dive or a question | Loading what a system says into the model (`GAP20`); writing to a system |
| Systems that answer the Model Context Protocol | A system that answers only its own API, until something puts the protocol in front of it |

## Gap notes

- **A retired element is asked what it serves.** Retiring a shape taken out of a drawing adds
  it to the draft as a change, and the rule of initiative 24 asks what business an application
  element being changed serves — for something being retired, where the question matters less.
  It is the rule's, not the drawing's; a later look at the rule could leave a retirement out.

- **Loading from a connected system (`GAP20`).** A connected system already says what it masters;
  loading what it says through the feed pipeline — validation, provenance, a branch, review — is
  the step after, and waits on the source-of-record table as step 3 does.
- **An outside agent that proposes.** Handing in a proposal from an agent in an editor is Propose
  over the protocol; it needs a person's tick on the other side of it, and is left until an
  architect asks for it.
- **Proving it on the platform.** The tool server's and the connected systems' platform half —
  sign-in, the reader's identity passed on — waits with the rest of `PLAT2`'s workspace run.
