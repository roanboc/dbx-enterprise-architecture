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

The Import page takes a mapping YAML of your own as well as the two that ship with the
repository; an uploaded mapping overrides the choice in the dropdown.

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

`elements.csv` is written as **one wide file** — the core columns above, then a column for every
attribute any exported element carries, whether the pack declares it or not. A row leaves the
cells that do not apply to its type blank, which is what the importer already reads.

Markdown descriptions survive the trip, fenced Mermaid diagrams included: commas, quotes and
newlines inside a quoted cell are what CSV is for. Two things to know before editing the file in
a spreadsheet — Excel caps a cell at 32,767 characters, and it re-saves using the list separator
of the machine that saved it, which is where `delimiter` comes in.
