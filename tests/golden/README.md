# Golden files

What an export of the sample model looks like, byte for byte, so a change to the layout or
to the file's mechanics is seen before it ships (decision 0024: a change to the layout is a
change to every golden file, on purpose).

## `drawio/`

Each file is `ea.views.drawio.to_drawio` over the sample model in `data/sample`, exported
with the timestamp fixed at `2026-01-01T00:00:00Z` and the page link base
`http://localhost:8050`, and compared by `tests/test_drawio_quality.py::test_golden_file`:

| File | View | Viewpoint | Marked |
| ---- | ---- | --------- | ------ |
| `layered.drawio` | `LDC-CURR` and its neighbourhood, depth 2 | `layered` | no |
| `application_cooperation.drawio` | the same | `application_cooperation` | no |
| `process_cooperation.drawio` | the same | `process_cooperation` | no |
| `staged_delivery.drawio` | the same | `staged_delivery` | no |
| `impact-layered.drawio` | the impact of `DE-SRS-COURSE`, depth 3 | `layered` | no |
| `layered-marked.drawio` | `LDC-CURR` and its neighbourhood, depth 2 | `layered` | yes: every shape and edge carries its target state |
| `layered-overview.drawio` | the same, at the **overview** level of detail | `layered` | no |
| `application_cooperation-overview.drawio` | the same, at the overview level | `application_cooperation` | no |

The viewpoints are the four the higher-education pack declares
(`packs/higher_education/metamodel.yaml`, section `viewpoints`).

## Regenerating

When the layout or the exporter changes on purpose, rewrite the files instead of comparing:

```bash
EA_UPDATE_GOLDEN=1 uv run pytest -q -p no:cacheprovider tests/test_drawio_quality.py
```

Then open one of the rewritten files in draw.io, look at the drawing rather than the diff of
coordinates, and commit the files with the change that moved them. A run without the
variable compares and fails on the first difference, naming the file.
