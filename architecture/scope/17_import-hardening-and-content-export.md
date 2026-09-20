# Project Scope — Import Hardening and Content Export

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/import-module-improvements-wgrfgm`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 16.
**Target plateau:** `PLAT1` extended. No plateau moves; no gap opens.

The metamodel is settled, so the import module is the next thing that will
actually be used. Asked to find what it needed, the agent read it and ran it,
and found seven things — one of them silent data loss. **A links file loaded on
its own deleted the links it was meant to add**, because `set_links` replaces an
element's links wholesale while this module's own docstring called the file "a
second pass adding documentation". It was reported as a clean load.

The rest were the marks of a module the capacity work of initiative 16 never
reached: endpoints and link owners resolved one store round trip per row, an
unbounded issue list where the compatibility report already counted and capped,
a report that computed how many rows were new and how many were overwritten and
then added them together, and a file written with a semicolon — what a
spreadsheet saves across much of Europe — refused for having no `id` column.

Reading that, the Requester asked the question the list did not answer: **can we
get content back out in the shape we put it in?** The metamodel exports as YAML
and content exported as nothing, so the cheapest way to correct a thousand rows —
export, fix the column in a spreadsheet, import again — did not exist.

## Is an export inside `ASVC3`, or a service of its own?

**Inside it, once `ASVC3` is read as the contract rather than as one direction of travel.**

| Reading | Verdict |
| ------- | ------- |
| **A new application service, `ASVC12` Content export** | It would duplicate `ASVC3`'s whole substance — the same three files, the same columns, the same metamodel. Two services owning one contract is how the two drift apart |
| **Inside `ASVC3` as written, so no row changes** | `ASVC3` said *CSV ingestion*. An export is not ingestion, and shipping it under a row that does not mention it is exactly what the gate exists to stop |
| **`ASVC3` widened to ingestion and extraction** (chosen) | One service owns the contract in both directions, so the columns the exporter writes are the columns the importer reads by construction. `ACMP4` widens with it |
| **Export as a view, under `ASVC6` Generated views** | Views are for reading — Mermaid and draw.io, drawn from the pack's notation. A CSV meant to be edited and loaded back is not a picture |

## What makes the trip out and back a round trip

A relationship's identity is derived from the source system that declared it, and
the contract's `relationships.csv` had no column for it. An export re-imported
under any other `--source` would therefore have created **a second copy of every
edge** rather than updating it. `source_system` is now a column of the contract
on both files, overriding `--source` for the row that carries it. That is the one
change to what the contract claims; everything else the exporter writes, the
importer already read.

The same URL reaching an element twice — inline in the elements file and again in
the links file, which is what an export writes — now lands once, keeping the
labelled one.

## What a row is called

Reading the export back, the Requester named the case the contract had no answer
for: several systems are about to be loaded, and **nothing namespaced an
identifier**. Two sources that both number their rows from one made `1001` the
same element, and the second load overwrote the first without a word. And what
many of those systems know a row by is not a surrogate id at all but the human
key — `DT007` — which the contract carried and never merged on.

Both are settled in the mapping, which is where a source's shape belongs:
`id_prefix` goes in front of every identifier a source brings, and `match_on`
chooses between the `id` column and the `key` column as the identity the source
is merged on. Merging on the key, an element the repository already holds under
that key keeps the identity it was given, so a reload updates it however the
source has renumbered its own ids — and an element created in the application is
found the same way, rather than gaining a parallel copy beside it.

One function resolves all four kinds of reference — an element row, a
relationship endpoint, a link owner, a named work package — so the files cannot
disagree about what a row is called. A prefix reaching only elements would leave
every endpoint dangling, which is what the test for it caught while it was being
written.

This is an import format for a service that already exists, so it was coded
directly; it is recorded here because it shipped on this branch, not because it
needed a gate of its own.

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares. The change widens one
application service and the component that realises it, and adds no stakeholder,
driver, goal or principle. It is an ordinary initiative at the **Understanding**
gate.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change.** No driver, goal, principle or assessment moves. `P5` (nothing framework-specific in `src/`) is honoured: the exporter reads its columns from the pack and the contract, and names no type. |
| 2_business | **No change.** The same roles and the same review before merge. An export is a read, so it is available to every role that may browse. |
| 3_information | **No change.** No data object is added: the exported files are the same three the contract already names, written from the objects the store already holds. |
| 4_application | `ASVC3` widened from **CSV ingestion** to **CSV ingestion and extraction**, and re-worded for what the report now says and what a links file now does. `ACMP4` widened from **Importer** to **Importer and exporter**, naming `csv_export.py` and the batched reads. `ACMP7`'s command list gains `ea export`. See [1_application-services.md](../4_application/1_application-services.md) and [2_application-components.md](../4_application/2_application-components.md). |
| 5_technology | **No runtime changes.** |
| Transition | **No gap opens or closes.** Step 3 of the roadmap (provenance and feeds) still waits on the source-of-record table agreed outside the repository; this initiative makes the manual path work well, it does not anticipate the automated one. See [2_sequence.md](../6_transition/2_sequence.md). |

## What the capacity rule required

Both passes of the exporter page with `capacity.pages()` and write each page out
before reading the next, so nothing here holds the model (decision 0019). The
elements file needs its header before its first row and an element may carry an
attribute the pack never declared, so the attribute columns are a pass of their
own that keeps the names and lets the elements go. `write_links` is one read per
element that carries a link and says so in its docstring, with what that costs.

## What this initiative deliberately left

Recorded so the next piece of work starts from what was found rather than from
scratch. None of it is promised, and none of it widens the PoC.

**The load is not atomic.** Elements are written, then relationships, then
links, and a failure between them leaves the branch half-loaded. There is no
transaction primitive anywhere in `backend/` — no `BEGIN`, no commit or
rollback, no context manager — so this is not a change to the importer but the
introduction of transactions to the shared SQL store, honoured by both engines.
Its cost is low while loads stay idempotent and re-runnable, which they are.

**A source that stops exporting a row leaves it in the model forever.** There is
no notion of a full load against a delta, so an import can only add and update.
Deciding otherwise — that a feed owns its rows, and absence means retirement —
changes what the model claims about a feed and needs the Requester at a gate,
not a code change. It is the question that blocks unattended feeds, more than
any of the plumbing below.

**Feeds from landing tables.** The Requester's direction is a table per source
in the platform's catalogue, already in the contract's shape, which the
application reads and puts through the same pipeline — so validation, the issue
report, branch targeting and the change log all come for free and no pipeline
reimplements them in SQL. `import_frames` already takes frames, so a landing
table would be read straight into one rather than written to CSV first. What
remains open is not the reading but the triggering, and these questions decide
it before any mechanism does:

| Open question | Why it blocks |
| ------------- | ------------- |
| **What branch does an unattended feed write to?** | An import writes to the current branch and the Import page refuses `main` outright, because review happens before anything merges. A feed has nobody to open a branch or approve the merge. Either every run gets a branch somebody drains, or feeds are trusted onto `main` — which is the rule the application enforces hardest. A gate question |
| **Which role does a feed run as?** | `require("import")` needs an actor, and whatever it is appears in the change log as the author of every row |
| **One landing table or several?** | Several. Each source then carries its own `id_prefix` and `match_on`, which is what the mapping now expresses; one shared table would force a single identity rule on every source |
| **How is it triggered?** | Sketched, not decided: the refreshing job calling the import as its last task (the trigger is the pipeline's own completion, and freshness becomes "did the job succeed"); a watermark per source deciding what is actually new; a scheduled sweep beneath both as a safety net; and a button in the application whatever else is chosen, so the path stays testable by hand |

**Two smaller notes.** The links file is one read per element that carries a
link, bounded by how many carry documentation rather than by the model, and says
so in its docstring. And a per-type export (a file per element type, which
`type_from_filename` already reads) was considered and not built: one wide file
was chosen, and a second shape would be a second round trip to keep true.

## Approvals

| Gate | Approved by | Date | What was approved |
| ---- | ----------- | ---- | ----------------- |
| **Understanding** | The product owner (the Requester), in the session | 2026-09-20 | The seven import findings, presented with the evidence for each; then the export, presented with the round-trip trap that `source_system` fixes, the choice of one wide file over a file per type, and this widening of `ASVC3` rather than a service of its own. Granted in the session, with the file shape chosen as one wide file |
