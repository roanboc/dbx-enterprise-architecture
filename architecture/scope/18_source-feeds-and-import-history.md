# Project Scope — Source Feeds and Import History

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/import-module-improvements-wgrfgm`, restarted
from `main` after initiative 17 merged.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 17.
**Target plateau:** `PLAT3` — the roadmap's step 3, provenance and feeds.
**Gap:** `GAP4` **No source feeds**, opened against `PLAT1` and `PLAT3`, is what
this initiative closes.

Initiative 17 made the manual path work: a file is validated, loaded, exported
and loaded back without losing anything. The Requester then named what the
manual path cannot do. **Content arrives from several systems on a schedule** —
a reference model, a service management system, an HR extract — and three things
are missing before that can happen: an import cannot delete, nothing records
that an import happened in a form anybody could undo, and nothing reads a table.

The Requester's direction is a staging table per source in the platform's
catalogue, already in the contract's shape, which the application reads and puts
through the same pipeline — so validation, the report, branch targeting and the
change log come for free and no pipeline reimplements them in SQL. The
configuration of each feed belongs in the application: where the table is, how
it merges, how it deletes, when it runs.

## What the analysis found before any of it was designed

Three findings change the shape of the work, and one closes an item outright.

**A two-character separator cannot be supported.** Settled in initiative 17 and
recorded in `connectors/README.md`, because the Requester asked for `||`: the
CSV writer refuses a delimiter longer than one character, a multi-character
separator makes the reader stop honouring quotes — so every description holding
a newline, every fenced diagram, breaks into several rows — and `|` already
separates the values of `links` and of a multi-valued attribute. A tab and the
ASCII unit separator work today. **No work remains here.**

**Deletion already exists, one layer down.** `branch_element` carries an `op`
column, a merge applies `op = "delete"`, and `remove_relationship` already uses
it. An import does not need a new deletion mechanism; it needs a way to say
which rows are deleted, and the existing review-before-merge gate then decides.

**Reversal is not possible from what is logged today.** The change log holds a
before and an after payload and the Element page already reads it, but a bulk
import writes **one summary entry** — inserted, updated, unchanged — and no
per-row before-images. Nothing could be reversed from that. This is the item
with the largest hidden cost, and the one the feed-target decision below
mostly removes.

## The calls the Requester made

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **What may a feed delete?** | **Retire by default, hard delete opt-in per source** | A deletion indicator sets `status` to `retired`, keeping the element, its relationships and its history, and is itself reversible. A source that genuinely owns its rows may be configured to delete them outright, which is the `op = "delete"` path that already exists |
| **Where does a feed write?** | **Configurable per source** | A trusted reference-model feed may land on `main`; a CMDB feed lands on a branch for review. Both paths are built, and the choice is a property of the feed rather than of the application |
| **Where does the work go?** | **A new initiative, its own pull request** | Initiative 17 stays reviewable at about 1,500 lines. This is several thousand more |
| **How much of item 5 is built now?** | **The history, yes; the reversal, when it is really needed** | Made after the rest of the initiative was built and reviewed. The account of every run is what a feed running unattended needs first — without it a load at a quarter past two reports to nobody. Reversal is the expensive half, and its open questions (below) are still open. `GAP19` therefore **opens and stays open** rather than opening and closing here |

The second call is the expensive one, and it should be said plainly: **had every
feed written to a branch, reversal would already exist** — abandoning a branch
undoes everything on it. Allowing a feed onto `main` is what makes per-row
before-images necessary, and that is most of item 5's cost. It buys feeds that
are current without anyone draining a queue of branches.

## What would be added to the model

| Identifier | Element | Why it is not an existing one |
| ---------- | ------- | ----------------------------- |
| `DOBJ3.7` | **Import run** — one execution: its source, actor, organisation, branch, mapping, the files or staging tables it read, the counts, and the issues. **Built without two of the things first listed here:** the before-images of the rows it changed, which are what reversal needs, and a content hash of what it read. Both are named under *what was deliberately left* | `DOBJ3.3` Import report is what a run *said*; this is what a run *was*, and it has to outlive the request that produced it |
| `DOBJ3.8` | **Source feed** — a configured source: where its staging tables are, which mapping it uses (inline), its target branch or `main`, whether it empties what it loaded, its schedule and the zone that schedule is written in. **Three things proposed here are not on it:** a merge mode and a deletion mode, which travel inside the mapping where a source's shape belongs, and a watermark, which nothing needed once a feed empties what it loaded | Nothing today configures a source. A mapping (`DOBJ3.2`) says how a file's columns read; it says nothing about where the data comes from or when |
| `ASVC12` | **Source feeds** — configure a feed, run it on demand, and see every run with what it read, what it changed and why it stopped. Proposed as *Source feeds and import history*, running "on its trigger" and able to "reverse one"; **shipped as neither**: nothing in the application fires a schedule (decision 0020 puts that outside it) and reversal is not built (`GAP19`) | `ASVC3` is the contract in both directions and this *uses* it. Putting the schedule, the configuration and the run history inside `ASVC3` would make one service own four unrelated things |
| `ACMP14` | **Feed runner** — reads a staging table into frames, drives `ACMP4` over them, records the run | `ACMP4` is the importer and exporter; it reads files and frames and knows nothing about where they come from |
| `GAP19` | **A run that landed on `main` cannot be reversed** — opened by this initiative and **left open** | Names the cost the second call above incurs, so it is visible rather than implied. Defined in [1_target-state.md](../6_transition/1_target-state.md), which is where a gap lives |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares. The change adds one
application service, one component and two data objects, and it closes a gap the
roadmap already names. It adds no stakeholder, driver, goal or principle, so it
is an ordinary initiative at the **Understanding** gate.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change.** No driver, goal, principle or assessment moves. `P5` holds: a feed's configuration names a table and a mapping, never a type or an institution. |
| 2_business | **One change to assess.** Review before merge is a business rule, and a feed configured onto `main` writes without a human. The rule is not removed — it is made a property of the feed, and `BPROC1` **Load content from a source** gains an unattended path. The information architect should see this row before anything is built. |
| 3_information | Two objects added under `DOBJ3` **Exchange and audit**: `DOBJ3.7` Import run and `DOBJ3.8` Source feed. `DOBJ3.4` Change log is unchanged — a bulk import still writes one summary entry, and the before-images a reversible run would need are not written, which is what `GAP19` says. Retention of runs is stated as unenforced rather than implied. |
| 4_application | `ASVC12` and `ACMP14` added; `ASVC3` and `ACMP4` re-worded for the deletion indicator they would read. `ACMP6`'s page list gains a Feeds page, carrying the import history under the feeds; `ACMP7`'s command list gains `ea feed …` and `ea runs …`. |
| 5_technology | **No change, and the open question is closed.** The application cannot read a catalogue table and will not learn how: decision [0020](../decisions/0020-staging-tables-live-in-the-store.md) puts a staging table in the store's own database, in a schema of its own, reached over the connection the store already holds. No warehouse, no new dependency, no new identity. `NODE2` gains a clause naming the staging schema. |
| Transition | `GAP4` **No source feeds** is **narrowed, not closed**: a source's rows are read, validated and loaded on a branch or on `main` as the feed is configured, and every run is kept — but nothing in the application fires a schedule, and the per-type source-of-record semantics still wait on the table agreed outside the repository. `GAP19` **opens and stays open**. Roadmap step 3 moves from waiting to in flight, for that same part only. |

## What is not settled, and would be before building

1. ~~Can the deployed application read a catalogue table at all?~~ **Settled,
   and it cannot.** Decision 0013 retired the warehouse, and a catalogue read
   needs one under any name. Decision
   [0020](../decisions/0020-staging-tables-live-in-the-store.md) puts the
   staging table in the store's own database instead, which costs no dependency,
   resource, identity or grant — and lets the unit suite cover a feed on both
   engines, because the boundary is a table shape rather than a platform API.
2. **The clone-and-drop window.** The Requester's design — clone the staging
   table, drop the staging table, import from the clone, so the staging table
   only ever holds pending rows — is sound and gives a clear pending set. What
   happens if the application stops between the clone and the drop, or between
   the drop and the import, has to be answered: one loses rows, the other
   repeats them. Idempotent loads make repetition harmless, which argues for
   dropping last.
3. **How long before-images are kept.** They roughly double an import's write
   volume, and the store is assessed at a hundred thousand elements
   (decision 0019). A run that may be reversed for thirty days is a different
   figure from one that may be reversed forever.
4. **What reverses.** Reversing a run that created elements is deletion;
   reversing one that updated them is restoring before-images; reversing one
   whose rows a later run changed again is a conflict, not an undo. The honest
   answer is probably that a run is reversible only while nothing has touched
   its rows since, and that the page says so.
5. **Deletion of an element that is an endpoint.** Retiring keeps its
   relationships; deleting does not. What happens to an edge whose end a feed
   deleted has to be stated before a feed may delete.

## What the capacity rule requires of it

Written before the work; **what shipped differs in two places, and the code says
so where it differs.** A staging table is read from the store in pages of
`capacity.READ_CHUNK` and then joined into one frame, not folded a page at a
time — because the frame is what the importer takes, and a staging table is the
same size class as an uploaded file. `frames_from_staging` states that bound in
its own docstring rather than implying a smaller one. Before-images are not
written at all: that is `GAP19`.

What did hold: the run list is paged like every other read, on the screen and on
the command line, and one request reads one page however far back a reader goes.
`tests/test_capacity.py` holds that with a test of its own. It does **not** yet
cover the feed runner's own read, which is the honest gap in this paragraph.

## What was built, and what was deliberately left

Written after the work, against the list above, so the difference between what this document
proposed and what shipped is on the page rather than in a diff.

**Built.** The staging schema and decision 0020 behind it; the deletion indicator (`retire` by
default, hard delete refused *with its reason*); the feed runner, read-load-clear in that order;
the stored feed with its inline mapping, its target branch and its schedule in the zone it was
written in; the Feeds page with a readable schedule picker, the cron escape hatch, the mapping
guidance and the contract by example; `ea feed …`; and **the import history** — every run of
every kind kept as `DOBJ3.7`, read a page at a time on the Feeds page and through `ea runs …`.

**Left, and why.**

| Left | Why, and what it would take |
| ---- | --------------------------- |
| **Reversing a run** | The Requester's call, after the history was scoped: the account first, the undo when it is really wanted. It needs the before-image of every row a run changed, a retention period for them, and an answer to the case where the honest one is *no* — a run whose rows a later run has changed again. `GAP19` |
| **Content hashes of what a run read** | Worth having: it answers "did this feed send me the same file twice". It costs a pass over the data that nothing else needs, and the counts already answer most of what a reader asks. Not built rather than half-built |
| **A retention period for runs** | Nothing prunes the table. A run is a few kilobytes and a nightly feed writes one a day, so it grows slowly — but it grows, and saying so beats a figure nobody measured |
| **Firing a schedule** | Outside the application by decision 0020. The stored expression is what a trigger honours; the page says so rather than implying the opposite |
| **`GAP4` closed** | It is narrowed. The per-type source-of-record table is agreed outside this repository and still gates the rest |

## Approvals

| Gate | Approved by | Date | What was approved |
| ---- | ----------- | ---- | ----------------- |
| **Understanding** | The product owner (the Requester), in the session | 2026-09-20 | This document, presented with the three findings that shaped it — deletion needs no new mechanism, reversal is impossible from what is logged today, and the catalogue read was unverified — and with the first three calls recorded above. Granted after initiative 17 merged |
| **Understanding, narrowed** | The product owner (the Requester), in the session | 2026-09-21 | The fourth call: the feeds, the page and the command line having been built and reviewed, what remained of item 5 was put to the Requester as history-then-reversal or both together. **The history was directed, the reversal deferred** — "we should add at least the run history, I'll defer the reversal for when really needed". Narrowing an approved scope needs no new gate; it is recorded here because `GAP19` opens and stays open because of it |
