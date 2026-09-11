# 0002 — A generic graph schema on DuckDB now and Delta later, with in-process traversal

_[← Decisions](./README.md)_

**Status:** Accepted, 2026-09-05; the platform store superseded by [0013](./0013-lakebase-not-the-lakehouse.md) — Lakebase, not Delta. **Touches:** `ACMP2`, `ACMP3`, `DOBJ2`.

## Context

The owner wants "DuckDB (local) or any Databricks delta table" with the same
code, and asked whether the current EA tool's database engine matters (it does not: only
the exports do). The content is small (about 4,600 elements) and the business
case's directive to push every traversal to a SQL warehouse would make each
click a warehouse query. Lakebase (Postgres) is available if needed.

## Decision

One portable DDL for the schema (`element`, `relationship`, `element_link`,
`change_log` and the `meta_*` tables), written in the types DuckDB and Delta
share, with JSON as text. A `DatabaseBackend` interface with a DuckDB
implementation now and a Databricks implementation later on the same DDL and
MERGE semantics. Traversals exist twice on purpose: as recursive SQL with a
cycle guard (works on both engines, used by the CLI and the agent) and as an
in-process cached graph for the app (no round trip per click). Optimistic
concurrency on a `_version` column, and every write appends to the change log.

## Alternatives

- **A graph database** (Neo4j, Cosmos Gremlin) — better traversal semantics,
  but a second platform to run, secure and pay for, outside Unity Catalog.
- **Lakebase as the primary store** — transactional and Postgres-compatible,
  but it would make Delta a copy; it stays an option for the app's own
  transactional state if optimistic concurrency on Delta proves too slow.
- **Typed tables per element type** — readable in a catalogue, unusable when
  the metamodel changes; kept as a generated projection (decision 0003).

## Consequences

- The DuckDB file is single-writer: the CLI cannot open it while the app
  holds it. Documented in the README.
- The Databricks backend is a known gap (`GAP1`) with a defined contract; the
  tests that run against DuckDB in memory are the acceptance tests for it.
