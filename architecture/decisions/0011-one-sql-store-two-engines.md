# 0011 — The store is written once on SQL, and an engine adds only its dialect

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-09 (initiative 13) — adopted by the agent, for the Requester to confirm or override at the initiative's gate. **Touches:** `ACMP2`, `ACMP2.1`, `ACMP2.2`, `TSVC4`.

## Context

Decision 0002 promised a Databricks implementation of the store "on the same
DDL and MERGE semantics", and named the DuckDB test suite as its acceptance
suite. The DuckDB module had grown to sixteen hundred lines, most of them the
branch overlay, the diff and the merge — none of it DuckDB. A second copy of
that for Delta would be the copy that drifts, and it could not be proved
without a warehouse, which the repository does not have.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| A second backend written from scratch against the interface | Two implementations of the overlay and the merge to keep in step; the platform one testable only live |
| One SQL implementation with engine hooks — **chosen** | The shared code is the code the suite already covers; an engine is the connection, the statement, the bulk load and the type spelling, a page for DuckDB |
| An ORM or query builder over both engines | A third dialect to learn, and the recursive trace and the overlay `UNION` are exactly what such layers express worst |
| Prove the Databricks engine only on a live warehouse | Nothing would guard it on a pull request; a warehouse played by DuckDB reads the same `MERGE`, `DESCRIBE`, `INSTR` and `WITH RECURSIVE`, and can be taught Spark's string escapes |

## Decision

`SqlBackend` holds everything the repository asks of a SQL store; `DuckDBBackend`
and `DatabricksBackend` implement the hooks it leaves open (run, fetch, append,
replace by key, add a column, close; a table's DDL and a reader's values where
the dialect differs). The unit suite's `backend`
fixture runs every test on both engines, the Databricks one over a fake
warehouse on DuckDB, and a third time on a real warehouse when asked. On a
warehouse, rows land as `MERGE` batches of literals (the connector allows 255
parameter markers a statement), and the trace falls back to the same walk in
process when the warehouse has no recursive queries.

## Consequences

- A change to the store is made once and proved on both engines in the
  seconds `make test-fast` takes; the suite runs twice, in about a minute.
- The fake warehouse is a copy of Spark's reading of a statement (types,
  `ADD COLUMNS`, string escapes) that has to be kept true; the live run
  (`make test-live`) is what catches a divergence, and is the Requester's
  first step on a workspace.
- Every engine-specific line is in one module per engine; SQL stays in
  `backend/` (principle `P4`).
