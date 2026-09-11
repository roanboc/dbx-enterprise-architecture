# Target state

_[← Roadmap](./README.md) · [EA home](../README.md)_

**Status: `◐` draft catalogue** — the plateaus and gaps as the owner set them
on 2026-09-05 after the business-case review. Approved at the **Direction**
gate (recorded in [scope/1_curriculum-poc.md](../scope/1_curriculum-poc.md));
the gaps beyond `PLAT1` are intent, not work.

## How to read this document

```mermaid
flowchart LR
  %% legend
  n0[["≡ «Plateau» a state the architecture reaches [PLAT#]"]]:::implementation
  n1(("⊘ «Gap» what stands between two plateaus [GAP#]")):::implementation

  n1 --> n0

  classDef implementation fill:#ffd6d6,stroke:#d99b9b,color:#333
```

## Plateaus

```mermaid
flowchart LR
  p1["≡ Local PoC on DuckDB [PLAT1]"]:::implementation
  p2["≡ Same application on Databricks [PLAT2]"]:::implementation
  p3["≡ Real content with provenance [PLAT3]"]:::implementation
  p4["≡ Governed change [PLAT4]"]:::implementation
  p5["≡ Semantic front doors [PLAT5]"]:::implementation
  p6["≡ Current EA tool retired [PLAT6]"]:::implementation
  p2 -->|depends on| p1
  p3 -->|depends on| p1
  p4 -->|depends on| p2
  p5 -->|depends on| p2
  p5 -->|depends on| p3
  p6 -->|depends on| p4
  p6 -->|depends on| p5

  classDef implementation fill:#f8d7da,stroke:#c0392b,color:#333
```

| ID | Plateau | Status | What is true when it is reached |
| -- | ------- | ------ | ------------------------------- |
| `PLAT1` | **Local PoC on DuckDB** — the four deliverables (metamodel manager, element browse and edit, CSV ingestion, grounded agent) run on a DuckDB file with the higher-education pack and the curriculum export; extended by initiative 2 with generated architecture views and answer documents | In flight — initiatives 1 and 2 | The owner can show the app on the curriculum slice; the information architect has seen it |
| `PLAT2` | **Same application on Databricks** — the app runs on Databricks Apps, the store is a schema in a Lakebase database the bundle creates, identity comes from the workspace | In flight — initiative 13 (built 2026-09-09: the bundle, the workspace identity, an engine on a SQL warehouse) and initiative 14 (built 2026-09-11: the plateau restated on Lakebase, the engine and the bundle rebuilt on it; the run on a workspace pending) | Same tests pass against a Lakebase instance; one deployment bundle |
| `PLAT3` | **Real content with provenance** — every type of the institution's metamodel is loaded, every type declares mirrored, authored or enriched semantics, and the mirrored ones are fed from their sources (the CMDB, the HR system, the project portfolio tool, the information asset register, the data platform's metadata catalogue) by scheduled jobs | Planned | A fact from the CMDB is never edited by hand in the repository; freshness is visible per source |
| `PLAT4` | **Governed change** — proposals are change sets with a base version, an impact assessment and a recorded approval; stewards and owners review in the app; sensitive attributes are granted by role | In flight — initiatives 4 to 7 delivered the change sets, the roles and the review on DuckDB; the platform's identity and grants wait for `PLAT2` | No approved status is written without a recorded human decision |
| `PLAT5` | **Semantic front doors** — a typed, commented projection with keys is generated from the metamodel into Unity Catalog; Business Definitions and Measures are published to the Unity Catalog business glossary and metric views; Genie-based agents over the projection, or whichever agent framework the platform offers, traverse the graph and answer in Markdown, with questions, answers and user feedback logged for monitoring and improvement; a tool server exposes the model to external agents | Planned | The three reference questions are answered through a Genie-based agent and through an external agent, with the same identifiers |
| `PLAT6` | **Current EA tool retired** — the repository is the system of record for authored types, the mirror for the rest, and the diagrams architects need are generated from it | Planned | The current tool's licence not renewed; retirement criteria agreed with the IT division's enterprise architecture team |

## Gaps

