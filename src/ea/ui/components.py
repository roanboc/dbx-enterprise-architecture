"""Small presentational helpers shared by the pages."""

from __future__ import annotations

import base64
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import dash_mantine_components as dmc
from dash import ALL, MATCH, Input, Output, State, dcc, html, no_update
from dash import ctx as dash_ctx

from ea.metamodel.registry import Registry
from ea.models import Element, Issue
from ea.ui import ids

# Colours come from the pack (a domain's `notation.colour` and `notation.hex`); these are the fallbacks.
FALLBACK_COLOUR, FALLBACK_HEX = "gray", "#adb5bd"
STATUS_COLORS = {"draft": "orange", "approved": "green", "retired": "red"}
LEVEL_COLORS = {"error": "red", "warning": "yellow", "info": "blue"}


ICON_DIR = Path(__file__).resolve().parents[3] / "assets" / "icons"


@cache
def _icon_data_uri(name: str) -> str | None:
    """Tabler outline icon (MIT) shipped with the app, so no request ever leaves the browser for an icon."""
    path = ICON_DIR / f"{name.split(':', 1)[-1]}.svg"
    if not path.is_file():
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def icon(name: str, size: int = 16, **kwargs: Any) -> html.Span:
    """An inline icon that takes the text colour of its parent (CSS mask over the SVG)."""
    uri = _icon_data_uri(name)
    style = {
        "display": "inline-block",
        "width": f"{size}px",
        "height": f"{size}px",
        "verticalAlign": "middle",
    }
    if uri:
        style.update(
            {
                "backgroundColor": "currentColor",
                "WebkitMaskImage": f"url({uri})",
                "maskImage": f"url({uri})",
                "WebkitMaskSize": "contain",
                "maskSize": "contain",
                "WebkitMaskRepeat": "no-repeat",
                "maskRepeat": "no-repeat",
            }
        )
    style.update(kwargs.pop("style", {}) or {})
    return html.Span(style=style, className="ea-icon", **kwargs)


def element_href(element_id: str) -> str:
    return f"/element/{element_id}"


def domain_colour(registry: Registry, domain_id: str) -> str:
    """The palette name a domain declares in its notation, for badges and legends."""
    d = next((d for d in registry.pack.domains if d.id == domain_id), None)
    return (d.notation.get("colour") if d else None) or FALLBACK_COLOUR


def domain_hex(registry: Registry, domain_id: str) -> str:
    """The fill colour a domain declares in its notation, for graphs."""
    d = next((d for d in registry.pack.domains if d.id == domain_id), None)
    return (d.notation.get("hex") if d else None) or FALLBACK_HEX


def darken(hex_colour: str, amount: float = 0.3) -> str:
    """A darker shade of a hex colour, for borders."""
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        return "#495057"
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    f = 1 - amount
    return f"#{int(r * f):02x}{int(g * f):02x}{int(b * f):02x}"


def type_color(registry: Registry, type_id: str) -> str:
    t = registry.get_type(type_id)
    return domain_colour(registry, t.domain if t else "")


def type_badge(registry: Registry, type_id: str, size: str = "sm") -> dmc.Badge:
    t = registry.get_type(type_id)
    return dmc.Badge(
        t.name if t else type_id, color=type_color(registry, type_id), variant="light", size=size
    )


def status_badge(status: str, size: str = "sm") -> dmc.Badge:
    return dmc.Badge(status, color=STATUS_COLORS.get(status, "gray"), variant="outline", size=size)


def element_anchor(e: Element | dict[str, Any]) -> dmc.Anchor:
    eid = e.element_id if isinstance(e, Element) else e["element_id"]
    name = e.name if isinstance(e, Element) else e["name"]
    return dmc.Anchor(name, href=element_href(eid), size="sm", fw=500)


