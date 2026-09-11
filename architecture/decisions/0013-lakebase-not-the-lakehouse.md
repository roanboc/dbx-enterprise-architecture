# 0013 — Lakebase, not the lakehouse, is the store on Databricks

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-11 (initiative 14) — the Requester's instruction in the session; supersedes the platform half of [0002](./0002-store-and-engines.md) and the engine named in [0011](./0011-one-sql-store-two-engines.md). **Touches:** `ACMP2.3`, `TSVC6`, `NODE2`, `ART6`, `PLAT2`, `GAP16`.

## Context

Decision 0002 put the platform store on Delta tables reached through a SQL
warehouse, and kept Lakebase — the platform's Postgres — as an option for the
app's own state should optimistic concurrency on Delta prove slow. Initiative
13 built that engine and showed what a warehouse costs an application: every
statement is a round trip of seconds on a warehouse that may be asleep, a
statement binds at most 255 values so rows land as literals, a table has no
constraints, a write is one statement with no transaction around the next, and
the open-source engine has no recursive queries. The Requester settled it on
2026-09-11: the project runs on Lakebase, not on the lakehouse.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Keep the warehouse engine and add Lakebase beside it as a third | Two platform engines to keep true, the suite run three times, and a store nobody asked for kept alive for the day somebody might |
| Lakebase for the app's state, Delta for the content | Every write crosses two stores, and the branch overlay, the diff and the merge — the store's whole point — straddle them |
| Lakebase as the one store on the platform — **chosen** | Postgres reads the portable DDL as written, binds sixty-five thousand values a statement, holds a bulk load in one transaction and runs the recursive trace; Delta becomes a projection the lakehouse reads through Unity Catalog when plateau `PLAT5` wants one |

## Decision

The store on Databricks is one schema in a Lakebase database (Postgres) the
deployment bundle creates as an instance of its own; the app reaches it over
the Postgres protocol as its service principal, with an OAuth token the SDK
generates. The warehouse engine, its stand-in and the grant step are retired;
the one SQL store keeps two engines, DuckDB and Lakebase, and the Lakebase
engine is proved on a real Postgres in every test run.

## Consequences

- The platform store is transactional: a bulk load lands or does not, a
  reader's query runs read-only on the server, and a click costs a round trip
  of milliseconds rather than a warehouse statement.
- A Postgres has to be reachable for half of the store tests: the run starts
  one of its own where `initdb` is installed, CI runs a service container, and
  a workstation with neither runs the store tests on DuckDB only, and is told.
- The lakehouse reads the store rather than holding it: registering the
  database in Unity Catalog is the step before the projection and the glossary
  of `PLAT5`, and the change log's two-year retention is a job on the instance
  rather than on a warehouse.
- What the platform grants is decided by the app's database resource, not by
  a grant step; whoever runs the live tests from a workstation needs a Postgres
  role on the instance of their own.
