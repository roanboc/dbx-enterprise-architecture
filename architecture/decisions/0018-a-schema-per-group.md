# 0018 — A schema per group of tables

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-20, for the Requester to confirm or override. **Touches:** `ACMP2`, `ACMP2.1`, `ACMP2.3`, `DOBJ1`, `DOBJ2`, `DOBJ3`.

## Context

The store made seventeen tables in one schema. The information layer already
groups them five ways — the metamodel, the content, the branch overlay,
governance and the audit trail — and the table names carry the grouping as
prefixes (`meta_`, `branch_`). A prefix is a convention, not a boundary: a
person opening the database with a SQL client meets a heap and has to know the
convention to read it, and a grant is all seventeen tables or none. The
Requester asked for the groups to be the schemas.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| One schema, prefixed table names | What it did. The reader has to know the convention, and nothing can be granted per group |
| One schema per group, named from `EA_SCHEMA` — **chosen** | The grouping the document already states, made real where the data is; the prefix keeps two deployments apart in one database |
| A database per group | Joins and transactions across groups are the store's ordinary work, and both engines make that harder across databases than across schemas |
| Wait until the store runs on the platform | Grouping is the one change to this schema that cannot be made additively later: it moves data. It is cheapest while the only stores are a PoC file and a test schema |

## Decision

`EA_SCHEMA` names a prefix (`ea` by default) and each group of tables is a
schema of its own: `ea_metamodel`, `ea_content`, `ea_branch`, `ea_governance`,
`ea_audit`. Only the statements that make or alter a table name a schema;
every other statement names the table alone and lets the search path find it,
so the store's SQL reads as it did. A store made before the split keeps every
table in one schema, and its next start moves each one into the schema of its
group with its rows — `ALTER TABLE … SET SCHEMA` on Postgres, a copy and a drop
on DuckDB, which has no such statement — before the DDL runs, or the DDL would
make an empty table in the new place and leave the rows behind.

## Consequences

- A grant can be given per group. The audit trail can be readable by more
  people than may write content, and the metamodel writable by fewer.
- On the platform there are five schemas to name instead of one, so the app's
  database resource, any synced table and any grant the deployment makes have
  five names to carry rather than one.
- An unqualified `CREATE TABLE` now lands in whichever schema the search path
  reads first. Every statement that makes or alters a table names its schema,
  and a test holds each table against the group it is documented under.
- The move runs one way. A store that has been grouped is not ungrouped by
  going back to an older build, which would find its tables missing.
- Two deployments can share one database by taking a prefix each, which is what
  the test suite does for every test.
