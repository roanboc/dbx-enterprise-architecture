# 0017 — The database holds the keys, and the references stay in the services

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-20, for the Requester to confirm or override. **Touches:** `ACMP2`, `DOBJ1.6`, `DOBJ2.1`.

## Context

The DDL declared columns and nothing else: no primary key, no foreign key, no
unique index. The store enforced every key in Python — it is the only writer,
it reads by the key before it writes, and it carries the whole key in every
update and delete — so the rows were right. Two things were still missing. A
second writer, a hand-written `INSERT` against the file, would not be caught.
And the query planner had nothing to work with, so every hop of a traversal
read the whole relationship table: 608 ms where an index makes it 44 ms.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Leave the database with no constraints | What it did. The store is the only writer today, but nothing holds a second one, and a traversal pays for it on every hop |
| Unique indexes on the logical keys, created on start-up — **chosen** | The keys the store already enforced, now enforced where the rows are; `CREATE INDEX IF NOT EXISTS` is idempotent and reads the same on both engines |
| Primary keys declared in the DDL | The same constraint, plus a migration for every store that already exists, in a statement whose dialect differs between the two engines |
| Foreign keys on the references as well | An element points at the element type of the version its organisation applies. A version may be retired and a type deleted while the content that used it stays exactly where it is — a foreign key would forbid what decision [0015](./0015-metamodel-versions.md) requires |

## Decision

Every logical key of `3_logical-data-model.md` is a unique index, created on
start-up, each one on its own: a store that already holds a duplicate keeps the
row and logs the refusal rather than failing to open. Both ends of a
relationship, the rows that hang off an element and the change log by entity
are indexed too. References are not declared: they stay checked by the services
on the way in, which is where a person can be told what is wrong.

## Consequences

- A duplicate row is refused by the database, not only by the code that meant
  to write it. A store that was already holding one keeps it, and somebody has
  to read the log — the alternative was an application that would not start.
- `meta_attribute` has no unique index. Its key holds `type_id` or
  `rel_type_id` and never both, and the two engines do not agree on whether two
  NULLs are the same value; the loader replaces every row of a version at once,
  so a duplicate cannot arise there in the first place.
- A deleted element type leaves its content in place, and the compatibility
  check reports it when the version is applied. That is the behaviour decision
  0015 asks for, and a foreign key would have made it impossible.
- Integrity between tables is only as good as the services. A second writer is
  still a second writer: it would be caught on a key and not on a reference.
