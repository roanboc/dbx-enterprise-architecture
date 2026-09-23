# Metamodel packs

A pack is the whole definition of an architecture framework as data: element
types, their attributes and supertypes, relationship types with the endpoint
types they allow, domains, provenance, and the viewpoints its diagrams are
drawn under. The engine loads a pack into the `meta_*` tables and everything
else — validation, forms, the type graph, the agent's vocabulary, the exported
drawings — follows from it. Changing the metamodel is editing this
file (or the Metamodel page); no code or DDL changes.

A pack is stored **per version**, and a version has a life: a `draft` is edited
in place, a `published` one is frozen so that what was validated against it
stays validated, and a `retired` one is kept for the record and applied to
nobody. Each organisation applies exactly one version, and applying is preceded
by a check of that organisation's content against it (decision
[0015](../architecture/decisions/0015-metamodel-versions.md)). So a change to
the metamodel is a new version, tried where it can do no harm, and published
when it is right.

## The two packs that ship

| Pack | What it is | Why it is here |
| ---- | ---------- | -------------- |
| `higher_education/` | An anonymised university's TOGAF-based metamodel: 59 element types and 54 relationship types, with the endpoint pairs the source document allows | The first configuration, and what the sample content is typed against |
| `archimate_core/` | The ArchiMate 3.2 core: six layers as domains, 28 element types, and the standard's relationships declared once against `ANY` | The second worked pack. Principle `P5` says no framework lives in `src/`, and one pack cannot show that — whatever the engine assumed about the first would just look like the engine working. Loading a framework with different layers, different types and relationships that are not declared per pair is what tests the claim |

Both live in one store, each applied by an organisation of its own
(decision [0014](../architecture/decisions/0014-organisations-as-a-partition.md)):

```bash
uv run ea load-pack packs/archimate_core/metamodel.yaml
uv run ea org create "ArchiMate trial" --metamodel "ArchiMate Core@3.2"
uv run ea --org archimate-trial summary
```

A further pack lands beside them with the same shape — and either of these two
is picked from the Organisations page instead, which stores it and starts a new,
empty organisation on it.

**A pack's `id:` is opaque.** It is minted once, carried by the file and never
recomputed, so the `name:` beside it is free to change and nothing breaks
(decisions [0021](../architecture/decisions/0021-an-opaque-pack-identifier.md)
and [0022](../architecture/decisions/0022-a-name-is-not-frozen.md)). A file
written with a readable `id:`, or with none at all, is folded onto a permanent
one deterministically, so loading it twice is one framework rather than two.
Name a version by its name, or by the first few characters of its identifier —
both reach the same place.

**Watch the commas.** A `description:` inside a `{...}` flow mapping ends at
the first comma, and the rest becomes a key of its own that the engine keeps in
`properties` without a word. Quote any description that carries one —
`description: 'A, B'`.

Loading a file says so when it sees the shape — an empty property whose key
reads like prose — on `ea load-pack`, in the log, and on the Metamodel page's
**Load YAML file…**. It is a warning, not a refusal: only the author can say
whether the key was meant. `tests/test_second_pack.py` fails a **shipped** pack
that does it.

## File shape (`metamodel.yaml`)

