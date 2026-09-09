# 0010 — A browser-driven test round on demand, unit tests on every change, and an accessibility floor

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-09 — adopted by the agent, to be confirmed or overridden by the Requester. **Touches:** `ACMP6`, `ACMP7`.

## Context

The owner reported design, functional and usability defects while using the
web application, and a coding agent answered with a browser-driven test round:
417 scenarios that drive every screen and every command, read each screen
against a usability checklist, and write a report with screenshots. The round
found real defects the unit tests could not see — a metamodel save that wrote
only the filtered rows, a permission checked by a hidden button alone,
`javascript:` links accepted, controls that had never worked, and some thirty
contrast failures — and it fixed them.

It also cost more than it should. The round is larger than the application it
tests, runs for forty minutes, is not run by CI, and its scenarios pin exact
wording, so every fix moved several of them; the branch was pushed with six
scenarios red against the fixes it carried. The fixes themselves had no fast
test, so nothing guarded them on a pull request. A coverage check failed CI
whenever a page or command lacked a browser scenario, and the round's own
instructions defined "done" as every finding fixed and re-triggered the round
after any change to the interface, which is why it ran for ten hours and
would have kept running.

The two earlier interface reviews (scope documents 11 and 12) went through
the Requester's gate. This one did not, and the accessibility bar it applied
is nowhere stated in the model: no principle in `1_strategy` names it, so it
is adopted here as a call the Requester can confirm as a principle at the
next gate, or override.

## Decision

- **Every behavioural fix has a unit test**, on the service, the importer or
  the command line in-process, and those tests run on every change in the
  seconds `make check` takes. The command-line scenarios need no browser and
  run there too.
- **The browser round runs on demand** — before a demo or a release, or when
  the Requester asks — never as a gate on a pull request and never triggered
  by a change of its own accord. A round ends with a report and a triaged
  list of findings; what is fixed, and in what order, is the Requester's
  choice, and each fix is its own scoped piece of work with its unit test
  first.
- **The coverage of the round is audited, not enforced.** Whether a new page
  or command deserves a browser scenario is a decision taken when the round
  next runs, not a rule that blocks the pull request adding it.
- **The reviewable evidence is the screen audit**: every screen once wide and
  once at 480 px, and each state no plain address reaches — about forty
  images on one page beside the report. The rest of the screenshots are the
  machine's evidence.
- **The accessibility floor is WCAG 2.2 AA**, read two ways: the repository's
  own checklist for what is specific to this application, and the axe-core
  rule engine for the industry's list. A serious or critical violation fails
  the audit; the rest are findings.
- **The round is repository content, not policy**: its skill is invoked by
  name when a round is wanted, and the standing instruction names it as a
  tool rather than as a step in every change.

## Consequences

- `make check` grows by the command-line scenarios (about three minutes);
  `make test-fast` keeps the unit tests alone for iterating.
- A scenario that pins wording is expected to move when the wording does; a
  scenario that fails without a fix behind it is a stale assertion or a
  flake, and either is repaired in the scenario, never by widening the fix.
- The round's size is a cost to be reduced, not a coverage figure to be
  defended: a behavioural assertion that can be made against a service or a
  callback belongs there, and its browser scenario can go once it has.
- Two accessibility defects the round's own checklist did not read were fixed
  when axe-core first ran: the document declared no language, and eighty
  progress bars carried no name.

## Alternatives not taken

- **Run the round in CI:** forty minutes on every pull request, on a suite
  whose assertions move with the wording, would turn every change red for
  reasons unrelated to it.
- **Delete the round:** it found what nothing else did, and the harness is
  sound; the fault was the loop around it and the layer the assertions sat
  in, not the instrument.
- **A hosted visual-review service:** worth revisiting once the round runs
  regularly; for a proof of concept reviewed by one owner, a baseline of the
  audit's forty images and a diff against it is enough, and can be added
  without a third party.
