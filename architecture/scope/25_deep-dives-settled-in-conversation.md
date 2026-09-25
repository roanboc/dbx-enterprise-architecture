# Project Scope — Deep Dives Settled in Conversation

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/beautiful-hamilton-vci1sy` (Understanding granted 2026-09-25; in flight).
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 24.
**Target plateau:** `PLAT1` The repository running locally, extended.
**Gaps:** `GAP27` **An analysis is answered in one pass, and nothing learnt is kept**,
opened and closed by this initiative; `GAP28` **The documentation an element links to is
not read**, opened by it for later.

The Requester asked for a second way to ask: a **deep mode** in which the assistant behaves
as it does on Propose — it holds a conversation to settle what kind of analysis the reader
needs — and ends in a **deep dive**. Shown the first draft, the Requester widened it: the
deep dive is a comprehensive, styled **PDF** whose diagrams are **draw.io** diagrams, handed
out together in a ZIP; the analysis weighs the **maturity** of the elements it rests on and
recognises where an element and its documentation **disagree**; it **reads from the top
down**, the high level drawn to be presented — varied diagrams, colour, icons — and the detail
in the application's ArchiMate style; and a deep dive is
**catalogued and kept** in the platform, **rated** by the people who read it, **linked** from
the elements it covers and **weighed by later analyses**. In the Requester's words, this is
what can change enterprise architecture work: an analysis built on the model and on the
analyses before it, instead of architects drawing diagrams from scratch. Reading the pages
an element links to — a wiki's design pages — is the next step, and is left for later.

## What changes

**Ask gains a deep dive beside the quick answer.** The quick answer stays as it is. A reader
who chooses a deep dive says what they need to know in their own words, and the assistant
settles a **brief** with them before it analyses anything — a few questions at a time, each
with the choices the model allows, as Propose asks about a draft.

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

The reader answers with a choice or in their own words, can change any answer, and sees the
brief as one sentence before the assistant writes. It also lists the **earlier deep dives**
on the same elements, best rated first, so the reader can open one instead.

**Every element it rests on is given a maturity**, read from what the element already
carries, and the deep dive says how far its findings can be trusted from the maturity of
what they rest on — an analysis resting mostly on named, undescribed elements says so on its
first page.

| Maturity | What makes it |
| -------- | ------------- |
| **1 — Named** | It exists, and little more |
| **2 — Described** | A description, and the links its type expects |
| **3 — Related** | It traces up to the business or the strategy it serves, and holds the relationships its type declares |
| **4 — Approved** | Reviewed and approved, not draft |
| **5 — Current** | Approved, and refreshed from its source or confirmed by a person recently |

**Where an element and its documentation disagree, the deep dive says so.** Today the
documentation is what the repository holds about an element — its description, its
attributes, its states and its links:

| Inconsistency | For example |
| ------------- | ----------- |
| The description names an element it has no relationship with | *"feeds the student record"*, and nothing joins the two |
| A state contradicts the relationships | A live application depends on a retired one; something new depends on what is being decommissioned |
| The status contradicts the documentation | Approved, with no description |
| A link is malformed, or the same page is linked twice | |

With a hosted model, the model also compares the description with what the element's
relationships and attributes say. Reading the pages the links point at is `GAP28`.

**The findings come from rules the application already applies**, so a deep dive states them
with or without a model:

| Finding | Where the rule comes from |
| ------- | ------------------------- |
| Many elements depend on one — a single point of dependency | The impact the store already answers |
| Something depends on an element that is retired or being decommissioned | The target state and the change impact Propose reads |
| A change reaches elements outside its work package | The target state by work package |
| An element below the business layer traces up to nothing (principle `P9`) | The trace Propose's questions already test |
| A relationship the element's type declares has no instance | The completeness the impact already reports |
| An element and its documentation disagree | The table above |
| The analysis rests on elements of low maturity, or on content its source has not refreshed for long | The maturity above, and the freshness Health reports |

With a hosted model, the model reads the reader's words, asks in its own words where the
rules have nothing to offer, writes the summary from the findings and the views, and may add
what it read — every identifier it cites checked against what the tools returned, as in every
answer (principle `P6`).

**The deep dive is a pack.** One ZIP holding a styled PDF and a draw.io file for each
diagram, and nothing in Markdown. The PDF's diagrams are drawn from the same layout as the
draw.io files, so what is printed is what opens in draw.io.

**It reads from the top down, in two styles.** Every deep dive starts at the highest level
and zooms in, and the way it draws changes as it does. The high level is drawn to be shared
and presented — varied kinds of diagram, colour, icons and shapes chosen for a reader who is
not an architect. The detail is drawn as the application draws a view today: the metamodel's
own notation, ArchiMate in shape and colour.

| Level | What it shows | Drawn as |
| ----- | ------------- | -------- |
| **1 — Context** | The subject in its enterprise: the goals, capabilities and business it serves, and who is concerned | **Presentation**: a context map around the subject, icons and colour by layer |
| **2 — Overview** | The landscape the analysis covers, layer by layer, with where the findings and the low maturity sit | **Presentation**: layer bands with icons, a heat map of the area coloured by maturity or by finding, and charts of the maturity and the findings |
| **3 — Architecture** | One chapter per aspect of the analysis — what it serves, what depends on it, the trace, the transition | **Architecture**: the metamodel's notation, as the application draws a view |
| **4 — Detail** | The key elements up close — each one's neighbourhood, its maturity, and where it and its documentation disagree | **Architecture**, as above |

Both styles are generated from the model and never drawn by hand, and every shape that stands
for an element carries its identifier, however it is styled (principle `P8`); a chart carries
figures, never an element. An icon is picked from what the metamodel's notation already says
the element is — its ArchiMate kind, the way the draw.io export picks a stencil today — and
from its layer where the notation says nothing, so no framework's names enter the code
(principle `P5`).

| The PDF, in order | What it holds |
| ----------------- | ------------- |
| **Cover** | The title, the brief in one sentence, the organisation, the branch and the metamodel version it read, who asked and when |
| **What you need to know** | The findings that matter most for what the analysis is for, how far they can be trusted, and the figures behind them |
| **Context**, then **Overview** | Levels 1 and 2, each diagram with a short reading of it |
| **Architecture**, then **Detail** | Levels 3 and 4, each diagram with the table of what it draws and each element's maturity |
| **Findings** | Each with its severity, what was found, the elements it rests on and why it matters, placed at the level it concerns |
| **Inconsistencies** | Where an element and its documentation disagree |
| **References** | The earlier deep dives it weighed, with their ratings, and the elements it cites |
| **How it was answered** | The tool trace, and any identifier no tool returned |

The draw.io files are numbered in the same order, level first, so the pack reads top-down in a
folder as the PDF does on paper.

**A deep dive is catalogued, kept, linked and rated** (decision
[0024](../decisions/0024-deep-dives-are-kept.md)). It is kept the moment it is written, in the
organisation's own store, under a catalogue entry: the domains and element types of its
subject, the kind of analysis, the work package it concerns, the branch and version it read,
who asked and when. A **Deep dives** page lists the catalogue, narrowed by any of those and by
rating, and opens one; every element it cites lists it on the element's own page. Whoever
reads it may rate it — one to five stars, with a line of why — and the catalogue shows the
average and how many rated it. The next deep dive on the same elements weighs the earlier
ones by their rating: it names them among its references, best rated first, and a hosted model
reads their findings — which it checks against the model as it is now rather than repeating.
A deep dive can be **run again**: a new one from the same brief, which considers the one it
came from.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **One rating, or three?** | One, one to five stars, with a line of why | The Requester's *"a single star rating"*: confidence, quality and usefulness judged together. Three separate ratings, if the Requester reads it otherwise |
| **Who may rate?** | Anyone who may read; one rating per person, which they may change | A rating is a person's judgement; the assistant never rates (principle `P3`) |
| **Who may run one?** | Every role that may ask; it is kept as soon as it is written | It writes nothing to the model. A finding that calls for a change is handed in on Propose by an architect |
| **Can a deep dive be removed?** | Its author or an admin withdraws it; its row is kept | As nothing in the store is deleted; a withdrawn deep dive leaves the catalogue and is not weighed again |
| **Is maturity set by a person, or read from the element?** | Read from what the element carries | A field somebody must fill is one more field nobody fills; what the element already says is evidence. A maturity a steward sets, if the Requester wants one, would be one more thing it reads |
| **Is a deep dive edited once kept?** | No | It is what was true when it was read; running it again makes a new one |
| **Does it work without a model?** | Yes | The brief's questions are choices; the analysis, the maturity, the inconsistencies and the findings are rules. Reading an answer in the reader's own words needs a model; without one, words are searched as names |
| **Which branch does it read?** | The one the reader is on | Kept with the branch, and listed as read on it |
| **How much does it read?** | No more than a quick answer may | Three steps at most, the same limit on what a view draws, every read paged (decision [0019](../decisions/0019-the-size-the-application-declares.md)) |
| **Do the presentation diagrams keep principle `P8`?** | Yes | Generated from the model like every view; a shape that stands for an element carries its identifier, in small type beneath its name. Only a chart carries none, because it draws figures, not elements |
| **Where do the icons come from?** | The element's ArchiMate kind in the metamodel's notation, else its layer | As the draw.io export picks a stencil today; a metamodel that wants its own icons would add them to its notation, later |
| **How is the PDF made?** | In the application, from what is kept, with a library that needs nothing installed beside Python | So it runs on Databricks Apps as it runs locally; chosen when the technology layer is aligned, and recorded as a decision |
| **Which kinds of analysis?** | The five above | They are the product's, not a framework's: layers and states are read from the metamodel's notation and the model's vocabularies (principle `P5`) |
| **On the command line?** | Not in this initiative | Ask has no command today |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `BPROC3` | **Answer an architecture question** | Answered at once, or as a deep dive: a brief settled in conversation; the maturity and the inconsistencies weighed; views and findings; catalogued, kept and rated; weighed by the next |
| `BSVC1` | **Architecture knowledge** | Holds the deep dives kept on the model, so an analysis builds on the last one |
| `ACT6`, `ROLE5` | **Architecture assistant**, **Agent** | May ask a reader what a deep dive should cover, analyse what they settle and weigh the earlier deep dives by their ratings; may not rate one |
| `ROLE4` | **Reader** | May run, keep, rate and download a deep dive, and withdraw their own; may not change the model |
| `DOBJ3.11` | **Deep dive** | Added: its brief, catalogue entry, maturity, views, findings, references and ratings; kept, linked from the elements it cites |
| `GAP27`, `GAP28` | The two gaps above | Opened under `PLAT1`, and `PLAT1` and `PLAT3`; defined in [1_target-state.md](../6_transition/1_target-state.md) |
| decision 0024 | **A deep dive is kept, catalogued and rated; an answer is not** | New |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned — no change.** Serves `G1` **Query the architecture sustainably** — answers without drawing tools, which is the Requester's *instead of architects creating diagrams from scratch* — and `DRV2` **Agents need a queryable model**. Stays inside `P2` (the maturity reads the provenance every element carries), `P3` (it writes nothing to the model; people rate, the assistant does not), `P6` (every finding cites the elements it rests on), `P8` (every diagram is generated from the model) and `P9` (a trace to nothing is a finding). |
| 2_business | [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC3`, `BSVC1`. [1_actors-and-roles.md](../2_business/1_actors-and-roles.md): `ACT6`, `ROLE4`, `ROLE5`. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.11` **Deep dive**, added, with what it cites, embeds, is read on and is catalogued by; its retention. [2_conceptual-data-model.md](../3_information/2_conceptual-data-model.md): the entities `DEEP_DIVE` and `DEEP_DIVE_RATING`. [3_logical-data-model.md](../3_information/3_logical-data-model.md): tables `deep_dive`, `deep_dive_element` and `deep_dive_rating` in a new schema group `ea_knowledge`, and the index that lists an element's deep dives. Recorded as [decision 0024](../decisions/0024-deep-dives-are-kept.md). |
| 4_application | To align after Understanding: `ASVC5` **Grounded question answering** gains the deep dive; a **Deep dives** service for the catalogue — list, narrow, open, download, rate, withdraw, run again; `ACMP5` **Agent** gains the brief, the analyses, the maturity, the inconsistencies and the findings, and read tools for a work package's target state and an area's health; `ACMP8` **View generator** gains the presentation style beside the architecture style, and writes the PDF and a draw.io file per diagram from one layout; `ACMP6` **Web application** gains the mode on the Ask page, the Deep dives page and the list on the element page; the store gains the three tables on both engines; the roles gain keeping, rating and withdrawing. |
| 5_technology | To align after Understanding: a PDF library in the runtime, needing nothing installed beside Python; the `ea_knowledge` schema in the Lakebase database the bundle already creates, within the grant the app already holds. The same assistant model answers a deep dive. |
| Transition | `GAP27` opened and closed; `GAP28` opened, not started; step 1n recorded on the roadmap when this is built, extending `PLAT1`. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-25 | This document; `BPROC3` and `BSVC1` in [2_processes-and-services.md](../2_business/2_processes-and-services.md); `ACT6`, `ROLE4` and `ROLE5` in [1_actors-and-roles.md](../2_business/1_actors-and-roles.md); `DOBJ3.11` in [1_data-objects.md](../3_information/1_data-objects.md), the entities `DEEP_DIVE` and `DEEP_DIVE_RATING` in [2_conceptual-data-model.md](../3_information/2_conceptual-data-model.md) and the three tables in [3_logical-data-model.md](../3_information/3_logical-data-model.md); [decision 0024](../decisions/0024-deep-dives-are-kept.md); `GAP27` and `GAP28` on the roadmap — each linked on the branch, in the session. Presented three times: the first draft handed out Markdown and kept nothing; the Requester asked for a styled PDF with draw.io diagrams in a ZIP, for the maturity and the inconsistencies to be weighed, and for deep dives to be catalogued, kept, rated and linked from their elements, with the linked documentation read later; then for the document to read from the top down, the high level drawn to be presented and the detail in the application's ArchiMate style. The word was *"Yes, approved"*, with more changes to come |

## Work packages

| WP | Delivers |
| -- | -------- |
| 1 — The brief | The deep dive's questions and choices by rules, an answer applied to the brief, the brief as one sentence, the earlier deep dives listed; with a hosted model, the reader's own words read and questions asked in the model's |
| 2 — The analyses | The five kinds of analysis over the store, each within the assessed capacity, and the views each draws |
| 3 — Maturity and inconsistencies | The maturity of every element an analysis rests on, and the inconsistencies between an element and its documentation |
| 4 — The findings | The seven rules above, each with its severity and the elements it cites; the summary led by them, with how far they can be trusted |
| 5 — The pack | The styled PDF, top-down from context to detail; the presentation style for the high level — context maps, layer bands, heat maps, charts — and the metamodel's notation for the detail; a draw.io file per diagram, drawn from one layout, numbered by level, in one ZIP |
| 6 — The catalogue | The three tables on both engines; a deep dive kept when written, catalogued, linked from its elements; ratings; withdrawing; running again; earlier deep dives weighed by their rating |
| 7 — The pages | The choice between a quick answer and a deep dive on Ask, with the conversation beside the brief; the Deep dives page; the deep dives on the element page |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| A deep dive on the Ask page, settled in conversation | A deep dive on the command line |
| Five kinds of analysis; the maturity; the inconsistencies between an element and what the repository holds about it | Reading the pages an element links to, and comparing them with the model (`GAP28`) |
| A PDF and draw.io files in one ZIP, top-down, in two styles | A pack in any other format; icons a metamodel declares for itself |
| Deep dives catalogued, kept, linked from elements, rated and weighed by later ones | Editing a kept deep dive; publishing the catalogue to the platform's own catalogue, or logging questions and answers for monitoring (`PLAT5`) |
| One rating per person, one to five stars | Several rated dimensions; a maturity a steward sets by hand |

## Gap notes

- **Reading the linked documentation (`GAP28`).** The Requester's next step: a deep dive that
  follows the links of its key elements — a wiki's design pages — reads them, cites them among
  its references, and reports where they disagree with the model. It takes reaching those pages
  as the reader on the platform, as a connected source is under `GAP20`, with their permissions
  rather than the app's; a bound on how much is read; and the model to compare prose with the
  model's structure. The rules of the inconsistency table already give it somewhere to land.
- **On the command line.** Ask has no command today; one would take the brief's questions in
  the terminal, as `ea propose --interactive` does, and write the pack to a file.
- **A deep dive ages.** It is what was true when it was read, and says so on its cover. Running
  it again is the answer this initiative gives; telling a reader that the model has moved under
  a deep dive since it was read would be a later one.