MERMAID_FENCE = re.compile(r"```mermaid\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
MARKDOWN_SNIPPETS = {
    "heading": "## Heading",
    "bold": "**bold text**",
    "table": "| Column | Value |\n| ------ | ----- |\n| Example | Replace me |",
    "mermaid": "```mermaid\nflowchart LR\n  a[Start] --> b[Next]\n```",
}


def markdown(text: str, block_id: str = "markdown") -> html.Div:
    source = text or "_No description._"
    parts: list[Any] = []
    start = 0
    for i, match in enumerate(MERMAID_FENCE.finditer(source)):
        before = source[start : match.start()].strip()
        if before:
            parts.append(dcc.Markdown(before, link_target="_blank", className="ea-doc"))
        code = match.group(1).strip()
        if code:
            parts.append(mermaid_block(f"{block_id}-mermaid-{i}", code, arrangeable=False))
        start = match.end()
    after = source[start:].strip()
    if after:
        parts.append(dcc.Markdown(after, link_target="_blank", className="ea-doc"))
    if not parts:
        parts.append(dcc.Markdown("_No description._", link_target="_blank", className="ea-doc"))
    return html.Div(parts, className="ea-markdown")


def markdown_editor(
    editor_id: str,
    label: str,
    value: str = "",
    placeholder: str = "",
    min_rows: int = 6,
) -> html.Div:
    buttons = [("heading", "Heading"), ("bold", "Bold"), ("table", "Table"), ("mermaid", "Mermaid")]
    return html.Div(
        [
            dmc.Group(
                [
                    dmc.Text(label, size="sm", fw=500),
                    dmc.Group(
                        [
                            dmc.Button(
                                label_text,
                                id={"type": ids.MD_INSERT, "id": editor_id, "kind": kind},
                                variant="light",
                                color="gray",
                                size="compact-xs",
                            )
                            for kind, label_text in buttons
                        ]
                        + [
                            dmc.SegmentedControl(
                                id={"type": ids.MD_MODE, "id": editor_id},
                                data=[
                                    {"value": "edit", "label": "Edit"},
                                    {"value": "split", "label": "Split"},
                                    {"value": "preview", "label": "Preview"},
                                ],
                                value="edit",
                                size="xs",
                            ),
                        ],
                        gap=6,
                        className="ea-markdown-toolbar",
                    ),
                ],
                justify="space-between",
                align="center",
                mb=4,
                className="ea-markdown-header",
            ),
            html.Div(
                [
                    html.Div(
                        dmc.Textarea(
                            id={"type": ids.MD_TEXT, "id": editor_id},
                            value=value,
                            placeholder=placeholder,
                            # A placeholder is a hint, and it goes the moment anything is
                            # typed. The name has to outlast it.
                            **{"aria-label": label or "Markdown"},
                            resize="vertical",
                            styles={"input": {"minHeight": f"{min_rows * 24}px"}},
                        ),
                        className="ea-md-edit-pane",
                    ),
                    html.Div(
                        dmc.Paper(
                            [
                                dmc.Text("Preview", size="xs", fw=700, c="dimmed", mb=4),
                                html.Div(
                                    markdown(value, f"md-preview-{editor_id}"),
                                    id={"type": ids.MD_PREVIEW, "id": editor_id},
                                ),
                            ],
                            p="sm",
                            withBorder=True,
                            className="ea-markdown-preview",
                        ),
                        className="ea-md-preview-pane",
                    ),
                ],
                className="ea-md-body",
            ),
        ],
        id={"type": ids.MD_WRAP, "id": editor_id},
        className="ea-markdown-editor mode-edit",
    )


def modal_title(title: str, modal_key: str) -> dmc.Group:
    """A modal title with a full-screen toggle, so a small window can take the whole screen."""
    return dmc.Group(
        [
            dmc.Text(title, fw=600),
            dmc.Tooltip(
                dmc.ActionIcon(
                    icon("tabler:maximize", 14),
                    variant="subtle",
                    color="gray",
                    size="sm",
                    className="ea-modal-full",
                    id=f"{modal_key}-full",
                    **{"aria-label": "Full screen"},
                ),
                label="Full screen (Escape leaves it)",
            ),
        ],
        gap="xs",
    )


def register_markdown(app) -> None:
    @app.callback(
        Output({"type": ids.MD_TEXT, "id": MATCH}, "value"),
        Input({"type": ids.MD_INSERT, "id": MATCH, "kind": ALL}, "n_clicks"),
        State({"type": ids.MD_TEXT, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def insert_markdown(_clicks, value):
        triggered = dash_ctx.triggered_id
        if not triggered:
            return no_update
        snippet = MARKDOWN_SNIPPETS.get(triggered.get("kind"))
        if not snippet:
            return no_update
        current = value or ""
        separator = "" if not current else ("\n" if current.endswith("\n") else "\n\n")
        return f"{current}{separator}{snippet}"

    @app.callback(
        Output({"type": ids.MD_WRAP, "id": MATCH}, "className"),
        Input({"type": ids.MD_MODE, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def switch_markdown_mode(mode):
        mode = mode if mode in ("edit", "split", "preview") else "edit"
        return f"ea-markdown-editor mode-{mode}"

    @app.callback(
        Output({"type": ids.MD_PREVIEW, "id": MATCH}, "children"),
        Input({"type": ids.MD_TEXT, "id": MATCH}, "value"),
    )
    def preview_markdown(value):
        output_id = dash_ctx.outputs_list.get("id", {})
        editor_id = output_id.get("id", "markdown") if isinstance(output_id, dict) else "markdown"
        return markdown(value or "", f"md-preview-{editor_id}")


def kv_table(rows: list[tuple[str, Any]]) -> dmc.Table:
    return dmc.Table(
        [
            dmc.TableTbody(
                [
                    dmc.TableTr(
                        [
                            dmc.TableTd(dmc.Text(k, size="sm", c="dimmed")),
                            dmc.TableTd(v if _is_component(v) else dmc.Text(_fmt(v), size="sm")),
                        ]
                    )
                    for k, v in rows
                ]
            )
        ],
        withRowBorders=False,
        verticalSpacing="xs",
    )


def _is_component(v: Any) -> bool:
    return hasattr(v, "to_plotly_json")


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "" if v is None else str(v)


def simple_table(headers: list[str], rows: list[list[Any]], striped: bool = True) -> Any:
    """A table that scrolls inside its own card rather than pushing the page sideways.

    A model table is naturally wide — an identifier, a name, a type, two states. On a
    phone that width has to go somewhere, and the reader would rather pan one table than
    the whole document.
    """
    return dmc.TableScrollContainer(
        dmc.Table(
            [
                dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in headers])),
                dmc.TableTbody(
                    [
                        dmc.TableTr(
                            [dmc.TableTd(c if not isinstance(c, (str, int, float)) else _fmt(c)) for c in r]
                        )
                        for r in rows
                    ]
                ),
            ],
            striped=striped,
            highlightOnHover=True,
            withTableBorder=True,
            verticalSpacing="xs",
            fz="sm",
        ),
        minWidth=560,
    )


def issues_table(issues: list[Issue]) -> Any:
    if not issues:
        return dmc.Alert("No issues.", color="green", variant="light")
    rows = [
        [
            dmc.Badge(i.level, color=LEVEL_COLORS.get(i.level, "gray"), size="xs"),
            i.code,
            i.message,
            i.file or "",
            i.row or "",
            i.entity or "",
        ]
        for i in issues
    ]
    return simple_table(["level", "code", "message", "file", "row", "entity"], rows)


def alert(message: str, color: str = "blue", dismissible: bool = True) -> dmc.Alert:
    """A message the reader can close — unless it is the only thing on the screen saying
    why a control is refused, in which case closing it would leave the refusal unexplained."""
    return dmc.Alert(message, color=color, variant="light", withCloseButton=dismissible)


def error_alert(exc: Exception) -> dmc.Alert:
    return alert(str(exc), "red")


def page_title(
    title: str, subtitle: str | None = None, right: Any = None, subtitle_id: str = ""
) -> dmc.Group:
    left = dmc.Stack(
        [
            # The one h1 on the page: a document that starts at h2 gives assistive
            # technology no title to announce.
            dmc.Title(title, order=1, size="h2"),
            dmc.Text(subtitle, c="dimmed", size="sm", **({"id": subtitle_id} if subtitle_id else {}))
            if subtitle
            else None,
        ],
        gap=2,
    )
    return dmc.Group(
        [left, right] if right is not None else [left], justify="space-between", align="flex-start", mb="md"
    )


def empty(text: str) -> html.Div:
    return html.Div(dmc.Text(text, c="dimmed", size="sm"), style={"padding": "1rem 0"})


def keep_selected_option(
    options: list[dict[str, str]], value: str | None, previous: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """A Select shows nothing when its value has no option, so carry the selected one over."""
    if not value or any(o["value"] == value for o in options):
        return options
    selected = next((o for o in (previous or []) if o["value"] == value), None)
    return [selected, *options] if selected else options


def mermaid_block(block_id: str, code: str, arrangeable: bool = True) -> html.Div:
    """A generated diagram: the Mermaid source (hidden), the rendered SVG in a pan-and-zoom viewport,
    and, when arrangeable, a store of the shape positions that the draw.io export honours."""
    children: list[Any] = [
        html.Pre(code, id={"type": "mermaid-src", "id": block_id}, hidden=True),
        dcc.Store(id={"type": "mermaid-pos", "id": block_id}, data=None),
        dcc.Store(id={"type": "mermaid-view", "id": block_id}, data=None),
        html.Div(
            [
                _view_control("mermaid-zoom-out", block_id, "tabler:minus", "Zoom out"),
                _view_control("mermaid-zoom-in", block_id, "tabler:plus", "Zoom in"),
                _view_control("mermaid-fit", block_id, "tabler:arrows-maximize", "Fit to the window"),
                _view_control("mermaid-full", block_id, "tabler:maximize", "Full screen (Escape leaves it)"),
            ],
            className="ea-mermaid-controls",
        ),
        html.Div(id={"type": "mermaid-svg", "id": block_id}, className="ea-mermaid"),
    ]
    if arrangeable:
        children.append(
            dmc.Group(
                [
                    dmc.Text(
                        "Drag to pan, scroll to zoom, Ctrl-drag (Command on a Mac) to move a shape. Nothing is saved.",
                        size="xs",
                        c="dimmed",
                    ),
                    dmc.Button(
                        "Reset layout",
                        id={"type": "mermaid-reset", "id": block_id},
                        size="compact-xs",
                        variant="subtle",
                        color="gray",
                        leftSection=icon("tabler:refresh", 12),
                    ),
                ],
                gap="sm",
                mt=4,
            )
        )
    else:
        # The render callback declares this control as an Input; keep it in the tree, invisible.
        children.append(
            html.Div(
                dmc.Button("Reset layout", id={"type": "mermaid-reset", "id": block_id}),
                style={"display": "none"},
            )
        )
    return html.Div(children, className="ea-mermaid-frame")


def _view_control(kind: str, block_id: str, icon_name: str, label: str) -> dmc.Tooltip:
    return dmc.Tooltip(
        dmc.ActionIcon(
            icon(icon_name, 14),
            id={"type": kind, "id": block_id},
            variant="default",
            size="sm",
            # The tooltip describes the control once it is hovered; the name is what a
            # reader who cannot hover, or cannot see the icon, is given instead.
            **{"aria-label": label},
        ),
        label=label,
    )


def view_toolbar(
    md_id: str,
    drawio_id: str,
    note: str = "",
    copy_content: str | None = None,
    extra: list[Any] | None = None,
    md_reason: str = "",
    drawio_reason: str = "",
    note_id: str = "",
) -> dmc.Group:
    """Download (and optionally copy) buttons under a generated view or document.

    A reason disables the button it names and says why: a button that can produce nothing
    should not take the click and answer with silence.
    """
    items: list[Any] = []
    if copy_content is not None:
        items.append(
            dmc.Tooltip(
                dmc.Group(
                    [
                        dcc.Clipboard(content=copy_content, title="Copy Markdown", className="ea-clipboard"),
                        dmc.Text("Copy Markdown", size="xs", fw=500),
                    ],
                    gap=4,
                    className="ea-copy",
                ),
                label="Copy the whole document as Markdown",
            )
        )

    def download_button(label: str, button_id: str, reason: str) -> Any:
        return dmc.Button(
            label,
            id=button_id,
            size="xs",
            variant="light",
            leftSection=icon("tabler:download", 14),
            disabled=bool(reason),
        )

    items += [
        download_button("Download Markdown", md_id, md_reason),
        download_button("Download draw.io", drawio_id, drawio_reason),
        *(extra or []),
    ]
    # The note is beside the buttons, so a disabled one has its reason where a reader
    # looking at it is already looking. With an id, a callback can change it.
    if note or note_id:
        text = dmc.Text(note, size="xs", c="dimmed")
        items.append(html.Div(text, id=note_id) if note_id else text)
    return dmc.Group(items, gap="sm", mt="xs", align="center")
