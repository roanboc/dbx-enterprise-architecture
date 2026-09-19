# 0014 — An organisation is a partition of the one store, not a second store

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-19 (initiative 15) — adopted by the agent, for the Requester to confirm or override at the initiative's gate. **Touches:** `DOBJ2.8`, `ASVC11`, `ACMP2`, `ACMP13`.

## Context

Trying a version of the metamodel needs content to try it on, and the only
content worth trying it on is the content the repository already holds. The
Requester ruled out a test environment for that, and asked that the trial be
part of the architecture work. A branch cannot carry it: a branch is a change
to the content, reviewed and merged back, and it reads the metamodel of the
body of content it belongs to. So the store needs a second body of content
beside the first — one the architect creates, works in and throws away. An
enterprise architecture repository that later serves a faculty, a subsidiary
or a merged institution needs the same thing.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| A second database, or a second deployment | The Requester's own objection, and a practical one: the content is copied by hand, the result is carried back by hand, and an architect cannot create one |
| A schema per organisation in the one database | The store would build a table name per read, the DDL would run once per organisation, and no query could reach across two of them to ask how many of the faculties call this type by that name |
| A branch of the content, on the overlay of [0006](./0006-branches-as-overlays.md) | A branch merges back, and a metamodel version is never merged into content; a trial on a branch also changes the language every other branch of that content reads |
| An `org_id` on every content row, honoured by a context variable — **chosen** | The column the branch overlay already composes with, the same shape the current branch is set in, one store to project to a catalogue later, and a copy that is an `INSERT … SELECT` rather than a deployment |

## Decision

Every content and branch table carries `org_id`, and an `organisation` table
names the organisations, their applied metamodel version, which one is the
default and which one each was copied from. The current organisation is a
context variable (`src/ea/backend/organisations.py`) beside the current
branch: the application sets it from the session, the command line from
`--org`, a service through `use_org()`. The store builds every element and
relationship query over two scoped sources, which read the current
organisation's main and lay that organisation's branch overlay over it; a
reader's own SQL runs with the tables shadowed by scoped common table
expressions. A sandbox is an organisation created by copying another's main
content.

## Consequences

- A scoped read costs one equality on a column every content query already
  carries a filter for; the branch overlay is unchanged, because the scope
  sits inside it rather than beside it.
- A query that forgets the scope would answer with another organisation's
  rows. Two things answer that: the scoped sources are built in one place, and
  the tests hold two organisations carrying the same identifiers apart —
  elements, relationships, branches, reviewers and history.
- Every new read or write path goes through a scoped source, the way it
  already honours the branch. A direct table read names the organisation
  itself.
- The store stays one store, so the projection the lakehouse will read
  (plateau `PLAT5`) gains a column rather than a database.
- Deleting an organisation deletes everything in it; the change log keeps the
  record of what was there.
