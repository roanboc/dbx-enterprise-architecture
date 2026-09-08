---
name: application-test-round
description: Run a full test and improvement round of this repository's application — drive every screen in a browser and every command on the command line, audit each screen for consistency and usability, produce the evidence report, then triage and fix what it found and run it again. Use when asked to test the app, to check everything still works, to review the GUI or the UX, to produce a test report with screenshots, or after a change to src/ea/ui/, assets/ or the CLI.
---

# A full application test round

A round proves the application does what this repository says it does, and says so in one
document a reader can review instead of clicking through eleven screens. It is not a test
run: it ends with the defects fixed and the report green.

The scenarios live in `tests/ui/` and are the durable record. A run is not — it is written
to `.testrun/<stamp>/` and never committed. `tests/ui/README.md` is the reference for the
harness and the usability checklist; read it before writing a scenario.

## Before anything: which side of the model a fix is on

`AGENTS.md` governs. A fix inside something the model already names — a screen, a filter,
a label, a control that does not work, a missing icon — is coded directly and documents
nothing. A fix that changes **what the model claims** — an element added, removed or
re-related, a rule in `architecture/` contradicted — is never coded directly: align it
through the layers, stop at Understanding for the Requester, write the scope document,
and only then write the code.

Most of what a round finds is the first kind. Decide per finding, not per round, and say
which in the report. When it is the second kind, stop and hand off rather than widening
the round.

## 1 — Bootstrap

```bash
make gui-install     # the browser driver and its browser; once per machine
make seed            # only if data/ea.duckdb is missing
```

The round seeds a database of its own under a temporary directory and starts the
application on a free port, so it never touches `data/ea.duckdb` and never needs a model
key. Stop `make run` first all the same: one writer per database file.

If `uv sync --frozen` complains, the lock is behind `pyproject.toml` — run `uv lock` and
commit `uv.lock` in the same commit.

## 2 — Run

```bash
make gui                                   # the whole round
.venv/bin/python -m pytest tests/ui/test_b_browse.py -m gui -q    # one group, while iterating
```

Use `.venv/bin/python` directly while iterating: `uv run` without `--group gui`
re-synchronises the environment and removes the driver.

The run writes `.testrun/<stamp>/report.md` with its screenshots beside it. A first pass
on a change of any size is expected to be red. Read the whole report before touching
anything — fixing while it runs loses the picture.

## 3 — Audit

The report's Findings table is what the round noticed; the screenshots are what it saw.
Work both:

- Read each screen's two screenshots — wide and narrow — against the checklist in
  `tests/ui/README.md`. Checkpoints 1 to 10 are asserted; 11 and 12 (alignment and
  rhythm, terminology) are yours to judge, and the judgement goes into the report.
- Read the coverage tables. A route, control, role, download or command with no scenario
  is itself a finding: the scenario is missing, and writing it comes before fixing
  anything else.

`.venv/bin/python -m pytest tests/test_ui_coverage.py -q` says whether every page,
command, role and download is exercised. It needs no browser and runs in CI.

## 4 — Triage

Order by what a reader loses: a control that does not work, then a permission that is
wrong, then a message that misleads, then a screen that is merely untidy. For each
finding name the file and the control, the scenario that caught it, and which side of
the model it is on.

Larger visual rework is in scope for a round, but size it and say so before starting it —
it is the part that grows without noticing.

## 5 — Fix

- Code the fix. A new component id belongs in `src/ea/ui/ids.py`; a new icon in
  `assets/icons/` as a Tabler outline SVG, matching the ones already there.
- **A fix without a scenario that would have caught it is not finished.** Extend
  `tests/ui/` in the same commit.
- `make check` after each fix, before the next.

## 6 — Run it again

`make gui` on a clean tree. Compare the summary against the previous run. A scenario that
changed outcome without a fix behind it is flake: repair the wait in `tests/ui/harness.py`,
never the expectation. The usual cause is a screen that finishes drawing after its
callback returns — a generated view or a graph — so wait for what is drawn, not for the
network to fall quiet.

## 7 — Report

The report the Requester reads is the last run's, green, with every finding listed and
its status. Keep the last few run folders and delete the rest; nothing under `.testrun/`
is ever committed.

## 8 — Commit

Conventional Commits, one concern each: `test(ui):` for scenarios, `fix(ui):` per defect,
`docs:` for the documentation. Never commit `.testrun/`. Describe the pull request with
`/archreator:write-pr-description`, and put the round's numbers in its Verification
section — scenarios run, findings found, findings fixed.

## Done when

- Every group in `tests/ui/README.md` has scenarios and they all pass.
- `tests/test_ui_coverage.py` passes: no page, command, role or download is unexercised.
- Every finding is fixed, or listed with a reason it was not and what it would take.
- Every fix has a scenario that would have caught it.
- `make check` is green, and the report of the final run is in `.testrun/`.
