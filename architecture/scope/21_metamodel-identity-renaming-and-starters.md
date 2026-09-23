# Project Scope — Metamodel Identity, Renaming and Starters

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/enterprise-arch-assessment-iln3rz`.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 20.
**Target plateau:** `PLAT1` extended, on the way to `PLAT3`.
**Gap:** `GAP22` **A metamodel is known by a name that cannot change, and
nothing starts from one that ships**, opened and closed by this initiative.

The Requester asked for three changes to the Metamodel page after using it:
the Manage lists reordered, a metamodel's name made changeable, and a way to
*start with some metamodels*. The first is a screen detail inside an element
the model already names and was coded directly, with no document and no gate.
The other two add to what `ASVC1` claims, so they were aligned through the
layers and stopped at **Understanding** before anything was written. This
document records that gate and what followed it.

## What was asked, and what it turned out to be

The Requester's words on the identifier decided the shape of the whole
initiative:

> identifier should be a hash that no longer changes, as opposed to keys
> dependent on name. Name could change without dependency.

Read literally that is two things, and only the second was obvious. A
metamodel's name and its identifier are already separate fields — `Pack.name`
is "Higher Education EA Metamodel" and `Pack.id` is `higher_education` — so
nothing was *derived* from the name in code. What was true is that the
identifier **reads like a name**: it is a readable slug, it is the key of
`meta_pack` and of the five `meta_` tables under it, it is what every
organisation's `pack_id` holds, it is half of every `<pack id>@<version>`
reference typed on the command line, and it is shown in the header. Rename the
framework and the key is left describing something that no longer exists, with
no mechanism that would ever notice.

So the ask is not a rename feature with a key change bolted on. It is the
reverse: **make the key meaningless, and the rename follows.** That is what
was built.

One correction was made to the request and is recorded here rather than put
back to the Requester as a question. An identifier that is a hash *of the
content* would change whenever the content changed, which is the opposite of
"no longer changes". The identifier is therefore opaque but not a digest of
anything that moves: it is minted once from a namespace and the framework's
first identifier, and never recomputed.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Is the key minted per store, or carried in the pack file?** | Carried in the file | A migrated store and a freshly seeded one land on the same key, so the same framework loaded into two stores stays one framework. Minted per load, every `ea init` would fork the metamodel, because `save_pack` matches a row by `(pack_id, version)` |
| **How does a person name a version now?** | By its name, or by a unique prefix of its identifier | A token beginning `mm_` is an identifier, anything else is a name matched through `slugify`. Two candidates is a refusal that lists them, never a silent pick. The alternative — a third, readable "handle" field — reintroduces exactly the key the Requester asked to remove |
| **Does the rename reach a retired version?** | Yes | The freeze is on what a version *defines*. A label is not a definition, and a retired version is kept to be read, so a wrong name on one is worth correcting |
| **May a pack *file* rename a published version, or only the screen?** | The file too | The alternative is a file format that carries a `name:` the file can never change: a name-only edit would be accepted and silently do nothing, which is worse than either a refusal or a rename |
| **Does `description` leave the frozen definition with `name`?** | No | The Requester approved the name. `description` is arguably the same kind of thing and would move by the same mechanism, but widening an approval is not the agent's to do. Named below as left |
| **What happens to identifiers already in a store?** | Re-keyed | Grandfathering them would let `DOBJ1.6` claim only that an identifier is never *derived*, not that it is opaque — and the store would carry two kinds of key indefinitely, which every read path would then have to tolerate |
| **Does the command line gain a starter verb?** | No | `ea load-pack <file>` followed by `ea org create --metamodel <ref>` already does it. The approval covers the application control, and a second way to say the same thing owes its own scenario |
| **Does the version diff still compare the name and the notes?** | No | The suite found it: `diff.summary()` ends "define the same metamodel", and a diff that reported a difference in what neither version *defines* was contradicting its own sentence. The same line decision 0022 draws for the freeze is drawn here. A rename is visible in the versions listing and in the change log, and it changes nothing content validates against. This closes a scenario (`M68`) that had never passed, because behaviour and assertion shipped disagreeing |
| **What does the metamodel summary say the pack is?** | Its name | `Registry.summary_markdown` opened `# <name> (pack \`<id>\`, …)`. That line is read by people and by the agent, and neither can do anything with an opaque key |

