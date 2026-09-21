# Bringing content in — the CSV contract and source mappings

The importer reads plain CSV files. Any source that can export a spreadsheet
can feed the repository; the builder decides how (a one-off export, a
scheduled job, a dbt exposure) and the mapping file says what the columns mean.

## The contract (no mapping needed)

Three kinds of file, matched by name: `*element*.csv`, `*relationship*.csv`,
`*link*.csv`. UTF-8, header row, one entity per row.

**elements.csv**

| column | meaning |
| ------ | ------- |
| `id` | stable identifier of the element in the source (used by relationships); becomes the element id |
| `type` | element type — the pack type id, its name or its plural (`Logical Data Component`, `logical_data_component`) |
| `name` | display name (required) |
| `key` | optional human key (e.g. `DT007`) |
| `description` | Markdown |
| `status` | `draft`, `approved` (default) or `retired` |
| `lifecycle_status` | free text from the source (`Live`, `Planned`, …) |
| `links` | URLs separated by `|` |
| `current_state` | what is true of the artefact today: `proposed`, `planned`, `in_implementation`, `live`, `retired`, `non_existent`. Left blank, it is derived from `lifecycle_status` (see below) |
| `target_state` | what the organisation intends: `undecided` (default), `keep`, `new`, `change`, `decommission`, `merge` |
| `target_work_package` | the id of the work package (initiative) that carries the change |
| `target_note` | why, and into what for `merge` |
| `source_ref`, `origin`, `source_system` | optional provenance overrides; `source_system` overrides `--source` for that row |
| `operation` | `upsert` (default) loads the row; `delete` says the source no longer holds it |
| anything else | an attribute; declared attributes are typed from the pack, others are kept as text |

**relationships.csv**

| column | meaning |
| ------ | ------- |
| `src_id`, `dst_id` | element ids (must exist in this import or already in the store) |
| `rel_type` | relationship type id or its name as written in the pack (`encapsulates`, `is source for`); resolved against the two endpoint types, supertypes and `ANY` included |
| `qualifier` | role qualifier where the type declares one (`Data Steward`) |
| `current_state`, `target_state`, `target_work_package`, `target_note` | the same state columns as elements, optional |
| `status`, `source_ref` | optional |
| `source_system` | which source declared the edge; optional, and it overrides `--source` for that row. A relationship's identity is derived from it, so a file that carries it updates the edge instead of creating a second one |
| `operation` | `upsert` (default) loads the row; `delete` retires the edge |
| anything else | an attribute of the relationship |

**links.csv**: `element_id`, `url`, `label`.

The same URL stated twice for one element — inline in `links` and again in the links file —
lands once, keeping the labelled one.

A links file loaded on its own **adds** to what an element already has: what is stored
stays, a URL sent again may carry a new label, and the rest is appended. An element
whose own row is in the same import is different — that row's `links` column declares
what its links are, so re-importing it with one link leaves it with one.

## What validation does

Every row is checked against the loaded metamodel before anything is written:
unknown type (error, skipped), inactive type (warning, imported), missing name
or id (error), unknown or disallowed relationship (error, skipped — the message
lists what *is* allowed between the two types), qualifier issues (warning),
endpoints that do not exist (error, skipped). `ea validate DIR` runs the check
without loading; `ea import DIR` loads and prints the same report.

Every issue is counted; the report keeps the first 2,000 of them and says so, because a
wrong header makes one issue per row and the two-thousandth tells a reader nothing the
first told them. The command line prints 50 by default (`--issues N`, `0` for every one
kept) and then the totals by code. A load also reports how many rows were new and how
many overwrote something already there.

Re-importing the same files is safe: elements are matched by id and
relationships by (source, type, endpoints, qualifier), so a reload updates
rather than duplicates.

An import writes to the branch you are on: `ea --branch <id> import DIR` on the
command line, the branch shown in the header in the app. On `main` it changes
the model directly, as before.

## Current state from lifecycle text

Most tools carry a free-text lifecycle (`Live`, `Planned`, `Retired 2024`, …).
When `current_state` is not given, the importer derives it: an exact entry of
the mapping's `lifecycle_states` table wins, then the first keyword found in the
text (`retired`, `decommissioned` → `retired`; `in implementation`, `in
development`, `pilot` → `in_implementation`; `planned`, `roadmap` → `planned`;
`proposed`, `candidate`, `draft` → `proposed`; `live`, `production`, `active` →
`live`), and `live` when nothing matches. The lifecycle text itself is kept.

