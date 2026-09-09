# AGENTS.md

**EA Repository** — a generic, metamodel-driven enterprise architecture
repository that runs on DuckDB locally and on Databricks later, configured
first with an anonymised higher-education metamodel. This file is the standing instruction for any
coding agent (and any person) working in this repository. The model of the
project itself lives in [`architecture/`](./architecture/README.md); the code
lives in [`src/ea/`](./src/ea).

## The rule that governs everything else

**Strategy and information architecture are validated before any other layer,
and the Requester approves at an explicit gate before development.** A change
to what the model claims — an element added, removed or re-related, a rule it
states contradicted — is never coded directly: align it through the numbered
EA layers (`architecture/1_strategy` → `3_information` → `4_application`),
stop at **Understanding** for the Requester's approval, record it in a scope
document (`architecture/scope/`), then implement. At Depth 1 that is the only
gate an ordinary change meets; **Direction** belongs to discovery and to the
roadmap. A change inside an element the model already names — a screen, a
filter, an import format for a service that exists, a defect — is coded
directly and documents nothing; one that only keeps a row true edits the row
in the same commit. `model.py --project . names <path>` says which element
names a file, or that none does.

**Ask only what blocks the work now.** A question reaches the Requester when
the answer changes what gets built now and nothing in the model settles it.
Everything else is the agent's call — taken, applied, and written into the row
it changes with `Source` reading `adopted — <the call>`, in a document that
stays `◐`, so a later word from the Requester overrides it. Never ask about a
state that does not exist yet.

**The PoC posture** (initiatives 1 to 5, built; the Databricks step next):
iterate and fail fast inside the approved scope, keep the long-term roadmap in
[`architecture/6_transition/`](./architecture/6_transition/README.md) honest,
and never quietly widen the PoC with a roadmap item.

## Who decides

