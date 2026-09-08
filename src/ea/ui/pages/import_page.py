"""Import: upload CSV files, validate against the metamodel, load."""

from __future__ import annotations

import base64
import csv
import fnmatch
import io
import zipfile
from pathlib import Path

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.config import ROOT
from ea.importer import Mapping, import_frames, load_mapping
from ea.importer.csv_import import CsvShapeError, read_csv_text
from ea.models import Forbidden
from ea.ui import ids
from ea.ui.components import alert, icon, issues_table, page_title
from ea.ui.context import AppContext, get_context

MAPPINGS = {
    "": "No mapping (CSV contract)",
    "tool-export": "EA tool export, one CSV per type (connectors/tool-export/mapping.yaml)",
}
TEMPLATE_DIR = ROOT / "templates" / "import-template"
TEMPLATE_FILES = ("README.md", "elements.csv", "relationships.csv", "links.csv")


def import_template_archive() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in TEMPLATE_FILES:
            archive.write(TEMPLATE_DIR / name, arcname=name)
    return out.getvalue()


def render(ctx: AppContext) -> html.Div:
    return html.Div(
        [
            page_title(
                "Import",
                "Drop CSV files that follow the contract in connectors/README.md (elements, relationships, links), validate them against the metamodel, then load. Re-importing updates rather than duplicates.",
            ),
            alert(
                f"You are on branch {ctx.branch()}: what you load lands on the branch and reaches main when it is merged."
                if ctx.on_branch()
                else "You are on main: what you load changes the model directly. Switch to a branch in the header to stage an import for review.",
                "orange" if ctx.on_branch() else "blue",
            ),
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dcc.Upload(
                                    id=ids.IM_UPLOAD,
                                    multiple=True,
                                    children=dmc.Stack(
                                        [
                                            icon("tabler:cloud-upload", 32),
                                            dmc.Text("Drop CSV files here or click to choose", size="sm"),
                                        ],
                                        align="center",
                                        gap=4,
                                        py="lg",
                                    ),
                                    style={
                                        "border": "1px dashed #adb5bd",
                                        "borderRadius": 8,
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Div(id=ids.IM_FILES),
                                dcc.Store(id=ids.IM_STORE, data={}),
                            ]
                        ),
                        p="md",
                        withBorder=True,
                    ),
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dmc.TextInput(
                                    id=ids.IM_SOURCE,
                                    label="Source system",
                                    value="tool-export",
                                    description="Recorded on every imported row; the same source re-imported updates in place.",
                                ),
                                dmc.Select(
                                    id=ids.IM_MAPPING,
                                    label="Mapping",
                                    data=[{"value": k, "label": v} for k, v in MAPPINGS.items()],
                                    value="",
                                ),
                                dmc.Group(
                                    [
                                        dmc.Button(
                                            "Download template",
                                            id=ids.IM_TEMPLATE,
                                            variant="light",
                                            leftSection=icon("tabler:download"),
                                        ),
                                        dmc.Button(
                                            "Validate only",
                                            id=ids.IM_VALIDATE,
                                            variant="light",
                                            leftSection=icon("tabler:checklist"),
                                        ),
                                        dmc.Button(
                                            "Load",
                                            id=ids.IM_LOAD,
                                            leftSection=icon("tabler:database-import"),
                                            disabled=not (
                                                ctx.can("import")
                                                and (ctx.on_branch() or ctx.can("edit_main"))
                                            ),
                                        ),
                                    ]
                                ),
                                dmc.Text(
                                    "The template ZIP follows the no-mapping CSV contract in connectors/README.md. Or from the command line: `uv run ea import <dir> --source ea-tool --mapping connectors/tool-export/mapping.yaml`.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ]
                        ),
                        p="md",
                        withBorder=True,
                    ),
                ],
                cols={"base": 1, "md": 2},
                spacing="md",
                mb="md",
            ),
            html.Div(id=ids.IM_REPORT),
        ]
    )


def _classify(name: str, mapping: Mapping) -> str | None:
    low = name.lower()
    for kind, patterns in (
        ("relationships", mapping.relationship_files),
        ("links", mapping.link_files),
        ("elements", mapping.element_files),
    ):
        if any(fnmatch.fnmatch(low, p.lower()) for p in patterns):
            return kind
    return None


def _frames(store: dict, mapping: Mapping):
    frames = {"elements": [], "relationships": [], "links": []}
    unclassified: list[str] = []
    malformed: list[CsvShapeError] = []
    for name, text in (store or {}).items():
        kind = _classify(name, mapping)
        if kind is None:
            unclassified.append(name)
            continue
        try:
            frames[kind].append((name, read_csv_text(text, name)))
        except CsvShapeError as exc:
            malformed.append(exc)
    return frames, unclassified, malformed


