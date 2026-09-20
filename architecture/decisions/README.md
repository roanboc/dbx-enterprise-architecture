# Decisions

_[← Repository README](../../README.md) · [Enterprise architecture](../README.md)_

One file per decision, numbered chronologically, each explaining a single
call that is smaller than an initiative (see [scope/](../scope/README.md))
but consequential enough that a future reader will ask "why this and not the
alternative?".

## Index

| #   | Decision | Status | Touches |
| --- | -------- | ------ | ------- |
| [0001](./0001-ui-stack.md) | Dash with Mantine components, AG Grid and Cytoscape for the app | Accepted 2026-09-05 | `ACMP6` |
| [0002](./0002-store-and-engines.md) | A generic graph schema on DuckDB now and Delta later, with in-process traversal | Accepted 2026-09-05; the platform store superseded by 0013, the traversal moved into the store by 0016, the size it assumes restated by 0019 | `ACMP2`, `ACMP3`, `DOBJ2` |
| [0003](./0003-metamodel-as-data.md) | The metamodel is a data pack, and typed tables are a generated projection | Accepted 2026-09-05 | `ACMP1`, `DOBJ1` |
| [0004](./0004-agent-grounding.md) | The agent only drafts, only uses tools, and every identifier it cites is checked | Accepted 2026-09-05 | `ACMP5` |
| [0005](./0005-generated-views.md) | Generated views, not a diagram editor | Accepted 2026-09-05 | `ACMP8`, `ASVC6`, `P8` |
| [0006](./0006-branches-as-overlays.md) | Branches as overlays on the same schema, merged once with base versions | Accepted 2026-09-06 (built) | `ACMP2`, `ACMP3`, `DOBJ2.5`, `DOBJ2.6` |
| [0007](./0007-current-and-target-state.md) | Current and target state as core fields, analysed by work package | Accepted 2026-09-06 (built) | `DOBJ2.1`, `DOBJ2.2`, `ASVC8` |
| [0008](./0008-roles-from-groups.md) | Roles derived from workspace groups, a debug persona locally, one permission function | Accepted 2026-09-06 | `ACMP12`, `ROLE1`–`ROLE5` |
| [0009](./0009-review-before-merge.md) | Review before merge, approved per element type by assigned reviewers | Accepted 2026-09-06 | `ACMP12`, `DOBJ2.7`, `BPROC2.4` |
| [0010](./0010-application-test-round.md) | A browser-driven test round on demand, unit tests on every change, and an accessibility floor | Adopted 2026-09-09, for the Requester to confirm | `ACMP6`, `ACMP7` |
| [0011](./0011-one-sql-store-two-engines.md) | The store is written once on SQL, and an engine adds only its dialect | Adopted 2026-09-09, for the Requester to confirm; the engine it names replaced by 0013 | `ACMP2`, `ACMP2.1`, `ACMP2.2`, `TSVC4` |
| [0012](./0012-workspace-groups-looked-up.md) | The forwarded user's groups are read from the workspace, once, and kept for a few minutes | Adopted 2026-09-09, for the Requester to confirm | `ACMP12`, `TSVC5` |
| [0013](./0013-lakebase-not-the-lakehouse.md) | Lakebase, not the lakehouse, is the store on Databricks | Accepted 2026-09-11 (the Requester's instruction) | `ACMP2.3`, `TSVC6`, `NODE2`, `ART6`, `PLAT2`, `GAP16` |
| [0014](./0014-organisations-as-a-partition.md) | An organisation is a partition of the one store, not a second store | Adopted 2026-09-19, for the Requester to confirm | `DOBJ2.8`, `ASVC11`, `ACMP2`, `ACMP13` |
| [0015](./0015-metamodel-versions.md) | The metamodel is kept in versions, and a published version is frozen | Adopted 2026-09-19, for the Requester to confirm | `DOBJ1.6`, `ASVC1`, `ACMP1`, `ACMP13` |
| [0016](./0016-a-walk-not-an-enumeration.md) | A traversal is a walk over the graph, not an enumeration of its paths | Adopted 2026-09-20, for the Requester to confirm | `ASVC4`, `ACMP2`, `DOBJ2.2` |
| [0017](./0017-keys-indexed-references-not.md) | The database holds the keys, and the references stay in the services | Adopted 2026-09-20, for the Requester to confirm | `ACMP2`, `DOBJ1.6`, `DOBJ2.1` |
| [0018](./0018-a-schema-per-group.md) | A schema per group of tables | Adopted 2026-09-20, for the Requester to confirm | `ACMP2`, `ACMP2.1`, `ACMP2.3`, `DOBJ1`, `DOBJ2`, `DOBJ3` |
| [0019](./0019-the-size-the-application-declares.md) | The application declares the size it is built for | Proposed 2026-09-20, with initiative 16 at the Understanding gate | `ASM6`, `ASVC4`, `ACMP3`, `DOBJ2`, `GAP18` |