```mermaid
flowchart LR
  p2["≡ Same application on Databricks [PLAT2]"]:::implementation
  p3["≡ Real content with provenance [PLAT3]"]:::implementation
  p5["≡ Semantic front doors [PLAT5]"]:::implementation
  p6["≡ Current EA tool retired [PLAT6]"]:::implementation
  g1["⊘ No Delta backend [GAP1]"]:::implementation
  g2["⊘ No deployment bundle [GAP2]"]:::implementation
  g16["⊘ No Lakebase engine [GAP16]"]:::implementation
  g3["⊘ No real institutional content [GAP3]"]:::implementation
  g4["⊘ No source feeds [GAP4]"]:::implementation
  g6["⊘ No projection, glossary or Genie-based agent [GAP6]"]:::implementation
  g7["⊘ No tool server for external agents [GAP7]"]:::implementation
  g8["⊘ No retirement criteria for the current EA tool [GAP8]"]:::implementation
  g1 -.-> p2
  g2 -.-> p2
  g16 -.-> p2
  g3 -.-> p3
  g4 -.-> p3
  g6 -.-> p5
  g7 -.-> p5
  g8 -.-> p6

  classDef implementation fill:#f8d7da,stroke:#c0392b,color:#333
```

| ID | Gap | Between | Closed by |
| -- | --- | ------- | --------- |
| `GAP1` | **No Delta backend** — the store interface has one implementation | `PLAT1` and `PLAT2` as first stated | Initiative 13 (built 2026-09-09): the store written once on SQL, and a Databricks engine on a SQL warehouse; superseded when initiative 14 restated `PLAT2` on Lakebase (decision 0013) and retired that engine — the store written once is what stands |
| `GAP2` | **No deployment bundle** — `app.yaml` exists, the bundle, catalog, schema, warehouse and grants do not | `PLAT1` and `PLAT2` | Initiative 13 (built 2026-09-09): `databricks.yml` with the schema, the app and its warehouse, the grant step after the first deploy; rebuilt by initiative 14 (2026-09-11) around a Lakebase instance and the app's database resource, with no grant step; the deploy waits for a workspace |
| `GAP3` | **No real institutional content** — the sample model stands in for the curriculum export | `PLAT1` and `PLAT3` | The current tool's export loaded through the export mapping (inside initiative 1 once the CSVs arrive) |
| `GAP4` | **No source feeds** — the current EA tool's export is the source of everything; nothing distinguishes a mirrored fact from an authored one yet | `PLAT1` and `PLAT3` | Initiative 4: per-type source-of-record semantics enforced, scheduled feeds |
| `GAP5` | **No change-set model** — edits are immediate, with optimistic concurrency and a change log but no proposal, review or approval | `PLAT1` and `PLAT4` | Core closed by initiative 4 (built 2026-09-06): branches as overlays, diff with base versions, merge item by item with conflicts resolved; the review and approval flow by a second person follows once roles are enforced |
| `GAP6` | **No projection, glossary or Genie-based agent** — the graph is generic tables only | `PLAT2` and `PLAT5` | Initiative 6: generated typed views with comments and keys, glossary publishing to Unity Catalog, Genie-based agents |
| `GAP7` | **No tool server for external agents** — the agent's tools are in-process | `PLAT2` and `PLAT5` | Initiative 6 |
| `GAP8` | **No retirement criteria for the current EA tool** — nobody has written down what must be true before the current tool goes | `PLAT5` and `PLAT6` | Agreed with the IT division's enterprise architecture team before initiative 7 |
| `GAP9` | **Views are graph layouts, not architecture diagrams** — neighbourhood, impact and agent answers show force-directed graphs; an answer has no picture | `PLAT1` as delivered by initiative 1 and `PLAT1` as extended | Initiative 2 (built 2026-09-05): a view model rendered to Mermaid in the archreator notation on the Element and Impact pages, answers composed into documents with views |
| `GAP10` | **No reusable diagram export** — an architect who wants to start a solution diagram from the model has nothing to open in a diagram tool | `PLAT1` and `PLAT1` as extended | Initiative 2 (built 2026-09-05): the same view exported as a draft draw.io file with ArchiMate stencils and an element identifier on every shape |
| `GAP11` | **No notation editor, hard-coded colours, fixed diagrams, graphs that overlap** — the metamodel's visual styles had no editor, the app's domain colours lived in code, generated diagrams could not be arranged, and the network graphs had no grouping | `PLAT1` as extended by initiative 2 and `PLAT1` as extended further | Initiative 3 (built 2026-09-05): Notation tab with live preview, colours in the pack, draggable views exported to draw.io, one graph panel with grouping and compound layouts; roles documented, none enforced by the owner's decision |
| `GAP12` | **No target state model** — an element has a workflow status and the source tool's lifecycle text, no current state against a target state, no work package to analyse by | `PLAT1` and `PLAT4` | Initiative 4 (built 2026-09-06): current and target state on every element and relationship, derived from lifecycle text on import, the Target state page with the current-by-target matrix, marked views in Mermaid and draw.io |
| `GAP13` | **No proposal intake** — a design document cannot be handed to the repository; every element is typed in by hand or imported from a tool | `PLAT1` and `PLAT4` | Initiative 5 (built 2026-09-06): the Propose page with the editable merge-log preview, the pushback rule, the Proposal Template; a hosted reader for free text, a stub for the template |
| `GAP14` | **No roles, no review before merge** — every user could do everything and any author could merge their own branch; nothing recorded a second person's decision | `PLAT1` and `PLAT4` | Initiative 7 (built 2026-09-06): roles derived from groups (Admin, Architect, Reviewer, Reader, Agent) enforced in the app and the command line, a debug persona switcher locally, review requested and decided per element type before a merge |
| `GAP15` | **Nothing tells the model's health** — no way to see which source went stale, which types lack descriptions or owners, or to fix many rows at once; search read names only | `PLAT1` and `PLAT3` | Initiative 6 (built 2026-09-06): full-text search over descriptions and attributes, bulk edit from Browse, the Health page with freshness per source and completeness per type |
| `GAP16` | **No Lakebase engine** — the store's platform engine spoke to a SQL warehouse, not to the transactional database an application needs | `PLAT1` and `PLAT2` | Initiative 14 (built 2026-09-11): the Lakebase engine on the same DDL, proved on a Postgres the test run starts for itself in every run and on a Lakebase instance by `make test-live`, which waits for a workspace |

