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
| `source_ref`, `origin` | optional provenance overrides |
| anything else | an attribute; declared attributes are typed from the pack, others are kept as text |

**relationships.csv**

| column | meaning |
| ------ | ------- |
| `src_id`, `dst_id` | element ids (must exist in this import or already in the store) |
| `rel_type` | relationship type id or its name as written in the pack (`encapsulates`, `is source for`); resolved against the two endpoint types, supertypes and `ANY` included |
| `qualifier` | role qualifier where the type declares one (`Data Steward`) |
| `current_state`, `target_state`, `target_work_package`, `target_note` | the same state columns as elements, optional |
| `status`, `source_ref` | optional |
| anything else | an attribute of the relationship |

**links.csv**: `element_id`, `url`, `label`.

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
files: {elements: ["*.csv"], relationships: ["*relationship*.csv"], links: []}
elements:
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
