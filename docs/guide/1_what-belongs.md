# What belongs in the repository

For everyone who reads or changes the model.

## What the repository is for

The repository holds the enterprise's architecture as a model: the elements the
enterprise is made of — goals, capabilities, processes, information,
applications, technology — and the relationships between them. It answers
questions at the level they are asked: what depends on this system, what a
change touches, who owns this information, which capability a project serves.

Its value is in the relationships. An element nothing relates to answers no
question.

## The boundary

One principle draws the line: **an element earns its place by its
relationships** (principle P9 of this product). It has two tests.

- **Upward.** Below the business layer, every element traces to the business or
  strategy it serves. An application that serves no process, service or
  capability has no reason given for being in the model.
- **Outward.** Something outside its own system relates to it. The inside of a
  system — parts nothing else uses — is not modelled. The system links to the
  page that describes it.

The C4 model gives the vocabulary. It describes software at four levels: system
context, containers, components and code.

| C4 level | In the repository |
| -------- | ----------------- |
| 1 — System context: people, systems, external systems | Always |
| 2 — Containers: applications, databases, queues inside a system | Only when something beyond the system uses it — a shared database, an interface other systems call |
| 3 — Components, 4 — Code | Never: linked from the system |

A system's own detail lives with the system: its wiki, its portal, its code
repository. The repository keeps a link to that page on the system, so a reader
finds the detail in one step.

<!-- boundary -->

## How a change is settled

Top-down. A proposal says first **why** the change is made — the goal, driver or
capability it serves — and **which business** it changes: the processes,
services and roles. The applications, data and technology follow, each one
tracing up to what it serves.

The assistant keeps to that order. It asks about the context before anything
technical, and it asks about any new element that relates only to its own
system. *A purely technical change* is a valid answer: it is recorded, and the
reviewer reads it.

The architect decides every answer. The assistant drafts and asks; nothing is
written to a branch until the architect applies the draft.

## States, work packages, branches, proposals and reviews

- **States.** Every element and relationship says what is true today — its
  current state: proposed, planned, in implementation, live, retired — and what
  the organisation intends — its target state: keep, new, change, decommission,
  merge. The target state shows a change before it happens.
- **Work packages.** A work package is the initiative that delivers a change.
  Every changing element names the work package that changes it.
- **Branches.** A change is made on a branch, never on the model itself. The
  branch is reviewed, then merged into the model, which is called *main*.
- **Proposals.** A proposal is a design handed in: a page in a template, a
  document, links. The assistant reads it into rows and asks what is unclear;
  the architect applies the settled rows to a branch. The conversation stays
  with the proposal.
- **Reviews.** Each element type has reviewers. A branch is approved when every
  type it touches has an approval from one of that type's reviewers.