def _row_count(text: str) -> int:
    """How many records a file holds, which is not how many lines it has.

    A quoted field may run over several lines — a description pasted from a document
    routinely does — and counting lines then says the file holds rows it does not, before
    the reader has pressed anything.
    """
    try:
        return max(0, sum(1 for _ in csv.reader(io.StringIO(text))) - 1)
    except csv.Error:
        return max(0, len(text.splitlines()) - 1)


def _malformed_alert(malformed: list[CsvShapeError]):
    """A file whose rows do not match its own header is named, and nothing of it is read."""
    if not malformed:
        return None
    return alert(
        "Not read — a row does not match the header the file declares, and reading it anyway "
        "would load rows under identifiers the file never named: "
        + "; ".join(f"{e.filename} ({e.detail})" for e in malformed),
        "red",
    )


def _run(store, source, mapping_key, dry_run: bool):
    ctx = get_context()
    if not store:
        return alert("Upload at least one CSV file first.", "yellow")
    mapping = load_mapping(ROOT / "connectors" / mapping_key / "mapping.yaml") if mapping_key else Mapping()
    frames, unclassified, malformed = _frames(store, mapping)
    if not any(frames.values()) and not malformed:
        return alert(
            "None of the files matched the element/relationship/link file patterns of the mapping.", "red"
        )
    if not any(frames.values()):
        return html.Div([_malformed_alert(malformed)])
    try:
        report = import_frames(
            ctx.backend,
            ctx.registry,
            frames,
            source or mapping.source_system or "import",
            mapping,
            ctx.actor,
            dry_run,
        )
    except Forbidden as exc:
        return alert(str(exc), "red")
    if not dry_run:
        ctx.graph.invalidate()
    color = "green" if report.ok else "red"
    wrote = report.elements_loaded + report.relationships_loaded + report.links_loaded
    if dry_run:
        lead = "Validation only — nothing written. "
    elif wrote:
        lead = "Loaded. "
    else:
        lead = "Nothing was loaded. "
    head = lead + report.summary()
    return html.Div(
        [
            alert(head, "red" if malformed else color),
            _malformed_alert(malformed),
            alert("Ignored (no pattern matched): " + ", ".join(unclassified), "yellow")
            if unclassified
            else None,
            dmc.Title(f"Issues ({len(report.issues)})", order=2, size="h5", my="sm"),
            issues_table(report.issues[:500]),
        ]
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.IM_TEMPLATE, "n_clicks"),
        prevent_initial_call=True,
    )
    def template(n):
        if not n:
            return no_update
        return dcc.send_bytes(import_template_archive(), "ea-import-template.zip", type="application/zip")

    @app.callback(
        Output(ids.IM_STORE, "data"),
        Output(ids.IM_FILES, "children"),
        Input(ids.IM_UPLOAD, "contents"),
        State(ids.IM_UPLOAD, "filename"),
        State(ids.IM_STORE, "data"),
        prevent_initial_call=True,
    )
    def upload(contents, names, store):
        if not contents:
            return no_update, no_update
        store = dict(store or {})
        for content, name in zip(contents, names, strict=True):
            _, b64 = content.split(",", 1)
            store[name] = base64.b64decode(b64).decode("utf-8-sig", errors="replace")
        rows = [
            dmc.Group(
                [
                    icon("tabler:file-type-csv"),
                    dmc.Text(n, size="sm"),
                    dmc.Text(f"{_row_count(t)} rows", size="xs", c="dimmed"),
                ],
                gap="xs",
            )
            for n, t in store.items()
        ]
        return store, dmc.Stack(rows, gap=4)

    @app.callback(
        Output(ids.IM_REPORT, "children"),
        Input(ids.IM_VALIDATE, "n_clicks"),
        State(ids.IM_STORE, "data"),
        State(ids.IM_SOURCE, "value"),
        State(ids.IM_MAPPING, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.IM_VALIDATE, "loading"), True, False)],
    )
    def validate(n, store, source, mapping_key):
        return _run(store, source, mapping_key, True) if n else no_update

    @app.callback(
        Output(ids.IM_REPORT, "children", allow_duplicate=True),
        Input(ids.IM_LOAD, "n_clicks"),
        State(ids.IM_STORE, "data"),
        State(ids.IM_SOURCE, "value"),
        State(ids.IM_MAPPING, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.IM_LOAD, "loading"), True, False)],
    )
    def load(n, store, source, mapping_key):
        return _run(store, source, mapping_key, False) if n else no_update


_ = Path
