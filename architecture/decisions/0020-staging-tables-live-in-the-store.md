# 0020 — A staging table lives in the store, not in the catalogue

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-20 (initiative 18), for the Requester to confirm — it follows from [0013](./0013-lakebase-not-the-lakehouse.md) rather than reopening it. **Touches:** `DOBJ3.8`, `ASVC12`, `ACMP14`, `NODE2`, `GAP4`.

## Context

The Requester's direction for automated feeds was a table per source in the
platform's catalogue, already in the contract's shape, which the application
reads and puts through the same pipeline. Scope document 18 listed one thing as
unsettled ahead of everything else: **whether the deployed application can read
a catalogue table at all.**

It cannot, and the reason is a decision already taken. Decision 0013 put the
store on Lakebase and retired the warehouse engine, its stand-in and the grant
step, because a warehouse costs an application seconds a statement. The
deployed application therefore has exactly two ways out: a psycopg connection
to its Lakebase database, and the platform SDK it uses to sign in to that
database and read a user's workspace groups. `databricks.yml` declares one
resource, the database; there is no warehouse and no SQL connector dependency.

Reading a Unity Catalog table needs a SQL warehouse — directly, or behind the
statement execution API, which takes a warehouse identifier either way. Adding
one back would contradict 0013 for the sake of a read the store can serve.

Decision 0013 already said which way the arrow points: *the lakehouse reads the
store rather than holding it.*

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| A warehouse, for the staging tables only | Contradicts 0013 within a fortnight of it being taken, and brings back the round trip, the grant step and a second identity for one read a day |
| The statement execution API instead of a connector | The same warehouse under another name, plus a second way of running SQL to keep true |
| **A staging table is a table in the store's own database — chosen** | The application already has a connection to it, already has an identity on it, already reads it in pages, and a transaction there is a transaction over the load. No new dependency, no new resource, no new grant |
| The application reads files from a volume instead | Workable, and it is the same shape as today's upload. Kept as the fallback if a source cannot write Postgres, but a table is what the Requester asked for and what a pipeline produces most naturally |

## Decision

A staging table is an ordinary table in the Lakebase database the application
already connects to, in a schema of its own (`<EA_SCHEMA>_staging`). What puts
the rows there is outside the application: a platform job writing to Postgres,
or a Lakebase synced table replicating a catalogue table into it. The
application's contract with a source is the **shape of the table**, which is
the CSV contract's columns, and nothing else.

The application never reaches into the catalogue, and no feed gives it a second
way of running SQL.

## Consequences

- Feeds cost no new dependency, resource, identity or grant. The feed runner
  reads its staging table over the connection the store already holds, in pages,
  like every other read.
- The boundary is a table shape rather than a platform API, so the same feed
  works on DuckDB locally — which is what lets the unit suite cover it on both
  engines, as the store tests already are.
- A source that can only produce files is served by the upload path that
  already exists, or by a volume, which stays the declared fallback.
- Whoever writes the staging table needs a Postgres role on the instance. That
  is the same grant a person running the live tests needs, and it is decided by
  the database resource rather than by a grant step, as 0013 has it.
- Registering the database in Unity Catalog — the step 0013 names ahead of the
  `PLAT5` projection — is what lets the lakehouse *read* these tables. The
  arrow keeps pointing that way.