```yaml
pack:
  id: higher_education
  name: ...
  version: "2026-08-11"       # the version this definition is stored under
  status: published           # draft (editable) | published (frozen) | retired
  derived_from: pack@version  # optional: the version this one was drafted from
  notes: ...                  # optional: what this version tries
  description: ...
  source: ...
  provenance_values: [TOGAF, CORE_EA, LOCAL]
  properties: {}              # optional: anything the framework wants kept here
domains:
  - {id, name, description, properties: {}}
attribute_groups:             # the sections an element's attributes are read in, in this order
  - {id, name, description, properties: {}}
common_attributes:            # every element may carry these
  - {name, label, type, required, enum, group, default, multiple, unit,
     pattern, min, max, help, description, sensitivity, properties: {}}
element_types:
  - id: information_asset     # [a-z][a-z0-9_]*
    name: Information Asset
    plural: Information Assets
    supertype: business_information   # optional; relationships on the supertype apply
    active: true                       # false keeps the type importable but flagged
    abstract: false                    # true groups its sub-types; no element may be one
    deactivation_reason: ...
    domain: information
    provenance: LOCAL                  # one of pack.provenance_values
    prefix: IA                         # for minted ids
    description: ...
    examples: [...]
    source_of_record: ...              # informational: where instances come from
    type_owner: ...
    instance_owner: ...
    attributes: [{name, label, type, ...}]   # the same keys as common_attributes
    properties: {}
relationship_types:
  - id: logical_data_component__encapsulates__data_entity
    name: encapsulates
    inverse: is encapsulated by
    source: logical_data_component     # type id or ANY
    target: data_entity                # type id or ANY
    provenance: CORE_EA
    qualifiers: [Owner, Data Steward]  # optional role qualifier values
    diagrams: [information]            # which domain diagrams show it
    description: ...
    src_max: 1                         # optional cardinality hints
    dst_max: null
    attributes: [{name, label, type, ...}]   # what a relationship of this type carries
    notation: {archimate: realization, direction: forward}   # how the export draws it
    properties: {}
viewpoints:                   # what a diagram is for; the reader picks one at export
  - id: application_cooperation
    name: Application cooperation
    description: ...
    element_types: [logical_application_component, interface, data_entity]   # empty or absent: every type
    relationship_types: []             # empty or absent: every type
    bands: type                        # layer (default) | type | related
    band_order: [logical_application_component, interface, data_entity]      # top to bottom
    band_type: role                    # bands: related — the type whose elements are the bands
    band_relationships: [role__performs__process]   # bands: related — what places an element in a band
    other_band: Other                  # the band for what the rule cannot place
    nest: [logical_data_component__encapsulates__data_entity]   # drawn as one shape inside another
    span: [physical_application_component__processes__data_entity]   # drawn as a bar across the shapes
    properties: {}
```

A relationship declared on a supertype is allowed for all its sub-types; `ANY`
allows any element type. Any key the format does not name is kept in
`properties` rather than dropped, so a framework loses nothing by being loaded
here.

## What an attribute declares

`name` and `type` are the only required keys. Everything else narrows what a
value may be, or says how the form and the page show it; the registry validates
a value against all of it and reports what does not fit rather than refusing
the row.

| Key | Meaning |
| --- | ------- |
| `type` | `string`, `text` (Markdown), `integer`, `number`, `boolean`, `date`, `url`, `json` |
| `label` | What the form and the page call it; the name title-cased when absent |
| `required` | An element without it is reported as incomplete |
| `enum` | The values it may take; anything else is reported |
| `default` | What a new element starts with |
| `multiple` | Several values, written `a \| b` or `a; b`; the form gives a tag input |
| `unit` | Shown after the label: `Cost (AUD)` |
| `pattern` | A regular expression the value must match |
| `min`, `max` | Bounds for a number, or the first and last date |
| `group` | The `id` of an entry in `attribute_groups`. An element's attributes are read and edited in these sections, in the order the pack declares them, so a long list is a page rather than a wall. The Metamodel screen offers the declared groups rather than a text box, because a typo used to make a section of its own that nobody could see was a mistake. A group written as a label (`group: Governance`) still resolves by name, and one that nothing declares is **added** to the pack rather than dropped |
| `help` | One line under the control, where the description is too long |
| `sensitivity` | Marks the value restricted wherever it is shown |
| `properties` | Anything else the framework keeps with the attribute |

## What a viewpoint declares

What a diagram is for: which elements and relationships it admits, what its
bands are, and which relationships are drawn as a line, as one shape inside
another, or as a bar across several. The reader picks one when a view is
exported, and the application draws what it says (decision
[0023](../architecture/decisions/0023-a-viewpoint-is-pack-data.md)). A
viewpoint belongs to the version it is declared in: a published version
freezes its viewpoints with its types, and `ea metamodel diff` reports a change
to them. A viewpoint naming a type the version does not declare is refused on
load. A pack with none exports the layered drawing.

`id` is the only required key, and `name` is the id when absent. A type named
anywhere below admits its sub-types too.

