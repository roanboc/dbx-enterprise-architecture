# The application test round

A round drives the running application in a browser and on the command line, proves
every feature the repository claims, reads every screen against a fixed usability
checklist, and writes one document with the screenshots that evidence it.

**417 scenarios in sixteen groups**, and around forty minutes end to end.

```bash
make gui-install   # once: the browser driver and its browser
make seed          # once: data/ea.duckdb, if you have not already
make gui           # the round — writes .testrun/<stamp>/report.md
```

The round needs no model key and no running app: it seeds a database of its own, starts
the application on a free port with the stub agent provider, and stops it afterwards.
Nothing it does touches `data/ea.duckdb`.

## What is committed, and what is not

**The scenarios are the record**, and they are committed: `test_*.py` in this folder,
one module per group. Each scenario declares what it proves, and the run decides whether
it does.

**A run is not the record.** The report and its screenshots are written together into
`.testrun/<stamp>/`, which is gitignored, so the image links resolve where the report is
opened and no run is ever committed as a second version of the truth.

```
.testrun/2026-09-08-0930-round/
├── report.md          ← the document to review
├── screenshots/       ← one image per evidence point
├── downloads/         ← every file the application produced
└── server.log         ← what the application logged while it ran
```

`make check` is unaffected: the round is marked `gui` and `pytest` deselects it, so the
suite CI runs stays what it was.

## Groups

| | Group | Covers | Scenarios |
| - | ----- | ------ | --------- |
| A | Shell and navigation | The header, the four navigation groups, routing, the narrow viewport | 19 |
| B | Browse | Filters, ranked search, the grid, the New element modal, bulk edit | 29 |
| C | Element | Five tabs, editing, relationships, the graph, the generated view, history | 35 |
| D | Impact | Closure both ways, completeness, the graph and the view | 19 |
| E | Target state | Work packages, the current-by-target matrix, the marked view | 16 |
| F | Ask | The answer document, its views, the trace, grounding | 20 |
| G | Propose | Sources, analysis, pushback, the editable merge log, applying | 21 |
| H | Import | Validation, loading, the issue report, the template | 23 |
| I | Branches | Overlay, merge log, conflicts, review and the freeze | 26 |
| J | Metamodel | The type graph, the editable grids, notation, reviewers, export | 23 |
| K | Health | Freshness, completeness, and the links behind every figure | 18 |
| L | Roles and permissions | Four personas against every gated control | 32 |
| M | Command line | Every command, and the flags that change who and where | 64 |
| N | Downloads | Every file the application can produce | 25 |
| O | Negative paths | What is supposed to fail, failing well | 18 |
| P | Screen audit | Every screen against the usability checklist | 29 |

## The usability checklist

Group P applies the same list to every screen, so two rounds can be compared and a
regression in polish is as visible as a regression in behaviour.

| | Checkpoint | How it is judged |
| - | ---------- | ---------------- |
| 1 | **Navigation** — the current page is marked, the groups are stable, every link resolves | asserted |
| 2 | **Heading hierarchy** — one page title, no level skipped | asserted |
| 3 | **Labelling** — every control has a visible label or an accessible name | asserted |
| 4 | **Disabled with a reason** — nothing is disabled without saying why | asserted |
| 5 | **Empty states** — a screen with nothing to show says so, and says what to do | asserted |
| 6 | **Error states** — a refusal names what was refused and what to do instead | asserted |
| 7 | **Loading** — an action that takes time shows that it is taking time | asserted |
| 8 | **Contrast** — text meets the contrast floor against its background | asserted |
| 9 | **Focus** — tabbing reaches every control, the focused one is visible, and the header and navigation can be skipped in one press | asserted |
| 10 | **Narrow viewport** — the page is usable at 480 px with nothing clipped | asserted |
| 11 | **Alignment and rhythm** — tiles, cards and columns line up | read from the screenshot |
| 12 | **Terminology** — the same thing has the same name everywhere | read from the screenshot |

## Writing a scenario

```python
@pytest.mark.scenario(
    scenario_id="B04",
    group="B",
    title="Bulk edit sets a target state on the ticked rows",
    feature="Browse · bulk edit",
    expected="Ticking two rows and choosing a target state updates both and says so.",
    role="architect",
    branch="cms-upgrade",
)
def test_bulk_edit(ui, record):
    ui.goto("/browse")
    ui.grid_tick("browse-grid", [0, 1])
    ui.click("bulk-open")
    ui.select("bulk-target", "change")
    ui.click("bulk-save")
    ui.check("both rows were updated", "Updated 2" in ui.text("bulk-feedback"))
    ui.shot("Bulk edit reports what it changed")
```

`ui.check` records an assertion and carries on, so one run reports everything that is
wrong rather than the first thing. `ui.must` stops the scenario when the rest of it
depends on what failed. `ui.shot` waits for the page to settle before it photographs it.

A component id is written bare — `"bulk-save"` means `#bulk-save`; anything else is a
CSS selector.

| What you need | Method |
| ------------- | ------ |
| Open a page | `ui.goto("/browse")` |
| A Mantine select | `ui.select("browse-type", "Data Entity")` |
| A segmented control | `ui.segmented("br-status", "Merged")` |
| A switch | `ui.toggle("tg-only-changes", True)` |
| A grid | `ui.grid_row_count`, `ui.grid_cell`, `ui.grid_tick`, `ui.grid_set`, `ui.grid_click_cell` |
| A generated view | `ui.wait_mermaid()` |
| A network graph | `ui.wait_graph()` |
| A file the app produces | `ui.download("el-view-md", ".md")` |
| Another role | `ui.persona("Architect")` |
| Another branch | `ui.branch("CMS upgrade")` |
| A narrow screen | `ui.narrow()` … `ui.wide()` |

A finding that is worth reporting but should not fail a scenario is lodged with the
`finding` fixture, and reaches the report's Findings table.
