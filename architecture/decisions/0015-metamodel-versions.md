# 0015 — The metamodel is kept in versions, and a published version is frozen

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-19 (initiative 15) — adopted by the agent, for the Requester to confirm or override at the initiative's gate; what a published version freezes narrowed by [0022](./0022-a-name-is-not-frozen.md), which takes the name out of it. **Touches:** `DOBJ1.6`, `ASVC1`, `ACMP1`, `ACMP13`; extends decision [0003](./0003-metamodel-as-data.md).

## Context

Decision 0003 made the metamodel data: a pack loaded into tables and edited
there. One definition, edited in place, costs three things. A reader cannot
say which definition a piece of content was validated against. Two
definitions cannot be compared, because only one is ever stored. And the
architect who adds a type changes the language every reader of the repository
sees, the moment the row is saved. The source metamodel document is itself
dated and supersedes an earlier one, so the repository has to hold both
anyway.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| One definition edited in place, with the change log as its history | What the repository did. A log of field changes reconstructs no definition, and nothing can be validated against it |
| A version of every type and attribute row, dated independently | Nobody applies a hundred separately dated rows; an architect applies a language. The difference between two definitions becomes unreadable |
| A version of the whole pack, drafted, published and retired — **chosen** | One thing an organisation applies, one thing two people compare, one thing that stops moving when it is published |
| Migrate the content when a version is applied | The engine has no rule to apply: nothing says what an element becomes when its type is gone, or what fills an attribute a version made required |

## Decision

A pack is stored per pack and version, with a status. A **draft** is edited in
place, and carries the version it was derived from and a note saying what it
is for. A **published** version is frozen: saving different content under it
is refused, and a change to it is a new draft copied from it. A **retired**
version stays readable and is applied to nothing. Each organisation applies
exactly one version. Applying one runs a **compatibility check** first: every
element and relationship of that organisation's main is validated against the
candidate, and the findings come back as a report. Errors refuse the apply
unless the architect forces it; warnings never refuse.

## Consequences

- Content validated against a published version stays validated, because
  nothing behind it moves. That is what the freeze buys, and it is why a
  correction to a published version costs a new version rather than an edit.
- Version names accumulate. The store suggests today's date and numbers the
  second one of a day; a version an organisation still applies is neither
  retired nor deleted.
- The check reports and the architect decides. Forcing an apply is a
  legitimate move, made when the version is agreed and the content has not
  caught up; it is logged like any other change to the organisation.
- The difference between two versions is read from data
  (`src/ea/metamodel/diff.py`) rather than by opening two screens, which is
  what makes a review of a draft possible before it is published.
- A pack file names its own version, so loading one lands beside the versions
  already stored rather than over them. A file repeating a published version
  with different content is refused, and is given a version of its own.