## Mappings

A mapping YAML adapts a source's headers and vocabulary to the contract; see
`connectors/tool-export/mapping.yaml`. Keys:

```yaml
source_system: ea-tool
encoding: utf-8-sig            # how the file is encoded
delimiter: ","                 # the field separator; ";" for a spreadsheet saved in much of Europe
id_prefix: "CMDB-"             # put in front of every identifier this source brings
files: {elements: ["*.csv"], relationships: ["*relationship*.csv"], links: []}
elements:
  match_on: id                     # id (default) or key — which column carries this source's identity
  type_from_filename: false        # true = one file per type, type = file name
  columns: {ID: id, Name: name}    # source header -> contract column
  type_names: {Definition: business_definition}   # source type label -> pack type id
  defaults: {status: approved}
  ignore_columns: [Categories]
  lifecycle_states: {"Being built": in_implementation, "Sunset": retired}   # lifecycle text -> current_state
relationships:
  columns: {Source ID: src_id, Relationship: rel_type, Target ID: dst_id, Role: qualifier}
  rel_names: {"is owner of": position__is_steward_of__information_asset}
```

Headers not listed under `columns` are normalised (`Lifecycle Status` ->
`lifecycle_status`) and treated as attributes.

A file read with the wrong separator parses as a single column, so every row looks as
though it has no `id`. The importer recognises that shape and names the separator the
file was really written with instead of blaming the id column.

**`delimiter` must be a single character.** A tab (`"\t"`) and the ASCII unit separator
(`"\u001f"`) both work and neither appears in ordinary text, so either is a good choice for a
source whose values are full of commas. A two-character separator such as `||` cannot be
supported and is not a matter of effort: Python's CSV writer refuses a delimiter longer than one
character, so the export could not write it; a multi-character separator makes the reader fall
back to a mode that **stops honouring quotes**, so every description holding a newline — every
fenced Mermaid diagram — would break apart into several broken rows; and `|` already separates
the values of `links` and of a multi-valued attribute, so the two meanings would collide. The
problem `||` is reaching for — commas inside a description — is the problem quoting already
solves, which is why a description with commas, quotes and newlines round-trips today.

The Import page takes a mapping YAML of your own as well as the two that ship with the
repository; an uploaded mapping overrides the choice in the dropdown.

## Editing an export in a spreadsheet

The comma is the right separator and quoting handles everything a description can hold —
commas, quotes, and the newlines of a fenced diagram. The risk in a CSV round trip is not the
separator; it is what a spreadsheet does to the file when it saves it, and only some of it can
be recognised afterwards:

| What a spreadsheet does | What happens here |
| ----------------------- | ----------------- |
| Reformats a date (`2024-12-31` → `31/12/2024`) | **Caught** — a `wrong_type` warning naming the attribute, and the raw value is kept rather than guessed at |
| Turns a long numeric identifier into scientific notation (`1.23457E+14`) | **Caught** — a `suspect_identifier` warning, because no source issues an identifier in that shape |
| Strips leading zeros from an identifier (`007` → `7`) | **Not caught, and cannot be.** `7` is a legitimate identifier and nothing in the file records that it was once `007` |
| Re-saves with the machine's list separator | **Caught** — the file parses as one column and is refused by naming the separator it was really written with |
| Truncates a cell past 32,767 characters | **Not caught.** Only a very long description reaches it |

Two things avoid all of it. Format the identifier columns as text before saving, which stops
both the scientific notation and the lost zeros. And set `id_prefix`, which makes every
identifier non-numeric (`CMDB-007`) so a spreadsheet has nothing to reinterpret — worth doing
for the identity reasons below anyway.

## Saying that something is gone

A row whose `operation` is `delete` says the source no longer holds what it names. The row
need carry nothing else — a source deleting something says it is gone, it does not describe it
again — so `id,operation` with `E1,delete` is a complete deletion row. A relationship's row
still carries its two ends and its type, because that is what its identity is derived from.

**What `delete` does is retire, not remove.** The element keeps its relationships, its history
and its place in every view; its `status` becomes `retired`. Three things follow, and they are
why this is the only mode today:

