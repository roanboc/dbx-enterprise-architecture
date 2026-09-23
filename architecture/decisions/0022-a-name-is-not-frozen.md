# 0022 — A published version is frozen in what it defines, and a name is not part of that

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-22 (initiative 21), at the Requester's word — it narrows [0015](./0015-metamodel-versions.md) and leaves the rest of that decision standing. **Touches:** `DOBJ1.6`, `ASVC1`, `ACMP2`, `ACMP13`.

## Context

Decision 0015 froze a published version: content validated against it stays
validated, so its definition cannot change — it is copied into a new draft
instead. The store enforced that by comparing everything on the pack row except
its lifecycle, which meant the pack's **name** counted as part of the frozen
definition.

So a wrong name on a published version could not be corrected. To fix a typo an
admin had to take a draft, rename it, publish it and apply it — three steps and
a new version number for a label nothing reads. The application refused a
name-only save; `ea load-pack` refused a file that differed only in `name:`; and
a scenario existed to prove that refusal.

The Requester asked for the name to be renameable in place, and
[0021](./0021-an-opaque-pack-identifier.md) had already removed the reason to
be careful: nothing keys off the name, because the identifier does that and it
is opaque.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Leave the freeze as it is | Correct on the letter of 0015, and it makes a typo cost a version number. A freeze exists to protect what content was validated against, and a label was never that |
| A rename produces a new draft to be published and applied | What the code did. Three admin steps and a version number nobody wanted, for a change that alters nothing anything reads |
| **Narrow the freeze to what a version *defines* — chosen** | `name` joins `status`, `derived_from` and `notes` outside the frozen definition. A published version is still frozen in every domain, type, relationship type and attribute it declares |
| Move `description` out with it | `description` is arguably the same kind of thing and would move by the same mechanism. Not taken: the Requester approved the name, and widening an approval is not the agent's to do |
| Move `source` and `provenance_values` out too | Rejected on the merits. `source` says where a definition came from and `provenance_values` is the vocabulary the registry checks a type's provenance against, so both are part of what content was validated under |

## Decision

**A published or retired version is frozen in what it defines.** Its name is a
label: nothing is stored against it and nothing looks anything up by it, so it
is corrected where it is wrong, at any point in a version's life.

A retired version is included. It is kept to be read by whoever once applied
it, and a wrong name on one is worth correcting for exactly that reader.

A pack **file** renames in place as well, not only the application. The
alternative is a file format carrying a `name:` the file can never change,
where a name-only edit is accepted and silently does nothing — which is worse
than either a refusal or a rename.

A rename is written through the same path that refuses everything else, and is
recorded in the change log with the name the version had. The row keeps no
history of its own, and a correction nobody can trace back is not one anybody
can argue with.

## Consequences

- `sql_backend.NOT_DEFINITION` is where the line is drawn, in one place, and
  the version diff draws the same line: its summary ends "define the same
  metamodel", so reporting a difference in what neither version defines was
  contradicting its own sentence.
- A rename is invisible in a version diff. It is visible in the versions
  listing, in the change log, and on every screen — and it changes nothing
  content validates against, which is what a diff is read for.
- The scenarios that proved the old refusal now prove both halves: a name-only
  file is accepted and takes effect, and a file that changes what the version
  defines is still refused as frozen.
- 0015 stands otherwise. A published version's definition is still frozen, a
  draft is still edited in place, and a change to a metamodel is still a new
  version tried in an organisation of its own.
