# Information Layer

_[← EA home](../README.md)_

The passive structure of the repository: the metamodel that says what may
exist, the architecture graph that holds what does exist, and the exchange
files and audit trail around them. This layer describes the repository's
*own* information; the enterprise content it holds (the enterprise's own elements) is data
inside `DOBJ2`, not elements of this model.

## How to read this document

```mermaid
flowchart LR
  %% legend
  n0[/"⎔ «Artifact» a file the build produces or reads [ART#]"/]:::technology
  n1["▦ «Data Object» what is stored [DOBJ#]"]:::application

  n0 -->|loaded into| n1
  n1 -->|persisted in| n0

  classDef technology fill:#c9e7b7,stroke:#558b2f,color:#333
  classDef application fill:#c2f0ff,stroke:#0288d1,color:#333
```

## Analysis order

| #   | Document | Elements | Question it answers |
| --- | -------- | -------- | ------------------- |
| 1   | [1_data-objects.md](./1_data-objects.md) | Data domains, the Data Objects inside them, their code locations, persistence and classification | What information exists, in which domain, where does it live, how sensitive is it? |
| 2   | [2_conceptual-data-model.md](./2_conceptual-data-model.md) | The same data objects as entities — no new element | What are the entities, and how many of one hangs off another? |
| 3   | [3_logical-data-model.md](./3_logical-data-model.md) | The same entities as tables — no new element | Which table holds what, keyed how, referencing what? |
| 4   | Data flows | — | Folded into document 1 (one flow: pack → registry → tables; CSV → importer → tables → app and agent) |
| 5   | Data architecture | — | Folded into document 1: one DuckDB file locally, one Lakebase schema later, same DDL |

**Every data object belongs to a domain, and the identifier carries it.** The
three domains are the level-1 rows of the catalogue (`DOBJ1` the metamodel,
`DOBJ2` the architecture graph, `DOBJ3` exchange and audit) and their objects
extend them (`DOBJ2.1`).

**The catalogue is the only document that defines an element here.** Documents 2
and 3 read the same objects at two more levels of detail — the entities and
their cardinalities, then the tables, their keys and their references — because
a catalogue row says what an object is and not how much of it may exist or what
it is stored as.

## Layer view

```mermaid
flowchart LR
  subgraph META["DOBJ1 Metamodel"]
    pack[/"⎔ Metamodel pack [ART2]"/]:::technology
    reg["▦ Element type · Relationship type · Attribute"]:::application
  end
  subgraph GRAPH["DOBJ2 Architecture graph"]
    el["▦ Element · Relationship · Link"]:::application
    store[/"⎔ Repository file [ART1]"/]:::technology
  end
  subgraph XCH["DOBJ3 Exchange and audit"]
    csv[/"⎔ Exchange files [ART3]"/]:::technology
    log["▦ Change log · Import report"]:::application
  end

  pack -->|loaded into| reg
  reg -->|validates| el
  csv -->|imported as| el
  el -->|persisted in| store
  el -->|every write recorded in| log

  classDef business fill:#fffbb5,stroke:#b8a200,color:#333
  classDef application fill:#c2f0ff,stroke:#0288d1,color:#333
  classDef technology fill:#c9e7b7,stroke:#558b2f,color:#333
```
