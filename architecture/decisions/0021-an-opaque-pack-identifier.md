# 0021 — A metamodel's identifier means nothing, so its name is free to change

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-22 (initiative 21), at the Requester's word — it extends [0003](./0003-metamodel-as-data.md) and [0015](./0015-metamodel-versions.md) rather than reopening either. **Touches:** `DOBJ1`, `DOBJ1.6`, `ASVC1`, `ACMP1`, `ACMP2`, `ACMP13`, `ART2`.

## Context

The Requester asked for a metamodel's name to be changeable, and said what the
identifier should be instead:

> identifier should be a hash that no longer changes, as opposed to keys
> dependent on name. Name could change without dependency.

A pack's name and its identifier were already separate fields, so nothing in
code *derived* one from the other. What was true is that the identifier **read
like a name.** It was a slug — `higher_education` — and it was the key of
`meta_pack`, of the five `meta_` tables under it, of every organisation's
`pack_id`, of `derived_from`, and half of every `<pack id>@<version>` a person
typed. Rename the framework and the key was left describing something that no
longer existed, with nothing anywhere that would notice.

A key that reads like a name is also a key somebody will read. The header
showed it, the Versions table showed it, `ea metamodel versions` printed it —
each of them offering a value that looked like an answer and was not one.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Leave the slug and allow renaming | The stated ask, taken literally, and the smallest change. Rejected because it leaves every key describing a name that may since have moved — the rename works and the repository quietly stops making sense |
| A digest of the pack's content | What "a hash" says on its face. Rejected because it is the opposite of "no longer changes": edit a draft and the key moves, taking every organisation that applies it |
| **An opaque identifier, minted once — chosen** | `mm_` and sixteen Crockford base32 characters. Eighty bits, so it needs no registry to stay unique; nineteen characters, so it reads back over a desk; no `i`, `l`, `o` or `u`, so it is never a word and `1`/`l` and `0`/`O` are never confused. It satisfies the column the store already has, so there is no DDL, no new column and no re-indexing on either engine |
| Minted per store on load | Rejected outright. `save_pack` matches a row by `(pack_id, version)`, and `ea init`, `make seed` and the deployed application all re-load the shipped file routinely — so a value minted per load forks the framework on every start, and two stores can never exchange a pack |
| A third, readable "handle" beside the identifier, for typing | Rejected. It removes the quoting a name with spaces needs on the command line, and reintroduces exactly the readable key this decision removes — something would come to depend on it |

## Decision

**A pack's identifier is opaque and permanent.** It is minted once when a
framework is first written down, carried unchanged by every version of it, and
never recomputed — not from the name, and not from the content.

**The pack file carries it.** A file written since this decision is taken at
its word; anything else is folded deterministically rather than minted, from
the identifier it had, or from its name when it had none. A store brought
forward in place and one seeded from the shipped file therefore land on the
same key without either having to ask the other, and loading one file twice is
the no-op it looks like.

**Readability moves to the service.** `MetamodelService.resolve()` dispatches
on one look at the first characters: a token beginning `mm_` is an identifier,
exact or a prefix of at least six; anything else is a name, matched through
`slugify`. Two packs matching is a refusal that lists them, never a silent
pick — choosing one for somebody who was ambiguous is how the wrong metamodel
gets applied to an organisation.

**A screen shows the name.** The canonical `<pack id>@<version>` stays the only
form anything stores or passes between layers. The identifier is shown in one
place, the Versions table, where a person picks one up to paste into a command.

## Consequences

- Renaming a framework moves no row in the six `meta_` tables and breaks no
  `organisation.pack_id`. That is what makes [0022](./0022-a-name-is-not-frozen.md)
  possible at all.
- An existing store is re-keyed in place when it is next opened, across the six
  `meta_` tables, `organisation.pack_id` and the `derived_from` prefix. No DDL,
  no new column, no index change, on DuckDB or on Lakebase. A store holding
  both an old and a new key for one framework at one version is left as it is
  with a warning: an application that will not open is worse than a row
  somebody has to look at.
- `change_log` is not rewritten. It records what happened under the names things
  had at the time, and rewriting a record of the past to match the present is
  not a migration.
- The store's keys carry no framework's name, which is `P5` enforced by the
  data rather than by review.
- A pack whose name has spaces must be quoted on the command line, or reached
  by its identifier's prefix. That is the cost of refusing a readable handle,
  and it is named in scope document 21 as a thing somebody may ask to change.
- Nothing sorts or compares identifiers for meaning: versions are ordered by
  when they were loaded, the "more than one pack" checks are set cardinality,
  and the diff keys off type identifiers. What is lost is alphabetical order in
  a listing, which the page and the command line recover by sorting on the name.