## Gaps closed so far, and by what

```mermaid
flowchart LR
  p1["≡ Local PoC on DuckDB [PLAT1]"]:::implementation
  p2["≡ Same application on Databricks [PLAT2]"]:::implementation
  p4["≡ Governed change [PLAT4]"]:::implementation
  g1["⊘ No Delta backend [GAP1]"]:::implementation
  g2["⊘ No deployment bundle [GAP2]"]:::implementation
  g16["⊘ No Lakebase engine [GAP16]"]:::implementation
  g9["⊘ Views are graph layouts, not architecture diagrams [GAP9]"]:::implementation
  g11["⊘ No notation editor, hard-coded colours, fixed diagrams, graphs that overlap [GAP11]"]:::implementation
  g5["⊘ No change-set model [GAP5]"]:::implementation
  g12["⊘ No target state model [GAP12]"]:::implementation
  g13["⊘ No proposal intake [GAP13]"]:::implementation
  g14["⊘ No roles, no review before merge [GAP14]"]:::implementation
  g15["⊘ Nothing tells the model's health [GAP15]"]:::implementation
  g9 -->|closed, initiative 2| p1
  g11 -->|closed, initiative 3| p1
  g12 -->|closed, initiative 4| p4
  g13 -->|closed, initiative 5| p4
  g5 -->|core closed, initiative 4| p4
  g14 -->|closed, initiative 7| p4
  g15 -->|closed, initiative 6| p1
  g1 -->|closed in code, initiative 13, superseded| p2
  g2 -->|closed in code, initiatives 13 and 14| p2
  g16 -->|closed in code, initiative 14| p2

  classDef implementation fill:#f8d7da,stroke:#c0392b,color:#333
```

## Relationships

| From | | To | | Relationship | Note |
| ---- | - | -- | - | ------------ | ---- |
| `PLAT2` | ▭ «Plateau» Same application on Databricks | `PLAT1` | ▭ «Plateau» Local PoC on DuckDB | depends on | same code, second engine |
| `PLAT3` | ▭ «Plateau» Real content with provenance | `PLAT1` | ▭ «Plateau» Local PoC on DuckDB | depends on | the importer and the pack |
| `PLAT4` | ▭ «Plateau» Governed change | `PLAT2` | ▭ «Plateau» Same application on Databricks | depends on | workspace identity and grants |
| `PLAT5` | ▭ «Plateau» Semantic front doors | `PLAT2` | ▭ «Plateau» Same application on Databricks | depends on | Unity Catalog is where the projection lives, reading the Lakebase database registered there |
| `PLAT5` | ▭ «Plateau» Semantic front doors | `PLAT3` | ▭ «Plateau» Real content with provenance | depends on | a projection of sample data sells nothing |
| `PLAT6` | ▭ «Plateau» Current EA tool retired | `PLAT4` | ▭ «Plateau» Governed change | depends on | authored types need governance before the current tool goes |
| `PLAT6` | ▭ «Plateau» Current EA tool retired | `PLAT5` | ▭ «Plateau» Semantic front doors | depends on | diagrams and glossary must come from somewhere |
