# Project Scope — Proposals Refined in Conversation

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/great-franklin-30i81n`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 23.
**Target plateaus:** `PLAT4` Governed change, its intake; `PLAT2` Same
application on Databricks, prepared.
**Gaps:** `GAP24` **The assistant cannot ask**, `GAP25` **The assistant's
model is reached outside the platform** and `GAP26` **Nothing says, or keeps to,
what belongs at the enterprise level**, opened by this initiative.

The Requester asked for an agentic experience: the architect works *with* the
assistant on a proposal, and the assistant asks for what it needs when an
element or a relationship is unclear, so a proposal is refined actively rather
than handed in and corrected by hand. The assistant's model is to be one
Databricks Model Serving provides. At this document's gate the Requester added two
rules — a change is settled top-down, and a system's inside is not modelled — which
[initiative 23](./23_the-enterprise-level.md) states as principle `P9`, and asked
for a guide in the application that states the boundary for enterprise and
solution architects.

## What changes

**A proposal becomes a conversation.** Today the reader reads the page once and
answers with rows and a list of what is missing. From here it asks about what it
cannot settle — a few questions at a time, each tied to the row it is about and
offering the choices the model allows.

**It settles the change top-down.** The context comes first: why the change is
made and which business it changes. Questions about information, application and
technology rows wait until that is clear, and every element below the business
layer has to trace up — through relationships on the page or in the model — to a
business or strategy element. The layers are read from the metamodel's own
notation, so the order holds in any framework.

| It asks when | The choices it offers |
| ------------ | --------------------- |
| The page says nothing of why: no goal, driver or capability it serves | The ones the model holds that the page's elements come closest to, or a new one |
| The page changes no business process, service or role, or names one the model lacks | The ones the change's elements already serve, or *a purely technical change*, recorded as such |
| An application or technology element traces up to nothing in the business or strategy layers | The processes, services and capabilities it most likely serves |
| A name matches more than one element, or nearly matches one | The candidates, or *new* |
| A row names no type, or one the metamodel lacks | The types the metamodel has |
| Two elements are joined by a relationship the metamodel does not allow | The relationships it allows between them |
| An element being retired still has something depending on it | Retire that relationship too, move it to a named element, or keep the element |
| A new element is connected to nothing that exists | The elements it most likely serves or uses, or *leave it* |
| A new element has no description, or the page names no work package | A sentence, or a work package |
| A new element relates only to its own system — a part of it, or the system that contains it — or is of a type the metamodel places below the enterprise level (`P9`) | *Link it from the system*, with the page that describes it; *keep it*, naming what outside the system relates to it; or *drop it* |

The architect answers by picking a choice, editing a row, or saying it in their
own words; the assistant redrafts, the impact and the drawing follow, and it asks
again until nothing is unclear. The draft is kept between sittings. Once applied,
the conversation stays with the proposal, so the reviewer reads how each row was
settled.

**The boundary is data, and the test is relationships.** Each element type of a
metamodel says whether it sits at the enterprise level or below it, so an
organisation draws its own line; the two packs the repository ships place every
type at the enterprise level and let the relationship test find a system's inside.
A part linked rather than modelled is an element link on its system — the link
every element already carries — with the page that describes it.

**A guide in the application.** A Guide page, written for the people who use the
repository rather than as a manual of its screens: what the repository is for and
what belongs in it — the boundary of `P9` in C4 terms, with the types the
organisation's metamodel places on each side — how a change is settled top-down,
what states, work packages, branches, proposals and reviews are for, and where a
solution's own detail goes instead. One section per persona: the enterprise
architect, the solution architect, the reviewer and steward, the reader, and the
metamodel's owner. Conceptual and procedural: what to do and why, not which button
to press.

**The model is served by the platform.** A Databricks Model Serving endpoint is
the assistant's model for Ask and Propose alike, reached as the app's own
identity on Databricks and with the architect's own Databricks credentials
locally.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Does it work without a model?** | Yes, for choices | The questions in the table above come from the rules the application already applies, so the model-free reader asks them too and applies a picked choice. Understanding an answer in the architect's own words needs a model |
| **Who decides a question?** | The architect, always | An answer changes the draft only; nothing is written until the architect applies it (`P3`, decision 0004). The assistant never settles a question it asked |
| **How many questions at once?** | Five at most, top layer first | A long page does not become a wall of questions; technical questions wait until the context is settled |
| **Does an unanswered context question stop Apply?** | Yes, until answered — *a purely technical change* is an answer | Nothing below the business layer lands without a stated reason, and the reviewer reads which one |
| **Where does a draft live?** | With the proposal, status `draft`, per architect | Picked up from the Propose page; an empty branch until a new one is created at Apply |
| **The tool server for external agents (`GAP7`)?** | Not in this initiative | It stays step 5 on the roadmap. The conversation uses the same tools, so the tool server later exposes what is built here |
| **Where does the line sit in the packs we ship?** | Every type at the enterprise level | The relationship test finds a system's inside in any framework; marking types is the organisation's call, in its own metamodel version |
| **Where is the guide written?** | In the repository, as Markdown, one file per persona, generic | It ships with the application and names no organisation; the list of types on each side of the line is read from the organisation's metamodel when the page is drawn |
| **The direct provider?** | Kept, for development | Model Serving is the default on Databricks; the direct provider and the model-free reader remain for a laptop without a workspace |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `BPROC2.2` | **Hand in a proposal** | The assistant settles the change top-down, keeps a system's inside out, and asks rather than guesses; the architect answers; the draft is kept between sittings |
| `DOBJ1.1` | **Element type** | Says whether it sits at the enterprise level or below it |
| `DOBJ2.3` | **Element link** | Also where a system's inside is referenced |
| `ACT6`, `ROLE5` | **Architecture assistant**, **Agent** | May ask the architect and redraft from the answers; may not settle its own question |
| `DOBJ3.6` | **Proposal** | A draft until applied, with its conversation |
| `GAP24`, `GAP25`, `GAP26` | The three gaps above | Opened under `PLAT4`, `PLAT2` and `PLAT4`; defined in [1_target-state.md](../6_transition/1_target-state.md) |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned** with `P9`, which [initiative 23](./23_the-enterprise-level.md) adds and this initiative keeps to. Serves `G1` and `DRV2`; stays inside `P3` (the agent drafts and asks, a person decides) and `P6` (every identifier it offers comes from a tool). |
| 2_business | [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC2.2`. [1_actors-and-roles.md](../2_business/1_actors-and-roles.md): `ACT6`, `ROLE5`. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.6`, `DOBJ1.1`, `DOBJ2.3`. [3_logical-data-model.md](../3_information/3_logical-data-model.md): `proposal` gains `conversation_json` and `updated_at`, and a `draft` status; `meta_element_type` gains `level`. |
| 4_application | **After Understanding.** `ASVC9` and `ACMP10`: the conversation and the boundary test; `ACMP5`: the served model for Ask; a Guide service and page. |
| 5_technology | **After Understanding.** A Model Serving endpoint on `NODE2`, granted to the app by the bundle; recorded as a decision. |
| Transition | `GAP24`, `GAP25`, `GAP26` opened and in flight; step 1m on the sequence. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-24 | This document; `BPROC2.2` in [2_processes-and-services.md](../2_business/2_processes-and-services.md); `ACT6` and `ROLE5` in [1_actors-and-roles.md](../2_business/1_actors-and-roles.md); `DOBJ1.1`, `DOBJ2.3` and `DOBJ3.6` in [1_data-objects.md](../3_information/1_data-objects.md) and the `proposal` and `meta_element_type` columns in [3_logical-data-model.md](../3_information/3_logical-data-model.md); `GAP24` to `GAP26` on the roadmap — each linked on the branch, in the session. Presented twice: the first time the Requester asked for the change to be settled top-down and for a system's inside to be kept out, which became initiative 23 and the additions above; the second time the word was *"Yes, approved, implement both"* |

## Work packages

| WP | Delivers |
| -- | -------- |
| 1 — The conversation | A draft proposal with its conversation; the assistant's turn — redraft, then ask; an answer applied to the draft; a draft resumed |
| 2 — Questions without a model | The questions of the table above from the rules and the impact, and a picked choice applied |
| 3 — The Propose page as a conversation | The conversation beside the draft's tabs; choices as buttons, a free answer, the drafts to pick up; Apply as today |
| 4 — The served model | A provider for a Model Serving endpoint for Ask and Propose; the endpoint in configuration and granted to the app in the bundle |
| 5 — The command line | `ea propose --interactive`: the questions asked in the terminal |
| 6 — The boundary | `level` on an element type, edited on the Metamodel page; the relationship test; a part linked from its system |
| 7 — The guide | The Guide page and its Markdown, one section per persona; reached from the navigation and from the Propose page |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| Questions about rows, choices and free answers, drafts kept | The tool server for external agents (`GAP7`, step 5) |
| One Model Serving endpoint for Ask and Propose | Choosing the model per task; evaluating the assistant's questions |
| The boundary kept by every new proposal | Finding what already crosses it in the content held today — a Health figure, later |
| A guide that ships with the application | An organisation's own additions to the guide |
| The conversation kept with the proposal for the reviewer | A conversation shared by two architects at once |

## Gap notes

- **No workspace to prove it on.** The served provider is tested against a stand-in
  for the endpoint; the run on a workspace waits with the rest of `PLAT2`.
- **Evaluating the assistant.** `PLAT5` asks for questions, answers and feedback to be
  logged for monitoring; the kept conversations are the raw material, not the monitor.
