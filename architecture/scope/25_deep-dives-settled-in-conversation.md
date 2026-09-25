# Project Scope — Deep Dives Settled in Conversation

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/beautiful-hamilton-vci1sy` (drafted for Understanding; not built).
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 24.
**Target plateau:** `PLAT1` The repository running locally, extended.

The Requester asked for a second way to ask: a **deep mode** in which the assistant
behaves as it does on Propose — it holds a conversation to settle what kind of analysis
the reader needs — and ends with a **deep-dive document**: several diagrams, each a
different view of the subject, and the findings the reader needs to know. Today a
question is answered in one pass, with one view, and the reader who needed an analysis
rather than an answer has to ask five questions and assemble the result themselves.

## What changes

**Ask gains a deep dive beside the quick answer.** The quick answer stays as it is. A
reader who chooses a deep dive says what they need to know in their own words, and the
assistant settles a **brief** with them before it analyses anything — a few questions at
a time, each with the choices the model allows, as Propose asks about a draft.

| It asks | The choices it offers |
| ------- | --------------------- |
| **What the analysis is about** | The elements the reader's words most likely mean, a work package, or *something else*, named |
| **Which kind of analysis** | The five below, with the one the words point to first |
| **How far it reaches** | One, two or three steps from the subject, and which layers to cover |
| **What it is for** | The decision it supports, in the reader's words — optional; it orders the summary |

| Kind of analysis | The question it answers | The views it draws |
| ---------------- | ----------------------- | ------------------ |
| **Impact** | What happens if this changes or goes? | What it serves, up to the business and the strategy; what depends on it; what it depends on — each marked with its target state where one is set |
| **Landscape** | What makes up this area? | The area from strategy down to technology, one view per layer band |
| **Transition** | What does this work package change, and what does it leave behind? | The package's elements as they are, and as targeted; what they touch outside the package |
| **Information flow** | Where does this information come from, and where does it go? | The trace from the sources that master it to what consumes it |
| **Model quality** | How far can what the repository says about this area be trusted? | The area, with the elements that carry a finding marked |

The reader answers with a choice or in their own words, can change any answer, and sees
the brief as one sentence before the assistant writes. Then it analyses what was settled
and writes the **deep-dive document**:

1. **The brief** — what was asked, as settled.
2. **What you need to know** — a summary led by the findings that matter most for what
   the analysis is for.
3. **One section per view** — each a generated view with the table of what it draws.
4. **Findings** — each with its severity, what was found, the elements it rests on and
   why it matters.
5. **The elements**, what was not found in the model, and how it was answered — the tool
   trace — as every answer document carries today.

It downloads as Markdown, and as draw.io with one page per view.

**The findings come from rules the application already applies**, so a deep dive states
them with or without a model:

| Finding | Where the rule comes from |
| ------- | ------------------------- |
| Many elements depend on one — a single point of dependency | The impact the store already answers |
| Something depends on an element that is retired or being decommissioned | The target state and the change impact Propose reads |
| A change reaches elements outside its work package | The target state by work package |
| An element below the business layer traces up to nothing (principle `P9`) | The trace Propose's questions already test |
| A relationship the element's type declares has no instance | The completeness the impact already reports |
| Content not refreshed from its source for long, or still in draft | The freshness Health reports, and the element's status |

With a hosted model, the model reads the reader's words, asks in its own words where the
rules have nothing to offer, writes the summary from the findings and the views, and may
add what it read — every identifier it cites checked against what the tools returned, as
in every answer (principle `P6`).

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Is a deep dive kept in the repository?** | No, as no answer document is | The row of the answer document records it: answer documents are not stored. It is downloaded; the conversation lives for the reader's session, as Ask's does today |
| **Does it work without a model?** | Yes | The brief's questions are choices, and the analysis and the findings are rules. Reading an answer in the reader's own words needs a model; without one, words are searched as names |
| **Who may run one?** | Every role that may ask | It reads and writes nothing (principle `P3`). A finding that calls for a change is handed in on Propose by an architect |
| **Which branch does it read?** | The one the reader is on | As every answer does |
| **How much does it read?** | No more than a quick answer may | Three steps at most, the same limit on what a view draws, every read paged (decision [0019](../decisions/0019-the-size-the-application-declares.md)) |
| **Which kinds of analysis?** | The five above | They are the product's, not a framework's: layers and states are read from the metamodel's notation and the model's vocabularies (principle `P5`) |
| **On the command line?** | Not in this initiative | Ask has no command today; a deep dive on the command line is a gap note below |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `BPROC3` | **Answer an architecture question** | Answered at once, or as a deep dive: a brief settled in conversation, then several views and the findings |
| `ACT6`, `ROLE5` | **Architecture assistant**, **Agent** | May ask a reader what a deep dive should cover, and analyse what they settle |
| `DOBJ3.5` | **Answer document** | Its deep-dive form: the brief, a summary, a view per aspect of the analysis, and findings with their severity; still not kept |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned — no change.** Serves `G1` **Query the architecture sustainably** and `DRV2` **Agents need a queryable model**; stays inside `P3` (it reads and writes nothing), `P6` (every finding cites the elements it rests on), `P8` (every diagram is generated from the model) and `P9` (a trace to nothing is a finding). |
| 2_business | [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC3`. [1_actors-and-roles.md](../2_business/1_actors-and-roles.md): `ACT6`, `ROLE5`. No new business service: the deep dive is `BSVC1` **Architecture knowledge** answered at length. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.5` and what it embeds. [3_logical-data-model.md](../3_information/3_logical-data-model.md): **no change** — nothing new is stored. |
| 4_application | To align after Understanding: `ASVC5` **Grounded question answering** gains the deep dive; `ACMP5` **Agent** gains the brief, the analyses and the findings, and read tools for a work package's target state and an area's health; `ACMP8` **View generator** writes several views as one draw.io file; `ACMP6` **Web application** gains the mode on the Ask page. |
| 5_technology | **No change.** The same assistant model — the served endpoint on Databricks — answers a deep dive as it answers a question. |
| Transition | A gap and step 1n recorded on the roadmap when this is built, extending `PLAT1`. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |

## Work packages

| WP | Delivers |
| -- | -------- |
| 1 — The brief | The deep dive's questions and choices by rules, an answer applied to the brief, the brief as one sentence; with a hosted model, the reader's own words read and questions asked in the model's |
| 2 — The analyses | The five kinds of analysis over the store, each within the assessed capacity, and the views each draws |
| 3 — The findings | The six rules above, each with its severity and the elements it cites; the summary led by them |
| 4 — The document | The deep-dive form of the answer document, in Markdown and as draw.io with one page per view |
| 5 — The Ask page | The choice between a quick answer and a deep dive; the conversation beside the brief; *Write the deep dive*; the document on the page and its downloads |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| A deep dive on the Ask page, settled in conversation | A deep dive on the command line |
| Five kinds of analysis and six kinds of finding | Kinds an organisation defines for itself |
| The document downloaded as Markdown and draw.io | Keeping a deep dive in the repository, or sharing one by address |
| The findings computed by rules, a model's reading added to them | Evaluating what a model adds; logging questions and answers for monitoring (`PLAT5`) |

## Gap notes

- **On the command line.** Ask has no command today; one would take the brief's
  questions in the terminal, as `ea propose --interactive` does, and write the document
  to a file.
- **Keeping a deep dive.** Answer documents are deliberately not stored. Keeping deep
  dives would take a table of their own, per organisation and branch, and a place on a
  page to read them back — a change of that resolution, and its own initiative.
