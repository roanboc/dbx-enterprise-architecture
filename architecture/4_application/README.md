# Application Layer

_[← EA home](../README.md)_

The software: the services the repository offers, the components providing
them, and where each component lives in the code. Two documents are enough at
this size; collaborations, solution design and interface contracts are folded
into the components document until the component count justifies more.

## How to read this document

```mermaid
flowchart LR
  %% legend
  n0["⊞ «Application Component» a piece of software [ACMP#]"]:::application
  n1["⊸ «Application Interface» where it is reached [ASVC#]"]:::application

  n0 --> n1
  n1 -->|realized by| n0

  classDef application fill:#c2f0ff,stroke:#0288d1,color:#333
```

## Analysis order

| #   | Document | Elements | Question it answers |
| --- | -------- | -------- | ------------------- |
| 1   | [1_application-services.md](./1_application-services.md) | Application Services | What does the software offer its users and the agents? |
| 2   | [2_application-components.md](./2_application-components.md) | Application Components, mapped to source files, with the layering rule and the dependency diagram | Which components provide those services, and how do they depend on each other? |

`2_application-components.md` is where the **grounding rule** bites hardest:
every component row points at the module that implements it, and a component
that does not exist yet is marked **Pending** with the initiative that will
build it.

## Layer view

```mermaid
flowchart TB
  ui["⊞ Web application [ACMP6]"]:::application
  cli["⊞ Command line [ACMP7]"]:::application
  agent["⊞ Agent [ACMP5]"]:::application
  views["⊞ View generator [ACMP8]"]:::application
  svc["⊞ Repository and graph services [ACMP3]"]:::application
  imp["⊞ Importer [ACMP4]"]:::application
  reg["⊞ Metamodel registry [ACMP1]"]:::application
  store["⊸ Graph store [ACMP2]"]:::application
  duck["⊞ DuckDB backend [ACMP2.1]"]:::application
  dbx["⊞ Databricks backend [ACMP2.2]"]:::application

  ui --> svc
  ui --> imp
  ui --> agent
  cli --> svc
  cli --> imp
  agent --> svc
  agent --> views
  ui --> views
  views --> svc
  views --> reg
  svc --> reg
  imp --> reg
  svc --> store
  imp --> store
  health["⊞ Health and search services [ACMP11]"]:::application
  roles["⊞ Roles and review [ACMP12]"]:::application
  ui --> health
  ui --> roles
  health --> svc
  roles --> svc
  store -->|realized by| duck
  store -->|realized by| dbx

  classDef application fill:#c2f0ff,stroke:#0288d1,color:#333
```
