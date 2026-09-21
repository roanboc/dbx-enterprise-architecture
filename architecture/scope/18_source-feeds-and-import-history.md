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

## The three calls the Requester made

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **What may a feed delete?** | **Retire by default, hard delete opt-in per source** | A deletion indicator sets `status` to `retired`, keeping the element, its relationships and its history, and is itself reversible. A source that genuinely owns its rows may be configured to delete them outright, which is the `op = "delete"` path that already exists |
| **Where does a feed write?** | **Configurable per source** | A trusted reference-model feed may land on `main`; a CMDB feed lands on a branch for review. Both paths are built, and the choice is a property of the feed rather than of the application |
| **Where does the work go?** | **A new initiative, its own pull request** | Initiative 17 stays reviewable at about 1,500 lines. This is several thousand more |

The second call is the expensive one, and it should be said plainly: **had every
feed written to a branch, reversal would already exist** — abandoning a branch
undoes everything on it. Allowing a feed onto `main` is what makes per-row
before-images necessary, and that is most of item 5's cost. It buys feeds that
are current without anyone draining a queue of branches.

## What would be added to the model

| Identifier | Element | Why it is not an existing one |
| ---------- | ------- | ----------------------------- |
| `DOBJ3.7` | **Import run** — one execution: its source, actor, organisation, branch, mapping, the file names and their content hashes or the staging table and its snapshot, the counts, the issues, and the before-images of the rows it changed | `DOBJ3.3` Import report is what a run *said*; this is what a run *was*, and it has to outlive the request that produced it |
| `DOBJ3.8` | **Source feed** — a configured source: where its staging table is, which mapping it uses, its merge mode, its deletion mode, its target branch or `main`, its trigger, and its watermark | Nothing today configures a source. A mapping (`DOBJ3.2`) says how a file's columns read; it says nothing about where the data comes from or when |
| `ASVC12` | **Source feeds and import history** — configure a feed, run it on demand or on its trigger, see every run with what it did and what it changed, and reverse one | `ASVC3` is the contract in both directions and this *uses* it. Putting the schedule, the configuration and the run history inside `ASVC3` would make one service own four unrelated things |
| `ACMP14` | **Feed runner** — reads a staging table into frames, drives `ACMP4` over them, records the run | `ACMP4` is the importer and exporter; it reads files and frames and knows nothing about where they come from |
| `GAP19` | **A feed onto `main` is not reversible without per-row history** — opened and closed by this initiative | Names the cost the second call above incurs, so it is visible rather than implied |

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
| 3_information | Two objects added under `DOBJ3` **Exchange and audit**: `DOBJ3.7` Import run and `DOBJ3.8` Source feed. `DOBJ3.4` Change log is re-worded: it records a bulk import as a summary today, and would record before-images for a run that may be reversed. |
| 4_application | `ASVC12` and `ACMP14` added; `ASVC3` and `ACMP4` re-worded for the deletion indicator they would read. `ACMP6`'s page list gains a Feeds page; `ACMP7`'s command list gains `ea feed …`. |
| 5_technology | **No change, and the open question is closed.** The application cannot read a catalogue table and will not learn how: decision [0020](../decisions/0020-staging-tables-live-in-the-store.md) puts a staging table in the store's own database, in a schema of its own, reached over the connection the store already holds. No warehouse, no new dependency, no new identity. `NODE2` gains a clause naming the staging schema. |
| Transition | `GAP4` **No source feeds** closes. `GAP19` opens and closes with this initiative. Roadmap step 3 moves from waiting to in flight — but only for the part that does not depend on the per-type source-of-record table agreed outside the repository, which still gates the rest. |

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

A staging table is read in pages with `capacity.pages()` and folded into frames
a page at a time, never held whole. A run's before-images are written as the
rows are written, not accumulated in the request. The run list is paged like
every other read. `tests/test_capacity.py` fails a new unbounded read, and it
would have to cover the feed runner.

## Approvals

| Gate | Approved by | Date | What was approved |
| ---- | ----------- | ---- | ----------------- |
| **Understanding** | The product owner (the Requester), in the session | 2026-09-20 | This document, presented with the three findings that shaped it — deletion needs no new mechanism, reversal is impossible from what is logged today, and the catalogue read was unverified — and with the three calls recorded above. Granted after initiative 17 merged |
