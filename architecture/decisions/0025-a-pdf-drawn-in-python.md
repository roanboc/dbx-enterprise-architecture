# 0025 — A deep dive's PDF is drawn in Python, with ReportLab

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-25 (initiative 25), the agent's call within the Requester's
*"a comprehensive PDF with nice style format and diagrams"*. **Touches:** `ACMP8`, `ART4`.

## Context

A deep dive is handed out as a styled PDF whose diagrams are the ones its draw.io files carry,
generated in the application from what is kept. The application runs on Databricks Apps, which
installs what `pyproject.toml` and `uv.lock` name and nothing else: no system package, no
browser, no font server. The PDF has to be drawn there exactly as it is drawn on a laptop, and
its diagrams have to come from the same layout the draw.io export computes, not from a second
drawing of the same view.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Render HTML to PDF with WeasyPrint | It needs cairo and pango installed on the machine, which Databricks Apps does not offer |
| Print the page from a headless browser | A browser in the app's runtime is hundreds of megabytes and a process to supervise, for one document |
| fpdf2 | Pure Python, but no charting and no drawing model to compose a diagram in; every chart would be hand-built |
| **ReportLab** | Chosen: installed from a wheel with nothing beside Python, it composes a document from styled paragraphs and tables and draws vector graphics and charts in the same model, so a diagram is drawn from the draw.io layout shape by shape |

## Decision

The PDF is composed with ReportLab: its page templates carry the style, its tables the
findings and the elements, its graphics the diagrams — drawn from the same boxes and lines the
draw.io files are written from — and its charts the figures of the overview.

## Consequences

One more runtime dependency, BSD-licensed, and Pillow with it. Icons are drawn from a small set
of shapes the application defines once and writes both into the PDF and into the draw.io files,
because ReportLab does not read SVG without a further library. The PDF uses ReportLab's standard
fonts, so it carries no font of its own and looks the same wherever it is made.
