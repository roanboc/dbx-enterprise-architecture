# Project Scope — The Enterprise Level

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Motivation.
**Delivered as:** branch `claude/great-franklin-30i81n`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 22.

Strategy discovery, documents only. At the Understanding gate of the initiative
that follows ([initiative 24](./24_proposals-refined-in-conversation.md)), the
Requester set two rules for what the repository holds: a change is understood
top-down, strategy and business before technology; and what lies inside one
system — its internal components, which interface with nothing else — does not
belong in the enterprise architecture and is referenced from the system instead.
Asked whether a framework draws that line better, the Requester agreed to one
definition: **an element belongs when something outside its own system relates to
it**, with the C4 model's levels as the vocabulary. Both rules state what every
change is tested against, so they are a principle, and a principle is approved at
**Direction**.

## What changes

**One principle, not two.** The two rules are the same test pointed in two
directions — what an element relates to — so they are one principle with two
tests:

- **`P9` — An element earns its place by its relationships.** *Upward:* below the
  business layer, an element traces to the business or strategy it serves.
  *Outward:* something outside its own system relates to it. The inside of a
  system is not modelled; the system links to the page that describes it.

| C4 level | At the enterprise level |
| -------- | ----------------------- |
| 1 — System context: people, systems, external systems | Always |
| 2 — Containers: applications, databases, queues inside a system | Only when something beyond the system uses it — a shared database, an API other systems call |
| 3 — Components, 4 — Code | Never: linked from the system |

The one-page brief gains the same point in a sponsor's words.

## EA alignment

**Depth 1 — Application.** Verdict: **strategy discovery** — the change adds a
principle.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | [1_motivation.md](../1_strategy/1_motivation.md): `P9` added, realising `G1` (a model at the level questions are asked at, traceable to why). [3_pitch.md](../1_strategy/3_pitch.md): the point in plain words. |
| 2_business to 5_technology | **Not in this initiative.** How the product keeps to `P9` — the assistant's questions, the metamodel marking where a pack draws its line, the guide that explains it — is [initiative 24](./24_proposals-refined-in-conversation.md). |
| Transition | No change here; initiative 24 opens the gap it closes. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |

## What comes next

[Initiative 24](./24_proposals-refined-in-conversation.md) — proposals refined in
conversation — builds the tests of `P9` into the assistant and the metamodel, and
the in-app guide that states the boundary for enterprise and solution architects.