- **It is reversible.** Loading the row again without the indicator brings it back. A feed that
  deletes half an estate by mistake is a re-run away from correct.
- **Nothing is left pointing at nothing.** Removing an element would leave every relationship
  that ended on it dangling, and what should happen to those is not yet settled.
- **A re-sent deletion is not work.** Retiring what is already retired writes nothing and is
  not counted, so a feed re-sending its deletions every night stays quiet.

`deletion_mode` in the mapping names what a source may do. It takes `retire` today; a source
naming anything else is refused with the reason rather than quietly retiring instead.

Deleting something the model does not hold is a `delete_unknown` warning, not an error: a
source is allowed to be sure about what it no longer has.

## Which column is the identity

Every identifier a source brings — the elements it declares, the endpoints of its
relationships, the owners of its links, the work packages it names — goes through one rule,
so the files cannot disagree about what a row is called.

**`id_prefix`** is put in front of all of them. Two systems that both number their rows from
one collide on `1001` without it, and the second load silently overwrites the first. With
`id_prefix: "CMDB-"` the element becomes `CMDB-1001`, while `source_ref` keeps `1001` — the
prefix is the repository's business, not the source's.

**`match_on`** says which column carries the identity the source is merged on:

| | What it means |
| ---- | ---- |
| `id` (default) | The `id` column becomes the element id, prefixed. Right when the source has a stable surrogate key |
| `key` | The `key` column is what the source system knows the row by (`DT007`). An element the repository already holds under that key **keeps the identity it was given**, so a reload updates it however the source has renumbered its `id` column; anything new is created as `<id_prefix><key>`. Endpoints and link owners in the other files are keys too |

Nothing makes a key unique. A key that names two elements is reported as `ambiguous_key` and
merged onto the first by identifier, rather than one being picked silently — that is how an
import rewrites the wrong row. A row with no key, under `match_on: key`, is refused by name.

## Getting content back out

`uv run ea export <dir>` writes the current organisation and branch as the same three files,
and the Import page has **Download current content** beside the template. What comes out goes
back in: an export re-imported lands on the same elements and the same edges rather than beside
them, so the cheapest way to correct a thousand rows is to export them, fix the column in a
spreadsheet, and import the file again.

Beside the three content files it writes **`schema.csv`**, the reference an adopter builds
a feed from: every column the three may carry, the type or file that is its parent, the data
type the value is read as, whether it takes many values, the vocabulary where one is fixed, the
attribute group, and what the pack says the column means. It is written from the metamodel
version the organisation applies, so it describes the columns *this* import will accept. It is
a reference and is not imported back — the Import page says so rather than calling it ignored.

`elements.csv` is written as **one wide file** — the core columns above, then a column for every
attribute any exported element carries, whether the pack declares it or not. A row leaves the
cells that do not apply to its type blank, which is what the importer already reads.

Markdown descriptions survive the trip, fenced Mermaid diagrams included: commas, quotes and
newlines inside a quoted cell are what CSV is for. Two things to know before editing the file in
a spreadsheet — Excel caps a cell at 32,767 characters, and it re-saves using the list separator
of the machine that saved it, which is where `delimiter` comes in.

## Feeds: the same load, from a table

A source that runs on a schedule does not upload a file. It leaves rows in the **staging
schema** of the store's own database — `<EA_SCHEMA>_staging`, which the application creates and
never fills — and the application loads them through the same validation, the same report, the
same identity rules and the same branch targeting a file gets.

What puts the rows there is outside the application: a platform job writing to Postgres, or a
catalogue table replicated into it. **The contract with a source is the shape of the table**,
which is this document's columns, and nothing else. The application never reaches into a
catalogue, which is why a feed costs no new dependency, resource, identity or grant
(decision 0020) — and why the same feed works against DuckDB locally.

A feed names the staging table holding its elements, its relationships and its links, and
carries the same mapping a file import would use, so `id_prefix`, `match_on`, `deletion_mode`
and the column renames are said once whichever way the rows arrive.

Rows are emptied **after** they are loaded, and only when the load succeeded. A run that stops
between the two repeats itself next time, and repeating a load changes nothing the first did
not already change; clearing first would have lost them. A feed reading a table something else
maintains — a replicated catalogue table — is configured to leave it alone.