## What changed in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `DOBJ1.6` | **Metamodel version** | The key is now stated as opaque and permanent, and the name as a label nothing keys off, corrected at any point in a version's life. The freeze is restated as a freeze on what a version *defines* |
| `DOBJ1` | **Metamodel pack** | The Holds cell named the two shipped packs by their slug identifiers, which is the thing this initiative removes |
| `ASVC1` | **Metamodel management** | Gains renaming at any point in a version's life, and starting from a metamodel the repository ships |
| `ASVC11` | **Organisation management** | An organisation can now be started empty on a starter, not only copied from another |
| `ACMP2` | **Graph store** | The freeze clause narrowed to what a version defines |
| `ACMP6` | **Web application** | The two new controls, and where they live |
| `ACMP13` | **Metamodel lifecycle and organisation services** | Renaming, starting empty on a starter, and the starters themselves |
| `ART2` | **Metamodel pack** | A pack file carries the identifier its framework is stored under; one without is a framework the store has not met |
| `GAP22` | **A metamodel is known by a name that cannot change…** | Opened and closed by this initiative. Defined in [1_target-state.md](../6_transition/1_target-state.md), which is where a gap lives |
| decision 0021 | **An opaque pack identifier** | New |
| decision 0022 | **A name is not frozen** | New. It narrows [0015](../decisions/0015-metamodel-versions.md) and leaves the rest of it standing |

`ACMP7` **Command line** is deliberately unchanged — see the calls table.

## EA alignment (assessed top-down before implementing)

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change, and one thing it enforces.** `P5` says nothing framework-specific in `src/`. The starter catalogue is therefore read from a directory and each file's own header, never from a list of framework names in code; and the opaque identifier removes a framework name from the store's keys as a side effect. `G5` **Reusable by any enterprise** is what the starters serve. |
| 2_business | **No change.** Who may edit a metamodel is unchanged; renaming is an Admin's write like every other metamodel write, behind the same `require()`. |
| 3_information | `DOBJ1.6` and `DOBJ1` re-worded; the conceptual and logical models follow them. No data object is added: a starter is a file the repository ships, not something the store holds until it is picked. |
| 4_application | `ASVC1` and `ASVC11` widened; `ACMP2`, `ACMP6` and `ACMP13` re-worded. No component is added. |
| 5_technology | `ART2` re-worded. The store schema is **unchanged** — the new identifier satisfies the existing column and index, so there is no DDL, no new column and no index change on either engine. |
| Transition | `GAP22` opens and closes. Step 1k added to the sequence. |

## What was built, and what was deliberately left

Left, and each is a thing somebody may reasonably ask for next:

1. **`description` out of the frozen definition.** The same argument as the
   name, and the same mechanism. Not built, because the approval covered the
   name and widening an approval is not the agent's to do.
2. **A starter verb on the command line.** Two existing commands already do
   it.
3. **The first run.** `EA_PACK` still names one pack as what `ea init` and
   `make seed` load, so `src/ea/config.py` still holds one framework's
   directory name as a default path. The starters are additive and do not
   touch it. Closing that is what would take the last framework name out of
   `src/`.
4. **A readable handle for typing.** Named in the calls table. A pack whose
   name has spaces has to be quoted on the command line, or reached by its
   identifier's prefix.

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------------- |
| Understanding | The product owner | 2026-09-22 | Three questions, each with the options the code makes possible and the cost of each: which name was meant (the display name, the identifier, or both); whether renaming a published version should be allowed given that decision 0015 and `DOBJ1.6` freeze it, and that a scenario exists to prove the refusal; and which of four shapes the starters should take. The Requester answered that the identifier should be opaque and permanent with the name free of it, that the name should be renameable in place, and that a starter should begin a new organisation. Those three answers are the approval this row records |

**Direction** was not sought and no row records it: `GAP22` sits under
plateaus the roadmap already holds, and nothing here changes where the project
is going.
