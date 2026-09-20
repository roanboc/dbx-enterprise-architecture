"""Import: upload CSV files, validate against the metamodel, load."""

from __future__ import annotations

import base64
import csv
import fnmatch
import io
import zipfile
from pathlib import Path
from typing import Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.config import ROOT
from ea.importer import Mapping, export_archive, import_frames, load_mapping, mapping_from_text
from ea.importer.csv_import import CsvShapeError, read_csv_text
from ea.models import Forbidden, Issue
from ea.services.roles import a_role
from ea.ui import ids
from ea.ui.components import alert, icon, issues_table, page_title
from ea.ui.context import AppContext, get_context

ISSUE_LIMIT = 500  # a page cannot usefully show more, and says so when it holds back

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


def _why_not(ctx: AppContext) -> str:
    """Why Load is off, in the reader's own terms, or empty when it is not.

    Telling a Reader to switch to a branch is advice that will never enable the button for
    them: importing is an Architect's or an Admin's action, and the page has to say which.
    """
    if not ctx.can("import"):
        return f"{a_role(ctx.role_label())} may not load an import; an architect or an admin can."
    if ctx.frozen_reason():
        return ctx.frozen_reason()
    return ""


def render(ctx: AppContext) -> html.Div:
    on_branch = ctx.on_branch()
    why_not = _why_not(ctx)
    return html.Div(
        [
            page_title(
                "Import",
                "Drop CSV files that follow the contract in connectors/README.md (elements, relationships, links), validate them against the metamodel, then load. Re-importing updates rather than duplicates.",
            ),
            alert(
                f"You are on branch {ctx.branch()}: what you load lands on the branch and reaches main when it is merged."
                if on_branch
                else "You are on main: switch to a branch in the header first. Import never writes to main directly, so review happens before anything is merged.",
                "orange" if on_branch else "blue",
            ),
            alert(why_not, "blue", dismissible=False) if why_not else None,
            dmc.SimpleGrid(
                [
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dmc.Text("1 · Set up the import", fw=700, size="sm"),
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
                                    comboboxProps={"withinPortal": False},
                                ),
                                # The command line takes any mapping YAML by path. Without this
                                # the screen could only ever use the two that ship, so a reader
                                # with their own source had to leave the app to use it.
                                dcc.Upload(
                                    id=ids.IM_MAP_UPLOAD,
                                    multiple=False,
                                    accept=".yaml,.yml",
                                    children=dmc.Text(
                                        "…or upload your own mapping YAML", size="xs", td="underline"
                                    ),
                                    style={"cursor": "pointer"},
                                ),
                                html.Div(id=ids.IM_MAP_NAME),
                                dcc.Store(id=ids.IM_MAP_STORE, data=""),
                                dmc.Divider(),
                                dmc.Button(
                                    "Download template",
                                    id=ids.IM_TEMPLATE,
                                    variant="light",
                                    leftSection=icon("tabler:download"),
                                ),
                                dmc.Button(
                                    "Download current content",
                                    id=ids.IM_EXPORT,
                                    variant="light",
                                    leftSection=icon("tabler:database-export"),
                                ),
                                dmc.Text(
                                    "The template ZIP is the empty contract; the content ZIP is this "
                                    "organisation and branch written out in the same three files. Edit "
                                    "either in a spreadsheet and drop it back here — an export re-imports "
                                    "onto the same elements and edges rather than beside them. From the "
                                    "command line: `uv run ea export <dir>` and `uv run ea import <dir>`.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                            gap="sm",
                        ),
                        p="md",
                        withBorder=True,
                    ),
                    dmc.Paper(
                        dmc.Stack(
                            [
                                dmc.Text("2 · Add the files", fw=700, size="sm"),
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
                                dmc.Divider(),
                                dmc.Group(
                                    [
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
                                            disabled=bool(why_not) or not (ctx.can("import") and on_branch),
                                        ),
                                    ]
                                ),
                                dmc.Text(
                                    "Load is disabled on main: switch to a branch to load."
                                    if not on_branch
                                    else "Validate checks the files against the metamodel without writing anything; Load applies them to the branch.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                            gap="sm",
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


def _text(raw: str, encoding: str = "utf-8-sig") -> str:
    """One uploaded file's bytes as text, in the encoding the mapping names.

    The bytes are kept as they arrived and decoded here rather than at upload, because which
    encoding is right is the mapping's answer and the mapping is chosen after the drop. The
    command line has always honoured it; decoding early is what made the two doors disagree.
    """
    try:
        return base64.b64decode(raw).decode(encoding, errors="replace")
    except (ValueError, LookupError):
        return base64.b64decode(raw).decode("utf-8-sig", errors="replace")


def _frames(store: dict, mapping: Mapping):
    frames = {"elements": [], "relationships": [], "links": []}
    unclassified: list[str] = []
    malformed: list[CsvShapeError] = []
    for name, raw in (store or {}).items():
        kind = _classify(name, mapping)
        if kind is None:
            unclassified.append(name)
            continue
        try:
            frames[kind].append((name, read_csv_text(_text(raw, mapping.encoding), name, mapping.delimiter)))
        except CsvShapeError as exc:
            malformed.append(exc)
    return frames, unclassified, malformed


def _row_count(raw: str) -> int:
    """How many records a file holds, which is not how many lines it has.

    A quoted field may run over several lines — a description pasted from a document
    routinely does — and counting lines then says the file holds rows it does not, before
    the reader has pressed anything.
    """
    text = _text(raw)
    try:
        return max(0, sum(1 for _ in csv.reader(io.StringIO(text))) - 1)
    except csv.Error:
        return max(0, len(text.splitlines()) - 1)


def _file_list(store: dict) -> Any:
    """What has been uploaded so far, each with the way to take it back off."""
    if not store:
        return dmc.Text("No files yet.", size="xs", c="dimmed")
    return dmc.Stack(
        [
            dmc.Group(
                [
                    icon("tabler:file-type-csv"),
                    dmc.Text(name, size="sm"),
                    dmc.Text(_rows_label(_row_count(raw)), size="xs", c="dimmed"),
                    dmc.ActionIcon(
                        icon("tabler:trash", 14),
                        id={"type": ids.IM_DROP, "name": name},
                        variant="subtle",
                        color="red",
                        size="sm",
                        **{"aria-label": f"Remove {name}"},
                    ),
                ],
                gap="xs",
            )
            for name, raw in store.items()
        ],
        gap=4,
    )


def _rows_label(n: int) -> str:
    return f"{n} row" if n == 1 else f"{n} rows"


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


def _run(store, source, mapping_key, dry_run: bool, map_yaml: str = ""):
    ctx = get_context()
    if not store:
        return alert("Upload at least one CSV file first.", "yellow")
    if map_yaml:
        # An uploaded mapping wins over the dropdown: it is the more specific thing the
        # reader did, and leaving the dropdown to override it would be a silent no-op.
        try:
            mapping = mapping_from_text(map_yaml)
        except Exception as exc:  # noqa: BLE001 — any YAML fault is the reader's to see
            return alert(f"That mapping YAML could not be read: {exc}", "red")
    elif mapping_key:
        mapping = load_mapping(ROOT / "connectors" / mapping_key / "mapping.yaml")
    else:
        mapping = Mapping()
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
    for bad in malformed:
        # The command line counts a file it could not read as an error of the import
        # (`ragged_row`); the two counts have to agree, or the page reads '0 errors' over a
        # file that went unread.
        report.add_issue(
            Issue(
                level="error",
                code="ragged_row",
                message=f"a row does not match the header this file declares: {bad.detail}",
                file=bad.filename,
            )
        )
    if not dry_run:
        ctx.graph.invalidate()
    color = "green" if report.ok and not malformed else "red"
    wrote = report.elements_loaded + report.relationships_loaded + report.links_loaded
    if dry_run:
        lead = "Validation only — nothing written. "
    elif wrote:
        lead = "Loaded. "
    else:
        lead = "Nothing was loaded. "
    head = lead + report.summary()
    # The report counts every issue it found and keeps only the first few thousand, so the
    # totals a reader compares with the command line come from the counts, not the kept list.
    found = sum(report.counts.values())
    by_code = ", ".join(f"{code} {n}" for code, n in sorted(report.counts.items(), key=lambda kv: -kv[1])[:6])
    if malformed:
        # A file that could not be read is an error, and the count a reader compares with
        # the command line has to say so.
        head += f"; {len(malformed)} file(s) refused"
    return html.Div(
        [
            alert(head, "red" if malformed else color),
            _malformed_alert(malformed),
            alert("Ignored (no pattern matched): " + ", ".join(unclassified), "yellow")
            if unclassified
            else None,
            dmc.Title(f"Issues ({found})", order=2, size="h5", my="sm"),
            issues_table(report.issues[:ISSUE_LIMIT]),
            dmc.Text(
                f"Showing the first {min(ISSUE_LIMIT, len(report.issues))} of {found}"
                + (f", of which the report kept {len(report.issues)}" if report.truncated else "")
                + ". Fix these and run it again to see the rest."
                + (f" By code: {by_code}." if by_code else ""),
                size="xs",
                c="dimmed",
            )
            if found > ISSUE_LIMIT
            else None,
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
            store[name] = b64  # decoded when the mapping says in what encoding
        return store, _file_list(store)

    @app.callback(
        Output(ids.IM_STORE, "data", allow_duplicate=True),
        Output(ids.IM_FILES, "children", allow_duplicate=True),
        Input({"type": ids.IM_DROP, "name": dash.ALL}, "n_clicks"),
        State(ids.IM_STORE, "data"),
        prevent_initial_call=True,
    )
    def drop_file(clicks, store):
        """Take one file back off the list. Uploading the wrong file was the commonest way
        to end up reloading the page, because there was no way to undo it."""
        trigger = dash.ctx.triggered_id
        if not isinstance(trigger, dict) or not any(clicks or []):
            return no_update, no_update
        store = dict(store or {})
        store.pop(trigger.get("name"), None)
        return store, _file_list(store)

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.IM_EXPORT, "n_clicks"),
        prevent_initial_call=True,
        running=[(Output(ids.IM_EXPORT, "loading"), True, False)],
    )
    def export_content(n):
        """This organisation and branch as the three contract files, ready to re-import."""
        if not n:
            return no_update
        ctx = get_context()
        name = f"ea-content-{ctx.branch()}.zip"
        return dcc.send_bytes(export_archive(ctx.backend, ctx.registry), name, type="application/zip")

    @app.callback(
        Output(ids.IM_MAP_STORE, "data"),
        Output(ids.IM_MAP_NAME, "children"),
        Input(ids.IM_MAP_UPLOAD, "contents"),
        State(ids.IM_MAP_UPLOAD, "filename"),
        prevent_initial_call=True,
    )
    def mapping_upload(content, name):
        """Keep the uploaded mapping, and say on the page which one is in force."""
        if not content:
            return no_update, no_update
        text = base64.b64decode(content.split(",", 1)[1]).decode("utf-8", errors="replace")
        try:
            mapping_from_text(text)
        except Exception as exc:  # noqa: BLE001 — any YAML fault is the reader's to see
            return "", alert(f"{name} could not be read: {exc}", "red")
        return text, dmc.Text(f"Using {name} — this overrides the choice above.", size="xs", c="dimmed")

    @app.callback(
        Output(ids.IM_REPORT, "children"),
        Input(ids.IM_VALIDATE, "n_clicks"),
        State(ids.IM_STORE, "data"),
        State(ids.IM_SOURCE, "value"),
        State(ids.IM_MAPPING, "value"),
        State(ids.IM_MAP_STORE, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.IM_VALIDATE, "loading"), True, False)],
    )
    def validate(n, store, source, mapping_key, map_yaml):
        return _run(store, source, mapping_key, True, map_yaml) if n else no_update

    @app.callback(
        Output(ids.IM_REPORT, "children", allow_duplicate=True),
        Input(ids.IM_LOAD, "n_clicks"),
        State(ids.IM_STORE, "data"),
        State(ids.IM_SOURCE, "value"),
        State(ids.IM_MAPPING, "value"),
        State(ids.IM_MAP_STORE, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.IM_LOAD, "loading"), True, False)],
    )
    def load(n, store, source, mapping_key, map_yaml):
        return _run(store, source, mapping_key, False, map_yaml) if n else no_update


_ = Path
