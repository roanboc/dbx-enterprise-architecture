# Business Layer

_[← EA home](../README.md)_

The people and the work around the repository: who plays which role, what
the repository offers them as a service, and the processes through which
content enters, is curated, reviewed and answered from. At Depth 1 this layer
is about the application's own users and its own processes; the enterprise's
business architecture is content *inside* the repository, not this model.

## How to read this document

```mermaid
flowchart LR
  %% legend
  n0["⚉ «Business Role» what they are allowed to be [ROLE#]"]:::business
  n1(["⬭ «Business Service» what the business offers [BSVC#]"]):::business

  n0 --> n1

  classDef business fill:#fffbb5,stroke:#b8a200,color:#333
```

## Analysis order

| #   | Document | Elements | Question it answers |
| --- | -------- | -------- | ------------------- |
| 1   | [1_actors-and-roles.md](./1_actors-and-roles.md) | Actors, Business Roles | Who works with the repository, in which role, and what may each role do? |
| 2   | [2_processes-and-services.md](./2_processes-and-services.md) | Business Services, Business Processes | What does the repository offer the enterprise, and through which processes is it delivered? |

The value stream the processes realise lives in the strategy layer
([1_strategy/2_value-stream.md](../1_strategy/2_value-stream.md)), where
archreator keeps value streams; each of its stages names the processes here
that realise it.

## Layer view

```mermaid
flowchart LR
  subgraph ROLES["Roles"]
    admin["⚉ Admin [ROLE1]"]:::business
    arch["⚉ Architect [ROLE2]"]:::business
    rev["⚉ Reviewer [ROLE3]"]:::business
    reader["⚉ Reader [ROLE4]"]:::business
    agent["⚉ Agent [ROLE5]"]:::ai
  end
  subgraph SVC["Business services"]
    know(["⬭ Architecture knowledge [BSVC1]"]):::business
    gov(["⬭ Governed change [BSVC2]"]):::business
    meta(["⬭ Metamodel stewardship [BSVC3]"]):::business
  end
  reader --> know
  agent --> know
  arch --> gov
  rev --> gov
  admin --> meta

  classDef business fill:#fffbb5,stroke:#b8a200,color:#333
  classDef ai fill:#b2ebf2,stroke:#00acc1,color:#333
```
