# Technology Layer

_[← EA home](../README.md)_

What runs the application today: one Python process over one DuckDB file on
a workstation, and the artifacts around it. The Databricks runtime the roadmap
targets is drawn dashed where it touches this layer and described as a plateau
in [6_transition/](../6_transition/README.md); it becomes rows here once it
runs.

## How to read this document

```mermaid
flowchart LR
  %% legend
  n0["⬒ «Node» where it runs [NODE#]"]:::technology
  n1(["⬯ «Technology Service» what the runtime offers [TSVC#]"]):::technology
  n2[/"⎔ «Artifact» a file the build produces or reads [ART#]"/]:::technology

  n0 --> n1
  n1 --> n2
  n0 -->|reads| n2

  classDef technology fill:#c9e7b7,stroke:#558b2f,color:#333
```

## Analysis order

| #   | Document | Elements | Question it answers |
| --- | -------- | -------- | ------------------- |
| 1   | [1_runtime.md](./1_runtime.md) | Nodes, Technology Services, Artifacts | On what does the software run, which services does the runtime offer it, and which files matter? |

## Layer view

```mermaid
flowchart TB
  subgraph WS["⬒ Workstation [NODE1]"]
    py["⬒ Python process [NODE1.1]"]:::technology
    duck["⬒ DuckDB engine [NODE1.2]"]:::technology
    web(["⬯ Web serving [TSVC1]"]):::technology
    sql(["⬯ Embedded SQL store [TSVC2]"]):::technology
  end
  file[("⎔ Repository file [ART1]")]:::technology
  pack[("⎔ Metamodel pack [ART2]")]:::technology
  dbx["⬒ Databricks workspace [NODE2]"]:::technology
  py --> web
  duck --> sql
  sql --> file
  py -->|reads| pack
  py -.->|realized by, pending| dbx

  classDef technology fill:#c9e7b7,stroke:#558b2f,color:#333
```