| Role | Who | Does |
| ---- | --- | ---- |
| **Requester** | The product owner (a university's data and analytics unit), with the information architect validating the information layer | Says what should change — a requirement or a problem, not a diff. **Grants the gate approvals** before any code is written |
| **Agent** | The coding agent (or a person) | Works the change through the layers, stops at Understanding, decides what the model already settles, writes the scope document, implements, opens a pull request |
| **Reviewer** | The product owner | Reviews and merges. Nothing ships without a human approving it |

An approval that isn't recorded didn't happen: every gate granted is written
into the scope document's Approvals table, with who approved, when, and what
was shown. One that was not granted gets no row — the table records what
happened, not a census of what did not.

## The method comes from the archreator plugin

This repository enables the [archreator](https://github.com/roanboc/archreator)
plugin (`.claude/settings.json`: marketplace `archreator`, plugin
`archreator@archreator`), so every session, local or remote, holds the same
rulebook. Three skills surface on their own — `align-change-through-layers`
when a requirement arrives, `architecture-document-style` and `document-style`
when a document is edited; every other skill is invoked by name, and a skill
that hands off to one reads it from disk. **Invoke the skill before the step,
not after:**

| Step | Skill |
| ---- | ----- |
| Writing or editing anything under `architecture/` | `architecture-document-style`, on its own (every element document opens with its legend, **each section opens with its own diagram and its own tables follow it** — never every diagram stacked at the top; a node reads `<glyph> <name> [<ID>]` and carries no stereotype outside the legend; identifiers, status glyphs, relationship tables) |
| Opening an initiative from a requirement | `align-change-through-layers`, on its own, then `/archreator:write-scope-document` |
| Touching the roadmap in `6_transition/` | `/archreator:plan-the-transition` |
| Recording a call smaller than an initiative | `/archreator:record-decision` |
| Describing a pull request | `/archreator:write-pr-description` |

The two validators under `scripts/` are copies of the plugin's scaffold
scripts (`plugins/archreator/scaffold/scripts/`, plugin version 0.4.0) so that
CI, which has no plugin, runs the same checks. Keep them identical to the
plugin's; a change to a validator goes upstream first. Without the plugin
(a session where it failed to load), read the skill from the plugin's
repository before writing a layer document: the validators check identifiers,
status, that each section's diagram comes before that section's tables, and
that no node label carries a stereotype outside a fence marked `%% legend` —
not the rest of a document's shape.

## Modeling depth

**Declared depth: 1 — Application.** The repository manages an enterprise
model but is itself one application; its strategy layer is light (motivation
only), its business and technology layers are declared gaps on the front door
until the PoC has users and runs on Databricks. The enterprise content it holds
(the institution's elements) is data inside the application, not this model.

## Layout

- `architecture/` — the model of this project. Its `README.md` is the front
  door and says, per layer, what is modeled, what is a gap and why.
  **A folder exists only once it holds something.** Every document that
  defines an element says how far it has been validated (`○`, `◐`, `●`);
  `scripts/check_model.py` fails one that declares nothing.
- `architecture/reference/` — says what the model was built from (the owner's
  business case and the institution's metamodel document), which are held
  privately and are not in this public repository.
- `packs/` — metamodels as data (`higher_education` today). `connectors/` — the
  CSV contract and per-tool column mappings (`tool-export`). `data/sample/` — a
  fictional university's curriculum slice so the demo works without real data.
- `src/ea/` — `models` → `metamodel` → `backend` → `services` → `views`,
  `importer`, `agent` → `ui`, plus `cli.py`. `views/` renders a subgraph of the
  model as Mermaid or draw.io from the pack's `notation`; nothing is drawn by
  hand and every shape carries an element identifier (principle `P8`). `ui/graph.py`
  is the one network-graph panel (grouping, layouts, pack colours);
  `assets/ea-views.js` lets a reader arrange a generated view without saving it. A module imports only from layers to its
  left; SQL lives in `backend/` only; framework and institution names live in
  `packs/` and `connectors/` only.
- **Branches and states.** `main` is the model; a branch is an overlay on the
  same tables (decision 0006), and the current branch is a context variable
  (`backend/branching.py`) that every read and write honours: the app sets it
  from the session, the CLI from `--branch`, a service from `use_branch()`.
  Never write to `branch_*` tables directly and never bypass it. Every element
  and relationship carries `current_state`, `target_state`,
  `target_work_package` and `target_note` (decision 0007); the vocabularies
  live in `models.py` and are not extended per pack. The Propose module
  (`agent/proposal.py`) writes only to a branch and only what the architect
  ticked.
- **Roles.** The role is a context variable too (`services/roles.py`), set per
  request from the identity headers (or the debug persona under mock
  authentication) and from `--as` on the command line. `allowed()` is the only
  place that knows what a role may do; every writing path calls `require()`
  and the pages hide what the role may not use. A branch in review is frozen.
  Never add a write path without its `require()`.
- `tests/` — pytest on an in-memory DuckDB, and the command-line scenarios;
  both run in `make check` on every change, and **every behavioural fix has a
  unit test there first.** `tests/ui/` is the application test round: it
  drives every screen in a browser, audits each against a fixed usability
  checklist and axe-core, and writes the evidence to a gitignored folder. It
  runs on demand — before a demo or a release, or when asked — never as a
  gate on a change, and it ends with a triaged list for the Requester
  (decision 0010). The scenarios are the record and are committed; a run
  never is. `.claude/skills/application-test-round/` is the skill, invoked
  by name. `scripts/` — the two archreator validators, run before every push.

## Commands

```bash
make install     # uv sync (runtime and dev dependencies)
make seed        # create data/ea.duckdb, load the higher-education pack and the sample model
make run         # http://localhost:8050 (Dash debug server, no reloader)
make check       # ruff + pytest + the two validators — must be green before pushing
make test-fast   # the unit tests alone, in seconds, while iterating
make gui         # the application test round in a browser, on demand; writes .testrun/<stamp>/report.md and key-screens.html
uv run ea --help # the CLI: init, import, validate, find, get, set, neighbours, trace, impact, view, target, health, sql, summary, branch …, reviewers …; --branch and --as on any command
```

The DuckDB file is single-writer: stop the app before running the CLI on the
same file, or point `EA_DB_PATH` elsewhere.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, …).
- Documentation language: **English**. Australian spelling in prose is fine;
  identifiers and pack keys are ASCII `snake_case`.
- Element identifiers in `architecture/` follow archreator's prefixes
  (`STK`, `DRV`, `ASM`, `G`, `OUT`, `P`, `DOBJ`, `ASVC`, `ACMP`, `PLAT`,
  `GAP`); identifiers of enterprise content inside the repository follow the
  pack's prefixes (`LDC-…`, `DE-…`) and are not archreator identifiers.
- No model names or vendor identifiers in commit messages, code comments or
  documents; the agent provider is configured by environment variable.
- Nothing institution-specific anywhere, and nothing framework-specific in
  `src/`: a type name belongs in a pack, a column name in a mapping, an example
  in the sample data. **This repository is public: never name the organisation
  it was built for, its people, its tools or its internal systems.**
