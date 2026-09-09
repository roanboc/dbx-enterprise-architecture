---
name: application-test-round
description: Run one test round of this repository's application on demand — drive every screen in a browser and every command on the command line, audit each screen against a fixed usability checklist and the axe-core rule engine, and hand the Requester a report, a page of key screenshots and a triaged list of findings. Use when asked to test the app, to review the GUI or the UX, to produce a test report with screenshots, or before a demo or a release. Not a step of every change — a fix is its own scoped piece of work, with a unit test first.
---

# One application test round

A round proves what the application does today and says so in one document a reader can
review instead of clicking through eleven screens. **A round ends with the report and a
triaged list of findings.** It does not end with every finding fixed: what is fixed, and in
what order, is the Requester's choice, and each fix is its own piece of work.

The scenarios live in `tests/ui/` and are the durable record. A run is not — it is written
to `.testrun/<stamp>/` and never committed. `tests/ui/README.md` is the reference for the
harness, the checklist and where an assertion belongs; read it before writing a scenario.
Decision `architecture/decisions/0010` says why the round is shaped this way.

## Before anything: which side of the model a finding is on

`AGENTS.md` governs. A finding inside something the model already names — a screen, a
filter, a label, a control that does not work, a missing icon — is coded directly and
documents nothing. A finding that changes **what the model claims** — an element added,
removed or re-related, a rule in `architecture/` contradicted — is never coded directly:
align it through the layers, stop at Understanding for the Requester, write the scope
document, and only then write the code. Say which kind each finding is, in the report.

## 1 — Bootstrap

```bash
make gui-install     # the browser driver, its browser and axe-core; once per machine
make seed            # only if data/ea.duckdb is missing
```

The round seeds a database of its own under a temporary directory and starts the
application on a free port, so it never touches `data/ea.duckdb` and never needs a model
key. Stop `make run` first all the same: one writer per database file.

If `uv sync --frozen` complains, the lock is behind `pyproject.toml` — run `uv lock` and
commit `uv.lock` in the same commit.

## 2 — Run

```bash
make gui                                                          # the whole round, about forty minutes
.venv/bin/python -m pytest tests/ui/test_b_browse.py -m gui -q    # one group, while iterating
```

Use `.venv/bin/python` directly while iterating: `uv run` without `--group gui`
re-synchronises the environment and removes the driver.

The run writes `.testrun/<stamp>/report.md`, `key-screens.html` and the screenshots beside
them. Read the whole report before touching anything — fixing while it runs loses the
picture.

## 3 — Read

Three things, in this order:

- **`key-screens.html`** — every screen wide and at 480 px and each state the audit reaches,
  about forty images on one page. This is what a person reviews; the other screenshots are
  the machine's evidence and are folded away under it by group. Checkpoints 11 and 12
  (alignment and rhythm, terminology) are read here, by eye, and the judgement goes into
  the list of findings.
- **The Findings table** in `report.md`, with each finding's detail under it: what the
  checklist and axe-core raised, whether or not a scenario failed for it.
- **What failed.** A scenario that failed with a fix behind it is a stale assertion: the
  wording moved and the scenario pinned it. Repair the scenario, never widen the fix. One
  that failed with no fix behind it is a flake or a defect; a flake is a wait repaired in
  `tests/ui/harness.py`, never an expectation loosened.

The coverage checks in `tests/test_ui_coverage.py` run with the round and say which page,
command, role or download has no scenario. That is information for the triage, not a rule:
a browser scenario is the most expensive test there is, and whether one is wanted is a
decision.

## 4 — Triage, and stop

Order the findings by what a reader loses: a control that does not work, then a
permission that is wrong, then a message that misleads, then a screen that is merely
untidy. For each, name the file and the control, the scenario or checkpoint that caught
it, which side of the model it is on, and a rough size. Put the list to the Requester.

**The round is over here.** Do not start fixing because the list is long, and do not run
the round again to see whether it got shorter. A round is one run and one triage.

## 5 — A fix, when the Requester asks for one

Each fix is its own scoped piece of work, and it is finished in this order:

1. **A unit test first** — on the service, the importer, a callback function or the
   command line in-process (`tests/test_*.py`, seconds, runs on every change). Every
   behavioural fix has one; the browser is not where a behavioural assertion belongs.
2. **The code.** A new component id belongs in `src/ea/ui/ids.py`; a new icon in
   `assets/icons/` as a Tabler outline SVG, matching the ones already there.
3. **The scenario**, only where the round is the only thing that can see the fix — a
   layout, a control wired to the wrong property, a screen at 480 px. Turn the finding
   into a check: a finding lodged unconditionally is replaced by a `ui.check` that
   asserts the behaviour the fix gives. Run that group alone to prove it.
4. `make check` green; one Conventional Commit per concern (`fix(ui):`, `test:`,
   `test(ui):`); the finding's row in the report marked fixed.

The whole round runs again before the next demo or release, not after each fix.

## 6 — Commit and describe

Never commit `.testrun/`. Describe the pull request with
`/archreator:write-pr-description`, and put the round's numbers in its Verification
section — scenarios run, findings found, which the Requester chose to fix.

## Done when

- The report, the key screens and the triaged list have been handed to the Requester.
- Every scenario that failed is explained: a stale assertion repaired, a flake's wait
  repaired, or a defect on the list.
- `make check` is green.
