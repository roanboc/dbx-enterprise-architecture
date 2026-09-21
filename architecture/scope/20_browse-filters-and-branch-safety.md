# Project Scope — Browse Filters and Branch Safety

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/enterprise-arch-assessment-iln3rz`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 19.
**Target plateau:** `PLAT1` extended, on the way to `PLAT3`.
**Gap:** `GAP21` **A search cannot be narrowed, shared or carried past its first
page**, opened and closed by this initiative.

The Requester asked what to improve next, named browse and branching as the two
things the current commercial tool is used for daily, and named one symptom:
*a search returns too many results and needs more criteria.* An assessment of
both modules was run before anything was designed. It produced 149 findings
across twelve dimensions; what follows is what survived checking against the
code, and what was done about it.

## What the assessment found

**The filtering symptom was the smaller half of the problem.** `_where` in the
store accepted exactly three criteria — free text, one type, one status — while
an element carries eleven fields worth filtering on. But underneath it sat a
defect that made the search wrong rather than merely narrow: **ranking happened
in Python over the alphabetically first 5,000 rows.** Above that cut the best
match for a query could not reach the first screen, and the count beside it —
"5000 of 41230" — offered a page two the page could not turn to.

**Four more things were wrong rather than missing.** A Health drill-down was
applied after the row limit and the total then rewritten to what survived, so
the screen read "N of N" while matching rows were dropped. A partial merge wrote
a relationship to `main` without the element it pointed at. A row `main` had
deleted came back silently when a branch holding an edit to it was merged. And a
merged or abandoned branch still accepted writes that could reach neither `main`
nor an abandon.

**Three refusals were not refusals.** `ea sql` and the agent's SQL tool answered
from `main` while the reader stood on a branch, with nothing saying so — and a
security review of the fix found that laying the branch over the *bare* table
names left a qualified one (`<prefix>_content.element`) reaching the base table,
which reads **every organisation's rows**, not only the reader's. That half
pre-dates this work and contradicts decision 0014's partition; naming a schema
is refused now, and the catalogues that disclose the names with it.
Configuring a feed needed the Admin role on the page and nobody's role on the
command line. A bulk edit naming an attribute with an empty value wrote the
blank over every ticked row — the one bulk edit nobody can undo.

## The calls made without asking

Under **Ask only what blocks the work now**, these were the agent's to take.
Each is recorded here so a later word from the Requester overrides it.

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **How do the criteria reach the store?** | One `ElementFilter` object, not a widening parameter list | The store, the services, the page, the command line and the address bar name the same criteria, and a new criterion is added in one place. `find_elements` and `count_elements` took three arguments they disagreed with each other about; they take the filter instead |
| **Where does ranking happen?** | In SQL | It is the only layer that can see every matching row. A page is then the rows after the page before it, and the count is the result set |
| **What does a conflict default to?** | Nothing | It defaulted to *take the branch*, which made overwriting somebody else's work the thing that happens when nobody looks at the row |
| **What does a blank attribute value mean in a bulk edit?** | A refusal | Emptying an attribute on purpose is `--clear-attr`, which says so. The old behaviour and the documented behaviour disagreed, and the documented one is the safe one |
| **How much of the branching list is in scope?** | The safety, not the features | The unsafe defaults, the staleness signal and the branch's visibility are defects and near-defects. Rebase, cherry-pick, revert, per-item comments and a reviewer inbox are features, and they are named below as left |

## What changed in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `ASVC2` | **Element browsing and editing** | The row claimed exactly the three filters the code had. It now says what narrows a list, that the store ranks the whole result set before it pages, that the criteria are carried in the address, and that a result set comes out as CSV |
| `DOBJ2.5` | **Branch** | Named three statuses where the code has five, and said nothing about which of them accept writes. Both corrected |
| `GAP21` | **A search cannot be narrowed, shared or carried past its first page** | Opened and closed by this initiative. Defined in [1_target-state.md](../6_transition/1_target-state.md), which is where a gap lives |

No stakeholder, driver, goal or principle moves. No new application service or
component: this is an existing service doing what its row already claimed, plus
the filtering it did not.

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change.** `P5` holds: every criterion is a column or an attribute the pack declares, never a type or an institution. `P8` is untouched. |
| 2_business | **No change.** Review before merge is unchanged; what changed is that a conflict now needs a decision rather than defaulting to one, which strengthens the rule rather than moving it. |
| 3_information | `DOBJ2.5` Branch re-worded for the statuses it actually has. `AttributeFilter` and `ElementFilter` are **not** data objects: nothing persists them, and a query that is never stored is not information the model holds. That is precisely what a saved query would change, which is why it is left. |
| 4_application | `ASVC2` re-worded. `ACMP3`'s search path and `ACMP7`'s `ea find` gain the criteria; no component is added. |
| 5_technology | **No change, and one thing to watch.** Every clause is still `ILIKE` over unindexed columns. At the sample's size that is milliseconds; at the assessed hundred thousand it is a full scan per keystroke, on DuckDB and on Lakebase alike. Named under *what was deliberately left*. |
| Transition | `GAP21` opens and closes. `GAP18` (capacity) is **touched and held**: the browse and branch paths now page, but `tests/test_capacity.py` still does not guard them, which is stated below rather than implied. |

## What the capacity rule requires of it

Written before the work, and it held. The page reads one page of one hundred
rows and asks the store for the total separately, so no request holds the model.
The CSV export pages rather than fetching at once, and stops at
`settings.max_rows` — a bound it states rather than a silent cut.

One thing did **not** hold and is worth saying plainly: the Health drill-down
passes a set of identifiers into the filter, and that set is as large as the
facet's answer. At the sample's size it is tens of rows. At the assessed
capacity a facet naming twenty thousand elements would build an `IN` clause of
twenty thousand parameters. The honest fix is a predicate the store understands
rather than a list of ids, which is a change to `HealthService` and is left.

## What was built, and what was deliberately left

**Built.** `ElementFilter` and `AttributeFilter` in `models.py`; the filter,
the SQL rank and the sort in `sql_backend.py`; `SearchService` reduced to
labelling the page the store returned; the Browse page rebuilt with multi-select
types and statuses, a drawer holding the other seven criteria, a column chooser,
server paging, removable chips naming what narrows the list, the filters carried
in the address and a CSV export of the result set; `ea find` taking every
criterion with `--json` and `--csv`; the eight defects above, each with a unit
test; the merge defaults made safe, a staleness alert on a branch behind `main`,
and a stripe above every page when the reader is not on `main`.

### Field-level merge (added after the Requester saw the first cut)

The Requester asked for the conflict handling this document had named as left, so it was
built rather than deferred. A branch row now keeps **the row as `main` held it when the
branch first touched it** (`branch_element.base_row`, `branch_relationship.base_row`).
With that base, what the branch changed and what `main` changed are each a set of fields,
and **only their intersection is a conflict** — two architects editing different fields of
one element have not disagreed about anything. An applied row is `main`'s current row with
the branch's changed fields laid over it; each disputed field is settled on its own, from
the merge log's detail panel or with `--resolve element:X.field=main`.

**An adversarial review of that change found seven defects in it, every one reproduced
against a real store.** They are recorded here because the change would otherwise have
shipped losing more than it saved:

| What | Why it mattered |
| ---- | --------------- |
| A branch's **delete** disagreed with nothing, because a delete changes no field — so deleting a row `main` had been editing applied silently and took `main`'s edit with it | The one path that destroyed a row rather than a field |
| A branch row that **changed no field** is a stale copy of `main` (setting links alone puts one there). It was not a conflict, so it was ticked by default, and merging it reverted everything `main` had done since | Silent, and reachable by an ordinary edit |
| **Links sat outside the field comparison**, so `main`'s links were replaced by the branch's stale copy with no conflict — while the new screen told the reader the opposite | The loss pre-dated this work; the wrong reassurance did not |
| `all(… == "main")` over an **empty** decision is vacuously true, so any mapping on a row `main` had deleted dropped it | The caller asked for the branch's value and got `main`'s |
| The apply path checked `base is None` where it meant `before is None`, so a per-field decision was **discarded** on any row with no base | Made worse by the next one |
| An **import onto a branch** wiped `base_row`, because `_replace_rows` names its columns and that one was left out | Turned a legacy edge case into an ordinary one |
| `--resolve element:LDC.FIN=main` read `FIN` as a field, because an element id may hold a dot | Resolved the wrong row |

Each is fixed, and each has a test in `tests/test_branches.py` named for the sequence that
found it. **What is still not built** is a merge of one field's *text*: where both sides
edited the same description, the choice is one value or the other, not a combined one.

**Left, and why.**

1. **A saved or named query.** It needs somewhere per reader to keep one, which
   is a data object this model does not have. Naming it properly is an
   initiative, not a control.
2. **A relationship as a criterion** — *applications that support no
   capability*. It needs a predicate over the edge table rather than over the
   element row, which is a different query shape.
3. **A generic matrix report** (type A by type B over a relationship type). The
   classic EA cross-tab, and the single largest remaining gap against the
   commercial tool. It is its own initiative.
4. **An index behind the search.** Every clause is still `ILIKE` over unindexed
   columns. It costs nothing today and will cost at the assessed capacity.
5. **The branching features:** rebase a stale branch, cherry-pick, revert a
   merge, compare two branches, a per-item review comment, a reviewer inbox.
   Every one is a feature rather than a defect, and the Requester has not been
   asked which of them matters. Field-level conflict resolution was on this list
   and came off it at the Requester's word.
6. **A per-element owner.** Review routes on element type only. An owner per
   element is what a commercial repository has and this does not; it reaches
   into the metamodel and belongs with the Requester.

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------------- |
| Understanding | The product owner | 2026-09-21 | The assessment of both modules — eight defects with file and line, the filtering gap, and the branching list — put to the Requester in the session that produced this document. The Requester's word was *"Start implementing all fixes and improvements"*, which is the approval this row records. The scope actually built is narrower than "all": what was left is listed above, and the Requester has not agreed to that narrowing |

A second **Understanding** is not recorded separately for the field-level merge: it is the
conflict handling this document already named as left, and the Requester asked for it by
name in the same session, which the row above covers.

**Direction** was not sought and no row records it: `GAP21` sits under plateaus
the roadmap already holds, and nothing here changes where the project is going.