| Key | Meaning |
| --- | ------- |
| `element_types` | The element types the drawing admits. Empty or absent: every type |
| `relationship_types` | The relationship types drawn. Empty or absent: every type |
| `bands` | What the drawing is banded by. `layer`, the default, is a band per ArchiMate layer of the notation; `type` is a band per element type; `related` is a band per element of `band_type`, each holding the elements reached from it through `band_relationships` — a swimlane per role, a band per stage |
| `band_order` | The bands from the top: layer names for `layer`, type ids for `type`. Absent: the layers in the standard's order from motivation down, or the types in the order the view meets them |
| `band_type` | With `bands: related`, the element type whose elements are the bands. Required there |
| `band_relationships` | With `bands: related`, the relationship types that place an element in a band, in either direction |
| `other_band` | The title of the last band, which takes every element the rule cannot place. `Other` unless named; a drawing that silently dropped an element would lie about the model |
| `nest` | The relationship types drawn as one shape inside another: the whole end holds the part end. The whole is the source unless the type's notation says `direction: reverse`, when it is the target |
| `span` | The relationship types drawn as a bar: the target end becomes a bar across the sources related to it, or the source end when the notation runs in reverse |
| `overview_relationships` | The relationship types an **overview** keeps between elements other than the focus. Absent: the structural ArchiMate kinds by the types' notation (composition, aggregation, realization, assignment, serving, triggering, flow). A line touching the focus, and one the viewpoint nests, spans or bands by, is always kept |
| `properties` | Anything else the framework keeps with the viewpoint |

The four each shipped pack declares are the worked examples. In
`higher_education/`: **Layered** (every element, a band per layer, the
capability, organisation unit and process hierarchies nested); **Application
cooperation** (the application, interface, integration, data and technology
types in a band per type, a data entity inside the logical data component that encapsulates
it); **Process cooperation** (a swimlane per role that performs a process,
`Not performed by a role` for the rest); and **Staged delivery** (a band per
capability holding what realises it, a data entity spanning the applications
that process it). `archimate_core/` carries the same four in the standard's
own words: layered, application cooperation, business process cooperation and
implementation and migration, the last a band per plateau with a deliverable
spanning the work packages that realise it.

## Notation (`notation:` on a domain or an element type)

How a type is drawn when a view is generated from the model. A flat map of
strings; a type without one inherits its supertype's, then its domain's, then
the engine's defaults. Nothing in the engine knows the values, so a framework
brings its own convention.

| Key | Meaning | Example |
| --- | ------- | ------- |
| `layer` | The ArchiMate layer whose colour fills the node in a generated view, named in the line above the diagram: `motivation`, `strategy`, `business`, `application`, `technology`, `physical`, `implementation`, `other` | `application` |
| `glyph` | One character shown before the stereotype, as the architecture documents do | `▤` |
| `stereotype` | The word in guillemets: `«Data Object»` | `Data Object` |
| `archimate` | The ArchiMate 3 element the draw.io export uses for its stencil. The type whose notation says `WorkPackage` is the one the Target state page and the Propose module treat as the work package (initiative) | `DataObject` |
| `shape` | Mermaid node shape: `rect`, `round`, `stadium`, `hex`, `cyl`, `subroutine`, `diamond`, `asym` | `rect` |
| `colour` | On a domain: the palette name the app uses for badges and legends (`blue`, `pink`, `yellow`, `gray`, `teal`, `grape`, …) | `blue` |
| `hex` | On a domain: the fill colour the graphs use for its elements | `#4dabf7` |

```yaml
domains:
  - id: information
    notation: {layer: application, glyph: '▤', stereotype: Data Object, archimate: DataObject, shape: rect}
element_types:
  - id: information_asset
    domain: information
    notation: {layer: business, glyph: '▤', stereotype: Business Object, archimate: BusinessObject, shape: rect}
```

## Notation (`notation:` on a relationship type)

How a relationship type is drawn when a view is exported: the ArchiMate
relationship whose arrowhead the edge takes, and which way the standard's
direction runs along it. A type with no notation is drawn as a plain directed
line.

| Key | Meaning | Example |
| --- | ------- | ------- |
| `archimate` | One of the ArchiMate 3 relationships: `composition`, `aggregation`, `assignment`, `realization`, `serving`, `access`, `influence`, `triggering`, `flow`, `specialization`, `association` | `realization` |
| `direction` | `forward` (the default) when the standard's direction — whole to part, active to behaviour, realiser to realised — runs from the type's source to its target; `reverse` when it runs the other way, so `position__belongs_to__organization_unit`, whose source is the part, still nests the position inside the unit | `forward` |

```yaml
relationship_types:
  - id: logical_data_component__encapsulates__data_entity
    source: logical_data_component
    target: data_entity
    notation: {archimate: composition}
```
