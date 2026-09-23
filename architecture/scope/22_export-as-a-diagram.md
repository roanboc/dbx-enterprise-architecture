# Project Scope — Export as a Diagram

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/enterprise-arch-assessment-iln3rz`.
**Requester:** the product owner, with the feedback of the solution
architects who open the exported files. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 21.
**Target plateau:** `PLAT1` extended.
**Gap:** `GAP23` **An exported diagram is a grid, not a drawing**, opened and
closed by this initiative.

The Requester opened a draw.io file the Ask page had exported, beside two
diagrams a solution architect had drawn by hand, and named what was wrong with
the export: connectors crossing each other with nothing written on them, a
font too small to read inside the shapes, and no thought given to where things
sit on the page. The hand-drawn diagrams group what belongs together, run in
one direction, and say on every line what the line means. The export was a
grid of identical boxes in stacked bands, and the difference is what this
initiative closes. The Requester also asked that the reader, not the
application, say what a diagram is *for*, so the picture comes from the
viewpoint and the focus the reader names.

## What was asked, and what it turned out to be

Three things were asked for, and they are three different layers of one
change:

1. **The mechanics.** The exported file had no font size on its shapes, so
   every name was drawn at the tool's default; a box was one fixed size
   whatever it held; an edge left a shape wherever the tool chose and crossed
   whatever was in the way; a label sat on the line with no background; every
   relationship was drawn with one arrowhead; the page was a fixed A4 sheet
   the drawing overflowed. None of this needs a design decision. It is fixed
   by writing into the file what a person would set by hand: a readable font,
   a box sized to its name, a port on each end of an edge, a label with a
   background, an arrowhead for the kind of relationship, a page sized to the
   drawing, a title and a legend.
2. **The layout.** A drawing with bands has most of its layout decided:
   the band gives the row, and what remains is the order within a band and
   the column each shape lands in, chosen so the lines between neighbouring
   bands cross as little as possible. That is a small, deterministic piece of
   code on the graph library the application already ships, and not a
   dependency (decision 0024).
3. **The viewpoint.** Which elements a diagram admits, what its bands are,
   and which relationships are drawn as a line, as one shape inside another,
   or as a bar across several, is framework knowledge. It lives in the pack
   as data (decision 0023), the reader picks one when they export, and the
   application draws what the viewpoint says. Four ship with each pack.

The screens keep the layout the browser gives them. The layout built here is
for the file, because a file is exported from the command line and by the
agent as well as from a page, and none of those has a browser.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Where does a viewpoint live?** | In the pack, as a section of its own, stored as a JSON column of `meta_pack` | It is part of what a version *defines*, so a published version's viewpoints are frozen with the rest; the version diff reports a change to them; and `P5` holds, because the application knows the grammar of a viewpoint and no viewpoint by name |
| **How does the application know which arrowhead a relationship takes?** | A relationship type carries a `notation` block naming its ArchiMate relationship, the way an element type names its ArchiMate element | The ArchiMate core pack names its own eleven; the higher-education pack maps each of its 54 onto the nearest one. A type that names none is drawn as a plain directed line, which is what every edge was before |
| **Bands by what?** | A viewpoint bands by architecture layer, by element type, or by a related element of a named type reached through named relationship types | The first is today's drawing done properly; the second is the application cooperation viewpoint; the third is a swimlane per role and a band per stage, which are the two hand-drawn diagrams the Requester showed |
| **What of an element the viewpoint's bands cannot place?** | It goes into a last band the viewpoint names, "Other" unless it says otherwise | A diagram that silently drops an element the reader asked for is a diagram that lies about the model; a band called Other is a visible answer |
| **Which viewpoints ship?** | Four per pack, mirroring the ArchiMate 3.2 example viewpoints that cover the Requester's three files: layered, application cooperation, process cooperation, and a staged delivery | The higher-education pack's four are drawn from its own diagram vocabulary (the `diagrams` key its relationship types already carry). Each is `adopted` and stays for the Requester to correct |
| **Does the reader choose the focus as well as the viewpoint?** | The focus is the element the page is about, and the reader may add to it | A neighbourhood or an impact grows from one element and the page already names it; the export dialogue shows it, takes the viewpoint, the depth and the layers, and lets the reader mark further elements as focus. Re-growing from a different element is picking a different element on the page |
| **Does the on-screen diagram follow the viewpoint?** | No | The screen is drawn by the browser's layout and stays so. Applying a viewpoint's element and relationship filter on screen is named below as left |
| **Is a viewpoint editable on the Metamodel page?** | Not in this initiative | It is edited in the pack file and loaded, like any other section, and read on the page. The page's Manage lists were reordered at the Requester's word and a sixth list owes its own scenario |
| **What happens to a store seeded before this initiative?** | Its published version gains the drawing rules once, on the next load of the shipped file | The store holds that version without viewpoints or notation, and `ea init` and `make seed` re-load the file routinely. Refusing it as a change to a frozen version would stop every store from before this initiative. A viewpoint and an arrowhead govern drawings and nothing content validates against, so the version takes them the way it takes a corrected name, logged; a file that also changes a type is refused whole |
| **May a relationship type's notation be edited on the Metamodel page?** | Not in this initiative | The Notation tab edits how a domain and an element type are drawn; a relationship type's arrowhead is edited in the pack file. The Manage grids carry no column for it and keep what the version has when they save. Named below as left |
| **Does the sample model gain process content?** | No | The process cooperation viewpoint has nothing in the sample to draw. The test builds its own handful of processes and roles, because seventeen assertions pin the sample at 47 elements and a viewpoint is not a reason to move them |
| **A dependency for the layout?** | No | Decision 0024: the two candidates ship compiled extensions, are under a year old, and solve the part of a layered layout the bands already decide |
| **How far may an export reach?** | As far as the page it is taken from | The Element page's dialogue reaches three hops, like its Graph tab; the Impact page's reaches six, like its own depth control, so an impact the tables answer in full is exported in full |

## What changed in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `DOBJ1.8` | **Viewpoint** | New: what a diagram admits, bands by, nests and spans; declared by a pack and frozen with the version |
| `DOBJ1.2` | **Relationship type** | Gains the ArchiMate relationship it is drawn as |
| `DOBJ2.4` | **Architecture view** | A view is exported through a viewpoint the reader picks; the layout in the file is the application's own |
| `ASVC6` | **Architecture views** | Gains the export dialogue (viewpoint, focus, depth, layers), the layered layout, the mechanics, and the viewpoints on the command line |
| `ACMP6` | **Web application** | The export dialogue on the Element, Impact, Ask, Target state and Metamodel pages |
| `ACMP7` | **Command line** | `ea view --viewpoint` and `--layers`, `ea viewpoints` |
| `ACMP8` | **View generator** | Gains the layout module and the export mechanics |
| `ART2` | **Metamodel pack** | Carries the viewpoints and the relationship notation |
| `GAP23` | **An exported diagram is a grid, not a drawing** | Opened and closed by this initiative. Defined in [1_target-state.md](../6_transition/1_target-state.md) |
| decision 0023 | **A viewpoint is pack data, and the reader picks it** | New |
| decision 0024 | **The layout is the application's own code** | New |

## EA alignment (assessed top-down before implementing)

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **No change, and two things it enforces.** `P8` **Diagrams are generated views, never the store** stands: a layout is computed on export and never stored, and every shape still carries its element identifier and its link. `P5` decides where viewpoints live: in the pack, never in code. Serves `G1` **Query the architecture sustainably** and `G5` **Reusable by any enterprise**. |
| 2_business | **No change.** Who may export is unchanged: every role that may read a view may export it. |
| 3_information | `DOBJ1.8` added; `DOBJ1.2` and `DOBJ2.4` re-worded. The logical model gains two JSON columns: `viewpoints` on `meta_pack` and `notation` on `meta_relationship_type`, added by the migration list the store already applies on start-up. |
| 4_application | `ASVC6` widened; `ACMP6`, `ACMP7` and `ACMP8` re-worded. No component is added. |
| 5_technology | `ART2` re-worded. **No new dependency** (decision 0024). The store schema gains two columns on both engines, no table and no index. |
| Transition | `GAP23` opens and closes. Step 1l added to the sequence. |

## Plateaus

| Plateau | State |
| ------- | ----- |
| **Baseline** (before) | A view exported to draw.io is a grid: one band per layer stacked on an A4 page, every box one size, no font size, one arrowhead, edges leaving wherever the tool decides, no title, no legend; the reader cannot say what the diagram is for |
| **Target** (delivered) | The reader names a viewpoint the pack declares, the focus, the depth and the layers; the file carries a title, bands the viewpoint defines, shapes sized to their names in a readable font, nesting and spanning where the viewpoint says so, an arrowhead per kind of relationship, a labelled edge with ports at both ends, a legend, and a page sized to the drawing — deterministically, so two exports of one view are one drawing, the file differing only in the time it says it was exported |

## Work packages and deliverables

### WP1 — The viewpoint and the relationship notation as pack data

- **Deliverables:** `Viewpoint` and `RelationshipType.notation` in
  `src/ea/models.py`; the `viewpoints:` section and the relationship
  `notation:` block read and written by `src/ea/metamodel/loader.py`; the two
  columns in `src/ea/backend/sql.py` and `src/ea/backend/sql_backend.py`;
  `Registry.viewpoints()`, `Registry.viewpoint()` and
  `Registry.rel_notation()`; the version diff over viewpoints in
  `src/ea/metamodel/diff.py`; four viewpoints and a notation on every
  relationship type in both `packs/*/metamodel.yaml`; `packs/README.md`.
- **Outcome:** a framework says what its diagrams are, and the application
  reads it.

### WP2 — The layered layout

- **Deliverables:** `src/ea/views/layout.py` — bands from the viewpoint,
  order within a band by barycentre, placement and compaction, nesting,
  spanning, and a port and waypoints per edge; `tests/test_layout.py`.
- **Outcome:** a deterministic drawing from a view and a viewpoint, without a
  browser and without a dependency.

### WP3 — The file

- **Deliverables:** `src/ea/views/drawio.py` — font sizes, shapes sized to
  their names, an arrowhead per ArchiMate relationship, labels with a
  background, ports and waypoints, nested children as children of their
  parent's cell, a title, a legend, the note, a page sized to the drawing;
  the same mechanics on the file exported from the browser's arrangement;
  `tests/test_drawio_quality.py` and the golden files under
  `tests/golden/drawio/`.
- **Outcome:** a file a solution architect opens and edits rather than
  redraws.

### WP4 — The reader picks

- **Deliverables:** the export dialogue in `src/ea/ui/export.py`, opened
  by the draw.io control on the Element, Impact, Ask, Target state and
  Metamodel pages; `apply_viewpoint()` in `src/ea/views/model.py`;
  `ea view --viewpoint --layers` and `ea viewpoints` in `src/ea/cli.py`;
  `tests/test_viewpoints.py` and the browser scenarios that read the dialogue.
- **Outcome:** the picture comes from the viewpoint and the focus the reader
  names.

## In scope / out of scope

| In scope | Out of scope (gaps, candidate future work) |
| -------- | ------------------------------------------- |
| The export mechanics, on the grid path and on the browser-arranged path | A round trip: reading a drawing back as a source for Propose (initiative 24, proposed) |
| A deterministic layered layout in the application's own code | A general graph layout for a viewpoint without bands |
| Viewpoints as pack data, four per shipped pack, picked by the reader | A viewpoint editor on the Metamodel page |
| The on-screen export dialogue and the command line | The viewpoint applied to the on-screen diagram |
| Bands by layer, by type and by a related element; nest and span | Bands by an attribute's value |
| The relationship notation kept by the page, and a version from before this initiative upgraded once | The relationship notation edited on the page |
| A legend of the layers and the relationship kinds present | A guided tour of the export (initiative 23, proposed) |

## Gap notes

- **A viewpoint editor.** The grammar is small enough for a form: a list of
  element types, a list of relationship types, a banding rule, two lists of
  relationship types for nesting and spanning. It is a sixth Manage list and
  its scenarios; nothing in the store stands in its way.
- **The viewpoint on screen.** `apply_viewpoint()` filters a view, and the
  Mermaid renderer draws whatever view it is given, so the filter is one
  control on the Graph tab. Banding on screen is a different matter: the
  browser lays the diagram out, and it knows nothing of bands.
- **Bands by an attribute.** A stage that is an attribute value rather than an
  element (a lifecycle, a tier) cannot band a diagram yet. It is one more
  `bands` mode in the grammar and a lookup in the layout.
- **A relationship type's notation on the page.** Two cells on the
  relationship types grid, the ArchiMate relationship and its direction, and
  the Notation tab's preview drawing one sample edge per kind. Nothing in the
  store stands in its way; the page keeps the notation it cannot show.
- **A drawing as a source.** Every shape carries `ea_id`; nothing reads a
  file back. Proposed as initiative 24, behind its own gate.

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------------- |
| Understanding | The product owner | 2026-09-23 | The three layers of the change (mechanics, layout, viewpoints) diagnosed from the Requester's own exported file and the two hand-drawn diagrams; the four viewpoints per pack; the reader naming the viewpoint, the focus, the depth and the layers at export; and the recommendation to write the layout rather than depend on a library, with the two candidates' compiled wheels and ages as the reason. The Requester approved the initiative as described, in the order 22 then 23 then 24 |

**Direction** was not sought and no row records it: `GAP23` sits under a
plateau the roadmap already holds, and nothing here changes where the project
is going.
